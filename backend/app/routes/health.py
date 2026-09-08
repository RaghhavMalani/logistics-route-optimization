"""Operational health for the digital twin.

This endpoint is the honest status line for the whole system: which artefacts
exist, how old the intelligence is, which model produced it, which data sources
are live, cached, stale or synthetic, and whether a reproducible benchmark backs
the accuracy claims. The terminal renders it verbatim -- if the twin is running
on stale data, the UI says so.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from backend.app.services import cache_service as cache

router = APIRouter()

#: Intelligence older than this is reported as stale rather than live.
LIVE_BUDGET_SECONDS = 30 * 60
STALE_BUDGET_SECONDS = 36 * 3600


def _intelligence_state(age_seconds: int | None) -> str:
    if age_seconds is None:
        return "not_ready"
    if age_seconds <= LIVE_BUDGET_SECONDS:
        return "live"
    if age_seconds <= STALE_BUDGET_SECONDS:
        return "cached"
    return "stale"


@router.get("/health")
def health_check() -> dict:
    now = datetime.now(timezone.utc)
    export_age = cache.artefact_age_seconds(cache.STATUS_CACHE)
    status = cache.get_live_status()
    provenance = cache.get_provenance()
    benchmark = cache.get_benchmark()

    artefacts = {
        "portState": cache.PORT_STATE_CACHE.exists(),
        "forecast": cache.FORECAST_CACHE.exists(),
        "regimes": cache.REGIME_CACHE.exists(),
        "decisions": cache.DECISION_CACHE.exists(),
        "pipeline": cache.PIPELINE_CACHE.exists(),
        "benchmark": cache.BENCHMARK_CACHE.exists(),
        "provenance": cache.PROVENANCE_CACHE.exists(),
        "weather": cache.WEATHER_CACHE.exists(),
        "news": cache.NEWS_CACHE.exists(),
        "vessels": cache.VESSEL_CACHE.exists(),
        "fleet": cache.FLEET_CACHE.exists(),
    }

    try:
        available_ports = cache.get_available_ports()
    except cache.CacheNotReadyError:
        available_ports = []

    payload = {
        "status": "ok" if artefacts["forecast"] else "degraded",
        "service": "india-portwatch-backend",
        "serverTimeUtc": now.isoformat(),
        "intelligence": _intelligence_state(export_age),
        "cacheAgeSeconds": export_age,
        "lastRefreshUtc": status.get("exportedAt"),
        "model": status.get("model"),
        "forecastOrigin": status.get("forecastOrigin"),
        "forecastOriginStatus": status.get("forecastOriginStatus"),
        "forecastOriginAgeHours": status.get("forecastOriginAgeHours"),
        "horizonDays": status.get("horizonDays"),
        "ports": status.get("ports"),
        "availablePorts": available_ports,
        "artefacts": artefacts,
        "benchmark": {
            "available": bool(benchmark.get("available")),
            "version": benchmark.get("version"),
            "generatedAt": benchmark.get("generatedAt"),
            "bestModel": (benchmark.get("summary") or {}).get("bestModel"),
            "folds": (benchmark.get("summary") or {}).get("folds"),
        },
        "sources": {
            "readiness": provenance.get("readiness", 0.0),
            "live": provenance.get("live", []),
            "cached": provenance.get("cached", []),
            "stale": provenance.get("stale", []),
            "synthetic": provenance.get("synthetic", []),
            "unavailable": provenance.get("unavailable", []),
        },
    }
    return payload
