"""The port simulator.

A fixed-step discrete simulation over :class:`~src.portwatch_os.twin.state.PortState`.
It is the environment the optimisers are measured in, the environment the RL
policies train in, and the thing that produces the ``+2h / +6h / +12h / +24h``
states the 3D twin shows. One engine, so those three can never disagree.

**Determinism is a hard requirement, not a nice property.** Two policies can only
be compared if the same arrivals, the same weather and the same disruptions hit
both. Every stochastic draw therefore comes from a seeded generator carried in
the config, and :func:`simulate` with the same inputs produces byte-identical
metrics. The test suite asserts this.

**The simulator never relaxes a physical constraint.** A vessel too long or too
deep for a berth is not assigned to it, whatever a policy asks for. A policy that
proposes an infeasible action gets it rejected and recorded, which is exactly how
an unsafe learned policy fails its promotion gate instead of quietly producing
impossible schedules.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.twin.state import (
    ALONGSIDE,
    APPROACHING,
    DEPARTED,
    WAITING,
    Berth,
    PortState,
    VesselCall,
)

#: Hours per simulation step. Fifteen minutes is fine enough that a berthing is
#: not quantised into invisibility and coarse enough that a 72 h horizon is a
#: few hundred steps.
DEFAULT_STEP_HOURS = 0.25

#: Fixed time alongside on either side of the cargo work: pilotage, mooring,
#: lashing, documentation. Modelled, and stated as such.
BERTHING_OVERHEAD_HOURS = 1.6
UNBERTHING_OVERHEAD_HOURS = 1.0

#: Above this yard utilisation, shuffling to reach a box slows the quay. The
#: curve is the standard congestion argument -- as free slots vanish, the number
#: of re-handles per productive move rises -- and it is a model, not a
#: measurement from any specific terminal.
YARD_FRICTION_KNEE = 0.80

#: Wind at which quay cranes stop. Used with the weather impact index.
CRANE_STOP_IMPACT = 0.62


@dataclass
class SimulationConfig:
    """Everything that makes a run reproducible."""

    horizon_hours: float = 72.0
    step_hours: float = DEFAULT_STEP_HOURS
    seed: int = 20260909
    #: Weather impact index by hour. Constant at the state's value when absent.
    weather_by_hour: Optional[Dict[int, float]] = None
    #: Additional arrivals generated per hour beyond the declared calls.
    background_arrival_rate: float = 0.0
    #: Standard deviation of ETA error, hours. Zero makes arrivals exact.
    eta_noise_hours: float = 0.0
    #: Multiplier on the modelled crane rate. 1.0 uses the state's figures.
    productivity_factor: float = 1.0
    record_trace: bool = True

    def weather_at(self, hour: float, default: float) -> float:
        if not self.weather_by_hour:
            return default
        key = int(hour)
        if key in self.weather_by_hour:
            return float(self.weather_by_hour[key])
        keys = sorted(self.weather_by_hour)
        if not keys:
            return default
        if key < keys[0]:
            return float(self.weather_by_hour[keys[0]])
        if key > keys[-1]:
            return float(self.weather_by_hour[keys[-1]])
        return float(self.weather_by_hour[min(keys, key=lambda k: abs(k - key))])


@dataclass
class SimulationEvent:
    hour: float
    kind: str
    subject: str
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {"hour": round(self.hour, 3), "kind": self.kind,
                "subject": self.subject, "detail": self.detail}


@dataclass
class SimulationResult:
    """What a run produced. Everything a benchmark or a reward needs."""

    final_state: PortState
    metrics: Dict[str, Any]
    trace: List[SimulationEvent] = field(default_factory=list)
    #: Snapshots at the horizons the 3D twin offers.
    snapshots: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    #: Actions a policy proposed that the simulator refused, with the reason.
    rejected_actions: List[Dict[str, Any]] = field(default_factory=list)
    #: Hard constraints checked over the whole run.
    violations: List[Dict[str, Any]] = field(default_factory=list)
    steps: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metrics": self.metrics,
            "steps": self.steps,
            "snapshots": {str(k): v for k, v in sorted(self.snapshots.items())},
            "rejectedActions": self.rejected_actions,
            "violations": self.violations,
            "trace": [e.to_dict() for e in self.trace[:400]],
        }


# --------------------------------------------------------------------------
# work-rate model
# --------------------------------------------------------------------------


def yard_friction(utilisation: float) -> float:
    """Multiplier on crane productivity from yard congestion, in (0, 1].

    Below the knee the yard is not the constraint. Above it, every productive
    move needs re-handles, and the cost grows quadratically as free slots vanish.
    Bottoms out at 0.45 rather than 0: a full yard is very slow, not stopped.
    """
    if utilisation <= YARD_FRICTION_KNEE:
        return 1.0
    over = (utilisation - YARD_FRICTION_KNEE) / (1.0 - YARD_FRICTION_KNEE)
    return float(max(0.45, 1.0 - 0.55 * over * over))


def weather_derate(impact: float) -> float:
    """Multiplier on crane productivity from weather, in [0, 1].

    Zero above :data:`CRANE_STOP_IMPACT`: the cranes are down, not slow. This is
    what makes a weather-driven advisory worth issuing at all.
    """
    if impact >= CRANE_STOP_IMPACT:
        return 0.0
    return float(max(0.0, 1.0 - (impact / CRANE_STOP_IMPACT) ** 1.5))


def call_work_hours(
    state: PortState,
    call: VesselCall,
    crane_ids: Sequence[str],
    *,
    productivity_factor: float = 1.0,
) -> Optional[float]:
    """Hours of cargo work for a call under current conditions.

    ``None`` when the assigned cranes cannot work at all, which the caller must
    treat as "cannot start", not as "takes zero time".
    """
    rate = sum(
        c.moves_per_hour for c in state.cranes if c.crane_id in set(crane_ids)
    ) * productivity_factor
    if rate <= 0:
        return None
    effective = rate * weather_derate(state.weather_impact) * yard_friction(state.yard_utilisation)
    if effective <= 0.01:
        return None
    return float(call.moves / effective)


# --------------------------------------------------------------------------
# actions
# --------------------------------------------------------------------------

ASSIGN_BERTH = "assign_berth"
ASSIGN_CRANES = "assign_cranes"
DELAY_ARRIVAL = "delay_arrival"
PRIORITISE = "prioritise"
OPEN_OVERFLOW = "open_overflow"
NO_ACTION = "no_action"

ACTION_KINDS = (ASSIGN_BERTH, ASSIGN_CRANES, DELAY_ARRIVAL, PRIORITISE,
                OPEN_OVERFLOW, NO_ACTION)


@dataclass
class Action:
    """One decision a policy may take at a step."""

    kind: str
    call_id: Optional[str] = None
    berth_id: Optional[str] = None
    crane_ids: List[str] = field(default_factory=list)
    hours: float = 0.0
    block_id: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind, "callId": self.call_id, "berthId": self.berth_id,
            "craneIds": self.crane_ids, "hours": self.hours,
            "blockId": self.block_id, "reason": self.reason,
        }


#: A policy is a function from state to actions. Deliberately not a class, so a
#: one-line rule and a trained network are the same kind of thing to the engine.
Policy = Callable[[PortState], List[Action]]


class ConstraintViolation(Exception):
    """An action the simulator refused. Never raised out of :func:`simulate`."""


def validate_action(state: PortState, action: Action) -> Optional[str]:
    """Why this action cannot be taken, or ``None`` if it can.

    This is the safety layer. It runs on every action from every policy --
    hand-written, optimised or learned -- and it is not overridable. A learned
    policy that repeatedly proposes infeasible berthings accumulates rejections,
    which is a promotion-gate failure rather than a schedule nobody can run.
    """
    if action.kind == NO_ACTION:
        return None

    if action.kind == ASSIGN_BERTH:
        call = state.call(action.call_id or "")
        berth = state.berth(action.berth_id or "")
        if call is None:
            return f"unknown call {action.call_id}"
        if berth is None:
            return f"unknown berth {action.berth_id}"
        if call.state not in (WAITING, APPROACHING):
            return f"call {call.call_id} is {call.state} and cannot be berthed"
        if berth.occupied_by is not None:
            return f"berth {berth.berth_id} is occupied by {berth.occupied_by}"
        if not berth.can_accept(call.loa_m, call.draught_m, call.cargo_type):
            return (
                f"berth {berth.berth_id} cannot accept {call.name}: "
                f"LOA {call.loa_m:.0f}m/{berth.length_m:.0f}m, "
                f"draught {call.draught_m:.1f}m/{berth.depth_m:.1f}m, "
                f"cargo {call.cargo_type}"
            )
        if not berth.crane_ids:
            return f"berth {berth.berth_id} has no crane able to serve it"
        return None

    if action.kind == ASSIGN_CRANES:
        call = state.call(action.call_id or "")
        if call is None:
            return f"unknown call {action.call_id}"
        if call.berth_id is None:
            return f"call {call.call_id} has no berth, so cranes cannot be assigned"
        berth = state.berth(call.berth_id)
        reachable = set(berth.crane_ids) if berth else set()
        unreachable = [c for c in action.crane_ids if c not in reachable]
        if unreachable:
            return (
                f"cranes {', '.join(unreachable)} cannot reach berth {call.berth_id}"
            )
        busy = [
            c for c in action.crane_ids
            if (crane := state.crane(c)) and crane.assigned_berth not in (None, call.berth_id)
        ]
        if busy:
            return f"cranes {', '.join(busy)} are working another berth"
        return None

    if action.kind == DELAY_ARRIVAL:
        call = state.call(action.call_id or "")
        if call is None:
            return f"unknown call {action.call_id}"
        if call.state != APPROACHING:
            return (
                f"call {call.call_id} is {call.state}; an arrival can only be "
                "restaggered before the vessel arrives"
            )
        if action.hours < 0:
            return "an arrival cannot be moved earlier than the vessel can steam"
        if action.hours > 48:
            return "arrival delays beyond 48 h are outside the advisory envelope"
        return None

    if action.kind == PRIORITISE:
        if state.call(action.call_id or "") is None:
            return f"unknown call {action.call_id}"
        return None

    if action.kind == OPEN_OVERFLOW:
        if state.block(action.block_id or "") is None:
            return f"unknown yard block {action.block_id}"
        return None

    return f"unknown action kind {action.kind}"


def apply_action(state: PortState, action: Action) -> None:
    """Apply a validated action. Callers must validate first."""
    if action.kind == ASSIGN_BERTH:
        call = state.call(action.call_id or "")
        berth = state.berth(action.berth_id or "")
        assert call and berth
        cranes = action.crane_ids or list(berth.crane_ids)[:2]
        work = call_work_hours(state, call, cranes)
        if work is None:
            return                     # cranes cannot work; leave the call waiting
        call.state = ALONGSIDE
        call.berth_id = berth.berth_id
        call.berthed_hour = state.hour
        call.assigned_cranes = list(cranes)
        berth.occupied_by = call.call_id
        berth.free_at_hour = state.hour + BERTHING_OVERHEAD_HOURS + work + UNBERTHING_OVERHEAD_HOURS
        for crane_id in cranes:
            crane = state.crane(crane_id)
            if crane:
                crane.assigned_berth = berth.berth_id

    elif action.kind == ASSIGN_CRANES:
        call = state.call(action.call_id or "")
        assert call
        for crane_id in call.assigned_cranes:
            crane = state.crane(crane_id)
            if crane and crane_id not in action.crane_ids:
                crane.assigned_berth = None
        call.assigned_cranes = list(action.crane_ids)
        for crane_id in action.crane_ids:
            crane = state.crane(crane_id)
            if crane:
                crane.assigned_berth = call.berth_id
        # Re-plan the remaining work at the new rate.
        berth = state.berth(call.berth_id or "")
        if berth and berth.free_at_hour is not None:
            remaining = max(0.0, berth.free_at_hour - state.hour - UNBERTHING_OVERHEAD_HOURS)
            old_rate = sum(
                c.moves_per_hour for c in state.cranes
                if c.crane_id in set(call.assigned_cranes)
            )
            new_work = call_work_hours(state, call, action.crane_ids)
            if new_work is not None and old_rate > 0:
                berth.free_at_hour = state.hour + remaining * (
                    new_work / max(new_work, 1e-6)
                ) + UNBERTHING_OVERHEAD_HOURS

    elif action.kind == DELAY_ARRIVAL:
        call = state.call(action.call_id or "")
        assert call
        call.imposed_delay_hours += action.hours

    elif action.kind == PRIORITISE:
        call = state.call(action.call_id or "")
        assert call
        call.priority = min(1.0, call.priority + 0.35)

    elif action.kind == OPEN_OVERFLOW:
        block = state.block(action.block_id or "")
        assert block
        # Opening overflow raises the working stack height by one tier. It is
        # not free: deeper stacks mean more re-handles, which the friction curve
        # already charges for through a higher utilisation denominator.
        block.tiers += 1


# --------------------------------------------------------------------------
# the engine
# --------------------------------------------------------------------------


def simulate(
    state: PortState,
    policy: Policy,
    config: Optional[SimulationConfig] = None,
    *,
    snapshot_hours: Sequence[int] = (2, 6, 12, 24),
) -> SimulationResult:
    """Run the twin forward under a policy.

    The state passed in is cloned, never mutated. The result carries the final
    state, the metrics, the refused actions and any constraint violation the run
    produced.
    """
    config = config or SimulationConfig()
    working = state.clone()
    rng = random.Random(config.seed)
    result = SimulationResult(final_state=working, metrics={}, steps=0)
    base_weather = working.weather_impact

    # ETA noise is drawn once per call, up front, so the same seed produces the
    # same arrival sequence regardless of how many steps a policy takes.
    if config.eta_noise_hours > 0:
        for call in working.calls:
            call.eta_hour += rng.gauss(0.0, config.eta_noise_hours)

    pending_snapshots = sorted(set(snapshot_hours))
    steps = int(round(config.horizon_hours / config.step_hours))

    for step in range(steps):
        hour = step * config.step_hours
        working.hour = hour
        working.weather_impact = config.weather_at(hour, base_weather)

        _advance_arrivals(working, hour)
        _release_completed(working, hour, result)

        for action in policy(working) or []:
            problem = validate_action(working, action)
            if problem:
                result.rejected_actions.append(
                    {"hour": round(hour, 3), **action.to_dict(), "rejectedBecause": problem}
                )
                continue
            apply_action(working, action)
            if config.record_trace:
                result.trace.append(
                    SimulationEvent(
                        hour, action.kind, action.call_id or action.berth_id or "-",
                        action.reason or "policy action",
                    )
                )

        _accrue(working, config.step_hours)

        while pending_snapshots and hour >= pending_snapshots[0]:
            horizon = pending_snapshots.pop(0)
            result.snapshots[horizon] = working.metrics()

        result.steps += 1

    working.hour = config.horizon_hours
    _release_completed(working, config.horizon_hours, result)
    for horizon in pending_snapshots:
        result.snapshots[horizon] = working.metrics()

    result.metrics = working.metrics()
    result.metrics["rejectedActions"] = len(result.rejected_actions)
    result.violations = _check_violations(working)
    result.metrics["violations"] = len(result.violations)
    return result


def _advance_arrivals(state: PortState, hour: float) -> None:
    for call in state.calls:
        if call.state == APPROACHING and call.effective_eta <= hour:
            call.state = WAITING
            call.arrived_hour = hour


def _release_completed(state: PortState, hour: float, result: SimulationResult) -> None:
    for berth in state.berths:
        if berth.occupied_by is None or berth.free_at_hour is None:
            continue
        if berth.free_at_hour > hour:
            continue
        call = state.call(berth.occupied_by)
        berth.occupied_by = None
        berth.free_at_hour = None
        for crane in state.cranes:
            if crane.assigned_berth == berth.berth_id:
                crane.assigned_berth = None
        if call is None:
            continue                                  # a seeded pseudo-occupancy
        call.state = DEPARTED
        call.departed_hour = hour
        if result.trace is not None:
            result.trace.append(
                SimulationEvent(hour, "departure", call.call_id,
                                f"{call.name} sailed from {berth.berth_id}")
            )


def _accrue(state: PortState, step_hours: float) -> None:
    """Advance the clocks that only move because time passed."""
    for call in state.calls:
        if call.state == WAITING:
            call.wait_hours += step_hours
    for berth in state.berths:
        if berth.occupied_by is not None:
            berth.occupied_hours += step_hours
    for crane in state.cranes:
        if crane.assigned_berth is not None:
            crane.working_hours += step_hours * weather_derate(state.weather_impact)


def _check_violations(state: PortState) -> List[Dict[str, Any]]:
    """Hard constraints that must hold at the end of any legal run."""
    problems: List[Dict[str, Any]] = []
    for berth in state.berths:
        occupants = [c for c in state.calls if c.berth_id == berth.berth_id
                     and c.state == ALONGSIDE]
        if len(occupants) > 1:
            problems.append(
                {"kind": "double_berthing", "berth": berth.berth_id,
                 "detail": f"{len(occupants)} vessels alongside one berth"}
            )
        for call in occupants:
            if not berth.can_accept(call.loa_m, call.draught_m, call.cargo_type):
                problems.append(
                    {"kind": "berth_incompatible", "berth": berth.berth_id,
                     "call": call.call_id,
                     "detail": "vessel exceeds the berth's length, draught or cargo type"}
                )
    for block in state.yard_blocks:
        if block.occupied_teu > block.capacity_teu + 1e-6:
            problems.append(
                {"kind": "yard_overflow", "block": block.block_id,
                 "detail": f"{block.occupied_teu:.0f} TEU in a {block.capacity_teu:.0f} TEU block"}
            )
    return problems


# --------------------------------------------------------------------------
# reward
# --------------------------------------------------------------------------

#: Reward weights. Negative terms are costs. These are the operational
#: priorities made explicit, and every policy in the repository is scored
#: against exactly this function -- a policy that optimises something else is
#: not comparable and the benchmark says so.
REWARD_WEIGHTS: Dict[str, float] = {
    "wait_hours": -1.00,          # per vessel-hour at anchor
    "turnaround_hours": -0.30,    # per vessel-hour in port
    "missed_departure": -25.00,   # per call that sailed after its window
    "yard_overflow_block": -8.00, # per block over 95% at the end of the run
    "berth_idle_hours": -0.12,    # per berth-hour idle with a queue waiting
    "completed_call": 12.00,      # per call served
    "violation": -100.00,         # per hard-constraint breach
    "rejected_action": -1.50,     # per infeasible action proposed
}


def reward(result: SimulationResult, state: Optional[PortState] = None) -> float:
    """Scalar operational reward for a run. Higher is better.

    Used by the policy benchmark and by the RL trainer. It is deliberately the
    same function for both: a policy that scores well in training and badly in
    the benchmark would otherwise just be measuring two different things.
    """
    final = state or result.final_state
    metrics = result.metrics or final.metrics()
    completed = [c for c in final.calls if c.state == DEPARTED]

    total_wait = sum(c.wait_hours for c in final.calls)
    total_turnaround = sum(
        c.turnaround_hours or 0.0 for c in completed
    )
    missed = sum(
        1 for c in completed
        if c.latest_departure_hour is not None and c.departed_hour is not None
        and c.departed_hour > c.latest_departure_hour
    )
    idle = _berth_idle_with_queue(final)

    w = REWARD_WEIGHTS
    return float(
        w["wait_hours"] * total_wait
        + w["turnaround_hours"] * total_turnaround
        + w["missed_departure"] * missed
        + w["yard_overflow_block"] * int(metrics.get("yardOverflowBlocks", 0))
        + w["berth_idle_hours"] * idle
        + w["completed_call"] * len(completed)
        + w["violation"] * len(result.violations)
        + w["rejected_action"] * len(result.rejected_actions)
    )


def _berth_idle_with_queue(state: PortState) -> float:
    """Berth-hours wasted while something was waiting.

    An idle berth is only a cost when there is a queue: a quiet port with empty
    berths is not being run badly.
    """
    if not state.queue_length:
        return 0.0
    free = len(state.free_berths())
    return float(free * min(state.queue_length, free))


def reward_breakdown(result: SimulationResult) -> Dict[str, float]:
    """The reward, term by term. Shown wherever a policy result is reported."""
    final = result.final_state
    metrics = result.metrics or final.metrics()
    completed = [c for c in final.calls if c.state == DEPARTED]
    missed = sum(
        1 for c in completed
        if c.latest_departure_hour is not None and c.departed_hour is not None
        and c.departed_hour > c.latest_departure_hour
    )
    w = REWARD_WEIGHTS
    terms = {
        "waitHours": w["wait_hours"] * sum(c.wait_hours for c in final.calls),
        "turnaroundHours": w["turnaround_hours"] * sum(
            c.turnaround_hours or 0.0 for c in completed
        ),
        "missedDepartures": w["missed_departure"] * missed,
        "yardOverflow": w["yard_overflow_block"] * int(metrics.get("yardOverflowBlocks", 0)),
        "berthIdle": w["berth_idle_hours"] * _berth_idle_with_queue(final),
        "completedCalls": w["completed_call"] * len(completed),
        "violations": w["violation"] * len(result.violations),
        "rejectedActions": w["rejected_action"] * len(result.rejected_actions),
    }
    terms["total"] = sum(terms.values())
    return {k: round(v, 3) for k, v in terms.items()}


__all__ = [
    "ACTION_KINDS",
    "ASSIGN_BERTH",
    "ASSIGN_CRANES",
    "BERTHING_OVERHEAD_HOURS",
    "CRANE_STOP_IMPACT",
    "DELAY_ARRIVAL",
    "NO_ACTION",
    "OPEN_OVERFLOW",
    "PRIORITISE",
    "REWARD_WEIGHTS",
    "UNBERTHING_OVERHEAD_HOURS",
    "YARD_FRICTION_KNEE",
    "Action",
    "ConstraintViolation",
    "Policy",
    "SimulationConfig",
    "SimulationEvent",
    "SimulationResult",
    "apply_action",
    "call_work_hours",
    "reward",
    "reward_breakdown",
    "simulate",
    "validate_action",
    "weather_derate",
    "yard_friction",
]
