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
    # A "+" in a timezone offset arrives as a space when a client forgets to
    # percent-encode it, which most do. Tolerate it rather than 400 an
    # otherwise well-formed instant.
    normalised = at.strip().replace(" ", "+").replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalised)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"'{at}' is not an ISO-8601 instant.",
        )
    return utc(parsed)


# --------------------------------------------------------------------------
# world assembly
# --------------------------------------------------------------------------


def _mode(mode: Optional[str]) -> str:
    """The licence mode a request is asking the world to be viewed in."""
    from src.portwatch_os.fabric import MODES as FABRIC_MODES, deployment_mode

    active = (mode or deployment_mode()).strip().upper()
    if active not in FABRIC_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"mode must be one of: {', '.join(FABRIC_MODES)}.",
        )
    return active


def _observed_voyages(mode: str, now: datetime):
    """Observed hulls as voyages, only when the traffic source is observed AIS.

    The same gate as the chart: LIVE_AIS or AIS_STALE. A lapsed feed's hulls
    leave the graph as they leave the chart, and a COMMERCIAL view sees none
    of them because the product is not licensed for it.
    """
    from src.portwatch_os.fabric import AIS_STALE, LIVE_AIS, ais_mode
    from src.portwatch_os.fusion.engine import get_engine
    from src.portwatch_os.world.observed import observed_voyages

    traffic = ais_mode(licence_mode=mode, now=now)
    if traffic["mode"] not in (LIVE_AIS, AIS_STALE):
        return [], traffic
    placements = observed_voyages(get_engine(), now=now)
    return placements, traffic


def _world(company_id: Optional[str] = None, *, mode: Optional[str] = None, now: Optional[datetime] = None):
    """The graph, and the events that seeded it.

    Versioned rather than cached: the event register is re-ingested and
    re-calibrated on every request, as it always was, and the register's
    stamp, the fleet's stamp and the observed-hull generation make up the
    revision. A request at the same revision gets the same graph; a request
    at a new one gets a rebuild. See :mod:`src.portwatch_os.world.live`.

    Observed hulls are added after the fleet, keyed by their canonical id, so
    a replay vessel and an observed one never share a node. The fleet is also
    registered with the fusion engine, which is how a fleet entry with an IMO
    finds its transponder -- and how one without an IMO is offered a name
    candidate rather than merged.
    """
    build, _events = _world_build(company_id, mode=mode, now=now)
    return build.graph, build.events


def _world_build(company_id: Optional[str] = None, *, mode: Optional[str] = None, now: Optional[datetime] = None):
    from backend.app.routes.global_eye import _company_voyages, _load_events
    from src.portwatch_os.fusion.engine import get_engine
    from src.portwatch_os.world.live import Revision, get_live_world

    # apply_calibration() stamps probabilities onto the events in place and
    # returns how many it stamped, so the event list itself is what carries the
    # calibrated values forward.
    events, _report, _calibrator, _stamped_count = _load_events()
    voyages = list(_company_voyages(company_id))
    engine = get_engine()
    for voyage in voyages:
        engine.register_fleet_vessel(
            vessel_id=voyage.vessel_id, name=voyage.name, imo=getattr(voyage, "imo", None),
        )
    moment = now or utc()
    active = _mode(mode)
    live = get_live_world()
    revision = Revision(
        mode=active,
        company_id=company_id,
        events_stamp=_events_stamp(events),
        fleet_stamp="|".join(f"{v.vessel_id}:{v.eta}:{v.destination_port}" for v in voyages),
        observed_generation=live.observed_generation,
    )

    def build():
        placements, _traffic = _observed_voyages(active, moment)
        all_voyages = voyages + [p.voyage for p in placements]
        return build_world(events=events, voyages=all_voyages, now=moment), events

    built, _reason = live.graph(revision, build=build, now=moment)
    return built, events


def _events_stamp(events) -> str:
    """What the register looks like, cheaply: count, newest, and the probabilities."""
    return "|".join(
        f"{e.event_id}:{e.last_seen}:{e.probability if e.probability is not None else '-'}"
        for e in events
    )


