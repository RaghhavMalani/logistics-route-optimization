from __future__ import annotations

from pathlib import Path
import calendar

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"


DGQI_FILE = RAW_DIR / "DGQI_merged_2020_2022.csv"
WEATHER_FILE = RAW_DIR.parent / "preprocessed" / "weather_preprocessed_2020_2025.csv"
NEWS_FILE = RAW_DIR / "maritime_news_preprocessed.csv"
ECON_FILE = RAW_DIR / "final_economic_features.csv"


PORT_NAME_MAP = {
    "APSEZ": ("MUNDRA", "INMUN"),
    "CHENNAI": ("CHENNAI", "INMAA"),
    "COCHIN": ("COCHIN", "INCOK"),
    "HALDIA": ("HALDIA", "INHAL"),
    "HAZIRA": ("HAZIRA", "INHZR"),
    "JNPT": ("JNPT", "INNSA"),
    "KANDLA": ("DEENDAYAL", "INIXY"),
    "KATTUPALLI": ("KATTUPALLI", "INKAT"),
    "KOLKATA": ("KOLKATA", "INCCU"),
    "KRISHNAPATNAM": ("KRISHNAPATNAM", "INKRI"),
    "NMPT": ("NEW_MANGALORE", "INNML"),
    "TUTICORIN": ("TUTICORIN", "INTUT"),
    "VIZAG": ("VIZAG", "INVTZ"),
}


MONTH_MAP = {
    month.upper(): i
    for i, month in enumerate(calendar.month_name)
    if month
}


def risk_from_zscore(series: pd.Series) -> pd.Series:
    """
    Your weather columns are standardized/z-scored, not raw physical units.
    This converts them into a stable 0..1 risk proxy.
    """
    s = pd.to_numeric(series, errors="coerce")
    return ((s + 2.0) / 4.0).clip(0.0, 1.0)


def load_dgqi_daily() -> pd.DataFrame:
    df = pd.read_csv(DGQI_FILE)

    df["portName"] = df["portName"].astype(str).str.upper().str.strip()
    df = df[~df["portName"].str.contains("REGION AVG", na=False)].copy()

    df["mapped"] = df["portName"].map(PORT_NAME_MAP)
    df = df.dropna(subset=["mapped"]).copy()

    df["port_id"] = df["mapped"].apply(lambda x: x[0])
    df["port_code"] = df["mapped"].apply(lambda x: x[1])

    df["month_num"] = df["month"].astype(str).str.upper().str.strip().map(MONTH_MAP)
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["dwellTime"] = pd.to_numeric(df["dwellTime"], errors="coerce")

    df = df.dropna(subset=["year", "month_num", "dwellTime"]).copy()

    monthly = (
        df.groupby(["port_id", "port_code", "year", "month_num"], as_index=False)
        .agg(
            dwell_time=("dwellTime", "mean"),
            dwell_time_min=("dwellTime", "min"),
            dwell_time_max=("dwellTime", "max"),
            dwell_time_records=("dwellTime", "count"),
        )
    )

    rows = []
    for _, row in monthly.iterrows():
        year = int(row["year"])
        month = int(row["month_num"])

        start = pd.Timestamp(year=year, month=month, day=1)
        end = start + pd.offsets.MonthEnd(0)

        for date in pd.date_range(start, end, freq="D"):
            dwell = float(row["dwell_time"])

            rows.append(
                {
                    "date": date,
                    "port_id": row["port_id"],
                    "port_code": row["port_code"],
                    "dwell_time": dwell,
                    "delay_hours": dwell,
                    # 0..100 congestion proxy from dwell time.
                    # We cap very high dwell time so one extreme does not dominate training.
                    "congestion_index": float(np.clip(dwell, 0, 200) / 2.0),
                    # Basic proxy for now. Later, real throughput comes from PortWatch activity.
                    "throughput_proxy": float(np.clip(100 - (np.clip(dwell, 0, 200) / 2.0), 0, 100)),
                    "dwell_time_min": row["dwell_time_min"],
                    "dwell_time_max": row["dwell_time_max"],
                    "dwell_time_records": row["dwell_time_records"],
                }
            )

    return pd.DataFrame(rows)


