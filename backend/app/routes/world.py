"""The World State Engine over HTTP, and the attention queue it feeds.

Two rules govern the shape of every payload here.

**The frontend never re-derives consequence.** A cascade arrives with its nodes,
its edges, every propagated quantity and the full step trace that produced them.
The map draws what the engine concluded; it does not re-run the reasoning in
TypeScript, because two implementations of the same rule are two implementations
that will eventually disagree, and the one on the screen is the one a customer
would believe.

**Time is a query parameter, not a second model.** ``at`` moves the whole world:
an event past its claim horizon stops contributing, its consequences vanish with
it, and the attention queue empties accordingly. That is what makes PROJECT 72H
a projection of this graph rather than a separate forecast that could disagree
with the present.

Visibility follows the same identity headers the rest of the operations layer
uses, so an attention queue cannot become a way around advisory scoping.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query

from src.portwatch_os.attention.engine import attention_for
from src.portwatch_os.attention.model import AttentionItem
from src.portwatch_os.roles import (
    DEFAULT_ROLE,
    NATIONAL_ADMIN,
    WORKSPACE_ROLES,
    is_workspace_role,
)
from src.portwatch_os.world.build import build_world, seed_for
from src.portwatch_os.world.cascade import Cascade, narrate, propagate
from src.portwatch_os.world.graph import (
    CHOKEPOINT,
    EVENT,
    LANE,
    PORT,
    VESSEL,
    WorldGraph,
    key,
)
from src.portwatch_os.world.quantity import utc
from src.portwatch_os.world.transfers import registered

router = APIRouter()

#: How far ahead the scrubber may ask. Past this the event register itself is
#: mostly lapsed, so a longer horizon would return an emptying world and imply
#: a confidence the graph does not have.
MAX_HORIZON_HOURS = 168.0

#: The offsets the timeline transport offers. Named here so the API and the
#: control agree on what "+24h" means without the frontend inventing its own.
PROJECTION_OFFSETS: tuple[float, ...] = (0.0, 3.0, 6.0, 12.0, 24.0, 48.0, 72.0)


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------


def _scope(role: Optional[str]) -> str:
    if not role:
        return DEFAULT_ROLE
    normalised = role.strip().upper()
    if not is_workspace_role(normalised):
        raise HTTPException(
            status_code=403,
            detail=(
                f"'{role}' is not a workspace role. Send X-PortWatch-Role with one "
                f"of: {', '.join(WORKSPACE_ROLES)}."
            ),
        )
    return normalised


def _at(at: Optional[str]) -> datetime:
    """The instant to query the world at. Defaults to now."""
    if not at:
        return utc()
    try:
        parsed = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"'{at}' is not an ISO-8601 instant.",
        )
    return utc(parsed)


# --------------------------------------------------------------------------
# world assembly
# --------------------------------------------------------------------------


def _world(company_id: Optional[str] = None):
    """The graph, and the events that seeded it.

    Rebuilt per request rather than cached: the event register is re-ingested
    and re-calibrated on every Global Eye request already, and a world graph
    that lagged behind it would be the quiet inconsistency this product exists
    to avoid.
    """
    from backend.app.routes.global_eye import _company_voyages, _load_events

    # apply_calibration() stamps probabilities onto the events in place and
    # returns how many it stamped, so the event list itself is what carries the
    # calibrated values forward.
    events, _report, _calibrator, _stamped_count = _load_events()
    voyages = _company_voyages(company_id)
    graph = build_world(events=events, voyages=voyages)
    return graph, events


def _event_or_404(events, event_id: str):
    for event in events:
        if event.event_id == event_id:
            return event
    raise HTTPException(status_code=404, detail=f"no event {event_id}")


def _cascade_payload(
    cascade: Cascade,
    graph: WorldGraph,
    *,
    include_steps: bool = True,
) -> Dict[str, Any]:
    """The full consequence, shaped so the map can draw it without thinking.

    Affected subjects are pulled out by kind rather than left for the client to
    filter, because "which lanes light up" is a question about the cascade and
    answering it twice invites the two answers to differ.
    """
    payload = cascade.to_dict(include_steps=include_steps)
    payload["narrative"] = narrate(cascade)
    payload["affected"] = {
        "chokepoints": [_subject(r) for r in cascade.by_kind(CHOKEPOINT)],
        "lanes": [_subject(r) for r in cascade.by_kind(LANE)],
        "vessels": [_subject(r) for r in cascade.by_kind(VESSEL)],
        "ports": [_subject(r) for r in cascade.by_kind(PORT)],
    }
    payload["totals"] = {
        unit: quantity.to_dict()
        for unit in ("risk", "vessels", "hours", "ratio", "inr")
        if (quantity := cascade.total(unit)) is not None
    }
    return payload


def _subject(reached) -> Dict[str, Any]:
    """One affected thing, with the geometry the map needs to place it."""
    node = reached.node
    return {
        "key": node.key,
        "id": node.identifier,
        "kind": node.kind,
        "label": node.label,
        "depth": reached.depth,
        "lat": node.attrs.get("lat"),
        "lon": node.attrs.get("lon"),
        "attrs": node.attrs,
        "quantities": {u: q.to_dict() for u, q in sorted(reached.quantities.items())},
        "steps": reached.step_indices,
    }


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------


@router.get("/world/state")
def world_state(
    at: Optional[str] = Query(None, description="ISO instant. Defaults to now."),
    company_id: Optional[str] = Query(None, alias="companyId"),
) -> Dict[str, Any]:
    """What the world contains at one instant, and how it is wired.

    The structural answer, without any consequence in it. A client uses this to
    know what exists before asking what any of it is doing.
    """
    moment = _at(at)
    graph, events = _world(company_id)
    view = graph.at(moment)
    return {
        "at": moment.isoformat(),
        "summary": view.summary(),
        "nodes": [n.to_dict() for n in view.nodes()],
        "edges": [e.to_dict() for e in view.edges()],
        "rules": registered(),
        "projectionOffsets": list(PROJECTION_OFFSETS),
        "maxHorizonHours": MAX_HORIZON_HOURS,
    }


@router.get("/world/cascades")
def world_cascades(
    at: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None, alias="companyId"),
    limit: int = Query(12, ge=1, le=64),
) -> Dict[str, Any]:
    """Every live event's consequence, worst first.

    Steps are omitted here and served in full by the detail route: a list of
    twelve cascades with every trace attached would be megabytes, and the
    frontend needs the traces only for the one a person actually opened.
    """
    moment = _at(at)
    graph, events = _world(company_id)

    rows: List[Dict[str, Any]] = []
    for event in events:
        seed_key = key(EVENT, event.event_id)
        if graph.node(seed_key) is None:
            continue
        cascade = propagate(graph, seed_key, seed_for(event), at=moment)
        if len(cascade.reached) <= 1:
            # Nothing followed from it at this instant. Reported as a lapsed or
            # inert event rather than dropped, so the timeline can show it
            # falling quiet rather than simply vanishing.
            rows.append({
                "eventId": event.event_id,
                "seed": seed_key,
                "title": event.title,
                "live": False,
                "reason": (
                    "no consequence propagates from this event at the queried "
                    "instant"
                ),
                "nodeCount": 0,
            })
            continue
        payload = _cascade_payload(cascade, graph, include_steps=False)
        payload.update({
            "eventId": event.event_id,
            "title": event.title,
            "live": True,
            "category": event.category,
            "lat": event.lat,
            "lon": event.lon,
        })
        rows.append(payload)

    rows.sort(key=lambda r: -(r.get("nodeCount") or 0))
    return {"at": moment.isoformat(), "cascades": rows[:limit], "total": len(rows)}


@router.get("/world/cascades/{event_id}")
def world_cascade(
    event_id: str,
    at: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None, alias="companyId"),
    actor: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
) -> Dict[str, Any]:
    """One event's full consequence, with the trace that produced every number.

    This is the payload Evidence Mode reads. Each step names the rule that ran,
    the quantity in, the quantity out and the catalogue the relationship came
    from, so "why do you think this?" is answered from the computation itself
    rather than by a second explanation system that could drift from it.
    """
    moment = _at(at)
    graph, events = _world(company_id)
    event = _event_or_404(events, event_id)
    seed_key = key(EVENT, event_id)
    if graph.node(seed_key) is None:
        raise HTTPException(
            status_code=404, detail=f"event {event_id} is not in the world graph"
        )

    cascade = propagate(graph, seed_key, seed_for(event), at=moment)
    payload = _cascade_payload(cascade, graph, include_steps=True)
    payload.update({
        "eventId": event.event_id,
        "title": event.title,
        "category": event.category,
        "lat": event.lat,
        "lon": event.lon,
        "live": len(cascade.reached) > 1,
    })

    scope = _scope(role)
    payload["attentionItems"] = [
        item.to_dict()
        for item in attention_for(
            cascade,
            scope=scope,
            now=moment,
            port_code=header_port,
            organisation=organisation,
            vessel_ids=[v.strip() for v in (vessel_ids or "").split(",") if v.strip()],
            limit=8,
        )
    ]
    return payload


@router.post("/world/cascade/simulate")
def simulate_cascade(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Project one event's consequence across several instants.

    The signature "what happens next" interaction. Every horizon is the *same*
    graph queried at a different time, so a projection cannot contradict the
    present: an event past its claim horizon simply stops reaching anything, and
    the caller sees the consequence drain away rather than a second model's
    opinion of the future.
    """
    event_id = str(payload.get("eventId") or "").strip()
    if not event_id:
        raise HTTPException(status_code=400, detail="eventId is required.")

    offsets = payload.get("offsets") or list(PROJECTION_OFFSETS)
    try:
        hours = sorted({float(o) for o in offsets})
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="offsets must be numbers.")
    if any(h < 0 or h > MAX_HORIZON_HOURS for h in hours):
        raise HTTPException(
            status_code=400,
            detail=f"offsets must lie between 0 and {MAX_HORIZON_HOURS:.0f} hours.",
        )

    base = _at(payload.get("at"))
    graph, events = _world(payload.get("companyId"))
    event = _event_or_404(events, event_id)
    seed_key = key(EVENT, event_id)

    frames: List[Dict[str, Any]] = []
    for offset in hours:
        moment = base + timedelta(hours=offset)
        cascade = propagate(graph, seed_key, seed_for(event), at=moment)
        frames.append({
            "offsetHours": offset,
            "at": moment.isoformat(),
            "live": len(cascade.reached) > 1,
            "nodeCount": len(cascade.reached),
            "affected": {
                "chokepoints": [_subject(r) for r in cascade.by_kind(CHOKEPOINT)],
                "lanes": [_subject(r) for r in cascade.by_kind(LANE)],
                "vessels": [_subject(r) for r in cascade.by_kind(VESSEL)],
                "ports": [_subject(r) for r in cascade.by_kind(PORT)],
            },
            "totals": {
                unit: quantity.to_dict()
                for unit in ("risk", "vessels", "hours", "ratio", "inr")
                if (quantity := cascade.total(unit)) is not None
            },
            "notes": cascade.notes,
        })

    return {
        "eventId": event_id,
        "title": event.title,
        "base": base.isoformat(),
        "horizonHours": max(hours),
        "frames": frames,
    }


