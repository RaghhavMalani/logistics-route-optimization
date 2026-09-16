"""The product's refresh jobs: one per artifact, each wrapping the code that
already produced that artifact by hand.

Before this module, keeping the demo current meant knowing that the event
register lapses about three days after ``run_award_demo.py --refresh``, that
the marine grid has an hour's TTL kept by its own thread, and that the port
forecasts come from a two-minute pipeline nobody would run mid-demo. The
knowledge was real and it lived in people. Here it lives in policies, and
the coordinator acts on it.

    events          GDELT + GDACS -> data/cache/news_bundle.json. The register
                    the world graph is built from. Its claims carry 72 h
                    horizons, so a bundle older than that is a world with
                    nothing live in it.
    marine          Open-Meteo Marine -> the process grid and its disk cache.
                    Licence-gated exactly as the adapter is.
    port_forecast   the full pipeline (IMF PortWatch, weather, macro, the
                    ensemble) -> data/cache/*.json. Daily; it is the one job
                    that takes minutes, and it runs in a subprocess so a
                    failure cannot take the API with it.
    macro           FRED series, refreshed by the same pipeline run; probed
                    separately so its own age is visible.
    port_weather    Open-Meteo surface forecast per port, likewise.
    news            model-derived port alerts, likewise.
    traffic         the AIS feed. Not a file to rebuild but a socket to keep
                    open: its "refresh" is a reconnect, bounded like the rest,
                    and its state is SIMULATED when the replay was chosen or
                    NOT_APPLICABLE when no source may be used here.
    world           the versioned live world and its cascades. Derived: it is
                    fed by events and traffic, invalidated when they change,
                    and never refreshed on a clock of its own.

Every probe reads the artifact's own recorded instant. No job writes one
anywhere except by producing a new artifact.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.portwatch_os import telemetry
from src.portwatch_os.clock import wall_now
from src.portwatch_os.freshness.coordinator import RefreshCoordinator
from src.portwatch_os.freshness.job import JobOutcome, RefreshContext, RefreshJob
from src.portwatch_os.freshness.policy import (
    ArtifactProbe,
    FreshnessPolicy,
    NOT_APPLICABLE,
    SIMULATED,
)

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "data" / "cache"
NEWS_BUNDLE = CACHE_DIR / "news_bundle.json"
LIVE_STATUS = CACHE_DIR / "live_status.json"
PROVENANCE = CACHE_DIR / "provenance.json"
WEATHER_BY_PORT = CACHE_DIR / "weather_by_port.json"
FORECAST_BY_PORT = CACHE_DIR / "forecast_by_port.json"

#: Provenance entries the pipeline records, by artifact.
PROVENANCE_KEYS = {
    "port_forecast": "Port activity (IMF PortWatch)",
    "macro": "Macro: oil / FX / inflation (FRED)",
    "port_weather": "Marine weather (Open-Meteo)",
}

#: Environment switch: the pipeline job is the only one that costs minutes
#: of CPU, and a machine running the benchmark suite may not want it started
#: by the scheduler. It is never silent: the artifact still reports EXPIRED.
PIPELINE_AUTOSTART_ENV = "PORTWATCH_PIPELINE_AUTOREFRESH"


def _parse(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _mtime(path: Path) -> Optional[datetime]:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_atomic(path: Path, payload: Dict[str, Any]) -> int:
    """Write next to the target and rename, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = json.dumps(payload, indent=2, default=str)
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
    return len(body)


# --------------------------------------------------------------------------
# events: the register
# --------------------------------------------------------------------------

EVENTS_POLICY = FreshnessPolicy(
    artifact="events", label="Event register (GDELT + GDACS)", provider="GDELT DOC 2.0 + GDACS",
    fresh_for=timedelta(hours=6), lead=timedelta(hours=1), stale_after=timedelta(hours=72),
    max_attempts=3, backoff_base=timedelta(seconds=30), backoff_cap=timedelta(minutes=15),
    feeds=("world",),
    rationale=(
        "GDELT publishes every fifteen minutes and the connector caches for three hours; a six-hour "
        "SLA keeps the register within one connector cycle of the feed. Claims carry 72 h horizons, "
        "so past 72 h the register is a world with nothing live in it and is labelled stale."
    ),
)


