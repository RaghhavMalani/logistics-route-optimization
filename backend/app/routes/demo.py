"""Explicit demo API. No forwarding to operational routes or their stores."""
import secrets
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from backend.app.services.demo_store import get_demo_store, ROLES, seed_world, utc_now
from backend.app.services.demo_terminal import bind, demo_hulls, demo_principal
from backend.app.services import public_workspace

router = APIRouter(prefix="/demo")
Role = Literal["SHIPPING_COMPANY", "VESSEL_OPERATOR", "PORT_AUTHORITY", "NATIONAL_ADMIN"]


def token(request: Request, authorization: str = Header("")):
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(401, "A demo bearer session is required")
    store = get_demo_store()
    session, world = store.session_world(credential)
    if request.method == "POST" and request.url.path not in ("/api/demo/role", "/api/demo/logout"):
        request.state.screen_namespace = str(bind(session, world, store).root)
    return credential


class RoleInput(BaseModel):
    role: Role


@router.post("/session")
def create(body: RoleInput):
    return get_demo_store().create(body.role)


@router.get("/session")
def restore(credential=Depends(token)):
    return get_demo_store().session(credential)


@router.post("/logout")
def logout(credential=Depends(token)):
    get_demo_store().revoke(credential)
    return {"revoked": True}


@router.post("/role")
def switch(body: RoleInput, credential=Depends(token)):
    return get_demo_store().switch(credential, body.role)


@router.post("/reset")
def reset(credential=Depends(token)):
    def change(world):
        world.clear()
        world.update(seed_world(utc_now().isoformat()))
        return {"reset": True}
    return get_demo_store().update(credential, change)


def twin_state(world):
    from src.portwatch_os.twin.state import state_from_snapshot, seed_calls
    snapshot = {"berthCount": 4, "capacityIndex": .65, "capacityPressure": .78, "queuePressure": .7, "anchorageCount": 3, "arrivalRate": 6, "weatherImpact": .18}
    state = state_from_snapshot("INNSA", snapshot, epoch=world["epoch"])
    seed_calls(state, snapshot, horizon_hours=48)
    from src.portwatch_os.twin.state import VesselCall, APPROACHING
    # The company proposal enters the twin as an explicitly future demo call,
    # rather than only changing an arrival label in the UI. Missing ETA effects
    # remain unavailable and are not silently converted to zero.
    for vessel in world["fleet"]:
        shift = 0
        proposal = world.get("terminalProposal") or world.get("proposal")
        if proposal and proposal["vesselId"] == vessel["id"]:
            if proposal["etaShiftHours"] is None:
                continue
            shift = proposal["etaShiftHours"]
        state.calls.append(VesselCall(call_id="demo-"+vessel["id"], vessel_id=vessel["id"], name=vessel["name"],
            vessel_class="container", loa_m=220, draught_m=10, eta_hour=vessel["etaHours"]+shift, moves=640,
            state=APPROACHING, latest_departure_hour=vessel["etaHours"]+shift+30))
    state.notes = ["FICTIONAL DEMO inputs. Berth geometry, occupancy, cranes and calls are schematic, not port measurements."]
    return state


def _port_comparison(world, allowed):
    comparison = world["portComparison"]
    if comparison is None:
        return None
    # Earlier simulations seated the whole fleet. Treat that as their scope.
    included = comparison.get("vesselIds", [row["id"] for row in world["fleet"]])
    return comparison if set(included) <= allowed else None


@router.get("/workspace")
def workspace(credential=Depends(token)):
    store = get_demo_store()
    session = store.session(credential)
    source = store.read(credential)
    who = demo_principal(session["user"])
    fleet = demo_hulls(source, who)
    allowed = {row["id"] for row in fleet}
    world = {key: source[key] for key in ("version", "epoch", "meaning", "organisation", "portCode", "event")}
    world.update(fleet=fleet, selectedVessel=source["selectedVessel"] if source["selectedVessel"] in allowed else None,
                 comparisons=[row for row in source["comparisons"] if row["vesselId"] in allowed],
                 proposal=source["proposal"] if (source["proposal"] or {}).get("vesselId") in allowed else None,
                 advisories=[row for row in source["advisories"] if row["proposal"]["vesselId"] in allowed],
                 portComparison=_port_comparison(source, allowed) if who.role in ("PORT_AUTHORITY", "NATIONAL_ADMIN") else None)
    if (source.get("terminalProposal") or {}).get("vesselId") in allowed:
        world["terminalProposal"] = source["terminalProposal"]
    scene = public_workspace.workspace()
    return {"session": session, "world": world, "scene": scene,
        "twin": twin_state(world).to_dict(), "scope": "Only this visitor's demo namespace; public evidence retains real receipt clocks."}


