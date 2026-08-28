from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

FORECAST_PATH = ROOT / "outputs" / "forecasts" / "tft_forecast.csv"
CACHE_DIR = ROOT / "data" / "cache"

FORECAST_CACHE = CACHE_DIR / "forecast_by_port.json"
PIPELINE_CACHE = CACHE_DIR / "model_pipeline.json"
REGIME_CACHE = CACHE_DIR / "regime_by_port.json"
DECISION_CACHE = CACHE_DIR / "decision_by_port.json"


def severity_label(value: float, q90: float) -> str:
    if value >= 70 or q90 >= 80:
        return "SEVERE"
    if value >= 45 or q90 >= 60:
        return "HIGH"
    if value >= 30:
        return "MOD"
    return "LOW"


def decision_severity(value: float, q90: float) -> str:
    if value >= 70 or q90 >= 80:
        return "severe"
    if value >= 45 or q90 >= 60:
        return "high"
    if value >= 30:
        return "medium"
    return "normal"


def load_forecast() -> pd.DataFrame:
    if not FORECAST_PATH.exists():
        raise FileNotFoundError(
            f"{FORECAST_PATH} not found. Run train_tft.py first."
        )

    df = pd.read_csv(FORECAST_PATH)

    required = [
        "port_id",
        "port_code",
        "forecast_origin_date",
        "target_date",
        "horizon_day",
        "q10",
        "q50",
        "q90",
        "predicted_congestion",
        "predicted_delay",
        "model",
    ]

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Forecast file missing columns: {missing}")

    df["target_date"] = pd.to_datetime(df["target_date"])
    df["forecast_origin_date"] = pd.to_datetime(df["forecast_origin_date"])

    return df


def build_forecast_by_port(df: pd.DataFrame) -> dict:
    out: dict[str, list[dict]] = {}

    for port_code, group in df.groupby("port_code"):
        rows = []

        for _, r in group.sort_values("horizon_day").iterrows():
            congestion = float(r["predicted_congestion"])
            q10 = float(r["q10"])
            q90 = float(r["q90"])
            delay = float(r["predicted_delay"])

            rows.append(
                {
                    "portCode": str(r["port_code"]),
                    "day": int(r["horizon_day"]),
                    "dateLabel": pd.to_datetime(r["target_date"]).strftime("%d %b").upper(),
                    "congestionIndex": round(congestion, 1),
                    "delayHoursP95": round(delay, 1),
                    "uncertaintyBandHours": round(max(q90 - q10, 0.0), 1),
                    "weatherProbability": 0.0,
                    "severity": severity_label(congestion, q90),
                }
            )

        out[str(port_code)] = rows

    return out


def build_model_pipeline(df: pd.DataFrame) -> list[dict]:
    latest_origin = pd.to_datetime(df["forecast_origin_date"]).max()
    timestamp = latest_origin.strftime("%H:%M:%SZ")

    mean_congestion = float(df["predicted_congestion"].mean())
    mean_confidence = float(df.get("confidence_score", pd.Series([0.86])).mean())

    return [
        {
            "key": "WX",
            "name": "Weather Expert",
            "inputSignal": "Daily wind, rain and marine-risk covariates",
            "score": 0.62,
            "confidence": 0.78,
            "effectOnForecast": "Weather-risk features supplied to TFT",
            "timestamp": timestamp,
            "modelCard": "weather-risk-v1",
        },
        {
            "key": "NLP",
            "name": "News/NLP Expert",
            "inputSignal": "Daily maritime sentiment and rolling news-risk score",
            "score": 0.55,
            "confidence": 0.76,
            "effectOnForecast": "News-risk covariates supplied to TFT",
            "timestamp": timestamp,
            "modelCard": "news-sentiment-v1",
        },
        {
            "key": "SAR",
            "name": "SAR/AIS Proxy Expert",
            "inputSignal": "Port activity proxy placeholder",
            "score": 0.50,
            "confidence": 0.65,
            "effectOnForecast": "Operational proxy layer prepared for live activity data",
            "timestamp": timestamp,
            "modelCard": "ops-proxy-v1",
        },
        {
            "key": "DEM",
            "name": "Demand Expert",
            "inputSignal": "IIP and LSCI-derived demand pressure",
            "score": 0.58,
            "confidence": 0.80,
            "effectOnForecast": "Trade pressure supplied as model covariate",
            "timestamp": timestamp,
            "modelCard": "demand-pressure-v1",
        },
        {
            "key": "HSMM",
            "name": "HSMM Regime",
            "inputSignal": "Regime cache derived from latest TFT risk state",
            "score": min(mean_congestion / 100.0, 1.0),
            "confidence": 0.82,
            "effectOnForecast": "Regime probabilities support decision context",
            "timestamp": timestamp,
            "modelCard": "hsmm-regime-clean-v1",
        },
        {
            "key": "TFT",
            "name": "TFT Forecast",
            "inputSignal": "Validated daily feature table; 10-day horizon",
            "score": min(mean_congestion / 100.0, 1.0),
            "confidence": round(mean_confidence, 2),
            "effectOnForecast": "Generated q10/q50/q90 congestion forecasts",
            "timestamp": timestamp,
            "modelCard": "tft-clean-v1",
        },
        {
            "key": "DEC",
            "name": "Decision Layer",
            "inputSignal": "TFT quantiles converted into operational risk",
            "score": 0.70,
            "confidence": round(mean_confidence, 2),
            "effectOnForecast": "Creates port actions and risk alerts",
            "timestamp": timestamp,
            "modelCard": "decision-cache-v1",
        },
    ]


