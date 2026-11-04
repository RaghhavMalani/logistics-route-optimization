"""Marine weather endpoints.

Serves the measured Open-Meteo conditions the weather expert consumed, together
with the risk decomposition the model used and the shock-vs-persistence split.
Fields the feed could not supply are ``null`` rather than filled in.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.services import cache_service as cache
from src.utils import port_registry

router = APIRouter()


def _bundle() -> dict:
    try:
        return cache.get_weather_by_port()
    except cache.CacheNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/weather")
def weather_all() -> list[dict]:
    return list(_bundle().values())


@router.get("/weather/intelligence")
def weather_intelligence() -> dict:
    try:
        return cache.get_weather_intelligence()
    except cache.CacheNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/weather/{port_code}")
def weather_signal(port_code: str) -> dict:
    bundle = _bundle()
    port = port_registry.resolve(port_code)
    code = port.locode if port else port_code.upper()
    if code not in bundle:
        raise HTTPException(status_code=404,
                            detail=f"No weather record for {port_code}.")
    return bundle[code]
