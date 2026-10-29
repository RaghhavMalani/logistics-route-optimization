"""The decision engine over HTTP: "what should I do?" as a resource.

A decision problem is built from the same frozen world the attention queue
was framed from, evaluated option by option through the engine, and served
whole: every catalogue action with whether it could be considered, every
option with its constraints, measures, branch and Critic verdict, the
frontier, the ranking with its weights, the recommendation, and the evidence
each number rests on. The frontend draws it; it does not re-derive any of it.

Decision is not execution. The workflow routes move a problem through
REVIEWED -> APPROVED -> PROPOSED -> ... with a named actor on every step, and
the only path from an approved port option to a master is the advisory
boundary that already exists: ``/handoff`` raises DRAFT advisories through the
same store, under the same authorisation, and nothing else can.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.portwatch_os.decision.continuation import connected_basis
from fastapi import APIRouter, Body, Header, HTTPException, Query

from backend.app.identity import Identity, identity_from_headers, may_see_decision, resolve_role
from backend.app.routes.world import _at, _event_or_404, _mode, _scope, _world_build
from src.portwatch_os.decision.actions import CATALOGUE, SHIFT_ARRIVAL_SLOT
from src.portwatch_os.decision.critic import DecisionCritic
from src.portwatch_os.decision.engine import DecisionEngine, TRANSITIONS, get_engine
from src.portwatch_os.decision.model import (
    ACTORS,
    APPROVED,
    DecisionActor,
    DecisionError,
    DecisionProblem,
    PORT_AUTHORITY,
    PORT_BERTHING,
    PROPOSED,
    VESSEL_ROUTING,
)
from src.portwatch_os.finance.basis import CostBasis, assumption as cost_assumption
from src.portwatch_os.world.branch import ObservedWorldState, get_registry, snapshot
from src.portwatch_os.world.build import seed_for
from src.portwatch_os.world.graph import EVENT, key
from src.portwatch_os.world.quantity import utc

router = APIRouter()



# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------


def _actor(role: Optional[str], organisation: Optional[str], port_code: Optional[str],
           vessel_ids: Optional[str]) -> DecisionActor:
    who = identity_from_headers(role, None, port_code, organisation, vessel_ids)
    organisation, port_code = who.organisation, who.port_code
    vessel_ids = ",".join(who.vessel_ids)
    scope = _scope(role)
    if scope not in ACTORS:
        raise HTTPException(status_code=403, detail=f"{scope} cannot hold a decision")
    # Ownership is what scoping reads back: a company's or an operator's
    # decision belongs to its organisation, a port authority's to its port.
    # An identity that names neither would hold a decision nobody -- itself
    # included -- could read or move, so it is refused up front.
    if scope in ("SHIPPING_COMPANY", "VESSEL_OPERATOR") and not (organisation or "").strip():
        raise HTTPException(status_code=400, detail=f"a {scope} decision needs X-PortWatch-Org: the organisation that will hold it")
    if scope == "PORT_AUTHORITY" and not (port_code or "").strip():
        raise HTTPException(status_code=400, detail="a PORT_AUTHORITY decision needs X-PortWatch-Port: the port that will hold it")
    return DecisionActor(
        role=scope, organisation=organisation, port_code=port_code,
        vessel_ids=tuple(v.strip() for v in (vessel_ids or "").split(",") if v.strip()),
    )


def _require_actor_name(actor: Optional[str]) -> str:
    if not actor:
        raise HTTPException(
            status_code=401,
            detail="Every decision step must name its actor. Send X-PortWatch-Actor with the "
                   "signed-in operator's name.",
        )
    return actor


def _identity(role: Optional[str], actor: Optional[str], port_code: Optional[str], organisation: Optional[str],
              vessel_ids: Optional[str]) -> Identity:
    return identity_from_headers(role, actor, port_code, organisation, vessel_ids)


def _visible_or_403(problem: DecisionProblem, identity: Identity) -> DecisionProblem:
    """A decision is read and moved only by the people it belongs to."""
    if not may_see_decision(identity, problem.actor.to_dict(),
                            {"type": problem.subject_type, "id": problem.subject_id}, problem.domain):
        raise HTTPException(
            status_code=403,
            detail=f"decision {problem.decision_id} is held by {problem.actor.role}"
                   + (f" ({problem.actor.organisation})" if problem.actor.organisation else "")
                   + (f" at {problem.actor.port_code}" if problem.actor.port_code else "")
                   + f"; {identity.role} may not read or move it",
        )
    return problem


def _domain_allowed_or_403(domain: str, identity: Identity) -> None:
    """Which domains a role may hold a decision in, from the action catalogue."""
    from src.portwatch_os.decision.actions import ADVISING_ACTORS, for_domain

    key = {"vessel": VESSEL_ROUTING, "port": PORT_BERTHING, "cargo": "CARGO_CONNECTION"}.get(domain)
    if key is None:
        return
    # Holding a decision means holding its baseline: the actor the domain's
    # "change nothing" action belongs to, plus the advisers the builders map
    # onto the executing actor (executing_actor_for).
    holders = set()
    for spec in for_domain(key):
        if spec.baseline:
            holders.update(spec.actors)
    if key in (VESSEL_ROUTING, "CARGO_CONNECTION"):
        holders.update(ADVISING_ACTORS)
    if identity.role not in holders:
        raise HTTPException(status_code=403,
                            detail=f"a {domain} decision is held by {', '.join(sorted(holders))}; not by {identity.role}")


def _problem_or_404(engine: DecisionEngine, decision_id: str) -> DecisionProblem:
    problem = engine.get(decision_id)
    if problem is None:
        recorded = engine.ledger is not None and engine.ledger.get_decision_problem(decision_id) is not None
        raise HTTPException(
            status_code=404 if not recorded else 409,
            detail=(f"no decision {decision_id} in this process" + (
                "; the ledger holds it as computed before a restart (GET /decisions/problems/{id}), and a decision "
                "pinned to a world this process has not rebuilt is not moved on: recompute it and decide on the "
                "world as it is now" if recorded else "")),
        )
    return problem


def _from_ledger(engine: DecisionEngine, decision_id: str) -> Optional[Dict[str, Any]]:
    """A problem this process no longer holds, as the ledger recorded it.

    After a restart the engine's memory is empty but the ledger is not. The
    record is served read-only -- the payload as computed, with the workflow
    columns the ledger kept up to date -- and says so. It cannot be moved
    through the workflow: it was pinned to a world revision this process has
    not rebuilt, so the operator recomputes and decides on the world as it
    is now.
    """
    if engine.ledger is None:
        return None
    record = engine.ledger.get_decision_problem(decision_id)
    if record is None:
        return None
    body = dict(record.problem or {})
    body["workflow"] = record.workflow
    body["humanChoice"] = record.human_choice
    body["restoredFromLedger"] = True
    body["restoredNote"] = ("served from the decision ledger: this process did not compute it (restart or "
                            "another process); recompute to move it through the workflow")
    if record.actual_action:
        body["actualAction"] = record.actual_action
    if record.observed_outcome:
        body["observedOutcome"] = record.observed_outcome
    return body


# --------------------------------------------------------------------------
# the world a problem is built from
# --------------------------------------------------------------------------


def _observed_state(company_id: Optional[str], mode: Optional[str], moment: datetime):
    from src.portwatch_os.fabric import ais_mode

    build, events = _world_build(company_id, mode=mode)
    traffic = ais_mode(licence_mode=_mode(mode), now=utc())
    return build, events, snapshot(build, traffic_mode=traffic["mode"], at=moment)


def _marine_grid(mode: Optional[str]):
    """The marine grid when the licence mode allows it, else None (and said so)."""
    from src.portwatch_os.fabric.marine import OpenMeteoMarineAdapter

    adapter = OpenMeteoMarineAdapter(licence_mode=_mode(mode))
    availability = adapter.availability()
    if not availability.ready:
        return None, availability.to_dict()
    return adapter.service.grid(now=utc(), allow_fetch=False), availability.to_dict()


def _basis_with_assumptions(engine: DecisionEngine, rows: List[Dict[str, Any]], actor: str) -> CostBasis:
    """The engine's basis plus the request's scenario assumptions, labelled."""
    if not rows:
        return engine.basis
    basis = CostBasis(engine.basis.rates)
    for schedule in engine.basis.schedules:
        basis._schedules.append(schedule)  # noqa: SLF001 - same package family
    for row in rows:
        if not isinstance(row, dict):
            raise HTTPException(status_code=400, detail="assumptions must be objects of primitive, value, currency")
        value = row.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HTTPException(status_code=400, detail=f"assumption rejected: {row.get('primitive')} value must be a JSON number")
        try:
            basis.add(cost_assumption(
                str(row.get("primitive")), float(value), str(row.get("currency") or "USD"),
                entered_by=actor, purpose=str(row.get("purpose") or "scenario"),
                scope=str(row.get("scope") or "*"), note=str(row.get("note") or ""),
            ))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"assumption rejected: {exc}")
    return basis


# --------------------------------------------------------------------------
# catalogue
# --------------------------------------------------------------------------


@router.get("/decisions/actions")
def decision_actions() -> Dict[str, Any]:
    """Every action the engine knows, by domain, with who may execute it."""
    return {
        "actions": [spec.to_dict() for spec in CATALOGUE.values()],
        "actors": list(ACTORS),
        "workflow": {state: list(targets) for state, targets in TRANSITIONS.items()},
        "critic": DecisionCritic.describe(),
        "note": (
            "An action is offered only when its data exists, its constraints can be evaluated "
            "and a simulator here supports it. Otherwise it is listed with the reason it was not."
        ),
    }


# --------------------------------------------------------------------------
# problems
# --------------------------------------------------------------------------


@router.post("/decisions/problems")
def create_problem(
    payload: Dict[str, Any] = Body(...),
    actor_name: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
) -> Dict[str, Any]:
    """Build and evaluate a decision problem.

    ``domain`` is ``vessel`` (needs ``vesselId`` and ``eventId`` or a
    ``branchId`` with its seed), ``port`` (needs ``portCode``) or ``cargo``
    (needs ``portCode``, optional ``shipmentId``). ``assumptions`` is a list
    of scenario cost rates ``{primitive, value, currency, scope?, note?}``;
    every figure built on one is labelled ASSUMPTION. ``at`` moves the world
    clock, as it does everywhere else.
    """
    engine = get_engine()
    domain = str(payload.get("domain") or "vessel").lower()
    moment = _at(payload.get("at"))
    actor = _actor(role, organisation, header_port, vessel_ids)
    _domain_allowed_or_403(domain, _identity(role, actor_name, header_port, organisation, vessel_ids))
    basis = _basis_with_assumptions(engine, payload.get("assumptions") or [], actor_name or "operator")
    mode = payload.get("mode")
    predecessor = None
    successor_key = None
    if payload.get("predecessorDecisionId"):
        from src.portwatch_os.sandbox import current_sandbox
        identity = _identity(role, actor_name, header_port, organisation, vessel_ids)
        if current_sandbox.get() is None or identity.role != "SHIPPING_COMPANY":
            raise HTTPException(403,"Company creates linked successors in its own visitor world")
        if domain != "vessel" or not isinstance(payload.get("currentArrival"), dict):
            raise HTTPException(400,"A connected voyage successor requires currentArrival inputs")
        predecessor = engine.get(str(payload["predecessorDecisionId"]))
        if predecessor is None:
            raise HTTPException(404,"No predecessor comparison in this visitor's records")
        _visible_or_403(predecessor, identity)
        if not connected_basis(predecessor) or predecessor.actor.role != "SHIPPING_COMPANY" or predecessor.subject_id != payload.get("vesselId"):
            raise HTTPException(409,"The predecessor must be this Company's connected comparison for the same voyage")
        try:
            successor_key = hashlib.sha256(json.dumps({
                "vesselId": payload.get("vesselId"), "currentArrival": payload["currentArrival"],
                "assumptions": payload.get("assumptions") or [],
            }, sort_keys=True, allow_nan=False).encode()).hexdigest()
        except (ValueError, TypeError):
            raise HTTPException(400,"Successor inputs must contain finite JSON values") from None
        prior_id = (predecessor.evidence.get("successorRequests") or {}).get(successor_key)
        if prior_id and engine.get(prior_id):
            return engine.get(prior_id).to_dict()

    try:
        if domain == "vessel":
            problem = _vessel_problem(engine, payload, actor, moment, basis, mode)
        elif domain == "port":
            problem = _port_problem(engine, payload, actor, moment, basis, mode, header_port)
        elif domain == "cargo":
            problem = _cargo_problem(engine, payload, actor, moment, basis, mode, header_port)
        else:
            raise HTTPException(status_code=400, detail="domain must be vessel, port or cargo")
    except DecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if predecessor is not None:
        problem.evidence["predecessorDecisionId"] = predecessor.decision_id
        predecessor.evidence["successorDecisionId"] = problem.decision_id
        successors = predecessor.evidence.setdefault("successorDecisionIds", [])
        if problem.decision_id not in successors:
            successors.append(problem.decision_id)
        predecessor.evidence.setdefault("successorRequests", {})[successor_key] = problem.decision_id
        engine._record(problem)
        engine._record(predecessor)
    return problem.to_dict()


def _vessel_problem(engine, payload, actor, moment, basis, mode) -> DecisionProblem:
    vessel_id = str(payload.get("vesselId") or "").strip()
    if not vessel_id:
        raise HTTPException(status_code=400, detail="vesselId is required for a vessel decision")
    if payload.get("currentArrival") is not None:
        from src.portwatch_os.sandbox import current_sandbox
        from src.portwatch_os.clock import get_clock, LIVE
        from backend.app.routes.company import resolve_company
        from src.portwatch_os.decision.current_arrival import build_arrival_problem
        if current_sandbox.get() is None:
            raise HTTPException(403,"The current approach comparison is an isolated demo capability")
        if get_clock().state.mode != LIVE or payload.get("at"):
            raise HTTPException(409,"Current forecasts cannot be injected into a historical or projected decision clock")
        profile = resolve_company(payload.get("companyId"))
        vessel = next((v for v in profile.vessels if v.vessel_id == vessel_id),None)
        if vessel is None:
            raise HTTPException(404,"Voyage is not in this demo fleet")
        _build, _events, state = _observed_state(payload.get("companyId"),mode,moment)
        problem = build_arrival_problem(vessel,payload["currentArrival"],actor,state,moment)
        if connected_basis(problem).get("cargoCommitment"):
            from src.portwatch_os.decision.passage_cargo_integration import bind_declaration
            bind_declaration(problem, predecessor_id=payload.get("predecessorDecisionId"), persist=False)
            # Persist the frozen assessment first. An interrupted mirror save
            # may leave an inspectable unused comparison, never a declaration
            # pointing to a comparison which the ledger cannot recover.
            problem = engine.finish(problem)
            bind_declaration(problem, predecessor_id=payload.get("predecessorDecisionId"))
            return problem
        return engine.finish(problem)
    branch_id = payload.get("branchId")
    grid, marine = _marine_grid(mode)
    # Figures the hull does not declare, supplied for this scenario. Numbers
    # only, positive, and named -- the builder refuses anything it does not
    # know how to read.
    attributes: Dict[str, float] = {}
    for name, value in (payload.get("vesselAssumptions") or {}).items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"vessel assumption {name} must be a number")
        if number <= 0:
            raise HTTPException(status_code=400, detail=f"vessel assumption {name} must be positive")
        attributes[str(name)] = number
    if branch_id:
        held = get_registry().get(str(branch_id))
        if held is None:
            raise HTTPException(status_code=404, detail=f"no branch {branch_id}")
        seeds = dict(held.seeds)
        seed_key = str(payload.get("seed") or (next(iter(seeds)) if seeds else ""))
        if seed_key not in seeds:
            raise HTTPException(status_code=400, detail="seed must name one of the branch's assumed events")
        # The branch's world is the observed world for this decision: the
        # assumed closure is on it, labelled, and every option forks from it.
        state = ObservedWorldState(
            state_id=f"{held.parent.state_id}+{held.branch_id}", revision=held.parent.revision,
            at=moment, graph=held.graph, traffic_mode=held.parent.traffic_mode,
        )
        problem = engine.solve_vessel(
            state, event_key=seed_key, seed=seeds[seed_key], vessel_id=vessel_id, actor=actor,
            at=moment, grid=grid, attention_item_id=payload.get("attentionId"), basis=basis,
            attribute_assumptions=attributes or None,
        )
        problem.evidence["branch"] = held.summary(current_revision=None)
    else:
        event_id = str(payload.get("eventId") or "").strip()
        if not event_id:
            raise HTTPException(status_code=400, detail="eventId or branchId is required for a vessel decision")
        build, events, state = _observed_state(payload.get("companyId"), mode, moment)
        event = _event_or_404(events, event_id)
        problem = engine.solve_vessel(
            state, event_key=key(EVENT, event_id), seed=seed_for(event), vessel_id=vessel_id, actor=actor,
            at=moment, grid=grid, attention_item_id=payload.get("attentionId"), basis=basis,
            attribute_assumptions=attributes or None,
        )
    problem.evidence["marine"] = {**(problem.evidence.get("marine") or {}), "availability": marine}
    return problem


def _port_problem(engine, payload, actor, moment, basis, mode, header_port) -> DecisionProblem:
    from backend.app.routes.port_twin import build_state_for

    port_code = str(payload.get("portCode") or header_port or "").strip().upper()
    if not port_code:
        raise HTTPException(status_code=400, detail="portCode is required for a port decision")
    state = build_state_for(port_code)
    assumed: Dict[str, Any] = {}
    bunch = payload.get("bunchArrivals")
    if bunch:
        # A scenario assumption, recorded as one: the first N approaching calls
        # are placed within ninety minutes of each other so the bunching case
        # exists to decide about. The observed twin is not edited; this is a
        # clone with the assumption on it.
        state = state.clone()
        approaching = [c for c in state.calls if c.state == "approaching"][: int(bunch)]
        base = float(payload.get("bunchAtHour") or 3.0)
        for index, call in enumerate(approaching):
            call.eta_hour = base + index * 0.5
        assumed = {"kind": "bunch_arrivals", "calls": [c.call_id for c in approaching], "atHour": base,
                   "source": "ASSUMPTION"}
    camera_basis = None
    if payload.get("cameraPlanning") is not None:
        from backend.app.identity import require_verified
        from backend.app.routes.intelligence import registry, may_write
        from src.portwatch_os.intelligence.camera_planning import CameraPlanningAssumption, apply_camera_hold
        camera_request = CameraPlanningAssumption.model_validate(payload["cameraPlanning"])
        camera_operator = require_verified()
        may_write(camera_operator, state.port_code)
        state, camera_basis = apply_camera_hold(state, camera_request, registry(), camera_operator)
    build, _events, observed = _observed_state(payload.get("companyId"), mode, moment)
    scenario_evidence = {"assumedBunching": assumed} if assumed else {}
    scenario_notes = ["arrival bunching is a scenario assumption on a clone of the observed twin"] if assumed else []
    scenario_id = observed.state_id
    if camera_basis:
        import json
        import hashlib
        scenario_evidence["cameraPlanning"] = camera_basis
        scenario_id += "+camera:" + hashlib.sha256(json.dumps(camera_basis, sort_keys=True).encode()).hexdigest()[:16]
        scenario_notes.append(
            f"Reviewed camera {camera_basis['observation']['cameraId']} at {camera_basis['observation']['observedAt']}: "
            f"mapping to {camera_request.berthId} and holding for {camera_request.holdHours:g}h are operator assumptions; "
            "only this berth is affected and no vessel identity is inferred. Observed state is unchanged.")
    problem = engine.solve_port(
        state, actor=actor, at=moment, world_state_id=scenario_id,
        world_revision=observed.summary()["revision"],
        horizon_hours=float(payload.get("horizonHours") or 24.0),
        attention_item_id=payload.get("attentionId"), basis=basis,
        evidence=scenario_evidence, notes=scenario_notes,
    )
    return problem


def _cargo_problem(engine, payload, actor, moment, basis, mode, header_port) -> DecisionProblem:
    from backend.app.routes.company import resolve_company
    from backend.app.routes.port_twin import build_state_for
    from src.portwatch_os.cargo.model import demo_manifest, zones_from_state
    from src.portwatch_os.fleet.company import capacities_for

    port_code = str(payload.get("portCode") or header_port or "").strip().upper()
    if not port_code:
        raise HTTPException(status_code=400, detail="portCode is required for a cargo decision")
    profile = resolve_company(payload.get("companyId"))
    if profile is None:
        raise HTTPException(status_code=404, detail="no company account to read capacities from")
    vessels = capacities_for(profile, port_code=port_code)
    if not vessels:
        raise HTTPException(status_code=404, detail=f"no fleet vessel calls at {port_code}")
    state = build_state_for(port_code)
    zones = zones_from_state(state)
    manifest = demo_manifest(port_code)
    from src.portwatch_os.cargo.model import evaluate_connection

    from src.portwatch_os.cargo.optimizer import _best_zone

    def booked_for(shipment):
        serving = sorted((v for v in vessels if v.serves(shipment.destination_port)),
                         key=lambda v: v.departure_hour if v.departure_hour is not None else 1e9)
        return serving[0] if serving else None

    chosen = None
    wanted = payload.get("shipmentId")
    # Candidates ranked for the demo: a booking that misses its cut-off with
    # another sailing that can take it, then any consignment with a real
    # choice of sailings, then anything booked at all.
    ranked: List[tuple] = []
    for shipment in manifest:
        booked = booked_for(shipment)
        if booked is None:
            continue
        # The demo manifest carries no booking; the earliest sailing to the
        # destination stands in for it, staged in the nearest zone that can
        # take the consignment, as the cargo optimiser would place it.
        shipment.booked_vessel_id = booked.vessel_id
        if shipment.yard_block_id is None:
            zone = _best_zone(shipment, zones)
            shipment.yard_block_id = zone.zone_id if zone else None
        if wanted and shipment.shipment_id == wanted:
            chosen = shipment
            break
        zone = next((z for z in zones if z.zone_id == shipment.yard_block_id), None)
        keep = evaluate_connection(shipment, booked, zone=zone)
        others = [v for v in vessels if v.serves(shipment.destination_port) and v.vessel_id != booked.vessel_id]
        alternative_ok = any(evaluate_connection(shipment, v, zone=zone).feasible for v in others)
        rank = 0 if (not keep.feasible and alternative_ok) else 1 if others else 2
        ranked.append((rank, len(ranked), shipment))
    if chosen is None and not wanted and ranked:
        chosen = min(ranked, key=lambda row: (row[0], row[1]))[2]
    if chosen is None:
        raise HTTPException(status_code=404, detail="no consignment in the manifest has a booking to decide about")
    build, _events, observed = _observed_state(payload.get("companyId"), mode, moment)
    return engine.solve_cargo(
        chosen, vessels, zones, actor=actor, at=moment, port_code=port_code,
        world_state_id=observed.state_id, world_revision=observed.summary()["revision"],
        attention_item_id=payload.get("attentionId"), basis=basis,
    )


@router.get("/decisions/problems")
def list_problems(
    limit: int = Query(20, ge=1, le=100),
    actor_name: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
) -> Dict[str, Any]:
    """This process's problems first, then the ledger's from before it started;
    only the ones the caller may see."""
    identity = _identity(role, actor_name, header_port, organisation, vessel_ids)
    engine = get_engine()
    rows = [p.to_dict(include_options=False) for p in engine.all()
            if may_see_decision(identity, p.actor.to_dict(), {"type": p.subject_type, "id": p.subject_id}, p.domain)]
    rows.reverse()
    held = {r["decisionId"] for r in rows} | {p.decision_id for p in engine.all()}
    restored = 0
    if engine.ledger is not None:
        # A scoped identity's rows may sit behind other tenants' newer ones,
        # so the ledger applies the visibility rule itself, before the page,
        # and never reads a body to do it. This process's own problems are
        # in the ledger too: they are asked for on top and skipped.
        def visible(actor: Dict[str, Any], subject: Dict[str, Any], domain: str) -> bool:
            return may_see_decision(identity, actor, subject, domain)

        for problem_id in engine.ledger.visible_decision_problem_ids(visible, limit=limit + len(held)):
            if len(rows) >= limit:
                break
            if problem_id in held:
                continue
            body = _from_ledger(engine, problem_id) or {}
            if not may_see_decision(identity, body.get("actor") or {}, body.get("subject") or {}, str(body.get("domain") or "")):
                continue
            body.pop("options", None)
            rows.append(body)
            restored += 1
    return {"problems": rows[:limit], "total": len(rows), "restoredFromLedger": restored,
            "scope": identity.to_dict()}


@router.get("/decisions/problems/{decision_id}")
def get_problem(
    decision_id: str,
    actor_name: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
) -> Dict[str, Any]:
    identity = _identity(role, actor_name, header_port, organisation, vessel_ids)
    engine = get_engine()
    problem = engine.get(decision_id)
    if problem is not None:
        return _visible_or_403(problem, identity).to_dict()
    restored = _from_ledger(engine, decision_id)
    if restored is None:
        raise HTTPException(status_code=404, detail=f"no decision {decision_id} in this process or its ledger")
    if not may_see_decision(identity, restored.get("actor") or {}, restored.get("subject") or {},
                            str(restored.get("domain") or "")):
        raise HTTPException(status_code=403, detail=f"decision {decision_id} is not held by {identity.role}")
    return restored


@router.post("/decisions/problems/{decision_id}/transition")
def transition_problem(
    decision_id: str,
    payload: Dict[str, Any] = Body(...),
    actor_name: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
) -> Dict[str, Any]:
    """One workflow step, attributed. APPROVED needs ``optionId``."""
    engine = get_engine()
    name = _require_actor_name(actor_name)
    target = str(payload.get("target") or "").upper()
    held = _visible_or_403(_problem_or_404(engine, decision_id),
                           _identity(role, actor_name, header_port, organisation, vessel_ids))
    current_revision = None
    from src.portwatch_os.decision.continuation import connected_basis
    environment = connected_basis(held)
    if target == APPROVED and environment:
        proposal = held.evidence.get("companyProposal") or {}
        if environment.get("passagePlan") and proposal and payload.get("optionId") != proposal.get("optionId"):
            raise HTTPException(409,"Port review must preserve the Company's selected passage plan. Company must create and approve a linked successor to propose a different plan.")
        from src.portwatch_os.decision.continuation import require_current
        require_current(held)
        from src.portwatch_os.intelligence.current_environment import instant
        from src.portwatch_os.clock import wall_now, get_clock, LIVE
        from datetime import timedelta
        if get_clock().state.mode != LIVE or instant(environment["plannedArrival"]) <= wall_now() or wall_now()-instant(environment["availableAt"]) > timedelta(hours=1):
            raise HTTPException(409,"The frozen weather receipt or planned arrival has expired; recompute this comparison")
        # This comparison consumes approach weather and explicit limits, not the
        # unrelated Suez cascade/fleet revision. Preserve that boundary in audit.
        held.evidence["approvalBasis"] = {"scope":"FROZEN_AUTHORITY_RESTRICTION" if environment.get('kind')=='NOTICE_RESTRICTION' else "FROZEN_INTELLIGENCE_SCENARIO" if held.evidence.get("intelligenceBasis") else "FROZEN_APPROACH_WEATHER", "environmentEvidenceId":environment["evidenceId"],
            "availableAt":environment["availableAt"], "note":"Only frozen inputs and explicit assumptions drive this comparison; ambient cascade revisions are not consumed."}
    elif target == APPROVED and held.world_revision.get("mode") not in (None, "REPLAY"):
        # The live world's revision now, so an approval on a world that has
        # moved on is refused unless acknowledged.
        try:
            build, _events = _world_build(payload.get("companyId"), mode=held.world_revision.get("mode"))
            current_revision = {
                "mode": build.revision.mode, "eventsStamp": build.revision.events_stamp[:48],
                "fleetStamp": build.revision.fleet_stamp[:48],
                "observedGeneration": build.revision.observed_generation,
                "fingerprint": build.revision.fingerprint,
            }
        except HTTPException:
            current_revision = None
    try:
        problem = engine.transition(
            decision_id, target, actor=name, note=str(payload.get("note") or ""),
            option_id=payload.get("optionId"), current_revision=current_revision,
            acknowledge_moved_world=bool(payload.get("acknowledgeMovedWorld")),
        )
    except DecisionError as exc:
        raise HTTPException(status_code=409 if "moved on" in str(exc) else 400, detail=str(exc))
    from src.portwatch_os.sandbox import current_sandbox
    scoped = current_sandbox.get()
    if scoped and scoped.save_world and target == APPROVED and problem.domain == VESSEL_ROUTING and (
        not connected_basis(problem) or problem.actor.role == "SHIPPING_COMPANY"):
        chosen = next((o for o in problem.options if o.option_id == payload.get("optionId")), None)
        if chosen and chosen.evaluation:
            eta = chosen.evaluation.objectives.get("eta")
            proposal = {"decisionId":decision_id,"optionId":chosen.option_id,"vesselId":problem.subject_id,
                        "etaShiftHours":eta.value if eta else None,"state":"APPROVED_DEMO","source":"original constrained decision workflow"}
            if connected_basis(problem):
                proposal.update(etaShiftHours=chosen.evaluation.derived["arrivalShiftHours"],
                    arrivalAt=chosen.evaluation.derived["arrivalAt"],portCode=chosen.evaluation.derived["destinationPort"],
                    environmentEvidenceId=connected_basis(problem)["evidenceId"])
                action = _approved_operational_action(problem, chosen)
                if action:
                    proposal.update(operationalEpisode=action["operationalEpisode"], approvedAction=action)
            def update(world):
                history = world.setdefault("weatherJourneys", {})
                if connected_basis(problem):
                    previous = world.get("terminalProposal") or {}
                    if previous.get("environmentEvidenceId"):
                        history.setdefault(previous["decisionId"], {"proposal":previous,
                            "reviewDecisionId":world.get("currentArrivalReview")})
                    history.setdefault(decision_id, {}).update(proposal=proposal)
                if connected_basis(problem) and (world.get("terminalProposal") or {}).get("decisionId") != decision_id:
                    world.pop("currentArrivalReview", None)
                    world.pop("currentArrivalOutcome", None)
                world["terminalProposal"] = proposal
            scoped.save_world(update)
            scoped.world["terminalProposal"] = proposal
    return problem.to_dict()


@router.post("/decisions/problems/{decision_id}/handoff")
def handoff_problem(
    decision_id: str,
    payload: Dict[str, Any] = Body(default={}),
    actor_name: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    admin: Optional[str] = Header(None, alias="X-PortWatch-Admin"),
) -> Dict[str, Any]:
    """Hand an approved option into the advisory boundary as DRAFT advisories.

    Only an issuer -- a port authority or national command -- can, and only
    through the advisory store's own authorisation. A shipping company or
    vessel operator executes its own routing choice and records the outcome;
    it is told so rather than handed a door it may not use.
    """
    from backend.app.routes.advisories import _default_validity, principal_from_request
    from src.portwatch_os.advisories.model import Advisory, AdvisoryError, ISSUER
    from src.portwatch_os.advisories.store import AuthorisationError, get_advisory_store
    from src.portwatch_os.ledger.schema import ACTION_PENDING, DecisionRecord, utc_now
    from src.portwatch_os.ledger.store import get_ledger
    from src.utils import port_registry

    engine = get_engine()
    name = _require_actor_name(actor_name)
    problem = _visible_or_403(_problem_or_404(engine, decision_id),
                              _identity(role, actor_name, header_port, organisation, None))
    if connected_basis(problem) and problem.evidence.get("advisories"):
        acting = principal_from_request(name, role, header_port, organisation, None)
        rows = [get_advisory_store().require(i) for i in problem.evidence["advisories"]]
        for row in rows: acting.assert_may_issue(row)
        return {"decision":problem.to_dict(include_options=False), "advisories":[r.to_dict() for r in rows]}
    if connected_basis(problem):
        from src.portwatch_os.decision.continuation import require_current
        require_current(problem)
    if problem.workflow != APPROVED:
        raise HTTPException(status_code=400, detail=f"a decision is handed off once APPROVED; {decision_id} is {problem.workflow}")
    option = problem.option(problem.human_choice or "")
    if option is None:
        raise HTTPException(status_code=400, detail="no approved option to hand off")
    if option.is_baseline:
        raise HTTPException(
            status_code=400,
            detail="the approved option is the current plan; continuing it needs no advisory. Record the "
                   "outcome with /outcome once observed.",
        )

    # Administrator standing follows the role; the X-PortWatch-Admin flag is
    # not honoured (backend.app.identity).
    acting = principal_from_request(name, role, header_port, organisation, None)
    if acting.role != ISSUER:
        raise HTTPException(
            status_code=403,
            detail=(f"{acting.actor} acts as a recipient and executes its own choice; record the outcome "
                    "with /outcome once observed. A port authority or national command hands the same "
                    "option to the vessel as an advisory."),
        )

    port_code = problem.subject_id if problem.domain == PORT_BERTHING else (
        (option.evaluation.derived.get("destinationPort") if option.evaluation else None) or header_port or ""
    )
    record = port_registry.resolve(port_code or "")
    created = utc_now()
    store = get_advisory_store()
    advisories: List[Dict[str, Any]] = []

    recipients = _recipients_for(problem, option, payload)
    from src.portwatch_os.sandbox import current_sandbox
    scoped = current_sandbox.get()
    if scoped:
        owned = {v["id"] for v in scoped.world["fleet"]}
        for recipient in recipients:
            if recipient["vesselId"] in owned:
                recipient["organisation"] = scoped.world["organisation"]
    if not recipients:
        raise HTTPException(status_code=400, detail="the approved option names no vessel to advise")
    approved_action = _approved_operational_action(problem, option)
    for recipient in recipients:
        advisory = Advisory(
            advisory_id=Advisory.make_id(port_code, recipient["vesselId"], recipient["kind"],
                decision_id if connected_basis(problem) else created),
            kind=recipient["kind"], port_code=(record.locode if record else port_code),
            issuer=acting.actor,
            issuer_organisation=str(payload.get("issuerOrganisation") or (record.authority if record else port_code)),
            recipient_vessel_id=recipient["vesselId"], recipient_vessel_name=recipient["vesselName"],
            recipient_organisation=str(payload.get("recipientOrganisation") or recipient.get("organisation") or "Unknown operator"),
            created_at=created, recommendation=recipient["recommendation"],
            reason=f"{problem.recommendation.statement if problem.recommendation else option.label} "
                   f"Decision {decision_id}, option {option.option_id}, approved by {name}.",
            model_confidence=None if option.evaluation is None else option.evaluation.weakest_confidence,
            evidence={"decisionId": decision_id, "optionId": option.option_id,
                      **({"approvedAction": approved_action} if approved_action else {}),
                      **({"intelligenceBasis" if problem.evidence.get("intelligenceBasis") else "currentEnvironment":connected_basis(problem)} if connected_basis(problem) else {}),
                      **{k: m.value for k, m in (option.evaluation.objectives.items() if option.evaluation else [])
                         if m.available}},
            critic_verdict=(option.critic or {}).get("verdict"),
            critic_reasons=list((option.critic or {}).get("reasons") or []),
            valid_until=payload.get("validUntil") or _default_validity(),
        )
        try:
            store.create(advisory, principal=acting)
        except (AdvisoryError, AuthorisationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        decision = DecisionRecord(
            decision_id=DecisionRecord.make_id("decision_handoff", advisory.advisory_id, created, acting.actor),
            kind=f"advisory:{advisory.kind}", subject=advisory.recipient_vessel_id, issued_at=created,
            issuer=acting.actor, recommendation=advisory.recommendation, reason=advisory.reason,
            confidence=advisory.model_confidence,
            expected_impact={k: float(v) for k, v in advisory.evidence.items() if isinstance(v, (int, float))},
            critic_verdict=advisory.critic_verdict, critic_reasons=advisory.critic_reasons,
            approval_state="draft", action_state=ACTION_PENDING,
        )
        get_ledger().record_decision(decision)
        advisory.decision_id = decision.decision_id
        store._write(advisory)  # noqa: SLF001 - same module family as /advisories
        advisories.append(advisory.to_dict())

    try:
        engine.transition(decision_id, PROPOSED, actor=name,
                          note=f"{len(advisories)} DRAFT advisory(ies) raised: " + ", ".join(a["advisoryId"] for a in advisories))
    except DecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    problem.evidence["advisories"] = [a["advisoryId"] for a in advisories]
    engine._record(problem)  # noqa: SLF001 - keep the ledger row's evidence current
    return {"decision": problem.to_dict(include_options=False), "advisories": advisories}


def _approved_operational_action(problem: DecisionProblem, option) -> Optional[Dict[str, Any]]:
    """Identify the chosen plan while keeping approval separate from execution."""
    basis = connected_basis(problem) or {}
    episode = basis.get("operationalEpisode")
    if not episode:
        return None
    from src.portwatch_os.learning.shared_feedback import (
        identifier, operational_action_basis, operational_action_id, operational_metric_basis)
    action_id = operational_action_id(basis, option)
    targets = {}
    for metric in ("SCHEDULE_SHIFT", "WAITING", "ACCESS_TIME"):
        metric_basis = operational_metric_basis(basis, option, metric)
        targets[metric] = {"metricBasis": metric_basis, "metricBasisSha256": identifier(metric_basis),
                           "independentTargetKey": identifier([episode["namespace"], episode["id"], metric])}
    return {"contractVersion": "operational-action-v1", "kind": "APPROVED_CONDITIONAL_PLAN",
            "operationalEpisode": episode,
            "operationalActionId": action_id, "actionBasisSha256": action_id,
            "actionBasis": operational_action_basis(basis, option),
            "measurementTargets": targets,
            "action": option.action, "parameters": option.params, "decisionId": problem.decision_id,
            "optionId": option.option_id, "evidenceId": basis["evidenceId"],
            **({"passageCalculation": {
                "version": (basis.get("passageComparison") or {}).get("version"),
                "inputVersion": (basis.get("passageComparison") or {}).get("inputVersion") or option.params.get("passagePlanVersion"),
                "inputs": copy.deepcopy(basis["passagePlan"]),
                "selected": copy.deepcopy(option.evaluation.derived),
                "financial": copy.deepcopy(option.evaluation.financial),
            }} if basis.get("passagePlan") else {}),
            **({"cargoCalculation": {
                "version": basis["cargoComparison"]["version"],
                "inputVersion": basis["cargoComparison"]["inputVersion"],
                "inputs": copy.deepcopy(basis["cargoCommitment"]),
                "selected": copy.deepcopy(option.evaluation.derived["cargoAssessment"]),
                "executionAuthority": "Assessment only; navigation acceptance does not book or execute a cargo alternative",
            }} if basis.get("cargoCommitment") else {}),
            "approvedAt": next((h["at"] for h in problem.workflow_history if h["state"] == "APPROVED"), None),
            "actualExecutionStatus": "NOT_OBSERVED", "actualExecutionAt": None}


def _recipients_for(problem: DecisionProblem, option, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Who the approved option is addressed to, and as which advisory kind."""
    if problem.domain == VESSEL_ROUTING:
        derived = option.evaluation.derived if option.evaluation else {}
        if connected_basis(problem):
            if connected_basis(problem).get("passagePlan"):
                return [{"vesselId":problem.subject_id,"vesselName":problem.subject_label,"kind":"arrival_window",
                    "recommendation":{
                        "recommendedArrival":derived["arrivalAt"], "approachClearAt":derived.get("approachClearAt"),
                        "action":option.action, "recommendedSpeedKn":derived.get("speedKn"),
                        "departureAt":derived.get("departureAt"),
                        "arrivalShiftHours":derived["arrivalShiftHours"], "holdHours":derived["holdHours"],
                        "sailingHours":derived.get("sailingHours"), "anchorageWaitHours":derived.get("anchorageWaitHours"),
                        "totalElapsedHours":derived.get("totalElapsedHours"),
                        "scheduleShiftHours":derived.get("scheduleShiftHours"), "deadlineMet":derived.get("deadlineMet"),
                        "passagePlanVersion":option.params.get("passagePlanVersion"),
                        "basis":"Company-proposed passage under frozen operator inputs and hourly approach forecasts; Port review is advisory and does not command vessel navigation"},
                    "organisation":payload.get("recipientOrganisation")}]
            return [{"vesselId":problem.subject_id,"vesselName":problem.subject_label,"kind":"arrival_window",
                "recommendation":{"recommendedArrival":derived["arrivalAt"],"approachClearAt":derived.get("approachClearAt"),
                    "arrivalShiftHours":derived["arrivalShiftHours"],"holdHours":derived["holdHours"],
                    "requestedPassageAt":derived.get('requestedPassageAt'),"earliestScheduledAccess":derived.get('earliestScheduledAccess'),
                    "actualEarliestPermittedAccess":derived.get('actualEarliestPermittedAccess'),
                    "totalScheduleShiftHours":derived.get('totalScheduleShiftHours'),
                    "basis":"Authority-published lock closure and declared route; first published operational tide requires operator confirmation" if connected_basis(problem).get('kind')=='NOTICE_RESTRICTION' else "Reported intelligence with explicit operator-assumed review hold" if problem.evidence.get("intelligenceBasis") else "Current public forecast under frozen operator demo assumptions"},
                "organisation":payload.get("recipientOrganisation")}]
        recommendation: Dict[str, Any] = {"approach": option.label, "action": option.action,
                                          "speedKn": derived.get("speedKn"), "holdHours": derived.get("holdHours")}
        if option.action in ("SLOW_STEAM", "SPEED_UP") and derived.get("speedKn"):
            kind = "speed"
            recommendation = {"recommendedSpeedKn": derived["speedKn"], "action": option.action,
                              "holdHours": derived.get("holdHours")}
        else:
            kind = "approach"
        return [{"vesselId": problem.subject_id, "vesselName": problem.subject_label, "kind": kind,
                 "recommendation": recommendation, "organisation": payload.get("recipientOrganisation")}]
    if problem.domain == PORT_BERTHING and option.action == SHIFT_ARRIVAL_SLOT:
        out = []
        derived = option.evaluation.derived if option.evaluation else {}
        for row in derived.get("assignments", []):
            if row.get("imposedDelayHours"):
                out.append({"vesselId": row["callId"], "vesselName": row.get("name") or row["callId"], "kind": "arrival_window",
                            "recommendation": {"recommendedArrival": f"+{row['imposedDelayHours']:.0f}h",
                                               "arrivalShiftHours": row["imposedDelayHours"]},
                            "organisation": payload.get("recipientOrganisation")})
        return out
    if problem.domain == PORT_BERTHING:
        derived = option.evaluation.derived if option.evaluation else {}
        vessel = payload.get("vesselId")
        rows = [r for r in derived.get("assignments", []) if r.get("berthId") and (not vessel or r["callId"] == vessel)]
        return [{"vesselId": r["callId"], "vesselName": r.get("name") or r["callId"], "kind": "berth",
                 "recommendation": {"recommendedBerth": r["berthId"], "action": option.action},
                 "organisation": payload.get("recipientOrganisation")} for r in rows[:3]]
    return []


