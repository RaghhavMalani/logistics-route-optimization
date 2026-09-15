"""The security lens: what observed AIS alone can say about a hull's behaviour.

Seven rules, each a statement about the observations themselves and nothing
else. There is no watch list, no intelligence feed and no inference about
intent here; a detection says that a transponder did something the rule
describes, at these instants, past this threshold, and how confident the
rule is that the observations support it. That is the whole of the claim.

    prolonged_ais_gap            silence longer than the threshold while the
                                 hull was last seen under way
    improbable_position_jump     an implied speed between two reports that no
                                 merchant hull makes
    unusual_loitering            hours inside a small circle, under way by its
                                 own status, well away from any catalogued port
    route_deviation              a hull with an inferred lane and a resolved
                                 destination sitting far off that lane
    destination_inconsistency    a course sustained away from the resolved
                                 destination
    abnormal_speed_state         speed that contradicts the declared status:
                                 making way while "at anchor" or "moored",
                                 or stopped for hours while "under way"
    repeated_identity_conflict   the fusion engine recorded more than one
                                 identity conflict on the hull

The lens runs on observed tracks only. Under SIMULATED_TRAFFIC it returns
SECURITY ANALYTICS UNAVAILABLE with the reason, because running behaviour
rules on a deterministic replay and presenting the result as intelligence
would be manufacturing a finding. Under AIS_STALE it runs on what was
observed and says the picture is stale.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.portwatch_os.clock import world_now
from src.portwatch_os.fabric.ais.messages import AisObservation
from src.portwatch_os.fabric.ais.tracks import Track
from src.portwatch_os.world.observed import bearing_deg, haversine_nm, infer_lane

UNAVAILABLE = "SECURITY ANALYTICS UNAVAILABLE"
AVAILABLE = "SECURITY ANALYTICS AVAILABLE"

# Thresholds. Named, on the payload, so every detection can quote its own.
GAP_HOURS = 3.0
JUMP_KNOTS = 50.0
LOITER_HOURS = 6.0
LOITER_RADIUS_NM = 2.0
LOITER_MIN_PORT_DISTANCE_NM = 25.0
DEVIATION_NM = 120.0
COURSE_AWAY_DEG = 120.0
COURSE_AWAY_MIN_REPORTS = 3
MOVING_WHILE_STOPPED_KN = 1.0
STOPPED_WHILE_UNDER_WAY_KN = 0.3
STOPPED_WHILE_UNDER_WAY_HOURS = 2.0
IDENTITY_CONFLICTS = 2

THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "prolonged_ais_gap": {"gapHours": GAP_HOURS},
    "improbable_position_jump": {"impliedSpeedKn": JUMP_KNOTS},
    "unusual_loitering": {"hours": LOITER_HOURS, "radiusNm": LOITER_RADIUS_NM, "minPortDistanceNm": LOITER_MIN_PORT_DISTANCE_NM},
    "route_deviation": {"crossTrackNm": DEVIATION_NM},
    "destination_inconsistency": {"courseAwayDeg": COURSE_AWAY_DEG, "minReports": COURSE_AWAY_MIN_REPORTS},
    "abnormal_speed_state": {"movingWhileStoppedKn": MOVING_WHILE_STOPPED_KN,
                             "stoppedWhileUnderWayKn": STOPPED_WHILE_UNDER_WAY_KN,
                             "stoppedWhileUnderWayHours": STOPPED_WHILE_UNDER_WAY_HOURS},
    "repeated_identity_conflict": {"conflicts": IDENTITY_CONFLICTS},
}

UNDER_WAY = ("under way using engine", "under way sailing")
STOPPED_STATUSES = ("at anchor", "moored")


@dataclass(frozen=True)
class Detection:
    rule: str
    mmsi: str
    #: 0..1: how well the observations support the rule's statement.
    confidence: float
    evidence: Dict[str, Any]
    threshold: Dict[str, Any]
    observation_timestamps: List[str]
    statement: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule, "mmsi": self.mmsi, "confidence": round(self.confidence, 3),
            "evidence": dict(self.evidence), "threshold": dict(self.threshold),
            "observationTimestamps": list(self.observation_timestamps), "statement": self.statement,
            "basis": "observed AIS only; no watch list, no intent inferred",
        }


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _positions(track: Track) -> List[AisObservation]:
    return [p for p in track.positions if p.lat is not None and p.lon is not None]


# --------------------------------------------------------------------------
# the rules
# --------------------------------------------------------------------------


def prolonged_ais_gap(track: Track, *, now: datetime) -> List[Detection]:
    out: List[Detection] = []
    positions = _positions(track)
    pairs = list(zip(positions, positions[1:]))
    for a, b in pairs:
        gap = (b.source_timestamp - a.source_timestamp).total_seconds() / 3600.0
        if gap > GAP_HOURS and (a.sog_knots or 0.0) > 1.0:
            out.append(Detection(
                "prolonged_ais_gap", track.mmsi, min(1.0, 0.6 + 0.1 * (gap - GAP_HOURS)),
                {"gapHours": round(gap, 2), "lastSpeedBeforeGapKn": a.sog_knots,
                 "before": {"lat": a.lat, "lon": a.lon}, "after": {"lat": b.lat, "lon": b.lon}},
                THRESHOLDS["prolonged_ais_gap"], [_iso(a.source_timestamp), _iso(b.source_timestamp)],
                f"no report for {gap:.1f} h while last seen making {a.sog_knots or 0:.1f} kn",
            ))
    # A gap that is still open: the last report is old and the hull was under way.
    if positions:
        last = positions[-1]
        open_gap = (now - last.source_timestamp).total_seconds() / 3600.0
        if open_gap > GAP_HOURS and (last.sog_knots or 0.0) > 1.0:
            out.append(Detection(
                "prolonged_ais_gap", track.mmsi, min(1.0, 0.6 + 0.1 * (open_gap - GAP_HOURS)),
                {"gapHours": round(open_gap, 2), "lastSpeedBeforeGapKn": last.sog_knots, "open": True,
                 "before": {"lat": last.lat, "lon": last.lon}},
                THRESHOLDS["prolonged_ais_gap"], [_iso(last.source_timestamp)],
                f"silent for {open_gap:.1f} h since last seen making {last.sog_knots or 0:.1f} kn",
            ))
    return out


def improbable_position_jump(track: Track, *, now: datetime) -> List[Detection]:
    out: List[Detection] = []
    positions = _positions(track)
    for a, b in zip(positions, positions[1:]):
        dt = (b.source_timestamp - a.source_timestamp).total_seconds() / 3600.0
        if dt <= 0:
            continue
        distance = haversine_nm(a.lat, a.lon, b.lat, b.lon)
        implied = distance / dt
        if implied > JUMP_KNOTS and distance > 1.0:
            out.append(Detection(
                "improbable_position_jump", track.mmsi, min(1.0, 0.7 + 0.005 * (implied - JUMP_KNOTS)),
                {"distanceNm": round(distance, 1), "hours": round(dt, 3), "impliedSpeedKn": round(implied, 1),
                 "from": {"lat": a.lat, "lon": a.lon}, "to": {"lat": b.lat, "lon": b.lon}},
                THRESHOLDS["improbable_position_jump"], [_iso(a.source_timestamp), _iso(b.source_timestamp)],
                f"{distance:.0f} nm in {dt * 60:.0f} min implies {implied:.0f} kn",
            ))
    return out


def _nearest_port_nm(lat: float, lon: float) -> float:
    from src.utils import port_registry

    return min((haversine_nm(lat, lon, p.lat, p.lon) for p in port_registry.all_ports()), default=float("inf"))


def unusual_loitering(track: Track, *, now: datetime) -> List[Detection]:
    positions = _positions(track)
    if len(positions) < 4:
        return []
    # The longest tail of the track that stays within the radius of its own
    # first point, with the hull reporting itself under way throughout.
    tail = positions[-1]
    start_index = len(positions) - 1
    for index in range(len(positions) - 1, -1, -1):
        p = positions[index]
        if haversine_nm(p.lat, p.lon, tail.lat, tail.lon) > LOITER_RADIUS_NM:
            break
        if p.nav_status and p.nav_status not in UNDER_WAY:
            break
        start_index = index
    window = positions[start_index:]
    hours = (window[-1].source_timestamp - window[0].source_timestamp).total_seconds() / 3600.0
    if hours < LOITER_HOURS or len(window) < 4:
        return []
    port_distance = _nearest_port_nm(tail.lat, tail.lon)
    if port_distance < LOITER_MIN_PORT_DISTANCE_NM:
        return []
    statuses = sorted({p.nav_status for p in window if p.nav_status})
    return [Detection(
        "unusual_loitering", track.mmsi, min(1.0, 0.55 + 0.05 * (hours - LOITER_HOURS)),
        {"hours": round(hours, 2), "radiusNm": LOITER_RADIUS_NM, "reports": len(window),
         "nearestPortNm": round(port_distance, 1), "navStatus": statuses or ["not reported"],
         "centre": {"lat": tail.lat, "lon": tail.lon}},
        THRESHOLDS["unusual_loitering"],
        [_iso(window[0].source_timestamp), _iso(window[-1].source_timestamp)],
        f"within {LOITER_RADIUS_NM:.0f} nm for {hours:.1f} h, {port_distance:.0f} nm from the nearest catalogued port, "
        f"reporting {', '.join(statuses) or 'no status'}",
    )]


def _destination(track: Track):
    from src.portwatch_os.fusion.destination import resolve_destination

    return resolve_destination(track.destination_text)


def route_deviation(track: Track, *, now: datetime) -> List[Detection]:
    from src.portwatch_os.decision.routing import nearest_index, primary_route

    latest = track.latest
    if latest is None or latest.lat is None:
        return []
    destination = _destination(track)
    if not destination.resolved:
        return []
    guess = infer_lane(latest.lat, latest.lon, destination.port_code)
    if guess.lane_code is None:
        return []
    route, _sources = primary_route(guess.lane_code, destination.port_code)
    if len(route) < 2:
        return []
    _index, off_nm = nearest_index(route, (latest.lat, latest.lon))
    if off_nm <= DEVIATION_NM:
        return []
    return [Detection(
        "route_deviation", track.mmsi, min(1.0, guess.confidence * 0.9),
        {"laneCode": guess.lane_code, "laneConfidence": guess.confidence, "destinationPort": destination.port_code,
         "destinationText": track.destination_text, "crossTrackNm": round(off_nm, 1),
         "position": {"lat": latest.lat, "lon": latest.lon}},
        THRESHOLDS["route_deviation"], [_iso(latest.source_timestamp)],
        f"{off_nm:.0f} nm off the modelled {guess.lane_code} lane to {destination.port_code} "
        f"(lane inferred at confidence {guess.confidence:.2f})",
    )]


def destination_inconsistency(track: Track, *, now: datetime) -> List[Detection]:
    from src.utils import port_registry

    destination = _destination(track)
    if not destination.resolved:
        return []
    port = port_registry.resolve(destination.port_code)
    if port is None:
        return []
    positions = [p for p in _positions(track) if p.cog_degrees is not None and (p.sog_knots or 0.0) > 3.0]
    recent = positions[-COURSE_AWAY_MIN_REPORTS:]
    if len(recent) < COURSE_AWAY_MIN_REPORTS:
        return []
    away = []
    for p in recent:
        bearing = bearing_deg(p.lat, p.lon, port.lat, port.lon)
        diff = abs((p.cog_degrees - bearing + 180.0) % 360.0 - 180.0)
        away.append(round(diff, 1))
    if not all(d > COURSE_AWAY_DEG for d in away):
        return []
    return [Detection(
        "destination_inconsistency", track.mmsi, min(1.0, 0.5 + destination.confidence * 0.4),
        {"destinationText": track.destination_text, "destinationPort": destination.port_code,
         "destinationConfidence": destination.confidence, "courseAwayDeg": away,
         "lastCog": recent[-1].cog_degrees},
        THRESHOLDS["destination_inconsistency"], [_iso(p.source_timestamp) for p in recent],
        f"course {recent[-1].cog_degrees:.0f} sustained {min(away):.0f}+ degrees away from {destination.port_code} "
        f"over {len(recent)} reports",
    )]


def abnormal_speed_state(track: Track, *, now: datetime) -> List[Detection]:
    out: List[Detection] = []
    positions = _positions(track)
    latest = track.latest
    if latest is not None and latest.nav_status in STOPPED_STATUSES and (latest.sog_knots or 0.0) > MOVING_WHILE_STOPPED_KN:
        out.append(Detection(
            "abnormal_speed_state", track.mmsi, 0.8,
            {"navStatus": latest.nav_status, "sogKn": latest.sog_knots},
            THRESHOLDS["abnormal_speed_state"], [_iso(latest.source_timestamp)],
            f"making {latest.sog_knots:.1f} kn while reporting '{latest.nav_status}'",
        ))
    stopped = [p for p in positions if p.nav_status in UNDER_WAY and (p.sog_knots or 0.0) <= STOPPED_WHILE_UNDER_WAY_KN]
    if len(stopped) >= 2:
        hours = (stopped[-1].source_timestamp - stopped[0].source_timestamp).total_seconds() / 3600.0
        if hours >= STOPPED_WHILE_UNDER_WAY_HOURS:
            out.append(Detection(
                "abnormal_speed_state", track.mmsi, 0.6,
                {"navStatus": stopped[-1].nav_status, "hoursStopped": round(hours, 2), "reports": len(stopped)},
                THRESHOLDS["abnormal_speed_state"],
                [_iso(stopped[0].source_timestamp), _iso(stopped[-1].source_timestamp)],
                f"stopped for {hours:.1f} h while reporting '{stopped[-1].nav_status}'",
            ))
    return out


def repeated_identity_conflict(track: Track, *, now: datetime, conflicts: Sequence[Any] = ()) -> List[Detection]:
    if len(conflicts) < IDENTITY_CONFLICTS:
        return []
    return [Detection(
        "repeated_identity_conflict", track.mmsi, min(1.0, 0.5 + 0.15 * len(conflicts)),
        {"conflicts": [c.to_dict() if hasattr(c, "to_dict") else dict(c) for c in conflicts]},
        THRESHOLDS["repeated_identity_conflict"],
        sorted({(c.at.isoformat(timespec="seconds") if hasattr(c, "at") and hasattr(c.at, "isoformat") else str(getattr(c, "at", "")))
                for c in conflicts}),
        f"{len(conflicts)} identity conflicts recorded by the fusion engine",
    )]


RULES = (
    prolonged_ais_gap, improbable_position_jump, unusual_loitering, route_deviation,
    destination_inconsistency, abnormal_speed_state,
)


# --------------------------------------------------------------------------
# the lens
# --------------------------------------------------------------------------


def analyse_track(track: Track, *, now: Optional[datetime] = None, conflicts: Sequence[Any] = ()) -> List[Detection]:
    moment = now or world_now()
    out: List[Detection] = []
    for rule in RULES:
        out.extend(rule(track, now=moment))
    out.extend(repeated_identity_conflict(track, now=moment, conflicts=conflicts))
    return out


def security_lens(
    *,
    traffic: Dict[str, Any],
    tracks: Iterable[Track],
    conflicts_for: Optional[Any] = None,
    now: Optional[datetime] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    """The lens over a deployment's traffic: available only on observed AIS."""
    moment = now or world_now()
    mode = traffic.get("mode")
    if mode not in ("LIVE_AIS", "AIS_STALE"):
        return {
            "status": UNAVAILABLE,
            "mode": mode,
            "reason": (
                "the traffic on the chart is a deterministic replay, not observed AIS; behaviour rules run on a "
                "replay would be findings about the replay's author, not about any vessel"
                if mode == "SIMULATED_TRAFFIC" else
                f"no observed AIS is available ({traffic.get('statement', 'no traffic source')})"
            ),
            "rules": list(THRESHOLDS),
            "thresholds": THRESHOLDS,
            "detections": [],
            "tracksAnalysed": 0,
        }
    detections: List[Detection] = []
    analysed = 0
    for track in tracks:
        analysed += 1
        conflicts = list(conflicts_for(track) or []) if conflicts_for is not None else []
        detections.extend(analyse_track(track, now=moment, conflicts=conflicts))
    detections.sort(key=lambda d: (-d.confidence, d.rule, d.mmsi))
    return {
        "status": AVAILABLE,
        "mode": mode,
        "stale": mode == "AIS_STALE",
        "reason": None if mode == "LIVE_AIS" else "the observed picture is stale; detections are about the last observations",
        "rules": list(THRESHOLDS),
        "thresholds": THRESHOLDS,
        "detections": [d.to_dict() for d in detections[:limit]],
        "tracksAnalysed": analysed,
        "at": moment.isoformat(timespec="seconds"),
        "basis": "observed AIS only; every detection names its rule, evidence, threshold, confidence and instants",
    }


__all__ = [
    "AVAILABLE", "Detection", "RULES", "THRESHOLDS", "UNAVAILABLE", "abnormal_speed_state", "analyse_track",
    "destination_inconsistency", "improbable_position_jump", "prolonged_ais_gap", "repeated_identity_conflict",
    "route_deviation", "security_lens", "unusual_loitering",
]
