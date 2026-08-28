from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

FEATURES_PATH = ROOT / "data" / "processed" / "features_daily.csv"
RAW_NEWS_PATH = ROOT / "data" / "raw" / "maritime_news_preprocessed.csv"
FORECAST_CACHE_PATH = ROOT / "data" / "cache" / "forecast_by_port.json"

CACHE_DIR = ROOT / "data" / "cache"
WEATHER_BY_PORT_PATH = CACHE_DIR / "weather_by_port.json"
WEATHER_INTEL_PATH = CACHE_DIR / "weather_intelligence.json"
NEWS_BUNDLE_PATH = CACHE_DIR / "news_bundle.json"


PORT_NAMES = {
    "INMAA": "Chennai",
    "INNSA": "JNPT / Nhava Sheva",
    "INMUN": "Mundra",
    "INCOK": "Cochin",
    "INHAL": "Haldia",
    "INHZR": "Hazira",
    "INIXY": "Deendayal / Kandla",
    "INKAT": "Kattupalli",
    "INKRI": "Krishnapatnam",
    "INCCU": "Kolkata",
    "INNML": "New Mangalore",
    "INTUT": "Tuticorin",
    "INVTZ": "Visakhapatnam",
}


def clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def severity_from_risk(value: float) -> str:
    if value >= 0.75:
        return "severe"
    if value >= 0.55:
        return "elevated"
    if value >= 0.35:
        return "watch"
    return "normal"


