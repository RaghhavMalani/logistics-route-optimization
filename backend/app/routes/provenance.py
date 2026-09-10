"""Data provenance endpoint.

Exposes, source by source, which of the honesty states a source is in -- live,
cached, stale, synthetic, simulated traffic, schematic or unavailable -- with the
observation and fetch timestamps, the age and the confidence each state earns.

The states come from :mod:`src.utils.provenance`, which is the only place they
are defined. A reader comparing this payload with what a screen says should find
the same word in both.
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
