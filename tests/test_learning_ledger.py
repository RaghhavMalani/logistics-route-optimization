"""The ledger and the learning loop.

The properties under test are the ones that make the rest of the product
believable: that a claim cannot be rewritten after the answer is known, that a
weight cannot be fitted on the future, and that "why were we wrong" is an
arithmetic identity rather than a plausible bar chart.
"""

from __future__ import annotations

import random
import unittest

from src.portwatch_os.ledger.schema import (
    ACTION_TAKEN,
    BINARY,
    CONTINUOUS,
    DOMAIN_EVENT,
    DOMAIN_PORT_FORECAST,
    EVALUATING,
    OPEN,
    RESOLVED,
    DecisionRecord,
    EventOutcomeRecord,
    PolicyRecord,
    PredictionContext,
    PredictionRecord,
    can_transition,
    horizon_bucket,
    utc_now,
)
from src.portwatch_os.ledger.store import LedgerError, SqliteLedgerStore, shift_iso
from src.portwatch_os.learning.attribution import (
    attribute,
    rank_misses,
    verify_decomposition,
)
from src.portwatch_os.learning.outcome_agent import OutcomeAgent, score_prediction
from src.portwatch_os.learning.reliability import (
    LeakageError,
    MIN_SAMPLES_TO_APPLY,
    ReliabilityTable,
    accumulate,
    fit_reliability,
    shrink,
)
from src.portwatch_os.learning.scoring import (
    binary_report,
    brier_score,
    calibration,
    confusion,
    error_report,
    log_loss,
    pinball_loss,
    Residual,
    skill_score,
)

BASE = "2026-09-01T00:00:00+00:00"


def prediction(index, *, predicted=50.0, features=None, contributions=None, hours=24):
    valid = shift_iso(BASE, index * 6)
    return PredictionRecord(
        prediction_id=PredictionRecord.make_id(
            DOMAIN_PORT_FORECAST, "congestion_index", "INMAA", valid, "ens"
        ),
        domain=DOMAIN_PORT_FORECAST,
        kind=CONTINUOUS,
        target="congestion_index",
        subject="INMAA",
        model="adaptive_ensemble",
        model_version="1.0",
        issued_at=shift_iso(valid, -hours),
        valid_at=valid,
        context=PredictionContext(port_code="INMAA", horizon_hours=float(hours)),
        predicted_value=predicted,
        predicted_low=predicted - 4,
        predicted_high=predicted + 4,
        interval_nominal=0.8,
        features=features or {},
        contributions=contributions or {},
    )


class StoreIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.store = SqliteLedgerStore(":memory:")

    def test_a_resolved_claim_cannot_be_rewritten(self):
        """The single rule that makes the ledger evidence rather than a log."""
        record = prediction(0)
        self.store.record_prediction(record)
        self.store.resolve_prediction(record.prediction_id, 52.0, utc_now(), "panel")
        with self.assertRaises(LedgerError):
            self.store.record_prediction(record)

    def test_the_same_claim_written_twice_updates_rather_than_duplicates(self):
        record = prediction(0)
        self.store.record_prediction(record)
        self.store.record_prediction(record)
        self.assertEqual(len(self.store.predictions()), 1)

    def test_ids_are_content_derived_so_a_rerun_is_idempotent(self):
        self.assertEqual(prediction(0).prediction_id, prediction(0).prediction_id)
        self.assertNotEqual(prediction(0).prediction_id, prediction(1).prediction_id)

    def test_resolving_records_the_lead_time(self):
        record = prediction(0)
        self.store.record_prediction(record)
        settled = self.store.resolve_prediction(
            record.prediction_id, 52.0, record.valid_at, "panel",
            score_prediction(record, 52.0),
        )
        self.assertEqual(settled.status, RESOLVED)
        self.assertAlmostEqual(settled.lead_time_hours, 24.0, places=3)

    def test_an_open_claim_about_the_future_is_not_due(self):
        record = prediction(40)
        self.store.record_prediction(record)
        self.assertEqual(self.store.due_predictions(now=BASE), [])

    def test_every_write_leaves_an_audit_entry(self):
        record = prediction(0)
        self.store.record_prediction(record)
        self.store.resolve_prediction(record.prediction_id, 52.0, utc_now(), "panel")
        trail = self.store.audit_trail("prediction", record.prediction_id)
        self.assertEqual([e["action"] for e in trail], ["created", "resolved"])

    def test_a_decision_records_whether_it_was_taken(self):
        decision = DecisionRecord(
            decision_id=DecisionRecord.make_id("advisory", "PWD-001", BASE, "S. Iyer"),
            kind="advisory:arrival_window",
            subject="PWD-001",
            issued_at=BASE,
            issuer="S. Iyer",
            recommendation={"shiftHours": 4},
            reason="queue",
            expected_impact={"waitHoursSaved": 3.0},
        )
        self.store.record_decision(decision)
        self.store.resolve_decision(
            decision.decision_id, ACTION_TAKEN, {"waitHoursSaved": 2.6}, utc_now(),
            operational_reward=2.6,
        )
        settled = self.store.get_decision(decision.decision_id)
        self.assertEqual(settled.action_state, ACTION_TAKEN)
        self.assertEqual(settled.operational_reward, 2.6)

    def test_horizon_buckets_are_coarse_and_ordered(self):
        self.assertEqual(horizon_bucket(3), "0-6h")
        self.assertEqual(horizon_bucket(24), "12-24h")
        self.assertEqual(horizon_bucket(400), "7d+")


class PolicyPromotionTests(unittest.TestCase):
    def setUp(self):
        self.store = SqliteLedgerStore(":memory:")
        self.policy = PolicyRecord(
            policy_id="bandit", name="Bandit", family="learned", version="0.1.0",
            created_at=utc_now(), updated_at=utc_now(),
        )
        self.store.upsert_policy(self.policy)

    def test_a_candidate_cannot_jump_straight_to_approved(self):
        self.assertFalse(can_transition("candidate", "approved"))
        with self.assertRaises(LedgerError):
            self.store.transition_policy("bandit", "approved", actor="A. Deshmukh")

    def test_approval_requires_a_recorded_evaluation(self):
        self.store.transition_policy("bandit", EVALUATING)
        with self.assertRaises(LedgerError):
            self.store.transition_policy("bandit", "approved", actor="A. Deshmukh")

    def test_approval_requires_a_named_human(self):
        self.store.transition_policy(
            "bandit", EVALUATING, evaluation={"meanReward": 1.0},
            safety_checks={"beats_baseline": True},
        )
        with self.assertRaises(LedgerError):
            self.store.transition_policy("bandit", "approved")

    def test_a_failed_safety_check_blocks_approval(self):
        self.store.transition_policy(
            "bandit", EVALUATING, evaluation={"meanReward": 1.0},
            safety_checks={"beats_baseline": True, "no_violations": False},
        )
        with self.assertRaises(LedgerError):
            self.store.transition_policy("bandit", "approved", actor="A. Deshmukh")

    def test_a_clean_evaluation_with_an_approver_is_promoted(self):
        self.store.transition_policy(
            "bandit", EVALUATING, evaluation={"meanReward": 1.0},
            safety_checks={"beats_baseline": True, "no_violations": True},
        )
        promoted = self.store.transition_policy(
            "bandit", "approved", actor="A. Deshmukh"
        )
        self.assertEqual(promoted.state, "approved")
        self.assertEqual(promoted.approved_by, "A. Deshmukh")

    def test_a_rejected_policy_is_terminal(self):
        self.store.transition_policy("bandit", "rejected", reason="worse than greedy")
        with self.assertRaises(LedgerError):
            self.store.transition_policy("bandit", EVALUATING)


