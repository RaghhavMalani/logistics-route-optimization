"""Scenario branching: an observed world that cannot be edited, and branches
that can.

The observed world is what the fabric delivered: the event register, the
fleet, the transponders' claims, the sea. It is the thing every other layer
is accountable to, and the moment a "what if" is allowed to edit it, nobody
can say afterwards which numbers were observed and which were assumed. So
the observed state is frozen at the instant it is snapshotted, and a branch
is a *copy* with assumptions applied -- each assumption a node or an edge
carrying ``source: ASSUMPTION`` so that a cascade run on the branch can be
read step by step and every assumed link is visible as one.

Three assumptions exist in V1, chosen because each is a question an operator
actually asks:

*   **close a chokepoint** -- "what if Bab-el-Mandeb closes tonight?" -- a
    synthetic event at the strait, with a stated severity.
*   **divert a hull** -- "what if Konkan Pioneer takes the Cape?" -- the hull's
    lane edge is replaced by one to the alternative routing.
*   **derate a port** -- "what if Nhava Sheva loses a third of its capacity?"
    -- the port's capacity attribute is scaled.

A branch remembers the revision it forked from. When the observed world moves
on, the branch says so rather than silently comparing against a world that
no longer exists.

V2 adds the assumptions a *decision* needs -- retime a hull for slow steaming
or a faster passage, rebind it to another destination, detach it from its
lane while it holds -- and gives every branch the fields a decision option is
accountable for: the actions applied, the derived state, the cascade
consequences, the metrics, the constraint results and the provenance of each.
The observed world is still never edited; a branch is still a copy.
"""

from __future__ import annotations

import copy
import itertools
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.portwatch_os.global_eye.exposure import TRADE_LANES
from src.portwatch_os.world.cascade import Cascade, propagate
from src.portwatch_os.world.graph import (
    BOUND_FOR,
    CHOKEPOINT,
    EVENT,
    LANE,
    PORT,
    SAILS,
    THREATENS,
    VESSEL,
    Edge,
    Node,
    WorldGraph,
    key,
)
from src.portwatch_os.world.quantity import Quantity, RISK, window
from src.portwatch_os.clock import get_clock, world_now

SOURCE_ASSUMPTION = "ASSUMPTION"

CLOSE_CHOKEPOINT = "close_chokepoint"
DIVERT_VESSEL = "divert_vessel"
DERATE_PORT = "derate_port"
#: V2: a hull runs at another speed on the same routing (value = knots).
RETIME_VESSEL = "retime_vessel"
#: V2: a hull lands at another port the lane serves (target = locode).
REBIND_DESTINATION = "rebind_destination"
#: V2: a hull leaves its lane without taking the alternative -- it holds
#: clear of the threatened water. The cascade stops reaching it; the delay it
#: takes is carried by the decision branch that applied this.
DETACH_VESSEL = "detach_vessel"
ASSUMPTION_KINDS: Tuple[str, ...] = (
    CLOSE_CHOKEPOINT, DIVERT_VESSEL, DERATE_PORT, RETIME_VESSEL, REBIND_DESTINATION,
    DETACH_VESSEL,
)


class BranchError(ValueError):
    """An assumption that cannot be applied to this world, and why."""


@dataclass(frozen=True)
class Assumption:
    kind: str
    subject: str
    #: Severity for a closure (0..1), a lane code for a diversion, a factor
    #: for a derating (0..1 of remaining capacity).
    value: Optional[float] = None
    lane_code: Optional[str] = None
    note: str = ""
    #: A port code for a rebinding; unused by the other kinds.
    target: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "subject": self.subject, "value": self.value,
                "laneCode": self.lane_code, "target": self.target, "note": self.note,
                "source": SOURCE_ASSUMPTION}

    @classmethod
    def from_dict(cls, body: Dict[str, Any]) -> "Assumption":
        kind = str(body.get("kind") or "")
        if kind not in ASSUMPTION_KINDS:
            raise BranchError(f"{kind!r} is not an assumption this world can hold; one of {', '.join(ASSUMPTION_KINDS)}")
        subject = str(body.get("subject") or "").strip()
        if not subject:
            raise BranchError("an assumption needs a subject")
        value = body.get("value")
        try:
            value = None if value is None else float(value)
        except (TypeError, ValueError):
            raise BranchError("value must be a number") from None
        return cls(kind=kind, subject=subject, value=value,
                   lane_code=body.get("laneCode"), note=str(body.get("note") or ""),
                   target=(str(body["target"]).upper() if body.get("target") else None))


