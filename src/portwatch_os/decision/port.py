"""Port decisions through the port twin, on the same decision model as a
vessel's routing.

Three ships arrive within ninety minutes. The port authority can leave the
incumbent rule alone, reassign berths by expected work, stagger the arrivals
through advisories, size the crane gangs to the calls, or move one call up
the queue. Each is an option; each is the same twin state cloned and run
forward under that policy; each is measured on wait, turnaround, yard,
berths, cranes and missed departures; and the incumbent rule -- first come,
first served -- is the baseline every alternative is compared against,
computed by the same simulator.

The simulator's physical constraints are the hard constraints here. A policy
that proposes a berth the hull cannot fit has that action refused and
recorded; an option whose *defining* action is refused is REJECTED with the
simulator's reason, not scored a little lower.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.decision.actions import (
    CHANGE_CRANE_ALLOCATION,
    CHANGE_YARD_ALLOCATION,
    ISSUE_ADVISORY,
    KEEP_SCHEDULE,
    PRIORITISE_VESSEL,
    REASSIGN_BERTH,
    SHIFT_ARRIVAL_SLOT,
    availability_of,
    for_domain,
)
from src.portwatch_os.decision.model import (
    AVAILABLE,
    Availability,
    ConstraintResult,
    DecisionActor,
    DecisionEvaluation,
    DecisionOption,
    DecisionProblem,
    FEASIBLE,
    Measure,
    OBJECTIVES,
    PORT_BERTHING,
    REJECTED,
    UNAVAILABLE,
    known,
    unknown,
)
from src.portwatch_os.finance.basis import CostBasis
from src.portwatch_os.finance.evaluate import Pricer
from src.portwatch_os.finance.money import FxTable, HOUR, Quantity as MoneyQuantity
from src.portwatch_os.twin.policies import FirstComeFirstServed, GreedyPolicy, LookaheadPolicy, gang_size
from src.portwatch_os.twin.simulation import (
    ASSIGN_BERTH,
    DELAY_ARRIVAL,
    OPEN_OVERFLOW,
    PRIORITISE,
    Action,
    SimulationConfig,
    SimulationResult,
    simulate,
)
from src.portwatch_os.twin.state import APPROACHING, DEPARTED, PortState, VesselCall
from src.portwatch_os.world.quantity import utc

#: The twin is a model seeded from observation; its figures carry this.
TWIN_CONFIDENCE = 0.6
#: Arrivals within this many hours of each other are "bunched".
BUNCH_WINDOW_HOURS = 1.5
#: Stagger step for the arrival-slot option.
STAGGER_HOURS = 2.0
#: Yard blocks above this utilisation get an overflow tier under the yard option.
OVERFLOW_THRESHOLD = 0.90

PORT_OBJECTIVES: Tuple[str, ...] = (
    "port_wait", "turnaround", "missed_departures", "berth_utilisation", "yard_pressure",
    "crane_utilisation", "cost", "uncertainty",
)
FRONTIER_OBJECTIVES: Tuple[str, ...] = ("port_wait", "missed_departures", "turnaround")


class PortDecisionError(ValueError):
    """The twin does not hold what a port decision needs."""


# --------------------------------------------------------------------------
# option policies
# --------------------------------------------------------------------------


def _bunched(state: PortState) -> List[VesselCall]:
    """Approaching calls whose ETAs fall within the bunch window of another."""
    approaching = sorted((c for c in state.calls if c.state == APPROACHING), key=lambda c: c.effective_eta)
    out: List[VesselCall] = []
    for index, call in enumerate(approaching):
        near = [o for o in approaching if o is not call and abs(o.effective_eta - call.effective_eta) <= BUNCH_WINDOW_HOURS]
        if near:
            out.append(call)
    return out


def _with_prelude(base: Callable[[PortState], List[Action]], prelude: List[Action]) -> Callable[[PortState], List[Action]]:
    """A policy that emits scripted actions at hour zero, then defers to ``base``."""
    fired = {"done": False}

    def policy(state: PortState) -> List[Action]:
        actions: List[Action] = []
        if not fired["done"]:
            fired["done"] = True
            actions.extend(prelude)
        actions.extend(base(state) or [])
        return actions

    return policy


def _max_gang(base: Callable[[PortState], List[Action]]) -> Callable[[PortState], List[Action]]:
    """The base policy's berthings, with every free reachable crane on the call."""

    def policy(state: PortState) -> List[Action]:
        actions = list(base(state) or [])
        claimed: set = set()
        for action in actions:
            if action.kind != ASSIGN_BERTH:
                continue
            berth = state.berth(action.berth_id or "")
            call = state.call(action.call_id or "")
            if berth is None or call is None:
                continue
            free = [c.crane_id for c in state.cranes
                    if c.crane_id in berth.crane_ids and c.assigned_berth is None and c.crane_id not in claimed]
            want = min(5, gang_size(call) + 1)
            action.crane_ids = free[:want]
            action.reason = "berthed with the largest gang the quay can reach"
            claimed.update(action.crane_ids)
        return actions

    return policy