def _cascade_for(build, event, moment: datetime):
    """One event's cascade at one instant, reused when nothing it reaches moved."""
    from src.portwatch_os.world.live import get_live_world

    seed_key = key(EVENT, event.event_id)
    return get_live_world().cascade(build, seed_key, seed_for(event), at=moment, now=utc())


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
    mode: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """What the world contains at one instant, and how it is wired.

    The structural answer, without any consequence in it. A client uses this to
    know what exists before asking what any of it is doing.
    """
    moment = _at(at)
    graph, events = _world(company_id, mode=mode)
    view = graph.at(moment)
    observed = [n for n in view.nodes() if n.kind == VESSEL and n.attrs.get("source") == "OBSERVED_AIS"]
    return {
        "at": moment.isoformat(),
        "summary": {**view.summary(), "observedVessels": len(observed)},
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
    mode: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Every live event's consequence, worst first.

    Steps are omitted here and served in full by the detail route: a list of
    twelve cascades with every trace attached would be megabytes, and the
    frontend needs the traces only for the one a person actually opened.
    """
    moment = _at(at)
    build, events = _world_build(company_id, mode=mode)
    graph = build.graph

    rows: List[Dict[str, Any]] = []
    for event in events:
        seed_key = key(EVENT, event.event_id)
        if graph.node(seed_key) is None:
            continue
        cascade, _reason = _cascade_for(build, event, moment)
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
    mode: Optional[str] = Query(None),
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
    build, events = _world_build(company_id, mode=mode)
    graph = build.graph
    event = _event_or_404(events, event_id)
    seed_key = key(EVENT, event_id)
    if graph.node(seed_key) is None:
        raise HTTPException(
            status_code=404, detail=f"event {event_id} is not in the world graph"
        )

    cascade, computed = _cascade_for(build, event, moment)
    payload = _cascade_payload(cascade, graph, include_steps=True)
    payload["computation"] = computed
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
    graph, events = _world(payload.get("companyId"), mode=payload.get("mode"))
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
    mode: Optional[str] = Query(None),
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
    graph, events = _world(company_id, mode=mode)

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

    from src.portwatch_os.attention.engine import feed_item
    from src.portwatch_os.attention.model import order as rank_all
    from src.portwatch_os.fabric import ais_mode

    # The feed's own state, when the observed picture is not current. Ranked
    # with the rest so it sits where MONITOR_ONLY items sit, not on top.
    traffic = ais_mode(licence_mode=_mode(mode), now=utc())
    feed = feed_item(traffic, scope=scope, now=moment)
    if feed is not None:
        collected.append(feed)

    ranked = rank_all(collected)
    # The feed's state qualifies every item above it, so a page that is cut
    # before it still carries it -- at the bottom, where it ranks.
    page = ranked[:limit]
    if feed is not None and feed not in page:
        page = page + [feed]
    return {
        "at": moment.isoformat(),
        "scope": scope,
        "items": [item.to_dict() for item in page],
        "total": len(ranked),
        "actionable": sum(1 for i in ranked if i.actionable),
        "observed": sum(1 for i in ranked if i.source == "OBSERVED_AIS"),
        "traffic": traffic["mode"],
    }


@router.get("/attention/{attention_id:path}")
def attention_item(
    attention_id: str,
    at: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None, alias="companyId"),
    mode: Optional[str] = Query(None),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
) -> Dict[str, Any]:
    """One item, with the cascade steps behind it. The Evidence Mode payload."""
    moment = _at(at)
    scope = _scope(role)
    held = [v.strip() for v in (vessel_ids or "").split(",") if v.strip()]
    graph, events = _world(company_id, mode=mode)

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


@router.get("/fabric/health")
def fabric_health(
    mode: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """What every signal is actually doing right now.

    The trust surface. A product that draws a vessel and a forecast on one chart
    has to be able to say, without being asked twice, which of them was observed
    two minutes ago and which is an artefact from this morning. Freshness here is
    the *reading's* age, not the age of the HTTP call that just read a file --
    the second number is always small and always meaningless.

    Traffic mode is answered from the websocket client's own state machine
    rather than a flag, so a deployment with a key that has received nothing
    cannot report LIVE.
    """
    from src.portwatch_os.fabric import COMMERCIAL, MODES as FABRIC_MODES
    from src.portwatch_os.fabric import SignalFabric, ais_mode, build_adapters

    active = (mode or COMMERCIAL).strip().upper()
    if active not in FABRIC_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"mode must be one of: {', '.join(FABRIC_MODES)}.",
        )

    fabric = SignalFabric(mode=active)
    signals: List[Dict[str, Any]] = []
    for adapter in build_adapters(licence_mode=active):
        availability = adapter.availability()
        observations = adapter.fetch()
        newest = observations[0] if observations else None
        provider = fabric.get(adapter.provider_id)
        product = fabric.product(getattr(adapter, "product_id", "")) if provider else None
        if product is None and provider is not None and provider.products:
            product = provider.products[0]
        signals.append({
            "capability": adapter.capability,
            "providerId": adapter.provider_id,
            "providerName": provider.name if provider else adapter.provider_id,
            "productId": product.product_id if product else None,
            "productName": product.name if product else None,
            "availability": availability.to_dict(),
            "freshness": newest.freshness() if newest else "UNAVAILABLE",
            "ageSeconds": None if newest is None else round(newest.age_seconds(), 1),
            "quality": None if newest is None else newest.quality.to_dict(),
            "coverage": product.coverage if product else adapter.coverage,
            "licenceMode": active,
            # Four-state, so the surface can say REQUIRES_REVIEW rather than
            # collapsing "we do not know" into yes or no.
            "commercialUse": product.policy.commercial_use if product else None,
            "governmentUse": product.policy.government_use if product else None,
            "attributionRequired": (
                product.policy.attribution_required if product else None
            ),
            "termsUrl": product.policy.evidence.terms_url if product else None,
            "termsReviewedAt": product.policy.evidence.reviewed_at if product else None,
        })

    return {
        "mode": active,
        "traffic": ais_mode(licence_mode=active),
        "signals": sorted(signals, key=lambda row: row["capability"]),
        # Capabilities the registry knows about that nothing reads yet, so the
        # surface distinguishes "stale" from "never wired".
        "unwired": [
            capability
            for capability in ("marine", "disaster", "seismic", "fire",
                               "vessel_registry", "port_stats", "geography")
            if not any(s["capability"] == capability for s in signals)
        ],
    }


@router.get("/world/ais/tracks")
def ais_tracks(
    mode: Optional[str] = Query(None),
    history: int = Query(30, ge=0, le=240),
    limit: int = Query(2000, ge=1, le=20000),
) -> Dict[str, Any]:
    """Observed vessel tracks, and the source state that says what they are.

    Only what a transponder said reaches this payload. A track has an IMO or
    a name only if a static-data message carried it; a position report has
    its MMSI and nothing else, and the surface drawing it must say so. The
    ``traffic`` block is the same state machine ``/fabric/health`` reports, so
    the chart and the trust surface cannot disagree about whether the
    positions are live, stale or absent.

    When the source is not observed AIS the list is empty -- the replay is
    served elsewhere under its own name and is never returned here.
    """
    from src.portwatch_os.fabric import COMMERCIAL, MODES as FABRIC_MODES
    from src.portwatch_os.fabric import AIS_STALE, LIVE_AIS, ais_mode
    from src.portwatch_os.fabric.ais.client import get_client

    active = (mode or COMMERCIAL).strip().upper()
    if active not in FABRIC_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"mode must be one of: {', '.join(FABRIC_MODES)}.",
        )
    now = datetime.now(timezone.utc)
    traffic = ais_mode(licence_mode=active, now=now)
    tracks: List[Dict[str, Any]] = []
    if traffic["mode"] in (LIVE_AIS, AIS_STALE):
        store = get_client().store
        ordered = sorted(
            (t for t in store.tracks() if t.latest is not None),
            key=lambda t: t.latest.source_timestamp,
            reverse=True,
        )
        tracks = [t.to_dict(now=now, history=history) for t in ordered[:limit]]
    return {
        "generatedAt": now.isoformat(),
        "traffic": traffic,
        "count": len(tracks),
        "tracks": tracks,
    }


# --------------------------------------------------------------------------
# entities
# --------------------------------------------------------------------------


@router.get("/world/entities")
def world_entities(
    limit: int = Query(200, ge=1, le=5000),
    observed_only: bool = Query(False, alias="observedOnly"),
) -> Dict[str, Any]:
    """Every canonical vessel the fusion engine currently holds.

    Summaries only; the full record with every assertion is the detail route.
    Candidates and conflicts are counted here so a reviewer can find the hulls
    that need a person without opening each one.
    """
    from src.portwatch_os.fusion.engine import get_engine

    engine = get_engine()
    hulls = engine.vessels()
    if observed_only:
        hulls = [h for h in hulls if h.observed]
    hulls.sort(key=lambda h: (h.last_observed_at or h.created_at), reverse=True)
    return {
        "stats": engine.stats(),
        "count": len(hulls),
        "vessels": [h.to_dict() for h in hulls[:limit]],
    }


@router.get("/world/entities/lookup")
def world_entity_lookup(
    mmsi: Optional[str] = Query(None),
    imo: Optional[str] = Query(None),
    fleet_id: Optional[str] = Query(None, alias="fleetId"),
) -> Dict[str, Any]:
    """Which hull a key currently refers to, by an active strong link only.

    There is deliberately no ``name`` parameter: a name is not a key, and a
    lookup by name would be the merge-by-name this engine refuses.
    """
    from src.portwatch_os.fusion.engine import get_engine
    from src.portwatch_os.fusion.model import FLEET_ID, IMO, MMSI

    engine = get_engine()
    for kind, value in ((MMSI, mmsi), (IMO, imo), (FLEET_ID, fleet_id)):
        if value:
            hull = engine.lookup(kind, value)
            if hull is None:
                raise HTTPException(status_code=404, detail=f"no hull is linked to {kind} {value}")
            return hull.to_dict(include_assertions=True)
    raise HTTPException(status_code=400, detail="one of mmsi, imo or fleetId is required.")


@router.get("/world/entities/{canonical_id}")
def world_entity(canonical_id: str) -> Dict[str, Any]:
    """One hull with everything ever asserted about it, and every decision."""
    from src.portwatch_os.fusion.engine import get_engine

    body = get_engine().explain(canonical_id)
    if body is None:
        raise HTTPException(status_code=404, detail=f"no hull {canonical_id}")
    return body


# --------------------------------------------------------------------------
# the sea
# --------------------------------------------------------------------------


def _marine_gate(mode: Optional[str]):
    """The marine adapter for this view, or the availability that bars it."""
    from src.portwatch_os.fabric.marine import OpenMeteoMarineAdapter

    adapter = OpenMeteoMarineAdapter(licence_mode=_mode(mode))
    return adapter, adapter.availability()


@router.get("/world/marine")
def world_marine(
    at: Optional[str] = Query(None, description="ISO instant. Defaults to now."),
    mode: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """The sea at one instant: one cell per sample point, nearest forecast hour.

    What the WEATHER lens draws. Every cell carries when it is for and when
    it was fetched, and the block as a whole carries the product it came
    from, so the surface can say "Open-Meteo free tier, fetched 40 minutes
    ago, valid 13:00Z" rather than "weather".
    """
    moment = _at(at)
    adapter, availability = _marine_gate(mode)
    grid = adapter.service.grid(now=utc(), allow_fetch=False) if availability.ready else None
    lo, hi = grid.horizon if grid else (None, None)
    return {
        "at": moment.isoformat(),
        "availability": availability.to_dict(),
        "productId": adapter.product_id,
        "providerId": adapter.provider_id,
        "fetchedAt": None if grid is None or grid.fetched_at is None else grid.fetched_at.isoformat(),
        "ageSeconds": (
            None if grid is None or grid.fetched_at is None
            else round((utc() - grid.fetched_at).total_seconds(), 1)
        ),
        "horizon": [None if lo is None else lo.isoformat(), None if hi is None else hi.isoformat()],
        "withinHorizon": bool(grid and lo and hi and lo <= moment <= hi),
        "cells": [] if grid is None else [c.to_dict() for c in grid.at(moment)],
        "attribution": "Weather data by Open-Meteo.com (CC-BY 4.0)" if grid else None,
    }


@router.post("/world/route/exposure")
def route_exposure(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """A passage sampled against the sea it will run through.

    ``waypoints`` is a list of [lat, lon]; ``departsAt`` an ISO instant
    (default now); ``speedKn`` the planned speed. The answer is a profile
    with its coverage and confidence on it; an uncovered passage returns a
    profile that says so rather than a number.
    """
    from src.portwatch_os.world.route_exposure import sample_route

    raw = payload.get("waypoints") or []
    try:
        waypoints = [(float(p[0]), float(p[1])) for p in raw]
    except (TypeError, ValueError, IndexError):
        raise HTTPException(status_code=400, detail="waypoints must be a list of [lat, lon] pairs.")
    if len(waypoints) < 2:
        raise HTTPException(status_code=400, detail="at least two waypoints are required.")
    if any(abs(lat) > 90 or abs(lon) > 180 for lat, lon in waypoints):
        raise HTTPException(status_code=400, detail="a waypoint is out of range.")
    try:
        speed = float(payload.get("speedKn") or 12.0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="speedKn must be a number.")
    if not 0.5 <= speed <= 40.0:
        raise HTTPException(status_code=400, detail="speedKn must lie between 0.5 and 40.")
    departs = _at(payload.get("departsAt"))

    adapter, availability = _marine_gate(payload.get("mode"))
    grid = adapter.service.grid(now=utc(), allow_fetch=False) if availability.ready else None
    profile = sample_route(waypoints, grid=grid, departs_at=departs, speed_kn=speed)
    body = profile.to_dict(include_samples=bool(payload.get("includeSamples", True)))
    body["availability"] = availability.to_dict()
    body["productId"] = adapter.product_id
    return body


# --------------------------------------------------------------------------
# scenario branches
# --------------------------------------------------------------------------


def _observed_state(company_id: Optional[str], mode: Optional[str]):
    """The observed world, frozen now. What every branch forks from."""
    from src.portwatch_os.fabric import ais_mode
    from src.portwatch_os.world.branch import snapshot

    build, _events = _world_build(company_id, mode=mode)
    traffic = ais_mode(licence_mode=_mode(mode), now=utc())
    return build, snapshot(build, traffic_mode=traffic["mode"], at=utc())


@router.get("/world/observed")
def world_observed(
    company_id: Optional[str] = Query(None, alias="companyId"),
    mode: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """The observed world's identity: what any branch would fork from now."""
    from src.portwatch_os.world.branch import get_registry
    from src.portwatch_os.world.live import get_live_world

    build, state = _observed_state(company_id, mode)
    return {
        "state": state.summary(),
        "live": get_live_world().status(),
        "branches": [b.summary(current_revision=build.revision) for b in get_registry().all()],
    }


@router.post("/world/branches")
def create_branch(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Fork the observed world with assumptions applied.

    ``assumptions`` is a list of ``{kind, subject, value?, laneCode?, note?}``
    with kind one of ``close_chokepoint``, ``divert_vessel``, ``derate_port``.
    The observed world is copied, never edited; every assumed node and edge
    carries ``source: ASSUMPTION``.
    """
    from src.portwatch_os.world.branch import Assumption, BranchError, get_registry

    raw = payload.get("assumptions") or []
    if not isinstance(raw, list) or not raw:
        raise HTTPException(status_code=400, detail="assumptions must be a non-empty list.")
    try:
        assumptions = [Assumption.from_dict(item) for item in raw]
    except BranchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    build, state = _observed_state(payload.get("companyId"), payload.get("mode"))
    try:
        created = get_registry().create(state, assumptions, now=utc())
    except BranchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "branch": created.summary(current_revision=build.revision),
        "observed": state.summary(),
    }


@router.get("/world/branches/{branch_id}/cascades/{event_id}")
def branch_cascade(
    branch_id: str,
    event_id: str,
    at: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None, alias="companyId"),
    mode: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """One event's consequence on the branch beside its consequence as observed.

    ``event_id`` may be a register event or one of the branch's own seeds
    (``scenario:<branch>:<CHOKEPOINT>``). Observed and branched cascades are
    both computed on the branch's *parent* snapshot, so the comparison is
    between one world and the same world with the assumptions, not between
    two instants.
    """
    from src.portwatch_os.world.branch import compare, get_registry, propagate as run

    held = get_registry().get(branch_id)
    if held is None:
        raise HTTPException(status_code=404, detail=f"no branch {branch_id}")
    moment = _at(at)
    seed_key = key(EVENT, event_id)

    seeded = dict(held.seeds).get(seed_key)
    if seeded is None:
        build, events = _world_build(company_id, mode=mode)
        event = _event_or_404(events, event_id)
        seeded = seed_for(event)
        title = event.title
    else:
        title = held.graph.node(seed_key).label if held.graph.node(seed_key) else event_id

    observed_graph = held.parent.graph
    branched = run(held.graph, seed_key, seeded, at=moment) if held.graph.node(seed_key) else None
    observed = run(observed_graph, seed_key, seeded, at=moment) if observed_graph.node(seed_key) else None
    if branched is None:
        raise HTTPException(status_code=404, detail=f"{event_id} is not in the branch's world")

    from src.portwatch_os.world.live import get_live_world

    current = get_live_world()
    return {
        "branch": held.summary(current_revision=None),
        "eventId": event_id,
        "title": title,
        "at": moment.isoformat(),
        "assumed": seed_key in dict(held.seeds),
        "observed": None if observed is None else _cascade_payload(observed, observed_graph, include_steps=False),
        "branched": _cascade_payload(branched, held.graph, include_steps=True),
        "comparison": None if observed is None else compare(observed, branched),
        "live": current.status(),
    }
