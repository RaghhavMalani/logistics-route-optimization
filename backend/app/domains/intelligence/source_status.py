"""Public source health built from retained evidence and the licence catalogue."""

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from src.portwatch_os.clock import wall_now
from src.portwatch_os.fabric.licence import ALLOWED
from src.portwatch_os.fabric.model import deployment_mode
from src.portwatch_os.fabric.products import ProductCatalogue
from src.portwatch_os.freshness.source_snapshots import configured_store
from src.portwatch_os.intelligence import free_sources

router = APIRouter(prefix="/public")

SOURCES = {
    "aisstream-websocket": "Awaiting retention permission and an AISStream key. Replay remains the primary traffic source.",
    "copernicus-marine-forecast": "Awaiting a Toolbox login and a coastal forecast trial.",
    "incois-osf": "Use the official forecast link. A supported data feed and reuse terms are under review.",
    "imd-rsmc-cyclone": "Use the official bulletin link. Reproduction requires permission.",
    "nho-navarea-viii": "Existing retained warning context. Scheduled snapshot trial pending.",
    "frankfurter-ecb-fx": "Trial only. ECB reference rates are daily.",
    "gdelt-events": "Existing discovery context. The shorter query window is trial only.",
    "pib-ports-rss": "Use the official release links. Feed terms and Ministry filtering are under review.",
    "imf-portwatch-data": "Lagged daily aggregates for Paradip. The latest retained data date sets the displayed age.",
}

# Enter a freshness budget only after the reviewed trial and publication approval.
PUBLISHED_MAX_AGE: dict[str, timedelta] = {}


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


class SourceStatus(BaseModel):
    checkedAt: datetime
    sources: list[SourceHealth]


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
    rows = []
    for key, detail in SOURCES.items():
        provider, product = catalogue.product(key)
        metrics: dict = {"status": "unavailable"}
        if (key in PUBLISHED_MAX_AGE and product.policy.redistribution == ALLOWED
                and product.policy.permits(deployment_mode())[0]):
            try:
                store = configured_store()
                if store is not None:
                    metrics.update(store.health("published", key, now, PUBLISHED_MAX_AGE[key]))
                else:
                    detail = "Snapshot storage is unavailable."
            except (SQLAlchemyError, ValueError):
                detail = "Snapshot storage is unavailable."
        elif key == "imf-portwatch-data":
            metrics.update(_retained_imf(now))
        observed = metrics.get("observedAt")
        rows.append(SourceHealth(
            id=key, name=product.name, provider=provider.name, detail=detail,
            termsUrl=product.policy.evidence.terms_url, homepage=provider.homepage,
            dataAgeSeconds=(now - observed).total_seconds() if observed else None,
            **metrics,
        ))
    return SourceStatus(checkedAt=now, sources=rows).model_dump()