@dataclass
class PortPlan:
    action: str
    label: str
    params: Dict[str, Any]
    policy: Callable[[PortState], List[Action]]
    #: Scripted actions the option depends on; a refusal of any is a rejection.
    defining: List[Action]
    is_baseline: bool = False
    notes: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.notes is None:
            self.notes = []


def _plans(state: PortState, actor: str) -> Tuple[List[PortPlan], List[Dict[str, Any]]]:
    subject = {
        "calls": [c.call_id for c in state.calls] or None,
        "berths": [b.berth_id for b in state.berths] or None,
        "cranes": [c.crane_id for c in state.cranes] or None,
        "yard_blocks": [b.block_id for b in state.yard_blocks] or None,
        "anchorage": None,
    }
    bunched = _bunched(state)
    checks = {
        SHIFT_ARRIVAL_SLOT: lambda s: Availability(AVAILABLE) if bunched else Availability(
            UNAVAILABLE, "no approaching arrivals fall within the bunch window of each other"),
        PRIORITISE_VESSEL: lambda s: Availability(AVAILABLE) if any(
            c.latest_departure_hour is not None and c.state != DEPARTED for c in state.calls
        ) else Availability(UNAVAILABLE, "no call declares a departure commitment to prioritise for"),
        CHANGE_YARD_ALLOCATION: lambda s: Availability(AVAILABLE) if any(
            b.utilisation >= OVERFLOW_THRESHOLD for b in state.yard_blocks
        ) else Availability(UNAVAILABLE, f"no yard block is above {OVERFLOW_THRESHOLD:.0%}"),
    }
    plans: List[PortPlan] = []
    rows: List[Dict[str, Any]] = []
    for spec in for_domain(PORT_BERTHING):
        availability = availability_of(spec, subject, actor=actor, checks=checks)
        row = {**spec.to_dict(), "availability": availability.to_dict()}
        if spec.kind == ISSUE_ADVISORY:
            row["mechanism"] = ("the boundary an approved port option crosses to reach a master; "
                                "not a scenario of its own")
            rows.append(row)
            continue
        rows.append(row)
        if not availability.available:
            continue
        if spec.kind == KEEP_SCHEDULE:
            plans.append(PortPlan(KEEP_SCHEDULE, "Continue current plan (first come, first served)",
                                  {"policy": "fcfs"}, FirstComeFirstServed(), [], is_baseline=True))
        elif spec.kind == REASSIGN_BERTH:
            plans.append(PortPlan(REASSIGN_BERTH, "Reassign berths by expected work",
                                  {"policy": "greedy"}, GreedyPolicy(), []))
            plans.append(PortPlan(REASSIGN_BERTH, "Reassign berths with arrival lookahead",
                                  {"policy": "lookahead"}, LookaheadPolicy(), []))
        elif spec.kind == SHIFT_ARRIVAL_SLOT:
            prelude = [
                Action(kind=DELAY_ARRIVAL, call_id=c.call_id, hours=STAGGER_HOURS * index,
                       reason=f"staggered arrival slot (+{STAGGER_HOURS * index:.0f} h)")
                for index, c in enumerate(sorted(bunched, key=lambda c: c.effective_eta))
                if index > 0
            ]
            plans.append(PortPlan(SHIFT_ARRIVAL_SLOT,
                                  f"Stagger {len(bunched)} bunched arrivals by {STAGGER_HOURS:.0f} h",
                                  {"policy": "fcfs", "staggerHours": STAGGER_HOURS,
                                   "calls": [c.call_id for c in bunched]},
                                  _with_prelude(FirstComeFirstServed(), prelude), prelude))
        elif spec.kind == CHANGE_CRANE_ALLOCATION:
            plans.append(PortPlan(CHANGE_CRANE_ALLOCATION, "Size crane gangs to the call",
                                  {"policy": "fcfs+max-gang"}, _max_gang(FirstComeFirstServed()), []))
        elif spec.kind == PRIORITISE_VESSEL:
            committed = [c for c in state.calls if c.latest_departure_hour is not None and c.state != DEPARTED]
            target = min(committed, key=lambda c: c.latest_departure_hour)  # type: ignore[arg-type]
            prelude = [Action(kind=PRIORITISE, call_id=target.call_id,
                              reason="earliest departure commitment moved up the queue")]
            plans.append(PortPlan(PRIORITISE_VESSEL, f"Prioritise {target.name}",
                                  {"policy": "fcfs", "callId": target.call_id},
                                  _with_prelude(FirstComeFirstServed(), prelude), prelude))
        elif spec.kind == CHANGE_YARD_ALLOCATION:
            blocks = [b for b in state.yard_blocks if b.utilisation >= OVERFLOW_THRESHOLD]
            prelude = [Action(kind=OPEN_OVERFLOW, block_id=b.block_id, reason="overflow tier opened")
                       for b in blocks]
            plans.append(PortPlan(CHANGE_YARD_ALLOCATION, f"Open overflow on {len(blocks)} yard block(s)",
                                  {"policy": "fcfs", "blocks": [b.block_id for b in blocks]},
                                  _with_prelude(FirstComeFirstServed(), prelude), prelude))
    return plans, rows


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------