@router.get("/attention")
def attention_queue(
    at: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None, alias="companyId"),
    limit: int = Query(5, ge=1, le=25),
    actor: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
) -> Dict[str, Any]:
    """What this identity should act on, across every live event.

    Ranked by how much loss the operator's attention can still prevent, not by
    severity -- see the attention engine for why those give different orders,
    and why the operator's order is the useful one.
    """
    moment = _at(at)
    scope = _scope(role)
    held = [v.strip() for v in (vessel_ids or "").split(",") if v.strip()]
    graph, events = _world(company_id)

    collected: List[AttentionItem] = []
    for event in events:
        seed_key = key(EVENT, event.event_id)
        if graph.node(seed_key) is None:
            continue
        cascade = propagate(graph, seed_key, seed_for(event), at=moment)
        if len(cascade.reached) <= 1:
            continue
        collected.extend(
            attention_for(
                cascade,
                scope=scope,
                now=moment,
                port_code=header_port,
                organisation=organisation,
                vessel_ids=held,
                limit=0,          # rank across every event, then trim once
            )
        )

    from src.portwatch_os.attention.model import order as rank_all

    ranked = rank_all(collected)
    return {
        "at": moment.isoformat(),
        "scope": scope,
        "items": [item.to_dict() for item in ranked[:limit]],
        "total": len(ranked),
        "actionable": sum(1 for i in ranked if i.actionable),
    }


