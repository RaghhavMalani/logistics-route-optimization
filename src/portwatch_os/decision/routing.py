"""Route topology for routing decisions: where a hull is on its lane, what
water is still ahead of it, and where the alternative routing actually goes.

The lane catalogue knows that Europe-India traffic transits Suez and
Bab-el-Mandeb and that the Cape is its alternative, and it knows the two
distances. What it cannot answer is the question a routing decision turns on:
*from where this ship is now*, what is the remaining primary passage, what is
the alternative passage, and is the alternative still reachable at all? A
vessel in the Red Sea cannot take the Cape without a second Suez transit; a
vessel north of Singapore can still go round Lombok, one inside the strait
cannot.

So this module holds coarse lane polylines and walks them. In the Indian Ocean
theatre the geometry comes from the terminal's water-only routing catalogue --
the same A* legs the chart draws, so the line the engine reasoned over is the
line the operator sees. Outside that theatre (the Mediterranean, the Atlantic,
the Cape, the South China Sea) it holds hand-placed open-water waypoints. All
of it is **non-navigational**: it is a visualisation and a distance estimate,
never a passage plan, and every payload built from it says so.

Distances are polyline lengths and are graded accordingly: the lane
catalogue's own nominal detour travels alongside so the Critic can see when
the two disagree.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.global_eye.exposure import TRADE_LANES
from src.portwatch_os.global_eye.ingest import CHOKEPOINT_GEO
from src.portwatch_os.world.observed import haversine_nm
from src.utils import port_registry

ROUTE_DISCLAIMER = (
    "Non-navigational route geometry: water-only routing catalogue legs inside "
    "the Indian Ocean theatre, hand-placed open-water waypoints outside it. A "
    "distance estimate for decision comparison, never a passage plan."
)
SOURCE_CATALOGUE = "india-portwatch-terminal/src/assets/geo/sea-routes.json"
SOURCE_COARSE = "src.portwatch_os.decision.routing (coarse open-water waypoints)"

#: How far a polyline point may sit from a chokepoint and still anchor it.
ANCHOR_TOLERANCE_NM = 90.0

Point = Tuple[float, float]  # (lat, lon)


# --------------------------------------------------------------------------
# the routing catalogue, read from the terminal's asset
# --------------------------------------------------------------------------

_CATALOGUE: Optional[Dict[str, Any]] = None
_CATALOGUE_LOCK = threading.Lock()


def _catalogue_path() -> Path:
    override = os.getenv("PORTWATCH_SEA_ROUTES")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / SOURCE_CATALOGUE


def catalogue() -> Dict[str, Any]:
    """The routing catalogue, or an empty one if the asset is not present."""
    global _CATALOGUE
    with _CATALOGUE_LOCK:
        if _CATALOGUE is None:
            path = _catalogue_path()
            if path.exists():
                with path.open("r", encoding="utf-8") as handle:
                    _CATALOGUE = json.load(handle)
            else:
                _CATALOGUE = {"legs": {}, "waypoints": {}, "generatedAt": None}
        return _CATALOGUE


def leg(a: str, b: str) -> Optional[List[Point]]:
    """The catalogued passage from ``a`` to ``b`` as (lat, lon), or ``None``."""
    legs = catalogue().get("legs") or {}
    forward = legs.get(f"{a}>{b}")
    if forward:
        return [(c[1], c[0]) for c in forward["coords"]]
    reverse = legs.get(f"{b}>{a}")
    if reverse:
        return [(c[1], c[0]) for c in reversed(reverse["coords"])]
    return None


# --------------------------------------------------------------------------
# coarse open-water geometry
# --------------------------------------------------------------------------

#: Hand-placed waypoints. Each is on open water at basin scale; none is a
#: navigational mark. Ordered toward India.
GIBRALTAR: Point = (35.95, -5.6)
SUEZ: Point = CHOKEPOINT_GEO["SUEZ"][:2]
SCS_SOUTH: Point = (3.5, 105.5)

NORTH_EUROPE_TO_GIBRALTAR: List[Point] = [
    (51.9, 2.9), (50.2, -1.5), (48.6, -5.6), (45.5, -8.0), (42.5, -9.9),
    (38.5, -9.8), (36.4, -7.6), GIBRALTAR,
]
US_EAST_TO_GIBRALTAR: List[Point] = [
    (40.4, -73.4), (39.5, -60.0), (38.0, -45.0), (37.0, -30.0), (36.6, -15.0), GIBRALTAR,
]
GIBRALTAR_TO_SUEZ: List[Point] = [
    GIBRALTAR, (36.3, -3.0), (37.2, 1.5), (37.9, 6.0), (37.6, 10.8), (36.8, 14.0),
    (35.4, 19.5), (34.2, 25.0), (32.6, 29.5), (31.4, 32.2), (30.9, 32.35), SUEZ,
]
#: The Cape. From Gibraltar down the West African seaboard, round Agulhas, up
#: the Mozambique Channel to the East Africa lane, where the catalogue takes
#: over at Mombasa's offing.
GIBRALTAR_TO_MOMBASA_VIA_CAPE: List[Point] = [
    GIBRALTAR, (34.0, -9.5), (28.5, -14.5), (21.0, -18.5), (13.0, -18.5), (6.5, -14.0),
    (2.0, -8.0), (-2.5, -1.0), (-8.0, 4.5), (-15.0, 8.5), (-24.0, 12.5), (-31.5, 15.5),
    (-35.2, 18.6), (-35.6, 21.5), (-34.0, 27.0), (-31.2, 31.6), (-27.0, 34.4),
    (-22.0, 37.5), (-16.5, 41.0), (-11.0, 42.0), (-6.5, 41.2), (-4.2, 40.4),
]
#: A transatlantic hull already in the eastern Atlantic joins the Cape
#: routing off Morocco rather than steaming back to New York.
ATLANTIC_JOIN: Point = (36.6, -15.0)
ATLANTIC_JOIN_TO_MOMBASA_VIA_CAPE: List[Point] = [ATLANTIC_JOIN] + GIBRALTAR_TO_MOMBASA_VIA_CAPE[1:]
GULF_INTERIOR_TO_HORMUZ: List[Point] = [
    (26.1, 51.6), (25.9, 54.6), (26.2, 55.8), CHOKEPOINT_GEO["HORMUZ"][:2],
]
#: The South China Sea approach to Singapore, from the Taiwan Strait.
SHANGHAI_TO_SCS_SOUTH: List[Point] = [
    (31.0, 122.9), (28.0, 123.0), (24.8, 119.6), (21.5, 116.5), (17.5, 113.0),
    (12.5, 110.8), (8.0, 108.0), (5.5, 106.5), SCS_SOUTH,
]
US_WEST_TO_SCS_SOUTH: List[Point] = [
    (33.7, -118.3), (30.0, -140.0), (25.0, -165.0), (21.0, 175.0), (20.0, 150.0),
    (19.5, 125.0), (17.5, 118.0), (12.5, 110.8), (8.0, 108.0), (5.5, 106.5), SCS_SOUTH,
]
SCS_SOUTH_TO_SINGAPORE: List[Point] = [SCS_SOUTH, (2.2, 104.6), (1.25, 104.1)]
#: Down the Gaspar Strait between Bangka and Belitung to the Sunda Strait and
#: the Sunda approach the catalogue holds. The lane catalogue names Lombok as
#: the nominal alternative for the Far East lanes; for India-bound traffic
#: Sunda is the shorter of the two and is what is drawn and measured here.
SCS_SOUTH_TO_SUNDA: List[Point] = [
    SCS_SOUTH, (1.5, 106.2), (-1.0, 106.9), (-2.6, 107.25), (-4.8, 106.6), (-6.1, 105.7),
    (-7.4, 104.9),
]
SINGAPORE_TO_SUNDA: List[Point] = [
    (1.25, 104.1), (0.4, 105.2), (-1.0, 106.9), (-2.6, 107.25), (-4.8, 106.6),
    (-6.1, 105.7), (-7.4, 104.9),
]


# --------------------------------------------------------------------------
# lane geometry
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LaneGeometry:
    """How to assemble a lane's routes toward one Indian port."""

    lane_code: str
    #: Coarse polyline to the first catalogue gateway on the primary routing.
    primary_approach: Tuple[Point, ...]
    #: The catalogue gateway the primary routing enters the theatre through.
    primary_gateway: str
    #: Coarse polyline of the alternative, ending at a catalogue gateway.
    alternative_approach: Tuple[Point, ...] = ()
    alternative_gateway: Optional[str] = None
    #: Where the alternative leaves the primary; a vessel beyond the commit
    #: point cannot take it.
    join_anchor: Optional[Point] = None
    commit_anchor: Optional[Point] = None
    commit_reason: str = ""


