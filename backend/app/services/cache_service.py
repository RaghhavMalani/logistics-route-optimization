from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "data" / "cache"

FORECAST_CACHE = CACHE_DIR / "forecast_by_port.json"
PIPELINE_CACHE = CACHE_DIR / "model_pipeline.json"
REGIME_CACHE = CACHE_DIR / "regime_by_port.json"
DECISION_CACHE = CACHE_DIR / "decision_by_port.json"


class CacheNotReadyError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise CacheNotReadyError(
            f"{path} does not exist. Run `python backend/pipeline/export_cache.py` first."
        )

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_model_pipeline() -> list[dict]:
    return _read_json(PIPELINE_CACHE)


def get_forecast_by_port() -> dict[str, list[dict]]:
    return _read_json(FORECAST_CACHE)


def get_regime_by_port() -> dict[str, dict]:
    return _read_json(REGIME_CACHE)


def get_decision_by_port() -> dict[str, dict]:
    return _read_json(DECISION_CACHE)


def get_available_ports() -> list[str]:
    forecasts = get_forecast_by_port()
    return sorted(forecasts.keys())


def get_port_forecast(port_code: str) -> list[dict]:
    port_code = port_code.upper()
    forecasts = get_forecast_by_port()

    if port_code not in forecasts:
        raise KeyError(f"No forecast found for port code: {port_code}")

    return forecasts[port_code]


def get_port_regime(port_code: str) -> dict:
    port_code = port_code.upper()
    regimes = get_regime_by_port()

    if port_code not in regimes:
        raise KeyError(f"No regime found for port code: {port_code}")

    return regimes[port_code]


def get_port_decision(port_code: str) -> dict:
    port_code = port_code.upper()
    decisions = get_decision_by_port()

    if port_code not in decisions:
        raise KeyError(f"No decision found for port code: {port_code}")

    return decisions[port_code]