def load_weather_daily() -> pd.DataFrame:
    df = pd.read_csv(WEATHER_FILE)
    df = df.rename(columns={"Date": "date"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()

    for col in df.columns:
        if col != "date":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["wind_risk"] = risk_from_zscore(df.get("WindSpeed", 0.0))
    df["rain_risk"] = risk_from_zscore(df.get("Rainfall", 0.0))

    # No direct wave column exists, so create a conservative marine-risk proxy.
    df["wave_risk"] = (0.6 * df["wind_risk"] + 0.4 * df["rain_risk"]).clip(0.0, 1.0)

    # Storm risk is high only when wind/rain proxy is high.
    df["storm_risk"] = np.where(
        (df["wind_risk"] > 0.75) | (df["rain_risk"] > 0.80),
        1.0,
        0.0,
    )

    df["weather_confidence"] = 0.75

    keep = [
        "date",
        "Temperature",
        "Rainfall",
        "WindSpeed",
        "temp_rolling7",
        "rain_rolling7",
        "wind_rolling7",
        "wind_risk",
        "rain_risk",
        "wave_risk",
        "storm_risk",
        "weather_confidence",
    ]

    return df[[c for c in keep if c in df.columns]].copy()


def load_news_daily() -> pd.DataFrame:
    df = pd.read_csv(NEWS_FILE)
    df = df.rename(columns={"Date": "date"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()

    for col in df.columns:
        if col != "date":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Negative sentiment should increase risk.
    # tanh keeps extreme standardized values stable.
    sentiment = pd.to_numeric(df["sentiment"], errors="coerce")
    df["news_sentiment_score"] = ((-np.tanh(sentiment)) + 1.0) / 2.0

    if "sentiment_rolling14" in df.columns:
        rolling = pd.to_numeric(df["sentiment_rolling14"], errors="coerce")
        df["news_rolling_risk"] = ((-np.tanh(rolling)) + 1.0) / 2.0
    else:
        df["news_rolling_risk"] = df["news_sentiment_score"]

    keep = [
        "date",
        "sentiment",
        "sentiment_lag7",
        "sentiment_lag14",
        "sentiment_lag28",
        "sentiment_rolling14",
        "news_sentiment_score",
        "news_rolling_risk",
    ]

    return df[[c for c in keep if c in df.columns]].copy()


def load_economic_daily() -> pd.DataFrame:
    df = pd.read_csv(ECON_FILE)
    df = df.rename(columns={"Date": "date"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()

    for col in df.columns:
        if col != "date":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # IIP and LSCI are standardized. Higher values can mean higher trade pressure.
    iip = pd.to_numeric(df.get("IIP_Value", 0.0), errors="coerce")
    lsci = pd.to_numeric(df.get("Global_LSCI", 0.0), errors="coerce")

    df["demand_pressure"] = ((np.tanh(iip) + 1.0) / 2.0).clip(0.0, 1.0)
    df["trade_connectivity"] = ((np.tanh(lsci) + 1.0) / 2.0).clip(0.0, 1.0)

    if "IIP_lag7" in df.columns:
        df["trade_trend"] = (df["IIP_Value"] - df["IIP_lag7"]).fillna(0.0)
    else:
        df["trade_trend"] = 0.0

    keep = [
        "date",
        "Global_LSCI",
        "LSCI_lag7",
        "LSCI_lag14",
        "LSCI_lag28",
        "LSCI_rolling14",
        "IIP_Value",
        "IIP_lag7",
        "IIP_lag14",
        "IIP_lag28",
        "IIP_rolling14",
        "demand_pressure",
        "trade_connectivity",
        "trade_trend",
    ]

    return df[[c for c in keep if c in df.columns]].copy()


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    df["date"] = pd.to_datetime(df["date"])

    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["day_of_week"] = df["date"].dt.dayofweek
    df["day_of_month"] = df["date"].dt.day

    # India monsoon months: June to September.
    df["is_monsoon"] = df["month"].isin([6, 7, 8, 9]).astype(int)

    return df


def clean_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    protected = {"date", "port_id", "port_code"}

    numeric_cols = [c for c in df.columns if c not in protected]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col].replace([np.inf, -np.inf], np.nan)

    # First fill by date-wise values when possible, then global medians.
    for col in numeric_cols:
        df[col] = df.groupby("date")[col].transform(lambda s: s.fillna(s.median()))
        median = df[col].median()
        if pd.isna(median):
            median = 0.0
        df[col] = df[col].fillna(median)

    return df


def build_features() -> pd.DataFrame:
    print("Loading DGQI target data...")
    observed = load_dgqi_daily()

    print("Loading weather data...")
    weather = load_weather_daily()

    print("Loading news data...")
    news = load_news_daily()

    print("Loading economic data...")
    econ = load_economic_daily()

    print("Merging daily features...")
    df = observed.merge(weather, on="date", how="left")
    df = df.merge(news, on="date", how="left")
    df = df.merge(econ, on="date", how="left")

    df = add_calendar_features(df)
    df = clean_numeric_columns(df)

    df = df.sort_values(["port_id", "date"]).reset_index(drop=True)

    # Add a per-port time index for sequence models.
    df["time_idx"] = df.groupby("port_id").cumcount()

    # Final safety checks.
    model_cols = [c for c in df.columns if c not in ["date", "port_id", "port_code"]]
    bad = df[model_cols].isna().sum()
    bad = bad[bad > 0]

    if not bad.empty:
        raise ValueError(f"NaNs remain after cleaning:\n{bad}")

    return df


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    features = build_features()

    csv_path = PROCESSED_DIR / "features_daily.csv"
    parquet_path = PROCESSED_DIR / "features_daily.parquet"

    features.to_csv(csv_path, index=False)

    try:
        features.to_parquet(parquet_path, index=False)
        print(f"Wrote {parquet_path}")
    except Exception as exc:
        print(f"Could not write parquet: {exc}")
        print("CSV was still written successfully.")

    print(f"Wrote {csv_path}")
    print()
    print("Feature table summary")
    print("---------------------")
    print(f"Rows: {len(features):,}")
    print(f"Ports: {features['port_id'].nunique()}")
    print(f"Date range: {features['date'].min()} → {features['date'].max()}")
    print()
    print("Rows per port:")
    print(features.groupby("port_id").size().sort_values(ascending=False))


if __name__ == "__main__":
    main()