@router.get("/attention/{attention_id:path}")
def attention_item(
    attention_id: str,
    at: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None, alias="companyId"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
) -> Dict[str, Any]:
    """One item, with the cascade steps behind it. The Evidence Mode payload."""
    moment = _at(at)
    scope = _scope(role)
    held = [v.strip() for v in (vessel_ids or "").split(",") if v.strip()]
    graph, events = _world(company_id)

    for event in events:
        seed_key = key(EVENT, event.event_id)
        if graph.node(seed_key) is None:
            continue
        cascade = propagate(graph, seed_key, seed_for(event), at=moment)
        for item in attention_for(
            cascade, scope=scope, now=moment, port_code=header_port,
            organisation=organisation, vessel_ids=held, limit=0,
        ):
            if item.attention_id != attention_id:
                continue
            return {
                "item": item.to_dict(),
                "evidence": [
                    step.to_dict()
                    for step in cascade.explain(item.evidence_node_key)
                ],
                "narrative": narrate(cascade),
                "cascade": {
                    "eventId": event.event_id,
                    "title": event.title,
                    "seed": seed_key,
                    "at": moment.isoformat(),
                },
            }

    raise HTTPException(status_code=404, detail=f"no attention item {attention_id}")


__all__ = ["router"]


# --------------------------------------------------------------------------
# signal fabric
# --------------------------------------------------------------------------


