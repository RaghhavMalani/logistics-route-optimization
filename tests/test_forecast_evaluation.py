"""Forecasting and evaluation tests.

The claims this project makes about accuracy are only worth anything if the
machinery producing them is correct. These tests check the parts that would
quietly invalidate a benchmark: fold construction that leaks the future,
quantiles that cross, a conformal offset that does not achieve its coverage,
and a stacker that is fitted on the block it is scored on.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.evaluation import model_benchmark
from src.evaluation.metrics import interval_coverage, pinball_loss
from src.forecasting.calibration import apply_offset, conformal_offset
from src.forecasting.forecast_runner import (
    BaselineQuantileForecaster,
    PersistenceQuantileForecaster,
    run_baseline,
)
from src.forecasting.linear_model import RidgeQuantileForecaster
from src.forecasting.tft_dataset import build_supervised


def _panel(days: int = 220, ports=("CHENNAI", "JNPT", "MUNDRA")) -> pd.DataFrame:
    """A deterministic panel with trend, weekly seasonality and noise."""
    rng = np.random.default_rng(11)
    dates = pd.date_range("2025-06-01", periods=days, freq="D")
    rows = []
    for offset, port in enumerate(ports):
        level = 45.0 + offset * 6
        series = (level
                  + 6 * np.sin(np.arange(days) * 2 * np.pi / 7)
                  + np.cumsum(rng.normal(0, 0.6, days)) * 0.4)
        series = np.clip(series, 5, 98)
        for index, date in enumerate(dates):
            rows.append({
                "port_id": port, "date": date,
                "congestion_index": float(series[index]),
                "delay_hours": float(4 + series[index] * 0.12),
                "throughput": float(90_000 + series[index] * 400),
                "utilization": float(np.clip(series[index] / 100, 0, 1)),
                "queue_proxy": float(np.clip(series[index] / 110, 0, 1)),
                "turnaround_proxy": 0.4,
                "arrival_count": float(4 + (index % 5)),
                "anchorage_count": float(index % 3),
                "capacity_pressure": 0.5, "anomaly_score": 0.1,
                "berth_pressure": 0.3, "arrival_clustering": 0.1,
                "disruption_pressure": 0.05, "weather_persistence": 0.0,
                "data_quality_score": 0.9, "WxImpactIndex": 0.15,
            })
    return pd.DataFrame(rows)


class SupervisedFrameTests(unittest.TestCase):
    def setUp(self):
        self.panel = _panel()
        self.supervised = build_supervised(self.panel, None, horizon=10)

    def test_labels_come_only_from_the_target_date(self):
        frame = self.supervised.frame
        expected = frame["forecast_origin_date"] + pd.to_timedelta(
            frame["horizon_day"], unit="D")
        pd.testing.assert_series_equal(
            frame["target_date"].reset_index(drop=True),
            expected.reset_index(drop=True), check_names=False)

    def test_origin_features_are_known_at_the_origin(self):
        """`congestion_index_now` must equal the panel value at the origin."""
        frame = self.supervised.frame
        lookup = {(row.port_id, row.date): row.congestion_index
                  for row in self.panel.itertuples()}
        sample = frame.sample(60, random_state=3)
        for row in sample.itertuples():
            self.assertAlmostEqual(
                float(row.congestion_index_now),
                float(lookup[(row.port_id, row.forecast_origin_date)]),
                places=6)

    def test_specialist_features_reach_the_feature_matrix(self):
        for column in ("capacity_pressure", "anomaly_score", "berth_pressure",
                       "arrival_clustering", "disruption_pressure",
                       "data_quality_score"):
            self.assertIn(column, self.supervised.feature_cols,
                          f"{column} never reaches the forecaster")


class FoldTests(unittest.TestCase):
    def setUp(self):
        self.supervised = build_supervised(_panel(), None, horizon=10)
        self.folds = model_benchmark.expanding_folds(self.supervised.frame,
                                                     n_folds=4)

    def test_folds_expand_and_do_not_overlap_in_time(self):
        self.assertGreaterEqual(len(self.folds), 2)
        for previous, current in zip(self.folds, self.folds[1:]):
            self.assertGreaterEqual(len(current.train), len(previous.train))
            self.assertGreater(current.cutoff, previous.cutoff)

    def test_training_labels_are_observable_at_the_cutoff(self):
        for fold in self.folds:
            self.assertTrue((fold.train["target_date"] <= fold.cutoff).all(),
                            "a training label was not observable at the cutoff")

    def test_test_targets_are_strictly_after_the_cutoff(self):
        for fold in self.folds:
            self.assertTrue((fold.test["target_date"] > fold.cutoff).all())
            self.assertTrue((fold.test["forecast_origin_date"] > fold.cutoff).all())


class ForecasterTests(unittest.TestCase):
    def setUp(self):
        self.panel = _panel()
        self.supervised = build_supervised(self.panel, None, horizon=10)
        self.folds = model_benchmark.expanding_folds(self.supervised.frame,
                                                     n_folds=3)

    def test_gbm_quantiles_never_cross(self):
        fold = self.folds[-1]
        model = BaselineQuantileForecaster().fit(
            fold.train, self.supervised.feature_cols, ["congestion_index"])
        preds = model.predict(fold.test, self.supervised.feature_cols)
        self.assertTrue((preds["q10"] <= preds["q50"]).all())
        self.assertTrue((preds["q50"] <= preds["q90"]).all())

    def test_residual_mode_anchors_on_the_last_observation(self):
        """Turning the residual formulation off must change the predictions."""
        fold = self.folds[-1]
        cols = self.supervised.feature_cols
        residual = BaselineQuantileForecaster(residual=True).fit(
            fold.train, cols, ["congestion_index"]).predict(fold.test, cols)
        level = BaselineQuantileForecaster(residual=False).fit(
            fold.train, cols, ["congestion_index"]).predict(fold.test, cols)
        self.assertFalse(np.allclose(residual["q50"], level["q50"]))

    def test_persistence_bands_widen_with_horizon(self):
        fold = self.folds[-1]
        model = PersistenceQuantileForecaster().fit(fold.train)
        preds = model.predict(fold.test)
        widths = (preds["q90"] - preds["q10"]).groupby(
            preds["horizon_day"]).mean()
        self.assertGreater(float(widths.loc[10]), float(widths.loc[1]),
                           "a 10-day band must be wider than a 1-day band")

    def test_persistence_median_is_the_last_observation(self):
        fold = self.folds[-1]
        preds = PersistenceQuantileForecaster().fit(fold.train).predict(fold.test)
        np.testing.assert_allclose(
            preds["q50"].to_numpy(),
            np.clip(fold.test["congestion_index_now"].to_numpy(), 0, 100),
            atol=1e-6)

    def test_ridge_produces_usable_quantiles(self):
        fold = self.folds[-1]
        model = RidgeQuantileForecaster().fit(fold.train,
                                              self.supervised.feature_cols)
        preds = model.predict(fold.test, self.supervised.feature_cols)
        self.assertTrue((preds["q10"] <= preds["q90"]).all())
        self.assertTrue(preds["q50"].notna().all())

    def test_live_forecast_has_one_row_per_port_and_horizon(self):
        forecast = run_baseline(self.panel, None, horizon=10)
        self.assertEqual(len(forecast), self.panel["port_id"].nunique() * 10)
        self.assertTrue((forecast["q10"] <= forecast["q90"]).all())
        self.assertTrue(forecast["confidence_score"].between(0, 1).all())


class CalibrationTests(unittest.TestCase):
    def test_conformal_offset_reaches_the_nominal_coverage(self):
        rng = np.random.default_rng(5)
        truth = rng.normal(50, 10, 4000)
        # Deliberately too-narrow bands.
        lower, upper = np.full(4000, 47.0), np.full(4000, 53.0)
        self.assertLess(interval_coverage(truth, lower, upper), 0.5)

        offset = conformal_offset(truth, lower, upper, alpha=0.2)
        widened_lo, widened_hi = apply_offset(lower, upper, offset, lo_floor=-100)
        coverage = interval_coverage(truth, widened_lo, widened_hi)
        self.assertGreaterEqual(coverage, 0.78)
        self.assertLessEqual(coverage, 0.88)

    def test_offset_is_zero_when_the_band_already_covers(self):
        rng = np.random.default_rng(6)
        truth = rng.normal(50, 1, 2000)
        lower, upper = np.full(2000, 20.0), np.full(2000, 80.0)
        self.assertLessEqual(conformal_offset(truth, lower, upper, alpha=0.2), 0.0)

    def test_too_few_points_returns_no_offset(self):
        self.assertEqual(conformal_offset([1, 2, 3], [0, 1, 2], [2, 3, 4]), 0.0)

    def test_pinball_loss_is_minimised_at_the_true_quantile(self):
        rng = np.random.default_rng(7)
        truth = rng.normal(0, 1, 20_000)
        true_q90 = float(np.quantile(truth, 0.9))
        at_truth = pinball_loss(truth, np.full(20_000, true_q90), 0.9)
        below = pinball_loss(truth, np.full(20_000, true_q90 - 0.5), 0.9)
        above = pinball_loss(truth, np.full(20_000, true_q90 + 0.5), 0.9)
        self.assertLess(at_truth, below)
        self.assertLess(at_truth, above)


class StackingTests(unittest.TestCase):
    def test_missing_weighted_member_does_not_create_zero_predictions(self):
        block = pd.DataFrame({"q50__a": [np.nan], "q50__b": [30.0]})
        result = model_benchmark._blend_column(block, ["a", "b"], {"a": 1.0, "b": 0.0}, "q50")
        self.assertEqual(result[0], 30.0)

    def test_legacy_fitted_policy_and_accuracy_are_withheld(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from backend.app.services import cache_service
        from src.forecasting.ensemble import load_ensemble_policy
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "legacy.json"
            file.write_text(json.dumps({"available": True, "version": "walk-forward-v3", "fitted": True,
                                        "globalWeights": {"gbm": 1}, "summary": {"bestMae": 1}}))
            self.assertFalse(load_ensemble_policy(file).fitted)
            with patch.object(cache_service, "BENCHMARK_CACHE", file):
                result = cache_service.get_benchmark()
            self.assertFalse(result["available"])
            self.assertNotIn("summary", result)

    def test_manifest_tracks_data_changes_and_configuration(self):
        panel = _panel()
        before = model_benchmark.benchmark_manifest(panel, 5, 3, False, 12)
        panel.loc[0, "congestion_index"] += 1
        after = model_benchmark.benchmark_manifest(panel, 5, 3, False, 12)
        self.assertNotEqual(before["datasetSha256"], after["datasetSha256"])
        self.assertEqual(len(before["forecastCodeSha256"]), 64)
        self.assertEqual(before["configuration"]["horizonDays"], 5)

    def test_stacking_boundaries_purge_labels_and_holdout_cannot_change_weights(self):
        origins = pd.date_range("2025-06-01", periods=80)
        rows = []
        for i, origin in enumerate(origins):
            for model, offset in ((model_benchmark.NAIVE, 0), (model_benchmark.GBM, 5), (model_benchmark.RIDGE, 2)):
                rows.append({"port_id": "JNPT", "forecast_origin_date": origin,
                    "target_date": origin+pd.Timedelta(days=3), "horizon_day": 3,
                    "y_congestion_index": 20, "fold": i//30, "regime": "UNKNOWN",
                    "model": model, "q10": 15+offset, "q50": 20+offset, "q90": 25+offset})
        predictions = pd.DataFrame(rows)
        fit, calibration, holdout = model_benchmark.chronological_partitions(predictions)
        self.assertLess(fit.target_date.max(), calibration.forecast_origin_date.min())
        self.assertLess(calibration.target_date.max(), holdout.forecast_origin_date.min())
        policy, _, _ = model_benchmark.fit_stacking_policy(fit, "y_congestion_index", 2, model_benchmark.RIDGE, calibration)
        changed = predictions.copy()
        changed.loc[changed.fold == changed.fold.max(), "y_congestion_index"] = 10000
        next_fit, next_calibration, _ = model_benchmark.chronological_partitions(changed)
        other, _, _ = model_benchmark.fit_stacking_policy(next_fit, "y_congestion_index", 2, model_benchmark.RIDGE, next_calibration)
        self.assertEqual(policy.global_weights, other.global_weights)
        self.assertEqual(policy.conformal_by_horizon, other.conformal_by_horizon)

    def test_simplex_weights_sum_to_one(self):
        grid = model_benchmark._simplex(["a", "b", "c"], step=0.25)
        self.assertTrue(all(abs(sum(w.values()) - 1.0) < 1e-9 for w in grid))
        self.assertIn({"a": 1.0, "b": 0.0, "c": 0.0}, grid)

    def test_blend_renormalises_over_available_members(self):
        block = pd.DataFrame({
            "q50__a": [10.0, np.nan],
            "q50__b": [20.0, 30.0],
        })
        blended = model_benchmark._blend_column(
            block, ["a", "b"], {"a": 0.5, "b": 0.5}, "q50")
        # Row 0 blends both; row 1 falls back entirely to the member present.
        self.assertAlmostEqual(blended[0], 15.0, places=6)
        self.assertAlmostEqual(blended[1], 30.0, places=6)

    def test_benchmark_runs_end_to_end_and_writes_artefacts(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            summary = model_benchmark.run_benchmark(
                _panel(), None, horizon=5, n_folds=3, include_tft=False,
                output_dir=out)

            self.assertTrue(summary["summary"]["folds"] >= 2)
            for name in ("model_benchmark.csv", "horizon_benchmark.csv",
                         "port_benchmark.csv", "regime_benchmark.csv",
                         "calibration.json", "ensemble_weights.json",
                         "benchmark_summary.json"):
                self.assertTrue((out / name).exists(), f"{name} was not written")

            table = pd.read_csv(out / "model_benchmark.csv")
            self.assertIn(model_benchmark.NAIVE, set(table["model"]))
            self.assertIn(model_benchmark.ENSEMBLE, set(table["model"]))

            # The ensemble must be scored on the same rows as the baselines.
            naive_rows = int(table.loc[table["model"] == model_benchmark.NAIVE,
                                       "n"].iloc[0])
            ensemble_rows = int(table.loc[table["model"] == model_benchmark.ENSEMBLE,
                                          "n"].iloc[0])
            self.assertEqual(naive_rows, ensemble_rows)

            weights = json.loads((out / "ensemble_weights.json").read_text())
            self.assertTrue(weights["fitted"])
            for row in weights["byHorizon"].values():
                self.assertAlmostEqual(sum(row.values()), 1.0, places=6)

    def test_benchmark_reports_measured_untouched_holdout_coverage(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            model_benchmark.run_benchmark(_panel(), None, horizon=5, n_folds=3,
                                          include_tft=False, output_dir=out)
            table = pd.read_csv(out / "model_benchmark.csv")
            row = table[table["model"] == model_benchmark.ENSEMBLE].iloc[0]
            # Coverage can drift on a genuinely untouched period. Requiring it
            # to look like the fitting sample would encourage tuning on test.
            heldout = pd.read_csv(out / "holdout_predictions.csv")
            ensemble = heldout[heldout["model"] == model_benchmark.ENSEMBLE]
            measured = interval_coverage(ensemble["y_congestion_index"], ensemble["q10"], ensemble["q90"])
            self.assertAlmostEqual(float(row["coverage_80pct"]), measured, places=4)
            self.assertAlmostEqual(float(row["calibration_error"]), abs(measured-0.8), places=4)


if __name__ == "__main__":
    unittest.main()
