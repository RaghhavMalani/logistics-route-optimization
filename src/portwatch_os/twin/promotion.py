"""Safe policy promotion.

A policy that trained well is a candidate, not a decision-maker. This module is
the gate between the two, and it is deliberately hard to pass:

    CANDIDATE -> EVALUATING -> APPROVED
                            -> REJECTED

To reach APPROVED a policy must clear every one of :data:`PROMOTION_CHECKS`:

*   **beats_baseline** -- higher mean reward than the incumbent rule.
*   **beats_best_optimiser** -- higher mean reward than the best hand-written
    optimiser available. This is the check that matters. A learned policy that
    beats first-come-first-served but loses to a greedy heuristic has not earned
    anything: shipping it would be *worse* than shipping the heuristic, and the
    complexity would buy negative value.
*   **no_violations** -- zero hard-constraint breaches across the evaluation.
*   **no_rejected_actions** -- the policy never proposed an infeasible action.
*   **tail_not_worse** -- the worst episode is not materially worse than the
    baseline's worst. A policy with a better mean and a catastrophic tail is a
    policy that will one day produce the catastrophe.
*   **sufficient_episodes** -- evaluated on enough held-out scenarios to mean
    something.
*   **held_out_seeds** -- the evaluation seeds are disjoint from the training
    seeds. Checked, not assumed.

Then, and only then, a named human approves it. The ledger refuses the APPROVED
transition without an approver, so this is enforced by storage rather than by
convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.portwatch_os.ledger.schema import (
    APPROVED,
    CANDIDATE,
    EVALUATING,
    REJECTED,
    PolicyRecord,
    utc_now,
)
from src.portwatch_os.ledger.store import LedgerError, LedgerStore
from src.portwatch_os.twin.rl import BenchmarkResult, PolicyEvaluation

#: Minimum held-out episodes before a result is treated as evidence.
MIN_EVALUATION_EPISODES = 30

#: How much worse the candidate's worst episode may be than the baseline's,
#: as a fraction of the baseline's worst. A little tolerance, because the worst
#: episode is itself a noisy statistic.
TAIL_TOLERANCE = 0.05

#: Improvement over the best available baseline that counts as real rather than
#: as sampling noise.
MIN_IMPROVEMENT = 0.01

PROMOTION_CHECKS: Tuple[str, ...] = (
    "beats_baseline",
    "beats_best_optimiser",
    "no_violations",
    "no_rejected_actions",
    "tail_not_worse",
    "sufficient_episodes",
    "held_out_seeds",
)


@dataclass
class PromotionDecision:
    """The verdict, with every check and why it landed that way."""

    policy_id: str
    passed: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    reasons: Dict[str, str] = field(default_factory=dict)
    #: The measured comparison the decision rests on.
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def failed_checks(self) -> List[str]:
        return sorted(name for name, ok in self.checks.items() if not ok)

    def summary(self) -> str:
        if self.passed:
            return (
                f"{self.policy_id} cleared every promotion check and is eligible for "
                "human approval."
            )
        failures = "; ".join(self.reasons[name] for name in self.failed_checks)
        return f"{self.policy_id} is not promotable: {failures}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policyId": self.policy_id,
            "passed": self.passed,
            "checks": self.checks,
            "reasons": self.reasons,
            "failedChecks": self.failed_checks,
            "evidence": self.evidence,
            "summary": self.summary(),
        }


def evaluate_promotion(
    benchmark: BenchmarkResult,
    candidate_policy_id: str,
    *,
    training_seeds: Optional[Sequence[int]] = None,
    min_episodes: int = MIN_EVALUATION_EPISODES,
) -> PromotionDecision:
    """Run every gate against a benchmark result. No side effects."""
    candidate = next(
        (e for e in benchmark.evaluations if e.policy_id == candidate_policy_id), None
    )
    if candidate is None:
        return PromotionDecision(
            policy_id=candidate_policy_id,
            passed=False,
            checks={name: False for name in PROMOTION_CHECKS},
            reasons={
                name: f"{candidate_policy_id} does not appear in the benchmark"
                for name in PROMOTION_CHECKS
            },
        )

    baseline = benchmark.baseline
    optimisers = [
        e for e in benchmark.evaluations
        if e.family == "optimiser" and e.policy_id != candidate_policy_id
    ]
    best_optimiser = max(optimisers, key=lambda e: e.mean_reward) if optimisers else None

    checks: Dict[str, bool] = {}
    reasons: Dict[str, str] = {}

    # -- beats the incumbent rule -----------------------------------------
    if baseline is None:
        checks["beats_baseline"] = False
        reasons["beats_baseline"] = "no baseline policy was included in the benchmark"
    else:
        improvement = benchmark.improvement(candidate_policy_id) or 0.0
        ok = candidate.mean_reward > baseline.mean_reward and improvement >= MIN_IMPROVEMENT
        checks["beats_baseline"] = ok
        reasons["beats_baseline"] = (
            f"mean reward {candidate.mean_reward:.1f} against the {baseline.name} "
            f"baseline's {baseline.mean_reward:.1f} "
            f"({improvement:+.1%}); {'clears' if ok else 'does not clear'} the "
            f"{MIN_IMPROVEMENT:.0%} threshold"
        )

    # -- beats the best hand-written optimiser ----------------------------
    if best_optimiser is None:
        checks["beats_best_optimiser"] = True
        reasons["beats_best_optimiser"] = (
            "no hand-written optimiser was in the benchmark, so there is nothing "
            "stronger to beat"
        )
    else:
        margin = candidate.mean_reward - best_optimiser.mean_reward
        relative = margin / abs(best_optimiser.mean_reward) if best_optimiser.mean_reward else 0.0
        ok = relative >= MIN_IMPROVEMENT
        checks["beats_best_optimiser"] = ok
        reasons["beats_best_optimiser"] = (
            f"mean reward {candidate.mean_reward:.1f} against the best optimiser "
            f"({best_optimiser.name}) at {best_optimiser.mean_reward:.1f}, "
            f"a margin of {margin:+.1f} ({relative:+.1%}). "
            + (
                "The learned policy is the better of the two."
                if ok else
                "The learned policy does not beat a simpler optimiser, so promoting it "
                "would add complexity for no measured gain."
            )
        )

    # -- safety ------------------------------------------------------------
    checks["no_violations"] = candidate.violations == 0
    reasons["no_violations"] = (
        f"{candidate.violations} hard-constraint violations across "
        f"{candidate.episodes} episodes"
    )

    checks["no_rejected_actions"] = candidate.rejected_actions == 0
    reasons["no_rejected_actions"] = (
        f"{candidate.rejected_actions} infeasible actions proposed and refused by the "
        "simulator"
    )

    if baseline is None:
        checks["tail_not_worse"] = False
        reasons["tail_not_worse"] = "no baseline to compare the worst episode against"
    else:
        allowance = abs(baseline.min_reward) * TAIL_TOLERANCE
        ok = candidate.min_reward >= baseline.min_reward - allowance
        checks["tail_not_worse"] = ok
        reasons["tail_not_worse"] = (
            f"worst episode {candidate.min_reward:.1f} against the baseline's "
            f"{baseline.min_reward:.1f}, within a {TAIL_TOLERANCE:.0%} tolerance"
            if ok else
            f"worst episode {candidate.min_reward:.1f} is materially worse than the "
            f"baseline's {baseline.min_reward:.1f}"
        )

    checks["sufficient_episodes"] = candidate.episodes >= min_episodes
    reasons["sufficient_episodes"] = (
        f"evaluated on {candidate.episodes} held-out episodes; {min_episodes} required"
    )

    # -- leakage -----------------------------------------------------------
    if training_seeds is None:
        checks["held_out_seeds"] = False
        reasons["held_out_seeds"] = (
            "no training seed range was supplied, so the evaluation cannot be shown to "
            "be out of sample"
        )
    else:
        overlap: Set[int] = set(training_seeds) & set(candidate.seeds)
        ok = not overlap
        checks["held_out_seeds"] = ok
        reasons["held_out_seeds"] = (
            f"{len(candidate.seeds)} evaluation seeds, none of them in the "
            f"{len(set(training_seeds))} training seeds"
            if ok else
            f"{len(overlap)} evaluation seeds were also used for training; the result "
            "measures memorisation, not generalisation"
        )

    return PromotionDecision(
        policy_id=candidate_policy_id,
        passed=all(checks.values()),
        checks=checks,
        reasons=reasons,
        evidence={
            "candidate": candidate.to_dict(),
            "baseline": baseline.to_dict() if baseline else None,
            "bestOptimiser": best_optimiser.to_dict() if best_optimiser else None,
            "episodes": benchmark.episodes,
            "spec": benchmark.spec,
        },
    )


def register_candidate(
    store: LedgerStore,
    *,
    policy_id: str,
    name: str,
    family: str,
    version: str,
    environment: str,
    training: Dict[str, Any],
    notes: Optional[str] = None,
) -> PolicyRecord:
    """Record a freshly trained policy as a candidate. Never as approved."""
    now = utc_now()
    record = PolicyRecord(
        policy_id=policy_id,
        name=name,
        family=family,
        version=version,
        state=CANDIDATE,
        created_at=now,
        updated_at=now,
        environment=environment,
        training=training,
        notes=notes,
    )
    store.upsert_policy(record)
    return record


def submit_for_evaluation(
    store: LedgerStore,
    policy_id: str,
    decision: PromotionDecision,
) -> PolicyRecord:
    """Move a candidate into EVALUATING and attach its measured evidence."""
    return store.transition_policy(
        policy_id,
        EVALUATING,
        evaluation=decision.to_dict(),
        safety_checks=dict(decision.checks),
    )


def approve(
    store: LedgerStore,
    policy_id: str,
    decision: PromotionDecision,
    *,
    approver: str,
) -> PolicyRecord:
    """Promote an evaluated policy. Refuses unless every gate passed.

    Two independent locks: this function refuses a failing decision, and the
    ledger itself refuses an APPROVED transition whose ``safety_checks`` carry a
    false. Belt and braces on purpose -- this is the one transition that changes
    what the product recommends to a human operator.
    """
    if not decision.passed:
        raise LedgerError(
            f"{policy_id} cannot be approved: {decision.summary()}"
        )
    if not approver:
        raise LedgerError(f"{policy_id} requires a named human approver")
    return store.transition_policy(
        policy_id,
        APPROVED,
        actor=approver,
        evaluation=decision.to_dict(),
        safety_checks=dict(decision.checks),
    )


def reject(
    store: LedgerStore,
    policy_id: str,
    decision: PromotionDecision,
    *,
    actor: Optional[str] = None,
) -> PolicyRecord:
    """Record that a policy failed its gate, with the reasons preserved.

    A rejected policy is kept, not deleted. The record of *why* a learned policy
    was not shipped is part of the evidence that the gate is doing anything.
    """
    return store.transition_policy(
        policy_id,
        REJECTED,
        actor=actor,
        reason=decision.summary(),
        evaluation=decision.to_dict(),
        safety_checks=dict(decision.checks),
    )


def active_policy(store: LedgerStore) -> Optional[PolicyRecord]:
    """The approved policy, if any. What the recommendation path may use.

    Returns ``None`` when nothing has been promoted, and the caller must then
    fall back to the hand-written optimiser. That is the intended steady state
    until a learned policy actually earns its place.
    """
    approved = store.policies(state=APPROVED)
    if not approved:
        return None
    return max(approved, key=lambda p: p.approved_at or p.updated_at or "")


def promotion_pipeline(
    store: LedgerStore,
    benchmark: BenchmarkResult,
    *,
    candidate_policy_id: str,
    name: str,
    version: str,
    environment: str,
    training: Dict[str, Any],
    training_seeds: Sequence[int],
    approver: Optional[str] = None,
) -> Tuple[PolicyRecord, PromotionDecision]:
    """Register, evaluate and resolve a candidate in one call.

    ``approver`` is optional and, when omitted, a passing candidate is left in
    EVALUATING rather than being promoted. An automated pipeline may never
    approve on its own behalf: the whole point of the gate is that a person
    signs it.
    """
    record = register_candidate(
        store,
        policy_id=candidate_policy_id,
        name=name,
        family="learned",
        version=version,
        environment=environment,
        training=training,
    )
    decision = evaluate_promotion(
        benchmark, candidate_policy_id, training_seeds=training_seeds
    )
    record = submit_for_evaluation(store, candidate_policy_id, decision)

    if not decision.passed:
        record = reject(store, candidate_policy_id, decision, actor="promotion pipeline")
    elif approver:
        record = approve(store, candidate_policy_id, decision, approver=approver)
    return record, decision


__all__ = [
    "MIN_EVALUATION_EPISODES",
    "MIN_IMPROVEMENT",
    "PROMOTION_CHECKS",
    "TAIL_TOLERANCE",
    "PromotionDecision",
    "active_policy",
    "approve",
    "evaluate_promotion",
    "promotion_pipeline",
    "register_candidate",
    "reject",
    "submit_for_evaluation",
]