class Selection(BaseModel):
    vesselId: Literal["PWD-001", "PWD-002", "PWD-003"]


@router.post("/selection")
def select(body: Selection, credential=Depends(token)):
    def change(world):
        who = demo_principal(get_demo_store().session(credential)["user"])
        if not any(row["id"] == body.vesselId for row in demo_hulls(world, who)):
            raise HTTPException(404, "Voyage is unavailable in this workspace")
        world["selectedVessel"] = body.vesselId
        return {"selectedVessel": body.vesselId}
    return get_demo_store().update(credential, change)


class Scenario(Selection):
    hoursToRisk: float = Field(24, ge=-48, le=240, allow_inf_nan=False)
    closureHours: float = Field(72, ge=1, le=240, allow_inf_nan=False)
    speedKn: float = Field(16, ge=6, le=24, allow_inf_nan=False)
    waveM: float = Field(2, ge=0, le=12, allow_inf_nan=False)


@router.post("/scenario")
def compare(body: Scenario, credential=Depends(token)):
    def change(world):
        who = demo_principal(get_demo_store().session(credential)["user"])
        vessel = next((row for row in demo_hulls(world, who) if row["id"] == body.vesselId), None)
        if vessel is None:
            raise HTTPException(404, "Voyage is unavailable in this workspace")
        if len(world["comparisons"]) >= 30:
            raise HTTPException(409, "Demo comparison limit reached; reset your sandbox")
        result = public_workspace.simulate(lane_code=vessel["laneCode"], port_code=vessel["portCode"], hours_to_risk=body.hoursToRisk,
            speed=body.speedKn, closure_hours=body.closureHours, severity=1, wave_m=body.waveM, charter_day=30000, bunker_price=650, fuel_burn=45)
        item = {"id": secrets.token_hex(12), "vesselId": vessel["id"], "recordedAt": utc_now().isoformat(), "result": result}
        world["comparisons"].append(item)
        world["selectedVessel"] = vessel["id"]
        return item
    return get_demo_store().update(credential, change, (ROLES[0], ROLES[1], ROLES[3]))


class Proposal(BaseModel):
    comparisonId: str = Field(max_length=32)
    optionId: str = Field(max_length=200)


@router.post("/proposal")
def propose(body: Proposal, credential=Depends(token)):
    def change(world):
        comparison = next((c for c in world["comparisons"] if c["id"] == body.comparisonId), None)
        who = demo_principal(get_demo_store().session(credential)["user"])
        vessel = next((row for row in demo_hulls(world, who)
                       if comparison and row["id"] == comparison["vesselId"]), None)
        if vessel is None:
            raise HTTPException(404, "Comparison option is not in this demo")
        option = next((o for o in comparison["result"]["options"] if o["optionId"] == body.optionId), None)
        if not option:
            raise HTTPException(404, "Comparison option is not in this demo")
        if not option["feasible"]:
            raise HTTPException(409, "An infeasible option cannot become a proposal")
        if option.get("params", {}).get("portCode", vessel["portCode"]) != vessel["portCode"]:
            raise HTTPException(409, "This destination alternative cannot be submitted to the JNPA demo desk")
        proposal = body.model_dump() | {"vesselId": comparison["vesselId"], "etaShiftHours": option["evaluation"]["objectives"]["eta"]["value"], "createdAt": utc_now().isoformat(), "state": "PROPOSED"}
        world["proposal"] = proposal
        return proposal
    return get_demo_store().update(credential, change, (ROLES[0], ROLES[3]))


class PortScenario(BaseModel):
    weatherImpact: float = Field(.18, ge=0, le=1, allow_inf_nan=False)
    horizonHours: int = Field(72, ge=24, le=96)


