"""The replay engine: a mission's world at its clock, the decision made from
it, and the reveal that scores it.

At replay time PortWatch may read only the observations knowable at the
clock. The world graph is built from those alone -- the event's severity and
confidence are whatever the latest visible report established, the claim
horizon runs from that report, and the illustrative hulls are advanced by the
hours elapsed since the mission started. The decision engine then runs on
that world exactly as it would on the live one, and the problem is stamped
``replay`` so the Critic and the ledger know the instant is historical.

The reveal is explicit and irreversible for the replay object. Until it is
called, the hidden observations and the outcome are unreadable through this
interface; after it, the scorecard compares what PortWatch said with what the
sources say happened.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.portwatch_os.decision.engine import DecisionEngine
from src.portwatch_os.decision.model import DecisionActor, DecisionProblem
from src.portwatch_os.global_eye.exposure import VesselVoyage
from src.portwatch_os.global_eye.ingest import CHOKEPOINT_GEO
from src.portwatch_os.global_eye.model import GlobalEvent
from src.portwatch_os.missions.model import FutureLeak, Mission, MissionError
from src.portwatch_os.world.branch import ObservedWorldState
from src.portwatch_os.world.build import build_world, seed_for
from src.portwatch_os.world.graph import EVENT, key
from src.portwatch_os.world.live import Revision
from src.portwatch_os.world.quantity import utc


_REPLAY_COUNTER = itertools.count(1)


class MissionReplay:
    """One replay of one mission: a clock, a world, decisions, a reveal.

    Every replay is a new run with its own id, so a decision made on it is a
    new ledger row: a replay of the same mission at the same clock tomorrow
    must not collide with a row that was resolved today.
    """

    def __init__(self, mission: Mission, engine: DecisionEngine, *, replay_id: Optional[str] = None) -> None:
        self.mission = mission
        self.engine = engine
        self.replay_id = replay_id or f"{utc().strftime('%Y%m%dT%H%M%S')}-{next(_REPLAY_COUNTER)}"
        self.clock: datetime = mission.start
        self.revealed = False
        self.problems: Dict[str, DecisionProblem] = {}
        self.choices: Dict[str, str] = {}

    # -- the clock -------------------------------------------------------------
    def seek(self, clock: datetime) -> None:
        moment = utc(clock)
        if moment < self.mission.start:
            raise MissionError("the replay clock cannot run before the mission starts")
        limit = self.mission.start + timedelta(hours=self.mission.evaluation_window_hours)
        if moment > limit:
            raise MissionError(f"the replay clock cannot run past the evaluation window ({limit.isoformat()})")
        self.clock = moment

    @property
    def elapsed_hours(self) -> float:
        return (self.clock - self.mission.start).total_seconds() / 3600.0

    # -- the world as it was ---------------------------------------------------
    def event(self) -> GlobalEvent:
        """The event as the visible reports establish it. Nothing later."""
        claim = self.mission.claim_at(self.clock)
        if not claim:
            raise MissionError("no observation is visible at the replay clock")
        last_seen = claim.get("lastSeen") or self.mission.start_timestamp
        geo = CHOKEPOINT_GEO.get(self.mission.chokepoint)
        return GlobalEvent(
            event_id=f"mission:{self.mission.mission_id}",
            title=self.mission.event_title,
            category=self.mission.event_category,
            region=geo[2] if geo else None,
            lat=geo[0] if geo else None,
            lon=geo[1] if geo else None,
            geolocation_basis="chokepoint",
            # The claim horizon runs from the latest corroborating report: a
            # blockage re-reported every day is not a claim that lapsed three
            # days ago. Stated here because the live register keys on first
            # sighting, and the difference matters to the scorecard.
            first_seen=last_seen,
            last_seen=last_seen,
            source_count=int(claim.get("sourceCount") or 1),
            confidence=float(claim.get("confidence") or 0.5),
            severity=float(claim.get("severity") or 0.5),
            claim=f"{self.mission.chokepoint} closure holds",
            horizon_hours=self.mission.claim_horizon_hours,
            chokepoints=[self.mission.chokepoint],
            data_source=f"mission replay: {self.mission.mission_id}",
        )

    def voyages(self) -> List[VesselVoyage]:
        elapsed = self.elapsed_hours
        return [
            VesselVoyage(
                vessel_id=v.vessel_id, name=v.name, lane_code=v.lane_code,
                destination_port=v.destination_port,
                hours_to_chokepoint={code: round(h - elapsed, 1) for code, h in v.hours_to_chokepoint_at_start.items()},
                service_speed_kn=v.service_speed_kn, source="FLEET",
            )
            for v in self.mission.fleet
        ]

    def state(self) -> ObservedWorldState:
        event = self.event()
        graph = build_world(events=[event], voyages=self.voyages(), now=self.clock)
        visible = self.mission.visible(self.clock)
        revision = Revision(
            mode="REPLAY", company_id=None,
            events_stamp=f"{self.mission.mission_id}@{visible[-1].observed_at}",
            fleet_stamp=f"{len(self.mission.fleet)} illustrative hulls @ {self.clock.isoformat()}",
            observed_generation=len(visible),
        )
        return ObservedWorldState(
            state_id=f"mission-{self.mission.mission_id}-{int(self.clock.timestamp())}",
            revision=revision, at=self.clock, graph=graph, traffic_mode="REPLAY",
        )

    # -- reading, gated ------------------------------------------------------
    def observations(self) -> List[Dict[str, Any]]:
        return [o.to_dict() for o in self.mission.visible(self.clock)]

    def hidden(self) -> List[Dict[str, Any]]:
        if not self.revealed:
            raise FutureLeak("the hidden future is not readable before the reveal")
        return [o.to_dict() for o in self.mission.hidden(self.clock)]

    def outcome(self) -> Dict[str, Any]:
        if not self.revealed:
            raise FutureLeak("the outcome is not readable before the reveal")
        return self.mission.outcome.to_dict()

    # -- deciding ------------------------------------------------------------------
    def decide(self, vessel_id: str, actor: DecisionActor) -> DecisionProblem:
        if self.revealed:
            raise MissionError("decisions are made before the reveal, not after it")
        state = self.state()
        event = self.event()
        problem = self.engine.solve_vessel(
            state, event_key=key(EVENT, event.event_id), seed=seed_for(event), vessel_id=vessel_id,
            actor=actor, at=self.clock,
            replay={"missionId": self.mission.mission_id, "clock": self.clock.isoformat(),
                    "visibleObservations": len(self.mission.visible(self.clock)),
                    "hiddenObservations": len(self.mission.hidden(self.clock))},
            decision_id=f"dec-msn-{self.mission.mission_id}-{vessel_id}-{int(self.clock.timestamp())}-{self.replay_id}",
        )
        self.problems[vessel_id] = problem
        return problem

    def choose(self, vessel_id: str, option_id: str, *, actor: str) -> DecisionProblem:
        problem = self.problems.get(vessel_id)
        if problem is None:
            raise MissionError(f"no decision has been made for {vessel_id} on this replay")
        from src.portwatch_os.decision.model import APPROVED, REVIEWED

        if problem.workflow == "COMPUTED":
            self.engine.transition(problem.decision_id, REVIEWED, actor=actor, note="mission replay review")
        self.engine.transition(problem.decision_id, APPROVED, actor=actor, option_id=option_id,
                               note="mission replay choice")
        self.choices[vessel_id] = option_id
        return problem

    # -- the reveal ------------------------------------------------------------
    def reveal(self, *, actor: str = "mission-replay") -> Dict[str, Any]:
        """Open the future. Scores every decision made, records their outcomes."""
        from src.portwatch_os.missions.scorecard import scorecard

        self.revealed = True
        cards: Dict[str, Any] = {}
        for vessel_id, problem in self.problems.items():
            chosen = self.choices.get(vessel_id) or (problem.recommendation.option_id if problem.recommendation else None)
            card = scorecard(self.mission, problem, chosen_option_id=chosen)
            cards[vessel_id] = card
            if problem.workflow in ("APPROVED", "ACCEPTED", "DECLINED"):
                observed = dict(card["observedForLearning"])
                self.engine.record_outcome(
                    problem.decision_id, actor=actor,
                    actual_action=str((problem.option(chosen).action if chosen and problem.option(chosen) else "")),
                    observed=observed, note="mission reveal",
                )
        return {
            "mission": self.mission.to_dict(clock=self.clock, revealed=True),
            "scorecards": cards,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.mission.to_dict(clock=self.clock, revealed=self.revealed),
            "replayId": self.replay_id,
            "elapsedHours": round(self.elapsed_hours, 1),
            "decisions": {v: p.decision_id for v, p in self.problems.items()},
            "choices": dict(self.choices),
        }


__all__ = ["MissionReplay"]