LANE_GEOMETRY: Dict[str, LaneGeometry] = {
    g.lane_code: g for g in [
        LaneGeometry(
            "EUR_IND", tuple(NORTH_EUROPE_TO_GIBRALTAR + GIBRALTAR_TO_SUEZ[1:]), "SUEZ",
            tuple(GIBRALTAR_TO_MOMBASA_VIA_CAPE), "KEMBA",
            join_anchor=GIBRALTAR, commit_anchor=SUEZ,
            commit_reason="the Cape routing branches at Gibraltar; a hull that has entered "
                          "the Suez Canal cannot reach it without a second transit",
        ),
        LaneGeometry(
            "MED_IND", tuple(GIBRALTAR_TO_SUEZ), "SUEZ",
            tuple(GIBRALTAR_TO_MOMBASA_VIA_CAPE), "KEMBA",
            join_anchor=GIBRALTAR, commit_anchor=SUEZ,
            commit_reason="the Cape routing branches at Gibraltar; a hull that has entered "
                          "the Suez Canal cannot reach it without a second transit",
        ),
        LaneGeometry(
            "USEC_IND", tuple(US_EAST_TO_GIBRALTAR + GIBRALTAR_TO_SUEZ[1:]), "SUEZ",
            tuple(ATLANTIC_JOIN_TO_MOMBASA_VIA_CAPE), "KEMBA",
            join_anchor=ATLANTIC_JOIN, commit_anchor=SUEZ,
            commit_reason="the Cape routing branches in the eastern Atlantic; a hull that has "
                          "entered the Suez Canal cannot reach it without a second transit",
        ),
        LaneGeometry("GULF_IND", tuple(GULF_INTERIOR_TO_HORMUZ), "HORMUZ"),
        LaneGeometry("EAF_IND", ((-4.2, 40.4),), "KEMBA"),
        LaneGeometry(
            "SEA_IND", tuple(SCS_SOUTH_TO_SINGAPORE), "SGSIN",
            tuple(SINGAPORE_TO_SUNDA), "IDBLW",
            join_anchor=(1.25, 104.1), commit_anchor=(1.25, 104.1),
            commit_reason="the Sunda routing branches at Singapore; a hull already in the "
                          "Malacca Strait cannot take it",
        ),
        LaneGeometry(
            "FE_IND", tuple(SHANGHAI_TO_SCS_SOUTH + SCS_SOUTH_TO_SINGAPORE[1:]), "SGSIN",
            tuple(SCS_SOUTH_TO_SUNDA), "IDBLW",
            join_anchor=SCS_SOUTH, commit_anchor=SCS_SOUTH,
            commit_reason="the Sunda routing branches in the southern South China Sea; a "
                          "hull past that point is committed to the Singapore approach",
        ),
        LaneGeometry(
            "USWC_IND", tuple(US_WEST_TO_SCS_SOUTH + SCS_SOUTH_TO_SINGAPORE[1:]), "SGSIN",
            tuple(SCS_SOUTH_TO_SUNDA), "IDBLW",
            join_anchor=SCS_SOUTH, commit_anchor=SCS_SOUTH,
            commit_reason="the Sunda routing branches in the southern South China Sea; a "
                          "hull past that point is committed to the Singapore approach",
        ),
    ]
}


