"""Adaptive TFT + GBM ensemble for robust multi-horizon forecasting.

A single deep model is brittle on relatively small and non-stationary port data.
This module combines the TFT and leakage-safe GBM quantile baseline using
walk-forward benchmark error when it is available, and a conservative prior
otherwise. Confidence is discounted when the models disagree.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.utils.config import PORT_ID


def weights_from_benchmark(
    path: str | Path | None,
    default_tft: float = 0.72,
) -> tuple[float, float]:
    """Return (tft_weight, gbm_weight) using inverse benchmark MAE."""
    if path is None:
        return default_tft, 1.0 - default_tft
    p = Path(path)
    if not p.exists():
        return default_tft, 1.0 - default_tft
    try:
        table = pd.read_csv(p)
        if "model" not in table or "mae" not in table:
            return default_tft, 1.0 - default_tft
        tft = table[table["model"].astype(str).str.contains("TFT", case=False, na=False)]
        gbm = table[table["model"].astype(str).str.contains("GBM", case=False, na=False)]
        if tft.empty or gbm.empty:
            return default_tft, 1.0 - default_tft
        tft_mae = max(float(tft.iloc[0]["mae"]), 1e-6)
        gbm_mae = max(float(gbm.iloc[0]["mae"]), 1e-6)
        inverse_error = np.array([1.0 / tft_mae, 1.0 / gbm_mae], dtype=float)
        weights = inverse_error / inverse_error.sum()
        # A small holdout should never make either model completely dominate.
        tft_weight = float(np.clip(weights[0], 0.20, 0.85))
        return tft_weight, 1.0 - tft_weight
    except Exception:
        return default_tft, 1.0 - default_tft


def blend_forecasts(
    tft: pd.DataFrame,
    baseline: pd.DataFrame,
    tft_weight: float,
    baseline_weight: float | None = None,
) -> pd.DataFrame:
    """Blend aligned forecasts and preserve monotonic uncertainty bands."""
    baseline_weight = 1.0 - tft_weight if baseline_weight is None else baseline_weight
    total = max(tft_weight + baseline_weight, 1e-9)
    wt, wb = tft_weight / total, baseline_weight / total

    keys = [PORT_ID, "horizon_day"]
    bcols = keys + [
        c for c in (
            "q10", "q50", "q90", "predicted_congestion",
            "predicted_delay", "predicted_throughput", "confidence_score",
        ) if c in baseline.columns
    ]
    joined = tft.merge(
        baseline[bcols], on=keys, how="left", suffixes=("_tft", "_gbm")
    )

    excluded = {
        "q10", "q50", "q90", "predicted_congestion", "predicted_delay",
        "predicted_throughput", "confidence_score", "model",
    }
    out = joined[[c for c in tft.columns if c not in excluded]].copy()

    for col in ("q10", "q50", "q90", "predicted_congestion"):
        tft_col, gbm_col = f"{col}_tft", f"{col}_gbm"
        if tft_col in joined and gbm_col in joined:
            out[col] = wt * joined[tft_col] + wb * joined[gbm_col]
        elif tft_col in joined:
            out[col] = joined[tft_col]
        elif gbm_col in joined:
            out[col] = joined[gbm_col]
        elif col in joined:
            out[col] = joined[col]

    # The current TFT path delegates secondary targets to the GBM, so preserve
    # those complete estimates instead of pretending to have two independent
    # secondary models. Pandas only suffixes overlapping columns; a GBM-only
    # secondary target therefore remains unsuffixed after the merge.
    for col in ("predicted_delay", "predicted_throughput"):
        gbm_col, tft_col = f"{col}_gbm", f"{col}_tft"
        if gbm_col in joined:
            out[col] = joined[gbm_col]
        elif col in joined:
            out[col] = joined[col]
        elif tft_col in joined:
            out[col] = joined[tft_col]

    quantiles = np.sort(out[["q10", "q50", "q90"]].to_numpy(dtype=float), axis=1)
    out[["q10", "q50", "q90"]] = quantiles
    out["predicted_congestion"] = out["q50"]

    tft_conf = joined.get(
        "confidence_score_tft",
        joined.get("confidence_score", pd.Series(0.75, index=joined.index)),
    )
    gbm_conf = joined.get(
        "confidence_score_gbm",
        joined.get("confidence_score", pd.Series(0.70, index=joined.index)),
    )
    disagreement = ((joined["q50_tft"] - joined["q50_gbm"]).abs() / 35.0).clip(0, 1)
    agreement_discount = 1.0 - 0.30 * disagreement
    out["confidence_score"] = (
        (wt * tft_conf + wb * gbm_conf) * agreement_discount
    ).clip(0.05, 0.98).round(3)

    out["model"] = "adaptive_ensemble"
    out["ensemble_tft_weight"] = round(wt, 3)
    out["ensemble_gbm_weight"] = round(wb, 3)
    out["model_disagreement"] = disagreement.round(3)
    return out.reset_index(drop=True)
