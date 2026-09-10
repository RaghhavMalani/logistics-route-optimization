"""Agent runs, the tool catalogue and the MCP boundary, over HTTP.

The Agent surface in the terminal talks to this. Runs are kept in a bounded
in-process register so a trace can be reopened without re-running the chain;
they are not persisted, because an agent run is a view over state that *is*
persisted (the ledger, the advisory register) rather than a record in its own
right.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query

from src.portwatch_os.agents.orchestrator import INTENTS, AgentRun, CommandAgent
from src.portwatch_os.agents.portwatch_tools import build_registry
from src.portwatch_os.agents.tools import ACCESS_LEVELS, EXECUTE, PROPOSE, ToolScope
from src.portwatch_os.roles import NATIONAL_ADMIN, WORKSPACE_ROLES, is_workspace_role

router = APIRouter()

#: How many runs to keep. Enough that a demo can reopen anything on screen.
MAX_RUNS = 64

_RUNS: "OrderedDict[str, AgentRun]" = OrderedDict()
_LOCK = threading.Lock()
_COMMAND: Optional[CommandAgent] = None


def command_agent() -> CommandAgent:
    """The process-wide orchestrator.

    Built once because constructing it instantiates nine specialists and
    validates every declared tool against the registry -- work worth doing at
    startup and not on every request.
    """
    global _COMMAND
    if _COMMAND is None:
        _COMMAND = CommandAgent(build_registry())
    return _COMMAND


@router.get("/agents")
def describe_agents() -> Dict[str, Any]:
    """The agent architecture: intents, specialists, the Critic and the boundary."""
    return command_agent().describe()


@router.get("/agents/tools")
def list_tools(
    max_access: str = Query(PROPOSE, description="Ceiling to list at."),
) -> Dict[str, Any]:
    if max_access not in ACCESS_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown access level '{max_access}'. Known: {', '.join(ACCESS_LEVELS)}",
        )
    registry = command_agent().registry
    return {
        "ceiling": max_access,
        "tools": registry.schema(max_access=max_access),
        "byAccess": {
            level: [s.name for s in registry.specs(access=level)]
            for level in ACCESS_LEVELS
        },
        "boundary": {
            "read": "Observe. No side effects.",
            "simulate": "Run a model or a what-if. No side effects.",
            "propose": "Create a draft for a human to review.",
            "execute": (
                "Act. Requires an approval context that only an authenticated human "
                "session can build, so no agent and no model client can reach one."
            ),
        },
    }


def scope_from_request(
    actor: Optional[str],
    role: Optional[str],
    port_code: Optional[str],
    organisation: Optional[str],
    vessel_ids: Optional[str],
) -> Optional[ToolScope]:
    """The authenticated identity a run answers for, from the identity headers.

    Deliberately *not* read from the request body. A body field naming the role
    would let any caller ask for the national view, which is the same
    impersonation the advisory and policy endpoints refuse. Absent headers give
    no scope at all, and a scoped tool then declines rather than falling back to
    national visibility.
    """
    if not actor or not role:
        return None
    normalised = role.strip().upper()
    if not is_workspace_role(normalised):
        raise HTTPException(
            status_code=403,
            detail=(
                f"'{role}' is not a workspace role. Send X-PortWatch-Role with one "
                f"of: {', '.join(WORKSPACE_ROLES)}."
            ),
        )
    return ToolScope(
        actor=actor,
        role=normalised,
        port_code=port_code,
        organisation=organisation,
        vessel_ids=tuple(
            v.strip() for v in (vessel_ids or "").split(",") if v.strip()
        ),
        elevation_reason=(
            "national command holds network-wide visibility by role"
            if normalised == NATIONAL_ADMIN else None
        ),
    )


@router.post("/agents/run")
def run_agent(
    payload: Dict[str, Any] = Body(...),
    actor: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role_header: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
) -> Dict[str, Any]:
    """Run the orchestrator against a question.

    The body still chooses which workspace the answer is *phrased* for. What it
    cannot do is widen what the run may read: that follows the identity headers,
    and a run with no identity reads nothing that belongs to a port or a carrier.
    """
    question = str(payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="A question is required.")

    scope = scope_from_request(
        actor, role_header, header_port, organisation, vessel_ids,
    )

    run = command_agent().run(
        question,
        role=str(payload.get("role") or (scope.role if scope else NATIONAL_ADMIN)),
        scope=scope,
        port_code=payload.get("portCode"),
        vessel_id=payload.get("vesselId"),
        company_id=payload.get("companyId"),
        event_id=payload.get("eventId"),
        horizon_hours=float(payload.get("horizonHours") or 72.0),
        context=dict(payload.get("context") or {}),
    )

    with _LOCK:
        _RUNS[run.run_id] = run
        while len(_RUNS) > MAX_RUNS:
            _RUNS.popitem(last=False)

    return run.to_dict(include_results=bool(payload.get("includeResults")))


@router.get("/agents/runs")
def list_runs(limit: int = Query(20, ge=1, le=64)) -> Dict[str, Any]:
    with _LOCK:
        runs = list(_RUNS.values())[-limit:]
    return {
        "runs": [
            {
                "runId": r.run_id, "question": r.question, "intent": r.intent,
                "intentLabel": r.intent_label, "outcome": r.outcome,
                "confidence": r.confidence, "startedAt": r.started_at,
                "durationMs": round(r.duration_ms, 1),
                "agents": [a.agent for a in r.results],
                "criticVerdict": r.verdict.verdict if r.verdict else None,
            }
            for r in reversed(runs)
        ],
        "total": len(_RUNS),
    }


@router.get("/agents/runs/{run_id}")
def get_run(run_id: str, include_results: bool = False) -> Dict[str, Any]:
    with _LOCK:
        run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Run {run_id} is not in the register. Runs are kept in process and "
                f"the most recent {MAX_RUNS} are retained."
            ),
        )
    return run.to_dict(include_results=include_results)


@router.get("/agents/intents")
def list_intents() -> Dict[str, Any]:
    return {
        "intents": [
            {
                "key": i.key, "label": i.label, "agents": list(i.agents),
                "highImpact": i.high_impact, "description": i.description,
                "examples": list(i.keywords[:4]),
            }
            for i in INTENTS
        ]
    }
