"""Historical missions over HTTP: replay, decide, reveal, score.

One replay per mission per process. ``POST /missions/{id}/replay`` opens (or
reopens) it at the mission's start or at an offset; ``/decide`` runs the
decision engine on the world as it stood at the clock; ``/choose`` records
the operator's option; ``/reveal`` opens the hidden future and returns the
scorecard. Before the reveal the hidden observations and the outcome are
not served by any route, which is the property the whole surface exists for.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query

from backend.app.routes.decisions import _actor, _require_actor_name
from backend.app.routes.world import _at
from src.portwatch_os.decision.engine import get_engine
from src.portwatch_os.decision.model import DecisionError
from src.portwatch_os.missions import MISSIONS, FutureLeak, MissionError, MissionReplay, get_mission

router = APIRouter()

_REPLAYS: Dict[str, MissionReplay] = {}
_LOCK = threading.Lock()


def _mission_or_404(mission_id: str):
    try:
        return get_mission(mission_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _replay(mission_id: str, *, create: bool = False) -> MissionReplay:
    mission = _mission_or_404(mission_id)
    with _LOCK:
        held = _REPLAYS.get(mission_id)
        if held is None or create:
            held = MissionReplay(mission, get_engine())
            _REPLAYS[mission_id] = held
        return held


def reset_replays() -> None:
    with _LOCK:
        _REPLAYS.clear()


@router.get("/missions")
def list_missions() -> Dict[str, Any]:
    return {
        "missions": [
            {"missionId": m.mission_id, "name": m.name, "startTimestamp": m.start_timestamp,
             "chokepoint": m.chokepoint, "ports": list(m.ports), "subjectKind": m.subject_kind,
             "eventCategory": m.event_category, "description": m.description, "sources": len(m.sources),
             "observations": len(m.recording), "fleet": len(m.fleet),
             "evaluationWindowHours": m.evaluation_window_hours}
            for m in MISSIONS.values()
        ],
    }


_COMPARISON: Dict[str, Any] = {}


@router.get("/missions/compare")
def compare_missions_route() -> Dict[str, Any]:
    """Every mission replayed from its start, decided, revealed and scored in one table.

    Deterministic, so it is computed once per process on a private engine and
    served from memory after that; the operator's own replays are untouched.
    """
    from src.portwatch_os.decision.engine import DecisionEngine
    from src.portwatch_os.missions.compare import compare_missions

    with _LOCK:
        if "table" not in _COMPARISON:
            _COMPARISON.update(compare_missions(engine=DecisionEngine(capacity=64)))
        return _COMPARISON


@router.get("/missions/{mission_id}")
def get_mission_route(mission_id: str) -> Dict[str, Any]:
    """The mission at its replay clock. Hidden observations stay hidden."""
    replay = _replay(mission_id)
    return replay.to_dict()


@router.post("/missions/{mission_id}/replay")
def open_replay(mission_id: str, payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """Open a fresh replay at the start, or at ``offsetHours`` / ``clock``."""
    replay = _replay(mission_id, create=True)
    try:
        if payload.get("clock"):
            replay.seek(_at(str(payload["clock"])))
        elif payload.get("offsetHours") is not None:
            replay.seek(replay.mission.start + timedelta(hours=float(payload["offsetHours"])))
    except (MissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return replay.to_dict()


@router.post("/missions/{mission_id}/seek")
def seek_replay(mission_id: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    replay = _replay(mission_id)
    if replay.revealed:
        raise HTTPException(status_code=400, detail="the replay has been revealed; open a new one to seek")
    try:
        if payload.get("clock"):
            replay.seek(_at(str(payload["clock"])))
        else:
            replay.seek(replay.mission.start + timedelta(hours=float(payload.get("offsetHours") or 0.0)))
    except (MissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return replay.to_dict()


@router.get("/missions/{mission_id}/world")
def replay_world(mission_id: str) -> Dict[str, Any]:
    """The world graph as it stood at the clock: nodes, edges, the event as claimed."""
    replay = _replay(mission_id)
    state = replay.state()
    event = replay.event()
    return {
        "clock": replay.clock.isoformat(),
        "state": state.summary(),
        "event": event.to_dict(),
        "nodes": [n.to_dict() for n in state.graph.nodes()],
        "edges": [e.to_dict() for e in state.graph.edges()],
        "fleet": [v.to_dict() for v in replay.mission.fleet],
    }


@router.post("/missions/{mission_id}/decide")
def replay_decide(
    mission_id: str,
    payload: Dict[str, Any] = Body(...),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
) -> Dict[str, Any]:
    replay = _replay(mission_id)
    vessel_id = str(payload.get("vesselId") or "").strip()
    if not vessel_id:
        raise HTTPException(status_code=400, detail="vesselId is required")
    actor = _actor(role, organisation, header_port, vessel_ids)
    try:
        problem = replay.decide(vessel_id, actor)
    except (MissionError, DecisionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return problem.to_dict()


@router.post("/missions/{mission_id}/choose")
def replay_choose(
    mission_id: str,
    payload: Dict[str, Any] = Body(...),
    actor_name: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
) -> Dict[str, Any]:
    replay = _replay(mission_id)
    name = _require_actor_name(actor_name)
    try:
        problem = replay.choose(str(payload.get("vesselId") or ""), str(payload.get("optionId") or ""), actor=name)
    except (MissionError, DecisionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return problem.to_dict(include_options=False)


@router.post("/missions/{mission_id}/reveal")
def replay_reveal(
    mission_id: str,
    actor_name: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
) -> Dict[str, Any]:
    replay = _replay(mission_id)
    name = _require_actor_name(actor_name)
    return replay.reveal(actor=name)


@router.get("/missions/{mission_id}/outcome")
def replay_outcome(mission_id: str) -> Dict[str, Any]:
    replay = _replay(mission_id)
    try:
        return {"outcome": replay.outcome(), "hidden": replay.hidden()}
    except FutureLeak as exc:
        raise HTTPException(status_code=403, detail=str(exc))


__all__ = ["reset_replays", "router"]
