"""The decision engine: build, evaluate, criticise, rank, recommend, record.

One pipeline for every domain:

    subject + world revision
      -> DecisionProblem with every catalogue action marked available or not
      -> each available option simulated on its own scenario branch
      -> hard constraints: impossible options REJECTED, never penalised
      -> Critic v2 on every candidate, with named evidence
      -> Pareto frontier over the domain's objectives, labelled picks
      -> BALANCED ranking with its weights on the outside
      -> a recommendation, judged again as a whole
      -> the problem written to the ledger before anyone acts on it

The engine is deterministic. Given the same frozen world, the same basis and
the same instant it produces the same options in the same order with the
same numbers, which is what makes a recorded decision reconstructible and a
scorecard honest. Language models may explain what it produced; nothing they
say changes a number here.

Decision is not execution. A problem moves COMPUTED -> REVIEWED -> APPROVED ->
PROPOSED -> ISSUED -> ACCEPTED/DECLINED -> OBSERVED, every step attributed to
a named actor, and the only way an approved recommendation reaches a vessel
is through the advisory boundary that already exists.
"""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from src.portwatch_os.decision.critic import DecisionCritic, REJECT
from src.portwatch_os.decision.frontier import against_baseline, pareto, rank
from src.portwatch_os.decision.model import (
    ACCEPTED,
    APPROVED,
    CARGO_CONNECTION,
    COMPUTED,
    DECLINED,
    DecisionActor,
    DecisionError,
    DecisionProblem,
    DecisionRecommendation,
    ISSUED,
    OBJECTIVES,
    OBSERVED,
    PORT_BERTHING,
    PROPOSED,
    REJECTED,
    REVIEWED,
    VESSEL_ROUTING,
    WORKFLOW_STATES,
)
from src.portwatch_os.finance.basis import CostBasis
from src.portwatch_os.finance.evaluate import avoidable_cost
from src.portwatch_os.finance.money import FxTable
from src.portwatch_os.world.branch import BranchRegistry, ObservedWorldState
from src.portwatch_os.world.quantity import Quantity, utc

#: Legal workflow moves. Approval is the only step that carries a human
#: choice; observation is the only one that carries an outcome.
TRANSITIONS: Dict[str, tuple] = {
    COMPUTED: (REVIEWED,),
    REVIEWED: (APPROVED, DECLINED),
    APPROVED: (PROPOSED, OBSERVED, DECLINED),
    PROPOSED: (ISSUED, DECLINED),
    ISSUED: (ACCEPTED, DECLINED),
    ACCEPTED: (OBSERVED,),
    DECLINED: (OBSERVED,),
    OBSERVED: (),
}

FRONTIER_DEFAULTS: Dict[str, tuple] = {
    VESSEL_ROUTING: ("eta", "risk", "fuel"),
    PORT_BERTHING: ("port_wait", "missed_departures", "turnaround"),
    CARGO_CONNECTION: ("sailing", "slack", "dwell"),
}


def decision_id_for(domain: str, subject_id: str, at: datetime, salt: str = "") -> str:
    digest = hashlib.sha1(f"{domain}|{subject_id}|{at.isoformat()}|{salt}".encode("utf-8")).hexdigest()[:10]
    short = {VESSEL_ROUTING: "vsl", PORT_BERTHING: "prt", CARGO_CONNECTION: "cgo"}.get(domain, "dec")
    return f"dec-{short}-{digest}"


class DecisionEngine:
    """Holds the problems this process computed, and moves them through review."""

    def __init__(
        self,
        *,
        basis: Optional[CostBasis] = None,
        fx: Optional[FxTable] = None,
        currency: str = "USD",
        critic: Optional[DecisionCritic] = None,
        branches: Optional[BranchRegistry] = None,
        ledger: Any = None,
        capacity: int = 64,
    ) -> None:
        self.basis = basis if basis is not None else CostBasis()
        self.fx = fx if fx is not None else FxTable()
        self.currency = currency
        self.critic = critic or DecisionCritic()
        self.branches = branches if branches is not None else BranchRegistry(capacity=256)
        self.ledger = ledger
        self.capacity = capacity
        self._problems: Dict[str, DecisionProblem] = {}
        self._order: List[str] = []
        self._lock = threading.RLock()

    # -- building ----------------------------------------------------------
    def solve_vessel(
        self,
        state: ObservedWorldState,
        *,
        event_key: str,
        seed: Quantity,
        vessel_id: str,
        actor: DecisionActor,
        at: datetime,
        grid: Any = None,
        attention_item_id: Optional[str] = None,
        basis: Optional[CostBasis] = None,
        replay: Optional[Dict[str, Any]] = None,
        decision_id: Optional[str] = None,
    ) -> DecisionProblem:
        from src.portwatch_os.decision.vessel import build_vessel_problem

        problem = build_vessel_problem(
            state, decision_id=decision_id or decision_id_for(VESSEL_ROUTING, vessel_id, at, event_key),
            event_key=event_key, seed=seed, vessel_id=vessel_id, actor=actor, at=at,
            registry=self.branches, basis=basis if basis is not None else self.basis, fx=self.fx,
            currency=self.currency, grid=grid, attention_item_id=attention_item_id,
        )
        if replay:
            problem.evidence["replay"] = replay
        return self.finish(problem)

    def solve_port(
        self,
        state: Any,
        *,
        actor: DecisionActor,
        at: datetime,
        world_state_id: str,
        world_revision: Dict[str, Any],
        horizon_hours: float = 24.0,
        attention_item_id: Optional[str] = None,
        basis: Optional[CostBasis] = None,
        decision_id: Optional[str] = None,
    ) -> DecisionProblem:
        from src.portwatch_os.decision.port import build_port_problem

        problem = build_port_problem(
            state, decision_id=decision_id or decision_id_for(PORT_BERTHING, state.port_code, at, world_state_id),
            actor=actor, at=at, world_state_id=world_state_id, world_revision=world_revision,
            basis=basis if basis is not None else self.basis, fx=self.fx, currency=self.currency,
            horizon_hours=horizon_hours, attention_item_id=attention_item_id,
        )
        return self.finish(problem)

    def solve_cargo(
        self,
        shipment: Any,
        vessels: Sequence[Any],
        zones: Sequence[Any],
        *,
        actor: DecisionActor,
        at: datetime,
        port_code: str,
        world_state_id: str,
        world_revision: Dict[str, Any],
        now_hour: float = 0.0,
        attention_item_id: Optional[str] = None,
        basis: Optional[CostBasis] = None,
        decision_id: Optional[str] = None,
    ) -> DecisionProblem:
        from src.portwatch_os.decision.cargo import build_cargo_problem

        problem = build_cargo_problem(
            shipment, vessels, zones,
            decision_id=decision_id or decision_id_for(CARGO_CONNECTION, shipment.shipment_id, at, port_code),
            actor=actor, at=at, port_code=port_code, world_state_id=world_state_id,
            world_revision=world_revision, basis=basis if basis is not None else self.basis, fx=self.fx,
            currency=self.currency, now_hour=now_hour, attention_item_id=attention_item_id,
        )
        return self.finish(problem)

    def finish(self, problem: DecisionProblem, *, now: Optional[datetime] = None) -> DecisionProblem:
        """Criticise, rank, recommend and record. Idempotent on the problem."""
        moment = now or utc()
        for option in problem.options:
            verdict = self.critic.review_option(option, problem, now=moment)
            option.critic = verdict.to_dict()
            if verdict.verdict == REJECT and option.status != REJECTED:
                # The Critic found a blocking condition the constraint pass did
                # not express as a constraint (a closed window, say). The
                # option is withdrawn from ranking and says why.
                option.status = REJECTED
                option.provenance["rejectedByCritic"] = verdict.reasons

        frontier_keys = list(problem.evidence.get("frontierObjectives") or FRONTIER_DEFAULTS.get(problem.domain, ()))
        objectives = [OBJECTIVES[k] for k in frontier_keys if k in OBJECTIVES]
        problem.frontier = pareto(problem.options, objectives)
        ranking = rank(problem.options, problem.domain)
        problem.evidence["ranking"] = ranking

        chosen = self._choose(problem, ranking)
        if chosen is not None:
            baseline = problem.baseline
            comparison = against_baseline(chosen, baseline, problem.objectives)
            money = avoidable_cost(
                None if baseline is None or baseline.evaluation is None else _financial(baseline),
                None if chosen.evaluation is None else _financial(chosen),
            )
            problem.recommendation = DecisionRecommendation(
                option_id=chosen.option_id, actor=chosen.actor or problem.actor.role,
                ranking_basis={
                    "method": ranking.get("method"), "weights": ranking.get("weights"),
                    "objectivesUsed": ranking.get("objectivesUsed"),
                    "objectivesDropped": ranking.get("objectivesDropped"),
                    "score": (ranking.get("scores") or {}).get(chosen.option_id),
                    "order": ranking.get("order"),
                },
                against_baseline=comparison,
                expected_avoidable_cost=money,
                statement=_statement(problem, chosen, comparison),
            )
            problem.recommendation.critic = self.critic.review_recommendation(problem, chosen.option_id).to_dict()
        else:
            problem.recommendation = None
            problem.notes.append("no feasible option survived constraints and the Critic; nothing is recommended")

        problem.workflow_history.append({
            "at": moment.isoformat(timespec="seconds"), "state": COMPUTED, "actor": "portwatch-decision-engine",
            "note": f"{len(problem.feasible_options)} feasible, {len(problem.rejected_options)} rejected",
        })
        self._store(problem)
        self._record(problem)
        return problem

    def _choose(self, problem: DecisionProblem, ranking: Dict[str, Any]):
        frontier = problem.frontier
        for option_id in ranking.get("order") or []:
            option = problem.option(option_id)
            if option is None or not option.feasible:
                continue
            if option.critic and option.critic.get("verdict") == REJECT:
                continue
            if frontier is not None and option_id in frontier.dominated:
                continue
            if frontier is not None and option_id in frontier.incomparable:
                # Not measurable on a frontier objective: it may be shown, it
                # is not recommended over options that were.
                continue
            return option
        return None

    # -- registry ----------------------------------------------------------
    def _store(self, problem: DecisionProblem) -> None:
        with self._lock:
            if problem.decision_id not in self._problems:
                self._order.append(problem.decision_id)
            self._problems[problem.decision_id] = problem
            while len(self._order) > self.capacity:
                gone = self._order.pop(0)
                self._problems.pop(gone, None)

    def get(self, decision_id: str) -> Optional[DecisionProblem]:
        with self._lock:
            return self._problems.get(decision_id)

    def all(self) -> List[DecisionProblem]:
        with self._lock:
            return [self._problems[i] for i in self._order if i in self._problems]

    def clear(self) -> None:
        with self._lock:
            self._problems.clear()
            self._order.clear()

    # -- workflow ----------------------------------------------------------
    def transition(
        self,
        decision_id: str,
        target: str,
        *,
        actor: str,
        note: str = "",
        option_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> DecisionProblem:
        """Move a problem one workflow step, attributed and validated."""
        if target not in WORKFLOW_STATES:
            raise DecisionError(f"{target!r} is not a workflow state")
        if not actor:
            raise DecisionError("every workflow transition must name its actor")
        problem = self.get(decision_id)
        if problem is None:
            raise DecisionError(f"no decision {decision_id}")
        allowed = TRANSITIONS.get(problem.workflow, ())
        if target not in allowed:
            raise DecisionError(
                f"{problem.workflow} -> {target} is not a legal decision transition; from "
                f"{problem.workflow} the options are: {', '.join(allowed) or 'none'}"
            )
        if target == APPROVED:
            if not option_id:
                raise DecisionError("approving a decision means choosing an option; name one")
            option = problem.option(option_id)
            if option is None:
                raise DecisionError(f"{option_id} is not an option of {decision_id}")
            if option.status == REJECTED:
                raise DecisionError(
                    f"{option_id} was rejected ({'; '.join(c.detail for c in option.rejected_by) or 'by the Critic'}); "
                    "a rejected option cannot be approved"
                )
            problem.human_choice = option_id
        moment = now or utc()
        problem.workflow = target
        problem.workflow_history.append({
            "at": moment.isoformat(timespec="seconds"), "state": target, "actor": actor,
            "note": note, "optionId": option_id,
        })
        self._record(problem)
        return problem

    def record_outcome(
        self,
        decision_id: str,
        *,
        actor: str,
        actual_action: str,
        observed: Dict[str, float],
        note: str = "",
        now: Optional[datetime] = None,
    ) -> DecisionProblem:
        """What actually happened. The only step that may carry an outcome."""
        problem = self.get(decision_id)
        if problem is None:
            raise DecisionError(f"no decision {decision_id}")
        if problem.workflow not in (APPROVED, ACCEPTED, DECLINED):
            raise DecisionError(
                f"an outcome can be recorded once a decision is approved, accepted or declined; "
                f"{decision_id} is {problem.workflow}"
            )
        moment = now or utc()
        problem.workflow = OBSERVED
        problem.workflow_history.append({
            "at": moment.isoformat(timespec="seconds"), "state": OBSERVED, "actor": actor,
            "note": note, "actualAction": actual_action, "observed": dict(observed),
        })
        problem.evidence["outcome"] = {"actualAction": actual_action, "observed": dict(observed),
                                       "observedAt": moment.isoformat(timespec="seconds")}
        self._record(problem, outcome=True)
        return problem

    # -- ledger ------------------------------------------------------------
    def _record(self, problem: DecisionProblem, *, outcome: bool = False) -> None:
        if self.ledger is None:
            return
        from src.portwatch_os.decision.ledger import record_problem, resolve_problem

        if outcome:
            resolve_problem(self.ledger, problem)
        else:
            record_problem(self.ledger, problem)


def _financial(option):
    from src.portwatch_os.finance.evaluate import FinancialEvaluation
    from src.portwatch_os.finance.money import Money

    body = option.evaluation.financial if option.evaluation else None
    if not body:
        return None
    evaluation = FinancialEvaluation(currency=body.get("currency", "USD"))
    evaluation.unknown = list(body.get("unknown") or [])
    evaluation.assumption = bool(body.get("assumption"))
    if body.get("total"):
        evaluation.total = Money(body["total"]["amount"], body["total"]["currency"])
    if body.get("partialTotal"):
        evaluation.partial_total = Money(body["partialTotal"]["amount"], body["partialTotal"]["currency"])
    return evaluation


def _statement(problem: DecisionProblem, chosen, comparison: Dict[str, Dict[str, Any]]) -> str:
    if chosen.is_baseline:
        head = f"Continue the current plan for {problem.subject_label}."
    else:
        head = f"{chosen.label} for {problem.subject_label}."
    parts: List[str] = []
    for key in ("risk", "eta", "port_wait", "sailing", "fuel", "cost"):
        row = comparison.get(key)
        if not row or row.get("option") is None or row.get("baseline") is None:
            continue
        objective = OBJECTIVES[key]
        parts.append(f"{objective.label.lower()} {row['option']:.2f} vs {row['baseline']:.2f} {objective.unit} if unchanged")
    unknowns = [OBJECTIVES[k].label.lower() for k, row in comparison.items() if row.get("option") is None]
    tail = (" Not measured: " + ", ".join(unknowns) + ".") if unknowns else ""
    return head + (" " + "; ".join(parts) + "." if parts else "") + tail


_ENGINE: Optional[DecisionEngine] = None
_ENGINE_LOCK = threading.Lock()


def get_engine() -> DecisionEngine:
    """The process-wide engine, holding public tariffs and the process ledger."""
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            from src.portwatch_os.finance.tariffs import basis_with_public_tariffs
            from src.portwatch_os.ledger.store import get_ledger

            _ENGINE = DecisionEngine(basis=basis_with_public_tariffs(), ledger=get_ledger())
        return _ENGINE


def reset_engine() -> None:
    global _ENGINE
    with _ENGINE_LOCK:
        _ENGINE = None


__all__ = [
    "DecisionEngine",
    "FRONTIER_DEFAULTS",
    "TRANSITIONS",
    "decision_id_for",
    "get_engine",
    "reset_engine",
]