def probe_events() -> ArtifactProbe:
    bundle = _read_json(NEWS_BUNDLE)
    if bundle is None:
        return ArtifactProbe(observed_at=None, reason="no news bundle has been produced")
    events = bundle.get("events") or []
    newest = max((_parse(e.get("timestamp")) for e in events), default=None)
    # The bundle's own stamp, when a refresh wrote one; the export's stamp,
    # when the pipeline produced it; the file's mtime as the last resort.
    observed = _parse(bundle.get("refreshedAt")) or _parse((_read_json(LIVE_STATUS) or {}).get("exportedAt"))
    if observed is None:
        observed = _mtime(NEWS_BUNDLE)
    return ArtifactProbe(
        observed_at=observed, source_timestamp=newest,
        detail={"events": len(events), "alerts": len(bundle.get("alerts") or []),
                "dataSource": (bundle.get("summary") or {}).get("dataSource")},
    )


def refresh_events(context: RefreshContext) -> JobOutcome:
    """Rebuild the news bundle from the connectors, keeping the model's alerts."""
    from backend.pipeline.export_support_cache import build_news_cache
    from src.ingestion.connectors import port_events

    before = _read_json(NEWS_BUNDLE) or {}
    events = port_events.collect_events()
    if events is None or events.empty:
        raise RuntimeError("no event source returned usable records; the last known register stays in place")
    catalogue = port_events.build_event_catalogue(events)
    bundle = build_news_cache(catalogue)
    if not bundle.get("events"):
        raise RuntimeError("the rebuilt bundle carries no events; the last known register stays in place")
    stamp = wall_now()  # wall-clock: the register was rebuilt in the real present
    bundle["refreshedAt"] = stamp.isoformat(timespec="seconds")
    bundle["refreshedBy"] = f"freshness coordinator ({context.reason})"
    written = _write_atomic(NEWS_BUNDLE, bundle)
    old_ids = {(e.get("id"), e.get("timestamp")) for e in before.get("events") or []}
    new_ids = {(e.get("id"), e.get("timestamp")) for e in bundle["events"]}
    changed = old_ids != new_ids
    telemetry.gauge("events.register.size", len(bundle["events"]))
    return JobOutcome(
        changed=changed, observed_at=stamp,
        detail={"events": len(bundle["events"]), "new": len(new_ids - old_ids), "dropped": len(old_ids - new_ids),
                "bytes": written},
    )


# --------------------------------------------------------------------------
# marine: the sea
# --------------------------------------------------------------------------

MARINE_POLICY = FreshnessPolicy(
    artifact="marine", label="Marine forecast grid (Open-Meteo)", provider="Open-Meteo Marine",
    fresh_for=timedelta(hours=1), lead=timedelta(minutes=10), stale_after=timedelta(hours=3),
    max_attempts=4, backoff_base=timedelta(seconds=20), backoff_cap=timedelta(minutes=10),
    rationale=(
        "The service publishes no model-run time, so freshness is the fetch's age. The adapter's own "
        "TTL is an hour and its stale threshold three; the policy states the same numbers."
    ),
)


def _marine_adapter():
    from src.portwatch_os.fabric.marine import OpenMeteoMarineAdapter, get_service
    from src.portwatch_os.fabric.model import deployment_mode

    return OpenMeteoMarineAdapter(licence_mode=deployment_mode(), service=get_service())


def marine_eligibility() -> Optional[str]:
    barred = _marine_adapter().licence_gate()
    return None if barred is None else barred.reason


def probe_marine() -> ArtifactProbe:
    from src.portwatch_os.fabric.marine import get_service

    barred = marine_eligibility()
    if barred is not None:
        return ArtifactProbe(observed_at=None, override_state=NOT_APPLICABLE, reason=barred)
    service = get_service()
    grid = service.grid(allow_fetch=False)
    status = service.status()
    if grid is None or grid.fetched_at is None:
        return ArtifactProbe(observed_at=None, reason=status.get("lastError") or "no grid fetched yet",
                             detail={"productId": status.get("productId")})
    lo, hi = grid.horizon
    return ArtifactProbe(
        observed_at=grid.fetched_at, source_timestamp=grid.fetched_at,
        detail={"cells": len(grid), "points": len(grid.points), "productId": grid.product_id,
                "horizon": [lo.isoformat() if lo else None, hi.isoformat() if hi else None],
                "lastError": status.get("lastError")},
    )