def _crane_utilisation(result: SimulationResult, horizon: float) -> Optional[float]:
    cranes = result.final_state.cranes
    if not cranes or horizon <= 0:
        return None
    return sum(c.working_hours for c in cranes) / (len(cranes) * horizon)


def _mean_berth_utilisation(result: SimulationResult, horizon: float) -> Optional[float]:
    berths = result.final_state.berths
    if not berths or horizon <= 0:
        return None
    return sum(b.occupied_hours for b in berths) / (len(berths) * horizon)


def evaluate_plan(
    plan: PortPlan,
    state: PortState,
    *,
    config: SimulationConfig,
    basis: CostBasis,
    fx: FxTable,
    currency: str,
    at: datetime,
) -> DecisionOption:
    result = simulate(state, plan.policy, config)
    metrics = result.metrics
    horizon = config.horizon_hours
    measures: Dict[str, Measure] = {}
    basis_note = f"twin simulate() under {plan.params.get('policy')} over {horizon:.0f} h"

    wait = metrics.get("meanWaitHours")
    measures["port_wait"] = (known(wait, "hours", basis=basis_note, confidence=TWIN_CONFIDENCE,
                                   maxWaitHours=metrics.get("maxWaitHours"))
                             if wait is not None else unknown("hours", "no call completed within the horizon"))
    turnaround = metrics.get("meanTurnaroundHours")
    measures["turnaround"] = (known(turnaround, "hours", basis=basis_note, confidence=TWIN_CONFIDENCE)
                              if turnaround is not None else unknown("hours", "no call completed within the horizon"))
    measures["missed_departures"] = known(float(metrics.get("missedDepartures", 0)), "count",
                                          basis=basis_note, confidence=TWIN_CONFIDENCE)
    berths = _mean_berth_utilisation(result, horizon)
    measures["berth_utilisation"] = (known(berths, "ratio", basis=basis_note + " (mean occupied share)",
                                           confidence=TWIN_CONFIDENCE)
                                     if berths is not None else unknown("ratio", "the twin declares no berths"))
    measures["yard_pressure"] = known(float(metrics.get("yardUtilisation", 0.0)), "ratio",
                                      basis=basis_note + " (final yard utilisation)", confidence=TWIN_CONFIDENCE,
                                      overflowBlocks=metrics.get("yardOverflowBlocks"))
    cranes = _crane_utilisation(result, horizon)
    measures["crane_utilisation"] = (known(cranes, "ratio", basis=basis_note + " (working share)",
                                           confidence=TWIN_CONFIDENCE)
                                     if cranes is not None else unknown("ratio", "the twin declares no cranes"))

    # -- money: berth hire on alongside hours needs each call's tonnage ------
    pricer = Pricer(basis, at=at, currency=currency, fx=fx, scope=state.port_code, vessel_status="foreign",
                    vessel_type="container")
    alongside = sum(b.occupied_hours for b in result.final_state.berths)
    components = [
        pricer.unknown("berth_hire", "Berth hire",
                       "the twin's calls declare no gross tonnage, so per-GRT berth hire cannot be computed "
                       "for the alongside hours simulated", driver="berth_utilisation"),
        pricer.unknown("delay", "Cost of waiting",
                       "no demurrage or charter basis is scoped to the calls at this port", driver="port_wait"),
    ]
    financial = pricer.evaluation(components, notes=[f"{alongside:.0f} berth-hours alongside over the horizon"]).to_dict()
    measures["cost"] = unknown("money", "; ".join(u["reason"] for u in financial["unknown"]))
    measures["uncertainty"] = known(1.0 - TWIN_CONFIDENCE, "ratio",
                                    basis="the twin is a schematic model seeded from observation",
                                    confidence=1.0)

    constraints: List[ConstraintResult] = []
    violations = result.violations
    constraints.append(ConstraintResult(
        "physical_constraints", "No hard-constraint violation in the run", not violations, True,
        "; ".join(v.get("detail", "") for v in violations) or "the run ended with every berth and yard constraint held",
        basis="twin.simulation._check_violations",
    ))
    defining_ids = {(a.kind, a.call_id, a.block_id) for a in plan.defining}
    refused_defining = [r for r in result.rejected_actions
                        if (r.get("kind"), r.get("callId"), r.get("blockId")) in defining_ids]
    constraints.append(ConstraintResult(
        "defining_actions_accepted", "The option's own actions were accepted by the simulator",
        not refused_defining, True,
        "; ".join(r.get("rejectedBecause", "") for r in refused_defining) or
        (f"{len(plan.defining)} scripted action(s) accepted" if plan.defining else "no scripted action"),
        basis="twin.simulation.validate_action",
    ))
    constraints.append(ConstraintResult(
        "policy_rejections", "Policy proposals refused by the simulator", True, False,
        f"{len(result.rejected_actions) - len(refused_defining)} proposal(s) refused and recorded",
        basis="twin.simulation.validate_action",
    ))
    rejected = [c for c in constraints if c.hard and not c.passed]

    assignments = [
        {"callId": c.call_id, "name": c.name, "berthId": c.berth_id, "berthedHour": c.berthed_hour,
         "departedHour": c.departed_hour, "waitHours": round(c.wait_hours, 2),
         "craneIds": list(c.assigned_cranes), "imposedDelayHours": c.imposed_delay_hours, "state": c.state}
        for c in result.final_state.calls
    ]
    evaluation = DecisionEvaluation(
        objectives=measures,
        consequences=[{"node": f"port:{state.port_code}", "kind": "port", "label": state.port_name,
                       "metrics": metrics, "snapshots": {str(k): v for k, v in result.snapshots.items()}}],
        derived={"assignments": assignments, "rejectedActions": result.rejected_actions[:20],
                 "trace": [e.to_dict() for e in result.trace[:60]], "policy": plan.params.get("policy"),
                 "horizonHours": horizon},
        financial=financial, notes=list(plan.notes), computed_at=utc().isoformat(timespec="seconds"),
    )
    suffix = plan.params.get("policy", "").replace("+", "-")
    option_id = plan.action.lower() + (f"-{suffix}" if plan.action == REASSIGN_BERTH else "")
    return DecisionOption(
        option_id=option_id, action=plan.action, label=plan.label, actor="", params=plan.params,
        constraints=constraints, status=REJECTED if rejected else FEASIBLE,
        evaluation=None if rejected else evaluation, is_baseline=plan.is_baseline,
        assumptions=[{"kind": "policy", "policy": plan.params.get("policy"), "source": "ASSUMPTION"}],
        provenance={"simulator": "src.portwatch_os.twin.simulation.simulate", "seed": config.seed,
                    "closesInHours": _closes_in(plan, state)},
        timeline=[{"kind": "arrival", "subject": c.call_id, "hours": round(c.effective_eta, 1)}
                  for c in sorted(state.calls, key=lambda c: c.effective_eta) if c.state == APPROACHING][:8],
    )


