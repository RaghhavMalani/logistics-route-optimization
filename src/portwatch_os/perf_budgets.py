"""Performance budgets: the figures the product commits to, set from what was
measured and wide enough that a normal machine on a normal day does not trip
them.

Each budget names the measurement it was set from (``docs/PERFORMANCE.md``,
2026-09-15, one Windows workstation, Python 3.12) and is roughly twice that
figure rounded to something an engineer can hold in their head. Two uses:

*   ``scripts/benchmark_performance.py --gate`` judges a full run against the
    table and exits non-zero on a breach -- the release check;
*   ``tests/test_perf_budgets.py`` runs a small, stable subset in ordinary CI
    with the ``ciMultiplier`` applied, because a shared CI runner is slower
    and noisier than the workstation the figures came from and a flaky gate
    is a gate people learn to ignore.

A budget is a ceiling on a median or a p95, never on a single run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Budget:
    key: str
    label: str
    #: The ceiling, in milliseconds.
    budget_ms: float
    #: What the benchmark reported when the budget was set.
    measured_ms: float
    #: Which statistic the ceiling applies to: "median" or "p95".
    statistic: str
    #: Where in the benchmark's JSON the figure is read from.
    source: str
    #: Whether the ordinary CI test exercises it (small sizes only).
    in_ci: bool = False
    #: Slack CI runners get over the budget.
    ci_multiplier: float = 3.0

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "label": self.label, "budgetMs": self.budget_ms, "measuredMs": self.measured_ms,
                "statistic": self.statistic, "source": self.source, "inCi": self.in_ci, "ciMultiplier": self.ci_multiplier}


BUDGETS: Tuple[Budget, ...] = (
    Budget("world_build_10k", "World State build, 10,000 vessels", 1000.0, 503.6, "median", "world.byVessels.10000.wallMs.median"),
    Budget("world_build_1k", "World State build, 1,000 vessels", 150.0, 49.7, "median", "world.byVessels.1000.wallMs.median", in_ci=True),
    Budget("cascade_fanout_10k", "Cascade query, every chokepoint, 10,000 vessels", 400.0, 187.2, "median", "cascade.fanout.10000.wallMs.median"),
    Budget("attention_10k", "Attention queue, 10,000 vessels", 1000.0, 703.3, "median", "attention.10000.wallMs.median"),
    Budget("attention_1k", "Attention queue, 1,000 vessels", 400.0, 154.7, "median", "attention.1000.wallMs.median", in_ci=True),
    Budget("decision_generation", "DecisionProblem, vessel routing, 1,000-vessel world", 750.0, 404.5, "median", "decision.wallMs.median"),
    Budget("decision_generation_small", "DecisionProblem, vessel routing, 100-vessel world", 500.0, 158.1, "median", "decisionSmall.wallMs.median", in_ci=True),
    Budget("scenario_branch", "Scenario branch and cascade, 1,000 vessels", 100.0, 30.0, "median", "scenario.wallMs.median", in_ci=True),
    Budget("pareto_500", "Pareto frontier, 500 options", 100.0, 26.6, "median", "pareto.500.wallMs.median", in_ci=True),
    Budget("mission_replay", "Mission replay, decide every hull and reveal (Ever Given)", 750.0, 338.6, "median", "missions.suez-ever-given-2021.wallMs.median"),
    Budget("api_read_p95", "Read API, p95 across the read routes", 25.0, 7.3, "p95", "apiReads.p95Ms"),
    Budget("api_decision_post_p95", "POST /api/decisions/problems, p95", 250.0, 70.9, "p95", "api.POST /api/decisions/problems.p95Ms"),
)


def by_key() -> Dict[str, Budget]:
    return {b.key: b for b in BUDGETS}


def _dig(results: Dict[str, Any], path: str) -> Optional[float]:
    node: Any = results
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return float(node) if isinstance(node, (int, float)) else None


def judge(results: Dict[str, Any], *, multiplier: float = 1.0, only_ci: bool = False) -> List[Dict[str, Any]]:
    """Every budget against a benchmark result. A missing figure is reported,
    not passed."""
    rows: List[Dict[str, Any]] = []
    for budget in BUDGETS:
        if only_ci and not budget.in_ci:
            continue
        measured = _dig(results, budget.source)
        ceiling = budget.budget_ms * multiplier
        rows.append({
            "key": budget.key, "label": budget.label, "budgetMs": round(ceiling, 1), "statistic": budget.statistic,
            "measuredMs": None if measured is None else round(measured, 1),
            "setFromMs": budget.measured_ms,
            "passed": measured is not None and measured <= ceiling,
            "headroom": None if measured is None or ceiling <= 0 else round(1.0 - measured / ceiling, 3),
        })
    return rows


__all__ = ["BUDGETS", "Budget", "by_key", "judge"]