# --------------------------------------------------------------------------
# polyline arithmetic
# --------------------------------------------------------------------------


def length_nm(points: Sequence[Point]) -> float:
    return sum(haversine_nm(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:]))


def _cumulative(points: Sequence[Point]) -> List[float]:
    out = [0.0]
    for a, b in zip(points, points[1:]):
        out.append(out[-1] + haversine_nm(a[0], a[1], b[0], b[1]))
    return out


def nearest_index(points: Sequence[Point], target: Point) -> Tuple[int, float]:
    best, best_nm = 0, float("inf")
    for index, point in enumerate(points):
        d = haversine_nm(point[0], point[1], target[0], target[1])
        if d < best_nm:
            best, best_nm = index, d
    return best, best_nm


def point_at(points: Sequence[Point], along_nm: float) -> Point:
    """The point ``along_nm`` from the start, clamped to the polyline."""
    cumulative = _cumulative(points)
    if along_nm <= 0:
        return points[0]
    if along_nm >= cumulative[-1]:
        return points[-1]
    for index in range(1, len(points)):
        if cumulative[index] >= along_nm:
            a, b = points[index - 1], points[index]
            span = cumulative[index] - cumulative[index - 1]
            fraction = 0.0 if span <= 0 else (along_nm - cumulative[index - 1]) / span
            return (a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction)
    return points[-1]