def _closes_in(plan: PortPlan, state: PortState) -> Optional[float]:
    """An arrival can only be restaggered before it arrives."""
    if plan.action != SHIFT_ARRIVAL_SLOT:
        return None
    calls = [state.call(a.call_id or "") for a in plan.defining]
    etas = [c.effective_eta for c in calls if c is not None]
    return max(0.0, min(etas)) if etas else None


# --------------------------------------------------------------------------
# the problem
# --------------------------------------------------------------------------


def build_port_problem(
    state: PortState,
    *,
    decision_id: str,
    actor: DecisionActor,
    at: datetime,
    world_state_id: str,
    world_revision: Dict[str, Any],
    basis: CostBasis,
    fx: Optional[FxTable] = None,
    currency: str = "USD",
    horizon_hours: float = 24.0,
    attention_item_id: Optional[str] = None,
) -> DecisionProblem:
    if not state.berths:
        raise PortDecisionError(f"{state.port_code} declares no berths; nothing to decide")
    if not state.calls:
        raise PortDecisionError(f"{state.port_code} has no calls in the horizon; nothing to decide")
    plans, rows = _plans(state, actor.role)
    if not any(p.is_baseline for p in plans):
        raise PortDecisionError(f"{actor.role} holds no baseline action for a port decision")
    config = SimulationConfig(horizon_hours=horizon_hours)
    table = fx if fx is not None else FxTable()
    options = []
    for plan in plans:
        option = evaluate_plan(plan, state, config=config, basis=basis, fx=table, currency=currency, at=at)
        option.actor = actor.role
        options.append(option)
    baseline = next(o for o in options if o.is_baseline)
    windows = [o.provenance.get("closesInHours") for o in options
               if o.feasible and o.provenance.get("closesInHours") is not None]
    window = min(windows) if windows else None
    bunched = _bunched(state)
    problem = DecisionProblem(
        decision_id=decision_id, created_at=utc().isoformat(timespec="seconds"), domain=PORT_BERTHING,
        world_revision=world_revision, world_state_id=world_state_id,
        subject_type="port", subject_id=state.port_code, subject_label=state.port_name,
        actor=actor, attention_item_id=attention_item_id, cascade_id=None,
        decision_deadline=None if window is None else None, decision_window_hours=window, at=at.isoformat(),
        objectives=[OBJECTIVES[k] for k in PORT_OBJECTIVES],
        hard_constraints=["physical_constraints", "defining_actions_accepted"],
        soft_constraints=["policy_rejections"],
        available_actions=rows, baseline_option_id=baseline.option_id, options=options,
        evidence={
            "twin": {"portCode": state.port_code, "berths": len(state.berths), "cranes": len(state.cranes),
                     "calls": len(state.calls), "queue": state.queue_length,
                     "yardUtilisation": round(state.yard_utilisation, 3), "geometryBasis": state.geometry_basis,
                     "notes": state.notes},
            "bunchedArrivals": [{"callId": c.call_id, "name": c.name, "etaHour": round(c.effective_eta, 1),
                                 "loaM": c.loa_m, "draughtM": c.draught_m} for c in bunched],
            "simulation": {"horizonHours": horizon_hours, "seed": config.seed, "stepHours": config.step_hours},
            "costBasis": basis.coverage(at=at, scope=state.port_code),
            "frontierObjectives": list(FRONTIER_OBJECTIVES),
        },
        headline=f"{state.port_name} · {len(bunched)} arrivals bunched" if bunched else f"{state.port_name} · berth plan",
        do_nothing_statement=_do_nothing(baseline),
    )
    problems = problem.validate()
    if problems:
        raise PortDecisionError("; ".join(problems))
    return problem


def _do_nothing(baseline: DecisionOption) -> str:
    wait = baseline.measure("port_wait")
    missed = baseline.measure("missed_departures")
    parts = []
    if wait is not None and wait.available:
        parts.append(f"mean wait {wait.value:.1f} h under first come, first served")
    if missed is not None and missed.available and missed.value > 0:
        parts.append(f"{missed.value:.0f} missed departure(s)")
    return "If unchanged: " + ", ".join(parts) if parts else "If unchanged: no call completes within the horizon"


__all__ = [
    "BUNCH_WINDOW_HOURS",
    "FRONTIER_OBJECTIVES",
    "OVERFLOW_THRESHOLD",
    "PORT_OBJECTIVES",
    "PortDecisionError",
    "PortPlan",
    "STAGGER_HOURS",
    "TWIN_CONFIDENCE",
    "build_port_problem",
    "evaluate_plan",
]
