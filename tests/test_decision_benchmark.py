"""The decision benchmark corpus: fixed, blind, and honest about losses.

    the same seed produces the same cases and the same choices
    no policy is handed the truth; the truth changes only the scores
    an infeasible pick is a violation, scored as doing nothing
    a case PortWatch lost on is listed with what beat it
    the aggregate counts every case, including the ones the engine refused
"""

from __future__ import annotations

import unittest

from src.portwatch_os.decision import DecisionEngine
from src.portwatch_os.decision.benchmark import (
    CARGO,
    DOMAINS,
    POLICIES,
    PORT,
    VESSEL,
    aggregate,
    losses,
    run_cargo_case,
    run_port_case,
    run_suite,
    run_vessel_case,
)


class CorpusTests(unittest.TestCase):
    def test_the_same_seed_gives_the_same_case_and_the_same_choices(self):
        engine = DecisionEngine(capacity=64)
        a = run_vessel_case(4, engine)
        b = run_vessel_case(4, DecisionEngine(capacity=64))
        self.assertEqual(a.description, b.description)
        self.assertEqual(a.truth, b.truth)
        self.assertEqual({p: c.option_id for p, c in a.choices.items()}, {p: c.option_id for p, c in b.choices.items()})
        self.assertEqual({p: c.delay for p, c in a.choices.items()}, {p: c.delay for p, c in b.choices.items()})

    def test_every_policy_answers_every_case_in_every_domain(self):
        engine = DecisionEngine(capacity=64)
        for runner, seed in ((run_vessel_case, 7), (run_port_case, 2), (run_cargo_case, 3)):
            result = runner(seed, engine)
            self.assertIsNone(result.error, result.error)
            self.assertEqual(set(result.choices), set(POLICIES))
            for choice in result.choices.values():
                self.assertIsNotNone(choice.option_id, f"{result.case_id}: {choice.policy} chose nothing")
            self.assertIsNotNone(result.best_option_id)

    def test_the_truth_never_reaches_a_policy(self):
        """Changing the hidden truth changes the scores, never the choices."""
        from src.portwatch_os.decision import benchmark as module

        engine = DecisionEngine(capacity=64)
        original = module._vessel_case
        baseline = run_vessel_case(4, engine)

        def longer_closure(seed):
            event, subject, truth, description = original(seed)
            truth = {**truth, "closureHours": 400.0, "fizzled": False,
                     "reopenedAt": (module.NOW.replace(microsecond=0) + module.timedelta(hours=400)).isoformat(timespec="seconds"),
                     "backlogClearedAt": (module.NOW.replace(microsecond=0) + module.timedelta(hours=520)).isoformat(timespec="seconds")}
            return event, subject, truth, description

        module._vessel_case = longer_closure
        try:
            altered = run_vessel_case(4, DecisionEngine(capacity=64))
        finally:
            module._vessel_case = original
        self.assertEqual({p: c.option_id for p, c in baseline.choices.items()},
                         {p: c.option_id for p, c in altered.choices.items()})
        self.assertNotEqual(baseline.choices["current_plan"].delay, altered.choices["current_plan"].delay)

    def test_regret_is_measured_against_the_realised_best_and_is_never_negative(self):
        engine = DecisionEngine(capacity=64)
        for runner, seed in ((run_vessel_case, 1), (run_port_case, 1), (run_cargo_case, 1)):
            result = runner(seed, engine)
            for choice in result.choices.values():
                if choice.regret is not None:
                    self.assertGreaterEqual(choice.regret, -1e-6, f"{result.case_id} {choice.policy}")
            best = [c for c in result.choices.values() if c.regret == 0]
            self.assertTrue(best or all(c.regret is None for c in result.choices.values()))

    def test_an_infeasible_pick_is_a_violation_scored_as_doing_nothing(self):
        from src.portwatch_os.decision import benchmark as module

        engine = DecisionEngine(capacity=64)
        original = module._vessel_policies

        def pick_impossible(problem, event):
            picks = original(problem, event)
            # A rejected option where the case has one; otherwise an option the
            # engine never offered. Both are things a policy may not do.
            rejected = next((o for o in problem.options if not o.feasible), None)
            picks["greedy"] = (rejected.option_id if rejected else "not-an-option", 0.0, "forced")
            return picks

        module._vessel_policies = pick_impossible
        try:
            found = run_vessel_case(4, engine)
        finally:
            module._vessel_policies = original
        self.assertIsNone(found.error)
        self.assertEqual(found.choices["greedy"].violations, 1)
        self.assertEqual(found.choices["greedy"].delay, found.choices["current_plan"].delay)
        self.assertIn("infeasible pick", found.choices["greedy"].note)


class AggregateTests(unittest.TestCase):
    def test_the_suite_aggregates_every_domain_and_lists_losses_with_what_beat_them(self):
        out = run_suite(cases_per_domain=4, base_seed=1)
        self.assertEqual(set(out["aggregate"]), set(DOMAINS))
        for domain in DOMAINS:
            table = out["aggregate"][domain]
            self.assertEqual(table["cases"] + table["errors"], 4)
            self.assertEqual(set(table["policies"]), set(POLICIES))
            self.assertEqual(set(table["headToHead"]), {"portwatch_balanced", "portwatch_robust"})
            for mine, rows in table["headToHead"].items():
                self.assertEqual(set(rows), set(POLICIES) - {mine})
            for policy, summary in table["policies"].items():
                for key in ("meanRegret", "medianRegret", "p90Regret", "worstRegret", "interventionRate",
                            "unnecessaryInterventionRate", "waitRate", "p95DecisionMs"):
                    self.assertIn(key, summary, f"{policy} lacks {key}")
            self.assertIn("beneficialInterventionCapture", table)
        for loss in out["losses"]:
            self.assertIn(loss["domain"], DOMAINS)
            self.assertTrue(loss["beatenBy"])
            for policy, row in loss["beatenBy"].items():
                self.assertLess(row["delay"], loss["portwatch"]["delay"])
        self.assertEqual(len(out["results"]), 12)

    def test_a_refused_case_is_counted_not_dropped(self):
        from src.portwatch_os.decision.benchmark import CaseResult

        refused = CaseResult(VESSEL, "vessel-x", 99, "refused", {}, 0, 0, None, None, error="VesselDecisionError: no")
        table = aggregate([refused])
        self.assertEqual(table[VESSEL]["errors"], 1)
        self.assertEqual(table[VESSEL]["cases"], 0)
        self.assertEqual(losses([refused]), [])


if __name__ == "__main__":
    unittest.main()
