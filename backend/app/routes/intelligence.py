"""One global intelligence context, scoped local cameras, and forecast feedback."""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.app.identity import Identity, identity_from_headers, require_verified
from backend.app.services import cache_service as cache
from src.portwatch_os.clock import LIVE, get_clock, world_now
from src.portwatch_os.intelligence.cameras import Camera, CameraEvidence, CameraRegistry, EvidenceConflict
from src.portwatch_os.intelligence.context import economic_context
from src.portwatch_os.learning.weather_feedback import WeatherFeedback, WeatherObservation, instant
from src.portwatch_os.ledger.store import LedgerError, get_ledger
from src.portwatch_os.roles import NATIONAL_ADMIN, PORT_AUTHORITY
from src.utils import port_registry

router = APIRouter()


def identity(role: str | None = Header(None, alias="X-PortWatch-Role"),
             actor: str | None = Header(None, alias="X-PortWatch-Actor"),
             port: str | None = Header(None, alias="X-PortWatch-Port")) -> Identity:
    return identity_from_headers(role, actor, port, None, None)


def registry() -> CameraRegistry:
    from src.portwatch_os.sandbox import current_sandbox
    scoped = current_sandbox.get()
    if scoped is not None:
        return CameraRegistry(scoped.root / "cameras.sqlite3")
    return CameraRegistry()


def canonical_port(value: str | None) -> str | None:
    if value is None:
        return None
    port = port_registry.resolve(value)
    if port is None:
        raise HTTPException(404, "port is not registered")
    return port.locode


def may_write(who: Identity, port: str) -> None:
    who = require_verified()
    if get_clock().state.mode != LIVE:
        raise HTTPException(409, "Evidence and registry writes require the live clock")
    if not who.actor:
        raise HTTPException(401, "recording evidence requires a named operator")
    if who.role == NATIONAL_ADMIN:
        return
    if who.role == PORT_AUTHORITY and port in who.port_codes:
        return
    raise HTTPException(403, "only national command or this port's authority may record its evidence")


def visible_cameras(store: CameraRegistry, who: Identity, port: str | None = None) -> list[dict]:
    rows = [c for c in store.cameras() if (not port or c["portCode"] == port)
            and (c["access"] == "public" or (who.verified and (who.role == NATIONAL_ADMIN
                 or (who.role == PORT_AUTHORITY and c["portCode"] in who.port_codes))))]
    if get_clock().state.mode != LIVE:
        # There is no media archive or versioned registration history. Current registry
        # metadata is labelled as such, and no current stream URL leaves the replay API.
        return [{**c, "mediaUrl": None, "mediaAvailability": "HISTORICAL_UNAVAILABLE",
                 "healthNote": "Current registry metadata; live feeds are withheld during replay."} for c in rows]
    return [{**c, "mediaAvailability": "LIVE_UNVERIFIED"} for c in rows]


@router.get("/intelligence/context")
def context(port_code: str | None = Query(None, alias="portCode"),
            weather_variable: Literal["wind_speed", "wind_gust", "rainfall", "wave_height", "visibility"] = Query("wind_speed", alias="weatherVariable"),
            who: Identity = Depends(identity), store: CameraRegistry = Depends(registry)) -> dict:
    code = canonical_port(port_code)
    now = world_now()
    try:
        from backend.app.routes.global_eye import _load_events
        from src.portwatch_os.global_eye.exposure import build_impact
        events, _, _, _ = _load_events()
        # A live news cache cannot be used to invent historical knowledge.
        if get_clock().state.mode != LIVE:
            events = []
            news_status = "HISTORICAL_UNAVAILABLE"
        else:
            events = [e for e in events if instant(e.first_seen) <= now]
            newest = max((instant(e.last_seen) for e in events), default=None)
            news_status = "STALE" if newest and (now-newest).total_seconds() > 72*3600 else "CACHED"
        impacts = [build_impact(e).to_dict() for e in events]
        if code:
            wanted = {i["eventId"] for i in impacts if any(p["portCode"] == code for p in i.get("ports", []))}
            events = [e for e in events if e.event_id in wanted]
            impacts = [i for i in impacts if i["eventId"] in wanted]
        news = {"status": news_status, "events": [e.to_dict() for e in events[:60]], "impacts": impacts[:60], "reason": None}
    except HTTPException as exc:
        news = {"status": "UNAVAILABLE", "events": [], "impacts": [], "reason": str(exc.detail)}
    cameras = visible_cameras(store, who, code)
    return {"asOf": now.isoformat(), "clockMode": get_clock().state.mode,
            "selectedPort": code, "ports": [p.as_dict() for p in port_registry.all_ports()],
            "news": news, "economics": economic_context(cache.CACHE_DIR),
            "cameras": cameras, "cameraEvidence": store.evidence({c["id"] for c in cameras}),
            "weatherFeedback": WeatherFeedback(get_ledger()).report(code, limit=500, variable=weather_variable),
            "integration": {"name": "God's Eye View", "repository": "https://github.com/bilawalsidhu/gods-eye-view",
                "revision": "9542a5e58b19277d1f9b6698a46f69fdaa5fc5c1", "codeLicence": "MIT",
                "implemented": ["additional native globe", "global earthquakes", "PortWatch ships and events", "economic context", "port camera registry", "weather feedback", "regional ADS-B aircraft", "SGP4 stations catalogue propagation", "NHC cyclones", "OSM roads, rail and infrastructure", "non-commercial cable reference layer"],
                "pending": ["agency transit feeds", "FIRMS provider key", "radio", "surveyed camera projection", "Indian Ocean cyclone track adapter"]}}


@router.get("/intelligence/cameras")
def cameras(port_code: str | None = Query(None, alias="portCode"), who: Identity = Depends(identity),
            store: CameraRegistry = Depends(registry)) -> dict:
    rows = visible_cameras(store, who, canonical_port(port_code))
    return {"cameras": rows, "evidence": store.evidence({c["id"] for c in rows}),
            "note": "Registration does not verify stream health. Coverage applies only to the supplied viewpoint."}


@router.post("/intelligence/cameras")
def register_camera(payload: Camera, who: Identity = Depends(identity),
                    store: CameraRegistry = Depends(registry)) -> dict:
    may_write(who, payload.portCode)
    previous = store.get(payload.id)
    if previous and previous["portCode"] != payload.portCode:
        raise HTTPException(409, "a camera id cannot be moved to another port")
    return store.register(payload, who.actor)


@router.post("/intelligence/camera-evidence")
def camera_evidence(payload: CameraEvidence, who: Identity = Depends(identity),
                    store: CameraRegistry = Depends(registry)) -> dict:
    camera = store.get(payload.cameraId)
    if camera is None:
        raise HTTPException(404, "camera is not registered")
    may_write(who, camera["portCode"])
    try:
        return store.record_evidence(payload, who.actor)
    except EvidenceConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/weather/feedback")
def weather_feedback(port_code: str | None = Query(None, alias="portCode"),
                     variable: Literal["wind_speed", "wind_gust", "rainfall", "wave_height", "visibility"] | None = None,
                     limit: int = Query(100, ge=1, le=500), who: Identity = Depends(identity)) -> dict:
    code = canonical_port(port_code)
    from src.portwatch_os.sandbox import current_sandbox
    if current_sandbox.get() is not None:
        import json
        from src.portwatch_os.intelligence.current_environment import FEEDBACK_REPORT
        path = FEEDBACK_REPORT
        if not path.exists(): path = cache.CACHE_DIR / "public_weather_feedback.json"
        if path.exists():
            report = json.loads(path.read_text())
            forecasts = [r for r in report["forecasts"] if (not code or r["portCode"]==code) and (not variable or r["variable"]==variable)]
            report.update(forecasts=forecasts[:limit],matchingForecasts=len(forecasts),
                          scores=[r for r in report["scores"] if (not code or r["portCode"]==code) and (not variable or r["variable"]==variable)],
                          scope="Read-only public forecast archive; demo decisions remain visitor-owned")
            return report
    return WeatherFeedback(get_ledger()).report(code, limit=limit, variable=variable)


class ObservationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    portCode: str
    variable: Literal["wind_speed", "wind_gust", "rainfall", "wave_height", "visibility"]
    validAt: datetime
    availableAt: datetime
    value: float = Field(ge=0, allow_inf_nan=False)
    source: str = Field(min_length=1, max_length=200)
    kind: Literal["station", "operator_measurement", "reanalysis"]
    unit: str
    aggregation: Literal["daily"] = "daily"
    statistic: Literal["maximum", "mean", "sum"]


@router.post("/weather/observations")
def weather_observation(payload: ObservationInput, who: Identity = Depends(identity)) -> dict:
    code = canonical_port(payload.portCode)
    may_write(who, code)
    observation = WeatherObservation(code, payload.variable, payload.validAt.isoformat(),
        payload.availableAt.isoformat(), payload.value, payload.source, payload.kind, payload.unit, payload.aggregation, payload.statistic)
    try:
        count = WeatherFeedback(get_ledger()).observe(observation)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"resolved": count, "portCode": code, "variable": payload.variable,
            "recordedBy": who.actor, "note": "Only existing forecasts of this daily variable, port and target were resolved."}


_QUAKES: dict = {}
_QUAKE_LOCK = threading.Lock()


@router.get("/intelligence/earthquakes")
def earthquakes(who: Identity = Depends(identity)) -> dict:
    """Fixed USGS provider, bounded request; no arbitrary URL proxy."""
    if get_clock().state.mode != LIVE:
        raise HTTPException(409, "live earthquake observations are unavailable in a historical or scenario clock")
    now = world_now()
    with _QUAKE_LOCK:
        fresh = _QUAKES.get("at") and (now-_QUAKES["at"]).total_seconds() < 300
        if fresh:
            return _QUAKES["payload"]
        try:
            import requests
            response = requests.get("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson", timeout=(3, 8))
            response.raise_for_status()
            data = response.json()
            if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
                raise ValueError("USGS response is not a feature collection")
            data["portwatch"] = {"status": "LIVE", "fetchedAt": now.isoformat(), "source": "USGS"}
            _QUAKES.update(payload=data, at=now)
            return data
        except (requests.RequestException, ValueError) as exc:
            if _QUAKES.get("payload") and (now-_QUAKES["at"]).total_seconds() < 3600:
                return {**_QUAKES["payload"], "portwatch": {"status": "STALE", "fetchedAt": _QUAKES["at"].isoformat(), "source": "USGS"}}
            raise HTTPException(503, "USGS earthquake feed is unavailable") from exc
