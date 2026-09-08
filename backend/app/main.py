from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routes import (
    fleet,
    health,
    model,
    news,
    ports,
    sar,
    scenarios,
    weather,
)

app = FastAPI(
    title="India PortWatch Backend",
    version="0.2.0",
    description="Evidence-backed API for the India PortWatch maritime digital twin.",
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
app.include_router(model.router, prefix="/api")
app.include_router(ports.router, prefix="/api")
app.include_router(weather.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(sar.router, prefix="/api")
app.include_router(fleet.router, prefix="/api")
app.include_router(scenarios.router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {
        "service": "India PortWatch Backend",
        "version": "0.2.0",
        "docs": "/docs",
        "health": "/api/health",
    }
