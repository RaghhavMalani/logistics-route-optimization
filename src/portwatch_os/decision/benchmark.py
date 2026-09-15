"""The decision benchmark: does the optimiser add value, measured, on a fixed
corpus, against baselines that had the same options.

Every case is synthetic and seeded. Nothing is drawn from a live feed, so
the corpus is the same on every machine and every run, and nothing in it
was chosen after seeing which policy won. Three domains, five policies,
one hidden truth per case:

    VESSEL   a chokepoint claim and a hull bound through it. The hidden truth
             is how long the closure actually lasted (drawn from the claim's
             severity and confidence; some claims fizzle). Options are scored
             with the mission scorecard's realised model -- the same one the
             Ever Given replay is scored by -- so the evaluation is not the
             engine's own prediction.
    PORT     a berth plan for arrivals that bunch. The hidden truth is what
             the ships actually did: arrivals slip, moves run over. The chosen
             plan is re-simulated on the true state. The simulator is the
             product's port twin; the perturbation is what no policy knew.
    CARGO    a transshipment connection. The hidden truth is the inbound
             discharge slipping and the outbound cut-off moving. The chosen
             connection is re-evaluated on the true hours.

The five policies choose from the *same* option set the engine enumerated
and simulated. That is deliberate: it isolates what the optimiser adds --
the frontier, the balanced ranking, the Critic, the robust gate -- from what
the simulator adds, which every policy here gets for free.

    current_plan        the baseline option: do nothing, first come first
                        served, keep the booking
    greedy              the feasible option that minimises the headline
                        predicted objective (ETA shift, port wait, sailing
                        hour), ignoring the others
    heuristic           a rule a duty officer would apply: reroute a hull that
                        would reach a severe closure inside its horizon, else
                        slow down; prioritise the earliest departure
                        commitment, else stagger a bunch; move a box with no
                        slack to the most forgiving sailing
    portwatch_balanced  the incumbent: the BALANCED expected-value ranking
    portwatch_robust    the candidate: the robust gate over stress horizons,
                        which may answer KEEP_CURRENT_PLAN or
                        WAIT_FOR_MORE_INFORMATION

A ``WAIT_FOR_MORE_INFORMATION`` answer is scored by simulating the wait: if
the closure had ended by the re-evaluation instant the hull keeps its plan;
otherwise it takes the provisional option the recommendation named, or keeps
its plan when none was named. The benchmark has no second observation of its
own, so this is the stated model of what waiting does, and it is counted
separately as the wait rate.

Three corpora, disjoint by seed range, so a policy tuned on one can be
judged on another it never saw:

    tuning       seeds 1-40      the original corpus; results were read while
                                 the robust policy was designed
    validation   seeds 1001-1100 read once the design was fixed, to check it
    test         seeds 5001-5200 untouched until the final report

Metrics per case: realised delay (hours), constraint violations (a chosen
option that was infeasible, a missed departure, a missed connection), a
fuel proxy, realised risk (caught in the closure; the connection missed),
throughput (moves completed in the port horizon), regret against the
realised best option (floored at zero: an infeasible pick is scored as the
plan and counted as a violation, and the plan's figure earns it no credit),
whether the policy intervened and whether that intervention was unnecessary
(the current plan realised no more delay), and decision time. Aggregates -- mean, median, p90 and worst regret among them --
are published as they come out. Where PortWatch loses, the case is listed.
"""

from __future__ import annotations

import math
import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.decision.actions import (
    CHANGE_DESTINATION_PORT,
    PRIORITISE_VESSEL,
    REROUTE,
    SHIFT_ARRIVAL_SLOT,
    SLOW_STEAM,
    TRANSFER_TO_VESSEL,
)
from src.portwatch_os.decision.engine import DecisionEngine
from src.portwatch_os.decision.model import (
    DecisionActor,
    DecisionOption,
    DecisionProblem,
    PORT_AUTHORITY,
    SHIPPING_COMPANY,
    WAIT_FOR_MORE_INFORMATION,
)
from src.portwatch_os.decision.outcome import parse_instant
from src.portwatch_os.decision.robust import ROBUST_POLICY

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
VESSEL, PORT, CARGO = "VESSEL", "PORT", "CARGO"
DOMAINS = (VESSEL, PORT, CARGO)
INCUMBENT = "portwatch_balanced"
CANDIDATE = "portwatch_robust"
POLICIES = ("current_plan", "greedy", "heuristic", INCUMBENT, CANDIDATE)
METRICS = ("delay", "violations", "fuel", "risk", "throughput", "regret", "decision_ms")

#: The frozen corpora: name -> (first seed, cases per domain). Disjoint ranges.
CORPORA: Dict[str, Tuple[int, int]] = {
    "tuning": (1, 40),
    "validation": (1001, 100),
    "test": (5001, 200),
}


# --------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------


