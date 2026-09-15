"""Performance budgets in ordinary CI: the small, stable subset, with slack.

The full benchmark and its gate (``scripts/benchmark_performance.py --gate``)
are the release check; they run for minutes at sizes a shared runner cannot
time reliably. This test holds the budgets marked ``in_ci`` -- a thousand
vessels, a hundred-vessel decision, a scenario branch, a 500-option frontier
-- at three times their ceiling, so a regression of an order of magnitude is
caught and a slow runner is not.

Every budget is a ceiling on a median over repeats, never on a single run.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from src.portwatch_os.perf_budgets import BUDGETS, by_key, judge

ROOT = Path(__file__).resolve().parents[1]
CI_MULTIPLIER = 3.0


class BudgetTableTests(unittest.TestCase):
    def test_every_budget_is_wider_than_what_it_was_set_from(self):
        for budget in BUDGETS:
            self.assertGreater(budget.budget_ms, budget.measured_ms, budget.key)
            self.assertLessEqual(budget.budget_ms, 4 * budget.measured_ms + 20, f"{budget.key}: a budget that loose is not a budget")
            self.assertIn(budget.statistic, ("median", "p95"))
        self.assertEqual(by_key()["decision_generation"].budget_ms, 750.0)
        self.assertEqual(by_key()["api_read_p95"].budget_ms, 25.0)
        self.assertEqual(by_key()["api_decision_post_p95"].budget_ms, 250.0)
        self.assertEqual(by_key()["world_build_10k"].budget_ms, 1000.0)
        self.assertEqual(by_key()["attention_10k"].budget_ms, 1000.0)

    def test_judge_reports_a_missing_figure_as_a_failure_not_a_pass(self):
        rows = judge({"world": {"byVessels": {"1000": {"wallMs": {"median": 10.0}}}}}, only_ci=True)
        world = next(r for r in rows if r["key"] == "world_build_1k")
        self.assertTrue(world["passed"])
        missing = next(r for r in rows if r["key"] == "pareto_500")
        self.assertFalse(missing["passed"])
        self.assertIsNone(missing["measuredMs"])

    def test_the_document_carries_the_budgets(self):
        text = (ROOT / "docs" / "PERFORMANCE.md").read_text(encoding="utf-8")
        self.assertIn("## Budgets", text)
        for budget in BUDGETS:
            self.assertIn(budget.label, text, budget.key)


class CiSubsetTests(unittest.TestCase):
    """The in_ci budgets, measured here and now, at three times the ceiling."""

    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("PORTWATCH_LICENCE_MODE", "DEMO")
        os.environ["PORTWATCH_FRESHNESS_SCHEDULER"] = "0"
        sys.path.insert(0, str(ROOT / "scripts"))
        import benchmark_performance as bench

        cls.results = {
            "world": bench.bench_world((1000,), (), repeats=3),
            "attention": bench.bench_attention((1000,), repeats=3),
            "decisionSmall": bench.bench_decision(100, repeats=3),
            "scenario": bench.bench_scenario(1000, repeats=3),
            "pareto": bench.bench_pareto((500,), repeats=3),
        }

    def test_the_ci_subset_stays_inside_three_times_its_ceiling(self):
        rows = judge(self.results, multiplier=CI_MULTIPLIER, only_ci=True)
        self.assertGreaterEqual(len(rows), 5)
        over = [f"{r['key']}: {r['measuredMs']} ms against {r['budgetMs']} ms" for r in rows if not r["passed"]]
        self.assertEqual(over, [], "\n".join(over))


if __name__ == "__main__":
    unittest.main()
