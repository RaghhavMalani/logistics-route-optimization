"""Administration: freshness, diagnostics and deployment readiness.

Three surfaces, all read-only except the refresh trigger, all National
Command:

    /admin/freshness              every artifact's state, age, SLA and job
    /admin/freshness/{a}/refresh  ask for a refresh now; joins a running one
    /admin/diagnostics            the process's telemetry snapshot
    /admin/readiness              the deployment validated against its mode

No secret is ever in a payload here. The diagnostics route checks its own
output against the environment before returning it, and refuses itself if a
configured key's value appears anywhere in it.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query

from backend.app.routes.world import _scope
from src.portwatch_os.clock import get_clock
from src.portwatch_os.telemetry import get_telemetry

router = APIRouter()

#: Environment variables whose values must never appear in a payload.
SECRET_ENV = ("AISSTREAM_API_KEY", "OPEN_METEO_API_KEY", "DATABASE_URL", "KAFKA_BOOTSTRAP_SERVERS")


def _admin(role: Optional[str]) -> str:
    """National command, stated: a missing role is a refusal here, never a default."""
    from backend.app.identity import resolve_role

    return resolve_role(role, admin_surface=True)


def _coordinator():
    from src.portwatch_os.freshness import get_coordinator
    from src.portwatch_os.freshness.jobs import install_product_jobs

    return install_product_jobs(get_coordinator())


def _scrub(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Refuse a payload that carries a configured secret's value."""
    text = json.dumps(payload, default=str)
    for name in SECRET_ENV:
        value = os.getenv(name)
        if value and len(value) >= 6 and value in text:
            raise HTTPException(
                status_code=500,
                detail=f"the payload would have carried the value of {name}; refused",
            )
    return payload


@router.get("/admin/freshness")
def freshness(role: Optional[str] = Header(None, alias="X-PortWatch-Role")) -> Dict[str, Any]:
    """Every artifact, its own instant, its state against its SLA, and its job."""
    _admin(role)
    return _scrub(_coordinator().status())


@router.get("/admin/freshness/{artifact}")
def freshness_artifact(artifact: str, role: Optional[str] = Header(None, alias="X-PortWatch-Role")) -> Dict[str, Any]:
    _admin(role)
    try:
        return _scrub(_coordinator().describe(artifact))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/admin/freshness/{artifact}/refresh")
def refresh_artifact(
    artifact: str,
    wait: bool = Query(False, description="Block until the attempt finishes (seconds for most jobs; minutes for the pipeline)."),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    actor: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
) -> Dict[str, Any]:
    """Refresh now. A running job is joined, never duplicated."""
    _admin(role)
    if not actor:
        raise HTTPException(status_code=401, detail="a refresh request must name its actor (X-PortWatch-Actor)")
    coordinator = _coordinator()
    try:
        outcome = coordinator.request(artifact, reason=f"requested by {actor}", wait=wait, requested=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _scrub({"artifact": artifact, "outcome": outcome, **coordinator.describe(artifact)})


@router.get("/admin/diagnostics")
def diagnostics(role: Optional[str] = Header(None, alias="X-PortWatch-Role")) -> Dict[str, Any]:
    """The process's operational telemetry. Numbers and short labels only."""
    _admin(role)
    from src.portwatch_os.fabric.ais.client import get_client
    from src.portwatch_os.world.live import get_live_world

    snapshot = get_telemetry().snapshot()
    snapshot["world"] = get_live_world().status()
    snapshot["worldClock"] = get_clock().describe()
    snapshot["traffic"] = get_client().status.to_dict()
    snapshot["freshness"] = _coordinator().status()["summary"]
    # Whether the host was asked not to power-throttle this process (hostperf):
    # a slow deployment on a Windows laptop is a fact with a name.
    from backend.app.main import app as _app

    snapshot["host"] = {"powerThrottling": getattr(_app.state, "power_throttling", None)}
    return _scrub(snapshot)


@router.get("/admin/readiness")
def readiness(
    mode: Optional[str] = Query(None, description="Validate as this licence mode; defaults to the process's."),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
) -> Dict[str, Any]:
    """The deployment validated against what its mode requires. Never a silent fallback."""
    _admin(role)
    from src.portwatch_os.deployment import validate

    return _scrub(validate(mode=mode).to_dict())


__all__ = ["router"]