@dataclass
class Choice:
    """One policy's pick on one case, scored against the truth."""

    policy: str
    option_id: Optional[str]
    delay: Optional[float] = None
    violations: int = 0
    fuel: Optional[float] = None
    risk: Optional[float] = None
    throughput: Optional[float] = None
    regret: Optional[float] = None
    decision_ms: float = 0.0
    note: str = ""
    #: The recommendation kind the policy answered with (ACT, KEEP_CURRENT_PLAN,
    #: WAIT_FOR_MORE_INFORMATION); the baselines always ACT or keep.
    kind: Optional[str] = None
    #: Whether the option finally scored was not the baseline.
    intervened: bool = False
    #: An intervention that realised no less delay than the current plan.
    unnecessary: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"policy": self.policy, "optionId": self.option_id, "delay": self.delay,
                "violations": self.violations, "fuel": self.fuel, "risk": self.risk,
                "throughput": self.throughput, "regret": self.regret, "decisionMs": round(self.decision_ms, 2),
                "note": self.note, "kind": self.kind, "intervened": self.intervened, "unnecessary": self.unnecessary}


@dataclass
class CaseResult:
    domain: str
    case_id: str
    seed: int
    description: str
    truth: Dict[str, Any]
    options: int
    feasible: int
    best_option_id: Optional[str]
    best_delay: Optional[float]
    choices: Dict[str, Choice] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"domain": self.domain, "caseId": self.case_id, "seed": self.seed, "description": self.description,
                "truth": self.truth, "options": self.options, "feasible": self.feasible,
                "bestOptionId": self.best_option_id, "bestDelay": self.best_delay,
                "choices": {k: v.to_dict() for k, v in self.choices.items()}, "error": self.error}


def _elapsed_ms(started: float) -> float:
    return 1000.0 * (time.perf_counter() - started)


def _feasible(problem: DecisionProblem) -> List[DecisionOption]:
    return [o for o in problem.options if o.feasible and o.evaluation is not None]


def _value(option: Optional[DecisionOption], key: str) -> Optional[float]:
    if option is None:
        return None
    measure = option.measure(key)
    return None if measure is None or not measure.available else float(measure.value)


# --------------------------------------------------------------------------
# VESSEL
# --------------------------------------------------------------------------


def _vessel_case(seed: int):
    """A claim, a hull, and the closure that actually happened."""
    from src.portwatch_os.global_eye.exposure import VesselVoyage
    from src.portwatch_os.global_eye.model import GlobalEvent

    rng = random.Random(seed)
    chokepoint = rng.choice(["BAB_EL_MANDEB", "SUEZ"])
    lane = rng.choice(["EUR_IND", "MED_IND", "USEC_IND"])
    severity = round(rng.uniform(0.25, 1.0), 3)
    confidence = round(rng.uniform(0.4, 0.95), 3)
    horizon = rng.choice([48.0, 72.0, 96.0])
    first_seen = NOW - timedelta(hours=rng.uniform(0.5, 12.0))
    # Some hulls are already past Suez (negative hours), on the Red Sea side of
    # the routing branch: for them the Cape is not an option and the engine
    # must say so rather than offer it.
    suez = round(rng.uniform(-20.0, 120.0), 1)
    bab = suez + 30.0
    hours = {"SUEZ": suez, "BAB_EL_MANDEB": bab}
    event = GlobalEvent(
        event_id=f"BM-EV-{seed}", title=f"benchmark closure {seed}", category="chokepoint_disruption",
        region="benchmark", lat=12.6, lon=43.3, geolocation_basis="chokepoint",
        first_seen=first_seen.isoformat(), last_seen=NOW.isoformat(), source_count=rng.randint(1, 8),
        confidence=confidence, severity=severity, horizon_hours=horizon, chokepoints=[chokepoint],
    )
    subject = VesselVoyage(
        vessel_id=f"BM-V-{seed}", name=f"Benchmark hull {seed}", lane_code=lane, destination_port="INNSA",
        hours_to_chokepoint=hours, service_speed_kn=round(rng.uniform(14.0, 20.0), 1),
    )
    # The truth. Median closure grows with severity (a severity-1 claim is an
    # Ever Given; a 0.3 claim is a day's disruption); the spread is lognormal;
    # and a claim fizzles with a probability that falls with corroboration.
    fizzled = rng.random() < 0.5 * (1.0 - confidence)
    median = 12.0 + 150.0 * severity ** 2
    duration = 0.0 if fizzled else max(2.0, median * math.exp(rng.gauss(0.0, 0.55)))
    drain = 0.0 if fizzled else duration * rng.uniform(0.3, 0.8)
    truth = {
        "closureHours": round(duration, 1), "fizzled": fizzled, "backlogDrainHours": round(drain, 1),
        "blockedFrom": first_seen.isoformat(timespec="seconds"),
        "reopenedAt": (first_seen + timedelta(hours=duration)).isoformat(timespec="seconds"),
        "backlogClearedAt": (first_seen + timedelta(hours=duration + drain)).isoformat(timespec="seconds"),
    }
    description = (f"{lane} hull {suez:.0f} h from Suez; {chokepoint} claim severity {severity:.2f}, "
                   f"confidence {confidence:.2f}, horizon {horizon:.0f} h")
    return event, subject, truth, description


