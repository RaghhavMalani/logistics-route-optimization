"""Historical missions: a real incident replayed with only what was known then.

A mission is a recording of an incident with a clock in it. Every observation
carries the instant it became knowable; the replay engine serves only the
observations at or before its clock, and refuses the rest until the operator
asks for the reveal. PortWatch is then judged on what it said before the
outcome existed -- the only judgement that means anything.

Three rules, enforced by the model rather than by convention:

*   **Chronology is monotonic and sourced.** Every observation names its source
    and its instant; the recording is sorted and validated. A fact without a
    source is not an observation and is refused.
*   **The future is hidden by construction.** An observation later than the
    clock cannot be read through the replay interface. There is no flag that
    turns this off short of the explicit reveal.
*   **Missing data stays missing.** Where a source states a date without a
    time, the record holds the date and the outcome model says which bound it
    used. Nothing operational that the sources do not state is reconstructed
    as fact; illustrative hulls are labelled illustrative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence


class MissionError(ValueError):
    """A mission that does not meet the standard, or a replay misuse."""


class FutureLeak(MissionError):
    """An observation later than the replay clock was requested before reveal."""


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Source:
    source_id: str
    name: str
    url: str
    kind: str
    retrieved_at: str
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"sourceId": self.source_id, "name": self.name, "url": self.url, "kind": self.kind,
                "retrievedAt": self.retrieved_at, "note": self.note}


@dataclass(frozen=True)
class Observation:
    """One thing that became knowable at one instant, from one source."""

    observed_at: str
    kind: str
    text: str
    source_id: str
    #: What the observation changes about the event's claim, if anything:
    #: severity, confidence, status, chokepoint, ships_waiting, ...
    claim: Dict[str, Any] = field(default_factory=dict)
    #: True when the source gives a date without a time; ``observed_at`` then
    #: carries the bound the mission chose, and says so here.
    time_unstated: bool = False

    @property
    def at(self) -> datetime:
        return _parse(self.observed_at)

    def to_dict(self) -> Dict[str, Any]:
        return {"observedAt": self.observed_at, "kind": self.kind, "text": self.text,
                "sourceId": self.source_id, "claim": self.claim, "timeUnstated": self.time_unstated}


@dataclass(frozen=True)
class IllustrativeVessel:
    """A hull placed on the replayed world so a decision exists to make.

    Not a real ship. Real vessel positions at the time are not held by this
    deployment, and inventing them for named hulls would manufacture a record
    of voyages that never happened. The label says illustrative everywhere.
    """

    vessel_id: str
    name: str
    lane_code: str
    destination_port: str
    #: Hours to each chokepoint at the mission's start instant.
    hours_to_chokepoint_at_start: Dict[str, float]
    service_speed_kn: float
    #: Hours to the destination port at the start instant, for a mission whose
    #: event acts on the port rather than on a strait.
    hours_to_destination_at_start: Optional[float] = None
    note: str = "Illustrative hull. Not a real vessel; placed so the decision engine has a subject."

    def to_dict(self) -> Dict[str, Any]:
        return {"vesselId": self.vessel_id, "name": self.name, "laneCode": self.lane_code,
                "destinationPort": self.destination_port,
                "hoursToChokepointAtStart": dict(self.hours_to_chokepoint_at_start),
                "hoursToDestinationAtStart": self.hours_to_destination_at_start,
                "serviceSpeedKn": self.service_speed_kn, "illustrative": True, "note": self.note}


@dataclass(frozen=True)
class Outcome:
    """What happened, as the sources state it. Read only after reveal."""

    reopened_at: str
    blocked_from: str
    backlog_cleared_on: str
    #: The bound the outcome model uses for a date the source gives no time for.
    backlog_cleared_bound: str
    ships_waiting_peak: Optional[int]
    ships_waiting_source_id: Optional[str]
    summary: str
    sources: List[str] = field(default_factory=list)
    #: Per-port closures for an event that acts on ports: each entry holds
    #: closedFrom, reopenedAt and backlogClearedBound as the sources state
    #: them, with the bound named. The fields above then describe the primary
    #: subject, so a chokepoint mission reads exactly as before.
    closures: Dict[str, Dict[str, str]] = field(default_factory=dict)

    @property
    def blocked_hours(self) -> float:
        return (_parse(self.reopened_at) - _parse(self.blocked_from)).total_seconds() / 3600.0

    def closure_for(self, subject: Optional[str]) -> Dict[str, str]:
        """The closure window that applies to ``subject`` (a port code or a chokepoint)."""
        if subject and subject in self.closures:
            return dict(self.closures[subject])
        return {"closedFrom": self.blocked_from, "reopenedAt": self.reopened_at,
                "backlogClearedBound": self.backlog_cleared_bound}

    def to_dict(self) -> Dict[str, Any]:
        return {"reopenedAt": self.reopened_at, "blockedFrom": self.blocked_from,
                "blockedHours": round(self.blocked_hours, 1),
                "backlogClearedOn": self.backlog_cleared_on, "backlogClearedBound": self.backlog_cleared_bound,
                "shipsWaitingPeak": self.ships_waiting_peak, "shipsWaitingSourceId": self.ships_waiting_source_id,
                "summary": self.summary, "sources": list(self.sources),
                "closures": {k: dict(v) for k, v in self.closures.items()}}


@dataclass
class Mission:
    mission_id: str
    name: str
    start_timestamp: str
    #: The strait the event acts on, or None for an event that acts on ports.
    chokepoint: Optional[str]
    event_category: str
    event_title: str
    sources: List[Source]
    recording: List[Observation]
    fleet: List[IllustrativeVessel]
    outcome: Outcome
    evaluation_window_hours: float
    #: The claim horizon PortWatch's register applies to a chokepoint claim.
    claim_horizon_hours: float = 72.0
    #: Ports the event acts on directly (a cyclone over the approaches, a
    #: closure). Empty for a chokepoint mission.
    ports: List[str] = field(default_factory=list)
    #: Where the event is, for a mission whose subject is not a catalogued strait.
    event_lat: Optional[float] = None
    event_lon: Optional[float] = None
    description: str = ""
    disclaimer: str = (
        "Historical replay. The chronology and the outcome are transcribed from the cited "
        "sources; the hulls are illustrative and not real vessels; nothing operational the "
        "sources do not state has been reconstructed."
    )

    def __post_init__(self) -> None:
        problems = self.validate()
        if problems:
            raise MissionError("; ".join(problems))

    @property
    def start(self) -> datetime:
        return _parse(self.start_timestamp)

    @property
    def subject_kind(self) -> str:
        return "port" if self.ports else "chokepoint"

    @property
    def subject(self) -> str:
        """What the claim is about, for the event's title and claim text."""
        return self.chokepoint or " and ".join(self.ports)

    def validate(self) -> List[str]:
        problems: List[str] = []
        if not self.chokepoint and not self.ports:
            problems.append("a mission names a chokepoint or at least one port")
        if self.ports and (self.event_lat is None or self.event_lon is None):
            problems.append("a port mission states where its event is (event_lat, event_lon)")
        ids = {s.source_id for s in self.sources}
        for index, observation in enumerate(self.recording):
            if observation.source_id not in ids:
                problems.append(f"observation {index} cites unknown source {observation.source_id}")
            if index and observation.at < self.recording[index - 1].at:
                problems.append(f"observation {index} is out of order")
        if not any(o.at <= self.start for o in self.recording):
            problems.append("no observation is knowable at the start instant")
        if not any(o.at > self.start for o in self.recording):
            problems.append("the mission has no hidden future")
        for source_id in self.outcome.sources:
            if source_id not in ids:
                problems.append(f"the outcome cites unknown source {source_id}")
        return problems

    # -- the gate ------------------------------------------------------------
    def visible(self, clock: datetime) -> List[Observation]:
        """Observations knowable at ``clock``. The only read path before reveal."""
        return [o for o in self.recording if o.at <= clock]

    def hidden(self, clock: datetime) -> List[Observation]:
        return [o for o in self.recording if o.at > clock]

    def claim_at(self, clock: datetime) -> Dict[str, Any]:
        """The event's claim as it stood at ``clock``: the latest visible values."""
        state: Dict[str, Any] = {}
        for observation in self.visible(clock):
            state.update(observation.claim)
            state["lastSeen"] = observation.observed_at
        return state

    def to_dict(self, *, clock: Optional[datetime] = None, revealed: bool = False) -> Dict[str, Any]:
        moment = clock or self.start
        return {
            "missionId": self.mission_id,
            "name": self.name,
            "description": self.description,
            "startTimestamp": self.start_timestamp,
            "chokepoint": self.chokepoint,
            "ports": list(self.ports),
            "subjectKind": self.subject_kind,
            "eventLat": self.event_lat,
            "eventLon": self.event_lon,
            "eventCategory": self.event_category,
            "eventTitle": self.event_title,
            "claimHorizonHours": self.claim_horizon_hours,
            "evaluationWindowHours": self.evaluation_window_hours,
            "sources": [s.to_dict() for s in self.sources],
            "clock": moment.isoformat(),
            "visible": [o.to_dict() for o in self.visible(moment)],
            "hiddenCount": len(self.hidden(moment)),
            "hidden": [o.to_dict() for o in self.hidden(moment)] if revealed else None,
            "fleet": [v.to_dict() for v in self.fleet],
            "outcome": self.outcome.to_dict() if revealed else None,
            "revealed": revealed,
            "disclaimer": self.disclaimer,
        }


__all__ = ["FutureLeak", "IllustrativeVessel", "Mission", "MissionError", "Observation", "Outcome", "Source"]
