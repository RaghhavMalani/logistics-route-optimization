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
from src.portwatch_os.clock import get_clock, wall_now

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


def _licence_mode() -> dict:
    from src.portwatch_os.deployment import resolve_mode

    mode, source, problem = resolve_mode(None)
    return {
        "mode": mode,
        "source": source,
        "stated": source != "default",
        "warning": problem,
    }


def durable_stores() -> dict:
    """What must survive a restart, and whether it will: the ledger, the
    advisory register and the assumption journal, each probed on its own
    path, with the state directory it lives in and how it was chosen."""
    import os

    from src.portwatch_os.advisories.store import probe_advisory_store
    from src.portwatch_os.finance.basis import AssumptionJournal
    from src.portwatch_os.ledger.store import probe_ledger
    from src.utils.config import STATE_DIR

    ledger = probe_ledger()
    advisories = probe_advisory_store()
    assumptions = AssumptionJournal().probe()
    return {
        "stateDir": str(STATE_DIR),
        "stateDirSource": "PORTWATCH_STATE_DIR" if os.environ.get("PORTWATCH_STATE_DIR") else "default (outputs/)",
        "ok": ledger["ok"] and advisories["ok"] and assumptions["ok"],
        "ledger": ledger,
        "advisories": advisories,
        "costAssumptions": assumptions,
        "ephemeral": ["decision engine memory (recomputable; the ledger holds every problem)",
                      "scenario branches", "mission replays", "agent runs", "telemetry", "world state and caches"],
    }


@router.get("/health")
def health_check() -> dict:
    now = wall_now()  # wall-clock: serverTimeUtc is the server's own time
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

    # The durable stores, probed rather than assumed: a ledger that will not
    # open is reported here with its path, and the readiness page refuses.
    stores = durable_stores()

    payload = {
        "status": "ok" if artefacts["forecast"] and stores["ok"] else "degraded",
        "service": "india-portwatch-backend",
        "serverTimeUtc": now.isoformat(),
        # The world's own clock: LIVE reads the wall; a replay, mission or
        # scenario reads its anchor and says how far from the wall it sits.
        "worldClock": get_clock().describe(),
        # The licence mode in force and whether anyone stated it. A default is
        # reported as a default: the most restrictive mode, chosen by nobody.
        "licenceMode": _licence_mode(),
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
        "durableStores": stores,
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