class ScoringTests(unittest.TestCase):
    def test_brier_and_log_loss_reward_honesty(self):
        """A confident miss costs more than a hedged one."""
        self.assertGreater(brier_score(0.95, False), brier_score(0.55, False))
        self.assertGreater(log_loss(0.95, False), log_loss(0.55, False))

    def test_log_loss_is_finite_even_on_a_certain_miss(self):
        self.assertLess(log_loss(0.0, True), 1e9)
        self.assertGreater(log_loss(0.0, True), 0)

    def test_calibration_finds_a_systematic_over_forecast(self):
        pairs = [(0.9, i % 5 == 0) for i in range(50)]
        report = calibration(pairs)
        self.assertGreater(report.over_forecast, 0.5)
        self.assertGreater(report.expected_calibration_error, 0.5)

    def test_a_perfectly_calibrated_forecaster_scores_near_zero_error(self):
        pairs = [(0.5, i % 2 == 0) for i in range(100)]
        self.assertLess(calibration(pairs).expected_calibration_error, 0.05)

    def test_confusion_counts_at_an_explicit_threshold(self):
        pairs = [(0.8, True), (0.8, False), (0.2, False), (0.2, True)]
        counts = confusion(pairs, threshold=0.5)
        self.assertEqual(counts.true_positive, 1)
        self.assertEqual(counts.false_positive, 1)
        self.assertEqual(counts.false_negative, 1)
        self.assertEqual(counts.true_negative, 1)

    def test_brier_skill_is_negative_when_worse_than_the_base_rate(self):
        pairs = [(0.9, False) for _ in range(20)] + [(0.1, True) for _ in range(20)]
        report = binary_report(pairs)
        self.assertLess(report.brier_skill, 0)

    def test_error_report_separates_bias_from_scatter(self):
        biased = error_report([Residual(predicted=10, observed=13) for _ in range(10)])
        scattered = error_report(
            [Residual(predicted=10, observed=10 + (3 if i % 2 else -3)) for i in range(10)]
        )
        self.assertAlmostEqual(biased.bias, 3.0)
        self.assertAlmostEqual(scattered.bias, 0.0)
        self.assertAlmostEqual(biased.mean_absolute_error, scattered.mean_absolute_error)

    def test_interval_coverage_is_measured_against_the_nominal(self):
        residuals = [
            Residual(predicted=10, observed=10.5, low=8, high=12, nominal=0.8)
            for _ in range(9)
        ] + [Residual(predicted=10, observed=40, low=8, high=12, nominal=0.8)]
        report = error_report(residuals)
        self.assertAlmostEqual(report.interval_coverage, 0.9)
        self.assertAlmostEqual(report.coverage_error, 0.1, places=6)

    def test_pinball_loss_is_asymmetric(self):
        self.assertNotEqual(pinball_loss(10, 12, 0.1), pinball_loss(10, 8, 0.1))

    def test_skill_score_is_none_against_a_perfect_reference(self):
        self.assertIsNone(skill_score(1.0, 0.0))


