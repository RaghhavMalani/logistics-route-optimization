from __future__ import annotations

import os
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routes import (
    admin,
    advisories,
    agents,
    company,
    decisions,
    finance,
    fleet,
    global_eye,
    health,
    learning,
    lenses,
    missions,
    model,
    news,
    port_twin,
    ports,
    provenance,
    sar,
    scenarios,
    weather,
    world,
)

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

    log = logging.getLogger("portwatch.startup")
    mode, source, problem = resolve_mode(None)
    if problem:
        log.warning("licence mode %s by default: %s", mode, problem)
    else:
        log.info("licence mode %s (%s)", mode, source)
    start_client()
    coordinator = install_product_jobs(get_coordinator())
    scheduler = (os.getenv("PORTWATCH_FRESHNESS_SCHEDULER") or "1").strip().lower() not in ("0", "false", "no", "off")
    if scheduler:
        coordinator.start()
    try:
        yield
    finally:
        coordinator.stop()
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
cors_regex = os.getenv(
    "PORTWATCH_CORS_REGEX",
    r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
        return JSONResponse(status_code=503, content={
            "detail": f"a durable store is unavailable: {exc}",
            "store": "ledger" if isinstance(exc, (LedgerError, sqlite3.DatabaseError)) else "advisories",
            "remedy": "check PORTWATCH_STATE_DIR and /api/health.durableStores; nothing was substituted",
        })
    raise exc


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
    if response.status_code >= 500:
        telemetry.incr("api.errors", route=template, status=response.status_code)
        telemetry.event("api.errors", route=template, status=response.status_code)
    elif response.status_code >= 400:
        telemetry.incr("api.refusals", route=template, status=response.status_code)
    return response

app.include_router(health.router, prefix="/api")
app.include_router(provenance.router, prefix="/api")
app.include_router(model.router, prefix="/api")
app.include_router(ports.router, prefix="/api")
app.include_router(weather.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(sar.router, prefix="/api")
app.include_router(fleet.router, prefix="/api")
app.include_router(scenarios.router, prefix="/api")

# The agentic maritime OS surfaces. Everything above serves the forecasting
# pipeline's artefacts; everything below serves the layer built on top of them.
app.include_router(global_eye.router, prefix="/api")
app.include_router(company.router, prefix="/api")
app.include_router(port_twin.router, prefix="/api")
app.include_router(advisories.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(learning.router, prefix="/api")
app.include_router(world.router, prefix="/api")

# The decision intelligence engine, its financial twin and the historical
# missions that score it. All deterministic; all on the world above.
app.include_router(decisions.router, prefix="/api")
app.include_router(finance.router, prefix="/api")
app.include_router(missions.router, prefix="/api")

# Administration: freshness, diagnostics, readiness. National Command only.
app.include_router(admin.router, prefix="/api")

# Two lenses: structural trade exposure, and security over observed AIS.
app.include_router(lenses.router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {
        "service": "India PortWatch Backend",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }
