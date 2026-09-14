"""Writing decisions to the ledger, and reading them back for scoring.

Two records per problem. The :class:`DecisionProblemRecord` holds the whole
problem exactly as computed -- every option, the rejected ones with the
constraint that rejected them, the frontier, the recommendation and the
Critic's verdicts -- and the columns that are filled in afterwards: the human
choice, the action taken, the observed outcome. A :class:`DecisionRecord` for
the recommendation itself is written alongside, so the existing outcome agent
and take-up statistics see decision-engine recommendations in the same table
as advisories.

The computed payload is immutable at the store. A later workflow step
updates the workflow columns and nothing else, which is what lets the
learning pass reconstruct the decision from the record with no retrospective
information in it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.portwatch_os.decision.model import DecisionProblem
from src.portwatch_os.ledger.schema import (
    ACTION_MODIFIED,
    ACTION_NOT_TAKEN,
    ACTION_PENDING,
    ACTION_TAKEN,
    DecisionProblemRecord,
    DecisionRecord,
    utc_now,
)

MODEL = "portwatch-decision-engine"
MODEL_VERSION = "2"


def problem_record(problem: DecisionProblem) -> DecisionProblemRecord:
    recommendation = problem.recommendation
    return DecisionProblemRecord(
        problem_id=problem.decision_id,
        domain=problem.domain,
        subject=problem.subject_id,
        actor=problem.actor.role,
        issued_at=problem.created_at,
        world_state_id=problem.world_state_id,
        world_revision=dict(problem.world_revision),
        at=problem.at,
        problem=problem.to_dict(include_options=True),
        recommended_option=None if recommendation is None else recommendation.option_id,
        baseline_option=problem.baseline_option_id,
        options_evaluated=len(problem.options),
        options_rejected=len(problem.rejected_options),
        critic_verdict=None if recommendation is None or not recommendation.critic
        else recommendation.critic.get("verdict"),
        workflow=problem.workflow,
        human_choice=problem.human_choice,
    )


def decision_record(problem: DecisionProblem) -> Optional[DecisionRecord]:
    recommendation = problem.recommendation
    if recommendation is None:
        return None
    option = problem.option(recommendation.option_id)
    expected: Dict[str, float] = {}
    for key, row in recommendation.against_baseline.items():
        if row.get("delta") is not None:
            # Positive means the option improves on the baseline on that
            # objective; scored later against the observed delta.
            direction = 1.0 if row.get("better") else (-1.0 if row.get("better") is False else 0.0)
            expected[f"{key}_improvement"] = abs(float(row["delta"])) * direction
    return DecisionRecord(
        decision_id=f"{problem.decision_id}-rec",
        kind=f"decision:{problem.domain.lower()}",
        subject=problem.subject_id,
        issued_at=problem.created_at,
        issuer=MODEL,
        recommendation={
            "optionId": recommendation.option_id,
            "action": None if option is None else option.action,
            "label": None if option is None else option.label,
            "params": {} if option is None else option.params,
        },
        reason=recommendation.statement,
        model=MODEL,
        model_version=MODEL_VERSION,
        confidence=None if option is None or option.evaluation is None else option.evaluation.weakest_confidence,
        expected_impact=expected,
        critic_verdict=None if not recommendation.critic else recommendation.critic.get("verdict"),
        critic_reasons=[] if not recommendation.critic else list(recommendation.critic.get("reasons") or []),
        approval_state=problem.workflow.lower(),
        action_state=ACTION_PENDING,
    )


def record_problem(ledger: Any, problem: DecisionProblem) -> None:
    ledger.record_decision_problem(problem_record(problem))
    record = decision_record(problem)
    if record is not None:
        existing = ledger.get_decision(record.decision_id)
        if existing is None or existing.status != "resolved":
            ledger.record_decision(record)


def resolve_problem(ledger: Any, problem: DecisionProblem) -> None:
    outcome = problem.evidence.get("outcome") or {}
    full = dict(outcome.get("observed") or {})
    # The problem record keeps everything, counterfactual outcomes included;
    # the legacy decision row is scalar-only.
    observed = {k: float(v) for k, v in full.items() if isinstance(v, (int, float))}
    actual = str(outcome.get("actualAction") or "")
    observed_at = outcome.get("observedAt") or utc_now()
    ledger.resolve_decision_problem(
        problem.decision_id, human_choice=problem.human_choice, actual_action=actual,
        observed_outcome=full, observed_at=observed_at,
    )
    recommendation = problem.recommendation
    if recommendation is None:
        return
    recommended = problem.option(recommendation.option_id)
    recommended_action = None if recommended is None else recommended.action
    if actual == recommended_action:
        state = ACTION_TAKEN
    elif actual and problem.human_choice == recommendation.option_id:
        state = ACTION_MODIFIED
    else:
        state = ACTION_NOT_TAKEN
    existing = ledger.get_decision(f"{problem.decision_id}-rec")
    if existing is not None and existing.status != "resolved":
        ledger.resolve_decision(
            f"{problem.decision_id}-rec", state, observed, observed_at,
        )


__all__ = ["MODEL", "MODEL_VERSION", "decision_record", "problem_record", "record_problem", "resolve_problem"]
