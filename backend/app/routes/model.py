from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.services.cache_service import (
    CacheNotReadyError,
    get_available_ports,
    get_model_pipeline,
    get_port_decision,
    get_port_forecast,
    get_port_regime,
)

router = APIRouter()


def _handle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CacheNotReadyError):
        return HTTPException(status_code=503, detail=str(exc))

    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc))

    return HTTPException(status_code=500, detail=str(exc))


@router.get("/model/ports")
def list_model_ports() -> list[str]:
    try:
        return get_available_ports()
    except Exception as exc:
        raise _handle_error(exc)


@router.get("/model/pipeline")
def model_pipeline() -> list[dict]:
    try:
        return get_model_pipeline()
    except Exception as exc:
        raise _handle_error(exc)


@router.get("/model/{port_code}/forecast")
def model_forecast(port_code: str) -> list[dict]:
    try:
        return get_port_forecast(port_code)
    except Exception as exc:
        raise _handle_error(exc)


@router.get("/model/{port_code}/regime")
def model_regime(port_code: str) -> dict:
    try:
        return get_port_regime(port_code)
    except Exception as exc:
        raise _handle_error(exc)


@router.get("/model/{port_code}/decision")
def model_decision(port_code: str) -> dict:
    try:
        return get_port_decision(port_code)
    except Exception as exc:
        raise _handle_error(exc)