@dataclass(frozen=True)
class ObservedWorldState:
    """The world as observed at one instant. Immutable; branches copy it."""

    state_id: str
    revision: Any
    at: datetime
    graph: WorldGraph
    traffic_mode: str

    def summary(self) -> Dict[str, Any]:
        return {
            "stateId": self.state_id,
            "at": self.at.isoformat(),
            "trafficMode": self.traffic_mode,
            "nodes": len(self.graph),
            "observedVessels": sum(
                1 for n in self.graph.nodes(kind=VESSEL) if n.attrs.get("source") == "OBSERVED_AIS"
            ),
            "revision": {
                "mode": self.revision.mode,
                "eventsStamp": _short(self.revision.events_stamp),
                "fleetStamp": _short(self.revision.fleet_stamp),
                "observedGeneration": self.revision.observed_generation,
                "fingerprint": self.revision.fingerprint,
            },
        }


def _short(text: str) -> str:
    return text if len(text) <= 48 else f"{text[:45]}..."


@dataclass
class ScenarioBranch:
    branch_id: str
    parent: ObservedWorldState
    assumptions: List[Assumption]
    graph: WorldGraph
    created_at: datetime
    #: Seeds the assumptions introduced, so the branch can be cascaded from them.
    seeds: List[Tuple[str, Quantity]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    #: V2. The decision actions this branch realises, in the action
    #: catalogue's vocabulary; the state derived from applying them; what the
    #: world engine concluded on the branch; the metrics read off it; the
    #: constraints checked; and where every input came from.
    actions: List[Dict[str, Any]] = field(default_factory=list)
    derived: Dict[str, Any] = field(default_factory=dict)
    consequences: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    constraint_results: List[Dict[str, Any]] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def summary(self, *, current_revision: Any = None) -> Dict[str, Any]:
        return {
            "branchId": self.branch_id,
            "parentStateId": self.parent.state_id,
            "parentRevision": {
                "mode": self.parent.revision.mode,
                "eventsStamp": _short(self.parent.revision.events_stamp),
                "fleetStamp": _short(self.parent.revision.fleet_stamp),
                "observedGeneration": self.parent.revision.observed_generation,
            },
            "createdAt": self.created_at.isoformat(),
            "assumptions": [a.to_dict() for a in self.assumptions],
            "actions": list(self.actions),
            "derived": dict(self.derived),
            "consequences": list(self.consequences),
            "metrics": dict(self.metrics),
            "constraintResults": list(self.constraint_results),
            "provenance": dict(self.provenance),
            "seeds": [k for k, _ in self.seeds],
            "notes": list(self.notes),
            # True when the observed world has moved on since the fork. The
            # branch still compares against what it forked from; it says so.
            "observedWorldMovedOn": (
                current_revision is not None and current_revision != self.parent.revision
            ),
        }


def snapshot(build: Any, *, traffic_mode: str, at: Optional[datetime] = None) -> ObservedWorldState:
    """Freeze a live build. The graph is deep-copied so nothing shares it."""
    moment = at or world_now()
    return ObservedWorldState(
        state_id=f"obs-{int(moment.timestamp())}-{build.revision.observed_generation}",
        revision=build.revision,
        at=moment,
        graph=copy.deepcopy(build.graph),
        traffic_mode=traffic_mode,
    )


# --------------------------------------------------------------------------
# applying assumptions
# --------------------------------------------------------------------------


def _copy_graph(graph: WorldGraph) -> WorldGraph:
    out = WorldGraph()
    for node in graph.nodes():
        out.add_node(node)
    for edge in graph.edges():
        out.add_edge(edge)
    return out


def _close_chokepoint(graph: WorldGraph, branch_id: str, assumption: Assumption, now: datetime) -> Tuple[str, Quantity, str]:
    code = assumption.subject.upper()
    chokepoint_key = key(CHOKEPOINT, code)
    if graph.node(chokepoint_key) is None:
        raise BranchError(f"{code} is not a chokepoint in this world")
    severity = 1.0 if assumption.value is None else max(0.0, min(1.0, assumption.value))
    event_key = key(EVENT, f"scenario:{branch_id}:{code}")
    graph.add_node(Node(
        key=event_key, kind=EVENT, label=f"Assumed closure of {code}",
        interval=window(now, 72.0),
        attrs={"category": "scenario", "severity": severity, "confidence": 1.0,
               "source": SOURCE_ASSUMPTION, "assumption": assumption.to_dict(), "chokepoints": [code]},
    ))
    graph.add_edge(Edge(src=event_key, dst=chokepoint_key, kind=THREATENS, weight=1.0,
                        source=SOURCE_ASSUMPTION))
    seed = Quantity(value=severity, unit=RISK, confidence=1.0,
                    attrs={"event_id": f"scenario:{branch_id}:{code}", "category": "scenario",
                           "assumed": True})
    return event_key, seed, f"assumed {code} closed at severity {severity:.2f}"


def _divert_vessel(graph: WorldGraph, assumption: Assumption) -> str:
    vessel_key = key(VESSEL, assumption.subject)
    node = graph.node(vessel_key)
    if node is None:
        raise BranchError(f"{assumption.subject} is not a vessel in this world")
    current_lane = node.attrs.get("lane_code")
    current = TRADE_LANES.get(current_lane or "")
    target_code = assumption.lane_code
    if target_code is None:
        # No lane named: the assumption is "takes the alternative routing",
        # which means clear of the lane's chokepoints. Modelled as leaving the
        # lane; the detour it costs is the lane's own figure.
        if current is None:
            raise BranchError(f"{assumption.subject} is on no modelled lane; name a lane to divert to")
        if current.alternative is None:
            raise BranchError(f"{current.name} has no alternative routing to divert onto")
    elif target_code not in TRADE_LANES:
        raise BranchError(f"{target_code} is not a lane in this world")

    # Replace the lane relation on this hull; the copied graph is ours.
    removed = graph.remove_edges(kind=SAILS, dst=vessel_key)

    attrs = {**node.attrs, "assumption": assumption.to_dict(), "diverted_from": current_lane}
    if target_code:
        attrs["lane_code"] = target_code
        graph.add_edge(Edge(src=key(LANE, target_code), dst=vessel_key, kind=SAILS, weight=1.0,
                            attrs={"hours_to_chokepoint": {}}, source=SOURCE_ASSUMPTION))
    else:
        attrs["lane_code"] = None
        attrs["detour_hours"] = (current.detour_nm or 0.0) / max(1.0, float(node.attrs.get("service_speed_kn") or 12.0))
    graph.add_node(Node(key=vessel_key, kind=VESSEL, label=node.label, interval=node.interval, attrs=attrs))
    return (
        f"assumed {node.label} diverted "
        + (f"onto {target_code}" if target_code else f"off {current_lane} onto its alternative routing")
        + f"; {removed} lane link(s) replaced"
    )


def _retime_vessel(graph: WorldGraph, assumption: Assumption) -> str:
    """The hull runs at ``value`` knots: its timing to every strait rescales.

    Distance is what the hull's declared timing encodes -- hours at the
    declared speed -- so the new timing is that distance over the new speed.
    The detour it would take rescales the same way.
    """
    vessel_key = key(VESSEL, assumption.subject)
    node = graph.node(vessel_key)
    if node is None:
        raise BranchError(f"{assumption.subject} is not a vessel in this world")
    if assumption.value is None or assumption.value <= 0:
        raise BranchError("a retiming needs a speed in knots")
    old_speed = max(1.0, float(node.attrs.get("service_speed_kn") or 12.0))
    new_speed = float(assumption.value)
    factor = old_speed / new_speed
    replaced = 0
    for edge in list(graph.in_edges(vessel_key, kind=SAILS)):
        timings = {code: (h * factor if h is not None else None)
                   for code, h in (edge.attrs.get("hours_to_chokepoint") or {}).items()}
        graph.remove_edges(kind=SAILS, src=edge.src, dst=vessel_key)
        graph.add_edge(Edge(src=edge.src, dst=vessel_key, kind=SAILS, weight=edge.weight,
                            interval=edge.interval, attrs={**edge.attrs, "hours_to_chokepoint": timings},
                            source=SOURCE_ASSUMPTION))
        replaced += 1
    detour_nm = node.attrs.get("detour_nm")
    attrs = {**node.attrs, "assumption": assumption.to_dict(), "service_speed_kn": new_speed,
             "service_speed_observed_kn": old_speed}
    if detour_nm is not None:
        attrs["detour_hours"] = float(detour_nm) / new_speed
    graph.add_node(Node(key=vessel_key, kind=VESSEL, label=node.label, interval=node.interval, attrs=attrs))
    return f"assumed {node.label} at {new_speed:.1f} kn (was {old_speed:.1f}); {replaced} lane link(s) retimed"


def _rebind_destination(graph: WorldGraph, assumption: Assumption) -> str:
    """The hull lands at another port the world holds."""
    vessel_key = key(VESSEL, assumption.subject)
    node = graph.node(vessel_key)
    if node is None:
        raise BranchError(f"{assumption.subject} is not a vessel in this world")
    if not assumption.target:
        raise BranchError("a rebinding needs a target port")
    port_key = key(PORT, assumption.target.upper())
    if graph.node(port_key) is None:
        raise BranchError(f"{assumption.target} is not a port in this world")
    previous = node.attrs.get("destination_port")
    removed = graph.remove_edges(kind=BOUND_FOR, src=vessel_key)
    graph.add_edge(Edge(src=vessel_key, dst=port_key, kind=BOUND_FOR, weight=1.0,
                        attrs={"eta": None}, source=SOURCE_ASSUMPTION))
    attrs = {**node.attrs, "assumption": assumption.to_dict(),
             "destination_port": assumption.target.upper(), "rebound_from": previous}
    graph.add_node(Node(key=vessel_key, kind=VESSEL, label=node.label, interval=node.interval, attrs=attrs))
    return f"assumed {node.label} bound for {assumption.target.upper()} (was {previous}); {removed} port link(s) replaced"


def _detach_vessel(graph: WorldGraph, assumption: Assumption) -> str:
    """The hull holds clear of its lane: no exposure reaches it while it waits."""
    vessel_key = key(VESSEL, assumption.subject)
    node = graph.node(vessel_key)
    if node is None:
        raise BranchError(f"{assumption.subject} is not a vessel in this world")
    removed = graph.remove_edges(kind=SAILS, dst=vessel_key)
    attrs = {**node.attrs, "assumption": assumption.to_dict(), "holding": True,
             "held_from_lane": node.attrs.get("lane_code")}
    graph.add_node(Node(key=vessel_key, kind=VESSEL, label=node.label, interval=node.interval, attrs=attrs))
    return f"assumed {node.label} holding clear of its lane; {removed} lane link(s) removed"


def _derate_port(graph: WorldGraph, assumption: Assumption) -> str:
    port_key = key(PORT, assumption.subject.upper())
    node = graph.node(port_key)
    if node is None:
        raise BranchError(f"{assumption.subject} is not a port in this world")
    factor = 1.0 if assumption.value is None else max(0.0, min(1.0, assumption.value))
    capacity = node.attrs.get("capacity") or node.attrs.get("capacity_index")
    attrs = {**node.attrs, "assumption": assumption.to_dict(), "capacity_factor": factor}
    if isinstance(capacity, (int, float)):
        attrs["capacity"] = float(capacity) * factor
        attrs["capacity_observed"] = capacity
    graph.add_node(Node(key=port_key, kind=PORT, label=node.label, interval=node.interval, attrs=attrs))
    return f"assumed {node.label} at {factor:.0%} of its capacity"


def branch(
    state: ObservedWorldState,
    assumptions: List[Assumption],
    *,
    branch_id: str,
    now: Optional[datetime] = None,
) -> ScenarioBranch:
    """A copy of the observed world with the assumptions applied, in order."""
    moment = now or world_now()
    with get_clock().pin_scenario(moment, scenario_id=branch_id, parentStateId=state.state_id):
        return _branch(state, assumptions, branch_id=branch_id, moment=moment)


def _branch(
    state: ObservedWorldState,
    assumptions: List[Assumption],
    *,
    branch_id: str,
    moment: datetime,
) -> ScenarioBranch:
    graph = _copy_graph(state.graph)
    result = ScenarioBranch(branch_id=branch_id, parent=state, assumptions=list(assumptions),
                            graph=graph, created_at=moment)
    for assumption in assumptions:
        if assumption.kind == CLOSE_CHOKEPOINT:
            seed_key, seed, note = _close_chokepoint(graph, branch_id, assumption, moment)
            result.seeds.append((seed_key, seed))
        elif assumption.kind == DIVERT_VESSEL:
            note = _divert_vessel(graph, assumption)
        elif assumption.kind == DERATE_PORT:
            note = _derate_port(graph, assumption)
        elif assumption.kind == RETIME_VESSEL:
            note = _retime_vessel(graph, assumption)
        elif assumption.kind == REBIND_DESTINATION:
            note = _rebind_destination(graph, assumption)
        elif assumption.kind == DETACH_VESSEL:
            note = _detach_vessel(graph, assumption)
        else:  # pragma: no cover - guarded by Assumption.from_dict
            raise BranchError(f"unknown assumption {assumption.kind}")
        result.notes.append(note)
    return result


# --------------------------------------------------------------------------
# comparing
# --------------------------------------------------------------------------


def compare(observed: Cascade, branched: Cascade) -> Dict[str, Any]:
    """What the branch changed, per unit and per reached subject."""
    units = ("risk", "vessels", "hours", "ratio", "inr")
    totals: Dict[str, Any] = {}
    for unit in units:
        a = observed.total(unit)
        b = branched.total(unit)
        if a is None and b is None:
            continue
        totals[unit] = {
            "observed": None if a is None else a.to_dict(),
            "branch": None if b is None else b.to_dict(),
            # A side with no total reached nothing in that unit: zero, not
            # unknown, because the cascade did run and found none.
            "delta": round((0.0 if b is None else b.value) - (0.0 if a is None else a.value), 4),
        }
    before = set(observed.reached)
    after = set(branched.reached)
    return {
        "totals": totals,
        "reachedObserved": len(before),
        "reachedBranch": len(after),
        "newlyReached": sorted(after - before),
        "noLongerReached": sorted(before - after),
    }


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------


class BranchRegistry:
    """The branches this process holds. Bounded; oldest out first."""

    def __init__(self, *, capacity: int = 32) -> None:
        self._branches: Dict[str, ScenarioBranch] = {}
        self._order: List[str] = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self.capacity = capacity

    def create(self, state: ObservedWorldState, assumptions: List[Assumption], *, now: Optional[datetime] = None) -> ScenarioBranch:
        with self._lock:
            branch_id = f"br-{next(self._ids):04d}"
            created = branch(state, assumptions, branch_id=branch_id, now=now)
            self._branches[branch_id] = created
            self._order.append(branch_id)
            while len(self._order) > self.capacity:
                gone = self._order.pop(0)
                self._branches.pop(gone, None)
            return created

    def get(self, branch_id: str) -> Optional[ScenarioBranch]:
        with self._lock:
            return self._branches.get(branch_id)

    def all(self) -> List[ScenarioBranch]:
        with self._lock:
            return [self._branches[i] for i in self._order if i in self._branches]

    def clear(self) -> None:
        with self._lock:
            self._branches.clear()
            self._order.clear()


_REGISTRY: Optional[BranchRegistry] = None
_REGISTRY_LOCK = threading.Lock()


def get_registry() -> BranchRegistry:
    global _REGISTRY
    with _REGISTRY_LOCK:
        if _REGISTRY is None:
            _REGISTRY = BranchRegistry()
        return _REGISTRY


def reset_registry() -> None:
    global _REGISTRY
    with _REGISTRY_LOCK:
        _REGISTRY = None


__all__ = [
    "ASSUMPTION_KINDS",
    "Assumption",
    "BranchError",
    "BranchRegistry",
    "CLOSE_CHOKEPOINT",
    "DERATE_PORT",
    "DETACH_VESSEL",
    "DIVERT_VESSEL",
    "REBIND_DESTINATION",
    "RETIME_VESSEL",
    "ObservedWorldState",
    "SOURCE_ASSUMPTION",
    "ScenarioBranch",
    "branch",
    "compare",
    "get_registry",
    "propagate",
    "reset_registry",
    "snapshot",
]
