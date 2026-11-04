from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.portwatch_os.learning.weather_feedback import WeatherFeedback, WeatherObservation, consumed_value
from src.portwatch_os.ledger.schema import PredictionContext, PredictionRecord, _stable_id

UTC = timezone.utc
T0 = datetime(2025, 6, 1, 10, tzinfo=UTC)


class WeatherFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = SqliteLedgerStore(Path(self.tmp.name) / "ledger.db")
        self.feedback = WeatherFeedback(self.ledger)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def snapshot(self, issued=T0, horizon=5, value=10.0, provider="test-weather"):
        day = issued.replace(hour=0) + timedelta(days=horizon)
        frame = pd.DataFrame([{"port_id": "JNPT", "date": pd.Timestamp(day).tz_localize(None), "wind_speed": value}])
        return self.feedback.record_frame(frame, issued_at=issued, provider=provider, source_state="LIVE", now=issued)

    def observation(self, issued=T0, value=15.0, kind="station"):
        valid = (issued.replace(hour=0) + timedelta(days=6)).isoformat()
        available = (issued + timedelta(days=7)).isoformat()
        return WeatherObservation("INNSA", "wind_speed", valid, available, value, "JNPA met station", kind, "kn")

    def test_refresh_preserves_issue_snapshot_and_is_idempotent(self):
        self.snapshot()
        self.snapshot(value=999)
        records = self.ledger.predictions(domain="weather")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].predicted_value, 10)
        self.assertEqual(records[0].context.extra["horizonDays"], 5)
        self.assertEqual(records[0].provenance["issueTimeBasis"], "response_retrieved_at")

    def test_different_issue_times_preserve_multiple_runs(self):
        self.snapshot()
        self.snapshot(issued=T0+timedelta(hours=1))
        self.assertEqual(len(self.ledger.predictions(domain="weather")), 2)

    def test_forecast_api_backfill_cannot_resolve_a_claim(self):
        self.snapshot()
        with self.assertRaises(ValueError):
            self.feedback.observe(self.observation(kind="forecast_api_backfill"), now=T0+timedelta(days=8))

    def test_future_or_unfinished_outcomes_are_refused(self):
        self.snapshot()
        with self.assertRaises(ValueError):
            self.feedback.observe(self.observation(), now=T0+timedelta(days=2))

    def test_units_and_aggregation_must_match(self):
        self.snapshot()
        o = self.observation()
        with self.assertRaises(ValueError):
            self.feedback.observe(WeatherObservation(o.port_code, o.variable, o.valid_at, o.available_at, o.value, o.source, o.kind, "m/s"), now=T0+timedelta(days=8))

    def test_resolves_and_scores_matching_target_only(self):
        self.snapshot()
        self.snapshot(horizon=6)
        self.assertEqual(self.feedback.observe(self.observation(), now=T0+timedelta(days=8)), 1)
        row = self.ledger.predictions(domain="weather", status="resolved")[0]
        self.assertEqual(row.error, 5)
        self.assertEqual(row.absolute_error, 5)
        self.assertEqual(self.feedback.observe(self.observation(value=100), now=T0+timedelta(days=8)), 0)
        self.assertEqual(self.ledger.get_prediction(row.prediction_id).observed_value, 15)

    def test_replay_hides_outcomes_not_yet_available(self):
        self.snapshot()
        self.feedback.observe(self.observation(), now=T0+timedelta(days=8))
        report = self.feedback.report(now=T0+timedelta(days=6))
        self.assertEqual(report["resolved"], 0)
        self.assertIsNone(report["forecasts"][0]["observed"])

    def test_public_scores_withhold_private_providers_and_station_outcomes(self):
        self.snapshot(provider="private-weather")
        self.snapshot(provider="Open-Meteo surface")
        self.feedback.observe(self.observation(kind="station"), now=T0+timedelta(days=8))
        issue = T0+timedelta(days=1)
        self.snapshot(issued=issue, provider="Open-Meteo surface")
        observation = self.observation(issued=issue, kind="reanalysis")
        self.feedback.observe(WeatherObservation(observation.port_code, observation.variable, observation.valid_at,
            observation.available_at, observation.value, "Open-Meteo ERA5 archive", "reanalysis", "kn"), now=issue+timedelta(days=8))
        report = self.feedback.report(now=issue+timedelta(days=9), public_only=True, limit=0)
        self.assertEqual(report["total"], 2)
        self.assertEqual(report["resolved"], 1)
        self.assertEqual(report["pending"], 1)
        self.assertEqual(report["scores"][0]["samples"], 1)
        self.assertEqual(report["scores"][0]["provider"], "Open-Meteo surface")
        self.assertEqual(self.feedback.report(now=issue+timedelta(days=9))["resolved"], 3)

    def test_stale_cache_cannot_create_retrospective_predictions(self):
        frame = pd.DataFrame([{"port_id": "JNPT", "date": "2025-06-06", "wind_speed": 10.0}])
        self.feedback.record_frame(frame, issued_at=T0, provider="test-weather", source_state="CACHED_LIVE", now=T0+timedelta(days=15))
        self.assertEqual(len(self.ledger.predictions(domain="weather")), 0)

    def build_history(self):
        for day in range(80):
            issue = T0+timedelta(days=day)
            self.snapshot(issued=issue)
            self.feedback.observe(self.observation(issued=issue), now=issue+timedelta(days=8))

    def test_learns_bias_only_after_chronological_validation(self):
        self.build_history()
        issue = T0+timedelta(days=90)
        correction = self.feedback.correction("INNSA", "wind_speed", "test-weather", 5, issue)
        self.assertEqual(correction["status"], "VALIDATED")
        self.assertEqual(correction["bias"], 5)
        self.assertEqual(correction["partitions"]["calibration"], 13)
        self.assertEqual(correction["partitions"]["evaluation"], 20)
        self.assertGreater(correction["partitions"]["purged"], 0)
        consumed = self.snapshot(issued=issue)
        self.assertEqual(consumed.iloc[0]["wind_speed"], 10)
        latest = max(self.ledger.predictions(domain="weather"), key=lambda row: row.issued_at)
        self.assertEqual(latest.predicted_value, 10)
        self.assertEqual(latest.context.extra["correctedValue"], 10)
        shadow = latest.context.extra["shadowCorrection"]
        self.assertEqual(shadow["candidateValue"], 15)
        self.assertEqual(shadow["bias"], 5)
        self.assertTrue(shadow["candidateEligible"])
        self.assertFalse(shadow["decisionEligible"])
        self.assertEqual(shadow["mode"], "SHADOW_ONLY")
        self.assertEqual(shadow["adoptionStatus"], "NOT_ADOPTED")
        self.assertEqual(shadow["modelId"], correction["modelId"])
        self.assertFalse(latest.context.extra["correction"]["decisionEligible"])
        self.assertEqual(latest.context.extra["correction"]["bias"], 0)
        self.assertIsNone(latest.context.extra["correction"]["modelId"])
        self.assertIsNone(latest.context.extra["correctedLow"])
        self.assertIsNone(latest.context.extra["correctedHigh"])

    def test_legacy_replay_flags_do_not_authorize_new_consumption_or_rewrite_evidence(self):
        from src.portwatch_os.intelligence.arrivals import ArrivalWorkflow
        target = T0.replace(hour=0) + timedelta(days=5)
        valid_at = (target + timedelta(days=1)).isoformat()
        correction = {"status": "VALIDATED", "decisionEligible": True, "bias": 5,
                      "modelId": "legacy-candidate", "reason": "Historical replay passed"}
        original = PredictionRecord(
            prediction_id=_stable_id("wx", "INNSA", "wind_speed", "test-weather", T0.isoformat(), valid_at),
            domain="weather", kind="continuous", target="wind_speed", subject="INNSA", model="test-weather",
            model_version="weather-residual-v3", issued_at=T0.isoformat(), valid_at=valid_at, predicted_value=10,
            context=PredictionContext(port_code="INNSA", extra={"unit": "kn", "horizonDays": 5,
                "targetDate": target.date().isoformat(), "aggregation": "daily", "correctedValue": 15,
                "correctedLow": 12, "correctedHigh": 18, "correction": correction}))
        with patch("src.portwatch_os.ledger.store.utc_now", return_value=T0.isoformat()):
            self.ledger.record_prediction(original)
        before = self.ledger.get_prediction(original.prediction_id).to_row()
        self.assertEqual(self.snapshot(value=999).iloc[0]["wind_speed"], 10)
        self.assertEqual(self.ledger.get_prediction(original.prediction_id).to_row(), before)
        evidence, features = ArrivalWorkflow(self.ledger).signals("419000168", target, now=T0+timedelta(seconds=2))
        self.assertEqual(features["wind_speed"], 10)
        self.assertEqual(evidence["weather"][0]["consumed"], 10)
        self.assertFalse(evidence["weather"][0]["correctionConsumed"])
        self.assertEqual(evidence["weather"][0]["adoptionStatus"], "NOT_ADOPTED")
        self.assertEqual(self.ledger.get_prediction(original.prediction_id).to_row(), before)

    def test_consumption_guard_does_not_accept_unaudited_adoption_flags(self):
        correction = {"status": "VALIDATED", "decisionEligible": True, "adoptionStatus": "ADOPTED", "bias": 5}
        self.assertEqual(consumed_value(10, correction), 10)
        for invalid in (float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                consumed_value(invalid, correction)

    def test_future_labels_and_other_horizons_cannot_train_the_correction(self):
        self.build_history()
        correction = self.feedback.correction("INNSA", "wind_speed", "test-weather", 5, T0+timedelta(days=12))
        self.assertEqual(correction["status"], "COLLECTING")
        correction = self.feedback.correction("INNSA", "wind_speed", "test-weather", 6, T0+timedelta(days=90))
        self.assertEqual(correction["sampleCount"], 0)

    def test_calibration_tail_does_not_fit_or_select_the_bias(self):
        for day in range(80):
            issue = T0+timedelta(days=day)
            self.snapshot(issued=issue)
            self.feedback.observe(self.observation(issued=issue, value=35 if 40 <= day < 60 else 15), now=issue+timedelta(days=8))
        correction = self.feedback.correction("INNSA", "wind_speed", "test-weather", 5, T0+timedelta(days=90))
        self.assertEqual(correction["status"], "VALIDATED")
        self.assertEqual(correction["bias"], 5)
        self.assertEqual(correction["validationCorrectedMae"], 0)
        self.assertEqual(correction["upperResidual"], 20)
        self.assertEqual(correction["lowerResidual"], -20)

    def test_availability_purging_can_leave_an_insufficient_four_block_split(self):
        for day in range(32):
            issue = T0+timedelta(days=day)
            self.snapshot(issued=issue)
            self.feedback.observe(self.observation(issued=issue), now=issue+timedelta(days=8))
        correction = self.feedback.correction("INNSA", "wind_speed", "test-weather", 5, T0+timedelta(days=90))
        self.assertEqual(correction["status"], "COLLECTING")
        self.assertEqual(correction["partitions"]["evaluation"], 8)
        self.assertEqual(correction["partitions"]["calibration"], 1)
        self.assertLess(correction["partitions"]["fitting"], 8)

    def test_correction_cannot_train_from_refresh_duplicates(self):
        for hour in range(24):
            issue = T0+timedelta(minutes=hour)
            self.snapshot(issued=issue)
        self.feedback.observe(self.observation(), now=T0+timedelta(days=8))
        correction = self.feedback.correction("INNSA", "wind_speed", "test-weather", 5, T0+timedelta(days=20))
        self.assertEqual(correction["sampleCount"], 1)

    def test_subsequent_evaluation_can_reject_selected_correction(self):
        for day in range(80):
            issue = T0+timedelta(days=day)
            self.snapshot(issued=issue)
            self.feedback.observe(self.observation(issued=issue,value=10 if day>=60 else 15),now=issue+timedelta(days=8))
        result=self.feedback.correction("INNSA","wind_speed","test-weather",5,T0+timedelta(days=90))
        self.assertEqual(result["validationCorrectedMae"],0)
        self.assertEqual(result["status"],"REJECTED")
        self.assertFalse(result["decisionEligible"])
        self.assertEqual(result["bias"],0)

    def test_partitions_are_disjoint_and_availability_purged(self):
        self.build_history()
        result=self.feedback.correction("INNSA","wind_speed","test-weather",5,T0+timedelta(days=90))
        ids=result["targetIds"]
        flattened=[identifier for block in ids.values() for identifier in block]
        self.assertEqual(len(flattened),len(set(flattened)))
        for before,after in (("fitting","validation"),("validation","calibration"),("calibration","evaluation")):
            first=min(self.ledger.get_prediction(i).issued_at for i in ids[after])
            self.assertTrue(all(self.ledger.get_prediction(i).observed_at < first for i in ids[before]))

    def test_reanalysis_and_station_residuals_are_not_pooled(self):
        self.build_history()
        issue=T0+timedelta(days=81)
        self.snapshot(issued=issue)
        old=self.observation(issued=issue,kind="reanalysis")
        self.feedback.observe(WeatherObservation(old.port_code,old.variable,old.valid_at,old.available_at,old.value,"Open-Meteo ERA5 archive","reanalysis","kn"),now=issue+timedelta(days=8))
        result=self.feedback.correction("INNSA","wind_speed","test-weather",5,T0+timedelta(days=92))
        self.assertEqual(result["sampleCount"],1)
        self.assertEqual(result["status"],"COLLECTING")
        self.assertEqual(result["outcomeSource"],"reanalysis: Open-Meteo ERA5 archive")