def load_features() -> pd.DataFrame:
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(
            f"{FEATURES_PATH} not found. Run build_features.py first."
        )

    df = pd.read_csv(FEATURES_PATH)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_forecast_cache() -> dict:
    if not FORECAST_CACHE_PATH.exists():
        return {}

    with open(FORECAST_CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def top_tft_risk_ports(limit: int = 5) -> list[str]:
    cache = load_forecast_cache()
    scores = []

    for port_code, rows in cache.items():
        if not rows:
            continue
        peak = max(float(r.get("congestionIndex", 0.0)) for r in rows)
        scores.append((port_code, peak))

    scores.sort(key=lambda x: x[1], reverse=True)
    return [code for code, _ in scores[:limit]]


def build_weather_cache(features: pd.DataFrame) -> tuple[dict, dict]:
    latest = (
        features.sort_values("date")
        .groupby("port_code", as_index=False)
        .tail(1)
    )

    weather_by_port: dict[str, dict] = {}

    for _, row in latest.iterrows():
        code = str(row["port_code"]).upper()

        wind_risk = clip01(row.get("wind_risk", 0.0))
        rain_risk = clip01(row.get("rain_risk", 0.0))
        wave_risk = clip01(row.get("wave_risk", 0.0))
        storm_risk = clip01(row.get("storm_risk", 0.0))
        confidence = clip01(row.get("weather_confidence", 0.75))

        impact = max(wind_risk, rain_risk, wave_risk, storm_risk)

        weather_by_port[code] = {
            "portCode": code,
            "timestamp": pd.to_datetime(row["date"]).strftime("%Y-%m-%d"),
            "windKnots": round(8 + wind_risk * 28, 1),
            "gustKnots": round(12 + wind_risk * 36, 1),
            "windDirection": "WNW" if wind_risk >= 0.5 else "SW",
            "rainfallMm24h": round(rain_risk * 80, 1),
            "precipRateMmH": round(rain_risk * 8, 1),
            "waveHeightM": round(0.5 + wave_risk * 3.5, 1),
            "visibilityKm": round(max(2.0, 12.0 - rain_risk * 8.0), 1),
            "cycloneRisk7d": round(storm_risk, 3),
            "seaState": "Rough" if wave_risk >= 0.65 else "Moderate" if wave_risk >= 0.35 else "Calm",
            "impactScore": round(impact, 3),
            "persistenceScore": round((wind_risk + rain_risk + wave_risk) / 3, 3),
            "shockSigma": round(storm_risk, 3),
            "advisory": (
                "Weather risk elevated; monitor pilotage and berth windows."
                if impact >= 0.45
                else "Weather risk normal; continue standard monitoring."
            ),
            "confidence": round(confidence, 3),
            "dataSource": "data/processed/features_daily.csv",
        }

    mean_wind = latest["wind_risk"].mean()
    mean_rain = latest["rain_risk"].mean()
    mean_wave = latest["wave_risk"].mean()
    mean_storm = latest["storm_risk"].mean()

    weather_intelligence = {
        "monsoon": {
            "status": "ACTIVE" if latest["is_monsoon"].max() == 1 else "INACTIVE",
            "risk": severity_from_risk(float(mean_rain)),
            "description": "Derived from processed weather risk features used by the forecasting pipeline.",
        },
        "cyclone": {
            "probability72h": round(float(mean_storm), 3),
            "riskWindow": "Feature-derived operational watch window",
        },
        "swell": {
            "heightM": round(0.5 + float(mean_wave) * 3.5, 1),
            "direction": "WNW",
        },
        "operationalImpact": {
            "pilotage": "restricted windows possible" if mean_storm >= 0.4 else "normal",
            "berthProductivity": f"{round(-15 * float(mean_wave), 1)}%",
            "outerAnchorage": "moderate queue pressure" if mean_wind >= 0.4 else "normal",
        },
        "dataSource": "data/processed/features_daily.csv",
    }

    return weather_by_port, weather_intelligence


def build_news_cache(features: pd.DataFrame) -> dict:
    top_ports = top_tft_risk_ports(limit=5) or ["INMAA", "INNSA", "INMUN"]

    if RAW_NEWS_PATH.exists():
        news = pd.read_csv(RAW_NEWS_PATH)
        news["Date"] = pd.to_datetime(news["Date"])
        news = news.sort_values("Date").tail(8)
    else:
        news = pd.DataFrame()

    events = []

    for idx, row in enumerate(news.itertuples(index=False), start=1):
        date = pd.to_datetime(getattr(row, "Date"))
        sentiment = float(getattr(row, "sentiment"))
        rolling = float(getattr(row, "sentiment_rolling14", sentiment))

        risk_score = clip01(((-sentiment) + 2.5) / 5.0)
        severity = severity_from_risk(risk_score)

        affected = top_ports[:3] if risk_score >= 0.45 else top_ports[:2]

        events.append(
            {
                "id": f"NLP-{date.strftime('%Y%m%d')}-{idx}",
                "timestamp": date.strftime("%Y-%m-%d"),
                "source": "Historical maritime sentiment aggregate",
                "tag": "NLP",
                "entity": "NATIONAL_MARITIME",
                "severity": severity,
                "sentiment": round(sentiment, 3),
                "rollingSentiment14": round(rolling, 3),
                "text": (
                    f"Daily maritime news sentiment index={sentiment:.2f}; "
                    f"rolling14={rolling:.2f}. Affected ports are selected from current TFT risk ranking."
                ),
                "affectedPorts": affected,
                "confidence": 0.76,
                "dataSource": "data/raw/maritime_news_preprocessed.csv",
            }
        )

    if not events:
        latest = (
            features.sort_values("date")
            .groupby("port_code", as_index=False)
            .tail(1)
        )
        risk = float(latest["news_sentiment_score"].mean())
        events.append(
            {
                "id": "NLP-FEATURE-LATEST",
                "timestamp": pd.to_datetime(latest["date"].max()).strftime("%Y-%m-%d"),
                "source": "Processed NLP risk feature",
                "tag": "NLP",
                "entity": "NATIONAL_MARITIME",
                "severity": severity_from_risk(risk),
                "sentiment": round(1 - 2 * risk, 3),
                "text": "News risk derived from processed feature table.",
                "affectedPorts": top_ports[:3],
                "confidence": 0.72,
                "dataSource": "data/processed/features_daily.csv",
            }
        )

    alerts = []
    for idx, code in enumerate(top_ports[:5], start=1):
        alerts.append(
            {
                "id": f"AL-TFT-{idx:03d}",
                "portCode": code,
                "severity": "severe" if idx <= 2 else "watch",
                "text": f"{PORT_NAMES.get(code, code)} is among top TFT-ranked risk ports; review ETA buffer.",
                "ts": "TFT",
                "dataSource": "data/cache/forecast_by_port.json",
            }
        )

    return {
        "events": events,
        "alerts": alerts,
        "summary": {
            "totalEvents": len(events),
            "totalAlerts": len(alerts),
            "negativeEvents": sum(1 for e in events if float(e["sentiment"]) < 0),
            "averageConfidence": round(
                sum(float(e["confidence"]) for e in events) / len(events), 3
            ),
            "dataSource": "raw news sentiment + TFT risk ranking",
        },
    }


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Wrote {path}")


def main() -> None:
    features = load_features()

    weather_by_port, weather_intelligence = build_weather_cache(features)
    news_bundle = build_news_cache(features)

    write_json(WEATHER_BY_PORT_PATH, weather_by_port)
    write_json(WEATHER_INTEL_PATH, weather_intelligence)
    write_json(NEWS_BUNDLE_PATH, news_bundle)

    print()
    print("Support cache export complete.")
    print(f"Weather ports: {len(weather_by_port)}")
    print(f"News events: {len(news_bundle['events'])}")
    print(f"News alerts: {len(news_bundle['alerts'])}")


if __name__ == "__main__":
    main()
