"""Assemble a world graph from what PortWatch already knows.

Every node and edge here comes from an existing catalogue: the trade lanes and
their chokepoint routings, the port registry, the carrier's fleet, the Global
Eye event register. Nothing is invented for the graph's benefit, which is the
property that makes a cascade over it worth reading -- and the reason this
module is separate from the engine, so it is obvious where the world's contents
come from.

The mapping is deliberately literal:

    GlobalEvent          -> event node, threatens each chokepoint it names
    chokepoint           -> chokepoint node, transited by each lane that uses it
    TradeLane            -> lane node carrying its detour, serving its ports
    FleetVessel          -> vessel node, sails its lane, bound for its port
    PortRecord           -> port node carrying its capacity index
    Shipment             -> cargo node carried by its vessel

An event's lifetime is its horizon, so a cascade run at ``now + 96h`` does not
pick up a 72-hour claim that has since lapsed. That is what makes the time
scrubber a query against this graph rather than a second forecasting system.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.portwatch_os.global_eye.exposure import (
    DEFAULT_SERVICE_KN,
    TRADE_LANES,
    TradeLane,
    VesselVoyage,
)
from src.portwatch_os.global_eye.ingest import CHOKEPOINT_NAMES
from src.portwatch_os.global_eye.model import GlobalEvent, parse_time
from src.portwatch_os.world.graph import (
    BOUND_FOR,
    CARGO,
    CARRIES,
    CHOKEPOINT,
    EVENT,
    Edge,
    LANE,
    Node,
    PORT,
    SAILS,
    SERVES,
    THREATENS,
    TRANSITS,
    VESSEL,
    WorldGraph,
    key,
)
from src.portwatch_os.world.quantity import ALWAYS, Interval, Quantity, RISK, utc, window
from src.utils import port_registry

#: Where a fact came from, recorded on the edge for Evidence Mode.
SOURCE_LANE_CATALOGUE = "src.portwatch_os.global_eye.exposure.TRADE_LANES"
SOURCE_PORT_REGISTRY = "src.utils.port_registry"
SOURCE_EVENT_REGISTER = "src.portwatch_os.global_eye.ingest"
SOURCE_FLEET = "src.portwatch_os.fleet.company"


def build_world(
    *,
    events: Sequence[GlobalEvent] = (),
    voyages: Sequence[VesselVoyage] = (),
    lanes: Optional[Dict[str, TradeLane]] = None,
    port_codes: Optional[Iterable[str]] = None,
    now: Optional[datetime] = None,
) -> WorldGraph:
    """Build the graph. Every argument is optional; each adds a layer."""
    graph = WorldGraph()
    moment = utc(now)
    catalogue = TRADE_LANES if lanes is None else lanes

    _add_ports(graph, port_codes)
    _add_lanes(graph, catalogue)
    _add_events(graph, events, moment)
    _add_voyages(graph, voyages, catalogue, moment)
    return graph


# --------------------------------------------------------------------------
# layers
# --------------------------------------------------------------------------


def _add_ports(graph: WorldGraph, port_codes: Optional[Iterable[str]]) -> None:
    records = (
        port_registry.all_ports()
        if port_codes is None
        else [r for r in (port_registry.resolve(c) for c in port_codes) if r]
    )
    for record in records:
        graph.add_node(
            Node(
                key=key(PORT, record.locode),
                kind=PORT,
                label=record.name,
                attrs={
                    # The capacity index is what turns arrival bunching into
                    # yard pressure downstream. A port without one produces a
                    # refusal there rather than a fabricated percentage.
                    "capacity": record.capacity,
                    "berth_count": record.berth_count,
                    "connectivity": record.connectivity,
                    "authority": record.authority,
                    "lat": record.lat,
                    "lon": record.lon,
                    "coast": record.coast,
                },
            )
        )


def _add_lanes(graph: WorldGraph, catalogue: Dict[str, TradeLane]) -> None:
    for lane in catalogue.values():
        detour_nm = lane.detour_nm
        detour_hours = (
            None if detour_nm is None else detour_nm / DEFAULT_SERVICE_KN
        )
        graph.add_node(
            Node(
                key=key(LANE, lane.code),
                kind=LANE,
                label=lane.name,
                attrs={
                    "detour_nm": detour_nm,
                    "detour_hours": detour_hours,
                    "alternative": lane.alternative,
                    "primary_nm": lane.primary_nm,
                    "chokepoints": list(lane.chokepoints),
                },
            )
        )

        for code in lane.chokepoints:
            chokepoint_key = key(CHOKEPOINT, code)
            if chokepoint_key not in graph:
                graph.add_node(
                    Node(
                        key=chokepoint_key,
                        kind=CHOKEPOINT,
                        label=CHOKEPOINT_NAMES.get(code, code),
                        attrs={"code": code},
                    )
                )
            # A lane transiting a strait is a routing fact, so the coefficient
            # is 1.0 and the direction runs chokepoint -> lane: risk flows to
            # the traffic, not the other way about.
            graph.add_edge(
                Edge(
                    src=chokepoint_key,
                    dst=key(LANE, lane.code),
                    kind=TRANSITS,
                    weight=1.0,
                    source=SOURCE_LANE_CATALOGUE,
                )
            )

        for port_code in lane.india_ports:
            port_key = key(PORT, port_code)
            if port_key in graph:
                graph.add_edge(
                    Edge(
                        src=key(LANE, lane.code),
                        dst=port_key,
                        kind=SERVES,
                        weight=1.0,
                        source=SOURCE_LANE_CATALOGUE,
                    )
                )


def _add_events(
    graph: WorldGraph, events: Sequence[GlobalEvent], now: datetime
) -> None:
    for event in events:
        first_seen = parse_time(event.first_seen) or now
        # The event's lifetime is its claim horizon. Past it, a cascade run at a
        # later instant will not pick it up -- which is what stops a stale claim
        # quietly contributing to a future projection.
        interval = window(utc(first_seen), event.horizon_hours)
        graph.add_node(
            Node(
                key=key(EVENT, event.event_id),
                kind=EVENT,
                label=event.title,
                interval=interval,
                attrs={
                    "category": event.category,
                    "severity": event.severity,
                    "confidence": event.confidence,
                    "probability": event.probability,
                    "region": event.region,
                    "lat": event.lat,
                    "lon": event.lon,
                    "source_count": event.source_count,
                    "claim": event.claim,
                    "horizon_hours": event.horizon_hours,
                },
            )
        )

        for code in event.chokepoints:
            chokepoint_key = key(CHOKEPOINT, code)
            if chokepoint_key not in graph:
                graph.add_node(
                    Node(
                        key=chokepoint_key,
                        kind=CHOKEPOINT,
                        label=CHOKEPOINT_NAMES.get(code, code),
                        attrs={"code": code},
                    )
                )
            graph.add_edge(
                Edge(
                    src=key(EVENT, event.event_id),
                    dst=chokepoint_key,
                    kind=THREATENS,
                    # The classifier's corroborated confidence that this event
                    # bears on this chokepoint. Severity is carried by the seed
                    # quantity, not doubled up here.
                    weight=max(0.05, min(1.0, event.confidence or 0.5)),
                    interval=interval,
                    source=SOURCE_EVENT_REGISTER,
                )
            )


def _add_voyages(
    graph: WorldGraph,
    voyages: Sequence[VesselVoyage],
    catalogue: Dict[str, TradeLane],
    now: datetime,
) -> None:
    for voyage in voyages:
        vessel_key = key(VESSEL, voyage.vessel_id)
        graph.add_node(
            Node(
                key=vessel_key,
                kind=VESSEL,
                label=voyage.name,
                attrs={
                    "lane_code": voyage.lane_code,
                    "destination_port": voyage.destination_port,
                    "eta": voyage.eta,
                    "service_speed_kn": voyage.service_speed_kn,
                    "operator": voyage.operator,
                },
            )
        )

        lane = catalogue.get(voyage.lane_code or "")
        if lane is not None:
            lane_key = key(LANE, lane.code)
            detour_nm = lane.detour_nm
            detour_hours = (
                None if detour_nm is None else detour_nm / max(1.0, voyage.service_speed_kn)
            )
            # The vessel carries the lane's detour, because the delay it would
            # take is a function of its own speed, not the lane's nominal one.
            node = graph.require(vessel_key)
            graph.add_node(
                Node(
                    key=vessel_key,
                    kind=VESSEL,
                    label=node.label,
                    interval=node.interval,
                    attrs={**node.attrs, "detour_hours": detour_hours,
                           "detour_nm": detour_nm},
                )
            )
            # One edge per (lane, vessel), carrying the timing at every strait
            # the lane transits. An edge per chokepoint would apply the lane's
            # risk once for each of them, counting one hull several times and
            # inflating its exposure by the length of its own routing.
            graph.add_edge(
                Edge(
                    src=lane_key,
                    dst=vessel_key,
                    kind=SAILS,
                    weight=1.0,
                    attrs={
                        # The timing that decides whether this vessel is exposed
                        # and whether it can still act. A chokepoint missing from
                        # this map makes the transfer decline rather than guess.
                        "hours_to_chokepoint": {
                            code: voyage.hours_to_chokepoint.get(code)
                            for code in lane.chokepoints
                            if voyage.hours_to_chokepoint.get(code) is not None
                        },
                    },
                    source=SOURCE_FLEET,
                )
            )

        port_key = key(PORT, voyage.destination_port or "")
        if voyage.destination_port and port_key in graph:
            graph.add_edge(
                Edge(
                    src=vessel_key,
                    dst=port_key,
                    kind=BOUND_FOR,
                    weight=1.0,
                    attrs={"eta": voyage.eta},
                    source=SOURCE_FLEET,
                )
            )


# --------------------------------------------------------------------------
# seeds
# --------------------------------------------------------------------------


def seed_for(event: GlobalEvent) -> Quantity:
    """The claim a cascade starts from, taken from the event itself.

    Severity is the magnitude and corroborated confidence is the confidence, so
    a loudly-reported minor incident and a quietly-reported major one are not
    conflated. Where calibration has produced a probability, it is preferred to
    the raw severity -- a calibrated number has earned the right to be one.
    """
    magnitude = (
        event.probability if event.probability is not None else event.severity
    )
    return Quantity(
        value=float(magnitude or 0.0),
        unit=RISK,
        confidence=float(event.confidence or 0.0),
        attrs={
            "event_id": event.event_id,
            "category": event.category,
            "calibrated": event.probability is not None,
        },
    )


__all__ = [
    "SOURCE_EVENT_REGISTER",
    "SOURCE_FLEET",
    "SOURCE_LANE_CATALOGUE",
    "SOURCE_PORT_REGISTRY",
    "build_world",
    "seed_for",
]
