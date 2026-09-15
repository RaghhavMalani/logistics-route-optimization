"""Observed vessels into the world graph, with the confidence each step earned.

A replay vessel arrives in the graph knowing its lane, its destination and its
hours to every chokepoint, because the replay wrote them. An observed vessel
arrives knowing where it is, how fast it is going, which way it is pointing and
-- if a static report has been heard and a crew member typed something -- a
destination string. Everything else has to be derived, and every derivation
here carries the confidence it deserves so that a cascade built on an observed
hull is discounted by exactly how much was inferred.

Three derivations, in decreasing confidence:

*   **Destination** from the typed field, graded by the resolver: a LOCODE is
    0.9, a name 0.7, anything else unresolved and therefore no port edge.
*   **Lane** from the destination's coast and the vessel's position: a hull in
    the Gulf of Aden bound for Nhava Sheva is on the Suez lane. Where the
    position is ambiguous between lanes the vessel gets no lane and no
    chokepoint exposure, rather than a guessed one.
*   **Hours to chokepoint** from great-circle distance over speed over ground,
    only when the vessel is moving and pointing towards the strait. A vessel
    pointing away has passed it, and is recorded as such (negative hours).

A vessel the derivations cannot place still enters the graph, as a node with
its observed position and a destination of ``None``. It is on the chart and in
the inspector; it just does not transmit consequence it has not earned.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.portwatch_os.fusion.destination import resolve_destination
from src.portwatch_os.fusion.engine import FusionEngine
from src.portwatch_os.fusion.model import (
    ATTR_DESTINATION,
    ATTR_ETA,
    ATTR_POSITION,
    CanonicalVessel,
    OBSERVED_AIS,
)
from src.portwatch_os.global_eye.exposure import TRADE_LANES, VesselVoyage
from src.portwatch_os.global_eye.ingest import CHOKEPOINT_GEO
from src.utils import port_registry
from src.portwatch_os.clock import world_now

SOURCE_OBSERVED_AIS = "OBSERVED_AIS"

#: Below this speed a vessel is not making way and no ETA is derived.
MIN_SOG_FOR_ETA_KN = 0.5
#: A course more than this off the bearing to a chokepoint means the vessel
#: is not heading for it.
MAX_OFF_BEARING_DEG = 60.0
#: Confidence that the position-and-destination lane inference is right.
LANE_CONFIDENCE = 0.6
#: Confidence in an hours-to-chokepoint figure from SOG and a straight line.
TIMING_CONFIDENCE = 0.5

EARTH_NM = 3440.065


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_NM * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def _off_bearing(course: float, bearing: float) -> float:
    return abs((course - bearing + 180.0) % 360.0 - 180.0)


# --------------------------------------------------------------------------
# lane inference
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Region:
    code: str
    lat: Tuple[float, float]
    lon: Tuple[float, float]
    #: Lanes a vessel here, bound for an Indian port, is plausibly on.
    lanes: Tuple[str, ...]


#: Sea regions of the subscription box and the lanes that cross them. Coarse
#: on purpose: the point is to refuse an ambiguous placement, not to route.
REGIONS: Tuple[Region, ...] = (
    Region("PERSIAN_GULF", (23.5, 30.5), (48.0, 56.5), ("GULF_IND",)),
    Region("GULF_OF_OMAN", (22.0, 26.5), (56.5, 62.0), ("GULF_IND",)),
    Region("RED_SEA", (12.5, 30.0), (32.0, 44.0), ("EUR_IND", "MED_IND", "USEC_IND")),
    Region("GULF_OF_ADEN", (10.0, 15.5), (43.0, 52.0), ("EUR_IND", "MED_IND", "USEC_IND")),
    Region("MALACCA", (-1.0, 8.0), (95.0, 105.0), ("SEA_IND", "FE_IND", "USWC_IND")),
    Region("ANDAMAN_SEA", (5.0, 15.0), (92.0, 98.0), ("SEA_IND", "FE_IND", "USWC_IND")),
    Region("WEST_COAST", (7.0, 24.0), (66.0, 77.5), ("COAST_W",)),
    Region("EAST_COAST", (7.0, 23.0), (77.5, 92.0), ("COAST_E",)),
)


@dataclass(frozen=True)
class LaneGuess:
    lane_code: Optional[str]
    confidence: float
    reason: str
    region: Optional[str] = None


def infer_lane(lat: float, lon: float, destination_port: Optional[str]) -> LaneGuess:
    """Which lane a vessel at (lat, lon) bound for `destination_port` is on.

    Requires a resolved destination: without one, a position alone is any of
    several lanes and the honest answer is none of them.
    """
    if destination_port is None:
        return LaneGuess(None, 0.0, "no resolved destination; a position alone does not place a hull on a lane")
    region = next(
        (r for r in REGIONS if r.lat[0] <= lat <= r.lat[1] and r.lon[0] <= lon <= r.lon[1]),
        None,
    )
    if region is None:
        return LaneGuess(None, 0.0, "position is outside every sea region the lane model covers")
    serving = [
        code for code in region.lanes
        if destination_port in TRADE_LANES[code].india_ports
    ]
    if not serving:
        # The coastal lanes call everywhere on their coast; fall back to them
        # when the destination is on the region's coast at all.
        coast = port_registry.resolve(destination_port)
        if coast is not None:
            coastal = "COAST_W" if coast.coast in ("west", "south") else "COAST_E"
            if coastal in region.lanes:
                serving = [coastal]
    if len(serving) == 1:
        return LaneGuess(serving[0], LANE_CONFIDENCE,
                         f"in the {region.code.replace('_', ' ').title()} bound for {destination_port}", region.code)
    if len(serving) > 1:
        # Several long-haul lanes share these waters and chokepoints; pick the
        # one whose chokepoint set is the same and say the origin is unknown.
        chokepoints = {TRADE_LANES[c].chokepoints for c in serving}
        if len(chokepoints) == 1:
            return LaneGuess(serving[0], LANE_CONFIDENCE * 0.8,
                             f"in the {region.code.replace('_', ' ').title()} bound for {destination_port}; "
                             f"origin unknown, so one of {', '.join(serving)} -- same chokepoints", region.code)
        return LaneGuess(None, 0.0, f"lanes {', '.join(serving)} cross here with different chokepoints; not placed", region.code)
    return LaneGuess(None, 0.0, f"no lane through the {region.code.replace('_', ' ').title()} serves {destination_port}", region.code)


def hours_to_chokepoints(
    lat: float, lon: float, sog_kn: Optional[float], cog_deg: Optional[float], lane_code: str,
) -> Dict[str, float]:
    """Hours to each chokepoint on the lane, negative once passed, absent if unknowable."""
    out: Dict[str, float] = {}
    lane = TRADE_LANES.get(lane_code)
    if lane is None:
        return out
    for code in lane.chokepoints:
        geo = CHOKEPOINT_GEO.get(code)
        if geo is None:
            continue
        distance = haversine_nm(lat, lon, geo[0], geo[1])
        if cog_deg is not None:
            towards = _off_bearing(cog_deg, bearing_deg(lat, lon, geo[0], geo[1])) <= MAX_OFF_BEARING_DEG
        else:
            towards = None
        if towards is False:
            # Pointing away: it has been through, or is not going. Recorded
            # as passed so the transfer rule treats it as committed.
            out[code] = -round(distance / max(sog_kn or 1.0, 1.0), 1)
            continue
        if sog_kn is None or sog_kn < MIN_SOG_FOR_ETA_KN:
            continue
        out[code] = round(distance / sog_kn, 1)
    return out


# --------------------------------------------------------------------------
# hull -> voyage
# --------------------------------------------------------------------------


@dataclass
class ObservedPlacement:
    """How one observed hull was placed on the graph, and why."""

    voyage: VesselVoyage
    destination: Dict[str, Any]
    lane: LaneGuess
    timing_confidence: float
    notes: List[str] = field(default_factory=list)


def place_hull(hull: CanonicalVessel, *, now: Optional[datetime] = None) -> Optional[ObservedPlacement]:
    """One canonical vessel as a voyage the world graph can hold."""
    held = hull.attributes.get(ATTR_POSITION)
    if held is None or held.source_kind != OBSERVED_AIS:
        return None
    position = held.value
    lat, lon = position.get("lat"), position.get("lon")
    if lat is None or lon is None:
        return None

    destination_text = hull.attribute(ATTR_DESTINATION)
    destination = resolve_destination(destination_text)
    lane = infer_lane(lat, lon, destination.port_code)
    timing = (
        hours_to_chokepoints(lat, lon, position.get("sog"), position.get("cog"), lane.lane_code)
        if lane.lane_code else {}
    )
    speed = position.get("sog")
    voyage = VesselVoyage(
        vessel_id=hull.canonical_id,
        name=hull.name or (f"MMSI {hull.mmsis[0]}" if hull.mmsis else hull.canonical_id),
        lane_code=lane.lane_code,
        destination_port=destination.port_code,
        hours_to_chokepoint=timing,
        eta=hull.attribute(ATTR_ETA),
        service_speed_kn=float(speed) if speed else 12.0,
        source=SOURCE_OBSERVED_AIS,
        destination_confidence=destination.confidence if destination.resolved else None,
        lane_confidence=lane.confidence if lane.lane_code else None,
        timing_confidence=TIMING_CONFIDENCE if timing else None,
        lat=float(lat),
        lon=float(lon),
        observed_at=held.observed_at.isoformat(),
        mmsi=hull.mmsis[0] if hull.mmsis else None,
        identity_conflicts=len(getattr(hull, "conflicts", []) or []),
        imo=hull.imo,
        canonical_id=hull.canonical_id,
        name_stated=hull.name is not None,
    )
    notes = [destination.reason, lane.reason]
    if not timing and lane.lane_code:
        notes.append("no chokepoint timing: not making way, or course unknown")
    return ObservedPlacement(voyage, destination.to_dict(), lane, TIMING_CONFIDENCE if timing else 0.0, notes)


def observed_voyages(
    engine: FusionEngine,
    *,
    now: Optional[datetime] = None,
    max_age: timedelta = timedelta(hours=2),
) -> List[ObservedPlacement]:
    """Every observed hull recent enough to be on the chart, placed."""
    moment = now or world_now()
    placements: List[ObservedPlacement] = []
    for hull in engine.vessels():
        if not hull.observed or hull.last_observed_at is None:
            continue
        if moment - hull.last_observed_at > max_age:
            continue
        placed = place_hull(hull, now=moment)
        if placed is not None:
            placements.append(placed)
    return placements


__all__ = [
    "LANE_CONFIDENCE",
    "LaneGuess",
    "ObservedPlacement",
    "REGIONS",
    "SOURCE_OBSERVED_AIS",
    "TIMING_CONFIDENCE",
    "bearing_deg",
    "haversine_nm",
    "hours_to_chokepoints",
    "infer_lane",
    "observed_voyages",
    "place_hull",
]