def refresh_marine(context: RefreshContext) -> JobOutcome:
    from src.portwatch_os.fabric.marine import get_service

    service = get_service()
    before = service.grid(allow_fetch=False)
    before_at = None if before is None else before.fetched_at
    grid = service.refresh()
    if grid is None:
        raise RuntimeError(service.status().get("lastError") or "the marine fetch returned no grid")
    return JobOutcome(changed=grid.fetched_at != before_at, observed_at=grid.fetched_at,
                      detail={"cells": len(grid), "points": len(grid.points), "productId": grid.product_id})


# --------------------------------------------------------------------------
# the pipeline: port forecasts, weather, macro, alerts
# --------------------------------------------------------------------------

PIPELINE_POLICY = FreshnessPolicy(
    artifact="port_forecast", label="Port forecasts (pipeline export)", provider="IMF PortWatch + ensemble",
    fresh_for=timedelta(hours=24), lead=timedelta(hours=2), stale_after=timedelta(hours=36),
    max_attempts=2, backoff_base=timedelta(minutes=5), backoff_cap=timedelta(minutes=30),
    feeds=("macro", "port_weather", "news"),
    rationale=(
        "IMF PortWatch is daily and lags about ten days; the pipeline re-exports once a day and the "
        "source lag is reported separately as sourceLagSeconds rather than hidden in the export's age."
    ),
)

MACRO_POLICY = FreshnessPolicy(
    artifact="macro", label="Macro series (FRED)", provider="FRED",
    fresh_for=timedelta(hours=24), stale_after=timedelta(days=7),
    rationale="Daily series; refreshed by the pipeline run and probed on its own.",
)

PORT_WEATHER_POLICY = FreshnessPolicy(
    artifact="port_weather", label="Port weather forecast (Open-Meteo)", provider="Open-Meteo",
    fresh_for=timedelta(hours=24), stale_after=timedelta(hours=48),
    rationale="A ten-day surface forecast per port; refreshed by the pipeline run and probed on its own.",
)

NEWS_POLICY = FreshnessPolicy(
    artifact="news", label="Port alerts (model-derived)", provider="decision engine export",
    fresh_for=timedelta(hours=24), stale_after=timedelta(hours=36),
    rationale="Alerts are read off the pipeline's decisions; they are as fresh as the last export.",
)


def probe_pipeline_export() -> ArtifactProbe:
    status = _read_json(LIVE_STATUS) or {}
    provenance = (_read_json(PROVENANCE) or {}).get("sources") or {}
    exported = _parse(status.get("exportedAt")) or _mtime(FORECAST_BY_PORT)
    if exported is None:
        return ArtifactProbe(observed_at=None, reason="the pipeline has not exported its caches")
    activity = provenance.get(PROVENANCE_KEYS["port_forecast"]) or {}
    return ArtifactProbe(
        observed_at=exported, source_timestamp=_parse(activity.get("observed_at")),
        detail={"model": status.get("model"), "ports": status.get("ports"),
                "forecastOrigin": status.get("forecastOrigin"),
                "forecastOriginStatus": status.get("forecastOriginStatus"),
                "sourceStatus": activity.get("status")},
    )


def _probe_from_provenance(key: str, fallback: Path) -> ArtifactProbe:
    provenance = (_read_json(PROVENANCE) or {}).get("sources") or {}
    entry = provenance.get(key)
    if not entry:
        stamp = _mtime(fallback)
        return ArtifactProbe(observed_at=stamp, reason="" if stamp else f"no provenance entry for {key}")
    fetched = _parse(entry.get("fetched_at")) or _parse(entry.get("recorded_at"))
    return ArtifactProbe(
        observed_at=fetched, source_timestamp=_parse(entry.get("observed_at")),
        detail={"status": entry.get("status"), "provider": entry.get("provider"), "rows": entry.get("rows"),
                "fallback": entry.get("fallback")},
    )


