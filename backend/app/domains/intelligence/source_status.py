"""Public source health built from retained evidence and the licence catalogue."""

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from src.portwatch_os.clock import wall_now
from src.portwatch_os.fabric.products import ProductCatalogue
from src.portwatch_os.freshness.reviewed_sources import (
    ECB_RATES, PUBLISHED_MAX_AGE, REVIEW_DECISIONS, REVIEWED_TRIAL,
    ecb_readings, forecast_readings, permits_publication,
)
from src.portwatch_os.freshness.source_snapshots import configured_store
from src.portwatch_os.intelligence import free_sources

router = APIRouter(prefix="/public")

SOURCES = {
    "aisstream-websocket": "Awaiting retention and display permission. A key alone does not approve reuse; replay remains primary.",
    "gdelt-bigquery-gkg": "Private discovery trial; requires billing project, credentials and daily scan cap. Article bodies are excluded.",
    "open-meteo-marine-extended": "Modelled waves, swell and currents from Open-Meteo (CC BY 4.0). Missing port or field coverage is shown explicitly.",
    "open-meteo-ensemble": "Modelled wind member range from Open-Meteo (CC BY 4.0). For weather context only.",
    "copernicus-marine-forecast": "Awaiting a Toolbox login and a coastal forecast trial.",
    "incois-osf": "Use the official forecast link. A supported data feed and reuse terms are under review.",
    "imd-rsmc-cyclone": "Use the official bulletin link. Reproduction requires permission.",
    "nho-navarea-viii": "Existing retained warning context. Scheduled snapshot trial pending.",
    "frankfurter-ecb-fx": "Daily EUR reference rates from ECB statistics via Frankfurter. No publication on weekends or ECB closure days.",
    "gdelt-events": "Existing discovery context. The shorter query window is trial only.",
    "pib-ports-rss": "Use the official release links. Feed terms and Ministry filtering are under review.",
    "imf-portwatch-data": "Lagged daily aggregates for Paradip. The latest retained data date sets the displayed age.",
}

class SourceHealth(BaseModel):
    id: str
    name: str
    provider: str
    status: Literal["live", "stale", "unavailable"]
    detail: str
    termsUrl: str | None = None
    homepage: str | None = None
    lastSuccess: datetime | None = None
    observedAt: datetime | None = None
    successRate7d: float | None = None
    attempts7d: int = 0
    medianLagSeconds: float | None = None
    dataAgeSeconds: float | None = None
    availableAt: datetime | None = None
    validThrough: datetime | None = None
    lastError: str | None = None
    lastErrorAt: datetime | None = None
    core: bool = False
    policySeconds: float | None = None
    portsCurrent: int | None = None
    portsTotal: int | None = None
    circuit: str | None = None
    trial: dict | None = None


class SourceStatus(BaseModel):
    checkedAt: datetime
    sources: list[SourceHealth]
    scheduler: dict = {}
    degraded: bool = False


class ReadingValue(BaseModel):
    label: str
    value: str | None
    unit: str
    detail: str | None = None


class SourceReading(BaseModel):
    label: str
    validAt: datetime
    values: list[ReadingValue]


def _retained_imf(now: datetime) -> dict:
    try:
        record = free_sources.public_product("imf", at=now)
        rows = record["rows"]
        if not rows:
            return {}
        dates = [free_sources.imf_date(row.get("date")) for row in rows]
        observed = max((day for day in dates if day is not None and day <= now), default=None)
        last_check = record["lastSuccessfulCheckAt"]
        return {
            "status": "live" if observed and record["freshness"] == "CURRENT" else "stale",
            "lastSuccess": free_sources.instant(last_check) if last_check else None,
            "observedAt": observed,
        }
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return {}


@router.get("/sources", response_model=SourceStatus)
def source_status() -> dict:
    # wall-clock: provider freshness describes the actual present, including during replay.
    now = wall_now()
    catalogue = ProductCatalogue()
    from src.portwatch_os.freshness.source_trials import configured
    trial = configured()
    rows = []
    for key, detail in SOURCES.items():
        provider, product = catalogue.product(key)
        metrics: dict = {"status": "unavailable"}
        if permits_publication(product):
            try:
                store = configured_store()
                if store is not None:
                    metrics.update(store.health("published", key, now, PUBLISHED_MAX_AGE[key]))
                    metrics["policySeconds"] = PUBLISHED_MAX_AGE[key].total_seconds()
                    sample = store.latest("published", key)
                    if sample and key.startswith("open-meteo-"):
                        forecast_metrics, _ = forecast_readings(sample, key, now)
                        metrics.update(forecast_metrics)
                else:
                    detail = "Snapshot storage is unavailable."
            except (SQLAlchemyError, ValueError):
                detail = "Snapshot storage is unavailable."
        elif key == "imf-portwatch-data":
            metrics.update(_retained_imf(now))
        if trial and key in trial['products']:
            try:
                coverage = {}
                store = configured_store()
                if store is not None:
                    measured = store.health(trial['scope'], key, min(now, trial['end']), timedelta(hours=6))
                    coverage = {k: measured[k] for k in ('attempts7d', 'successRate7d', 'medianLagSeconds', 'lastSuccess', 'lastError')}
                    sample = store.latest(trial['scope'], key)
                    if sample:
                        coverage.update({'coverageKeys': len(sample.payload.get('coverage', {})),
                            'precision': sample.payload.get('precision'),
                            'ports': {code: {'error': row.get('error'), 'finiteValues': row.get('finiteValues', {})}
                                      for code, row in sample.payload.get('ports', {}).items()}})
                decision = REVIEW_DECISIONS.get(key) if trial['scope'] == REVIEWED_TRIAL and now >= trial['end'] else None
                metrics['trial'] = {'startedAt': trial['start'], 'endsAt': trial['end'],
                    'phase': 'in progress' if now < trial['end'] else 'completed', 'decision': decision or 'pending', **coverage}
            except (SQLAlchemyError, ValueError):
                detail = 'Private trial storage is unavailable; candidate data is unpublished.'
        observed = metrics.get("observedAt") or metrics.get("availableAt")
        rows.append(SourceHealth(
            id=key, name=product.name, provider=provider.name, detail=detail,
            termsUrl=product.policy.evidence.terms_url, homepage=provider.homepage,
            dataAgeSeconds=max(0, (now - observed).total_seconds()) if observed else None,
            **metrics,
        ))
    from src.portwatch_os.freshness.truth import core_sources
    core, scheduler = core_sources(now)
    ids = {row['id'] for row in core}
    rows = [row for row in rows if row.id not in ids] + [SourceHealth(**row) for row in core]
    return SourceStatus(checkedAt=now, sources=rows, scheduler=scheduler,
                        degraded=bool(scheduler.get('journalError')) or any(row['status'] != 'live' for row in core)).model_dump()


@router.get("/source-readings/{key}", response_model=list[SourceReading])
def source_readings(key: str) -> list[dict]:
    if key not in PUBLISHED_MAX_AGE:
        return []
    _, product = ProductCatalogue().product(key)
    if not permits_publication(product):
        return []
    try:
        store = configured_store()
        sample = store.latest("published", key) if store else None
        now = wall_now()  # wall-clock: provider readings must be valid in the real present.
        if sample and key.startswith("open-meteo-"):
            _, readings = forecast_readings(sample, key, now)
            return readings
        if sample and key == ECB_RATES:
            return ecb_readings(sample, now)
    except (SQLAlchemyError, ValueError):
        pass
    return []
