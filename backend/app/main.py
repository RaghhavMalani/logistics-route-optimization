from __future__ import annotations

from src.utils.settings import get_settings

import re
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.app.domains.system.router import router as system_router
from backend.app.domains.intelligence.router import router as intelligence_router
from backend.app.domains.ports.router import router as ports_router
from backend.app.domains.world.router import router as world_router
from backend.app.domains.voyages.router import router as voyages_router
from backend.app.domains.advisories.router import router as advisories_router
from backend.app.domains.system import screens
from backend.app.services import handoff_events

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start the live feeds and the freshness coordinator with the process.

    The AISStream client runs only when AISSTREAM_API_KEY is set; without it
    the call is a no-op and the deployment shows the labelled replay. The key
    is read here on the server and never leaves it.

    The coordinator replaces the marine module's own refresh thread and the
    operator's memory of when the event register lapses: every artifact has a
    policy, and the scheduler refreshes it before its SLA elapses. Set
    PORTWATCH_FRESHNESS_SCHEDULER=0 to run without the scheduler (tests, the
    benchmark), in which case every artifact still reports its real age.
    """
    import logging

    from src.portwatch_os.deployment import resolve_mode
    from src.portwatch_os.fabric.ais.client import start_client, stop_client
    from src.portwatch_os.freshness import get_coordinator
    from src.portwatch_os.freshness.jobs import install_product_jobs

    from src.portwatch_os.hostperf import opt_out_of_power_throttling

    log = logging.getLogger("portwatch.startup")
    # A serving process is not background work; on Windows the host would
    # otherwise throttle it after a minute of sustained load (hostperf).
    throttling = opt_out_of_power_throttling()
    app.state.power_throttling = throttling
    log.info("power throttling opt-out: %s (%s)", throttling["applied"], throttling["reason"])
    from src.portwatch_os.deployment_artifact import current as verify_image_source
    app.state.source_artifact=verify_image_source()
    mode, source, problem = resolve_mode(None)
    if problem:
        log.warning("licence mode %s by default: %s", mode, problem)
    else:
        log.info("licence mode %s (%s)", mode, source)
    # An explicit, reviewed public seed is merged before this process starts
    # any collectors. Unconfigured deployments do no import work.
    from src.portwatch_os.learning.public_evidence_seed import import_configured_seed
    app.state.public_evidence_import = import_configured_seed()
    log.info("public evidence seed: %s", app.state.public_evidence_import["status"])
    # Candidate-only one-shot recovery proof. Runs before all writers/listeners;
    # no SSH key, public mutation endpoint or duplicate worker is introduced.
    from scripts.candidate_state_backup import configured_backup
    app.state.candidate_backup=configured_backup()
    log.info("candidate backup: %s", app.state.candidate_backup)
    from src.portwatch_os.panel_runtime import snapshot_at
    panel = snapshot_at() is not None
    coordinator = install_product_jobs(get_coordinator())
    scheduler = (get_settings().PORTWATCH_FRESHNESS_SCHEDULER or "1").strip().lower() not in ("0", "false", "no", "off")
    if scheduler and not panel:
        coordinator.start()
    from src.portwatch_os.learning import weather_reconciliation
    from src.portwatch_os.learning import intelligence_reconciliation
    from src.portwatch_os.intelligence import operational_notices as authority_notices
    if not panel and coordinator.running:
        start_client()
        weather_reconciliation.start()
        intelligence_reconciliation.start()
        authority_notices.start()
    import asyncio
    from src.portwatch_os.freshness.source_trials import run as run_trials
    trial_task = asyncio.create_task(run_trials()) if not panel and coordinator.running else None
    try:
        yield
    finally:
        if trial_task:
            trial_task.cancel()
            await asyncio.gather(trial_task, return_exceptions=True)
        coordinator.stop()
        weather_reconciliation.stop()
        intelligence_reconciliation.stop()
        authority_notices.stop()
        stop_client()


app = FastAPI(
    title="India PortWatch Backend",
    version="2.0.0",
    lifespan=lifespan,
    description=(
        "Evidence-backed API for India PortWatch: forecasting, global event "
        "intelligence, port digital twins, cargo, human-approved advisories, "
        "agentic orchestration and the outcome ledger."
    ),
)

# Local development works out of the box. Production can set
# PORTWATCH_CORS_REGEX to the exact deployed frontend domain/regex without a
# source-code edit, e.g. https://portwatch\.example\.com.
cors_regex = get_settings().get(
    "PORTWATCH_CORS_REGEX",
    r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
)

@app.exception_handler(Exception)
async def _storage_failures(request: Request, exc: Exception):
    """A durable store that will not open or write is a 503 with its reason,
    never a 500 with a traceback and never a silently empty answer."""
    import sqlite3

    from fastapi.responses import JSONResponse

    from src.portwatch_os.advisories.model import AdvisoryError
    from src.portwatch_os.ledger.store import LedgerError

    store_fault = isinstance(exc, AdvisoryError) and (
        "cannot be opened" in str(exc) or "integrity check" in str(exc)
    )
    if isinstance(exc, (LedgerError, sqlite3.DatabaseError)) or store_fault:
        from src.portwatch_os import telemetry

        telemetry.incr("api.errors", route=request.url.path, status=503)
        # A fault seen on a request is what health should say next; drop the
        # minute's memory of the last probe.
        from backend.app.domains.system import health as health_route

        health_route._PROBE_CACHE["value"] = None
        return JSONResponse(status_code=503, content={
            "detail": f"a durable store is unavailable: {exc}",
            "store": "ledger" if isinstance(exc, (LedgerError, sqlite3.DatabaseError)) else "advisories",
            "remedy": "check PORTWATCH_STATE_DIR and /api/health.durableStores; nothing was substituted",
        })
    raise exc


#: Routes a request may reach with no identity even when identity is required:
#: liveness, the policy statements that say what this deployment verifies, and
#: the API's own description.
IDENTITY_EXEMPT = ("/api/health", "/api/provenance", "/api/advisories/policy", "/api/auth/login", "/", "/docs", "/openapi.json", "/redoc")


@app.middleware("http")
async def _identity_gate(request: Request, call_next):
    """Verify the session, derive server-owned scope, and gate protected API routes."""
    if request.url.path.startswith("/api/demo/"):
        # Demo routes authenticate against their separate store. Never create an
        # operational Identity or forward demo requests into protected routers.
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        return response
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool
    from backend.app.auth_store import get_auth_store
    from src.portwatch_os.ledger.store import LedgerError
    from backend.app.identity import Identity, REQUIRED, VERIFIED, current_identity, identity_mode

    path = request.url.path
    context_token = current_identity.set(None)
    try:
        public_read = request.method == "GET" and (path in ("/api/public/explore", "/api/public/research", "/api/public/workspace", "/api/public/scenario", "/api/public/weather-feedback")
            or path.startswith("/api/public/research/download/")
            or path in ("/api/public/port-calls", "/api/public/sources")
            or re.fullmatch(r"/api/public/port-calls/(?:evidence/[a-f0-9]{64}\.pdf|[a-f0-9]{64}/audit)", path) is not None)
        if path.startswith("/api/") and request.method != "OPTIONS" and path not in IDENTITY_EXEMPT and not public_read:
            authorization = request.headers.get("authorization", "")
            if authorization:
                scheme, _, token = authorization.partition(" ")
                if scheme.lower() != "bearer" or not token:
                    raise HTTPException(401, "A bearer session token is required")
                verified = await run_in_threadpool(get_auth_store().session, token)
                user = verified["user"]
                who = Identity(role=user["role"], actor=user["id"], port_code=user["portCode"],
                               port_codes=tuple(user["portCodes"]), organisation=user["organisation"],
                               vessel_ids=tuple(user["vesselIds"]), verified=True,
                               can_approve=user.get("canApprove", True) is True)
                current_identity.set(who)
                request.state.verified_session = verified
                request.state.session_token = token
                # Existing workflow routes consume these headers. Replace every caller assertion
                # with server-owned values before FastAPI resolves their Header dependencies.
                headers = [(k,v) for k,v in request.scope["headers"] if not k.lower().startswith(b"x-portwatch-")]
                values = {"role": who.role, "actor": who.actor, "port": who.port_code,
                          "org": who.organisation, "vessels": ",".join(who.vessel_ids)}
                for key, value in values.items():
                    if value:
                        headers.append((f"x-portwatch-{key}".encode(), value.encode("ascii", "ignore")))
                request.scope["headers"] = headers
                if hasattr(request, "_headers"):
                    del request._headers
            elif identity_mode() == VERIFIED or path.startswith("/api/auth/"):
                raise HTTPException(401, "A verified session is required", headers={"WWW-Authenticate": "Bearer"})
            elif identity_mode() == REQUIRED and not (request.headers.get("x-portwatch-role") or "").strip():
                raise HTTPException(401, "This deployment requires an identity from the authenticating proxy")
        response = await call_next(request)
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
    except LedgerError:
        return JSONResponse(status_code=503, content={"detail": "A durable identity or evidence store is unavailable"})
    finally:
        current_identity.reset(context_token)


@app.middleware("http")
async def _telemetry(request: Request, call_next):
    """Latency and error counts per route, for the diagnostics page.

    The route template is used where FastAPI resolved one, so a thousand
    vessel ids do not become a thousand timers.
    """
    from src.portwatch_os import telemetry

    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        telemetry.incr("api.errors", route=request.url.path, status=500)
        telemetry.event("api.errors", route=request.url.path, status=500)
        raise
    route = request.scope.get("route")
    template = getattr(route, "path", None) or request.url.path
    telemetry.observe("api.latency", time.perf_counter() - started, route=template)
    telemetry.incr("api.requests", route=template)
    if request.method in ("POST", "PATCH", "PUT", "DELETE") and 200 <= response.status_code < 300:
        namespace = getattr(request.state, "screen_namespace", None)
        if namespace is not None or (request.url.path.startswith("/api/") and not request.url.path.startswith("/api/demo/")):
            screens.invalidate(namespace)
            handoff_events.publish(namespace)
    if response.status_code >= 500:
        telemetry.incr("api.errors", route=template, status=response.status_code)
        telemetry.event("api.errors", route=template, status=response.status_code)
    elif response.status_code >= 400:
        telemetry.incr("api.refusals", route=template, status=response.status_code)
    return response

# CORS must also wrap authentication refusals, so cross-origin terminals can
# read a 401 and return to sign-in instead of reporting an opaque network error.
app.add_middleware(CORSMiddleware, allow_origin_regex=cors_regex,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for domain in (system_router, intelligence_router, ports_router, world_router, voyages_router, advisories_router):
    app.include_router(domain, prefix="/api")

@app.get("/")
def root() -> dict:
    return {
        "service": "India PortWatch Backend",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }
