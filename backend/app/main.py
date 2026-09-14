from __future__ import annotations

import os

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routes import (
    advisories,
    agents,
    company,
    decisions,
    finance,
    fleet,
    global_eye,
    health,
    learning,
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
    """Start the live feeds with the process, and stop them with it.

    The AISStream client runs only when AISSTREAM_API_KEY is set; without it
    the call is a no-op and the deployment shows the labelled replay. The key
    is read here on the server and never leaves it.
    """
    from src.portwatch_os.fabric.ais.client import start_client, stop_client
    from src.portwatch_os.fabric.marine import start_refresher, stop_refresher

    start_client()
    start_refresher()
    try:
        yield
    finally:
        stop_refresher()
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


@app.get("/")
def root() -> dict:
    return {
        "service": "India PortWatch Backend",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }
