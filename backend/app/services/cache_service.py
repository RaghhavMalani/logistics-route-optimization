"""Read-only access to the artefact cache the pipeline writes.

The API never computes intelligence of its own: it serves exactly what
``run_award_demo.py`` exported. A missing artefact is reported as 503 with the
command that produces it, rather than being papered over with a placeholder.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "data" / "cache"

PORT_STATE_CACHE = CACHE_DIR / "port_state.json"
FORECAST_CACHE = CACHE_DIR / "forecast_by_port.json"
PIPELINE_CACHE = CACHE_DIR / "model_pipeline.json"
REGIME_CACHE = CACHE_DIR / "regime_by_port.json"
DECISION_CACHE = CACHE_DIR / "decision_by_port.json"
BENCHMARK_CACHE = CACHE_DIR / "benchmark.json"
PROVENANCE_CACHE = CACHE_DIR / "provenance.json"
VESSEL_CACHE = CACHE_DIR / "vessels.json"
FLEET_CACHE = CACHE_DIR / "fleet.json"
WEATHER_CACHE = CACHE_DIR / "weather_by_port.json"
WEATHER_INTEL_CACHE = CACHE_DIR / "weather_intelligence.json"
NEWS_CACHE = CACHE_DIR / "news_bundle.json"
STATUS_CACHE = CACHE_DIR / "live_status.json"

REBUILD_HINT = "Run `python run_award_demo.py --source portwatch` to build it."


class CacheNotReadyError(RuntimeError):
    """Raised when an artefact the caller needs has not been exported yet."""


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise CacheNotReadyError(f"{path.name} has not been exported. {REBUILD_HINT}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise CacheNotReadyError(f"{path.name} is corrupt: {exc}. {REBUILD_HINT}") from exc


def _read_json_optional(path: Path, default: Any) -> Any:
    try:
        return _read_json(path)
    except CacheNotReadyError:
        return default


def artefact_age_seconds(path: Path) -> int | None:
    if not os.path.exists(path):
        return None
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - modified).total_seconds()))


# --- primary artefacts -----------------------------------------------------
def get_port_state() -> dict[str, dict]:
    return _read_json(PORT_STATE_CACHE)


def get_model_pipeline() -> list[dict]:
    return _read_json(PIPELINE_CACHE)


def get_forecast_by_port() -> dict[str, list[dict]]:
    return _read_json(FORECAST_CACHE)


def get_regime_by_port() -> dict[str, dict]:
    return _read_json(REGIME_CACHE)


def get_decision_by_port() -> dict[str, dict]:
    return _read_json(DECISION_CACHE)


def get_benchmark() -> dict:
    return _read_json_optional(BENCHMARK_CACHE, {"available": False,
                                                 "reason": REBUILD_HINT})


def get_provenance() -> dict:
    return _read_json_optional(PROVENANCE_CACHE, {"sources": {}, "readiness": 0.0})


def get_vessels() -> dict:
    return _read_json_optional(VESSEL_CACHE, {"vessels": [], "basis": "unavailable"})


def get_fleet() -> list[dict]:
    return _read_json_optional(FLEET_CACHE, [])


def get_weather_by_port() -> dict[str, dict]:
    return _read_json(WEATHER_CACHE)


def get_weather_intelligence() -> dict:
    return _read_json(WEATHER_INTEL_CACHE)


def get_news_bundle() -> dict:
    return _read_json(NEWS_CACHE)


def get_live_status() -> dict:
    return _read_json_optional(STATUS_CACHE, {})


# --- per-port lookups ------------------------------------------------------
def get_available_ports() -> list[str]:
    return sorted(get_forecast_by_port().keys())


def get_port_forecast(port_code: str) -> list[dict]:
    forecasts = get_forecast_by_port()
    code = _resolve(port_code, forecasts)
    if code is None:
        raise KeyError(f"No forecast found for port code: {port_code}")
    return forecasts[code]


def get_port_regime(port_code: str) -> dict:
    regimes = get_regime_by_port()
    code = _resolve(port_code, regimes)
    if code is None:
        raise KeyError(f"No regime found for port code: {port_code}")
    return regimes[code]


def get_port_decision(port_code: str) -> dict:
    decisions = get_decision_by_port()
    code = _resolve(port_code, decisions)
    if code is None:
        raise KeyError(f"No decision found for port code: {port_code}")
    return decisions[code]


def _resolve(port_code: str, mapping: dict) -> str | None:
    """Resolve a port identifier against a cache keyed by UN/LOCODE."""
    from src.utils import port_registry

    direct = str(port_code).strip().upper()
    if direct in mapping:
        return direct
    port = port_registry.resolve(direct)
    if port and port.locode in mapping:
        return port.locode
    return None
