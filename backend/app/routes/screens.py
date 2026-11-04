"""Private, tick-scoped snapshots for the four home screens."""

import asyncio
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, replace
from functools import partial
from hashlib import sha256
import inspect
import json
import logging
import re
from time import monotonic
from urllib.parse import urlencode

import brotli
from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from backend.app.identity import current_identity
from src.portwatch_os import telemetry
from src.portwatch_os.clock import get_clock
from src.portwatch_os.sandbox import current_sandbox

router = APIRouter()
log = logging.getLogger(__name__)
ROLES = {
    "company-home": "SHIPPING_COMPANY",
    "port-home": "PORT_AUTHORITY",
    "vessel-home": "VESSEL_OPERATOR",
    "admin-home": "NATIONAL_ADMIN",
}
TICK_SECONDS = 15
MAX_ENTRIES = 96


@dataclass(frozen=True)
class Packet:
    json: bytes
    compressed: bytes
    etag: str
    expires: float


_cache = OrderedDict()
_inflight: dict[tuple, asyncio.Task] = {}


def invalidate(namespace: str | None):
    # A verified write can affect the other operational roles. A demo write is
    # confined to its visitor. The generation also guards in-flight snapshots.
    for key in tuple(_cache):
        if key[0] == namespace:
            _cache.pop(key, None)
    for key in tuple(_inflight):
        if key[0] == namespace:
            _inflight.pop(key, None)


@contextmanager
def _screen_identity(request: Request, role: str, prefetch: bool):
    who = current_identity.get()
    sandbox = current_sandbox.get()
    if who is None or (sandbox is None and not who.verified):
        raise HTTPException(401, "A verified workspace session is required")
    session = getattr(request.state, "demo_session", None)
    if sandbox is None:
        from backend.app.routes.auth import session as auth_session
        session = auth_session(request, Response())
    if who.role == role:
        yield who, session
        return
    if sandbox is None or not prefetch:
        raise HTTPException(403, "This screen belongs to a different role")
    from backend.app.services.demo_store import describe_demo
    from backend.app.services.demo_terminal import demo_principal
    session = describe_demo(session["demoId"], session["issuedAt"], session["expiresAt"], role, sandbox.world)
    identity = demo_principal(session["user"])
    projected = sandbox
    if role == "VESSEL_OPERATOR":
        projected = replace(sandbox, world={**sandbox.world, "selectedVessel": "PWD-001"})
    identity_token = current_identity.set(identity)
    sandbox_token = current_sandbox.set(projected)
    try:
        yield identity, session
    finally:
        current_sandbox.reset(sandbox_token)
        current_identity.reset(identity_token)


def _fragments(request: Request, screen: str, who, session: dict | None, port: str | None):
    from backend.app.routes import company, current_inputs, demonstrations, fleet, handoffs, health, model, news, ports, weather, world
    from src.portwatch_os.deployment import resolve_mode
    from src.utils import port_registry

    sandbox = current_sandbox.get()
    mode = "DEMO" if sandbox is not None else resolve_mode(None)[0]
    result = {
        "/health": health.health_check,
        "/ports": ports.list_ports,
        "/ports/registry": ports.port_registry_listing,
        "/fleet": fleet.fleet,
        "/news": news.news_bundle,
        "/weather": weather.weather_all,
        "/weather/current-map": current_inputs.weather_map,
        "/world/clock": world.world_clock,
        f"/fabric/health?mode={mode}": partial(world.fabric_health, mode),
    }
    if sandbox is not None:
        result["/demonstrations/selection"] = demonstrations.selection
    if screen != "admin-home":
        result["/handoffs"] = handoffs.handoffs
    if screen == "company-home":
        company_id = (session or {}).get("user", {}).get("companyId")
        if not company_id:
            profile = company.resolve_company()
            company_id = profile.company_id if profile else None
        ids = {"company_id": company_id} if company_id else {}
        for path, arguments, fn in (
            ("/company/fleet", ids, partial(company.company_fleet, company_id)),
            ("/company/risk", {**ids, "horizon_hours": 72}, partial(company.company_risk, company_id, 72)),
        ):
            result[path + ("?" + urlencode(sorted(arguments.items())) if arguments else "")] = fn
        if sandbox is not None:
            result["/company/decision-triage"] = partial(company.fleet_decision_triage, request)
            result["/demonstrations/scenarios"] = demonstrations.catalogue
    if screen in ("port-home", "vessel-home"):
        candidate = who.port_code if screen == "port-home" and who.port_code else port
        candidate = candidate or (sandbox.world.get("portCode") if sandbox else None) or "INNSA"
        facility = port_registry.resolve(candidate)
        if facility:
            code = facility.locode
            result[f"/model/{code}/forecast"] = partial(model.model_forecast, code)
            if screen == "port-home":
                result[f"/model/{code}/decision"] = partial(model.model_decision, code)
    return result