class ReliabilityTests(unittest.TestCase):
    def _history(self, count=60, bias=6.0):
        rng = random.Random(11)
        rows = []
        truths = []
        for index in range(count):
            truth = 50 + 8 * rng.random()
            features = {
                "weather_expert": truth + bias + rng.random(),
                "arrival_dynamics": truth + 0.3 * rng.random(),
                "__persistence__": truth + 3,
            }
            blended = 0.5 * features["weather_expert"] + 0.5 * features["arrival_dynamics"]
            record = prediction(
                index, predicted=blended, features=features,
                contributions={"weather_expert": 0.5, "arrival_dynamics": 0.5},
            )
            record.status = RESOLVED
            record.observed_value = truth
            record.observed_at = shift_iso(record.valid_at, 1)
            rows.append(record)
            truths.append(truth)
        return rows

    def test_a_consistently_biased_contributor_is_downweighted(self):
        weights = {
            (r.contributor, r.context_key): r.weight
            for r in fit_reliability(self._history())
        }
        self.assertLess(
            weights[("weather_expert", "global")],
            weights[("arrival_dynamics", "global")],
        )

    def test_fitting_on_an_observation_after_the_barrier_is_refused(self):
        """Leakage raises rather than skipping, so a bug cannot hide."""
        rows = self._history(count=5)
        with self.assertRaises(LeakageError):
            accumulate(rows, as_of=BASE)

    def test_a_weight_shrinks_toward_neutral_with_little_evidence(self):
        self.assertLess(abs(shrink(2.0, 2) - 1.0), abs(shrink(2.0, 500) - 1.0))

    def test_weights_stay_inside_their_clamp(self):
        for record in fit_reliability(self._history(count=200, bias=40.0)):
            self.assertGreaterEqual(record.weight, 0.35)
            self.assertLessEqual(record.weight, 1.60)

    def test_a_weight_moves_gradually_rather_than_snapping(self):
        first = fit_reliability(self._history())
        second = fit_reliability(self._history(bias=0.1), previous=first)
        for record in second:
            if record.previous_weight is None:
                continue
            self.assertLessEqual(abs(record.weight - record.previous_weight), 0.1201)

    def test_a_thin_context_is_reported_but_not_applied(self):
        table = ReliabilityTable.from_records(fit_reliability(self._history(count=3)))
        weight, source = table.weight_for(
            "weather_expert", PredictionContext(port_code="INMAA", horizon_hours=24)
        )
        self.assertEqual(weight, 1.0)
        self.assertIsNone(source)

    def test_the_applied_weight_names_the_context_it_came_from(self):
        table = ReliabilityTable.from_records(fit_reliability(self._history()))
        weight, source = table.weight_for(
            "weather_expert", PredictionContext(port_code="INMAA", horizon_hours=24)
        )
        self.assertIsNotNone(source)
        self.assertGreaterEqual(source.sample_count, MIN_SAMPLES_TO_APPLY)

    def test_applying_weights_produces_a_normalised_blend(self):
        table = ReliabilityTable.from_records(fit_reliability(self._history()))
        _, normalised = table.apply(
            {"weather_expert": 56.0, "arrival_dynamics": 50.4},
            PredictionContext(port_code="INMAA", horizon_hours=24),
        )
        self.assertAlmostEqual(sum(normalised.values()), 1.0)
        self.assertLess(normalised["weather_expert"], normalised["arrival_dynamics"])


class AttributionTests(unittest.TestCase):
    def _resolved(self, observed=52.0):
        features = {"weather_expert": 58.0, "arrival_dynamics": 51.0}
        contributions = {"weather_expert": 0.5, "arrival_dynamics": 0.5}
        record = prediction(
            0, predicted=54.5, features=features, contributions=contributions
        )
        record.status = RESOLVED
        record.observed_value = observed
        record.observed_at = shift_iso(record.valid_at, 1)
        return record

    def test_the_decomposition_closes_exactly(self):
        """weight x residual sums to the error. Arithmetic, not estimate."""
        decomposition = attribute(self._resolved())
        self.assertTrue(decomposition.available)
        self.assertTrue(verify_decomposition(decomposition))

    def test_the_worst_contributor_is_named(self):
        decomposition = attribute(self._resolved())
        self.assertEqual(decomposition.dominant, "weather_expert")

    def test_shares_are_bounded_and_sum_to_one(self):
        decomposition = attribute(self._resolved())
        total = sum(s.share for s in decomposition.shares) + 0.0
        self.assertLessEqual(total, 1.0001)
        for share in decomposition.shares:
            self.assertGreaterEqual(share.share, 0.0)

    def test_no_signals_means_no_attribution_rather_than_zeros(self):
        record = prediction(0)
        record.status = RESOLVED
        record.observed_value = 52.0
        decomposition = attribute(record)
        self.assertFalse(decomposition.available)
        self.assertIn("cannot be decomposed", decomposition.reason)
        self.assertEqual(decomposition.shares, [])

    def test_an_unresolved_claim_has_nothing_to_attribute(self):
        self.assertFalse(attribute(prediction(0)).available)

    def test_weights_that_do_not_sum_to_one_leave_a_reported_residual(self):
        record = self._resolved()
        record.contributions = {"weather_expert": 0.3, "arrival_dynamics": 0.3}
        decomposition = attribute(record)
        self.assertTrue(verify_decomposition(decomposition))
        self.assertGreater(abs(decomposition.residual), 1e-6)

    def test_binary_misses_are_ranked_by_brier_not_by_raw_error(self):
        confident = PredictionRecord(
            prediction_id="a", domain=DOMAIN_EVENT, kind=BINARY, target="closure",
            subject="SUEZ", model="global_eye", model_version="1",
            issued_at=BASE, valid_at=BASE, context=PredictionContext(),
            predicted_value=0.95, status=RESOLVED, observed_value=0.0, brier=0.9025,
        )
        hedged = PredictionRecord(
            prediction_id="b", domain=DOMAIN_EVENT, kind=BINARY, target="closure",
            subject="HORMUZ", model="global_eye", model_version="1",
            issued_at=BASE, valid_at=BASE, context=PredictionContext(),
            predicted_value=0.55, status=RESOLVED, observed_value=0.0, brier=0.3025,
        )
        ranked = rank_misses([hedged, confident], limit=2)
        self.assertEqual(ranked[0].subject, "SUEZ")


