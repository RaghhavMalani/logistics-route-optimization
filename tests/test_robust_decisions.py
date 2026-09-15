"""The robust decision policy: an intervention only when it survives not
knowing how long the disruption lasts.

    the closure outcome model is one function, shared with the mission scorecard
    the recorded drain fractions match the missions' stated outcomes
    four labelled stress horizons, no invented probabilities
    the regret table, the picks and the break-even are computed, not asserted
    KEEP_CURRENT_PLAN when no intervention beats the plan under any horizon
    WAIT_FOR_MORE_INFORMATION when the window permits and the horizon decides it
    ACT when the intervention clears every blocking check
    an irreversible move must be justified by the claim as stated
    a recommendation dominated in expectation says why it was still chosen
    the incumbent policy is still available and still answers as it did
    the benchmark scores a WAIT by simulating the wait
    the promotion gate refuses a candidate that is not better out of sample
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.portwatch_os.decision.benchmark import CANDIDATE, CORPORA, INCUMBENT, POLICIES, run_vessel_case
from src.portwatch_os.decision.engine import ACTIVE_POLICY, DecisionEngine, POLICIES as ENGINE_POLICIES
from src.portwatch_os.decision.model import (
    ACT,
    DecisionActor,
    DecisionError,
    DecisionEvaluation,
    DecisionOption,
    DecisionProblem,
    DecisionRecommendation,
    FEASIBLE,
    KEEP_CURRENT_PLAN,
    OBJECTIVES,
    SHIPPING_COMPANY,
    VESSEL_ROUTING,
    WAIT_FOR_MORE_INFORMATION,
    known,
)
from src.portwatch_os.decision.outcome import (
    BIPARJOY_DRAIN_FRACTION,
    ClosureWindow,
    EVER_GIVEN_DRAIN_FRACTION,
    QUEUE_MODELS,
    closure_delay_hours,
    parse_instant,
)
from src.portwatch_os.decision.promotion import evaluate_policy_promotion, final_verdict
from src.portwatch_os.decision.robust import (
    BALANCED_POLICY,
    NOISE_TOLERANCE_HOURS,
    REVERSIBLE_HIGH,
    REVERSIBLE_OPEN,
    REVERSIBLE_UNTIL_BRANCH,
    ROBUST_POLICY,
    assess,
    break_even,
    reversibility_of,
    stress_scenarios,
)

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# constructed problems: the gate logic without the world
# --------------------------------------------------------------------------


def option(option_id, action, *, hours_to_choke=None, hold=0.0, eta=None, certain=True, closes=None,
           baseline=False, weather=None):
    measures = {}
    if eta is not None:
        measures["eta"] = known(eta, "hours", basis="test", confidence=0.8 if certain else 0.6, certain=certain)
    measures["risk"] = known(0.0 if hours_to_choke is None else 0.5, "risk", basis="test", confidence=0.7)
    measures["fuel"] = known(1.0, "index", basis="test", confidence=0.5)
    if weather is not None:
        measures["weather"] = known(weather, "m", basis="test", confidence=0.6)
    evaluation = DecisionEvaluation(objectives=measures, derived={
        "hoursToChokepoint": hours_to_choke, "holdHours": hold, "destinationPort": "INNSA",
    })
    return DecisionOption(option_id=option_id, action=action, label=option_id.replace("_", " "), actor=SHIPPING_COMPANY,
                          status=FEASIBLE, evaluation=evaluation, is_baseline=baseline,
                          provenance={"closesInHours": closes}, critic={"verdict": "PASS"})


def problem_with(options, *, claim_from_hours_ago=6.0, claim_remaining=72.0, hours_to_risk=10.0):
    claim_from = NOW - timedelta(hours=claim_from_hours_ago)
    claim_end = NOW + timedelta(hours=claim_remaining)
    baseline = next(o for o in options if o.is_baseline)
    problem = DecisionProblem(
        decision_id="t-1", created_at=NOW.isoformat(), domain=VESSEL_ROUTING, world_revision={"mode": "DEMO"},
        world_state_id="s", subject_type="vessel", subject_id="V-1", subject_label="MV Test",
        actor=DecisionActor(SHIPPING_COMPANY), at=NOW.isoformat(),
        objectives=[OBJECTIVES[k] for k in ("eta", "risk", "fuel")],
        baseline_option_id=baseline.option_id, options=list(options),
        evidence={
            "event": {"key": "event:E", "label": "closure", "claimFrom": claim_from.isoformat(),
                      "claimLapsesAt": claim_end.isoformat(), "seed": {"confidence": 0.7, "attrs": {"calibrated": False}}},
            "exposure": {"attrs": {"hours_to_risk_area": hours_to_risk}},
            "closureModel": {"riskKind": "chokepoint", "at": "SUEZ", "hoursToRisk": hours_to_risk},
            "frontierObjectives": ["eta", "risk", "fuel"],
        },
    )
    from src.portwatch_os.decision.frontier import pareto

    problem.frontier = pareto(problem.options, problem.objectives)
    return problem


def keep(hours_to_choke=10.0):
    return option("keep_plan", "KEEP_PLAN", hours_to_choke=hours_to_choke, eta=5.0, certain=False, baseline=True)


class OutcomeModelTests(unittest.TestCase):
    def test_the_drain_fractions_are_the_missions_stated_outcomes(self):
        from src.portwatch_os.missions.biparjoy import OUTCOME as BIPARJOY
        from src.portwatch_os.missions.catalogue import OUTCOME as EVER_GIVEN

        for outcome, expected in ((EVER_GIVEN, EVER_GIVEN_DRAIN_FRACTION), (BIPARJOY, BIPARJOY_DRAIN_FRACTION)):
            blocked = parse_instant(outcome.blocked_from)
            reopened = parse_instant(outcome.reopened_at)
            cleared = parse_instant(outcome.backlog_cleared_bound.split(" ")[0])
            fraction = (cleared - reopened).total_seconds() / (reopened - blocked).total_seconds()
            self.assertAlmostEqual(fraction, expected, places=2)
        self.assertAlmostEqual(QUEUE_MODELS["RECORDED"]["drainFraction"],
                               (EVER_GIVEN_DRAIN_FRACTION + BIPARJOY_DRAIN_FRACTION) / 2, places=3)
        self.assertEqual(QUEUE_MODELS["NONE"]["drainFraction"], 0.0)

    def test_the_model_is_the_scorecards_model(self):
        """Same option, same window: the scorecard and the policy agree to the tenth of an hour."""
        from src.portwatch_os.missions.model import Outcome
        from src.portwatch_os.missions.scorecard import realised_delay_hours

        keep_option = keep(hours_to_choke=20.0)
        problem = problem_with([keep_option])
        blocked, reopened, cleared = NOW - timedelta(hours=6), NOW + timedelta(hours=40), NOW + timedelta(hours=70)
        outcome = Outcome(reopened_at=reopened.isoformat(), blocked_from=blocked.isoformat(),
                          backlog_cleared_on=cleared.isoformat()[:10], backlog_cleared_bound=cleared.isoformat(),
                          ships_waiting_peak=None, ships_waiting_source_id=None, summary="t", sources=[])
        via_scorecard = realised_delay_hours(keep_option, problem, outcome, clock=NOW)
        via_model = closure_delay_hours(keep_option, ClosureWindow(blocked, reopened, cleared), clock=NOW)
        self.assertEqual(via_scorecard["hours"], via_model["hours"])
        # Arrived 20 h in, 26 h into a 46 h closure: waits 20 h then queues 26/46 of the 30 h drain.
        self.assertAlmostEqual(via_model["hours"], 20.0 + 30.0 * (26.0 / 46.0), places=1)

    def test_arriving_after_the_backlog_costs_only_the_hold(self):
        slow = option("slow_steam", "SLOW_STEAM", hours_to_choke=80.0, hold=60.0, eta=60.0)
        window = ClosureWindow.with_drain(NOW - timedelta(hours=6), NOW + timedelta(hours=10), drain_fraction=0.5)
        self.assertEqual(closure_delay_hours(slow, window, clock=NOW)["hours"], 60.0)
        cape = option("reroute", "REROUTE", eta=90.0)
        self.assertEqual(closure_delay_hours(cape, window, clock=NOW)["hours"], 90.0)


class ScenarioTests(unittest.TestCase):
    def test_four_labelled_horizons_multiples_of_the_remaining_claim(self):
        problem = problem_with([keep()], claim_remaining=60.0, claim_from_hours_ago=12.0)
        scenarios = stress_scenarios(problem)
        self.assertEqual([s.label for s in scenarios], ["FIZZLE", "SHORT", "BASE", "LONG"])
        self.assertEqual([s.closure_from_now_hours for s in scenarios], [None, 30.0, 60.0, 120.0])
        fizzle, short, base, long_ = scenarios
        self.assertEqual(fizzle.window.closure_hours, 0.0)
        self.assertEqual(base.window.reopened_at, NOW + timedelta(hours=60))
        # The closure began when the claim did; the drain is the recorded fraction of its whole length.
        self.assertEqual(short.window.blocked_from, NOW - timedelta(hours=12))
        self.assertAlmostEqual(long_.window.drain_hours, QUEUE_MODELS["RECORDED"]["drainFraction"] * 132.0, places=1)
        for scenario in scenarios:
            self.assertNotIn("probability", scenario.to_dict())

    def test_no_claim_horizon_means_no_scenarios_and_no_robust_verdict(self):
        problem = problem_with([keep()])
        problem.evidence["event"].pop("claimLapsesAt")
        self.assertEqual(stress_scenarios(problem), [])
        assessment = assess(problem, expected_best="keep_plan")
        self.assertFalse(assessment.applicable)
        self.assertEqual(assessment.kind, KEEP_CURRENT_PLAN)


class GateTests(unittest.TestCase):
    def test_keep_when_the_plan_wins_every_horizon(self):
        # A hold to the claim horizon against a plan that arrives early in the closure.
        slow = option("slow_steam", "SLOW_STEAM", hours_to_choke=74.0, hold=64.0, eta=64.0, closes=10.0)
        problem = problem_with([keep(), slow], claim_remaining=72.0)
        assessment = assess(problem, expected_best="slow_steam")
        self.assertTrue(assessment.applicable)
        self.assertEqual(assessment.kind, KEEP_CURRENT_PLAN)
        self.assertEqual(assessment.option_id, "keep_plan")
        self.assertEqual(assessment.picks["EXPECTED_BEST"], "slow_steam")
        self.assertEqual(assessment.picks["LOWEST_WORST_CASE_REGRET"], "keep_plan")
        self.assertEqual(assessment.summary["keep_plan"]["wins"], 4)
        self.assertEqual(assessment.table["slow_steam"]["FIZZLE"]["regret"], 64.0)   # the hold was pure cost
        self.assertIn("wins 4/4 stress horizons", assessment.why)
        be = assessment.summary["slow_steam"]["breakEven"]
        self.assertTrue(be["available"])
        self.assertIn("current plan", be["statement"])

    def test_act_when_a_reversible_intervention_clears_every_blocking_check(self):
        # A short, certain detour against a plan that would sit in a long closure.
        cape = option("reroute", "REROUTE", eta=30.0, closes=4.0, weather=1.2)
        problem = problem_with([keep(), cape], claim_remaining=72.0, hours_to_risk=10.0)
        assessment = assess(problem, expected_best="reroute")
        self.assertEqual(assessment.kind, ACT)
        self.assertEqual(assessment.option_id, "reroute")
        blocking = {c.name: c.passed for c in assessment.checks if c.blocking}
        self.assertEqual(set(blocking), {"worst_case_regret", "scenario_wins", "queue_model_agreement", "claim_as_stated"})
        self.assertTrue(all(blocking.values()), blocking)
        self.assertEqual(assessment.table["reroute"]["FIZZLE"]["regret"], 30.0)
        self.assertEqual(assessment.table["reroute"]["BASE"]["regret"], 0.0)
        self.assertGreater(assessment.summary["keep_plan"]["worstCaseRegret"], 30.0)
        self.assertIn("Worst-case regret", assessment.why)
        be = assessment.summary["reroute"]["breakEven"]
        self.assertIsNotNone(be["winsFromHours"])
        self.assertIsNone(be["winsUntilHours"])          # open-ended: the longer the closure, the better

    def test_wait_when_the_intervention_is_justified_but_the_branch_point_allows_a_refresh_first(self):
        cape = option("reroute", "REROUTE", eta=30.0, closes=20.0, weather=1.2)
        problem = problem_with([keep(), cape], claim_remaining=72.0, hours_to_risk=10.0)
        assessment = assess(problem, expected_best="reroute")
        self.assertEqual(assessment.kind, WAIT_FOR_MORE_INFORMATION)
        self.assertEqual(assessment.option_id, "keep_plan")               # what to do now
        self.assertEqual(assessment.provisional_option_id, "reroute")      # what to do if the claim stands
        self.assertEqual(assessment.information["reevaluateInHours"], 6.0)
        self.assertEqual(assessment.information["branchPointInHours"], 20.0)
        self.assertIn("Re-evaluate in 6 h", assessment.statement)

    def test_wait_when_the_plan_is_kept_but_a_longer_closure_would_change_the_answer(self):
        # The Cape wins only the LONG horizon: not recommended, but worth a refresh.
        cape = option("reroute", "REROUTE", eta=100.0, closes=30.0)
        problem = problem_with([keep(), cape], claim_remaining=72.0, hours_to_risk=10.0)
        assessment = assess(problem, expected_best="keep_plan")
        self.assertEqual(assessment.kind, WAIT_FOR_MORE_INFORMATION)
        self.assertEqual(assessment.option_id, "keep_plan")
        self.assertIsNone(assessment.provisional_option_id)
        self.assertEqual(assessment.contender_id, "reroute")
        self.assertTrue(assessment.information["scenarioSensitive"])
        self.assertGreater(assessment.information["informationValueHoursUpperBound"], NOISE_TOLERANCE_HOURS)
        self.assertIn("beats the current plan only if the closure persists beyond", assessment.why)

    def test_keep_not_wait_when_the_branch_point_closes_before_the_next_refresh(self):
        cape = option("reroute", "REROUTE", eta=100.0, closes=3.0)
        problem = problem_with([keep(), cape], claim_remaining=72.0, hours_to_risk=10.0)
        assessment = assess(problem, expected_best="keep_plan")
        self.assertEqual(assessment.kind, KEEP_CURRENT_PLAN)
        self.assertEqual(assessment.contender_id, "reroute")

    def test_an_irreversible_move_needs_the_claim_as_stated_not_the_tail(self):
        # Wins LONG by a mile, loses BASE: minimax picks it, the gate refuses it.
        cape = option("reroute", "REROUTE", eta=75.0, closes=4.0)
        problem = problem_with([keep(), cape], claim_remaining=72.0, hours_to_risk=10.0)
        assessment = assess(problem, expected_best="keep_plan")
        table = assessment.table
        self.assertGreater(table["reroute"]["BASE"]["regret"], NOISE_TOLERANCE_HOURS)
        self.assertEqual(table["reroute"]["LONG"]["regret"], 0.0)
        if assessment.picks["LOWEST_WORST_CASE_REGRET"] == "reroute":
            failed = [c.name for c in assessment.failed_blocking]
            self.assertIn("claim_as_stated", failed)
            self.assertNotEqual(assessment.kind, ACT)
        self.assertNotEqual(assessment.option_id, "reroute")

    def test_a_slow_steam_hold_is_reversible_and_a_diversion_is_not_past_the_branch(self):
        problem = problem_with([keep(), option("slow_steam", "SLOW_STEAM", hours_to_choke=74.0, hold=64.0, eta=64.0, closes=10.0),
                                option("reroute", "REROUTE", eta=100.0, closes=9.0)])
        classes = {o.option_id: reversibility_of(o, problem)["class"] for o in problem.options}
        self.assertEqual(classes, {"keep_plan": REVERSIBLE_OPEN, "slow_steam": REVERSIBLE_HIGH,
                                   "reroute": REVERSIBLE_UNTIL_BRANCH})
        self.assertEqual(reversibility_of(problem.option("keep_plan"), problem)["closesInHours"], 10.0)

    def test_the_break_even_is_a_grid_of_closure_lengths_with_a_stated_span(self):
        cape = option("reroute", "REROUTE", eta=30.0, closes=4.0)
        problem = problem_with([keep(), cape], claim_remaining=72.0, hours_to_risk=10.0)
        be = break_even(cape, problem.baseline, problem)
        self.assertTrue(be["available"])
        self.assertEqual(be["gridSpanHours"], 216.0)
        self.assertEqual(be["gridStepHours"], 1.0)
        self.assertTrue(0 < be["winningShare"] <= 1.0)
        self.assertTrue(all("closureFromNowHours" in p for p in be["curve"]))

    def test_the_queue_model_disagreement_check_recomputes_without_a_queue(self):
        cape = option("reroute", "REROUTE", eta=30.0, closes=4.0)
        problem = problem_with([keep(), cape], claim_remaining=72.0, hours_to_risk=10.0)
        assessment = assess(problem, expected_best="reroute")
        check = next(c for c in assessment.checks if c.name == "queue_model_agreement")
        self.assertTrue(check.passed)
        self.assertIn("with no queue the margin is", check.detail)
        self.assertTrue(check.blocking)


# --------------------------------------------------------------------------
# through the engine and the world
# --------------------------------------------------------------------------


class EngineTests(unittest.TestCase):
    def _solve(self, policy):
        from tests.test_decision_engine import observed_world, red_sea_event
        from src.portwatch_os.world.build import seed_for
        from src.portwatch_os.world.graph import EVENT, key

        event = red_sea_event()
        engine = DecisionEngine(policy=policy)
        return engine.solve_vessel(observed_world(event=event), event_key=key(EVENT, event.event_id),
                                   seed=seed_for(event), vessel_id="PWD-001", actor=DecisionActor(SHIPPING_COMPANY),
                                   at=datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc))

    def test_the_active_policy_is_the_robust_one_and_the_incumbent_still_answers(self):
        self.assertEqual(set(ENGINE_POLICIES), {BALANCED_POLICY, ROBUST_POLICY})
        self.assertIn(ACTIVE_POLICY, ENGINE_POLICIES)
        robust = self._solve(ROBUST_POLICY).recommendation
        balanced = self._solve(BALANCED_POLICY).recommendation
        self.assertEqual(robust.policy, ROBUST_POLICY)
        self.assertEqual(balanced.policy, BALANCED_POLICY)
        self.assertIsNone(balanced.robustness)
        self.assertEqual(balanced.option_id, "slow_steam")                 # the incumbent, as it always answered
        self.assertEqual(robust.kind, KEEP_CURRENT_PLAN)
        self.assertEqual(robust.option_id, "keep_plan")
        self.assertEqual(robust.robustness["picks"]["EXPECTED_BEST"], "slow_steam")
        self.assertEqual(robust.ranking_basis["expectedBest"], "slow_steam")
        with self.assertRaises(DecisionError):
            DecisionEngine(policy="clever-v9")

    def test_the_robust_recommendation_carries_its_evidence(self):
        problem = self._solve(ROBUST_POLICY)
        rob = problem.recommendation.robustness
        self.assertTrue(rob["applicable"])
        self.assertEqual([s["label"] for s in rob["scenarios"]], ["FIZZLE", "SHORT", "BASE", "LONG"])
        self.assertIn("keep_plan", rob["table"])
        self.assertIn("slow_steam", rob["table"])
        self.assertEqual(rob["durationConfidence"]["label"], "LOW / UNCALIBRATED")
        self.assertEqual(rob["information"]["nextObservationHours"], 6.0)
        self.assertEqual(rob["queueModel"]["name"], "RECORDED")
        self.assertIn("Ever Given", rob["queueModel"]["basis"])
        self.assertEqual(problem.evidence["closureModel"]["riskKind"], "chokepoint")
        self.assertIsNotNone(problem.evidence["event"]["claimFrom"])
        self.assertIn("robustness_stated", [c["name"] for c in problem.recommendation.critic["checks"]])
        self.assertNotIn("robustness_stated", problem.recommendation.critic["failed"])

    def test_a_dominated_option_may_be_recommended_only_with_a_robust_reason(self):
        from src.portwatch_os.decision.critic import BLOCKING, DecisionCritic, WARNING

        problem = self._solve(ROBUST_POLICY)
        # slow_steam dominates reroute in expectation; force the frontier to say the baseline is dominated
        # and check the Critic's wording with and without the robust reason.
        problem.frontier.dominated["keep_plan"] = "slow_steam"
        verdict = DecisionCritic().review_recommendation(problem, "keep_plan")
        check = next(c for c in verdict.checks if c.name == "not_dominated")
        self.assertEqual(check.severity, WARNING)
        self.assertIn("lowest worst-case regret", check.detail)
        problem.recommendation.robustness = None
        verdict = DecisionCritic().review_recommendation(problem, "keep_plan")
        check = next(c for c in verdict.checks if c.name == "not_dominated")
        self.assertEqual(check.severity, BLOCKING)

    def test_a_recommendation_kind_must_be_one_of_three(self):
        with self.assertRaises(DecisionError):
            DecisionRecommendation(option_id="x", actor=SHIPPING_COMPANY, kind="PANIC")


class BenchmarkTests(unittest.TestCase):
    def test_both_portwatch_policies_come_from_one_build(self):
        engine = DecisionEngine(capacity=64, policy=ROBUST_POLICY)
        result = run_vessel_case(4, engine)
        self.assertIn(INCUMBENT, result.choices)
        self.assertIn(CANDIDATE, result.choices)
        self.assertEqual(result.choices[INCUMBENT].option_id, "slow_steam")   # the documented tuning-corpus pick
        self.assertIn(result.choices[CANDIDATE].kind, (ACT, KEEP_CURRENT_PLAN, WAIT_FOR_MORE_INFORMATION))
        self.assertTrue(result.choices[INCUMBENT].intervened)
        self.assertEqual(result.choices["current_plan"].intervened, False)

    def test_a_wait_is_scored_by_simulating_the_wait(self):
        from src.portwatch_os.decision.benchmark import _robust_pick
        from src.portwatch_os.decision.robust import RobustAssessment

        cape = option("reroute", "REROUTE", eta=30.0, closes=20.0, weather=1.2)
        problem = problem_with([keep(), cape], claim_remaining=72.0, hours_to_risk=10.0)
        assessment = assess(problem, expected_best="reroute")
        self.assertEqual(assessment.kind, WAIT_FOR_MORE_INFORMATION)
        problem.recommendation = DecisionRecommendation(
            option_id=assessment.option_id, actor=SHIPPING_COMPANY, kind=assessment.kind,
            provisional_option_id=assessment.provisional_option_id, robustness=assessment.to_dict(),
        )
        ended = {"reopenedAt": (NOW + timedelta(hours=3)).isoformat()}
        stood = {"reopenedAt": (NOW + timedelta(hours=50)).isoformat()}
        self.assertEqual(_robust_pick(problem, truth=ended)[0], "keep_plan")
        self.assertEqual(_robust_pick(problem, truth=stood)[0], "reroute")

    def test_the_corpora_are_disjoint_and_the_tuning_corpus_is_the_original(self):
        self.assertEqual(CORPORA["tuning"], (1, 40))
        ranges = sorted((first, first + count - 1) for first, count in CORPORA.values())
        for (a0, a1), (b0, b1) in zip(ranges, ranges[1:]):
            self.assertLess(a1, b0)
        self.assertEqual(POLICIES[-2:], (INCUMBENT, CANDIDATE))


class PromotionGateTests(unittest.TestCase):
    def test_the_engine_default_is_what_the_published_gate_says(self):
        """The gate document is the record; the code's default must match it."""
        from pathlib import Path

        gate = Path(__file__).resolve().parents[1] / "docs" / "DECISION_POLICY_GATE.md"
        text = gate.read_text(encoding="utf-8")
        self.assertIn("## Verdict:", text)
        published = "portwatch_robust" if "Active policy: `portwatch_robust`" in text else "portwatch_balanced"
        self.assertIn(f"Active policy: `{published}`", text)
        expected = ROBUST_POLICY if published == CANDIDATE else BALANCED_POLICY
        self.assertEqual(ACTIVE_POLICY, expected)
        if published == CANDIDATE:
            self.assertIn("## Verdict: APPROVED", text)
            self.assertIn("## test corpus — APPROVED", text)

    def _suite(self, corpus, *, robust, balanced, cases=100, seed_range=(1001, 1100)):
        def row(mean, p90, worst, violations, rate, unnecessary):
            return {"meanRegret": mean, "p90Regret": p90, "worstRegret": worst, "violations": violations,
                    "interventionRate": rate, "unnecessaryInterventionRate": unnecessary, "waitRate": 0.0}
        base = row(0.2, 0.0, 5.0, 0, 0.0, None)
        agg = {}
        for domain in ("VESSEL", "PORT", "CARGO"):
            r, b = (robust, balanced) if domain == "VESSEL" else (balanced, balanced)
            agg[domain] = {"cases": cases, "errors": 0, "interventionWasBest": 3,
                           "beneficialInterventionCapture": {"current_plan": 0.0, INCUMBENT: 1.0, CANDIDATE: 0.0},
                           "policies": {"current_plan": base, "greedy": base, "heuristic": base,
                                        INCUMBENT: row(*b), CANDIDATE: row(*r)}}
        return {"corpus": corpus, "seedRange": list(seed_range), "aggregate": agg}

    def test_a_materially_better_candidate_is_approved(self):
        suite = self._suite("validation", robust=(0.2, 0.0, 5.0, 0, 0.0, None), balanced=(5.7, 12.0, 68.0, 0, 0.3, 0.75))
        decision = evaluate_policy_promotion(suite)
        self.assertTrue(decision.passed, decision.summary())
        self.assertEqual(decision.verdict, "APPROVED")

    def test_more_violations_or_a_worse_tail_or_a_marginal_gain_is_rejected(self):
        worse_tail = self._suite("validation", robust=(0.2, 0.0, 80.0, 0, 0.0, None), balanced=(5.7, 12.0, 68.0, 0, 0.3, 0.75))
        self.assertIn("worst_case_not_worse", evaluate_policy_promotion(worse_tail).failed_checks)
        violations = self._suite("validation", robust=(0.2, 0.0, 5.0, 2, 0.0, None), balanced=(5.7, 12.0, 68.0, 0, 0.3, 0.75))
        self.assertIn("no_more_violations", evaluate_policy_promotion(violations).failed_checks)
        marginal = self._suite("validation", robust=(5.5, 11.9, 68.0, 0, 0.3, 0.75), balanced=(5.7, 12.0, 68.0, 0, 0.3, 0.75))
        failed = evaluate_policy_promotion(marginal).failed_checks
        self.assertIn("mean_regret_lower", failed)
        self.assertIn("p90_regret_lower", failed)
        trigger_happy = self._suite("validation", robust=(0.2, 0.0, 5.0, 0, 0.6, 0.5), balanced=(5.7, 12.0, 68.0, 0, 0.3, 0.75))
        self.assertIn("intervention_rate_reasonable", evaluate_policy_promotion(trigger_happy).failed_checks)

    def test_leakage_and_small_corpora_are_refused(self):
        leaked = self._suite("validation", robust=(0.2, 0.0, 5.0, 0, 0.0, None), balanced=(5.7, 12.0, 68.0, 0, 0.3, 0.75),
                             seed_range=(20, 119))
        self.assertIn("held_out", evaluate_policy_promotion(leaked).failed_checks)
        small = self._suite("validation", robust=(0.2, 0.0, 5.0, 0, 0.0, None), balanced=(5.7, 12.0, 68.0, 0, 0.3, 0.75),
                            cases=40)
        self.assertIn("sufficient_cases", evaluate_policy_promotion(small).failed_checks)

    def test_the_final_verdict_needs_validation_and_test_both_approved(self):
        good = evaluate_policy_promotion(self._suite("validation", robust=(0.2, 0.0, 5.0, 0, 0.0, None),
                                                     balanced=(5.7, 12.0, 68.0, 0, 0.3, 0.75)))
        test_good = evaluate_policy_promotion(self._suite("test", robust=(0.2, 0.0, 5.0, 0, 0.0, None),
                                                          balanced=(5.7, 12.0, 68.0, 0, 0.3, 0.75), seed_range=(5001, 5200)))
        test_bad = evaluate_policy_promotion(self._suite("test", robust=(6.0, 13.0, 90.0, 0, 0.3, 0.8),
                                                         balanced=(5.7, 12.0, 68.0, 0, 0.3, 0.75), seed_range=(5001, 5200)))
        self.assertEqual(final_verdict([good, test_good])["verdict"], "APPROVED")
        self.assertEqual(final_verdict([good, test_good])["activePolicy"], CANDIDATE)
        self.assertEqual(final_verdict([good, test_bad])["verdict"], "REJECTED")
        self.assertEqual(final_verdict([good, test_bad])["activePolicy"], INCUMBENT)
        self.assertEqual(final_verdict([good])["verdict"], "REJECTED")           # no test corpus: not promotable


if __name__ == "__main__":
    unittest.main()
