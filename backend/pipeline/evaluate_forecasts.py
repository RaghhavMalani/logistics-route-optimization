from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FEATURES_PATH = ROOT / "data" / "processed" / "features_daily.csv"
TFT_PATH = ROOT / "outputs" / "forecasts" / "tft_forecast.csv"
REPORT_DIR = ROOT / "outputs" / "reports"
REPORT_PATH = REPORT_DIR / "forecast_evaluation.json"


def mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred):
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def mape(y_true, y_pred):
    denom = np.maximum(np.abs(y_true), 1e-6)
    return float(np.mean(np.abs((y_true - y_pred) / denom)) * 100)


def main():
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(f"Missing {FEATURES_PATH}")

    if not TFT_PATH.exists():
        raise FileNotFoundError(f"Missing {TFT_PATH}")

    features = pd.read_csv(FEATURES_PATH)
    forecasts = pd.read_csv(TFT_PATH)

    target_col = "congestion_index"

    if target_col not in features.columns:
        raise ValueError(f"Expected {target_col} in features_daily.csv")

    pred_col = None
    for candidate in ["predicted_congestion", "q50", "congestionIndex"]:
        if candidate in forecasts.columns:
            pred_col = candidate
            break

    if pred_col is None:
        raise ValueError("Could not find prediction column in TFT forecast file.")

    q10_col = "q10" if "q10" in forecasts.columns else None
    q90_col = "q90" if "q90" in forecasts.columns else None

    latest_actual = (
        features.sort_values("date")
        .groupby("port_id", as_index=False)
        .tail(1)[["port_id", "date", target_col]]
        .rename(columns={target_col: "latest_actual_congestion"})
    )

    first_forecast = (
        forecasts.sort_values(["port_id", "horizon_day"] if "horizon_day" in forecasts.columns else ["port_id"])
        .groupby("port_id", as_index=False)
        .head(1)
    )

    merged = first_forecast.merge(latest_actual, on="port_id", how="inner")

    y_true = merged["latest_actual_congestion"].astype(float)
    y_pred = merged[pred_col].astype(float)

    report = {
        "note": "Evaluation compares next-step forecast against latest available actual congestion per port. This is a lightweight demo evaluation, not a full walk-forward backtest.",
        "rows_evaluated": int(len(merged)),
        "prediction_column": pred_col,
        "mae": round(mae(y_true, y_pred), 4),
        "rmse": round(rmse(y_true, y_pred), 4),
        "mape_percent": round(mape(y_true, y_pred), 4),
    }

    if q10_col and q90_col:
        q10 = merged[q10_col].astype(float)
        q90 = merged[q90_col].astype(float)
        coverage = ((y_true >= q10) & (y_true <= q90)).mean() * 100
        report["q10_q90_coverage_percent"] = round(float(coverage), 4)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
