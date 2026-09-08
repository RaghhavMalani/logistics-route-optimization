"""Model Intelligence endpoints.

Serves the pipeline node table, the walk-forward benchmark artefacts and the
per-port forecast / regime / decision outputs, plus the explicit intelligence
chain (raw signal -> expert -> regime -> forecast -> decision) that the Model
Intelligence screen renders.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.services import cache_service as cache
from src.utils import port_registry

router = APIRouter()


def _handle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, cache.CacheNotReadyError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/model/ports")
def list_model_ports() -> list[str]:
    try:
        return cache.get_available_ports()
    except Exception as exc:
        raise _handle_error(exc)


@router.get("/model/pipeline")
def model_pipeline() -> list[dict]:
    try:
        return cache.get_model_pipeline()
    except Exception as exc:
        raise _handle_error(exc)


@router.get("/model/benchmark")
def model_benchmark() -> dict:
    """Walk-forward accuracy artefacts. Never hardcoded, never interpolated."""
    return cache.get_benchmark()


@router.get("/model/{port_code}/forecast")
def model_forecast(port_code: str) -> list[dict]:
    try:
        return cache.get_port_forecast(port_code)
    except Exception as exc:
        raise _handle_error(exc)


@router.get("/model/{port_code}/regime")
def model_regime(port_code: str) -> dict:
    try:
        return cache.get_port_regime(port_code)
    except Exception as exc:
        raise _handle_error(exc)


@router.get("/model/{port_code}/decision")
def model_decision(port_code: str) -> dict:
    try:
        return cache.get_port_decision(port_code)
    except Exception as exc:
        raise _handle_error(exc)


@router.get("/model/{port_code}/chain")
def model_chain(port_code: str) -> dict:
    """The full evidence chain for one port, in the order a judge asks for it.

    RAW SIGNAL -> EXPERT -> REGIME -> FORECAST -> DECISION.
    """
    port = port_registry.resolve(port_code)
    if port is None:
        raise HTTPException(status_code=404, detail=f"Unknown port: {port_code}")

    try:
        states = cache.get_port_state()
    except cache.CacheNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    state = states.get(port.locode)
    if state is None:
        raise HTTPException(status_code=404,
                            detail=f"No observed state for port: {port.locode}")

    try:
        forecast = cache.get_port_forecast(port.locode)
    except (KeyError, cache.CacheNotReadyError):
        forecast = []
    try:
        regime = cache.get_port_regime(port.locode)
    except (KeyError, cache.CacheNotReadyError):
        regime = None
    try:
        decision = cache.get_port_decision(port.locode)
    except (KeyError, cache.CacheNotReadyError):
        decision = None

    day1 = forecast[0] if forecast else {}
    return {
        "portCode": port.locode,
        "name": port.name,
        "stages": [
            {
                "stage": "RAW SIGNAL",
                "label": "Satellite-AIS port calls, weather, events",
                "observedAt": state.get("observedAt"),
                "status": state.get("dataStatus"),
                "metrics": {
                    "vesselCalls": state.get("vesselCalls"),
                    "anchorageCount": state.get("anchorageCount"),
                    "throughputTonnes": state.get("throughputTonnes"),
                    "weatherImpact": state.get("weatherImpact"),
                },
                "confidence": state.get("aisConfidence"),
            },
            {
                "stage": "EXPERT",
                "label": "Capacity, anomaly, arrival dynamics, disruption",
                "observedAt": state.get("observedAt"),
                "status": state.get("dataStatus"),
                "metrics": {
                    "queuePressure": state.get("queuePressure"),
                    "capacityPressure": state.get("capacityPressure"),
                    "anomalyScore": state.get("anomalyScore"),
                    "arrivalClustering": state.get("arrivalClustering"),
                    "disruptionPressure": state.get("disruptionPressure"),
                },
                "confidence": state.get("dataQuality"),
            },
            {
                "stage": "REGIME",
                "label": "HSMM operational state and dwell",
                "observedAt": (regime or {}).get("observedAt"),
                "status": (regime or {}).get("dataStatus"),
                "metrics": {
                    "state": (regime or {}).get("state"),
                    "daysInState": (regime or {}).get("daysInState"),
                    "expectedRemainingDays": (regime or {}).get("expectedRemainingDays"),
                    "transitionRisk24h": (regime or {}).get("transitionRisk24h"),
                },
                "confidence": (regime or {}).get("confidence"),
            },
            {
                "stage": "FORECAST",
                "label": "Adaptive ensemble quantile forecast",
                "observedAt": day1.get("originDate"),
                "status": day1.get("dataStatus"),
                "metrics": {
                    "q10": day1.get("q10"),
                    "q50": day1.get("q50"),
                    "q90": day1.get("q90"),
                    "modelDisagreement": day1.get("modelDisagreement"),
                    "model": day1.get("source"),
                },
                "confidence": day1.get("confidence"),
            },
            {
                "stage": "DECISION",
                "label": "Operational action and expected impact",
                "observedAt": (decision or {}).get("originDate"),
                "status": day1.get("dataStatus"),
                "metrics": {
                    "action": (decision or {}).get("action"),
                    "target": (decision or {}).get("target"),
                    "expectedDelaySavedHours": (decision or {}).get("expectedDelaySavedHours"),
                    "alternativeAction": (decision or {}).get("alternativeAction"),
                },
                "confidence": (decision or {}).get("confidence"),
            },
        ],
        "decision": decision,
        "regime": regime,
        "forecast": forecast,
        "state": state,
    }