def probe_macro() -> ArtifactProbe:
    return _probe_from_provenance(PROVENANCE_KEYS["macro"], CACHE_DIR / "fred_DEXINUS.txt")


def probe_port_weather() -> ArtifactProbe:
    return _probe_from_provenance(PROVENANCE_KEYS["port_weather"], WEATHER_BY_PORT)


def probe_news() -> ArtifactProbe:
    status = _read_json(LIVE_STATUS) or {}
    bundle = _read_json(NEWS_BUNDLE) or {}
    exported = _parse(status.get("exportedAt")) or _mtime(NEWS_BUNDLE)
    return ArtifactProbe(observed_at=exported, detail={"alerts": len(bundle.get("alerts") or [])})


def pipeline_eligibility() -> Optional[str]:
    value = (os.getenv(PIPELINE_AUTOSTART_ENV) or "1").strip().lower()
    if value in ("0", "false", "no", "off"):
        return f"{PIPELINE_AUTOSTART_ENV}={value}: the pipeline is not started by the scheduler on this machine"
    return None


def refresh_pipeline(context: RefreshContext) -> JobOutcome:
    """Run the pipeline in a subprocess. Minutes, not seconds."""
    before = probe_pipeline_export().observed_at
    source = os.getenv("PORTWATCH_SOURCE", "portwatch")
    model = os.getenv("PORTWATCH_MODEL", "ensemble")
    command = [sys.executable, str(ROOT / "run_award_demo.py"), "--source", source, "--model", model, "--refresh"]
    log.info("pipeline refresh: %s", " ".join(command))
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=45 * 60)
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()[-5:]
        raise RuntimeError(f"pipeline exited {completed.returncode}: " + " | ".join(tail))
    after = probe_pipeline_export()
    return JobOutcome(changed=after.observed_at != before, observed_at=after.observed_at,
                      detail={"source": source, "model": model, **after.detail})


# --------------------------------------------------------------------------
# traffic: the feed
# --------------------------------------------------------------------------

TRAFFIC_POLICY = FreshnessPolicy(
    artifact="traffic", label="Vessel traffic (AIS)", provider="AISStream",
    fresh_for=timedelta(minutes=10), lead=timedelta(minutes=2), stale_after=timedelta(hours=1),
    max_attempts=5, backoff_base=timedelta(seconds=15), backoff_cap=timedelta(minutes=5),
    feeds=("world",),
    rationale=(
        "A transponder reports every few seconds; ten minutes without a valid observation is the "
        "client's own AIS_STALE threshold, and an hour its lapse. The refresh is a reconnect."
    ),
)


def _traffic_mode() -> Dict[str, Any]:
    from src.portwatch_os.fabric import ais_mode
    from src.portwatch_os.fabric.model import deployment_mode

    return ais_mode(licence_mode=deployment_mode())


def traffic_eligibility() -> Optional[str]:
    from src.portwatch_os.fabric.ais.client import get_client

    mode = _traffic_mode()
    if mode["mode"] == "UNAVAILABLE" and mode.get("providerId") is None:
        return "no traffic source this deployment may legally use is configured"
    if mode["mode"] == "SIMULATED_TRAFFIC":
        return "the deterministic replay was chosen; there is no feed to reconnect"
    if not get_client().configured:
        return "no AISSTREAM_API_KEY is configured; the feed cannot be opened"
    return None


def probe_traffic() -> ArtifactProbe:
    from src.portwatch_os.fabric.ais.client import get_client

    mode = _traffic_mode()
    if mode["mode"] == "SIMULATED_TRAFFIC":
        return ArtifactProbe(observed_at=None, override_state=SIMULATED, reason=mode.get("statement", ""),
                             detail={"mode": mode["mode"], "providerId": mode.get("providerId")})
    if mode["mode"] == "UNAVAILABLE" and mode.get("providerId") is None:
        return ArtifactProbe(observed_at=None, override_state=NOT_APPLICABLE, reason=mode.get("statement", ""),
                             detail={"mode": mode["mode"]})
    status = get_client().status
    return ArtifactProbe(
        observed_at=status.last_good_observation_at, source_timestamp=status.last_good_observation_at,
        reason=mode.get("statement", ""),
        detail={"mode": mode["mode"], "health": status.health, "messagesSeen": status.messages_seen,
                "lastError": status.last_error, "configured": get_client().configured},
    )