async def _read(path, fn):
    try:
        body = await fn() if inspect.iscoroutinefunction(fn) else await run_in_threadpool(fn)
        return path, {"status": 200, "data": body}
    except HTTPException as exc:
        return path, {"status": exc.status_code, "data": {"detail": exc.detail}}
    except Exception:
        log.exception("Home snapshot fragment failed: %s", path)
        return path, {"status": 503, "data": {"detail": "This screen section is temporarily unavailable."}}


def _encode(sections, session):
    payload = jsonable_encoder({"sections": dict(sections), "session": session})
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return Packet(raw, brotli.compress(raw, quality=4), 'W/"' + sha256(raw).hexdigest()[:32] + '"', monotonic() + TICK_SECONDS)


async def _build(key, request, screen, who, session, port):
    try:
        sections = await asyncio.gather(*(_read(path, fn) for path, fn in _fragments(request, screen, who, session, port).items()))
        packet = await run_in_threadpool(_encode, sections, session)
        if _inflight.get(key) is asyncio.current_task() and all(row["status"] < 500 for _, row in sections):
            _cache[key] = packet
            _cache.move_to_end(key)
            while len(_cache) > MAX_ENTRIES:
                _cache.popitem(last=False)
        return packet
    finally:
        if _inflight.get(key) is asyncio.current_task():
            _inflight.pop(key, None)


def _accepts_brotli(header: str):
    for entry in header.split(","):
        name, _, parameters = entry.strip().partition(";")
        if name.strip().lower() == "br":
            match = re.search(r"(?:^|;)\s*q\s*=\s*(\d+(?:\.\d*)?)", parameters, re.I)
            return match is None or float(match[1]) > 0
    return False


@router.get("/screens/{screen}")
async def screen_snapshot(request: Request, screen: str, prefetch: bool = False, port: str | None = None):
    role = ROLES.get(screen)
    if not role:
        raise HTTPException(404, "Unknown screen")
    if port and not re.fullmatch(r"[A-Za-z0-9]{2,8}", port):
        raise HTTPException(422, "Invalid facility code")
    port = port.upper() if port else None
    sandbox = current_sandbox.get()
    request.state.screen_namespace = str(sandbox.root) if sandbox else None
    with _screen_identity(request, role, prefetch) as (who, session):
        clock = get_clock()
        state = clock.state
        tick = int(clock.now().timestamp()) // TICK_SECONDS
        key = (request.state.screen_namespace, who.actor, who.role, who.organisation,
               who.port_code, tuple(who.port_codes), tuple(who.vessel_ids), who.can_approve,
               (session or {}).get("issuedAt"), (session or {}).get("expiresAt"),
               screen, port, state.mode, state.anchor, state.set_at, state.rate, tick)
        packet = _cache.get(key)
        hit = packet is not None and packet.expires > monotonic()
        if hit:
            _cache.move_to_end(key)
        else:
            task = _inflight.get(key)
            if task is None:
                task = asyncio.create_task(_build(key, request, screen, who, session, port))
                _inflight[key] = task
            packet = await asyncio.shield(task)
    telemetry.incr("screen.requests", screen=screen, cache="hit" if hit else "miss")
    headers = {
        "ETag": packet.etag,
        "Cache-Control": "private, no-cache",
        "Vary": "Authorization, Accept-Encoding",
        "X-PortWatch-Cache": "HIT" if hit else "MISS",
    }
    tags = request.headers.get("if-none-match", "").split(",")
    if any(tag.strip() in (packet.etag, packet.etag[2:], "*") for tag in tags):
        return Response(status_code=304, headers=headers)
    if _accepts_brotli(request.headers.get("accept-encoding", "")):
        headers["Content-Encoding"] = "br"
        return Response(packet.compressed, media_type="application/json", headers=headers)
    return Response(packet.json, media_type="application/json", headers=headers)
