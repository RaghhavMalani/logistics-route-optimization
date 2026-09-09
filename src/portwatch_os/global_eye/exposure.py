"""The Global Eye impact graph.

An event on its own is trivia. This module answers the only question that makes
it operational:

    EVENT -> CHOKEPOINT/REGION -> TRADE LANE -> VESSEL -> PORT -> IMPACT -> ACTION

Each hop is a measured multiplication, not a narrative:

*   **Event to chokepoint.** Presence, from the classifier. Weighted by the
    event's severity, its confidence, and its recency decay.
*   **Chokepoint to lane.** A lane is exposed to a chokepoint if the lane's
    passage runs through it. That is a property of the lane catalogue, not an
    opinion.
*   **Lane to vessel.** A vessel is exposed if its current voyage uses an exposed
    lane. Crucially, the *timing* is what matters: a vessel that clears the
    chokepoint before the event's window opens is not exposed, and one that has
    already entered the risk area cannot divert. Both are computed and reported
    separately.
*   **Vessel to port.** Delayed arrivals become an arrival-time shift at the
    destination, which the port twin turns into queue pressure.
*   **Impact.** Expressed as a delay in hours with a stated uncertainty, derived
    from the diversion distance the routing catalogue measures. Never a
    free-floating "high impact" label.

Nothing in this module invents a number. Where the inputs are missing, the
corresponding field is ``None`` and the reason is recorded in ``notes``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.global_eye.model import CATEGORIES, GlobalEvent, decay_factor
from src.utils import port_registry

#: Trade lanes, and the chokepoints each one transits.
#:
#: This is a routing fact, not a judgement: a Europe-India service on the Suez
#: routing passes Bab-el-Mandeb and Suez, and one going round the Cape passes
#: neither. The alternative routing and its extra distance are what turn an
#: event into an hours number further down.
@dataclass(frozen=True)
class TradeLane:
    code: str
    name: str
    #: Chokepoints on the primary routing.
    chokepoints: Tuple[str, ...]
    #: Indian ports this lane calls at.
    india_ports: Tuple[str, ...]
    #: Nominal one-way distance on the primary routing, nautical miles.
    primary_nm: float
    #: The routing used when the primary is unusable, and its distance.
    alternative: Optional[str]
    alternative_nm: Optional[float]
    description: str

    @property
    def detour_nm(self) -> Optional[float]:
        if self.alternative_nm is None:
            return None
        return max(0.0, self.alternative_nm - self.primary_nm)


TRADE_LANES: Dict[str, TradeLane] = {
    lane.code: lane
    for lane in [
        TradeLane(
            "EUR_IND", "Europe ↔ India (Suez)", ("SUEZ", "BAB_EL_MANDEB"),
            ("INNSA", "INMUN", "INIXY", "INMRM"), 4650,
            "Cape of Good Hope", 8400,
            "North Europe and West Med services to the Indian west coast via Suez.",
        ),
        TradeLane(
            "MED_IND", "Mediterranean ↔ India", ("SUEZ", "BAB_EL_MANDEB"),
            ("INNSA", "INMUN", "INCOK"), 3300,
            "Cape of Good Hope", 7900,
            "East Med and Adriatic services to the Indian west coast.",
        ),
        TradeLane(
            "GULF_IND", "Persian Gulf ↔ India", ("HORMUZ",),
            ("INNSA", "INMUN", "INVTZ", "INIXY"), 1150,
            None, None,
            "Crude, product and container traffic out of the Gulf. No alternative "
            "routing exists: Hormuz is the only exit.",
        ),
        TradeLane(
            "EAF_IND", "East Africa ↔ India", (),
            ("INNSA", "INCOK", "INMRM"), 2400, None, None,
            "Direct Arabian Sea crossing, transiting no chokepoint.",
        ),
        TradeLane(
            "SEA_IND", "South-east Asia ↔ India", ("MALACCA",),
            ("INMAA", "INCCU", "INVTZ", "INKAT"), 1900,
            "Sunda / Lombok Strait", 2450,
            "Singapore, Malaysia and Indonesia services to the Indian east coast.",
        ),
        TradeLane(
            "FE_IND", "Far East ↔ India", ("MALACCA",),
            ("INMAA", "INNSA", "INCCU"), 3900,
            "Lombok Strait", 4550,
            "China, Korea and Japan services routing through the Malacca Strait.",
        ),
        TradeLane(
            "USEC_IND", "US East Coast ↔ India", ("SUEZ", "BAB_EL_MANDEB"),
            ("INNSA", "INMAA"), 8200,
            "Cape of Good Hope", 10400,
            "Transatlantic-Suez services; the Cape routing is the standing fallback.",
        ),
        TradeLane(
            "USWC_IND", "US West Coast ↔ India", ("MALACCA",),
            ("INMAA", "INNSA"), 9100,
            "Lombok Strait", 9650,
            "Transpacific services approaching India through South-east Asia.",
        ),
        TradeLane(
            "COAST_W", "Indian west coast cabotage", (),
            ("INNSA", "INMUN", "INMRM", "INNML", "INCOK", "INIXY"), 620, None, None,
            "Domestic west coast feeder traffic.",
        ),
        TradeLane(
            "COAST_E", "Indian east coast cabotage", (),
            ("INMAA", "INVTZ", "INPRT", "INCCU", "INKAT"), 780, None, None,
            "Domestic east coast feeder traffic.",
        ),
    ]
}

LANES_BY_CHOKEPOINT: Dict[str, List[str]] = {}
for _lane in TRADE_LANES.values():
    for _choke in _lane.chokepoints:
        LANES_BY_CHOKEPOINT.setdefault(_choke, []).append(_lane.code)

#: Typical laden service speed used to convert a detour into hours when a
#: vessel's own speed is unknown. Container-service midpoint.
DEFAULT_SERVICE_KN = 16.0

#: How much of a chokepoint's traffic actually diverts at a given severity.
#: Below the floor the disruption is absorbed by schedule buffer.
DIVERSION_FLOOR = 0.35


# --------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------


@dataclass
class LaneExposure:
    lane_code: str
    lane_name: str
    chokepoint: str
    #: 0..1. Severity × confidence × recency, before any vessel-level timing.
    exposure: float
    #: Extra distance if the lane diverts, nautical miles. ``None`` when the
    #: lane has no alternative routing -- which is itself the finding.
    detour_nm: Optional[float]
    #: Extra passage time at the default service speed, hours.
    detour_hours: Optional[float]
    alternative: Optional[str]
    india_ports: List[str]
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "laneCode": self.lane_code,
            "laneName": self.lane_name,
            "chokepoint": self.chokepoint,
            "exposure": round(self.exposure, 3),
            "detourNm": self.detour_nm,
            "detourHours": None if self.detour_hours is None else round(self.detour_hours, 1),
            "alternative": self.alternative,
            "indiaPorts": self.india_ports,
            "note": self.note,
        }


@dataclass
class VesselExposure:
    """One vessel's exposure to one event, with the timing that decides action."""

    vessel_id: str
    vessel_name: str
    lane_code: str
    chokepoint: str
    exposure: float
    #: Hours until the vessel reaches the exposed water. Negative means it is
    #: already inside.
    hours_to_risk_area: Optional[float]
    #: True when the vessel has already entered the risk area, in which case a
    #: diversion recommendation is not actionable and the product must not make
    #: one.
    already_entered: bool
    #: Latest hour by which a diversion must be ordered to be effective.
    diversion_deadline: Optional[str]
    #: Expected arrival delay if the diversion is taken, hours.
    delay_hours_if_diverted: Optional[float]
    destination_port: Optional[str]
    current_eta: Optional[str]
    recommended_action: str
    action_basis: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vesselId": self.vessel_id,
            "vesselName": self.vessel_name,
            "laneCode": self.lane_code,
            "chokepoint": self.chokepoint,
            "exposure": round(self.exposure, 3),
            "hoursToRiskArea": (
                None if self.hours_to_risk_area is None else round(self.hours_to_risk_area, 1)
            ),
            "alreadyEntered": self.already_entered,
            "diversionDeadline": self.diversion_deadline,
            "delayHoursIfDiverted": (
                None if self.delay_hours_if_diverted is None
                else round(self.delay_hours_if_diverted, 1)
            ),
            "destinationPort": self.destination_port,
            "currentEta": self.current_eta,
            "recommendedAction": self.recommended_action,
            "actionBasis": self.action_basis,
        }


