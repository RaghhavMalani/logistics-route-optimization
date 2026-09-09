from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routes import (
    advisories,
    agents,
    company,
    fleet,
    global_eye,
    health,
    learning,
    model,
    news,
    port_twin,
    ports,
    provenance,
    sar,
    scenarios,
    weather,
)

app = FastAPI(
    title="India PortWatch Backend",
    version="2.0.0",
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


@app.get("/")
def root() -> dict:
    return {
        "service": "India PortWatch Backend",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }
