from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"

INPUT_CSV = PROCESSED_DIR / "features_daily.csv"
OUTPUT_CSV = PROCESSED_DIR / "features_daily_hsmm.csv"
OUTPUT_PARQUET = PROCESSED_DIR / "features_daily_hsmm.parquet"
REGIME_CSV = PROCESSED_DIR / "hsmm_regimes.csv"

# Make sure project root is importable so src.regimes.hsmm_model can load.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from src.regimes.hsmm_model import HSMMRegimeModel
except Exception as exc:
    raise ImportError(
        "Could not import src.regimes.hsmm_model.HSMMRegimeModel. "
        "Make sure the original HSMM model exists at src/regimes/hsmm_model.py "
        "and its dependencies are available."
    ) from exc


REGIME_CODE = {
    "NORMAL": 0,
    "CONGESTED": 1,
    "SEVERE": 2,
    "DISRUPTED": 2,
    "HIGHLY_DISRUPTED": 2,
}


def normalized(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)

    if values.isna().all():
        return pd.Series(0.0, index=series.index)

    values = values.fillna(values.median())

    lo = values.quantile(0.05)
    hi = values.quantile(0.95)

    if hi <= lo:
        return pd.Series(0.0, index=series.index)

    return ((values - lo) / (hi - lo)).clip(0, 1)


