"""Regression tests for the specialist agents and the adaptive ensemble.

These cover the behaviours that would silently degrade the product if they
broke: an agent that stops reacting to a real operational spike, an ensemble
that emits non-monotonic quantiles, a fitted weighting policy that ignores the
horizon, and a leakage path that lets a feature see its own future.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.experts import (
    anomaly_expert,
    arrival_dynamics_expert,
    capacity_expert,
    data_quality_expert,
    disruption_expert,
    weather_persistence_expert,
)
from src.forecasting.ensemble import (
    EnsemblePolicy,
    GBM,
    PERSISTENCE,
    SECOND_OPINION,
    blend_forecasts,
    blend_members,
)


def _observed(days: int = 45, port: str = "CHENNAI") -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=days, freq="D")
    congestion = np.full(days, 35.0)
    congestion[-1] = 92.0
    throughput = np.full(days, 100.0)
    throughput[-1] = 45.0
    return pd.DataFrame({
        "port_id": port,
        "date": dates,
        "congestion_index": congestion,
        "delay_hours": np.r_[np.full(days - 1, 6.0), 30.0],
        "throughput": throughput,
        "utilization": np.r_[np.full(days - 1, 0.55), 0.95],
    })


def _ops(days: int = 45, port: str = "CHENNAI") -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=days, freq="D")
    return pd.DataFrame({
        "port_id": port,
        "date": dates,
        "queue_proxy": np.r_[np.full(days - 1, 0.2), 0.92],
        "turnaround_proxy": np.r_[np.full(days - 1, 0.25), 0.88],
        "arrival_count": np.r_[np.full(days - 1, 4.0), 14.0],
        "anchorage_count": np.r_[np.full(days - 1, 1.0), 9.0],
        "ais_confidence": 0.9,
    })


class SpecialistIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.observed = _observed()
        self.ops = _ops()

    def test_anomaly_agent_detects_terminal_spike(self):
        result = anomaly_expert.run(self.observed, self.ops)
        self.assertLess(float(result.iloc[-2]["anomaly_score"]), 0.25)
        self.assertGreater(float(result.iloc[-1]["anomaly_score"]), 0.75)
        self.assertGreater(float(result.iloc[-1]["anomaly_confidence"]), 0.75)

    def test_anomaly_agent_is_leakage_safe(self):
        """A spike on the final day must not raise the score on earlier days."""
        quiet = self.observed.copy()
        quiet.loc[quiet.index[-1], "congestion_index"] = 35.0
        quiet.loc[quiet.index[-1], "delay_hours"] = 6.0
        quiet.loc[quiet.index[-1], "throughput"] = 100.0

        with_spike = anomaly_expert.run(self.observed, self.ops)
        without_spike = anomaly_expert.run(quiet, self.ops)
        np.testing.assert_allclose(
            with_spike["anomaly_score"].to_numpy()[:-1],
            without_spike["anomaly_score"].to_numpy()[:-1],
            atol=1e-9,
            err_msg="a future spike changed a past anomaly score (leakage)")

    def test_capacity_agent_reacts_to_queue_and_utilization(self):
        result = capacity_expert.run(self.observed, self.ops)
        self.assertGreater(float(result.iloc[-1]["capacity_pressure"]), 0.75)
        self.assertGreater(float(result.iloc[-1]["queue_momentum"]), 0.8)
        self.assertGreater(float(result.iloc[-1]["capacity_confidence"]), 0.75)

    def test_arrival_dynamics_detects_clustering_and_buildup(self):
        result = arrival_dynamics_expert.run(self.observed, self.ops)
        last = result.iloc[-1]
        self.assertGreater(float(last["arrival_acceleration"]), 0.6)
        self.assertGreater(float(last["arrival_clustering"]), 0.1)
        self.assertGreater(float(last["anchorage_buildup"]), 0.5)
        self.assertGreater(float(last["berth_pressure"]),
                           float(result.iloc[-2]["berth_pressure"]))

    def test_arrival_dynamics_reports_no_confidence_without_a_stream(self):
        result = arrival_dynamics_expert.run(self.observed, None)
        self.assertEqual(float(result.iloc[-1]["arrival_confidence"]), 0.0)

    def test_weather_persistence_separates_shock_from_sustained(self):
        dates = pd.date_range("2026-01-01", periods=40, freq="D")
        calm = np.full(40, 0.05)

        shock = calm.copy()
        shock[-1] = 0.85
        shock_frame = pd.DataFrame({"port_id": "CHENNAI", "date": dates,
                                    "horizon_day": 0, "WxImpactIndex": shock,
                                    "weather_confidence": 0.9})
        shock_out = weather_persistence_expert.run(shock_frame).iloc[-1]

        sustained = calm.copy()
        sustained[-6:] = 0.7
        sustained_frame = pd.DataFrame({"port_id": "CHENNAI", "date": dates,
                                        "horizon_day": 0,
                                        "WxImpactIndex": sustained,
                                        "weather_confidence": 0.9})
        sustained_out = weather_persistence_expert.run(sustained_frame).iloc[-1]

        self.assertEqual(shock_out["weather_regime"], "SHOCK")
        self.assertEqual(sustained_out["weather_regime"], "PERSISTENT")
        self.assertGreater(float(sustained_out["weather_persistence"]),
                           float(shock_out["weather_persistence"]))

    def test_disruption_expert_propagates_a_chokepoint_collapse(self):
        dates = pd.date_range("2025-10-01", periods=120, freq="D")
        transits = np.full(120, 60.0)
        transits[-25:] = 12.0     # a sustained collapse at Hormuz
        history = pd.DataFrame({
            "date": np.r_[dates, dates],
            "portname": ["Strait of Hormuz"] * 120 + ["Malacca Strait"] * 120,
            "n_total": np.r_[transits, np.full(120, 200.0)],
        })
        grid = pd.DataFrame({
            "port_id": ["MUNDRA"] * 120 + ["VIZAG"] * 120,
            "date": np.r_[dates, dates],
        })
        result = disruption_expert.run(grid, history)

        mundra = result[result["port_id"] == "MUNDRA"].iloc[-1]
        vizag = result[result["port_id"] == "VIZAG"].iloc[-1]
        self.assertGreater(float(mundra["disruption_pressure"]), 0.3)
        # Mundra is far more Hormuz-exposed than Vizag, so it must feel more.
        self.assertGreater(float(mundra["disruption_pressure"]),
                           float(vizag["disruption_pressure"]))
        self.assertEqual(mundra["disruption_lead_chokepoint"], "HORMUZ")

    def test_data_quality_penalises_missing_inputs(self):
        complete = self.observed.merge(self.ops, on=["port_id", "date"])
        complete["capacity_pressure"] = 0.5
        complete["anomaly_score"] = 0.1
        complete["WxImpactIndex"] = 0.2
        complete["demand_pressure"] = 0.5

        degraded = complete.copy()
        for column in ("throughput", "utilization", "WxImpactIndex",
                       "demand_pressure", "turnaround_proxy"):
            degraded[column] = np.nan

        good = data_quality_expert.run(complete).iloc[-1]["data_quality_score"]
        bad = data_quality_expert.run(degraded).iloc[-1]["data_quality_score"]
        self.assertGreater(float(good), float(bad))
        self.assertGreater(float(good), 0.6)


def _member(q10, q50, q90, model, **extra) -> pd.DataFrame:
    meta = {
        "port_id": ["CHENNAI"],
        "forecast_origin_date": [pd.Timestamp("2026-09-08")],
        "target_date": [pd.Timestamp("2026-09-09")],
        "horizon_day": [1],
    }
    return pd.DataFrame({
        **meta, "q10": [q10], "q50": [q50], "q90": [q90],
        "predicted_congestion": [q50], "confidence_score": [0.85],
        "model": [model], **{k: [v] for k, v in extra.items()},
    })


class EnsembleTests(unittest.TestCase):
    def test_blend_is_monotonic_and_exposes_disagreement(self):
        tft = _member(48.0, 62.0, 82.0, "tft")
        gbm = _member(40.0, 50.0, 65.0, "baseline",
                      predicted_delay=14.0, predicted_throughput=90.0)

        out = blend_forecasts(tft, gbm, 0.7, 0.3).iloc[0]
        self.assertLessEqual(out["q10"], out["q50"])
        self.assertLessEqual(out["q50"], out["q90"])
        self.assertEqual(out["model"], "adaptive_ensemble")
        self.assertGreater(out["model_disagreement"], 0.0)
        self.assertEqual(out["predicted_delay"], 14.0)

    def test_fixed_weight_is_respected(self):
        tft = _member(50.0, 60.0, 70.0, "tft")
        gbm = _member(30.0, 40.0, 50.0, "baseline", predicted_delay=5.0)
        out = blend_forecasts(tft, gbm, 0.75, 0.25).iloc[0]
        self.assertAlmostEqual(float(out["q50"]), 0.75 * 60 + 0.25 * 40, places=6)

    def test_multi_member_blend_honours_horizon_weights(self):
        policy = EnsemblePolicy(
            members=[PERSISTENCE, GBM],
            global_weights={PERSISTENCE: 0.5, GBM: 0.5},
            by_horizon={1: {PERSISTENCE: 0.9, GBM: 0.1}},
            fitted=True, source="test")
        persistence = _member(30.0, 40.0, 50.0, "persistence")
        gbm = _member(60.0, 70.0, 80.0, "baseline", predicted_delay=9.0)

        out = blend_members({PERSISTENCE: persistence, GBM: gbm}, policy).iloc[0]
        self.assertAlmostEqual(float(out["q50"]), 0.9 * 40 + 0.1 * 70, places=6)
        self.assertAlmostEqual(float(out["weight_persistence"]), 0.9, places=3)

    def test_conformal_offset_widens_the_band(self):
        policy = EnsemblePolicy(
            members=[PERSISTENCE, GBM],
            global_weights={PERSISTENCE: 0.5, GBM: 0.5},
            conformal_by_horizon={1: 4.0}, fitted=True, source="test")
        persistence = _member(40.0, 50.0, 60.0, "persistence")
        gbm = _member(40.0, 50.0, 60.0, "baseline", predicted_delay=3.0)

        out = blend_members({PERSISTENCE: persistence, GBM: gbm}, policy).iloc[0]
        self.assertAlmostEqual(float(out["q10"]), 36.0, places=6)
        self.assertAlmostEqual(float(out["q90"]), 64.0, places=6)

    def test_disagreement_discounts_confidence(self):
        agree_a = _member(45.0, 50.0, 55.0, "tft")
        agree_b = _member(45.0, 50.0, 55.0, "baseline", predicted_delay=4.0)
        disagree_a = _member(20.0, 25.0, 30.0, "tft")
        disagree_b = _member(70.0, 75.0, 80.0, "baseline", predicted_delay=4.0)

        agreed = blend_forecasts(agree_a, agree_b, 0.5).iloc[0]
        disagreed = blend_forecasts(disagree_a, disagree_b, 0.5).iloc[0]
        self.assertLess(disagreed["confidence_score"], agreed["confidence_score"])
        self.assertGreater(disagreed["model_disagreement"],
                           agreed["model_disagreement"])

    def test_unfitted_policy_reports_itself_as_unfitted(self):
        policy = EnsemblePolicy()
        self.assertFalse(policy.fitted)
        self.assertIn("equal weighting", policy.describe())
        weights = policy.weights_for(horizon=3)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=6)

    def test_missing_member_row_renormalises_instead_of_zeroing(self):
        """A member absent on a row must not drag the blend toward zero."""
        policy = EnsemblePolicy(
            members=[PERSISTENCE, GBM, SECOND_OPINION],
            global_weights={PERSISTENCE: 0.3, GBM: 0.4, SECOND_OPINION: 0.3},
            fitted=True, source="test")
        persistence = _member(40.0, 50.0, 60.0, "persistence")
        gbm = _member(40.0, 50.0, 60.0, "baseline", predicted_delay=3.0)
        # The second opinion produced nothing for this row.
        absent = persistence.iloc[0:0].copy()

        out = blend_members(
            {PERSISTENCE: persistence, GBM: gbm, SECOND_OPINION: absent},
            policy).iloc[0]
        self.assertAlmostEqual(float(out["q50"]), 50.0, places=6)


if __name__ == "__main__":
    unittest.main()