def slice_from(points: Sequence[Point], along_nm: float) -> List[Point]:
    """The polyline from ``along_nm`` to its end, starting at that exact point."""
    cumulative = _cumulative(points)
    start = point_at(points, along_nm)
    rest = [p for p, c in zip(points, cumulative) if c > along_nm]
    return [start] + rest


def slice_to(points: Sequence[Point], along_nm: float) -> List[Point]:
    cumulative = _cumulative(points)
    end = point_at(points, along_nm)
    head = [p for p, c in zip(points, cumulative) if c < along_nm]
    return head + [end]


def _dedupe(points: Sequence[Point]) -> List[Point]:
    out: List[Point] = []
    for p in points:
        if not out or haversine_nm(out[-1][0], out[-1][1], p[0], p[1]) > 0.05:
            out.append(p)
    return out


# --------------------------------------------------------------------------
# routes for one voyage
# --------------------------------------------------------------------------


@dataclass
class VoyageRoutes:
    """The primary and alternative passages ahead of one hull."""

    lane_code: str
    port_code: str
    #: Full primary polyline, origin to port.
    primary: List[Point]
    #: Distance along ``primary`` at which the hull is now.
    position_nm: float
    position: Point
    #: Where the position came from.
    position_basis: str
    #: Distance along ``primary`` of each chokepoint anchor.
    chokepoint_nm: Dict[str, float]
    remaining_primary: List[Point]
    alternative: Optional[List[Point]] = None
    alternative_reachable: bool = True
    alternative_reason: str = ""
    sources: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def remaining_primary_nm(self) -> float:
        return length_nm(self.remaining_primary)

    @property
    def alternative_nm(self) -> Optional[float]:
        return None if self.alternative is None else length_nm(self.alternative)

    @property
    def detour_nm(self) -> Optional[float]:
        alt = self.alternative_nm
        return None if alt is None else alt - self.remaining_primary_nm

    def to_dict(self) -> Dict[str, Any]:
        return {
            "laneCode": self.lane_code,
            "portCode": self.port_code,
            "position": [round(self.position[0], 4), round(self.position[1], 4)],
            "positionBasis": self.position_basis,
            "remainingPrimaryNm": round(self.remaining_primary_nm, 1),
            "alternativeNm": None if self.alternative_nm is None else round(self.alternative_nm, 1),
            "detourNm": None if self.detour_nm is None else round(self.detour_nm, 1),
            "alternativeReachable": self.alternative_reachable,
            "alternativeReason": self.alternative_reason,
            "chokepointNm": {k: round(v, 1) for k, v in self.chokepoint_nm.items()},
            "sources": self.sources,
            "disclaimer": ROUTE_DISCLAIMER,
            "notes": self.notes,
        }


