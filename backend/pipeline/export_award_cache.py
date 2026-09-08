"""Export real pipeline artefacts into the terminal API cache.

Unlike the legacy cache exporter, this module does not manufacture HSMM states,
expert scores, or decision context from forecast quantiles. It reads the actual
expert, regime, forecast and decision artefacts produced by run_award_demo.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from backend.app.services.port_service import get_port

ROOT = Path(__file__).resolve().parents[2]
EXPERT_DIR = ROOT / "outputs" / "expert_features"
REGIME_PATH = ROOT / "outputs" / "regimes" / "regimes.csv"
FORECAST_PATH = ROOT / "outputs" / "forecasts" / "forecast_table.csv"
DECISION_PATH = ROOT / "outputs" / "forecasts" / "decisions.csv"
CACHE_DIR = ROOT / "data" / "cache"


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required artefact missing: {path}")
    return pd.read_csv(path)


def _write(name: str, payload) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / name
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    print(f"Wrote {path}")


def _code(model_id: str) -> str:
    return str(get_port(str(model_id))["code"])


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _severity(value: float, q90: float) -> str:
    if value >= 70 or q90 >= 80:
        return "SEVERE"
    if value >= 45 or q90 >= 60:
        return "HIGH"
    if value >= 30:
        return "MOD"
    return "LOW"


def build_forecasts(forecast: pd.DataFrame, weather: pd.DataFrame) -> dict:
    wx_latest = {}
    if not weather.empty and "WxImpactIndex" in weather:
        w = weather.copy()
        w["date"] = pd.to_datetime(w["date"], errors="coerce")
        if "horizon_day" in w:
            w = w[w["horizon_day"] == 0]
        wx_latest = (
            w.sort_values("date").groupby("port_id")["WxImpactIndex"].last().to_dict()
        )

    out: dict[str, list[dict]] = {}
    for model_id, group in forecast.groupby("port_id"):
        code = _code(model_id)
        rows = []
        for _, r in group.sort_values("horizon_day").iterrows():
            congestion = _num(r.get("predicted_congestion"))
            q10, q90 = _num(r.get("q10")), _num(r.get("q90"))
            rows.append({
                "portCode": code,
                "day": int(_num(r.get("horizon_day"), 1)),
                "dateLabel": pd.to_datetime(r.get("target_date")).strftime("%d %b").upper(),
                "congestionIndex": round(congestion, 1),
                "delayHoursP95": round(_num(r.get("predicted_delay")), 1),
                "uncertaintyBandHours": round(max(q90 - q10, 0.0), 1),
                "weatherProbability": round(_num(wx_latest.get(model_id), 0.0), 3),
                "severity": _severity(congestion, q90),
                "confidence": round(_num(r.get("confidence_score"), 0.65), 3),
                "source": str(r.get("model", "unknown")),
                "modelDisagreement": round(_num(r.get("model_disagreement"), 0.0), 3),
            })
        out[code] = rows
    return out


def build_regimes(regimes: pd.DataFrame) -> dict:
    r = regimes.copy()
    r["date"] = pd.to_datetime(r["date"], errors="coerce")
    latest = r.sort_values(["port_id", "date"]).groupby("port_id", as_index=False).tail(1)
    out = {}
    for _, row in latest.iterrows():
        code = _code(row["port_id"])
        out[code] = {
            "portCode": code,
            "state": str(row.get("regime_label", "NORMAL")),
            "probabilities": {
                "normal": round(_num(row.get("p_normal")), 3),
                "congested": round(_num(row.get("p_congested")), 3),
                "severe": round(_num(row.get("p_severe")), 3),
            },
            "daysInState": round(_num(row.get("days_in_state")), 2),
            "expectedRemainingDays": round(_num(row.get("expected_remaining_days")), 2),
            "transitionRisk24h": round(_num(row.get("transition_risk")), 3),
            "confidence": round(_num(row.get("regime_confidence"), 0.5), 3),
            "timestamp": pd.to_datetime(row.get("date")).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "HSMM",
        }
    return out


def build_decisions(decisions: pd.DataFrame, forecast: pd.DataFrame) -> dict:
    fconf = forecast.groupby("port_id")["confidence_score"].mean().to_dict() if "confidence_score" in forecast else {}
    out = {}
    for model_id, group in decisions.groupby("port_id"):
        peak = group.sort_values("priority_score", ascending=False).iloc[0]
        score = _num(peak.get("priority_score"))
        if score >= 0.72:
            severity, title = "severe", "Intervene now"
        elif score >= 0.52:
            severity, title = "high", "Activate congestion protocol"
        elif score >= 0.32:
            severity, title = "medium", "Prepare mitigation"
        else:
            severity, title = "normal", "Maintain normal operations"
        action = str(peak.get("operational_adjustment", "Continue monitoring."))
        actions = [part.strip() for part in action.split(";") if part.strip()]
        code = _code(model_id)
        out[code] = {
            "id": f"DEC-{code}",
            "portCode": code,
            "severity": severity,
            "title": title,
            "actions": actions or [action],
            "rationale": (
                f"Congestion probability {_num(peak.get('congestion_probability')):.0%}; "
                f"entry risk {peak.get('port_entry_risk', 'Unknown')}; "
                f"priority {score:.2f}."
            ),
            "confidence": round(_num(fconf.get(model_id), 0.65), 3),
            "timestamp": str(peak.get("forecast_origin_date", "")),
            "source": "DECISION_ENGINE",
        }
    return out


def _latest_mean(path: Path, score_cols: list[str], confidence_col: str) -> tuple[float, float]:
    if not path.exists():
        return 0.0, 0.0
    df = pd.read_csv(path)
    if df.empty:
        return 0.0, 0.0
    if "date" in df:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        latest = df["date"].max()
        df = df[df["date"] == latest]
    available = [c for c in score_cols if c in df]
    score = float(df[available].abs().mean(axis=1).mean()) if available else 0.0
    confidence = float(pd.to_numeric(df.get(confidence_col, pd.Series([0.0])), errors="coerce").mean())
    return max(0.0, min(score, 1.0)), max(0.0, min(confidence, 1.0))


def build_pipeline(forecast: pd.DataFrame, regimes: pd.DataFrame) -> list[dict]:
    latest_origin = pd.to_datetime(forecast["forecast_origin_date"], errors="coerce").max()
    timestamp = latest_origin.strftime("%Y-%m-%dT%H:%M:%SZ")
    specs = [
        ("WX", "Weather Expert", "weather_features.csv", ["WxImpactIndex"], "weather_confidence", "wind/wave/rain/storm"),
        ("NLP", "News + Geo Expert", "news_features.csv", ["geo_risk_score", "event_spike_score"], "news_confidence", "maritime events + geopolitical risk"),
        ("AIS", "AIS / Port Ops Expert", "port_ops_features.csv", ["queue_proxy", "turnaround_proxy"], "ais_confidence", "satellite-AIS activity + queue pressure"),
        ("DEM", "Trade Demand Expert", "trade_demand_features.csv", ["demand_pressure"], "demand_confidence", "trade and demand pressure"),
        ("CAP", "Capacity Agent", "capacity_features.csv", ["capacity_pressure", "queue_momentum"], "capacity_confidence", "berth/yard capacity squeeze"),
        ("ANOM", "Anomaly Agent", "anomaly_features.csv", ["anomaly_score"], "anomaly_confidence", "robust drift + abnormal operations"),
    ]
    rows = []
    for key, name, filename, scores, conf, signal in specs:
        score, confidence = _latest_mean(EXPERT_DIR / filename, scores, conf)
        rows.append({
            "key": key, "name": name, "inputSignal": signal,
            "score": round(score, 3), "confidence": round(confidence, 3),
            "effectOnForecast": "Feeds fused digital-twin state",
            "timestamp": timestamp, "modelCard": f"{key.lower()}-expert-v2",
        })

    r = regimes.copy()
    latest = r.sort_values("date").groupby("port_id", as_index=False).tail(1)
    regime_score = float((latest.get("p_congested", 0) + latest.get("p_severe", 0)).mean())
    regime_conf = float(pd.to_numeric(latest.get("regime_confidence", 0.5), errors="coerce").mean())
    model_conf = float(pd.to_numeric(forecast.get("confidence_score", 0.65), errors="coerce").mean())
    model_score = float(pd.to_numeric(forecast["predicted_congestion"], errors="coerce").mean() / 100.0)
    model_name = str(forecast.get("model", pd.Series(["forecast"])).iloc[0])
    rows.extend([
        {"key": "HSMM", "name": "HSMM Regime Engine", "inputSignal": "fused expert state panel",
         "score": round(regime_score, 3), "confidence": round(regime_conf, 3),
         "effectOnForecast": "State persistence + transition risk", "timestamp": timestamp, "modelCard": "hsmm-v2"},
        {"key": "ENS", "name": "Adaptive Forecast Ensemble", "inputSignal": "TFT + calibrated GBM quantiles",
         "score": round(model_score, 3), "confidence": round(model_conf, 3),
         "effectOnForecast": "10-day q10/q50/q90 forecast", "timestamp": timestamp, "modelCard": model_name},
        {"key": "DEC", "name": "Decision + Route Engine", "inputSignal": "forecast distributions + weather + risk",
         "score": round(model_score, 3), "confidence": round(model_conf, 3),
         "effectOnForecast": "Operational actions + alternate arrivals", "timestamp": timestamp, "modelCard": "decision-route-v2"},
    ])
    return rows


def main() -> None:
    forecast = _read(FORECAST_PATH)
    regimes = _read(REGIME_PATH)
    decisions = _read(DECISION_PATH)
    weather = pd.read_csv(EXPERT_DIR / "weather_features.csv") if (EXPERT_DIR / "weather_features.csv").exists() else pd.DataFrame()
    _write("forecast_by_port.json", build_forecasts(forecast, weather))
    _write("regime_by_port.json", build_regimes(regimes))
    _write("decision_by_port.json", build_decisions(decisions, forecast))
    _write("model_pipeline.json", build_pipeline(forecast, regimes))
    _write("live_status.json", {
        "status": "ready",
        "model": str(forecast.get("model", pd.Series(["unknown"])).iloc[0]),
        "forecastOrigin": str(pd.to_datetime(forecast["forecast_origin_date"], errors="coerce").max()),
        "ports": int(forecast["port_id"].nunique()),
        "pipelineSteps": 9,
    })


if __name__ == "__main__":
    main()