def refresh_traffic(context: RefreshContext) -> JobOutcome:
    """Reconnect a configured feed that has gone quiet."""
    from src.portwatch_os.fabric.ais.client import get_client

    client = get_client()
    if not client.configured:
        return JobOutcome(skipped_reason="no key configured")
    before = client.status.last_good_observation_at
    client.stop()
    client.status.reconnect_attempts += 1
    client.start()
    return JobOutcome(changed=False, observed_at=before,
                      detail={"reconnectAttempts": client.status.reconnect_attempts, "health": client.status.health})


# --------------------------------------------------------------------------
# world: derived, invalidated, never scheduled
# --------------------------------------------------------------------------

WORLD_POLICY = FreshnessPolicy(
    artifact="world", label="Live world and cascades (derived)", provider="World State Engine",
    fresh_for=timedelta(hours=72), stale_after=timedelta(hours=72),
    rationale=(
        "The world is versioned by what it was built from; it is rebuilt when the register, the fleet "
        "or the observed hulls change and never on a clock. Its 'age' is when the current build was made."
    ),
)


def probe_world() -> ArtifactProbe:
    from src.portwatch_os.world.live import get_live_world

    live = get_live_world()
    status = live.status()
    newest = None
    for build in list(getattr(live, "_builds", {}).values()):
        if newest is None or build.built_at > newest:
            newest = build.built_at
    return ArtifactProbe(observed_at=newest, reason="" if newest else "no world has been built in this process yet",
                         detail=status)


def invalidate_world(changed_by: str) -> None:
    """Drop the held builds so the next request rebuilds from the new inputs."""
    from src.portwatch_os.world.live import get_live_world

    live = get_live_world()
    with live._lock:  # noqa: SLF001 - the coordinator is the world's owner here
        dropped = len(live._builds)
        live._builds.clear()
        live._cascades.clear()
    telemetry.incr("world.invalidations", by_artifact=changed_by)
    telemetry.event("world.invalidations", by=changed_by, buildsDropped=dropped)
    log.info("live world invalidated by %s refresh (%d builds dropped)", changed_by, dropped)


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


def product_jobs() -> list[RefreshJob]:
    return [
        RefreshJob(policy=EVENTS_POLICY, probe=probe_events, run=refresh_events),
        RefreshJob(policy=MARINE_POLICY, probe=probe_marine, run=refresh_marine, eligibility=marine_eligibility),
        RefreshJob(policy=PIPELINE_POLICY, probe=probe_pipeline_export, run=refresh_pipeline,
                   eligibility=pipeline_eligibility),
        RefreshJob(policy=MACRO_POLICY, probe=probe_macro),
        RefreshJob(policy=PORT_WEATHER_POLICY, probe=probe_port_weather),
        RefreshJob(policy=NEWS_POLICY, probe=probe_news),
        RefreshJob(policy=TRAFFIC_POLICY, probe=probe_traffic, run=refresh_traffic, eligibility=traffic_eligibility),
        RefreshJob(policy=WORLD_POLICY, probe=probe_world, invalidate=invalidate_world),
    ]


def install_product_jobs(coordinator: RefreshCoordinator) -> RefreshCoordinator:
    for job in product_jobs():
        if job.artifact not in coordinator.artifacts():
            coordinator.register(job)
    return coordinator


__all__ = [
    "EVENTS_POLICY",
    "MACRO_POLICY",
    "MARINE_POLICY",
    "NEWS_POLICY",
    "PIPELINE_AUTOSTART_ENV",
    "PIPELINE_POLICY",
    "PORT_WEATHER_POLICY",
    "TRAFFIC_POLICY",
    "WORLD_POLICY",
    "install_product_jobs",
    "invalidate_world",
    "probe_events",
    "probe_marine",
    "probe_pipeline_export",
    "probe_traffic",
    "probe_world",
    "product_jobs",
    "refresh_events",
    "refresh_marine",
    "refresh_pipeline",
    "refresh_traffic",
]