def _port_point(port_code: str) -> Optional[Point]:
    record = port_registry.resolve(port_code)
    return None if record is None else (record.lat, record.lon)


def primary_route(lane_code: str, port_code: str) -> Tuple[List[Point], List[str]]:
    """The whole primary routing from the lane's origin to the port."""
    geometry = LANE_GEOMETRY.get(lane_code)
    sources: List[str] = []
    if geometry is None:
        # Coastal lanes and anything unmodelled: the port alone.
        point = _port_point(port_code)
        return ([point] if point else []), sources
    points = list(geometry.primary_approach)
    if geometry.primary_approach:
        sources.append(SOURCE_COARSE)
    theatre = leg(geometry.primary_gateway, port_code)
    if theatre is not None:
        sources.append(SOURCE_CATALOGUE)
        points = points + theatre
    else:
        point = _port_point(port_code)
        if point is not None:
            points.append(point)
    return _dedupe(points), sources


def alternative_route_tail(lane_code: str, port_code: str) -> Tuple[Optional[List[Point]], List[str]]:
    """The alternative from its join anchor to the port, or ``None``."""
    geometry = LANE_GEOMETRY.get(lane_code)
    if geometry is None or not geometry.alternative_approach or not geometry.alternative_gateway:
        return None, []
    sources = [SOURCE_COARSE]
    points = list(geometry.alternative_approach)
    theatre = leg(geometry.alternative_gateway, port_code)
    if theatre is not None:
        sources.append(SOURCE_CATALOGUE)
        points = points + theatre
    else:
        point = _port_point(port_code)
        if point is not None:
            points.append(point)
    return _dedupe(points), sources


