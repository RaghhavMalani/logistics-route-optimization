"""Original screen contracts in a visitor-owned sandbox, never HTTP forwarding.

Only audited domain routes are mounted. The dependency supplies server-owned
demo scope and separate domain resources before the original endpoint runs.
Authentication/admin collection/private camera endpoints are never mounted.
"""
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.routing import APIRoute
from backend.app.identity import Identity, current_identity
from backend.app.routes.demo import token
from backend.app.services.demo_store import get_demo_store
from backend.app.services.demo_terminal import bind
from src.portwatch_os.sandbox import current_sandbox
import asyncio
import weakref

_mutation_locks = weakref.WeakValueDictionary()


async def sandbox(request: Request, credential=Depends(token)):
    store = get_demo_store()
    session, world = store.session(credential), store.read(credential)
    user = session["user"]
    if request.method == "POST":
        payload = await request.json()
        if isinstance(payload, dict):
            if user["role"] == "VESSEL_OPERATOR" and payload.get("vesselId") and payload["vesselId"] not in user["vesselIds"]:
                raise HTTPException(403, "This bridge demo is assigned PWD-001")
            if user["role"] == "PORT_AUTHORITY" and payload.get("portCode") and payload["portCode"] != world["portCode"]:
                raise HTTPException(403, "This port demo is scoped to JNPA")
    scoped = bind(session, world, store)
    mutation_lock = None
    if request.method == "POST":
        key = str(scoped.root)
        mutation_lock = _mutation_locks.get(key)
        if mutation_lock is None:
            mutation_lock = asyncio.Lock()
            _mutation_locks[key] = mutation_lock
        await mutation_lock.acquire()
        scoped.world = store.read(credential)
    scoped.save_world = lambda change: store.update(credential, change)
    who = Identity(role=user["role"], actor=user["id"], port_code=user["portCode"],
                   organisation=user["organisation"], vessel_ids=tuple(user["vesselIds"]), verified=False)
    headers = [(k, v) for k, v in request.scope["headers"] if not k.lower().startswith(b"x-portwatch-")]
    for key, value in {"role": who.role, "actor": who.actor, "port": who.port_code,
                       "org": who.organisation, "vessels": ",".join(who.vessel_ids)}.items():
        if value:
            headers.append((f"x-portwatch-{key}".encode(), value.encode("ascii", "ignore")))
    request.scope["headers"] = headers
    if hasattr(request, "_headers"):
        del request._headers
    scope_token, identity_token = current_sandbox.set(scoped), current_identity.set(who)
    try:
        yield
    finally:
        if mutation_lock is not None: mutation_lock.release()
        current_identity.reset(identity_token)
        current_sandbox.reset(scope_token)


router = APIRouter(prefix="/demo/terminal", dependencies=[Depends(sandbox)])


def install():
    from backend.app.routes import (advisories, company, decisions, finance, fleet,
        global_eye, health, learning, lenses, missions, model, news, port_twin,
        ports, provenance, sar, scenarios, weather, weather_verification, shipping_intelligence, operational_notices, world, agents, admin, intelligence, capabilities, current_inputs)
    # Static /weather/feedback must precede the original /weather/{port_code}.
    read_modules = (current_inputs, shipping_intelligence, operational_notices, weather_verification, intelligence, capabilities, company, fleet, global_eye, learning, lenses, model, news,
                    port_twin, ports, sar, weather, health, provenance)
    workflow_modules = (advisories, decisions, missions, scenarios, agents)
    extras = {"/finance/basis", "/finance/tariffs", "/finance/assumptions",
              "/world/clock", "/world/state", "/world/cascades", "/world/cascades/{event_id}",
              "/world/cascade/simulate", "/world/branches", "/world/branches/{branch_id}/cascades/{event_id}",
              "/attention", "/attention/{attention_id:path}", "/fabric/health", "/fabric/providers",
              "/fabric/resolve/{capability}", "/world/ais/tracks", "/world/marine", "/world/route/exposure",
              "/admin/freshness", "/agents", "/agents/tools", "/agents/intents"}
    own_mutations = {"/world/clock", "/world/branches", "/world/cascade/simulate"}
    for module in (*read_modules, *workflow_modules, finance, world, admin):
        for route in module.router.routes:
            if not isinstance(route, APIRoute):
                continue
            permitted = (module in read_modules and route.methods == {"GET"}) or module in workflow_modules or (module in (current_inputs,shipping_intelligence,operational_notices) and route.methods == {"POST"}) or (route.path in extras and route.methods == {"GET"}) or (route.path in own_mutations and route.methods == {"POST"})
            if permitted:
                router.add_api_route(route.path, route.endpoint, methods=list(route.methods),
                                     name="demo_terminal_" + route.name, response_model=route.response_model)


install()