@router.post("/decisions/problems/{decision_id}/outcome")
def record_outcome(
    decision_id: str,
    payload: Dict[str, Any] = Body(...),
    actor_name: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
) -> Dict[str, Any]:
    """What actually happened. Resolves the ledger rows; nothing is rewritten."""
    engine = get_engine()
    name = _require_actor_name(actor_name)
    held = _problem_or_404(engine, decision_id)
    _visible_or_403(held,
                    _identity(role, actor_name, header_port, organisation, vessel_ids))
    if connected_basis(held):
        raise HTTPException(409,"This fictional weather comparison accepts only the labelled demo-outcome after advisory acceptance; it cannot resolve an observed forecast outcome")
    observed = payload.get("observed") or {}
    if not isinstance(observed, dict):
        raise HTTPException(status_code=400, detail="observed must be an object of objective -> value")
    try:
        problem = engine.record_outcome(
            decision_id, actor=name, actual_action=str(payload.get("actualAction") or ""),
            observed=observed, note=str(payload.get("note") or ""),
        )
    except DecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return problem.to_dict(include_options=False)


@router.get("/decisions/learning")
def decision_learning(
    domain: Optional[str] = Query(None),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
) -> Dict[str, Any]:
    """Did the recommendations help? Scored from the ledger alone. The ledger
    holds every tenant's decisions, so the score is National Command's."""
    from src.portwatch_os.decision.learning import score_history
    from src.portwatch_os.ledger.store import get_ledger

    resolve_role(role, admin_surface=True)
    rows = get_ledger().decision_problems(domain=domain)
    return score_history(rows)


__all__ = ["router"]