def _vessel_realised(problem: DecisionProblem, truth: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Every option's realised delay under the mission scorecard's model."""
    from src.portwatch_os.missions.model import Outcome
    from src.portwatch_os.missions.scorecard import realised_delay_hours

    outcome = Outcome(
        reopened_at=truth["reopenedAt"], blocked_from=truth["blockedFrom"], backlog_cleared_on=truth["backlogClearedAt"][:10],
        backlog_cleared_bound=truth["backlogClearedAt"], ships_waiting_peak=None, ships_waiting_source_id=None,
        summary="benchmark truth", sources=[],
    )
    clock = datetime.fromisoformat(problem.at)
    reopened = datetime.fromisoformat(truth["reopenedAt"])
    realised: Dict[str, Dict[str, Any]] = {}
    for option in problem.options:
        row = realised_delay_hours(option, problem, outcome, clock=clock)
        if row is None:
            continue
        derived = option.evaluation.derived if option.evaluation else (option.provenance.get("rejectedEvaluation") or {}).get("derived", {})
        hours_to = derived.get("hoursToChokepoint")
        caught = None
        if option.action in (REROUTE, CHANGE_DESTINATION_PORT):
            caught = 0.0
        elif hours_to is not None:
            hold = float(derived.get("holdHours") or 0.0)
            caught = 1.0 if clock + timedelta(hours=float(hours_to) + hold) < reopened else 0.0
        realised[option.option_id] = {"delay": row["hours"], "how": row["how"], "caught": caught,
                                      "feasible": option.feasible}
    return realised


def _vessel_policies(problem: DecisionProblem, event) -> Dict[str, Tuple[Optional[str], float, str]]:
    """Each policy's pick: (option id, selection time in ms, note)."""
    picks: Dict[str, Tuple[Optional[str], float, str]] = {}
    started = time.perf_counter()
    picks["current_plan"] = (problem.baseline_option_id, _elapsed_ms(started), "the baseline option")

    started = time.perf_counter()
    feasible = _feasible(problem)
    with_eta = [o for o in feasible if _value(o, "eta") is not None]
    greedy = min(with_eta, key=lambda o: _value(o, "eta")) if with_eta else None
    picks["greedy"] = (greedy.option_id if greedy else None, _elapsed_ms(started), "minimum predicted ETA shift")

    started = time.perf_counter()
    subject_hours = None
    for option in problem.options:
        derived = (option.evaluation.derived if option.evaluation else
                   (option.provenance.get("rejectedEvaluation") or {}).get("derived", {}))
        if derived.get("hoursToChokepoint") is not None and option.is_baseline:
            subject_hours = float(derived["hoursToChokepoint"])
    by_action = {o.action: o for o in feasible}
    if event.severity >= 0.7 and subject_hours is not None and subject_hours <= event.horizon_hours:
        chosen = by_action.get(REROUTE) or by_action.get(SLOW_STEAM) or problem.baseline
        note = "severe claim inside the horizon: reroute, else slow down"
    elif event.severity >= 0.4 and subject_hours is not None and subject_hours <= event.horizon_hours:
        chosen = by_action.get(SLOW_STEAM) or problem.baseline
        note = "moderate claim inside the horizon: slow down"
    else:
        chosen = problem.baseline
        note = "claim lapses before arrival, or a weak claim: proceed as planned"
    picks["heuristic"] = (chosen.option_id if chosen else None, _elapsed_ms(started), note)

    picks[INCUMBENT] = (problem.evidence.get("expectedBest"), 0.0, "the BALANCED expected-value ranking")
    picks[CANDIDATE] = _robust_pick(problem, truth=None)
    return picks


def _robust_pick(problem: DecisionProblem, *, truth: Optional[Dict[str, Any]]) -> Tuple[Optional[str], float, str]:
    """The robust policy's answer, with a WAIT simulated against the truth."""
    recommendation = problem.recommendation
    if recommendation is None:
        return None, 0.0, "no recommendation"
    kind = recommendation.kind
    if kind != WAIT_FOR_MORE_INFORMATION or truth is None:
        return recommendation.option_id, 0.0, f"the robust gate: {kind}"
    information = (recommendation.robustness or {}).get("information") or {}
    wait = float(information.get("reevaluateInHours") or 0.0)
    reopened = parse_instant(truth["reopenedAt"])
    clock = parse_instant(problem.at)
    if not recommendation.provisional_option_id:
        return problem.baseline_option_id, 0.0, f"the robust gate: WAIT {wait:.0f} h with no provisional option; kept the plan"
    if reopened <= clock + timedelta(hours=wait):
        return problem.baseline_option_id, 0.0, f"the robust gate: WAIT {wait:.0f} h; the closure had ended, kept the plan"
    return (recommendation.provisional_option_id, 0.0,
            f"the robust gate: WAIT {wait:.0f} h; the claim stood, took the provisional option")


def _mark(choice: Choice, problem: DecisionProblem, realised_baseline: Optional[float], kind: Optional[str]) -> None:
    choice.kind = kind
    choice.intervened = bool(choice.option_id) and choice.option_id != problem.baseline_option_id
    if choice.intervened and choice.delay is not None and realised_baseline is not None:
        choice.unnecessary = choice.delay >= realised_baseline - 1e-9


def run_vessel_case(seed: int, engine: DecisionEngine) -> CaseResult:
    from src.portwatch_os.world.branch import ObservedWorldState
    from src.portwatch_os.world.build import build_world, seed_for
    from src.portwatch_os.world.graph import EVENT, key
    from src.portwatch_os.world.live import Revision

    event, subject, truth, description = _vessel_case(seed)
    graph = build_world(events=[event], voyages=[subject], now=NOW)
    state = ObservedWorldState(state_id=f"bm-{seed}", revision=Revision("DEMO", None, "e", "f", 1), at=NOW,
                               graph=graph, traffic_mode="SIMULATED_TRAFFIC")
    started = time.perf_counter()
    try:
        problem = engine.solve_vessel(state, event_key=key(EVENT, event.event_id), seed=seed_for(event),
                                      vessel_id=subject.vessel_id, actor=DecisionActor(SHIPPING_COMPANY), at=NOW,
                                      decision_id=f"bm-vsl-{seed}")
    except Exception as exc:  # noqa: BLE001 - a case the engine refuses is recorded, not skipped
        return CaseResult(VESSEL, f"vessel-{seed}", seed, description, truth, 0, 0, None, None,
                          error=f"{type(exc).__name__}: {exc}")
    build_ms = _elapsed_ms(started)
    realised = _vessel_realised(problem, truth)
    scoreable = {oid: r for oid, r in realised.items() if r["feasible"]}
    best_id = min(scoreable, key=lambda oid: scoreable[oid]["delay"]) if scoreable else None
    best = scoreable[best_id]["delay"] if best_id else None
    result = CaseResult(VESSEL, f"vessel-{seed}", seed, description, truth, len(problem.options),
                        len(_feasible(problem)), best_id, best)
    picks = _vessel_policies(problem, event)
    picks[CANDIDATE] = _robust_pick(problem, truth=truth)
    baseline_row = realised.get(problem.baseline_option_id or "")
    kind = problem.recommendation.kind if problem.recommendation else None
    for policy, (option_id, ms, note) in picks.items():
        option = problem.option(option_id) if option_id else None
        choice = Choice(policy=policy, option_id=option_id,
                        decision_ms=ms + (build_ms if policy in (INCUMBENT, CANDIDATE) else 0.0),
                        note=note, fuel=_value(option, "fuel"))
        row = realised.get(option_id or "")
        if option is None or not option.feasible:
            # Choosing an infeasible option is a violation; the hull does what
            # it was already doing.
            choice.violations = 1
            row = realised.get(problem.baseline_option_id or "")
            choice.note += "; infeasible pick, scored as the baseline"
        if row is not None:
            choice.delay = row["delay"]
            choice.risk = row["caught"]
            choice.regret = None if best is None else round(max(0.0, row["delay"] - best), 1)
        else:
            choice.note += "; no realised figure under the stated model"
        _mark(choice, problem, None if baseline_row is None else baseline_row["delay"],
              kind if policy == CANDIDATE else None)
        result.choices[policy] = choice
    return result


# --------------------------------------------------------------------------
# PORT
# --------------------------------------------------------------------------


def _port_case(seed: int):
    """A berth plan for arrivals that bunch, and what the ships actually did."""
    from src.portwatch_os.twin.state import APPROACHING, VesselCall, WAITING, schematic_layout

    rng = random.Random(1000 + seed)
    port = rng.choice(["INMAA", "INNSA", "INCOK"])
    berths = rng.choice([2, 3])
    state = schematic_layout(port, berth_count=berths, capacity_index=round(rng.uniform(0.5, 0.85), 2))
    calls: List[VesselCall] = []
    count = rng.randint(3, 6)
    truth_calls: Dict[str, Dict[str, float]] = {}
    for index in range(count):
        eta = round(rng.uniform(-4.0, 6.0), 1)
        moves = rng.choice([220, 400, 800, 1400, 2400])
        committed = rng.random() < 0.4
        latest = round(eta + moves / 60.0 + rng.uniform(4.0, 18.0), 1) if committed else None
        waiting = eta <= 0
        calls.append(VesselCall(
            f"C-{seed}-{index}", f"V-{seed}-{index}", f"Call {index}", rng.choice(["panamax", "post-panamax", "feeder"]),
            round(rng.uniform(180.0, 330.0), 0), round(rng.uniform(9.0, 14.5), 1), eta, moves,
            latest_departure_hour=latest, state=WAITING if waiting else APPROACHING,
            arrived_hour=eta if waiting else None,
        ))
        # What actually happened: arrivals slip, work runs over or under.
        truth_calls[calls[-1].call_id] = {
            "etaHour": eta if waiting else round(eta + rng.gauss(1.0, 1.5), 1),
            "moves": int(moves * max(0.6, rng.gauss(1.08, 0.15))),
        }
    state.calls = calls
    description = f"{port}: {count} calls over {berths} berths, {sum(1 for c in calls if c.latest_departure_hour is not None)} with departure commitments"
    return state, truth_calls, description


def _true_port_state(state, truth_calls):
    import copy

    true = copy.deepcopy(state)
    for call in true.calls:
        facts = truth_calls[call.call_id]
        if call.arrived_hour is None:
            call.eta_hour = max(-12.0, facts["etaHour"])
        call.moves = facts["moves"]
    return true


def _port_policies(problem: DecisionProblem) -> Dict[str, Tuple[Optional[str], float, str]]:
    picks: Dict[str, Tuple[Optional[str], float, str]] = {}
    started = time.perf_counter()
    picks["current_plan"] = (problem.baseline_option_id, _elapsed_ms(started), "first come, first served")
    started = time.perf_counter()
    feasible = _feasible(problem)
    with_wait = [o for o in feasible if _value(o, "port_wait") is not None]
    greedy = min(with_wait, key=lambda o: _value(o, "port_wait")) if with_wait else None
    picks["greedy"] = (greedy.option_id if greedy else None, _elapsed_ms(started), "minimum predicted mean wait")
    started = time.perf_counter()
    by_action = {}
    for option in feasible:
        by_action.setdefault(option.action, option)
    chosen = by_action.get(PRIORITISE_VESSEL) or by_action.get(SHIFT_ARRIVAL_SLOT) or problem.baseline
    picks["heuristic"] = (chosen.option_id if chosen else None, _elapsed_ms(started),
                          "prioritise the earliest commitment, else stagger the bunch, else keep")
    picks[INCUMBENT] = (problem.evidence.get("expectedBest"), 0.0, "the BALANCED expected-value ranking")
    picks[CANDIDATE] = _robust_pick(problem, truth=None)
    return picks


def run_port_case(seed: int, engine: DecisionEngine) -> CaseResult:
    state, truth_calls, description = _port_case(seed)
    actor = DecisionActor(PORT_AUTHORITY, port_code=state.port_code)
    started = time.perf_counter()
    try:
        problem = engine.solve_port(state, actor=actor, at=NOW, world_state_id=f"bm-{seed}", world_revision={},
                                    horizon_hours=48.0, decision_id=f"bm-prt-{seed}")
    except Exception as exc:  # noqa: BLE001
        return CaseResult(PORT, f"port-{seed}", seed, description, {"calls": truth_calls}, 0, 0, None, None,
                          error=f"{type(exc).__name__}: {exc}")
    build_ms = _elapsed_ms(started)
    # The truth: the same plans, re-simulated on what the ships actually did.
    true_state = _true_port_state(state, truth_calls)
    realised_problem = engine.solve_port(true_state, actor=actor, at=NOW, world_state_id=f"bm-true-{seed}",
                                         world_revision={}, horizon_hours=48.0, decision_id=f"bm-prt-true-{seed}")
    realised = {o.option_id: o for o in realised_problem.options}
    scoreable = {oid: o for oid, o in realised.items() if o.feasible and _value(o, "port_wait") is not None}
    best_id = min(scoreable, key=lambda oid: _value(scoreable[oid], "port_wait")) if scoreable else None
    best = _value(scoreable[best_id], "port_wait") if best_id else None
    result = CaseResult(PORT, f"port-{seed}", seed, description, {"calls": truth_calls}, len(problem.options),
                        len(_feasible(problem)), best_id, best)
    baseline_actual = realised.get(problem.baseline_option_id or "")
    baseline_delay = None if baseline_actual is None else _value(baseline_actual, "port_wait")
    kind = problem.recommendation.kind if problem.recommendation else None
    for policy, (option_id, ms, note) in _port_policies(problem).items():
        choice = Choice(policy=policy, option_id=option_id,
                        decision_ms=ms + (build_ms if policy in (INCUMBENT, CANDIDATE) else 0.0), note=note)
        planned = problem.option(option_id) if option_id else None
        actual = realised.get(option_id or "")
        if planned is None or not planned.feasible or actual is None or not actual.feasible:
            choice.violations += 1
            actual = realised.get(problem.baseline_option_id or "")
            choice.note += "; infeasible pick, scored as first come first served"
        if actual is not None:
            choice.delay = _value(actual, "port_wait")
            missed = _value(actual, "missed_departures") or 0.0
            choice.violations += int(missed)
            choice.risk = 1.0 if missed else 0.0
            # Throughput proxy: berth utilisation over the horizon (the twin
            # reports no moves-completed metric on the option).
            choice.throughput = _value(actual, "berth_utilisation")
            choice.fuel = None
            choice.regret = None if best is None or choice.delay is None else round(max(0.0, choice.delay - best), 2)
        _mark(choice, problem, baseline_delay, kind if policy == CANDIDATE else None)
        result.choices[policy] = choice
    return result


# --------------------------------------------------------------------------
# CARGO
# --------------------------------------------------------------------------


def _cargo_case(seed: int):
    from src.portwatch_os.cargo.model import Shipment, StorageZone, VesselCapacity

    rng = random.Random(2000 + seed)
    port = rng.choice(["INMAA", "INNSA"])
    destination = rng.choice(["SGSIN", "AEJEA", "LKCMB", "MYPKG"])
    cargo_class = rng.choice(["dry", "dry", "dry", "reefer", "hazardous"])
    teu = rng.choice([2.0, 4.0, 8.0, 12.0])
    available = round(rng.uniform(1.0, 8.0), 1)
    booked_departure = round(available + rng.uniform(2.0, 10.0), 1)
    shipment = Shipment(
        shipment_id=f"BM-S-{seed}", teu=teu, cargo_class=cargo_class, destination_port=destination,
        inbound_vessel_id=f"IN-{seed}", booked_vessel_id=f"BM-OUT-{seed}-0", available_hour=available,
        latest_departure_hour=round(booked_departure + rng.uniform(6.0, 30.0), 1), yard_block_id="Z-FAR",
        weight_t=teu * rng.uniform(8.0, 22.0),
    )
    vessels = [VesselCapacity(
        vessel_id=f"BM-OUT-{seed}-0", name="Booked sailing", available_teu=rng.choice([0.0, 20.0, 200.0]),
        available_reefer_plugs=rng.choice([0, 4, 20]), accepts_hazardous=rng.random() < 0.6,
        accepts_oog=True, available_deadweight_t=5000.0, onward_ports=[destination], departure_hour=booked_departure,
    )]
    for index in range(1, rng.randint(2, 4)):
        vessels.append(VesselCapacity(
            vessel_id=f"BM-OUT-{seed}-{index}", name=f"Alternative {index}", available_teu=rng.choice([0.0, 30.0, 300.0]),
            available_reefer_plugs=rng.choice([0, 6, 30]), accepts_hazardous=rng.random() < 0.6, accepts_oog=True,
            available_deadweight_t=6000.0, onward_ports=[destination] if rng.random() < 0.8 else ["NLRTM"],
            departure_hour=round(booked_departure + rng.uniform(-3.0, 30.0), 1),
        ))
    zones = [
        StorageZone(zone_id="Z-FAR", name="Far yard", free_teu=400.0, capacity_teu=600.0, reefer_plugs_free=20,
                    accepts_hazardous=True, accepts_oog=True, quay_transfer_minutes_per_teu=2.4),
        StorageZone(zone_id="Z-NEAR", name="Quay-side zone", free_teu=rng.choice([0.0, 40.0]), capacity_teu=80.0,
                    reefer_plugs_free=rng.choice([0, 8]), accepts_hazardous=rng.random() < 0.5, accepts_oog=True,
                    quay_transfer_minutes_per_teu=0.8),
    ]
    # The truth: the discharge slips; each cut-off moves a little.
    truth = {
        "availableHour": round(available + max(0.0, rng.gauss(1.2, 1.4)), 1),
        "departures": {v.vessel_id: round(v.departure_hour + rng.gauss(0.0, 0.8), 1) for v in vessels},
    }
    description = (f"{port}: {teu:.0f} TEU {cargo_class} to {destination}, ready hour {available}, "
                   f"booked sailing hour {booked_departure}, {len(vessels) - 1} alternatives")
    return port, shipment, vessels, zones, truth, description


def _cargo_realised(shipment, vessels, zones, truth, options: Sequence[DecisionOption]) -> Dict[str, Dict[str, Any]]:
    """Each option re-evaluated on the true hours: delay to sailing, or the next sailing that works."""
    import copy

    from src.portwatch_os.cargo.model import evaluate_connection

    true_shipment = copy.deepcopy(shipment)
    true_shipment.available_hour = truth["availableHour"]
    true_vessels = []
    for vessel in vessels:
        moved = copy.deepcopy(vessel)
        moved.departure_hour = truth["departures"].get(vessel.vessel_id, vessel.departure_hour)
        true_vessels.append(moved)
    by_id = {v.vessel_id: v for v in true_vessels}
    zone_by_id = {z.zone_id: z for z in zones}
    realised: Dict[str, Dict[str, Any]] = {}
    for option in options:
        vessel = by_id.get(str(option.params.get("vesselId")))
        if vessel is None:
            continue
        zone = zone_by_id.get(option.params.get("zoneId") or "")
        connection = evaluate_connection(true_shipment, vessel, zone=zone, now_hour=0.0)
        if connection.feasible and vessel.departure_hour is not None:
            delay = max(0.0, vessel.departure_hour - truth["availableHour"])
            missed = 0
        else:
            # The box waits for the next sailing to the destination it fits on.
            later = sorted(
                (v for v in true_vessels if v.departure_hour is not None and v.vessel_id != vessel.vessel_id
                 and evaluate_connection(true_shipment, v, zone=zone, now_hour=0.0).feasible),
                key=lambda v: v.departure_hour,
            )
            if later:
                delay = max(0.0, later[0].departure_hour - truth["availableHour"])
            else:
                delay = 72.0  # no sailing in the case: a stated penalty, not a prediction
            missed = 1
        realised[option.option_id] = {"delay": round(delay, 1), "missed": missed, "feasible": option.feasible}
    return realised


def _cargo_policies(problem: DecisionProblem) -> Dict[str, Tuple[Optional[str], float, str]]:
    picks: Dict[str, Tuple[Optional[str], float, str]] = {}
    started = time.perf_counter()
    picks["current_plan"] = (problem.baseline_option_id, _elapsed_ms(started), "keep the booking")
    started = time.perf_counter()
    feasible = _feasible(problem)
    with_sailing = [o for o in feasible if _value(o, "sailing") is not None]
    greedy = min(with_sailing, key=lambda o: _value(o, "sailing")) if with_sailing else None
    picks["greedy"] = (greedy.option_id if greedy else None, _elapsed_ms(started), "earliest sailing")
    started = time.perf_counter()
    baseline = problem.baseline
    slack = _value(baseline, "slack")
    if baseline is not None and baseline.feasible and slack is not None and slack >= 2.0:
        chosen = baseline
        note = "the booking has slack: keep it"
    else:
        transfers = [o for o in feasible if o.action == TRANSFER_TO_VESSEL and _value(o, "slack") is not None]
        chosen = max(transfers, key=lambda o: _value(o, "slack")) if transfers else (baseline if baseline and baseline.feasible else None)
        note = "no slack: the most forgiving transfer"
    picks["heuristic"] = (chosen.option_id if chosen else None, _elapsed_ms(started), note)
    picks[INCUMBENT] = (problem.evidence.get("expectedBest"), 0.0, "the BALANCED expected-value ranking")
    picks[CANDIDATE] = _robust_pick(problem, truth=None)
    return picks


def run_cargo_case(seed: int, engine: DecisionEngine) -> CaseResult:
    port, shipment, vessels, zones, truth, description = _cargo_case(seed)
    actor = DecisionActor(SHIPPING_COMPANY)
    started = time.perf_counter()
    try:
        problem = engine.solve_cargo(shipment, vessels, zones, actor=actor, at=NOW, port_code=port,
                                     world_state_id=f"bm-{seed}", world_revision={}, decision_id=f"bm-cgo-{seed}")
    except Exception as exc:  # noqa: BLE001
        return CaseResult(CARGO, f"cargo-{seed}", seed, description, truth, 0, 0, None, None,
                          error=f"{type(exc).__name__}: {exc}")
    build_ms = _elapsed_ms(started)
    realised = _cargo_realised(shipment, vessels, zones, truth, problem.options)
    scoreable = {oid: r for oid, r in realised.items() if r["feasible"]}
    best_id = min(scoreable, key=lambda oid: scoreable[oid]["delay"]) if scoreable else None
    best = scoreable[best_id]["delay"] if best_id else None
    result = CaseResult(CARGO, f"cargo-{seed}", seed, description, truth, len(problem.options),
                        len(_feasible(problem)), best_id, best)
    baseline_row = realised.get(problem.baseline_option_id or "")
    kind = problem.recommendation.kind if problem.recommendation else None
    for policy, (option_id, ms, note) in _cargo_policies(problem).items():
        choice = Choice(policy=policy, option_id=option_id,
                        decision_ms=ms + (build_ms if policy in (INCUMBENT, CANDIDATE) else 0.0), note=note)
        option = problem.option(option_id) if option_id else None
        row = realised.get(option_id or "")
        if option is None or not option.feasible:
            choice.violations += 1
            row = realised.get(problem.baseline_option_id or "")
            choice.note += "; infeasible pick, scored as the booking"
        if row is not None:
            choice.delay = row["delay"]
            choice.violations += row["missed"]
            choice.risk = float(row["missed"])
            choice.regret = None if best is None else round(max(0.0, row["delay"] - best), 1)
        _mark(choice, problem, None if baseline_row is None else baseline_row["delay"],
              kind if policy == CANDIDATE else None)
        result.choices[policy] = choice
    return result


# --------------------------------------------------------------------------
# the suite
# --------------------------------------------------------------------------

RUNNERS: Dict[str, Callable[[int, DecisionEngine], CaseResult]] = {
    VESSEL: run_vessel_case, PORT: run_port_case, CARGO: run_cargo_case,
}


def run_suite(*, cases_per_domain: int = 40, base_seed: int = 1, domains: Sequence[str] = DOMAINS,
              engine: Optional[DecisionEngine] = None, corpus: Optional[str] = None) -> Dict[str, Any]:
    """Every case in every domain, the seeds fixed by the arguments alone.

    ``corpus`` names one of :data:`CORPORA` and overrides the seed range; the
    engine runs the robust policy so both PortWatch picks come from one build.
    """
    if corpus is not None:
        if corpus not in CORPORA:
            raise ValueError(f"{corpus!r} is not a corpus; one of {', '.join(CORPORA)}")
        base_seed, cases_per_domain = CORPORA[corpus]
    engine = engine or DecisionEngine(capacity=4096, policy=ROBUST_POLICY)
    results: List[CaseResult] = []
    for domain in domains:
        for index in range(cases_per_domain):
            results.append(RUNNERS[domain](base_seed + index, engine))
    return {
        "corpus": corpus, "casesPerDomain": cases_per_domain, "baseSeed": base_seed,
        "seedRange": [base_seed, base_seed + cases_per_domain - 1], "domains": list(domains),
        "policies": list(POLICIES), "incumbent": INCUMBENT, "candidate": CANDIDATE,
        "results": [r.to_dict() for r in results],
        "aggregate": aggregate(results),
        "losses": losses(results),
    }


def _mean(values: List[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    return None if not clean else round(statistics.mean(clean), 2)


def _median(values: List[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    return None if not clean else round(statistics.median(clean), 2)


def _percentile(values: List[Optional[float]], share: float) -> Optional[float]:
    """Nearest-rank percentile: the value at least ``share`` of the sample sits at or below."""
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    rank = max(1, math.ceil(share * len(clean)))
    return round(clean[rank - 1], 2)


def _max(values: List[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    return None if not clean else round(max(clean), 2)


def policy_summary(choices: List[Choice], *, best_option_ids: Optional[List[Optional[str]]] = None) -> Dict[str, Any]:
    """One policy's aggregate over a list of choices."""
    scored = [c for c in choices if c.delay is not None]
    intervened = [c for c in choices if c.intervened]
    return {
        "cases": len(choices),
        "meanDelay": _mean([c.delay for c in scored]),
        "meanRegret": _mean([c.regret for c in scored]),
        "medianRegret": _median([c.regret for c in scored]),
        "p90Regret": _percentile([c.regret for c in scored], 0.9),
        "worstRegret": _max([c.regret for c in scored]),
        "zeroRegretShare": None if not scored else round(sum(1 for c in scored if c.regret == 0) / len(scored), 3),
        "violations": sum(c.violations for c in choices),
        "meanRisk": _mean([c.risk for c in scored]),
        "meanFuel": _mean([c.fuel for c in choices]),
        "meanThroughput": _mean([c.throughput for c in scored]),
        "meanDecisionMs": _mean([c.decision_ms for c in choices]),
        "p95DecisionMs": _percentile([c.decision_ms for c in choices], 0.95),
        "interventionRate": None if not choices else round(len(intervened) / len(choices), 3),
        "unnecessaryInterventionRate": None if not intervened else round(
            sum(1 for c in intervened if c.unnecessary) / len(intervened), 3),
        "waitRate": None if not choices else round(
            sum(1 for c in choices if c.kind == WAIT_FOR_MORE_INFORMATION) / len(choices), 3),
        "kinds": {k: sum(1 for c in choices if c.kind == k) for k in sorted({c.kind for c in choices if c.kind})},
        "unscored": len(choices) - len(scored),
    }


def aggregate(results: List[CaseResult]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for domain in DOMAINS:
        rows = [r for r in results if r.domain == domain and r.error is None]
        errors = [r for r in results if r.domain == domain and r.error is not None]
        table: Dict[str, Any] = {"cases": len(rows), "errors": len(errors), "policies": {}}
        for policy in POLICIES:
            choices = [r.choices[policy] for r in rows if policy in r.choices]
            table["policies"][policy] = policy_summary(choices)
        # Where an intervention was the realised best, did the policy take one?
        cases_with_intervention_best = 0
        captured: Dict[str, int] = {p: 0 for p in POLICIES}
        for r in rows:
            base = r.choices.get("current_plan")
            if base is None or base.delay is None or r.best_delay is None:
                continue
            if base.delay > r.best_delay + 1e-9:
                cases_with_intervention_best += 1
                for policy in POLICIES:
                    c = r.choices.get(policy)
                    if c is not None and c.intervened and c.delay is not None and c.delay < base.delay - 1e-9:
                        captured[policy] += 1
        table["interventionWasBest"] = cases_with_intervention_best
        table["beneficialInterventionCapture"] = {
            p: (None if not cases_with_intervention_best else round(captured[p] / cases_with_intervention_best, 3))
            for p in POLICIES
        }
        # Head to head on the cases both policies scored, for each PortWatch policy.
        head: Dict[str, Any] = {}
        for mine_policy in (INCUMBENT, CANDIDATE):
            head[mine_policy] = {}
            for policy in [p for p in POLICIES if p != mine_policy]:
                wins = losses_ = ties = 0
                for r in rows:
                    a, b = r.choices.get(mine_policy), r.choices.get(policy)
                    if a is None or b is None or a.delay is None or b.delay is None:
                        continue
                    if a.delay < b.delay - 1e-9:
                        wins += 1
                    elif a.delay > b.delay + 1e-9:
                        losses_ += 1
                    else:
                        ties += 1
                head[mine_policy][policy] = {"wins": wins, "loses": losses_, "ties": ties}
        table["headToHead"] = head
        out[domain] = table
    return out


def losses(results: List[CaseResult], policy: str = CANDIDATE) -> List[Dict[str, Any]]:
    """Every case where some other policy realised a lower delay than ``policy``."""
    out: List[Dict[str, Any]] = []
    for r in results:
        if r.error is not None:
            continue
        mine = r.choices.get(policy)
        if mine is None or mine.delay is None:
            continue
        beaten_by = {p: c.delay for p, c in r.choices.items()
                     if p != policy and c.delay is not None and c.delay < mine.delay - 1e-9}
        if beaten_by:
            out.append({"domain": r.domain, "caseId": r.case_id, "description": r.description,
                        "policy": policy,
                        "portwatch": {"optionId": mine.option_id, "delay": mine.delay, "regret": mine.regret,
                                      "kind": mine.kind},
                        "beatenBy": {p: {"delay": d, "optionId": r.choices[p].option_id} for p, d in beaten_by.items()},
                        "truth": r.truth})
    return out


__all__ = [
    "CANDIDATE", "CARGO", "CORPORA", "Choice", "CaseResult", "DOMAINS", "INCUMBENT", "METRICS", "POLICIES",
    "PORT", "VESSEL", "aggregate", "losses", "policy_summary", "run_cargo_case", "run_port_case", "run_suite",
    "run_vessel_case",
]
