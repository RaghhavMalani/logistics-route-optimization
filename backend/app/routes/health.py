from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()
ROOT = Path(__file__).resolve().parents[3]
STATUS_CACHE = ROOT / "data" / "cache" / "live_status.json"


@router.get("/health")
def health_check() -> dict:
    payload = {
        "status": "ok",
        "service": "india-portwatch-backend",
        "intelligence": "not_ready",
    }
    if STATUS_CACHE.exists():
        modified = datetime.fromtimestamp(STATUS_CACHE.stat().st_mtime, tz=timezone.utc)
        age_seconds = max(0, int((datetime.now(timezone.utc) - modified).total_seconds()))
        with open(STATUS_CACHE, "r", encoding="utf-8") as fh:
            live = json.load(fh)
        payload.update({
            "intelligence": "live" if age_seconds <= 1800 else "stale",
            "cacheAgeSeconds": age_seconds,
            "lastRefreshUtc": modified.isoformat(),
            "model": live.get("model"),
            "forecastOrigin": live.get("forecastOrigin"),
            "ports": live.get("ports"),
            "pipelineSteps": live.get("pipelineSteps"),
        })
    return payload