@router.get("/fabric/providers")
def fabric_providers(
    mode: Optional[str] = Query(None, description="RESEARCH | DEMO | COMMERCIAL | GOVERNMENT"),
) -> Dict[str, Any]:
    """Every source this deployment knows about, and what it may be used for.

    Served rather than kept internal because "where does this number come from,
    and may we use it" is a procurement question, and a product that cannot
    answer it from its own API is asking a customer to take provenance on
    trust.
    """
    from src.portwatch_os.fabric import COMMERCIAL, MODES as FABRIC_MODES, SignalFabric

    active = (mode or COMMERCIAL).strip().upper()
    if active not in FABRIC_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"mode must be one of: {', '.join(FABRIC_MODES)}.",
        )
    return SignalFabric(mode=active).report()


@router.get("/fabric/resolve/{capability}")
def fabric_resolve(
    capability: str,
    mode: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """The best legally usable provider for one capability, or UNAVAILABLE.

    The rejected list travels with the answer. "No commercial AIS is
    configured" is only useful alongside "AISStream was rejected because its
    licence does not permit commercial use" -- the second sentence is the one
    that tells an operator what to buy.
    """
    from src.portwatch_os.fabric import CAPABILITIES, COMMERCIAL, MODES as FABRIC_MODES
    from src.portwatch_os.fabric import SignalFabric

    active = (mode or COMMERCIAL).strip().upper()
    if active not in FABRIC_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"mode must be one of: {', '.join(FABRIC_MODES)}.",
        )
    if capability not in CAPABILITIES:
        raise HTTPException(
            status_code=404,
            detail=(
                f"'{capability}' is not a capability this fabric models. "
                f"Known: {', '.join(CAPABILITIES)}."
            ),
        )
    return SignalFabric(mode=active).resolve(capability).to_dict()