@router.post("/port-scenario")
def port_compare(body: PortScenario, credential=Depends(token)):
    def change(world):
        from src.portwatch_os.twin.simulation import simulate, SimulationConfig
        from src.portwatch_os.twin.policies import FirstComeFirstServed, LookaheadPolicy
        who = demo_principal(get_demo_store().session(credential)["user"])
        hulls = demo_hulls(world, who)
        allowed = {row["id"] for row in hulls}
        state = twin_state({**world, "fleet": hulls})
        state.weather_impact = body.weatherImpact
        rows = []
        for name, policy in (("First come first served", FirstComeFirstServed()), ("Constrained lookahead", LookaheadPolicy())):
            result = simulate(state, policy, SimulationConfig(horizon_hours=body.horizonHours, seed=20261009, record_trace=False))
            rows.append({"policy": name, "metrics": result.metrics, "violations": result.violations, "rejectedActions": result.rejected_actions, "finalState": result.final_state.to_dict()})
        world["portComparison"] = {"recordedAt": utc_now().isoformat(), "inputs": body.model_dump(), "seed": 20261009, "meaning": "SIMULATION in the existing port twin; not measured operational performance.", "options": rows}
        world["portComparison"]["vesselIds"] = sorted(allowed)
        proposal = world["proposal"]
        world["portComparison"]["proposalInput"] = proposal.copy() if proposal and proposal["vesselId"] in allowed else None
        return world["portComparison"]
    return get_demo_store().update(credential, change, (ROLES[2], ROLES[3]))


class AdvisoryInput(BaseModel):
    policy: Literal["First come first served", "Constrained lookahead"] = "First come first served"


@router.post("/advisories")
def issue(body: AdvisoryInput, credential=Depends(token)):
    def change(world):
        if not world["proposal"] or not world["portComparison"]:
            raise HTTPException(409, "Review a company proposal and port comparison first")
        who = demo_principal(get_demo_store().session(credential)["user"])
        allowed = {row["id"] for row in demo_hulls(world, who)}
        if world["proposal"]["vesselId"] not in allowed:
            raise HTTPException(404, "Advisory not in this visitor's demo")
        comparison = _port_comparison(world, allowed)
        if comparison is None or comparison.get("proposalInput") != world["proposal"]:
            raise HTTPException(409, "The company proposal changed; recompute the port plan before approving")
        if len(world["advisories"]) >= 20:
            raise HTTPException(409, "Reset this demo before issuing more advisories")
        chosen = next(p for p in world["portComparison"]["options"] if p["policy"] == body.policy)
        if chosen["violations"]:
            raise HTTPException(409, "A port policy with hard violations cannot be approved")
        plan = {"policy": body.policy, "inputs": world["portComparison"]["inputs"], "seed": world["portComparison"]["seed"],
            "metrics": chosen["metrics"], "violations": chosen["violations"]}
        item = {"id": secrets.token_hex(12), "proposal": world["proposal"].copy(), "portComparisonAt": world["portComparison"]["recordedAt"],
            "portPlan": plan, "state": "ISSUED", "issuedAt": utc_now().isoformat(), "meaning": "DEMO advisory: delivered only within this visitor's sandbox"}
        world["advisories"].append(item)
        return item
    return get_demo_store().update(credential, change, (ROLES[2], ROLES[3]))


class Outcome(BaseModel):
    reportedWaitingHours: float = Field(ge=0, le=240, allow_inf_nan=False)


def advisory_change(credential, advisory_id, operation, value=None):
    def change(world):
        item = next((a for a in world["advisories"] if a["id"] == advisory_id), None)
        who = demo_principal(get_demo_store().session(credential)["user"])
        if not item or not any(row["id"] == item["proposal"]["vesselId"] for row in demo_hulls(world, who)):
            raise HTTPException(404, "Advisory not in this visitor's demo")
        if operation == "ack":
            if item["state"] != "ISSUED":
                raise HTTPException(409, "Only an issued advisory can be acknowledged")
            item.update(state="ACKNOWLEDGED", acknowledgedAt=utc_now().isoformat())
        else:
            if item["state"] != "ACKNOWLEDGED":
                raise HTTPException(409, "Recipient must acknowledge before recording a demo outcome")
            item.update(state="RESOLVED", outcome={"reportedWaitingHours": value, "recordedAt": utc_now().isoformat(), "source": "DEMONSTRATOR_ENTRY", "meaning": "Recorded demonstration outcome; not a measured port call or model score."})
        return item
    roles = (ROLES[0], ROLES[1], ROLES[3]) if operation == "ack" else (ROLES[2], ROLES[3])
    return get_demo_store().update(credential, change, roles)


@router.post("/advisories/{advisory_id}/ack")
def acknowledge(advisory_id: str, credential=Depends(token)):
    return advisory_change(credential, advisory_id, "ack")


@router.post("/advisories/{advisory_id}/outcome")
def outcome(advisory_id: str, body: Outcome, credential=Depends(token)):
    return advisory_change(credential, advisory_id, "outcome", body.reportedWaitingHours)
