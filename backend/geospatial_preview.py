"""Standalone public geometry API for teammate development; no private state.

Run: uvicorn backend.geospatial_preview:app --host 127.0.0.1 --port 8001
Production uses the same router through the existing port-twin router.
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.routes.port_geometry import router

app = FastAPI(title="PortWatch geographic integration", version="1")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get(
    "PORTWATCH_GEOSPATIAL_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173"
).split(","), allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
app.include_router(router, prefix="/api")
