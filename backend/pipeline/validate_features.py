from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"

FEATURES_CSV = PROCESSED_DIR / "features_daily.csv"
FEATURES_PARQUET = PROCESSED_DIR / "features_daily.parquet"

REQUIRED_COLUMNS = [
    "date",
    "port_id",
    "port_code",
    "time_idx",
    "congestion_index",
    "delay_hours",
    "dwell_time",
    "wind_risk",
    "rain_risk",
    "wave_risk",
    "storm_risk",
    "weather_confidence",
    "news_sentiment_score",
    "demand_pressure",
    "trade_trend",
    "month",
    "day_of_week",
    "is_monsoon",
]

MIN_ROWS_PER_PORT = 90


def load_features() -> pd.DataFrame:
    if FEATURES_PARQUET.exists():
        return pd.read_parquet(FEATURES_PARQUET)
    if FEATURES_CSV.exists():
        return pd.read_csv(FEATURES_CSV)
    raise FileNotFoundError("No features_daily.parquet or features_daily.csv found.")


def main() -> None:
    df = load_features()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    print("Validating feature table...")
    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns):,}")
    print(f"Ports: {df['port_id'].nunique()}")
    print(f"Date range: {df['date'].min()} → {df['date'].max()}")
    print()

    missing_required = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_required:
        raise ValueError(f"Missing required columns: {missing_required}")

    if df["date"].isna().any():
        raise ValueError("Some rows have invalid dates.")

    duplicate_rows = df.duplicated(["port_id", "date"]).sum()
    if duplicate_rows:
        raise ValueError(f"Found duplicate port/date rows: {duplicate_rows}")

    rows_per_port = df.groupby("port_id").size().sort_values()
    weak_ports = rows_per_port[rows_per_port < MIN_ROWS_PER_PORT]

    if not weak_ports.empty:
        raise ValueError(
            f"Some ports have less than {MIN_ROWS_PER_PORT} rows:\n{weak_ports}"
        )

    model_cols = [
        c for c in df.columns
        if c not in ["date", "port_id", "port_code"]
    ]

    nan_counts = df[model_cols].isna().sum()
    nan_counts = nan_counts[nan_counts > 0]

    if not nan_counts.empty:
        raise ValueError(f"NaN values found:\n{nan_counts}")

    inf_counts = {}
    for col in model_cols:
        vals = pd.to_numeric(df[col], errors="coerce")
        count = np.isinf(vals).sum()
        if count:
            inf_counts[col] = int(count)

    if inf_counts:
        raise ValueError(f"Infinite values found: {inf_counts}")

    target = pd.to_numeric(df["congestion_index"], errors="coerce")

    if target.isna().any():
        raise ValueError("congestion_index has missing values.")

    if target.nunique() < 5:
        raise ValueError(
            "congestion_index has too few unique values. "
            "The model will not learn meaningful variation."
        )

    report_path = PROCESSED_DIR / "feature_validation_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("Feature validation report\n")
        f.write("=========================\n\n")
        f.write(f"Rows: {len(df):,}\n")
        f.write(f"Columns: {len(df.columns):,}\n")
        f.write(f"Ports: {df['port_id'].nunique()}\n")
        f.write(f"Date range: {df['date'].min()} to {df['date'].max()}\n\n")
        f.write("Rows per port:\n")
        f.write(rows_per_port.to_string())
        f.write("\n\nTarget summary:\n")
        f.write(target.describe().to_string())

    print("Validation passed.")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()