from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.experts import anomaly_expert, capacity_expert
from src.forecasting.ensemble import blend_forecasts


class SpecialistIntelligenceTests(unittest.TestCase):
    def setUp(self):
        dates = pd.date_range("2026-01-01", periods=45, freq="D")
        congestion = np.full(45, 35.0)
        congestion[-1] = 92.0
        throughput = np.full(45, 100.0)
        throughput[-1] = 45.0
        self.observed = pd.DataFrame(
            {
                "port_id": "CHENNAI",
                "date": dates,
                "congestion_index": congestion,
                "delay_hours": np.r_[np.full(44, 6.0), 30.0],
                "throughput": throughput,
                "utilization": np.r_[np.full(44, 0.55), 0.95],
            }
        )
        self.ops = pd.DataFrame(
            {
                "port_id": "CHENNAI",
                "date": dates,
                "queue_proxy": np.r_[np.full(44, 0.2), 0.92],
                "turnaround_proxy": np.r_[np.full(44, 0.25), 0.88],
                "ais_confidence": 0.9,
            }
        )

    def test_anomaly_agent_detects_terminal_spike(self):
        result = anomaly_expert.run(self.observed, self.ops)
        self.assertLess(float(result.iloc[-2]["anomaly_score"]), 0.25)
        self.assertGreater(float(result.iloc[-1]["anomaly_score"]), 0.75)
        self.assertGreater(float(result.iloc[-1]["anomaly_confidence"]), 0.75)

    def test_capacity_agent_reacts_to_queue_and_utilization(self):
        result = capacity_expert.run(self.observed, self.ops)
        self.assertGreater(float(result.iloc[-1]["capacity_pressure"]), 0.75)
        self.assertGreater(float(result.iloc[-1]["queue_momentum"]), 0.8)
        self.assertGreater(float(result.iloc[-1]["capacity_confidence"]), 0.75)


class EnsembleTests(unittest.TestCase):
    def test_blend_is_monotonic_and_exposes_disagreement(self):
        meta = {
            "port_id": ["CHENNAI"],
            "forecast_origin_date": [pd.Timestamp("2026-09-08")],
            "target_date": [pd.Timestamp("2026-09-09")],
            "horizon_day": [1],
        }
        tft = pd.DataFrame(
            {
                **meta,
                "q10": [48.0], "q50": [62.0], "q90": [82.0],
                "predicted_congestion": [62.0], "confidence_score": [0.9],
                "model": ["tft"],
            }
        )
        gbm = pd.DataFrame(
            {
                **meta,
                "q10": [40.0], "q50": [50.0], "q90": [65.0],
                "predicted_congestion": [50.0],
                "predicted_delay": [14.0], "predicted_throughput": [90.0],
                "confidence_score": [0.82], "model": ["baseline"],
            }
        )
        out = blend_forecasts(tft, gbm, 0.7, 0.3).iloc[0]
        self.assertLessEqual(out["q10"], out["q50"])
        self.assertLessEqual(out["q50"], out["q90"])
        self.assertEqual(out["model"], "adaptive_ensemble")
        self.assertGreater(out["model_disagreement"], 0.0)
        self.assertEqual(out["predicted_delay"], 14.0)


if __name__ == "__main__":
    unittest.main()