def routes_for(
    lane_code: str,
    port_code: str,
    hours_to_chokepoint: Dict[str, float],
    speed_kn: float,
    *,
    position: Optional[Point] = None,
) -> Optional[VoyageRoutes]:
    """Place the hull and lay out what is ahead of it.

    An observed hull supplies its position. A declared voyage supplies its
    hours to each chokepoint, and the position is derived: the hull is
    ``hours x speed`` nautical miles short of the first chokepoint still
    ahead, or that far past the last one it has cleared. The basis is recorded
    either way.
    """
    lane = TRADE_LANES.get(lane_code)
    if lane is None:
        return None
    primary, sources = primary_route(lane_code, port_code)
    if len(primary) < 2:
        return None
    cumulative = _cumulative(primary)

    anchors: Dict[str, float] = {}
    for code in lane.chokepoints:
        geo = CHOKEPOINT_GEO.get(code)
        if geo is None:
            continue
        index, off = nearest_index(primary, (geo[0], geo[1]))
        if off <= ANCHOR_TOLERANCE_NM:
            anchors[code] = cumulative[index]

    notes: List[str] = []
    if position is not None:
        index, _off = nearest_index(primary, position)
        position_nm = cumulative[index]
        basis = "observed position projected onto the modelled lane"
    else:
        ahead = sorted(
            (h, code) for code, h in hours_to_chokepoint.items()
            if h is not None and h >= 0 and code in anchors
        )
        behind = sorted(
            (h, code) for code, h in hours_to_chokepoint.items()
            if h is not None and h < 0 and code in anchors
        )
        speed = max(1.0, float(speed_kn))
        if ahead:
            hours, code = ahead[0]
            position_nm = max(0.0, anchors[code] - hours * speed)
            basis = f"{hours:.1f} h short of {code} at {speed:.1f} kn on the modelled lane"
            if anchors[code] - hours * speed < 0:
                notes.append("the declared timing places the hull before the modelled lane's "
                             "origin; clamped to it")
        elif behind:
            # The last strait the hull cleared is the one closest behind it:
            # the least negative timing, not the most.
            hours, code = behind[-1]
            position_nm = min(cumulative[-1], anchors[code] + abs(hours) * speed)
            basis = f"{abs(hours):.1f} h past {code} at {speed:.1f} kn on the modelled lane"
        else:
            return None
    point = point_at(primary, position_nm)
    remaining = slice_from(primary, position_nm)

    routes = VoyageRoutes(
        lane_code=lane_code, port_code=port_code, primary=primary,
        position_nm=position_nm, position=point, position_basis=basis,
        chokepoint_nm=anchors, remaining_primary=remaining, sources=sources, notes=notes,
    )

    geometry = LANE_GEOMETRY.get(lane_code)
    tail, tail_sources = alternative_route_tail(lane_code, port_code)
    if geometry is None or tail is None:
        routes.alternative_reachable = False
        routes.alternative_reason = (
            f"{lane.name} has no alternative routing in the catalogue"
            if lane.alternative is None else
            f"no geometry is held for the {lane.alternative} routing"
        )
        return routes

    commit_index, _ = nearest_index(primary, geometry.commit_anchor)  # type: ignore[arg-type]
    join_index, _ = nearest_index(primary, geometry.join_anchor)  # type: ignore[arg-type]
    commit_nm = cumulative[commit_index]
    join_nm = cumulative[join_index]
    if position_nm >= commit_nm - 1.0:
        routes.alternative_reachable = False
        routes.alternative_reason = geometry.commit_reason
        return routes

    # Back along the primary to the join anchor (if the hull is past it), then
    # the alternative to the port. A hull short of the join anchor simply
    # continues to it.
    if position_nm > join_nm:
        back = list(reversed(slice_to(slice_from(primary, join_nm), position_nm - join_nm)))
        routes.notes.append(
            f"the alternative requires {position_nm - join_nm:.0f} nm back to the branch point"
        )
        alternative = back + tail[1:]
    else:
        forward = slice_to(slice_from(primary, position_nm), join_nm - position_nm)
        alternative = forward + tail[1:]
    routes.alternative = _dedupe(alternative)
    routes.sources = sorted(set(sources + tail_sources))
    return routes


def timeline_marks(
    routes: VoyageRoutes,
    speed_kn: float,
    *,
    alternative: bool = False,
) -> List[Dict[str, Any]]:
    """Hours from now at which the passage reaches each chokepoint and the port."""
    speed = max(1.0, float(speed_kn))
    if alternative:
        if routes.alternative is None:
            return []
        return [{"kind": "arrival", "subject": routes.port_code,
                 "hours": round(length_nm(routes.alternative) / speed, 1)}]
    marks: List[Dict[str, Any]] = []
    for code, along in sorted(routes.chokepoint_nm.items(), key=lambda kv: kv[1]):
        if along > routes.position_nm:
            marks.append({"kind": "chokepoint", "subject": code,
                          "hours": round((along - routes.position_nm) / speed, 1)})
    marks.append({"kind": "arrival", "subject": routes.port_code,
                  "hours": round(routes.remaining_primary_nm / speed, 1)})
    return marks


__all__ = [
    "ANCHOR_TOLERANCE_NM",
    "LANE_GEOMETRY",
    "LaneGeometry",
    "ROUTE_DISCLAIMER",
    "SOURCE_CATALOGUE",
    "SOURCE_COARSE",
    "VoyageRoutes",
    "alternative_route_tail",
    "catalogue",
    "leg",
    "length_nm",
    "point_at",
    "primary_route",
    "routes_for",
    "slice_from",
    "slice_to",
    "timeline_marks",
]