class OutcomeAgentTests(unittest.TestCase):
    def setUp(self):
        self.store = SqliteLedgerStore(":memory:")
        self.truths = {}
        for index in range(40):
            record = prediction(index, predicted=50.0 + index % 5)
            self.store.record_prediction(record)
            self.truths[record.prediction_id] = 51.0 + index % 5

    def _observer(self, record):
        value = self.truths.get(record.prediction_id)
        return None if value is None else (value, shift_iso(record.valid_at, 1), "panel")

    def test_the_pass_resolves_scores_and_recalibrates(self):
        agent = OutcomeAgent(self.store, observer=self._observer)
        run = agent.run(now=shift_iso(BASE, 500))
        self.assertEqual(run.resolved_predictions, 40)
        self.assertEqual(run.pending_predictions, 0)
        self.assertIsNotNone(run.overall.continuous)
        self.assertAlmostEqual(run.overall.continuous.bias, 1.0, places=6)

    def test_a_claim_about_the_future_stays_open(self):
        # An hour before the earliest claim's instant. At BASE itself the first
        # claim is due, which is correct: a claim about now is scorable now.
        agent = OutcomeAgent(self.store, observer=self._observer)
        run = agent.run(now=shift_iso(BASE, -1))
        self.assertEqual(run.resolved_predictions, 0)
        self.assertGreater(run.pending_predictions, 0)
        self.assertTrue(any("still open" in note for note in run.notes))

    def test_an_empty_ledger_reports_unavailable_rather_than_perfect(self):
        agent = OutcomeAgent(SqliteLedgerStore(":memory:"))
        run = agent.run()
        self.assertTrue(any("no resolved claims" in note for note in run.notes))
        self.assertIsNone(run.overall.continuous)

    def test_event_calibration_is_unavailable_until_a_horizon_elapses(self):
        agent = OutcomeAgent(self.store)
        self.assertFalse(agent.score_events()["available"])

    def test_an_event_claim_past_its_horizon_resolves_as_a_non_event(self):
        """An unconfirmed claim past its horizon is a measurement, not a gap."""
        claim = EventOutcomeRecord(
            outcome_id="evo-1", event_id="GE-1", category="chokepoint_disruption",
            region="Red Sea", claim="closure", horizon_hours=72.0,
            predicted_probability=0.8, confidence=0.9, source_count=3,
            issued_at=BASE, resolve_by=shift_iso(BASE, 72),
        )
        self.store.record_event_outcome(claim)
        agent = OutcomeAgent(self.store, event_observer=lambda _: None)
        resolved, pending = agent.resolve_events(now=shift_iso(BASE, 100))
        self.assertEqual((resolved, pending), (1, 0))
        settled = self.store.get_event_outcome("evo-1")
        self.assertFalse(settled.occurred)
        self.assertTrue(settled.false_alarm)

    def test_a_hedged_claim_that_did_not_happen_is_not_a_false_alarm(self):
        claim = EventOutcomeRecord(
            outcome_id="evo-2", event_id="GE-2", category="strike",
            region=None, claim="throughput loss", horizon_hours=24.0,
            predicted_probability=0.3, confidence=0.5, source_count=1,
            issued_at=BASE, resolve_by=shift_iso(BASE, 24),
        )
        self.store.record_event_outcome(claim)
        agent = OutcomeAgent(self.store, event_observer=lambda _: None)
        agent.resolve_events(now=shift_iso(BASE, 48))
        self.assertFalse(self.store.get_event_outcome("evo-2").false_alarm)

    def test_decision_take_up_is_reported_alongside_reward(self):
        decision = DecisionRecord(
            decision_id="dec-1", kind="advisory", subject="PWD-001",
            issued_at=BASE, issuer="S. Iyer", recommendation={}, reason="queue",
        )
        self.store.record_decision(decision)
        self.store.resolve_decision("dec-1", "not_taken", {}, utc_now())
        scored = OutcomeAgent(self.store).score_decisions()
        self.assertTrue(scored["available"])
        self.assertEqual(scored["takeUpRate"], 0.0)