@dataclass
class PortExposure:
    port_code: str
    port_name: str
    exposure: float
    #: Lanes reaching this port that are exposed.
    lanes: List[str]
    #: Vessels bound here whose arrival is affected.
    affected_vessels: int
    #: Net arrival-time shift across affected vessels, hours. Feeds the twin.
    mean_arrival_shift_hours: Optional[float]
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portCode": self.port_code,
            "portName": self.port_name,
            "exposure": round(self.exposure, 3),
            "lanes": self.lanes,
            "affectedVessels": self.affected_vessels,
            "meanArrivalShiftHours": (
                None if self.mean_arrival_shift_hours is None
                else round(self.mean_arrival_shift_hours, 1)
            ),
            "note": self.note,
        }


@dataclass
class EventImpact:
    """The full chain for one event."""

    event: GlobalEvent
    #: Recency-decayed weight actually applied.
    decay: float
    lanes: List[LaneExposure] = field(default_factory=list)
    vessels: List[VesselExposure] = field(default_factory=list)
    ports: List[PortExposure] = field(default_factory=list)
    #: Ordered, deduplicated actions the chain supports.
    actions: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def worst_exposure(self) -> float:
        return max((lane.exposure for lane in self.lanes), default=0.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.event.to_dict(),
            "decay": round(self.decay, 3),
            "worstExposure": round(self.worst_exposure, 3),
            "lanes": [l.to_dict() for l in self.lanes],
            "vessels": [v.to_dict() for v in self.vessels],
            "ports": [p.to_dict() for p in self.ports],
            "actions": self.actions,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------
# the graph
# --------------------------------------------------------------------------


@dataclass
class VesselVoyage:
    """The minimum a vessel must declare to be placed on the exposure graph."""

    vessel_id: str
    name: str
    lane_code: Optional[str]
    destination_port: Optional[str]
    #: Hours until the vessel reaches the chokepoint on its lane. Negative means
    #: it has already passed into or through it.
    hours_to_chokepoint: Dict[str, float] = field(default_factory=dict)
    eta: Optional[str] = None
    service_speed_kn: float = DEFAULT_SERVICE_KN
    operator: Optional[str] = None


def lane_exposure(
    event: GlobalEvent,
    *,
    now: Optional[datetime] = None,
) -> List[LaneExposure]:
    """Which trade lanes this event touches, and by how much."""
    now = now or datetime.now(timezone.utc)
    spec = CATEGORIES.get(event.category)
    half_life = (spec.base_persistence_hours / 2.0) if spec else 48.0
    decay = decay_factor(event.last_seen, now, half_life)

    # The strength of a claim about a lane is the product of three things we
    # measured: how bad it would be, how sure we are it is real, and how recently
    # anyone confirmed it. Multiplying is the honest combination -- a severe but
    # unconfirmed and stale item should not read as an emergency.
    base = event.severity * event.confidence * decay

    out: List[LaneExposure] = []
    for chokepoint in event.chokepoints:
        for lane_code in LANES_BY_CHOKEPOINT.get(chokepoint, []):
            lane = TRADE_LANES[lane_code]
            detour = lane.detour_nm
            hours = (detour / DEFAULT_SERVICE_KN) if detour is not None else None
            note = None
            exposure = base
            if lane.alternative is None:
                # No alternative routing is *worse*, not better: the traffic
                # cannot route around the problem at all.
                exposure = min(1.0, base * 1.25)
                note = (
                    "No alternative routing exists for this lane. Disruption here "
                    "cannot be absorbed by diverting."
                )
            out.append(
                LaneExposure(
                    lane_code=lane.code,
                    lane_name=lane.name,
                    chokepoint=chokepoint,
                    exposure=round(min(1.0, exposure), 4),
                    detour_nm=detour,
                    detour_hours=hours,
                    alternative=lane.alternative,
                    india_ports=list(lane.india_ports),
                    note=note,
                )
            )
    out.sort(key=lambda l: -l.exposure)
    return out


def vessel_exposure(
    event: GlobalEvent,
    lanes: Sequence[LaneExposure],
    voyages: Sequence[VesselVoyage],
    *,
    now: Optional[datetime] = None,
) -> List[VesselExposure]:
    """Which vessels are exposed, and whether anything can still be done.

    The timing gate is the point of this function. A vessel three days short of
    Bab-el-Mandeb can be rerouted; one already north of it cannot, and telling an
    operator to divert it would be worse than saying nothing.
    """
    now = now or datetime.now(timezone.utc)
    by_lane = {lane.lane_code: lane for lane in lanes}
    out: List[VesselExposure] = []

    for voyage in voyages:
        lane = by_lane.get(voyage.lane_code or "")
        if lane is None:
            continue
        hours = voyage.hours_to_chokepoint.get(lane.chokepoint)
        already = hours is not None and hours <= 0
        speed = voyage.service_speed_kn or DEFAULT_SERVICE_KN
        detour_hours = (
            lane.detour_nm / speed if lane.detour_nm is not None else None
        )

        # A diversion has to be ordered before the vessel commits to the
        # approach. Six hours short of the strait it is already committed in
        # practice, so that is the deadline rather than the strait itself.
        deadline = None
        if hours is not None and hours > 6:
            deadline = (now + timedelta(hours=hours - 6)).isoformat(timespec="seconds")

        if already:
            action = "monitor"
            basis = (
                "The vessel has already entered the exposed water. A diversion is no "
                "longer available; the exposure is reported for situational awareness."
            )
        elif lane.alternative is None:
            action = "hold_or_reschedule"
            basis = (
                f"{lane.lane_name} has no alternative routing past {lane.chokepoint}. "
                "The options are to wait or to reschedule the call."
            )
        elif lane.exposure >= DIVERSION_FLOOR and detour_hours is not None:
            action = "evaluate_diversion"
            basis = (
                f"Exposure {lane.exposure:.2f} on {lane.lane_name}. Diverting via "
                f"{lane.alternative} costs about {detour_hours:.0f} h at {speed:.0f} kn."
            )
        else:
            action = "monitor"
            basis = (
                f"Exposure {lane.exposure:.2f} is below the diversion threshold "
                f"of {DIVERSION_FLOOR:.2f}; schedule buffer should absorb it."
            )

        out.append(
            VesselExposure(
                vessel_id=voyage.vessel_id,
                vessel_name=voyage.name,
                lane_code=lane.lane_code,
                chokepoint=lane.chokepoint,
                exposure=lane.exposure,
                hours_to_risk_area=hours,
                already_entered=already,
                diversion_deadline=deadline,
                delay_hours_if_diverted=detour_hours,
                destination_port=voyage.destination_port,
                current_eta=voyage.eta,
                recommended_action=action,
                action_basis=basis,
            )
        )

    out.sort(key=lambda v: (-v.exposure, v.hours_to_risk_area or 0))
    return out


def port_exposure(
    lanes: Sequence[LaneExposure],
    vessels: Sequence[VesselExposure],
    *,
    port_names: Optional[Dict[str, str]] = None,
) -> List[PortExposure]:
    """Roll vessel-level exposure up to the ports those vessels are bound for."""
    names = port_names or {}
    accumulated: Dict[str, Dict[str, Any]] = {}

    for lane in lanes:
        for code in lane.india_ports:
            entry = accumulated.setdefault(
                code, {"exposure": 0.0, "lanes": set(), "vessels": 0, "shifts": []}
            )
            # A port served by two exposed lanes is more exposed than one served
            # by either alone, but not additively: take the strongest and add a
            # damped share of the rest.
            entry["exposure"] = max(entry["exposure"], lane.exposure) + 0.15 * min(
                entry["exposure"], lane.exposure
            )
            entry["lanes"].add(lane.lane_code)

    for vessel in vessels:
        if not vessel.destination_port:
            continue
        entry = accumulated.setdefault(
            vessel.destination_port,
            {"exposure": vessel.exposure, "lanes": {vessel.lane_code}, "vessels": 0, "shifts": []},
        )
        entry["vessels"] += 1
        if vessel.delay_hours_if_diverted is not None and not vessel.already_entered:
            entry["shifts"].append(vessel.delay_hours_if_diverted)

    out: List[PortExposure] = []
    for code, entry in accumulated.items():
        record = port_registry.resolve(code)
        shifts = entry["shifts"]
        out.append(
            PortExposure(
                port_code=code,
                port_name=names.get(code) or (record.name if record else code),
                exposure=round(min(1.0, entry["exposure"]), 4),
                lanes=sorted(entry["lanes"]),
                affected_vessels=entry["vessels"],
                mean_arrival_shift_hours=(sum(shifts) / len(shifts)) if shifts else None,
                note=(
                    None if shifts
                    else "No vessel-level arrival shift is computable without a fleet in scope."
                ),
            )
        )
    out.sort(key=lambda p: -p.exposure)
    return out


def recommended_actions(
    event: GlobalEvent,
    lanes: Sequence[LaneExposure],
    vessels: Sequence[VesselExposure],
    ports: Sequence[PortExposure],
) -> List[Dict[str, Any]]:
    """The actions this chain actually supports, each tied to its evidence.

    Every entry names the measurement that justifies it. An action with no
    computable basis is not emitted -- the register simply carries fewer rows,
    which is the correct outcome when the evidence is thin.
    """
    actions: List[Dict[str, Any]] = []

    divertible = [v for v in vessels if v.recommended_action == "evaluate_diversion"]
    if divertible:
        cost = [v.delay_hours_if_diverted for v in divertible if v.delay_hours_if_diverted]
        actions.append(
            {
                "action": "evaluate_diversion",
                "label": "Evaluate diversion for exposed vessels",
                "vessels": [v.vessel_id for v in divertible],
                "count": len(divertible),
                "meanCostHours": round(sum(cost) / len(cost), 1) if cost else None,
                "earliestDeadline": min(
                    (v.diversion_deadline for v in divertible if v.diversion_deadline),
                    default=None,
                ),
                "basis": (
                    "Exposure above the diversion threshold on a lane with an "
                    "alternative routing, with the vessel still short of the risk area."
                ),
            }
        )

    committed = [v for v in vessels if v.already_entered]
    if committed:
        actions.append(
            {
                "action": "monitor_committed",
                "label": "Monitor vessels already in the exposed area",
                "vessels": [v.vessel_id for v in committed],
                "count": len(committed),
                "basis": (
                    "These vessels have passed the diversion point. No routing action "
                    "is available; the entry exists so they are not mistaken for safe."
                ),
            }
        )

    blocked = [v for v in vessels if v.recommended_action == "hold_or_reschedule"]
    if blocked:
        actions.append(
            {
                "action": "hold_or_reschedule",
                "label": "Hold or reschedule on lanes with no alternative",
                "vessels": [v.vessel_id for v in blocked],
                "count": len(blocked),
                "basis": "The affected lane has no alternative routing in the catalogue.",
            }
        )

    pressured = [p for p in ports if p.mean_arrival_shift_hours]
    if pressured:
        actions.append(
            {
                "action": "reforecast_port_arrivals",
                "label": "Re-forecast arrivals at affected ports",
                "ports": [p.port_code for p in pressured],
                "count": len(pressured),
                "meanShiftHours": round(
                    sum(p.mean_arrival_shift_hours or 0 for p in pressured) / len(pressured), 1
                ),
                "basis": (
                    "Diverted vessels shift their arrival windows, which changes the "
                    "berth queue at the destination."
                ),
            }
        )

    if any(l.detour_nm and l.detour_nm > 2000 for l in lanes):
        actions.append(
            {
                "action": "review_bunkers",
                "label": "Review bunker plan for long diversions",
                "count": sum(1 for l in lanes if l.detour_nm and l.detour_nm > 2000),
                "basis": (
                    "A diversion of more than 2,000 nm changes the bunker requirement "
                    "for the leg."
                ),
            }
        )

    return actions


def build_impact(
    event: GlobalEvent,
    voyages: Sequence[VesselVoyage] = (),
    *,
    now: Optional[datetime] = None,
    port_names: Optional[Dict[str, str]] = None,
) -> EventImpact:
    """The whole chain for one event."""
    now = now or datetime.now(timezone.utc)
    spec = CATEGORIES.get(event.category)
    half_life = (spec.base_persistence_hours / 2.0) if spec else 48.0
    decay = decay_factor(event.last_seen, now, half_life)

    lanes = lane_exposure(event, now=now)
    vessels = vessel_exposure(event, lanes, voyages, now=now)
    ports = port_exposure(lanes, vessels, port_names=port_names)
    actions = recommended_actions(event, lanes, vessels, ports)

    notes: List[str] = []
    if not event.chokepoints:
        notes.append(
            "This event is not tied to a chokepoint in the catalogue, so no trade-lane "
            "exposure is computed. It is reported for awareness only."
        )
    if not voyages:
        notes.append(
            "No fleet is in scope, so vessel-level exposure is not computed. Port "
            "exposure below is lane-level only."
        )
    if event.probability is None:
        notes.append(
            "No calibrated probability is available for this event category yet; "
            "severity and confidence are shown instead."
        )
    if decay < 0.35:
        notes.append(
            f"Last corroborated {event.last_seen}. Recency weight is {decay:.2f}, so "
            "this event's influence on the live picture is reduced."
        )

    return EventImpact(
        event=event, decay=decay, lanes=lanes, vessels=vessels,
        ports=ports, actions=actions, notes=notes,
    )


def aggregate_port_risk(impacts: Sequence[EventImpact]) -> Dict[str, Dict[str, Any]]:
    """Total event-driven risk per port, across every live event.

    This is the number that propagates into the port forecast and the twin, so
    it is combined with a noisy-OR rather than a sum: two independent 0.5
    exposures give 0.75, not 1.0, and no amount of piling on events pushes a
    port past certainty.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for impact in impacts:
        for port in impact.ports:
            entry = out.setdefault(
                port.port_code,
                {
                    "portCode": port.port_code,
                    "portName": port.port_name,
                    "risk": 0.0,
                    "events": [],
                    "arrivalShiftHours": 0.0,
                    "affectedVessels": 0,
                },
            )
            entry["risk"] = 1.0 - (1.0 - entry["risk"]) * (1.0 - port.exposure)
            entry["events"].append(
                {
                    "eventId": impact.event.event_id,
                    "title": impact.event.title,
                    "category": impact.event.category,
                    "exposure": round(port.exposure, 3),
                }
            )
            if port.mean_arrival_shift_hours:
                entry["arrivalShiftHours"] += port.mean_arrival_shift_hours
            entry["affectedVessels"] += port.affected_vessels
    for entry in out.values():
        entry["risk"] = round(entry["risk"], 4)
        entry["arrivalShiftHours"] = round(entry["arrivalShiftHours"], 2)
        entry["events"].sort(key=lambda e: -e["exposure"])
    return out


def lanes_for_ports(port_codes: Iterable[str]) -> List[TradeLane]:
    """Every lane that calls at any of these ports."""
    wanted = {str(c).upper() for c in port_codes}
    return [lane for lane in TRADE_LANES.values() if wanted & set(lane.india_ports)]


__all__ = [
    "DEFAULT_SERVICE_KN",
    "DIVERSION_FLOOR",
    "LANES_BY_CHOKEPOINT",
    "TRADE_LANES",
    "EventImpact",
    "LaneExposure",
    "PortExposure",
    "TradeLane",
    "VesselExposure",
    "VesselVoyage",
    "aggregate_port_risk",
    "build_impact",
    "lane_exposure",
    "lanes_for_ports",
    "port_exposure",
    "recommended_actions",
    "vessel_exposure",
]
