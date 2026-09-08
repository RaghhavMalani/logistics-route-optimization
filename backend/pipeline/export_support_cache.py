"""Export the weather and event caches the terminal renders.

The previous version of this exporter reverse-engineered physical weather values
out of risk scores -- ``windKnots = 8 + wind_risk * 28`` -- and presented the
result as measurement. This version publishes the measured Open-Meteo values the
weather expert actually consumed, alongside the risk decomposition, and marks a
field ``null`` when the observation genuinely does not exist.

Written into ``data/cache/``:

    weather_by_port.json       measured conditions + risk decomposition per port
    weather_intelligence.json  national marine synthesis
    news_bundle.json           traceable maritime events and port alerts
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.utils import port_registry

ROOT = Path(__file__).resolve().parents[2]
EXPERT_DIR = ROOT / "outputs" / "expert_features"
FORECAST_DIR = ROOT / "outputs" / "forecasts"
CACHE_DIR = ROOT / "data" / "cache"

OBSERVATIONS_PATH = EXPERT_DIR / "weather_observations.csv"
WEATHER_FEATURES_PATH = EXPERT_DIR / "weather_features.csv"
WEATHER_FORECAST_PATH = EXPERT_DIR / "weather_forecast_features.csv"
PERSISTENCE_PATH = EXPERT_DIR / "weather_persistence_features.csv"
NEWS_FEATURES_PATH = EXPERT_DIR / "news_features.csv"
DECISION_PATH = FORECAST_DIR / "decisions.csv"

WEATHER_BY_PORT_PATH = CACHE_DIR / "weather_by_port.json"
WEATHER_INTEL_PATH = CACHE_DIR / "weather_intelligence.json"
NEWS_BUNDLE_PATH = CACHE_DIR / "news_bundle.json"


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    print(f"Wrote {path}")


def _opt(value, digits: int | None = None):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return round(result, digits) if digits is not None else result


def _iso(value) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.isoformat()


def _latest_per_port(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "date" not in frame:
        return frame
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out.sort_values(["port_id", "date"]).groupby("port_id", as_index=False).tail(1)


def _sea_state(wave_height: float | None) -> str | None:
    if wave_height is None:
        return None
    if wave_height >= 2.5:
        return "Rough"
    if wave_height >= 1.25:
        return "Moderate"
    return "Slight"


def _advisory(impact: float | None, regime: str | None) -> str:
    if impact is None:
        return "No measured marine weather for this port in the current run."
    if regime == "PERSISTENT":
        return ("Sustained weather disruption: plan multi-day berth windows and "
                "stagger arrivals rather than absorbing a single bad shift.")
    if impact >= 0.6:
        return "High weather impact: confirm safe-berthing windows and pilotage."
    if impact >= 0.35:
        return "Moderate weather impact: monitor pilotage and crane operations."
    return "Weather risk normal: continue standard monitoring."


# ---------------------------------------------------------------------------
def build_weather_cache() -> tuple[dict, dict]:
    """Measured conditions plus the risk decomposition the model actually used."""
    observations = _latest_per_port(_read(OBSERVATIONS_PATH))
    features = _latest_per_port(_read(WEATHER_FEATURES_PATH))
    persistence = _latest_per_port(_read(PERSISTENCE_PATH))
    forecast = _read(WEATHER_FORECAST_PATH)

    if features.empty:
        return {}, {"available": False,
                    "reason": "No weather features were produced in this run."}

    obs_by_port = {str(r["port_id"]): r for _, r in observations.iterrows()}
    pers_by_port = {str(r["port_id"]): r for _, r in persistence.iterrows()}

    forward_by_port: dict[str, list] = {}
    if not forecast.empty and "WxImpactIndex" in forecast:
        f = forecast.copy()
        f["date"] = pd.to_datetime(f["date"], errors="coerce")
        cutoff = pd.Timestamp.utcnow().normalize().tz_localize(None)
        upcoming = f[f["date"] > cutoff].sort_values("date")
        for port_id, group in upcoming.groupby("port_id"):
            forward_by_port[str(port_id)] = [
                {"date": _iso(d), "impact": _opt(v, 3)}
                for d, v in zip(group["date"].head(10), group["WxImpactIndex"].head(10))
            ]

    weather_by_port: dict[str, dict] = {}
    for _, row in features.iterrows():
        port = port_registry.resolve(str(row["port_id"]))
        if port is None:
            continue
        obs = obs_by_port.get(str(row["port_id"]))
        pers = pers_by_port.get(str(row["port_id"]))

        wave = _opt(obs.get("wave_height") if obs is not None else None, 2)
        impact = _opt(row.get("WxImpactIndex"), 3)
        regime = str(pers.get("weather_regime")) if pers is not None else None

        weather_by_port[port.locode] = {
            "portCode": port.locode,
            "name": port.name,
            "observedAt": _iso(row.get("date")),

            # Measured values. A null here means the feed did not carry it.
            "windKnots": _opt(obs.get("wind_speed") if obs is not None else None, 1),
            "gustKnots": _opt(obs.get("wind_gust") if obs is not None else None, 1),
            "rainfallMm24h": _opt(obs.get("rainfall") if obs is not None else None, 1),
            "waveHeightM": wave,
            "visibilityKm": _opt(obs.get("visibility") if obs is not None else None, 1),
            "seaState": _sea_state(wave),

            # Risk decomposition consumed by the model.
            "windRisk": _opt(row.get("wind_risk"), 3),
            "rainRisk": _opt(row.get("rain_risk"), 3),
            "waveRisk": _opt(row.get("wave_risk"), 3),
            "stormRisk": _opt(row.get("storm_risk"), 3),
            "impactScore": impact,
            "confidence": _opt(row.get("weather_confidence"), 3),

            # Shock vs sustained disruption.
            "weatherRegime": regime,
            "shockScore": _opt(pers.get("weather_shock") if pers is not None else None, 3),
            "persistenceScore": _opt(pers.get("weather_persistence") if pers is not None else None, 3),
            "forwardLoad": _opt(pers.get("weather_forward_load") if pers is not None else None, 3),
            "forecast": forward_by_port.get(str(row["port_id"]), []),

            "advisory": _advisory(impact, regime),
            "dataSource": "Open-Meteo (surface + marine) with GDACS storm flags",
        }

    intelligence = _build_intelligence(features, persistence, observations,
                                       weather_by_port)
    return weather_by_port, intelligence


def _build_intelligence(features: pd.DataFrame, persistence: pd.DataFrame,
                        observations: pd.DataFrame, by_port: dict) -> dict:
    def mean(frame: pd.DataFrame, column: str) -> float | None:
        if frame.empty or column not in frame:
            return None
        return _opt(pd.to_numeric(frame[column], errors="coerce").mean(), 3)

    persistent_ports = []
    if not persistence.empty and "weather_regime" in persistence:
        for _, row in persistence.iterrows():
            if str(row.get("weather_regime")) == "PERSISTENT":
                port = port_registry.resolve(str(row["port_id"]))
                if port:
                    persistent_ports.append(port.locode)

    worst = max(by_port.values(), key=lambda p: p.get("impactScore") or 0.0,
                default=None)
    return {
        "available": True,
        "observedAt": _iso(features["date"].max()) if "date" in features else None,
        "meanImpact": mean(features, "WxImpactIndex"),
        "meanWindRisk": mean(features, "wind_risk"),
        "meanRainRisk": mean(features, "rain_risk"),
        "meanWaveRisk": mean(features, "wave_risk"),
        "meanStormRisk": mean(features, "storm_risk"),
        "meanWindKnots": mean(observations, "wind_speed"),
        "meanWaveHeightM": mean(observations, "wave_height"),
        "persistentPorts": sorted(set(persistent_ports)),
        "highestImpactPort": (worst or {}).get("portCode"),
        "highestImpactScore": (worst or {}).get("impactScore"),
        "portsCovered": len(by_port),
        "dataSource": "Open-Meteo (surface + marine) with GDACS storm flags",
    }


# ---------------------------------------------------------------------------
def build_news_cache(event_catalogue: list[dict] | None = None) -> dict:
    """Traceable maritime events plus the port alerts the model actually raised."""
    catalogue = list(event_catalogue or [])
    news_features = _latest_per_port(_read(NEWS_FEATURES_PATH))
    decisions = _read(DECISION_PATH)

    events = []
    for item in catalogue:
        events.append({
            "id": item.get("id"),
            "timestamp": item.get("timestamp"),
            "title": item.get("title"),
            "source": item.get("source"),
            "url": item.get("url"),
            "tag": str(item.get("shockType", "event")).upper(),
            "entity": item.get("chokepointName") or "MARITIME",
            "chokepoint": item.get("chokepoint"),
            "severity": item.get("severityLabel"),
            "severityScore": item.get("severity"),
            "affectedPorts": [p["portCode"] for p in item.get("affectedPorts", [])],
            "exposure": item.get("affectedPorts", []),
            "dataSource": "GDELT DOC 2.0 + GDACS via IMF PortWatch",
        })

    alerts = []
    if not decisions.empty and "priority_score" in decisions:
        ranked = (decisions.sort_values("priority_score", ascending=False)
                  .drop_duplicates("port_id").head(8))
        for index, row in enumerate(ranked.itertuples(), start=1):
            port = port_registry.resolve(str(row.port_id))
            if port is None:
                continue
            alerts.append({
                "id": f"AL-{port.locode}-{index:02d}",
                "portCode": port.locode,
                "severity": str(getattr(row, "severity", "normal")),
                "text": f"{port.short}: {getattr(row, 'operational_adjustment', '')}",
                "action": str(getattr(row, "action_code", "MONITOR")),
                "priority": _opt(getattr(row, "priority_score", None), 3),
                "confidence": _opt(getattr(row, "decision_confidence", None), 3),
                "ts": _iso(getattr(row, "target_date", None)),
                "dataSource": "outputs/forecasts/decisions.csv",
            })

    sentiment = []
    for _, row in news_features.iterrows():
        port = port_registry.resolve(str(row["port_id"]))
        if port is None:
            continue
        mentions = sum(1 for event in events
                       if port.locode in event.get("affectedPorts", []))
        sentiment.append({
            "entity": port.locode,
            "mentions": mentions,
            "riskScore": _opt(row.get("geo_risk_score"), 3),
            "sentiment": _opt(row.get("news_sentiment_score"), 3),
            "eventSpike": _opt(row.get("event_spike_score"), 3),
            "confidence": _opt(row.get("news_confidence"), 3),
        })

    return {
        "events": events,
        "alerts": alerts,
        "sentiment": sentiment,
        "summary": {
            "totalEvents": len(events),
            "totalAlerts": len(alerts),
            "severeEvents": sum(1 for e in events if e["severity"] == "severe"),
            "eventsAvailable": bool(events),
            "dataSource": ("GDELT DOC 2.0 + GDACS (events); decision engine (alerts)"
                           if events else
                           "No event feed reached this run; alerts are model-derived only."),
        },
    }


def main(event_catalogue: list[dict] | None = None) -> None:
    weather_by_port, intelligence = build_weather_cache()
    news_bundle = build_news_cache(event_catalogue)

    _write(WEATHER_BY_PORT_PATH, weather_by_port)
    _write(WEATHER_INTEL_PATH, intelligence)
    _write(NEWS_BUNDLE_PATH, news_bundle)

    print(f"Support cache export complete. "
          f"Weather ports: {len(weather_by_port)} | "
          f"News events: {len(news_bundle['events'])} | "
          f"Alerts: {len(news_bundle['alerts'])}")


if __name__ == "__main__":
    main()