class ResolutionIsFinalTests(unittest.TestCase):
    """A resolved row is evidence, and evidence does not get a second draft.

    The insert paths already refuse to rewrite a resolved record. The resolve
    paths did not check at all, so calling one twice quietly replaced the
    observed value, the calibration metrics and the audit trail -- which is
    precisely the retroactive edit the ledger exists to make impossible.
    """

    def setUp(self):
        self.store = SqliteLedgerStore(":memory:")

    def test_a_prediction_cannot_be_resolved_twice(self):
        record = PredictionRecord(
            prediction_id="p-1", domain=DOMAIN_PORT_FORECAST, kind=CONTINUOUS,
            target="congestion_index", subject="INMAA", model="ens",
            model_version="1", issued_at=BASE, valid_at=BASE,
            context=PredictionContext(), predicted_value=0.4,
        )
        self.store.record_prediction(record)
        self.store.resolve_prediction("p-1", 0.5, shift_iso(BASE, 6), "observed")
        with self.assertRaises(LedgerError):
            self.store.resolve_prediction("p-1", 0.9, shift_iso(BASE, 12), "revised")
        self.assertEqual(self.store.get_prediction("p-1").observed_value, 0.5)

    def test_an_event_outcome_cannot_be_resolved_twice(self):
        claim = EventOutcomeRecord(
            outcome_id="evo-1", event_id="E1", category="closure", region="SUEZ",
            claim="chokepoint_closure_within_24h", horizon_hours=24.0,
            predicted_probability=0.8, confidence=0.7, source_count=3,
            issued_at=BASE,
        )
        self.store.record_event_outcome(claim)
        self.store.resolve_event_outcome("evo-1", True, shift_iso(BASE, 24), "observed")
        with self.assertRaises(LedgerError):
            self.store.resolve_event_outcome(
                "evo-1", False, shift_iso(BASE, 30), "revised"
            )
        self.assertTrue(self.store.get_event_outcome("evo-1").occurred)

    def test_a_decision_cannot_be_resolved_twice(self):
        self.store.record_decision(DecisionRecord(
            decision_id="dec-1", kind="advisory", subject="PWD-001",
            issued_at=BASE, issuer="S. Iyer", recommendation={}, reason="queue",
        ))
        self.store.resolve_decision("dec-1", ACTION_TAKEN, {}, utc_now())
        with self.assertRaises(LedgerError):
            self.store.resolve_decision("dec-1", "not_taken", {}, utc_now())
        self.assertEqual(self.store.get_decision("dec-1").action_state, ACTION_TAKEN)


if __name__ == "__main__":
    unittest.main()
