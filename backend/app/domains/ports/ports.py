"""Port snapshots for the national radar and the port cockpit.

Every number here is either an observed value from the merged expert panel or a
model output from the forecast/regime tables. Where an input is genuinely
missing the field is ``null`` -- the previous version of this route invented
throughput and vessel counts from the congestion index, which is exactly the
kind of fabricated telemetry this system must not ship.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.services import cache_service as cache
from src.utils import port_registry

router = APIRouter()


def risk_from(congestion_index: float | None, severity: str,
              regime_state: str) -> str:
    """Operational risk band. Regime evidence outranks a single-day index."""
    state = (regime_state or "").upper()
    if state == "SEVERE" or severity.upper() == "SEVERE":
        return "severe"
    if state == "CONGESTED" or severity.upper() in {"HIGH", "MOD"}:
        return "congested"
    if congestion_index is not None and congestion_index >= 60:
        return "congested"
    return "normal"


def build_port_snapshot(port_code: str,
                        forecast_rows: list[dict],
                        regime: dict | None,
                        state: dict | None,
                        decision: dict | None) -> dict:
    if not forecast_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No forecast rows available for port: {port_code}")

    port = port_registry.resolve(port_code)
    rows = sorted(forecast_rows, key=lambda x: int(x.get("day", 1)))
    day1 = rows[0]
    peak = max(rows, key=lambda x: float(x.get("congestionIndex", 0.0)))

    day1_congestion = float(day1.get("congestionIndex", 0.0))
    peak_congestion = float(peak.get("congestionIndex", day1_congestion))
    state = state or {}
    regime_state = str((regime or {}).get("state", "UNKNOWN"))

    observed_congestion = state.get("congestionIndex")
    snapshot = {
        "code": port_code,
        "portCode": port_code,
        "modelId": port.model_id if port else None,
        "name": port.name if port else port_code,
        "short": port.short if port else port_code,
        "authority": port.authority if port else None,
        "location": ({"lat": port.lat, "lon": port.lon} if port
                     else state.get("location")),
        "coast": port.coast if port else None,

        # Observed now-state (panel), never derived from the forecast.
        "observedCongestionIndex": observed_congestion,
        "observedAt": state.get("observedAt"),
        "dataStatus": state.get("dataStatus", day1.get("dataStatus", "UNAVAILABLE")),
        "dataAgeHours": state.get("dataAgeHours", day1.get("dataAgeHours")),
        "throughputTonnes": state.get("throughputTonnes"),
        "vesselCalls": state.get("vesselCalls"),
        "anchorageCount": state.get("anchorageCount"),
        "queuePressure": state.get("queuePressure"),
        "capacityPressure": state.get("capacityPressure"),
        "anomalyScore": state.get("anomalyScore"),
        "weatherImpact": state.get("weatherImpact"),
        "aisConfidence": state.get("aisConfidence"),
        "dataQuality": state.get("dataQuality"),
        "utilization": state.get("utilization"),
        "congestionHistory": state.get("congestionHistory", []),

        # Forecast-derived fields, explicitly labelled as forecast.
        "congestionIndex": round(day1_congestion, 1),
        "congestion": round(day1_congestion / 100.0, 3),
        "peakCongestionIndex": round(peak_congestion, 1),
        "peakDay": int(peak.get("day", 1)),
        "delayHours": float(day1.get("delayHoursP50", 0.0)),
        "forecastQ10": day1.get("q10"),
        "forecastQ90": day1.get("q90"),
        "modelDisagreement": day1.get("modelDisagreement"),
        "confidence": float(day1.get("confidence", 0.0)),
        "model": day1.get("source"),
        "forecastOrigin": day1.get("originDate"),
        "forecastHorizonDays": len(rows),

        # Regime + decision context.
        "regime": regime_state,
        "regimeConfidence": (regime or {}).get("confidence"),
        "transitionRisk24h": (regime or {}).get("transitionRisk24h"),
        "expectedRemainingDays": (regime or {}).get("expectedRemainingDays"),
        "recommendedAction": (decision or {}).get("action"),
        "actionTitle": (decision or {}).get("title"),
        "priorityScore": (decision or {}).get("priorityScore"),

        "risk": risk_from(observed_congestion, str(peak.get("severity", "LOW")),
                          regime_state),
        "dataSource": "merged expert panel + forecast/regime artefacts",
    }
    return snapshot


def _load_all() -> tuple[dict, dict, dict, dict]:
    try:
        forecasts = cache.get_forecast_by_port()
    except cache.CacheNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    regimes = _safe(cache.get_regime_by_port)
    states = _safe(cache.get_port_state)
    decisions = _safe(cache.get_decision_by_port)
    return forecasts, regimes, states, decisions


def _safe(loader) -> dict:
    try:
        return loader()
    except cache.CacheNotReadyError:
        return {}


@router.get("/ports")
def list_ports() -> list[dict]:
    forecasts, regimes, states, decisions = _load_all()
    snapshots = [
        build_port_snapshot(code, rows, regimes.get(code), states.get(code),
                            decisions.get(code))
        for code, rows in forecasts.items()
    ]
    return sorted(snapshots, key=lambda x: x["name"])


@router.get("/ports/registry")
def port_registry_listing() -> list[dict]:
    """The canonical port registry -- the single source of truth for codes."""
    return port_registry.to_dicts()


@router.get("/ports/{port_code}")
def get_port(port_code: str) -> dict:
    forecasts, regimes, states, decisions = _load_all()
    resolved = port_registry.resolve(port_code)
    code = resolved.locode if resolved else port_code.upper()
    if code not in forecasts:
        raise HTTPException(
            status_code=404,
            detail=f"Port not present in the forecast cache: {port_code}")
    return build_port_snapshot(code, forecasts[code], regimes.get(code),
                               states.get(code), decisions.get(code))