def ensure_hsmm_input_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    The original HSMMRegimeModel expects a specific set of operational/expert
    features through src.regimes.regime_features.select_hsmm_matrix.

    The clean rebuild has different feature names, so this adapter maps our
    clean daily features into the original HSMM feature schema.
    """
    out = df.copy()

    # Operational congestion proxies
    if "queue_proxy" not in out.columns:
        out["queue_proxy"] = normalized(out["congestion_index"])

    if "turnaround_proxy" not in out.columns:
        source = out["delay_hours"] if "delay_hours" in out.columns else out["congestion_index"]
        out["turnaround_proxy"] = normalized(source)

    if "throughput" not in out.columns:
        source = out["throughput_proxy"] if "throughput_proxy" in out.columns else 100 - out["congestion_index"]
        out["throughput"] = normalized(source)

    if "utilization" not in out.columns:
        out["utilization"] = normalized(out["congestion_index"])

    # Weather impact index
    weather_parts = []
    for col in ["wind_risk", "rain_risk", "wave_risk", "storm_risk"]:
        if col in out.columns:
            weather_parts.append(pd.to_numeric(out[col], errors="coerce").fillna(0))

    if "WxImpactIndex" not in out.columns:
        if weather_parts:
            out["WxImpactIndex"] = pd.concat(weather_parts, axis=1).max(axis=1).clip(0, 1)
        else:
            out["WxImpactIndex"] = 0.0

    # News/geopolitical/event proxies
    if "geo_risk_score" not in out.columns:
        if "news_rolling_risk" in out.columns:
            out["geo_risk_score"] = normalized(out["news_rolling_risk"])
        elif "news_sentiment_score" in out.columns:
            out["geo_risk_score"] = normalized(-pd.to_numeric(out["news_sentiment_score"], errors="coerce"))
        else:
            out["geo_risk_score"] = 0.0

    if "event_spike_score" not in out.columns:
        if "news_rolling_risk" in out.columns:
            out["event_spike_score"] = normalized(out["news_rolling_risk"])
        else:
            out["event_spike_score"] = out["geo_risk_score"]

    if "news_stress" not in out.columns:
        if "news_sentiment_score" in out.columns:
            out["news_stress"] = normalized(-pd.to_numeric(out["news_sentiment_score"], errors="coerce"))
        elif "news_rolling_risk" in out.columns:
            out["news_stress"] = normalized(out["news_rolling_risk"])
        else:
            out["news_stress"] = 0.0

    # Demand/trade proxies
    if "demand_pressure" not in out.columns:
        out["demand_pressure"] = 0.5

    if "vessel_density" not in out.columns:
        # Until satellite/AIS is merged, use congestion/utilization as a proxy.
        out["vessel_density"] = out["utilization"]

    if "oil_stress" not in out.columns:
        out["oil_stress"] = normalized(out["demand_pressure"])

    if "fx_stress" not in out.columns:
        if "trade_trend" in out.columns:
            out["fx_stress"] = normalized(-pd.to_numeric(out["trade_trend"], errors="coerce"))
        else:
            out["fx_stress"] = 0.5

    if "inflation_stress" not in out.columns:
        if "trade_connectivity" in out.columns:
            out["inflation_stress"] = normalized(out["trade_connectivity"])
        else:
            out["inflation_stress"] = 0.5

    required = [
        "queue_proxy",
        "turnaround_proxy",
        "WxImpactIndex",
        "geo_risk_score",
        "event_spike_score",
        "demand_pressure",
        "vessel_density",
        "throughput",
        "utilization",
        "oil_stress",
        "fx_stress",
        "inflation_stress",
        "news_stress",
    ]

    for col in required:
        out[col] = (
            pd.to_numeric(out[col], errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
        )

    return out


def main() -> None:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Missing {INPUT_CSV}. Run build_features.py first.")

    df = pd.read_csv(INPUT_CSV)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["port_id", "date"]).reset_index(drop=True)

    hsmm_panel = ensure_hsmm_input_columns(df)

    model = HSMMRegimeModel(n_states=3, smooth_window=3, seed=42)
    regimes = model.fit_predict(hsmm_panel)

    regimes["date"] = pd.to_datetime(regimes["date"])
    regimes = regimes.sort_values(["port_id", "date"]).reset_index(drop=True)

    regimes["regime_code"] = (
        regimes["regime_label"]
        .astype(str)
        .str.upper()
        .map(REGIME_CODE)
        .fillna(1)
        .astype(int)
    )

    merge_cols = [
        "port_id",
        "date",
        "regime_label",
        "regime_code",
        "p_normal",
        "p_congested",
        "p_severe",
        "days_in_state",
        "expected_remaining_days",
        "transition_risk",
        "regime_confidence",
    ]

    enriched = hsmm_panel.merge(
        regimes[merge_cols],
        on=["port_id", "date"],
        how="left",
    )

    required_regime_cols = [
        "regime_code",
        "p_normal",
        "p_congested",
        "p_severe",
        "days_in_state",
        "expected_remaining_days",
        "transition_risk",
        "regime_confidence",
    ]

    missing = [c for c in required_regime_cols if c not in enriched.columns]
    if missing:
        raise ValueError(f"Missing HSMM output columns after merge: {missing}")

    if enriched[required_regime_cols].isna().any().any():
        bad = enriched[required_regime_cols].isna().sum()
        raise ValueError(f"HSMM output contains NaNs:\n{bad}")

    # Save dates in CSV-friendly format.
    enriched["date"] = pd.to_datetime(enriched["date"]).dt.strftime("%Y-%m-%d")
    regimes["date"] = pd.to_datetime(regimes["date"]).dt.strftime("%Y-%m-%d")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(OUTPUT_CSV, index=False)
    regimes[merge_cols].to_csv(REGIME_CSV, index=False)

    try:
        enriched.to_parquet(OUTPUT_PARQUET, index=False)
    except Exception:
        pass

    print("HSMM model used: src.regimes.hsmm_model.HSMMRegimeModel")
    print(f"HSMM backend selected by model: {getattr(model, 'backend', 'unknown')}")
    print(f"Input: {INPUT_CSV}")
    print(f"Output: {OUTPUT_CSV}")
    print(f"Regimes: {REGIME_CSV}")
    print("Regime counts:")
    print(regimes["regime_label"].value_counts().to_string())
    print("Latest regime per port:")
    print(
        regimes.sort_values("date")
        .groupby("port_id")
        .tail(1)[
            [
                "port_id",
                "date",
                "regime_label",
                "p_normal",
                "p_congested",
                "p_severe",
                "days_in_state",
                "expected_remaining_days",
                "transition_risk",
                "regime_confidence",
            ]
        ]
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
