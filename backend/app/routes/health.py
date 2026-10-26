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
    from src.portwatch_os.sandbox import current_sandbox
    if current_sandbox.get() is not None:
        return {"mode": "DEMO", "source": "isolated session", "stated": True, "warning": None}
    from src.portwatch_os.deployment import resolve_mode

    mode, source, problem = resolve_mode(None)
    return {
        "mode": mode,
        "source": source,
        "stated": source != "default",
        "warning": problem,
    }


def release_identity() -> dict:
    """Non-secret, server-configured release binding for hosted verification.

    Unknown is intentional. Neither a request header nor a repository/cache
    timestamp can establish which application revision is actually serving.
    """
    import os
    import re

    def configured(name: str, pattern: str) -> str:
        value = os.environ.get(name, "")
        return value if re.fullmatch(pattern, value) else "UNKNOWN"

    sha = configured("PORTWATCH_RELEASE_SHA", r"[0-9a-fA-F]{40}")
    return {
        "sha": sha.lower() if sha != "UNKNOWN" else sha,
        "environment": configured("PORTWATCH_RELEASE_ENVIRONMENT", r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"),
        "provider": {
            key: configured(name, r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
            for key, name in (
                ("serviceId", "RAILWAY_SERVICE_ID"),
                ("environmentId", "RAILWAY_ENVIRONMENT_ID"),
                ("deploymentId", "RAILWAY_DEPLOYMENT_ID"),
            )
        },
        "basis": "SERVER_CONFIGURED_RELEASE_AND_PROVIDER_IDENTIFIERS",
    }


#: How long a durable-store probe is served from memory. Health is polled
#: every thirty seconds by the terminal and by a container's healthcheck, and
#: a probe opens and integrity-checks two databases; a minute's memory keeps
#: that off the request path without hiding a fault for long.
PROBE_TTL_SECONDS = 60.0
_PROBE_CACHE: dict = {"at": 0.0, "value": None}


def durable_stores(*, fresh: bool = False) -> dict:
    """What must survive a restart, and whether it will: the ledger, the
    advisory register and the assumption journal, each probed on its own
    path, with the state directory it lives in and how it was chosen."""
    import os
    import time

    from src.portwatch_os.advisories.store import probe_advisory_store
    from src.portwatch_os.finance.basis import AssumptionJournal
    from src.portwatch_os.ledger.store import probe_ledger
    from src.portwatch_os.intelligence.cameras import CameraRegistry
    from backend.app.auth_store import get_auth_store
    from src.utils.config import STATE_DIR

    from src.portwatch_os.sandbox import current_sandbox
    scoped = current_sandbox.get()
    if scoped is not None:
        # A demo health response never probes operational DBs or exposes paths.
        from src.portwatch_os.ledger.store import get_ledger
        from src.portwatch_os.advisories.store import get_advisory_store
        return {"ok": True, "scope": "visitor-owned demo", "ledger": get_ledger().counts(),
                "advisories": {"ok": True}, "ephemeral": ["resettable demo generation"]}

    now = time.monotonic()
    cached = _PROBE_CACHE["value"]
    if not fresh and cached is not None and now - _PROBE_CACHE["at"] < PROBE_TTL_SECONDS:
        return cached
    ledger = probe_ledger()
    advisories = probe_advisory_store()
    assumptions = AssumptionJournal().probe()
    cameras = CameraRegistry().probe()
    identity = get_auth_store().probe()
    value = {
        "stateDir": str(STATE_DIR),
        "stateDirSource": "PORTWATCH_STATE_DIR" if os.environ.get("PORTWATCH_STATE_DIR") else "default (outputs/)",
        "ok": ledger["ok"] and advisories["ok"] and assumptions["ok"] and cameras["ok"] and identity["ok"],
        "ledger": ledger,
        "advisories": advisories,
        "costAssumptions": assumptions,
        "cameraRegistry": cameras,
        "identity": identity,
        "ephemeral": ["decision engine memory (recomputable; the ledger holds every problem)",
                      "scenario branches", "mission replays", "agent runs", "telemetry", "world state and caches"],
        "probedAt": __import__("src.portwatch_os.clock", fromlist=["wall_now"]).wall_now().isoformat(timespec="seconds"),  # wall-clock: when the stores were last probed
        "probeTtlSeconds": PROBE_TTL_SECONDS,
    }
    _PROBE_CACHE["at"], _PROBE_CACHE["value"] = now, value
    return value


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
        "release": release_identity(),
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
        "generationAgeHours": status.get("generationAgeHours"),
        "generationStatus": status.get("generationStatus"),
        "targetFrom": status.get("targetFrom"),
        "targetThrough": status.get("targetThrough"),
        "targetStatus": status.get("targetStatus"),
        "futureTargetDays": status.get("futureTargetDays"),
        "sourceLagNote": status.get("sourceLagNote"),
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
    from src.portwatch_os.sandbox import current_sandbox
    scoped = current_sandbox.get()
    if scoped is not None:
        payload["trafficEpoch"] = scoped.world["epoch"]
    return payload
