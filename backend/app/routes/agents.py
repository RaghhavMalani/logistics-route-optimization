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

from fastapi import APIRouter, Body, HTTPException, Query

from src.portwatch_os.agents.orchestrator import INTENTS, AgentRun, CommandAgent
from src.portwatch_os.agents.portwatch_tools import build_registry
from src.portwatch_os.agents.tools import ACCESS_LEVELS, EXECUTE, PROPOSE
from src.portwatch_os.roles import NATIONAL_ADMIN

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


@router.post("/agents/run")
def run_agent(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Run the orchestrator against a question."""
    question = str(payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="A question is required.")

    run = command_agent().run(
        question,
        role=str(payload.get("role") or NATIONAL_ADMIN),
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
