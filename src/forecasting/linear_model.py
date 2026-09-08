"""Regularised linear quantile forecaster -- the ensemble's second opinion.

Boosted trees and a linear model fail differently. Trees are excellent at
capturing the sharp, threshold-like behaviour of a congested berth line but
extrapolate poorly; a ridge fit is smooth, extrapolates sensibly and degrades
gracefully at long horizons where tree splits run out of support. Averaging two
models with genuinely different inductive biases is the cheapest reliable
accuracy gain available on a dataset this size -- and unlike the TFT it needs no
deep-learning stack, so the adaptive ensemble is real in every deployment.

Intervals come from the empirical distribution of *training* residuals per
horizon, which keeps the quantiles honest: a 10-day-ahead band is wider than a
1-day-ahead band because the measured residuals say so, not because a constant
was chosen.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from src.utils.config import PORT_ID, PRIMARY_TARGET
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

_MIN_TRAIN_ROWS = 40
_MIN_RESIDUALS = 12


class RidgeQuantileForecaster:
    """Ridge median forecast plus horizon-specific empirical residual bands."""

    def __init__(self, primary_target: str = PRIMARY_TARGET, alpha: float = 3.0,
                 residual: bool = True):
        self.primary_target = primary_target
        self.alpha = alpha
        # Like the GBM, the ridge learns the departure from the last observed
        # value rather than the level, so persistence is its prior.
        self.residual = residual
        self.model = None
        self.scaler = None
        self.feature_cols: List[str] = []
        self.residual_quantiles: Dict[int, tuple[float, float]] = {}
        self.global_band: tuple[float, float] = (-8.0, 8.0)
        self.fallback_mean: float = 0.0

    def _anchor(self, frame: pd.DataFrame) -> np.ndarray | None:
        """Last observed value of the target at the forecast origin."""
        if not self.residual:
            return None
        column = f"{self.primary_target}_now"
        if column not in frame.columns:
            return None
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        return np.nan_to_num(values, nan=self.fallback_mean)

    def fit(self, train_frame: pd.DataFrame, feature_cols: List[str]
            ) -> "RidgeQuantileForecaster":
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler

        self.feature_cols = list(feature_cols)
        ycol = f"y_{self.primary_target}"
        frame = train_frame[train_frame[ycol].notna()]
        if len(frame) < _MIN_TRAIN_ROWS:
            log.warning("RidgeQuantileForecaster: only %d training rows; "
                        "falling back to the training mean.", len(frame))
            self.fallback_mean = float(frame[ycol].mean()) if len(frame) else 0.0
            return self

        X = frame[self.feature_cols].to_numpy(dtype=float)
        y = frame[ycol].to_numpy(dtype=float)
        self.fallback_mean = float(np.nanmean(y))
        anchor = self._anchor(frame)
        if anchor is not None:
            y = y - anchor

        self.scaler = StandardScaler().fit(X)
        self.model = Ridge(alpha=self.alpha, random_state=None)
        self.model.fit(self.scaler.transform(X), y)

        residuals = y - self.model.predict(self.scaler.transform(X))
        self.global_band = (float(np.quantile(residuals, 0.10)),
                            float(np.quantile(residuals, 0.90)))

        horizons = frame["horizon_day"].to_numpy(dtype=int)
        for horizon in np.unique(horizons):
            mask = horizons == horizon
            if mask.sum() >= _MIN_RESIDUALS:
                block = residuals[mask]
                self.residual_quantiles[int(horizon)] = (
                    float(np.quantile(block, 0.10)),
                    float(np.quantile(block, 0.90)))
        return self

    def predict(self, frame: pd.DataFrame,
                feature_cols: List[str] | None = None) -> pd.DataFrame:
        feature_cols = feature_cols or self.feature_cols
        out = frame[[PORT_ID, "forecast_origin_date", "target_date",
                     "horizon_day"]].copy()

        if self.model is None or self.scaler is None:
            centre = np.full(len(frame), self.fallback_mean, dtype=float)
        else:
            X = frame[feature_cols].to_numpy(dtype=float)
            centre = self.model.predict(self.scaler.transform(X))
            anchor = self._anchor(frame)
            if anchor is not None:
                centre = centre + anchor

        lows, highs = [], []
        for horizon in frame["horizon_day"].to_numpy(dtype=int):
            lo, hi = self.residual_quantiles.get(int(horizon), self.global_band)
            lows.append(lo)
            highs.append(hi)

        q50 = np.clip(centre, 0.0, 100.0)
        q10 = np.clip(centre + np.asarray(lows), 0.0, 100.0)
        q90 = np.clip(centre + np.asarray(highs), 0.0, 100.0)
        stacked = np.sort(np.vstack([q10, q50, q90]), axis=0)

        out["q10"], out["q50"], out["q90"] = stacked[0], stacked[1], stacked[2]
        out["predicted_congestion"] = out["q50"]
        width = (out["q90"] - out["q10"]).to_numpy(dtype=float)
        out["confidence_score"] = np.clip(1.0 - width / 60.0, 0.05, 0.95).round(3)
        out["model"] = "ridge_quantile"
        return out.reset_index(drop=True)
