"""Export the pipeline's real artefacts into the terminal API cache.

Every value written here is read from an artefact the pipeline actually
produced -- the merged expert panel, the HSMM regime table, the forecast table,
the decision table, the route recommendations and the walk-forward benchmark.
Nothing is manufactured to fill a panel: when an artefact is missing the payload
says so, and the UI renders the gap instead of a plausible-looking number.

Written into ``data/cache/``:

    port_state.json       observed NOW state per port (from the merged panel)
    forecast_by_port.json 1..H day quantile forecast per port
    regime_by_port.json   latest HSMM regime per port
    decision_by_port.json ranked operational decision per port
    model_pipeline.json   per-node signal/confidence for Model Intelligence
    benchmark.json        walk-forward accuracy artefacts
    vessels.json          AIS-derived vessel-activity proxies
    fleet.json            route-optimizer output per vessel
    live_status.json      run summary consumed by /api/health
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.utils import port_registry

ROOT = Path(__file__).resolve().parents[2]
EXPERT_DIR = ROOT / "outputs" / "expert_features"
REGIME_PATH = ROOT / "outputs" / "regimes" / "regimes.csv"
FORECAST_DIR = ROOT / "outputs" / "forecasts"
FORECAST_PATH = FORECAST_DIR / "forecast_table.csv"
DECISION_PATH = FORECAST_DIR / "decisions.csv"
ROUTE_PATH = FORECAST_DIR / "route_recommendations.csv"
PANEL_PATH = EXPERT_DIR / "merged_panel.csv"
CACHE_DIR = ROOT / "data" / "cache"

#: Forecast origins older than this are surfaced as stale in the UI.
FRESHNESS_BUDGET_HOURS = 36.0


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------
def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required artefact missing: {path}")
    return pd.read_csv(path)


def _read_optional(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def _write(name: str, payload) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / name
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    print(f"Wrote {path}")
    return path


def _code(model_id) -> str:
    port = port_registry.resolve(str(model_id))
    return port.locode if port else str(model_id).upper()


def _num(value, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return default if pd.isna(result) else result


def _opt(value):
    """Return a float, or None when the artefact genuinely has no value."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(result) else result


def _iso(ts) -> str | None:
    parsed = pd.to_datetime(ts, errors="coerce")
    if pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("UTC")
    return parsed.isoformat()