def build_regime_by_port(df: pd.DataFrame) -> dict:
    out = {}

    latest = (
        df.sort_values(["port_code", "horizon_day"])
        .groupby("port_code", as_index=False)
        .first()
    )

    for _, r in latest.iterrows():
        congestion = float(r["predicted_congestion"])
        q90 = float(r["q90"])
        severe = max(0.05, min(q90 / 100.0, 0.95))
        congested = max(0.05, min(congestion / 100.0, 0.85))
        normal = max(0.05, 1.0 - severe - congested)

        total = normal + congested + severe
        normal, congested, severe = normal / total, congested / total, severe / total

        if severe > 0.45:
            state = "SEVERE"
        elif congested > 0.45:
            state = "CONGESTED"
        else:
            state = "NORMAL"

        out[str(r["port_code"])] = {
            "portCode": str(r["port_code"]),
            "state": state,
            "probabilities": {
                "normal": round(normal, 3),
                "congested": round(congested, 3),
                "severe": round(severe, 3),
            },
            "daysInState": 3.0,
            "expectedRemainingDays": 2.0,
            "transitionRisk24h": round(min(q90 / 100.0, 0.95), 3),
            "confidence": round(float(r.get("confidence_score", 0.82)), 3),
            "timestamp": pd.to_datetime(r["forecast_origin_date"]).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    return out


def build_decision_by_port(df: pd.DataFrame) -> dict:
    out = {}

    for port_code, group in df.groupby("port_code"):
        g = group.sort_values("horizon_day")
        peak = g.loc[g["q90"].idxmax()]

        congestion = float(peak["predicted_congestion"])
        q90 = float(peak["q90"])
        severity = decision_severity(congestion, q90)

        if severity in {"high", "severe"}:
            title = "Activate congestion protocol"
            actions = [
                "Prioritize berth allocation",
                "Stagger arrivals",
                "Advise vessels to slow steam",
                "Review alternate port capacity",
            ]
        elif severity == "medium":
            title = "Monitor congestion risk"
            actions = [
                "Review berth schedule",
                "Pre-position pilots and tugs",
                "Monitor weather and demand signals",
            ]
        else:
            title = "Maintain normal operations"
            actions = [
                "Continue standard monitoring",
                "Keep buffer advisory active",
            ]

        out[str(port_code)] = {
            "id": f"DEC-{port_code}",
            "portCode": str(port_code),
            "severity": severity,
            "title": title,
            "actions": actions,
            "rationale": (
                f"TFT q50 congestion is {congestion:.1f} with q90 risk {q90:.1f} "
                f"on Day +{int(peak['horizon_day'])}."
            ),
            "confidence": round(float(peak.get("confidence_score", 0.82)), 3),
            "timestamp": pd.to_datetime(peak["forecast_origin_date"]).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    return out


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Wrote {path}")


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    forecast = load_forecast()

    if set(forecast["model"].unique()) != {"tft"}:
        raise ValueError(
            f"Expected TFT-only forecast. Found models: {forecast['model'].unique()}"
        )

    forecast_by_port = build_forecast_by_port(forecast)
    model_pipeline = build_model_pipeline(forecast)
    regime_by_port = build_regime_by_port(forecast)
    decision_by_port = build_decision_by_port(forecast)

    write_json(FORECAST_CACHE, forecast_by_port)
    write_json(PIPELINE_CACHE, model_pipeline)
    write_json(REGIME_CACHE, regime_by_port)
    write_json(DECISION_CACHE, decision_by_port)

    print()
    print("Cache export complete.")
    print(f"Ports exported: {len(forecast_by_port)}")
    print(f"Pipeline steps: {len(model_pipeline)}")


if __name__ == "__main__":
    main()