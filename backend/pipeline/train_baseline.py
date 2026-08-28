from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUT_DIR = ROOT / "outputs" / "forecasts"

FEATURES_CSV = PROCESSED_DIR / "features_daily.csv"
FEATURES_PARQUET = PROCESSED_DIR / "features_daily.parquet"

HORIZON = 10
TARGET = "congestion_index"


def load_features() -> pd.DataFrame:
    if FEATURES_PARQUET.exists():
        df = pd.read_parquet(FEATURES_PARQUET)
    elif FEATURES_CSV.exists():
        df = pd.read_csv(FEATURES_CSV)
    else:
        raise FileNotFoundError(
            "Could not find data/processed/features_daily.parquet or .csv. "
            "Run backend/pipeline/build_features.py first."
        )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()
    df = df.sort_values(["port_id", "date"]).reset_index(drop=True)

    return df


def get_feature_columns(df: pd.DataFrame) -> List[str]:
    exclude = {
        "date",
        "target_date",
        "forecast_origin_date",
        "port_id",
        "port_code",

        # future labels — never use these as model inputs
        "y_congestion",
        "y_delay",

        # metadata columns from monthly DGQI aggregation
        "dwell_time_min",
        "dwell_time_max",
        "dwell_time_records",
    }

    feature_cols = [
        col for col in df.columns
        if col not in exclude
        and not col.startswith("y_")
        and pd.api.types.is_numeric_dtype(df[col])
    ]

    # horizon_day is a valid model feature because we are doing multi-horizon forecasting.
    if "horizon_day" not in feature_cols:
        feature_cols.append("horizon_day")

    return feature_cols


def build_supervised_frame(df: pd.DataFrame, horizon: int = HORIZON) -> pd.DataFrame:
    """
    Converts daily port features into supervised learning rows.

    For each port and date t:
        input features = values known at date t
        target = congestion_index at date t + horizon_day
    """
    rows = []

    for h in range(1, horizon + 1):
        temp = df.copy()
        temp["horizon_day"] = h

        temp["target_date"] = temp.groupby("port_id")["date"].shift(-h)
        temp["y_congestion"] = temp.groupby("port_id")[TARGET].shift(-h)
        temp["y_delay"] = temp.groupby("port_id")["delay_hours"].shift(-h)

        temp = temp.dropna(subset=["target_date", "y_congestion"]).copy()
        rows.append(temp)

    supervised = pd.concat(rows, ignore_index=True)
    supervised = supervised.sort_values(["port_id", "date", "horizon_day"]).reset_index(drop=True)

    return supervised


def make_quantile_model(quantile: float):
    """
    Creates a quantile regression model.
    HistGradientBoostingRegressor is fast and supports quantile loss.
    If unavailable, falls back to GradientBoostingRegressor.
    """
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor

        return HistGradientBoostingRegressor(
            loss="quantile",
            quantile=quantile,
            max_iter=250,
            max_depth=4,
            learning_rate=0.05,
            random_state=42,
        )
    except Exception:
        from sklearn.ensemble import GradientBoostingRegressor

        return GradientBoostingRegressor(
            loss="quantile",
            alpha=quantile,
            n_estimators=250,
            max_depth=3,
            learning_rate=0.05,
            random_state=42,
        )


def risk_level(value: float, q90: float) -> str:
    if value >= 70 or q90 >= 80:
        return "High"
    if value >= 45 or q90 >= 60:
        return "Medium"
    return "Low"


def train_and_forecast() -> pd.DataFrame:
    print("Loading clean feature table...")
    df = load_features()

    print("Building supervised multi-horizon training frame...")
    supervised = build_supervised_frame(df, HORIZON)

    feature_cols = get_feature_columns(supervised)

    model_cols = [c for c in feature_cols if c in supervised.columns]
    X = supervised[model_cols].to_numpy(dtype=float)
    y = supervised["y_congestion"].to_numpy(dtype=float)

    print(f"Training rows: {len(supervised):,}")
    print(f"Feature columns: {len(model_cols)}")
    print(f"Ports: {supervised['port_id'].nunique()}")
    print(f"Horizon: 1-{HORIZON} days")

    print("Training q10/q50/q90 baseline quantile models...")
    models = {
        0.1: make_quantile_model(0.1),
        0.5: make_quantile_model(0.5),
        0.9: make_quantile_model(0.9),
    }

    for q, model in models.items():
        print(f"  fitting q{int(q * 100)}...")
        model.fit(X, y)

    print("Building live inference frame from latest row per port...")
    latest = (
        df.sort_values(["port_id", "date"])
        .groupby("port_id", as_index=False)
        .tail(1)
        .copy()
    )

    inference_rows = []
    for _, row in latest.iterrows():
        for h in range(1, HORIZON + 1):
            r = row.copy()
            r["horizon_day"] = h
            r["forecast_origin_date"] = row["date"]
            r["target_date"] = row["date"] + pd.Timedelta(days=h)
            inference_rows.append(r)

    inf = pd.DataFrame(inference_rows)
    inf = inf.sort_values(["port_id", "horizon_day"]).reset_index(drop=True)

    X_inf = inf[model_cols].to_numpy(dtype=float)

    q10 = models[0.1].predict(X_inf)
    q50 = models[0.5].predict(X_inf)
    q90 = models[0.9].predict(X_inf)

    # Enforce quantile order row-wise.
    stacked = np.sort(np.vstack([q10, q50, q90]), axis=0)
    q10, q50, q90 = stacked[0], stacked[1], stacked[2]

    out = pd.DataFrame(
        {
            "port_id": inf["port_id"].values,
            "port_code": inf["port_code"].values,
            "forecast_origin_date": inf["forecast_origin_date"].values,
            "target_date": inf["target_date"].values,
            "horizon_day": inf["horizon_day"].values,
            "q10": q10,
            "q50": q50,
            "q90": q90,
            "predicted_congestion": q50,
            # Temporary simple delay proxy. TFT/decision layer can improve this later.
            "predicted_delay": q50 * 2.0,
            "model": "baseline",
        }
    )

    out["uncertainty_band"] = out["q90"] - out["q10"]
    out["risk_level"] = [
        risk_level(v, hi)
        for v, hi in zip(out["predicted_congestion"], out["q90"])
    ]

    # Confidence is higher when uncertainty is narrower and horizon is nearer.
    width_term = 1.0 - (out["uncertainty_band"] / 100.0).clip(0, 0.9)
    horizon_term = 1.0 - (out["horizon_day"] * 0.03)
    out["confidence_score"] = (width_term * horizon_term).clip(0.05, 0.97)

    round_cols = [
        "q10",
        "q50",
        "q90",
        "predicted_congestion",
        "predicted_delay",
        "uncertainty_band",
        "confidence_score",
    ]
    for col in round_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce").round(3)

    return out


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    forecast = train_and_forecast()

    out_path = OUTPUT_DIR / "baseline_forecast.csv"
    forecast.to_csv(out_path, index=False)

    print()
    print(f"Wrote {out_path}")
    print()
    print("Forecast summary")
    print("----------------")
    print(f"Rows: {len(forecast):,}")
    print(f"Ports: {forecast['port_id'].nunique()}")
    print(f"Horizon days: {forecast['horizon_day'].min()}-{forecast['horizon_day'].max()}")
    print()
    print("Model counts:")
    print(forecast["model"].value_counts())
    print()
    print("Sample:")
    print(forecast.head(20))


if __name__ == "__main__":
    main()