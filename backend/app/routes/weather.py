from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "data" / "cache"

WEATHER_BY_PORT_PATH = CACHE_DIR / "weather_by_port.json"
WEATHER_INTEL_PATH = CACHE_DIR / "weather_intelligence.json"


def read_json(path: Path):
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"{path} not found. Run python backend/pipeline/export_support_cache.py first.",
        )

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/weather")
def weather_all() -> list[dict]:
    weather_by_port = read_json(WEATHER_BY_PORT_PATH)
    return list(weather_by_port.values())


@router.get("/weather/intelligence")
def weather_intelligence() -> dict:
    return read_json(WEATHER_INTEL_PATH)


@router.get("/weather/{port_code}")
def weather_signal(port_code: str) -> dict:
    port_code = port_code.upper()
    weather_by_port = read_json(WEATHER_BY_PORT_PATH)

    if port_code not in weather_by_port:
        raise HTTPException(status_code=404, detail=f"Weather not found for {port_code}")

    return weather_by_port[port_code]
