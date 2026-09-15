"""The decision-policy promotion gate: a new recommendation policy ships only
when a held-out corpus says it is better, by conditions fixed before the
corpus was run.

The RL policy gate (:mod:`src.portwatch_os.twin.promotion`) already refuses a
learned berth policy that has not beaten the hand-written optimiser out of
sample. This is the same discipline applied to the recommendation policy
itself: the robust gate is a candidate, the BALANCED expected-value ranking
is the incumbent, and the candidate replaces it only if it clears every one
of :data:`PROMOTION_CHECKS` on the validation corpus *and* on the untouched
test corpus. If it fails, the incumbent stays and the failure is published.

The checks, per domain, candidate against incumbent:

*   **no_more_violations** -- no increase in hard-constraint violations.
*   **mean_regret_lower** -- mean regret lower by at least
    :data:`MIN_IMPROVEMENT` on the domain the candidate changes (VESSEL), and
    not higher anywhere else.
*   **p90_regret_lower** -- the same on the 90th percentile of regret.
*   **worst_case_not_worse** -- worst-case regret no more than
    :data:`TAIL_TOLERANCE` worse than the incumbent's.
*   **intervention_rate_reasonable** -- the candidate intervenes no more
    often than the incumbent (within a small tolerance) and its
    unnecessary-intervention rate is no higher. How many of the cases where
    an intervention was the realised best each policy captured is published
    beside the check: a policy that has quietly become "never act" shows as
    a capture of zero, and the reader is told, rather than the gate deciding
    that a hedge which loses on net should have been taken.
*   **held_out** -- the corpus seeds are disjoint from the tuning corpus.
*   **sufficient_cases** -- at least :data:`MIN_CASES` declared cases per
    domain, with no more than :data:`MAX_REFUSED_SHARE` of them refused by
    the engine (a refusal is counted and reported, never dropped).

The verdict is APPROVED or REJECTED. Nothing here promotes a policy in code:
the engine's default is set by hand to what the published verdict says, and
the test suite asserts the two agree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.decision.benchmark import CANDIDATE, CORPORA, DOMAINS, INCUMBENT, VESSEL

#: Relative improvement in mean and p90 regret that counts as material on the
#: domain the candidate changes.
MIN_IMPROVEMENT = 0.10
#: How much worse the candidate's worst case may be, as a fraction of the
#: incumbent's worst case (or one hour where the incumbent's worst is zero).
TAIL_TOLERANCE = 0.05
#: Declared cases per domain below which the corpus is not evidence.
MIN_CASES = 100
#: Share of a domain's cases the engine may refuse before the corpus is suspect.
MAX_REFUSED_SHARE = 0.10
#: Intervening more often than this over the incumbent is not "reasonable".
INTERVENTION_RATE_TOLERANCE = 0.05

PROMOTION_CHECKS: Tuple[str, ...] = (
    "no_more_violations",
    "mean_regret_lower",
    "p90_regret_lower",
    "worst_case_not_worse",
    "intervention_rate_reasonable",
    "held_out",
    "sufficient_cases",
)

APPROVED = "APPROVED"
REJECTED = "REJECTED"


@dataclass
class PolicyGateDecision:
    corpus: str
    candidate: str
    incumbent: str
    passed: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    reasons: Dict[str, str] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def verdict(self) -> str:
        return APPROVED if self.passed else REJECTED

    @property
    def failed_checks(self) -> List[str]:
        return sorted(name for name, ok in self.checks.items() if not ok)

    def summary(self) -> str:
        if self.passed:
            return f"{self.candidate} clears every promotion check on the {self.corpus} corpus against {self.incumbent}."
        failures = "; ".join(self.reasons[name] for name in self.failed_checks)
        return f"{self.candidate} is not promotable on the {self.corpus} corpus: {failures}"

    def to_dict(self) -> Dict[str, Any]:
        return {"corpus": self.corpus, "candidate": self.candidate, "incumbent": self.incumbent,
                "passed": self.passed, "verdict": self.verdict, "checks": self.checks, "reasons": self.reasons,
                "failedChecks": self.failed_checks, "evidence": self.evidence, "summary": self.summary()}


def _num(value: Optional[float]) -> float:
    return 0.0 if value is None else float(value)


def evaluate_policy_promotion(
    suite: Dict[str, Any],
    *,
    candidate: str = CANDIDATE,
    incumbent: str = INCUMBENT,
    tuning_range: Optional[Tuple[int, int]] = None,
    min_cases: int = MIN_CASES,
) -> PolicyGateDecision:
    """Run every gate against one suite result. No side effects."""
    corpus = str(suite.get("corpus") or "unnamed")
    aggregate = suite.get("aggregate") or {}
    checks: Dict[str, bool] = {}
    reasons: Dict[str, str] = {}
    evidence: Dict[str, Any] = {"domains": {}}

    # -- per-domain figures ---------------------------------------------------
    rows: Dict[str, Dict[str, Any]] = {}
    for domain in DOMAINS:
        table = aggregate.get(domain) or {}
        policies = table.get("policies") or {}
        mine, theirs = policies.get(candidate), policies.get(incumbent)
        if mine is None or theirs is None:
            continue
        rows[domain] = {"candidate": mine, "incumbent": theirs, "cases": table.get("cases", 0),
                        "interventionWasBest": table.get("interventionWasBest"),
                        "capture": (table.get("beneficialInterventionCapture") or {})}
        evidence["domains"][domain] = rows[domain]
    if not rows:
        return PolicyGateDecision(corpus, candidate, incumbent, False,
                                  {name: False for name in PROMOTION_CHECKS},
                                  {name: f"{candidate} or {incumbent} is absent from the suite" for name in PROMOTION_CHECKS})

    # -- violations ------------------------------------------------------------
    worse = [d for d, r in rows.items() if r["candidate"]["violations"] > r["incumbent"]["violations"]]
    checks["no_more_violations"] = not worse
    reasons["no_more_violations"] = "; ".join(
        f"{d}: {r['candidate']['violations']} against {r['incumbent']['violations']}" for d, r in rows.items()
    ) + (" -- more violations on " + ", ".join(worse) if worse else "")

    # -- regret: material on VESSEL, not worse elsewhere -----------------------
    def _regret_check(name: str, key: str) -> None:
        details: List[str] = []
        ok = True
        for domain, r in rows.items():
            mine, theirs = _num(r["candidate"].get(key)), _num(r["incumbent"].get(key))
            if domain == VESSEL:
                needed = theirs * (1.0 - MIN_IMPROVEMENT)
                passed = mine <= needed and (theirs == 0.0 or mine < theirs)
                if theirs == 0.0:
                    passed = mine == 0.0
                details.append(f"{domain}: {mine:.2f} against {theirs:.2f} (needs <= {needed:.2f})")
            else:
                passed = mine <= theirs + 1e-9
                details.append(f"{domain}: {mine:.2f} against {theirs:.2f} (must not rise)")
            ok = ok and passed
        checks[name] = ok
        reasons[name] = f"{key}: " + "; ".join(details)

    _regret_check("mean_regret_lower", "meanRegret")
    _regret_check("p90_regret_lower", "p90Regret")

    # -- tail ------------------------------------------------------------------
    details = []
    ok = True
    for domain, r in rows.items():
        mine, theirs = _num(r["candidate"].get("worstRegret")), _num(r["incumbent"].get("worstRegret"))
        allowance = theirs * TAIL_TOLERANCE if theirs > 0 else 1.0
        passed = mine <= theirs + allowance
        ok = ok and passed
        details.append(f"{domain}: worst {mine:.1f} against {theirs:.1f} (+{allowance:.1f} allowed)")
    checks["worst_case_not_worse"] = ok
    reasons["worst_case_not_worse"] = "; ".join(details)

    # -- intervention behaviour ------------------------------------------------
    details = []
    ok = True
    for domain, r in rows.items():
        mine, theirs = r["candidate"], r["incumbent"]
        rate_ok = _num(mine.get("interventionRate")) <= _num(theirs.get("interventionRate")) + INTERVENTION_RATE_TOLERANCE
        unnecessary_ok = _num(mine.get("unnecessaryInterventionRate")) <= _num(theirs.get("unnecessaryInterventionRate")) + 1e-9
        capture = r["capture"]
        best_count = r.get("interventionWasBest") or 0
        passed = rate_ok and unnecessary_ok
        ok = ok and passed
        details.append(
            f"{domain}: intervenes {_num(mine.get('interventionRate')):.0%} against {_num(theirs.get('interventionRate')):.0%}, "
            f"unnecessary {_num(mine.get('unnecessaryInterventionRate')):.0%} against "
            f"{_num(theirs.get('unnecessaryInterventionRate')):.0%}, captures "
            f"{_num(capture.get(candidate)):.0%} of the {best_count} case(s) where an intervention was best "
            f"(incumbent {_num(capture.get(incumbent)):.0%})"
        )
    checks["intervention_rate_reasonable"] = ok
    reasons["intervention_rate_reasonable"] = "; ".join(details)

    # -- leakage ---------------------------------------------------------------
    seed_range = suite.get("seedRange") or [suite.get("baseSeed"), None]
    tuning = tuning_range or (CORPORA["tuning"][0], CORPORA["tuning"][0] + CORPORA["tuning"][1] - 1)
    first, last = seed_range[0], seed_range[1]
    if first is None or last is None:
        checks["held_out"] = False
        reasons["held_out"] = "the suite states no seed range"
    else:
        overlap = not (last < tuning[0] or first > tuning[1])
        checks["held_out"] = not overlap
        reasons["held_out"] = (
            f"seeds {first}-{last} against the tuning corpus's {tuning[0]}-{tuning[1]}: "
            + ("disjoint" if not overlap else "overlapping; the result measures memorisation")
        )

    # -- size ------------------------------------------------------------------
    # The corpus size is what was declared; a case the engine refused is
    # counted and reported, not dropped, and too many refusals is a finding.
    declared = {d: (aggregate.get(d) or {}).get("cases", 0) + (aggregate.get(d) or {}).get("errors", 0) for d in rows}
    refused = {d: (aggregate.get(d) or {}).get("errors", 0) for d in rows}
    smallest = min(declared.values())
    most_refused = max((refused[d] / declared[d]) if declared[d] else 1.0 for d in rows)
    checks["sufficient_cases"] = smallest >= min_cases and most_refused <= MAX_REFUSED_SHARE
    reasons["sufficient_cases"] = (
        f"{smallest} declared cases in the smallest domain ({min_cases} required); refused by the engine: "
        + ", ".join(f"{d} {refused[d]}" for d in rows) + f" (at most {MAX_REFUSED_SHARE:.0%} allowed)"
    )

    return PolicyGateDecision(corpus, candidate, incumbent, all(checks.values()), checks, reasons, evidence)


def final_verdict(decisions: Sequence[PolicyGateDecision]) -> Dict[str, Any]:
    """APPROVED only if every held-out corpus approved; the first failure names why."""
    held_out = [d for d in decisions if d.corpus in ("validation", "test")]
    passed = bool(held_out) and all(d.passed for d in held_out) and {"validation", "test"} <= {d.corpus for d in held_out}
    return {
        "verdict": APPROVED if passed else REJECTED,
        "corpora": {d.corpus: d.verdict for d in decisions},
        "activePolicy": CANDIDATE if passed else INCUMBENT,
        "summary": (
            f"{CANDIDATE} approved on validation and test; it is the active policy."
            if passed else
            f"{CANDIDATE} rejected: " + "; ".join(d.summary() for d in held_out if not d.passed)
            + (f"; the incumbent {INCUMBENT} stays active" if held_out else
               "; no held-out corpus was evaluated")
        ),
    }


__all__ = [
    "APPROVED",
    "INTERVENTION_RATE_TOLERANCE",
    "MAX_REFUSED_SHARE",
    "MIN_CASES",
    "MIN_IMPROVEMENT",
    "PROMOTION_CHECKS",
    "PolicyGateDecision",
    "REJECTED",
    "TAIL_TOLERANCE",
    "evaluate_policy_promotion",
    "final_verdict",
]
