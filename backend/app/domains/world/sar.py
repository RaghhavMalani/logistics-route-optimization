"""Vessel-activity endpoints.

India PortWatch does not have a per-vessel AIS licence, so this route never
pretends to track individual ships. What it serves are the measured daily
port-call aggregates from the IMF PortWatch satellite-AIS feed, plus the queue
buildup derived from each port's own backward-looking baseline. The payload
states that basis explicitly so the map can label it correctly.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.services import cache_service as cache
from src.utils import port_registry

router = APIRouter()


@router.get("/sar/vessels")
def vessel_activity() -> dict:
    return cache.get_vessels()


@router.get("/sar/feed-adapters")
def feed_adapters() -> list[dict]:
    """Which vessel-activity feeds are wired, and what each one really is."""
    provenance = cache.get_provenance().get("sources", {})
    ais = provenance.get("AIS / vessel activity", {})
    return [
        {
            "key": "PORTWATCH_AIS",
            "name": "IMF PortWatch satellite-AIS daily aggregates",
            "status": ais.get("status", "UNAVAILABLE"),
            "provider": ais.get("provider", "IMF PortWatch"),
            "observedAt": ais.get("observed_at"),
            "ageHours": ais.get("ageHours"),
            "confidence": ais.get("confidence"),
            "detail": ais.get("detail", ""),
            "granularity": "daily port aggregate",
        },
        {
            "key": "SAR_SENTINEL1",
            "name": "Sentinel-1 SAR vessel detection",
            "status": "UNAVAILABLE",
            "provider": "Copernicus / Google Earth Engine",
            "observedAt": None,
            "ageHours": None,
            "confidence": 0.0,
            "detail": "Not wired in this deployment. No SAR scenes are ingested, "
                      "so no SAR-derived detections are reported.",
            "granularity": "scene",
        },
    ]


@router.get("/sar/{port_code}")
def vessel_activity_for_port(port_code: str) -> dict:
    port = port_registry.resolve(port_code)
    if port is None:
        raise HTTPException(status_code=404, detail=f"Unknown port: {port_code}")

    bundle = cache.get_vessels()
    for row in bundle.get("vessels", []):
        if row.get("portCode") == port.locode:
            return {**row, "basis": bundle.get("basis")}

    raise HTTPException(
        status_code=404,
        detail=f"No vessel-activity record for {port.locode}.")
