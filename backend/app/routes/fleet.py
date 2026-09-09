"""Fleet board -- served straight from the route optimizer output.

Each row is a vessel the optimizer scored against the live forecast: its
intended port, the recommended port, the ETA and risk difference between them,
and the buffer it should carry. Nothing is invented here.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.services import cache_service as cache

router = APIRouter()


@router.get("/fleet")
def fleet() -> list[dict]:
    return cache.get_fleet()