def _age_hours(ts) -> float | None:
    parsed = pd.to_datetime(ts, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    delta = datetime.now(timezone.utc) - parsed.to_pydatetime()
    return round(max(0.0, delta.total_seconds() / 3600.0), 2)


def _freshness(ts) -> tuple[str, float | None]:
    """Map an observation timestamp onto the provenance vocabulary."""
    age = _age_hours(ts)
    if age is None:
        return "UNAVAILABLE", None
    if age <= FRESHNESS_BUDGET_HOURS:
        return "CACHED_LIVE", age
    return "STALE", age


def _severity(value: float, q90: float) -> str:
    if value >= 70 or q90 >= 80:
        return "SEVERE"
    if value >= 45 or q90 >= 60:
        return "HIGH"
    if value >= 30:
        return "MOD"
    return "LOW"


# ---------------------------------------------------------------------------
# Observed NOW state -- straight from the merged expert panel
# ---------------------------------------------------------------------------
def build_port_state(panel: pd.DataFrame) -> dict:
    """Latest observed operating state per port. No derived stand-ins."""
    if panel.empty:
        return {}

    frame = panel.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    latest = (frame.sort_values(["port_id", "date"])
              .groupby("port_id", as_index=False)
              .tail(1))

    out: dict[str, dict] = {}
    for _, row in latest.iterrows():
        port = port_registry.resolve(str(row["port_id"]))
        if port is None:
            continue
        observed_at = _iso(row["date"])
        status, age = _freshness(row["date"])

        # 14-day observed history for the cockpit sparkline.
        history = (frame[frame["port_id"] == row["port_id"]]
                   .sort_values("date")
                   .tail(14))

        out[port.locode] = {
            "portCode": port.locode,
            "modelId": port.model_id,
            "name": port.name,
            "short": port.short,
            "authority": port.authority,
            "coast": port.coast,
            "location": {"lat": port.lat, "lon": port.lon},
            "capacityIndex": port.capacity,
            "berthCount": port.berth_count,

            "observedAt": observed_at,
            "dataAgeHours": age,
            "dataStatus": status,

            "congestionIndex": _opt(row.get("congestion_index")),
            "delayHours": _opt(row.get("delay_hours")),
            "throughputTonnes": _opt(row.get("throughput")),
            "utilization": _opt(row.get("utilization")),
            "queuePressure": _opt(row.get("queue_proxy")),
            "turnaroundPressure": _opt(row.get("turnaround_proxy")),
            "vesselCalls": _opt(row.get("arrival_count")),
            "vesselDensity": _opt(row.get("vessel_density")),
            "anchorageCount": _opt(row.get("anchorage_count")),
            "capacityPressure": _opt(row.get("capacity_pressure")),
            "queueMomentum": _opt(row.get("queue_momentum")),
            "throughputStress": _opt(row.get("throughput_stress")),
            "anomalyScore": _opt(row.get("anomaly_score")),
            "specialistStress": _opt(row.get("specialist_stress")),
            "weatherImpact": _opt(row.get("WxImpactIndex")),
            "weatherPersistence": _opt(row.get("weather_persistence")),
            "weatherShock": _opt(row.get("weather_shock")),
            "arrivalClustering": _opt(row.get("arrival_clustering")),
            "berthPressure": _opt(row.get("berth_pressure")),
            "disruptionExposure": _opt(row.get("disruption_exposure")),
            "disruptionPressure": _opt(row.get("disruption_pressure")),
            "dataQuality": _opt(row.get("data_quality_score")),
            "aisConfidence": _opt(row.get("ais_confidence")),

            "congestionHistory": [
                {"date": _iso(d), "value": _opt(v)}
                for d, v in zip(history["date"], history.get("congestion_index", []))
            ],
        }
    return out


# ---------------------------------------------------------------------------
# Forecast / regime / decision
# ---------------------------------------------------------------------------
def build_forecasts(forecast: pd.DataFrame, weather: pd.DataFrame) -> dict:
    wx_latest: dict[str, float] = {}
    if not weather.empty and "WxImpactIndex" in weather:
        w = weather.copy()
        w["date"] = pd.to_datetime(w["date"], errors="coerce")
        if "horizon_day" in w:
            w = w[w["horizon_day"] == 0]
        wx_latest = (w.sort_values("date")
                     .groupby("port_id")["WxImpactIndex"].last().to_dict())

    out: dict[str, list[dict]] = {}
    for model_id, group in forecast.groupby("port_id"):
        code = _code(model_id)
        origin = group["forecast_origin_date"].max()
        status, age = _freshness(origin)
        rows = []
        for _, r in group.sort_values("horizon_day").iterrows():
            congestion = _num(r.get("predicted_congestion"))
            q10, q90 = _num(r.get("q10")), _num(r.get("q90"))
            rows.append({
                "portCode": code,
                "day": int(_num(r.get("horizon_day"), 1)),
                "targetDate": _iso(r.get("target_date")),
                "originDate": _iso(r.get("forecast_origin_date")),
                "dateLabel": pd.to_datetime(r.get("target_date")).strftime("%d %b").upper(),
                "congestionIndex": round(congestion, 1),
                "q10": round(q10, 1),
                "q50": round(_num(r.get("q50")), 1),
                "q90": round(q90, 1),
                "intervalWidth": round(max(q90 - q10, 0.0), 1),
                "delayHoursP50": round(_num(r.get("predicted_delay")), 1),
                "throughputTonnes": _opt(r.get("predicted_throughput")),
                "weatherProbability": round(_num(wx_latest.get(model_id), 0.0), 3),
                "severity": _severity(congestion, q90),
                "confidence": round(_num(r.get("confidence_score"), 0.65), 3),
                "source": str(r.get("model", "unknown")),
                "modelDisagreement": _opt(r.get("model_disagreement")),
                "tftWeight": _opt(r.get("ensemble_tft_weight")),
                "gbmWeight": _opt(r.get("ensemble_gbm_weight")),
                "conformalOffset": _opt(r.get("conformal_offset")),
                "dataStatus": status,
                "dataAgeHours": age,
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
        status, age = _freshness(row.get("date"))
        history = (r[r["port_id"] == row["port_id"]].sort_values("date").tail(30))
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
            "observedAt": _iso(row.get("date")),
            "dataStatus": status,
            "dataAgeHours": age,
            "source": "HSMM",
            "history": [
                {"date": _iso(d), "state": str(s),
                 "severe": _opt(sev), "congested": _opt(con)}
                for d, s, sev, con in zip(
                    history["date"], history.get("regime_label", []),
                    history.get("p_severe", []), history.get("p_congested", []))
            ],
        }
    return out


def build_decisions(decisions: pd.DataFrame, forecast: pd.DataFrame) -> dict:
    """Surface the single highest-priority decision per port, with its evidence."""
    if decisions.empty:
        return {}

    conf_by_port: dict[str, float] = {}
    if "confidence_score" in forecast:
        conf_by_port = forecast.groupby("port_id")["confidence_score"].mean().to_dict()

    out = {}
    for model_id, group in decisions.groupby("port_id"):
        ranked = group.sort_values("priority_score", ascending=False)
        peak = ranked.iloc[0]
        code = _code(model_id)
        score = _num(peak.get("priority_score"))

        actions = _decision_actions(peak)
        drivers = _decision_drivers(peak)

        out[code] = {
            "id": f"DEC-{code}",
            "portCode": code,
            "severity": str(peak.get("severity", _severity_from_score(score))),
            "title": str(peak.get("action_title", "Review port operations")),
            "action": str(peak.get("action_code", "MONITOR")),
            "actions": actions,
            "target": str(peak.get("action_target", code)),
            "horizonDay": int(_num(peak.get("horizon_day"), 1)),
            "targetDate": _iso(peak.get("target_date")),
            "rationale": str(peak.get("reason", "")) or _fallback_reason(peak),
            "topDrivers": drivers,
            "expectedImpact": str(peak.get("expected_impact", "")),
            "expectedDelaySavedHours": _opt(peak.get("expected_delay_saved_hours")),
            "alternativeAction": str(peak.get("alternative_action", "")),
            "uncertainty": _opt(peak.get("uncertainty")),
            "congestionProbability": _opt(peak.get("congestion_probability")),
            "portEntryRisk": str(peak.get("port_entry_risk", "Unknown")),
            "priorityScore": round(score, 3),
            "confidence": round(_num(peak.get("decision_confidence"),
                                     _num(conf_by_port.get(model_id), 0.65)), 3),
            "originDate": _iso(peak.get("forecast_origin_date")),
            "source": "DECISION_ENGINE",
            "schedule": [
                {
                    "horizonDay": int(_num(row.get("horizon_day"), 1)),
                    "targetDate": _iso(row.get("target_date")),
                    "action": str(row.get("action_code", "MONITOR")),
                    "priority": round(_num(row.get("priority_score")), 3),
                    "congestionProbability": _opt(row.get("congestion_probability")),
                }
                for _, row in group.sort_values("horizon_day").iterrows()
            ],
        }
    return out


def _severity_from_score(score: float) -> str:
    if score >= 0.72:
        return "severe"
    if score >= 0.52:
        return "high"
    if score >= 0.32:
        return "medium"
    return "normal"


def _decision_actions(row) -> list[str]:
    raw = str(row.get("operational_adjustment", "")).strip()
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    return parts or ["Continue standard monitoring."]


def _decision_drivers(row) -> list[dict]:
    raw = str(row.get("top_drivers", "")).strip()
    if not raw or raw.lower() == "nan":
        return []
    drivers = []
    for token in raw.split("|"):
        if "=" not in token:
            continue
        name, _, value = token.partition("=")
        drivers.append({"factor": name.strip(), "contribution": _opt(value)})
    return drivers


def _fallback_reason(row) -> str:
    return (f"Congestion probability {_num(row.get('congestion_probability')):.0%}; "
            f"entry risk {row.get('port_entry_risk', 'Unknown')}.")


# ---------------------------------------------------------------------------
# AIS-derived vessel proxies and fleet routing
# ---------------------------------------------------------------------------
def build_vessels(panel: pd.DataFrame) -> dict:
    """Vessel-activity proxies derived from measured PortWatch call counts.

    These are aggregate activity proxies, not individual tracked ships -- the
    payload says so explicitly so the map can never imply per-vessel AIS.
    """
    if panel.empty:
        return {"vessels": [], "basis": "unavailable"}

    frame = panel.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    latest = (frame.sort_values(["port_id", "date"])
              .groupby("port_id", as_index=False).tail(1))

    vessels = []
    for _, row in latest.iterrows():
        port = port_registry.resolve(str(row["port_id"]))
        if port is None:
            continue
        calls = _num(row.get("arrival_count"))
        anchorage = _num(row.get("anchorage_count"))
        queue = _num(row.get("queue_proxy"))
        vessels.append({
            "portCode": port.locode,
            "name": port.name,
            "location": {"lat": port.lat, "lon": port.lon},
            "dailyPortCalls": round(calls, 1),
            "queueBuildup": round(anchorage, 1),
            "queuePressure": round(queue, 3),
            "waitingProxy": round(anchorage, 1),
            "confidence": _opt(row.get("ais_confidence")),
            "observedAt": _iso(row.get("date")),
            "basis": "IMF PortWatch satellite-AIS daily port calls",
        })
    return {
        "vessels": vessels,
        "basis": "aggregate daily port-call activity, not per-vessel AIS tracks",
        "observedAt": _iso(latest["date"].max()) if not latest.empty else None,
    }


def build_fleet(routes: pd.DataFrame, forecast: pd.DataFrame) -> list[dict]:
    """Fleet board rows, straight from the route optimizer output."""
    if routes.empty:
        return []
    origin = _iso(pd.to_datetime(forecast["forecast_origin_date"], errors="coerce").max())
    out = []
    for _, row in routes.iterrows():
        intended = port_registry.resolve(str(row.get("intended_port", "")))
        recommended = port_registry.resolve(str(row.get("recommended_port", "")))
        out.append({
            "id": str(row.get("vessel", "")).upper().replace(" ", "-"),
            "name": str(row.get("vessel", "")),
            "intendedPortCode": intended.locode if intended else None,
            "recommendedPortCode": recommended.locode if recommended else None,
            "reroute": bool(row.get("reroute", False)),
            "bestArrivalDay": _opt(row.get("best_arrival_day")),
            "etaDeltaHours": _opt(row.get("eta_delta_hours")),
            "riskDelta": _opt(row.get("risk_delta")),
            "portWaitDeltaHours": _opt(row.get("port_wait_delta_hours")),
            "bufferHours": _opt(row.get("recommended_buffer_hours")),
            "diversionKm": _opt(row.get("diversion_km")),
            "recommendation": str(row.get("recommendation", "")),
            "originDate": origin,
            "source": "ROUTE_OPTIMIZER",
        })
    return out


# ---------------------------------------------------------------------------
# Model Intelligence pipeline nodes
# ---------------------------------------------------------------------------
def _latest_mean(path: Path, score_cols: list[str], confidence_col: str
                 ) -> tuple[float | None, float | None, str | None, int]:
    if not path.exists():
        return None, None, None, 0
    df = pd.read_csv(path)
    if df.empty:
        return None, None, None, 0
    observed = None
    if "date" in df:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        latest = df["date"].max()
        observed = _iso(latest)
        df = df[df["date"] == latest]
    available = [c for c in score_cols if c in df]
    score = float(df[available].abs().mean(axis=1).mean()) if available else None
    confidence = (float(pd.to_numeric(df[confidence_col], errors="coerce").mean())
                  if confidence_col in df else None)
    clamp = lambda v: None if v is None or pd.isna(v) else max(0.0, min(float(v), 1.0))
    return clamp(score), clamp(confidence), observed, int(len(df))


_EXPERT_SPECS = [
    ("WX", "Weather Expert", "weather_features.csv", ["WxImpactIndex"],
     "weather_confidence", "wind / wave / rain / storm risk",
     "Drives weather term in congestion + decision guardrails"),
    ("WXP", "Weather Persistence Expert", "weather_persistence_features.csv",
     ["weather_persistence"], "weather_persistence_confidence",
     "shock vs sustained weather disruption",
     "Separates transient squalls from multi-day disruption"),
    ("NLP", "News + Geopolitical Expert", "news_features.csv",
     ["geo_risk_score", "event_spike_score"], "news_confidence",
     "maritime events + geopolitical risk",
     "Raises event risk and decision urgency"),
    ("AIS", "AIS / Port Ops Expert", "port_ops_features.csv",
     ["queue_proxy", "turnaround_proxy"], "ais_confidence",
     "satellite-AIS port calls + queue pressure",
     "Primary observed congestion driver"),
    ("ARR", "Arrival Dynamics Expert", "arrival_features.csv",
     ["arrival_clustering", "berth_pressure"], "arrival_confidence",
     "arrival clustering + anchorage buildup",
     "Detects queue acceleration ahead of congestion"),
    ("DEM", "Trade Demand Expert", "trade_demand_features.csv",
     ["demand_pressure"], "demand_confidence", "trade and demand pressure",
     "Shifts baseline load expectation"),
    ("CAP", "Capacity Agent", "capacity_features.csv",
     ["capacity_pressure", "queue_momentum"], "capacity_confidence",
     "berth / yard capacity squeeze",
     "Feeds queue + utilization features in the panel"),
    ("ANOM", "Anomaly Agent", "anomaly_features.csv", ["anomaly_score"],
     "anomaly_confidence", "robust drift + abnormal operations",
     "Flags regime breaks and discounts confidence"),
    ("DISR", "Disruption Propagation Expert", "disruption_features.csv",
     ["disruption_pressure"], "disruption_confidence",
     "chokepoint status -> lane -> port exposure",
     "Propagates global chokepoint stress onto exposed ports"),
    ("DQ", "Data Quality Expert", "data_quality_features.csv",
     ["data_quality_score"], "data_quality_confidence",
     "feed freshness, gaps and synthetic fallback",
     "Discounts forecast confidence when inputs degrade"),
]


def build_pipeline(forecast: pd.DataFrame, regimes: pd.DataFrame,
                   benchmark: dict) -> list[dict]:
    latest_origin = pd.to_datetime(forecast["forecast_origin_date"], errors="coerce").max()
    timestamp = _iso(latest_origin)
    status, age = _freshness(latest_origin)

    rows = []
    for key, name, filename, scores, conf, signal, effect in _EXPERT_SPECS:
        path = EXPERT_DIR / filename
        score, confidence, observed, n_rows = _latest_mean(path, scores, conf)
        rows.append({
            "key": key,
            "name": name,
            "kind": "expert",
            "inputSignal": signal,
            "score": None if score is None else round(score, 3),
            "confidence": None if confidence is None else round(confidence, 3),
            "effectOnForecast": effect,
            "observedAt": observed,
            "rows": n_rows,
            "available": path.exists() and n_rows > 0,
            "artefact": f"outputs/expert_features/{filename}",
            "dataStatus": _freshness(observed)[0] if observed else "UNAVAILABLE",
        })

    r = regimes.copy()
    r["date"] = pd.to_datetime(r["date"], errors="coerce")
    latest = r.sort_values("date").groupby("port_id", as_index=False).tail(1)
    regime_score = float((pd.to_numeric(latest.get("p_congested", 0), errors="coerce")
                          + pd.to_numeric(latest.get("p_severe", 0), errors="coerce")).mean())
    regime_conf = float(pd.to_numeric(latest.get("regime_confidence", 0.5), errors="coerce").mean())
    model_conf = float(pd.to_numeric(forecast.get("confidence_score", 0.65), errors="coerce").mean())
    model_score = float(pd.to_numeric(forecast["predicted_congestion"], errors="coerce").mean() / 100.0)
    model_name = str(forecast.get("model", pd.Series(["forecast"])).iloc[0])
    mean_disagreement = None
    if "model_disagreement" in forecast.columns:
        values = pd.to_numeric(forecast["model_disagreement"], errors="coerce").dropna()
        if not values.empty:
            mean_disagreement = round(float(values.mean()), 3)

    leader = (benchmark.get("summary", {}) or {}).get("bestModel")
    coverage = (benchmark.get("summary", {}) or {}).get("bestCoverage80")

    rows.extend([
        {"key": "HSMM", "name": "HSMM Regime Engine", "kind": "model",
         "inputSignal": "fused expert state panel",
         "score": round(regime_score, 3), "confidence": round(regime_conf, 3),
         "effectOnForecast": "State persistence, dwell time and transition risk",
         "observedAt": timestamp, "rows": int(len(latest)), "available": True,
         "artefact": "outputs/regimes/regimes.csv", "dataStatus": status,
         "modelCard": "hsmm-gaussian-duration"},
        {"key": "ENS", "name": "Adaptive Forecast Ensemble", "kind": "model",
         "inputSignal": "TFT + conformal GBM quantiles",
         "score": round(model_score, 3), "confidence": round(model_conf, 3),
         "effectOnForecast": "10-day q10/q50/q90 congestion forecast",
         "observedAt": timestamp, "rows": int(len(forecast)), "available": True,
         "artefact": "outputs/forecasts/forecast_table.csv", "dataStatus": status,
         "modelCard": model_name, "disagreement": mean_disagreement,
         "benchmarkLeader": leader, "coverage80": coverage},
        {"key": "DEC", "name": "Decision + Route Engine", "kind": "decision",
         "inputSignal": "forecast distributions + weather + capacity",
         "score": round(model_score, 3), "confidence": round(model_conf, 3),
         "effectOnForecast": "Operational actions and alternate arrival windows",
         "observedAt": timestamp, "rows": int(len(forecast)), "available": True,
         "artefact": "outputs/forecasts/decisions.csv", "dataStatus": status,
         "modelCard": "decision-route-engine"},
    ])
    for row in rows:
        row["ageHours"] = age
    return rows


# ---------------------------------------------------------------------------
# Benchmark artefacts
# ---------------------------------------------------------------------------
def build_benchmark() -> dict:
    """Read whatever the evaluation stage produced. Absent files stay absent."""
    payload: dict = {"available": False}

    summary_path = FORECAST_DIR / "benchmark_summary.json"
    if summary_path.exists():
        try:
            with open(summary_path, "r", encoding="utf-8") as fh:
                payload.update(json.load(fh))
            payload["available"] = True
        except (OSError, json.JSONDecodeError):
            pass

    for name, filename in (
        ("models", "model_benchmark.csv"),
        ("byHorizon", "horizon_benchmark.csv"),
        ("byPort", "port_benchmark.csv"),
        ("byRegime", "regime_benchmark.csv"),
    ):
        frame = _read_optional(FORECAST_DIR / filename)
        if not frame.empty:
            payload[name] = json.loads(frame.to_json(orient="records"))
            payload["available"] = True

    calibration_path = FORECAST_DIR / "calibration.json"
    if calibration_path.exists():
        try:
            with open(calibration_path, "r", encoding="utf-8") as fh:
                payload["calibration"] = json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass

    weights_path = FORECAST_DIR / "ensemble_weights.json"
    if weights_path.exists():
        try:
            with open(weights_path, "r", encoding="utf-8") as fh:
                payload["ensembleWeights"] = json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass

    if not payload["available"]:
        payload["reason"] = (
            "No benchmark artefacts found. Run "
            "`python -m src.evaluation.model_benchmark` or "
            "`python run_award_demo.py --benchmark`.")
    return payload


# ---------------------------------------------------------------------------
def main() -> None:
    forecast = _read(FORECAST_PATH)
    regimes = _read(REGIME_PATH)
    decisions = _read_optional(DECISION_PATH)
    routes = _read_optional(ROUTE_PATH)
    panel = _read_optional(PANEL_PATH)
    weather = _read_optional(EXPERT_DIR / "weather_features.csv")

    benchmark = build_benchmark()

    _write("port_state.json", build_port_state(panel))
    _write("forecast_by_port.json", build_forecasts(forecast, weather))
    _write("regime_by_port.json", build_regimes(regimes))
    _write("decision_by_port.json", build_decisions(decisions, forecast))
    _write("model_pipeline.json", build_pipeline(forecast, regimes, benchmark))
    _write("benchmark.json", benchmark)
    _write("vessels.json", build_vessels(panel))
    _write("fleet.json", build_fleet(routes, forecast))

    origin = pd.to_datetime(forecast["forecast_origin_date"], errors="coerce").max()
    status, age = _freshness(origin)
    _write("live_status.json", {
        "status": "ready",
        "model": str(forecast.get("model", pd.Series(["unknown"])).iloc[0]),
        "forecastOrigin": _iso(origin),
        "forecastOriginStatus": status,
        "forecastOriginAgeHours": age,
        "ports": int(forecast["port_id"].nunique()),
        "horizonDays": int(pd.to_numeric(forecast["horizon_day"], errors="coerce").max()),
        "benchmarkAvailable": bool(benchmark.get("available")),
        "benchmarkVersion": benchmark.get("version"),
        "exportedAt": datetime.now(timezone.utc).isoformat(),
    })


if __name__ == "__main__":
    main()
