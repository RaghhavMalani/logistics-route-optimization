"""Two lenses on the world: trade exposure and security.

    /trade/exposure          which Indian cargo classes an event structurally reaches
    /trade/catalogue         which classes each port handles, with the sources
    /security/lens           behaviour detections over observed AIS, or UNAVAILABLE

Both refuse to say more than their inputs allow. Trade exposure is a chain
of catalogued facts with no volume on it; the security lens runs on
observed tracks only and says SECURITY ANALYTICS UNAVAILABLE under the
replay rather than presenting findings about a recording as intelligence.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.app.routes.world import _mode
from src.portwatch_os.clock import world_now

router = APIRouter()


@router.get("/trade/exposure")
def trade_exposure(
    event_id: Optional[str] = Query(None, alias="eventId"),
    port_code: Optional[str] = Query(None, alias="portCode"),
) -> Dict[str, Any]:
    """STRUCTURAL EXPOSURE of Indian cargo classes to the live register, or to one event."""
    from backend.app.routes.global_eye import _load_events
    from src.portwatch_os.trade import structural_exposure

    events, _report, _calibrator, _stamped = _load_events()
    if event_id is not None and not any(e.event_id == event_id for e in events):
        raise HTTPException(status_code=404, detail=f"no event {event_id} in the current register")
    return structural_exposure(events, event_id=event_id, port_code=(port_code or "").upper() or None)


@router.get("/trade/exposure/missions/{mission_id}")
def mission_trade_exposure(mission_id: str) -> Dict[str, Any]:
    """The same chains for a mission's event, at its replay clock."""
    from backend.app.routes.missions import _replay
    from src.portwatch_os.trade import structural_exposure

    replay = _replay(mission_id)
    return structural_exposure([replay.event()])


@router.get("/trade/catalogue")
def trade_catalogue() -> Dict[str, Any]:
    from src.portwatch_os.trade import CLASSES, DISCLAIMER, LABELS, port_classes
    from src.portwatch_os.trade.catalogue import BPS_2324

    return {
        "classes": [{"commodityClass": c, "label": LABELS[c]} for c in CLASSES],
        "links": [link.to_dict() for link in port_classes()],
        "primarySource": BPS_2324,
        "disclaimer": DISCLAIMER,
    }


@router.get("/security/lens")
def security_lens_route(
    mode: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
) -> Dict[str, Any]:
    """Behaviour detections over observed AIS. UNAVAILABLE under the replay."""
    from src.portwatch_os.fabric import ais_mode
    from src.portwatch_os.fabric.ais.client import get_client
    from src.portwatch_os.fusion.engine import get_engine
    from src.portwatch_os.security import security_lens

    active = _mode(mode)
    now = world_now()
    traffic = ais_mode(licence_mode=active, now=now)
    client = get_client()
    engine = get_engine()

    def conflicts_for(track):
        hull = engine.lookup("mmsi", track.mmsi)
        return [] if hull is None else list(hull.conflicts)

    tracks = client.store.tracks() if traffic["mode"] in ("LIVE_AIS", "AIS_STALE") else []
    return security_lens(traffic=traffic, tracks=tracks, conflicts_for=conflicts_for, now=now, limit=limit)


__all__ = ["router"]
