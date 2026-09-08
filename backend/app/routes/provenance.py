"""Data provenance endpoint.

Exposes, source by source, whether the twin is running on live measurements,
cached measurements, stale measurements or a synthetic stand-in -- including the
observation and fetch timestamps, the age and the confidence each state earns.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.services import cache_service as cache

router = APIRouter()


@router.get("/provenance")
def provenance() -> dict:
    payload = cache.get_provenance()
    if not payload.get("sources"):
        payload.setdefault("reason", cache.REBUILD_HINT)
    payload["cacheAgeSeconds"] = cache.artefact_age_seconds(cache.PROVENANCE_CACHE)
    return payload
