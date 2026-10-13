"""Verified public-data pilot for two exact physical ports."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.app.identity import Identity, require_verified
from backend.app.routes.intelligence import may_write
from src.portwatch_os.clock import LIVE, get_clock, world_now
from src.portwatch_os.intelligence.public_collection import collect_port, get_service as service
from src.portwatch_os.intelligence.public_ports import PublicPilot
from src.portwatch_os.roles import NATIONAL_ADMIN, PORT_AUTHORITY

router = APIRouter()


def scope(port_code: Literal["INPRT", "INMAA"] = Query(..., alias="portCode"), who: Identity = Depends(require_verified)):
    if who.role != NATIONAL_ADMIN and not (who.role == PORT_AUTHORITY and port_code in who.port_codes):
        raise HTTPException(403, "Public pilot requires this port's verified authority or national command")
    return port_code, who


@router.get("/public-arrivals/workspace")
@router.get("/public-arrivals/dataset")
def workspace(access=Depends(scope), store: PublicPilot = Depends(service)):
    from src.portwatch_os.freshness import get_coordinator
    from src.portwatch_os.intelligence.vesselfinder import get_vessel_store
    port, now = access[0], world_now()
    state = store.workspace(port, now)
    durable = store.collection_status(port, now)
    coordinator = get_coordinator()
    job = None
    if get_clock().state.mode == LIVE and "public_ports_"+port in coordinator.artifacts():
        job = coordinator.describe("public_ports_"+port)
    state["collection"] = {**durable, "schedulerRunning": coordinator.running if get_clock().state.mode == LIVE else None,
                           "backendJob": job}
    state["structuredVessels"] = get_vessel_store().workspace(port, now)
    return state


@router.post("/public-arrivals/refresh")
def refresh(access=Depends(scope), store: PublicPilot = Depends(service)):
    port, who = access
    may_write(who, port)
    result = collect_port(store, port, who.actor)
    return {"results": result["refresh"]["results"], "errors": result["errors"], "counts": result["counts"]}


@router.post("/public-arrivals/evaluate")
def evaluate(cohort_id: str | None = Query(None, alias="cohortId"), access=Depends(scope), store: PublicPilot = Depends(service)):
    port, who = access
    may_write(who, port)
    try:
        return store.evaluate(port, world_now(), who.actor, cohort_id=cohort_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


class CohortInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enrollmentDays: int = Field(default=30, ge=1, le=90, strict=True)


@router.post("/public-arrivals/cohorts")
def start_cohort(body: CohortInput, access=Depends(scope), store: PublicPilot = Depends(service)):
    port, who = access
    may_write(who, port)
    try:
        return store.start_cohort(port, world_now(), who.actor, enrollment_days=body.enrollmentDays)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/public-arrivals/evidence/{snapshot_id}")
def evidence(snapshot_id: str, access=Depends(scope), store: PublicPilot = Depends(service)):
    try:
        path = store.evidence(access[0], snapshot_id, world_now())
    except (ValueError, OSError) as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, media_type="application/pdf", filename=f"{access[0]}-{snapshot_id[:16]}.pdf",
                        headers={"Cache-Control": "private, no-store"})


@router.get("/public-arrivals/structured-evidence/{snapshot_id}")
def structured_evidence(snapshot_id: str, access=Depends(scope)):
    from src.portwatch_os.intelligence.vesselfinder import get_vessel_store
    try:
        path = get_vessel_store().evidence(access[0], snapshot_id, world_now())
    except (ValueError, OSError) as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, media_type="application/json", filename=f"{access[0]}-vessels-{snapshot_id[:16]}.json",
                        headers={"Cache-Control": "private, no-store"})
