"""Vessel routing decisions: what one exposed hull could still do, each option
simulated on its own branch of the observed world.

The question is the one a fleet operator asks when the Red Sea escalates:
*keep going, go round, or wait?* The answer here is not a score. It is a
baseline and a handful of alternatives, each a scenario branch with the
action applied, each run back through the World State Engine so that the
consequence of the choice -- at the strait, at the destination quay, in the
yard, on the cargo -- is computed by the same rules as the exposure that
raised the question.

What is computed, and from what:

*   **Residual risk** is read from the event's cascade at the instant the
    option reaches the threatened water. An option that reaches it after the
    claim lapses carries no modelled exposure and says so; an option that
    never reaches it carries none by construction.
*   **ETA shift** comes from route geometry and the hull's own speed. The
    baseline's shift is the engine's expected value -- the detour weighted by
    the risk -- because doing nothing is not free of consequence; a chosen
    diversion's shift is certain.
*   **Port and yard consequence** is the destination's arrival bunching with
    this hull's contribution replaced by the option's, propagated through the
    engine's yard-pressure and cost derivations.
*   **Weather** is the marine grid sampled where and when the option's passage
    runs, with the coverage it achieved.
*   **Fuel** is a relative index from a stated hull-agnostic law; tonnes and
    money need a basis and are unknown without one.

Nothing here is a default. Where the world does not hold what a measure needs,
the measure says so and the option is compared on what is known.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.decision.actions import (
    CATALOGUE,
    CHANGE_DESTINATION_PORT,
    KEEP_PLAN,
    REROUTE,
    SLOW_STEAM,
    SPEED_UP,
    availability_of,
    for_domain,
    ADVISING_ACTORS, EXECUTING_ACTOR, executing_actor_for,
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
    INSUFFICIENT_DATA,
    Measure,
    OBJECTIVES,
    REJECTED,
    UNAVAILABLE,
    VESSEL_ROUTING,
    known,
    unknown,
)
from src.portwatch_os.decision.routing import (
    ROUTE_DISCLAIMER,
    VoyageRoutes,
    length_nm,
    routes_for,
)
from src.portwatch_os.finance.basis import CostBasis
from src.portwatch_os.finance.evaluate import KNOWN as KNOWN_STATE, Pricer
from src.portwatch_os.finance.money import DAY, FxTable, HOUR, Quantity as MoneyQuantity, TONNE
from src.portwatch_os.global_eye.exposure import TRADE_LANES
from src.portwatch_os.world.branch import (
    Assumption,
    BranchRegistry,
    DETACH_VESSEL,
    DIVERT_VESSEL,
    ObservedWorldState,
    REBIND_DESTINATION,
    RETIME_VESSEL,
    ScenarioBranch,
)
from src.portwatch_os.world.cascade import Cascade, propagate
from src.portwatch_os.world.graph import CARGO, EVENT, PORT, SAILS, THREATENS, VESSEL, WorldGraph, key
from src.portwatch_os.world.quantity import HOURS, INR, RATIO, RISK, TEU, Quantity, utc
from src.portwatch_os.world.route_exposure import ROUGH_M, VERY_HEAVY_M, sample_route

#: The speed envelope the product will evaluate, matching the Critic's.
SPEED_FLOOR_KN = 6.0
SPEED_CEILING_KN = 24.0
#: A slow-steam below this fraction of service speed is a hold, not a passage.
SLOW_STEAM_FLOOR_FRACTION = 0.5
#: How far above service speed a "speed up" may run.
SPEED_UP_FACTOR = 1.10
#: Margin after a claim lapses before a held hull proceeds.
HOLD_MARGIN_HOURS = 2.0
#: An option that closes sooner than this is not offered.
MINIMUM_WINDOW_HOURS = 0.5
#: Route weather coverage below which the weather measure is unknown.
MIN_WEATHER_COVERAGE = 0.3
#: Objectives a vessel problem measures, in display order.
VESSEL_OBJECTIVES: Tuple[str, ...] = (
    "eta", "risk", "weather", "wave_hours", "distance", "fuel", "yard_pressure",
    "missed_connection", "cost", "emissions", "uncertainty",
)
#: The subset the frontier is drawn over by default.
FRONTIER_OBJECTIVES: Tuple[str, ...] = ("eta", "risk", "fuel")


class VesselDecisionError(ValueError):
    """The world does not hold what a routing decision for this hull needs."""


@dataclass
class VesselContext:
    """Everything about the subject the option builders read."""

    vessel_id: str
    label: str
    lane_code: str
    destination_port: str
    speed_kn: float
    hours_to_chokepoint: Dict[str, float]
    exposure: Quantity
    chokepoint: str
    already_entered: bool
    hours_to_risk: Optional[float]
    event_key: str
    event_label: str
    event_end: Optional[datetime]
    routes: VoyageRoutes
    observed: bool
    attrs: Dict[str, Any]
    #: "chokepoint" when the exposure is a strait on the lane; "port_closure"
    #: when it is the destination itself that cannot receive the hull.
    risk_kind: str = "chokepoint"
    #: Ports the same event acts on directly, so a diversion never lands in one.
    threatened_ports: Tuple[str, ...] = ()
    #: When the claim began: the closure's start for the outcome model.
    event_start: Optional[datetime] = None

    @property
    def claim_remaining_hours(self) -> Optional[float]:
        return None if self.event_end is None or self._at is None else max(
            0.0, (self.event_end - self._at).total_seconds() / 3600.0
        )

    _at: Optional[datetime] = None


# --------------------------------------------------------------------------
# reading the subject
# --------------------------------------------------------------------------


def _exposure_of(cascade: Cascade, vessel_id: str) -> Optional[Quantity]:
    reached = cascade.reached.get(key(VESSEL, vessel_id))
    return None if reached is None else reached.quantities.get(RISK)


def context_for(
    state: ObservedWorldState,
    *,
    event_key: str,
    seed: Quantity,
    vessel_id: str,
    at: datetime,
) -> VesselContext:
    graph = state.graph
    node = graph.node(key(VESSEL, vessel_id))
    if node is None:
        raise VesselDecisionError(f"{vessel_id} is not a vessel in this world")
    event = graph.node(event_key)
    if event is None:
        raise VesselDecisionError(f"{event_key} is not in this world")
    cascade = propagate(graph, event_key, seed, at=at)
    exposure = _exposure_of(cascade, vessel_id)
    if exposure is None:
        raise VesselDecisionError(
            f"{node.label} is not reached by {event.label} at {at.isoformat()}; there is "
            "no routing decision to make from this event"
        )
    lane_code = node.attrs.get("lane_code")
    destination = node.attrs.get("destination_port")
    if not lane_code or not destination:
        raise VesselDecisionError(f"{node.label} declares no lane or destination")
    timings: Dict[str, float] = {}
    for edge in graph.in_edges(key(VESSEL, vessel_id), kind=SAILS):
        timings.update({k: float(v) for k, v in (edge.attrs.get("hours_to_chokepoint") or {}).items()
                        if v is not None})
    speed = float(node.attrs.get("service_speed_kn") or 12.0)
    position = None
    if node.attrs.get("lat") is not None and node.attrs.get("lon") is not None:
        position = (float(node.attrs["lat"]), float(node.attrs["lon"]))
    routes = routes_for(lane_code, destination, timings, speed, position=position)
    if routes is None:
        raise VesselDecisionError(f"{node.label} cannot be placed on {lane_code}")
    closure = bool(exposure.attrs.get("closure"))
    threatened = tuple(
        e.dst.split(":", 1)[-1] for e in graph.out_edges(event_key) if e.kind == THREATENS and e.dst.startswith("port:")
    )
    context = VesselContext(
        vessel_id=vessel_id, label=node.label, lane_code=lane_code, destination_port=destination,
        speed_kn=speed, hours_to_chokepoint=timings, exposure=exposure,
        chokepoint=str(exposure.attrs.get("chokepoint") or exposure.attrs.get("port") or ""),
        already_entered=bool(exposure.attrs.get("already_entered")),
        hours_to_risk=exposure.attrs.get("hours_to_risk_area"),
        event_key=event_key, event_label=event.label, event_end=event.interval.end,
        routes=routes, observed=node.attrs.get("source") == "OBSERVED_AIS", attrs=dict(node.attrs),
        risk_kind="port_closure" if closure else "chokepoint", threatened_ports=threatened,
        event_start=event.interval.start,
    )
    context._at = at
    return context


# --------------------------------------------------------------------------
# availability
# --------------------------------------------------------------------------


def _availability_checks(context: VesselContext):
    def reroute(subject: Dict[str, Any]) -> Availability:
        if context.risk_kind == "port_closure":
            return Availability(UNAVAILABLE, f"the closure is at {context.chokepoint} itself; a different "
                                "routing still arrives into it")
        if context.already_entered:
            return Availability(UNAVAILABLE, f"{context.label} is already inside {context.chokepoint}; "
                                "no diversion is left to take")
        if not context.routes.alternative_reachable:
            return Availability(UNAVAILABLE, context.routes.alternative_reason)
        return Availability(AVAILABLE)

    def slow(subject: Dict[str, Any]) -> Availability:
        if context.already_entered:
            return Availability(UNAVAILABLE, f"{context.label} is already inside {context.chokepoint}; "
                                "holding clear is no longer possible")
        remaining = context.claim_remaining_hours
        if remaining is None:
            return Availability(INSUFFICIENT_DATA, "the event declares no claim horizon, so there is "
                                "no instant to hold until")
        hours = context.hours_to_risk
        if hours is None:
            return Availability(INSUFFICIENT_DATA, f"{context.label} declares no timing at {context.chokepoint}")
        if hours >= remaining:
            return Availability(UNAVAILABLE, f"{context.label} reaches {context.chokepoint} in {hours:.0f} h, "
                                f"after the claim lapses ({remaining:.0f} h); there is nothing to hold for")
        return Availability(AVAILABLE)

    def change_port(subject: Dict[str, Any]) -> Availability:
        lane = TRADE_LANES.get(context.lane_code)
        others = [p for p in (lane.india_ports if lane else ())
                  if p != context.destination_port and p not in context.threatened_ports]
        if not others:
            if context.threatened_ports:
                return Availability(UNAVAILABLE, f"every other port {context.lane_code} serves is under the "
                                    "same event")
            return Availability(UNAVAILABLE, f"{context.lane_code} serves no other Indian port")
        return Availability(AVAILABLE)

    return {REROUTE: reroute, SPEED_UP: reroute, SLOW_STEAM: slow, CHANGE_DESTINATION_PORT: change_port}


def _subject_dict(context: VesselContext) -> Dict[str, Any]:
    lane = TRADE_LANES.get(context.lane_code)
    return {
        "lane_code": context.lane_code,
        "alternative": lane.alternative if lane else None,
        "hours_to_chokepoint": context.hours_to_chokepoint,
        "service_speed_kn": context.speed_kn,
        "event_end": None if context.event_end is None else context.event_end.isoformat(),
        "destination_port": context.destination_port,
        "eta": context.attrs.get("eta"),
        # Underway, so no departure to delay; not declared, so not offered.
        "departure_port": None,
        "departure_at": None,
        "onward_ports": None,
        "cargo_manifest": None,
        "bunker_state": None,
        "bunker_ports": None,
    }


# --------------------------------------------------------------------------
# option plans
# --------------------------------------------------------------------------


@dataclass
class OptionPlan:
    """What an option does, before it is simulated."""

    action: str
    label: str
    params: Dict[str, Any]
    assumptions: List[Assumption]
    #: Speed the passage runs at.
    speed_kn: float
    #: The passage ahead of the hull under this option, as (lat, lon).
    geometry: List[Tuple[float, float]]
    #: Hours until the option reaches the threatened chokepoint, or None if never.
    hours_to_chokepoint: Optional[float]
    #: Hours the option adds to arrival against the current plan.
    delay_hours: Optional[float]
    delay_basis: str
    delay_certain: bool
    #: Hours until the option stops being available; None when it never does.
    closes_in_hours: Optional[float]
    destination_port: str
    is_baseline: bool = False
    hold_hours: float = 0.0
    notes: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.notes is None:
            self.notes = []


#: Hull attributes an operator may supply for a scenario when the hull does
#: not declare them, with the unit each is read in.
ASSUMABLE_ATTRIBUTES: Dict[str, str] = {"grt": "grt"}


def _plans(context: VesselContext, actor: str) -> Tuple[List[OptionPlan], List[Dict[str, Any]]]:
    """Every action in the catalogue, as a plan or as a reasoned absence.

    An advising actor -- a port authority, national command -- gets the
    options the executing actor would get, each marked as reaching the hull
    only through an advisory. It does not get an empty problem: the
    consequences are the same whoever is looking, and what differs is who can
    act on them.
    """
    subject = _subject_dict(context)
    checks = _availability_checks(context)
    executing = executing_actor_for(actor)
    routes = context.routes
    speed = context.speed_kn
    primary_nm = routes.remaining_primary_nm
    primary_hours = primary_nm / max(1.0, speed)
    commit_hours = _commit_hours(context)

    plans: List[OptionPlan] = []
    catalogue_rows: List[Dict[str, Any]] = []
    for spec in for_domain(VESSEL_ROUTING):
        availability = availability_of(spec, subject, actor=executing, checks=checks)
        catalogue_rows.append({
            **spec.to_dict(), "availability": availability.to_dict(),
            "evaluatedFor": executing,
            "requiresAdvisory": executing != actor,
        })
        if not availability.available:
            continue

        if spec.kind == KEEP_PLAN:
            plans.append(OptionPlan(
                action=KEEP_PLAN, label="Continue current plan", params={"speedKn": round(speed, 1)},
                assumptions=[], speed_kn=speed, geometry=list(routes.remaining_primary),
                hours_to_chokepoint=context.hours_to_risk, delay_hours=None,
                delay_basis="expected", delay_certain=False, closes_in_hours=None,
                destination_port=context.destination_port, is_baseline=True,
            ))
        elif spec.kind == REROUTE and routes.alternative is not None:
            alt_nm = routes.alternative_nm or 0.0
            plans.append(OptionPlan(
                action=REROUTE, label=f"Divert via {TRADE_LANES[context.lane_code].alternative}",
                params={"speedKn": round(speed, 1), "alternativeNm": round(alt_nm, 0)},
                assumptions=[Assumption(DIVERT_VESSEL, context.vessel_id,
                                        note="takes the lane's alternative routing")],
                speed_kn=speed, geometry=list(routes.alternative), hours_to_chokepoint=None,
                delay_hours=alt_nm / max(1.0, speed) - primary_hours,
                delay_basis="alternative passage at service speed minus remaining primary passage "
                            "(route geometry)",
                delay_certain=True, closes_in_hours=commit_hours,
                destination_port=context.destination_port,
            ))
        elif spec.kind == SPEED_UP and routes.alternative is not None:
            faster = min(SPEED_CEILING_KN, speed * SPEED_UP_FACTOR)
            alt_nm = routes.alternative_nm or 0.0
            plans.append(OptionPlan(
                action=SPEED_UP,
                label=f"Divert via {TRADE_LANES[context.lane_code].alternative} at {faster:.1f} kn",
                params={"speedKn": round(faster, 1), "alternativeNm": round(alt_nm, 0)},
                assumptions=[
                    Assumption(DIVERT_VESSEL, context.vessel_id, note="takes the lane's alternative routing"),
                    Assumption(RETIME_VESSEL, context.vessel_id, value=faster,
                               note=f"runs at {faster:.1f} kn"),
                ],
                speed_kn=faster, geometry=list(routes.alternative), hours_to_chokepoint=None,
                delay_hours=alt_nm / faster - primary_hours,
                delay_basis="alternative passage at increased speed minus remaining primary passage "
                            "(route geometry)",
                delay_certain=True, closes_in_hours=commit_hours,
                destination_port=context.destination_port,
            ))
        elif spec.kind == SLOW_STEAM:
            remaining = context.claim_remaining_hours or 0.0
            hours = context.hours_to_risk or 0.0
            hold = max(0.0, remaining + HOLD_MARGIN_HOURS - hours)
            # The declared timing is hours at service speed, so the distance to
            # the strait is hours x speed and the required speed follows.
            required = speed * hours / max(0.1, hours + hold)
            floor = max(SPEED_FLOOR_KN, speed * SLOW_STEAM_FLOOR_FRACTION)
            notes: List[str] = []
            if required < floor:
                assumptions = [Assumption(DETACH_VESSEL, context.vessel_id,
                                          note=f"holds clear of {context.chokepoint} for {hold:.0f} h")]
                run_speed = floor
                notes.append(f"the required {required:.1f} kn is below the {floor:.1f} kn floor; "
                             f"modelled as steaming at {floor:.1f} kn and holding clear")
                label = f"Slow to {floor:.1f} kn and hold clear of {context.chokepoint}"
            else:
                assumptions = [Assumption(RETIME_VESSEL, context.vessel_id, value=required,
                                          note=f"slows to {required:.1f} kn until the claim lapses")]
                run_speed = required
                label = f"Slow steam to {required:.1f} kn until the claim lapses"
            plans.append(OptionPlan(
                action=SLOW_STEAM, label=label,
                params={"speedKn": round(run_speed, 1), "holdHours": round(hold, 1),
                        "claimLapsesInHours": round(remaining, 1)},
                assumptions=assumptions, speed_kn=run_speed, geometry=list(routes.remaining_primary),
                hours_to_chokepoint=hours + hold, delay_hours=hold,
                delay_basis="hold until the event's claim lapses, plus a margin",
                delay_certain=True, closes_in_hours=hours, destination_port=context.destination_port,
                hold_hours=hold, notes=notes,
            ))
        elif spec.kind == CHANGE_DESTINATION_PORT:
            lane = TRADE_LANES[context.lane_code]
            for port_code in [p for p in lane.india_ports
                              if p != context.destination_port and p not in context.threatened_ports][:2]:
                alt_routes = routes_for(context.lane_code, port_code, context.hours_to_chokepoint,
                                        speed, position=routes.position)
                if alt_routes is None:
                    continue
                delta_hours = alt_routes.remaining_primary_nm / max(1.0, speed) - primary_hours
                plans.append(OptionPlan(
                    action=CHANGE_DESTINATION_PORT, label=f"Land at {port_code} instead",
                    params={"portCode": port_code, "speedKn": round(speed, 1)},
                    assumptions=[Assumption(REBIND_DESTINATION, context.vessel_id, target=port_code,
                                            note=f"lands at {port_code}")],
                    speed_kn=speed, geometry=list(alt_routes.remaining_primary),
                    hours_to_chokepoint=context.hours_to_risk, delay_hours=delta_hours,
                    delay_basis="passage to the alternative port minus passage to the planned port "
                                "(route geometry); the chokepoint is still transited",
                    delay_certain=True, closes_in_hours=None, destination_port=port_code,
                ))
    return plans, catalogue_rows


def _commit_hours(context: VesselContext) -> Optional[float]:
    """Hours until the alternative routing can no longer be taken."""
    routes = context.routes
    if not routes.alternative_reachable:
        return None
    lane = TRADE_LANES.get(context.lane_code)
    # The commit anchor is the first chokepoint the lane transits for the Suez
    # lanes and the branch point for the Malacca lanes; both are expressed as
    # the hull's own timing at the first strait ahead.
    ahead = sorted(h for h in context.hours_to_chokepoint.values() if h is not None and h > 0)
    if lane is None or not ahead:
        return None
    return max(0.0, ahead[0] - 1.0)


def _distance_to_chokepoint(context: VesselContext) -> Optional[float]:
    along = context.routes.chokepoint_nm.get(context.chokepoint)
    if along is None:
        return None
    return max(0.0, along - context.routes.position_nm)


# --------------------------------------------------------------------------
# constraints
# --------------------------------------------------------------------------


def _constraints(plan: OptionPlan, context: VesselContext, weather_max_m: Optional[float]) -> List[ConstraintResult]:
    results: List[ConstraintResult] = []
    speed = plan.speed_kn
    results.append(ConstraintResult(
        "speed_envelope", "Speed within envelope",
        SPEED_FLOOR_KN <= speed <= SPEED_CEILING_KN,
        True, f"{speed:.1f} kn against {SPEED_FLOOR_KN:.0f}-{SPEED_CEILING_KN:.0f} kn",
        basis="src.portwatch_os.decision.vessel.SPEED_FLOOR_KN/SPEED_CEILING_KN",
    ))
    if plan.action in (REROUTE, SPEED_UP):
        results.append(ConstraintResult(
            "route_topology", "Alternative routing reachable", context.routes.alternative_reachable, True,
            context.routes.alternative_reason or "the alternative branches ahead of the hull",
            basis="src.portwatch_os.decision.routing (commit anchor)",
        ))
    if plan.action in (REROUTE, SPEED_UP, SLOW_STEAM):
        results.append(ConstraintResult(
            "not_committed", "Not yet inside the exposed water", not context.already_entered, True,
            f"{context.label} is {'already inside' if context.already_entered else 'short of'} {context.chokepoint}",
            basis=f"cascade {context.event_key}: lane_reaches_vessel",
        ))
    if plan.closes_in_hours is not None:
        results.append(ConstraintResult(
            "decision_window", "Decision window open", plan.closes_in_hours >= MINIMUM_WINDOW_HOURS, True,
            f"closes in {plan.closes_in_hours:.1f} h against a {MINIMUM_WINDOW_HOURS:.1f} h minimum",
            basis="hull timing at the commit point",
        ))
    if weather_max_m is not None:
        results.append(ConstraintResult(
            "weather_safety", "Weather below the safety threshold", weather_max_m < VERY_HEAVY_M, True,
            f"worst sampled significant wave {weather_max_m:.1f} m against {VERY_HEAVY_M:.0f} m",
            basis="src.portwatch_os.world.route_exposure.sample_route",
        ))
    else:
        results.append(ConstraintResult(
            "weather_safety", "Weather below the safety threshold", True, False,
            "not checked: no marine coverage of the passage", basis="marine grid",
        ))
    results.append(ConstraintResult(
        "berth_draught", "Berth and draught compatibility", True, False,
        "not checked: the world graph holds no berth data for the destination",
        basis="world graph",
    ))
    return results


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------


def _others_port_hours(state: ObservedWorldState, context: VesselContext, seed: Quantity, at: datetime) -> Dict[str, Quantity]:
    """Arrival shift at each port from every *other* exposed hull.

    Computed once on a copy with the subject detached, so each option can add
    its own contribution without counting the subject twice.
    """
    from src.portwatch_os.world.branch import branch as fork

    detached = fork(state, [Assumption(DETACH_VESSEL, context.vessel_id, note="others-only cascade")],
                    branch_id="others", now=at)
    cascade = propagate(detached.graph, context.event_key, seed, at=at)
    out: Dict[str, Quantity] = {}
    for reached in cascade.by_kind(PORT):
        hours = reached.quantities.get(HOURS)
        if hours is not None:
            out[reached.node.key] = hours
    return out


def _weather(plan: OptionPlan, at: datetime, grid: Any) -> Tuple[Measure, Measure, Optional[float], List[Dict[str, Any]]]:
    if grid is None:
        return (unknown("m", "no marine forecast grid is available to this deployment"),
                unknown("hours", "no marine forecast grid is available to this deployment"), None, [])
    if len(plan.geometry) < 2:
        return (unknown("m", "the option has no passage to sample"),
                unknown("hours", "the option has no passage to sample"), None, [])
    profile = sample_route(plan.geometry, grid=grid, departs_at=at, speed_kn=plan.speed_kn)
    marks = [
        {"kind": "weather", "subject": "rough seas", "hours": round((s.eta - at).total_seconds() / 3600.0, 1),
         "waveM": s.wave_m}
        for s in profile.covered if s.wave_m is not None and s.wave_m >= ROUGH_M
    ][:6]
    if profile.coverage < MIN_WEATHER_COVERAGE:
        because = (f"the marine grid covers {profile.coverage:.0%} of the passage, below the "
                   f"{MIN_WEATHER_COVERAGE:.0%} needed to state a figure")
        return unknown("m", because, coverage=round(profile.coverage, 3)), unknown("hours", because), None, marks
    worst = profile.max_wave
    wave = known(worst.wave_m if worst and worst.wave_m is not None else 0.0, "m",
                 basis="route_exposure.sample_route: worst sampled significant wave height",
                 confidence=profile.confidence, coverage=round(profile.coverage, 3),
                 flags=profile.flags)
    rough = known(profile.hours_above(ROUGH_M), "hours",
                  basis=f"route_exposure.sample_route: hours above {ROUGH_M} m",
                  confidence=profile.confidence, coverage=round(profile.coverage, 3))
    return wave, rough, (worst.wave_m if worst else None), marks


def _fuel_index(plan: OptionPlan, context: VesselContext) -> Measure:
    """Burn relative to the plan: distance ratio times the square of the speed ratio.

    From the propeller law (power ∝ v³, so burn per mile ∝ v²). Hull-agnostic
    and stated as such; it ranks options, it does not price them.
    """
    base_nm = context.routes.remaining_primary_nm
    base_speed = context.speed_kn
    if base_nm <= 0:
        return unknown("index", "no remaining passage to compare against")
    distance = length_nm(plan.geometry)
    if plan.action == SLOW_STEAM:
        choke = _distance_to_chokepoint(context) or 0.0
        rest = max(0.0, base_nm - choke)
        index = (choke / base_nm) * (plan.speed_kn / base_speed) ** 2 + rest / base_nm
    else:
        index = (distance / base_nm) * (plan.speed_kn / base_speed) ** 2
    return known(index, "index", basis="propeller law: burn per nm ∝ speed²; hull-agnostic",
                 confidence=0.5, distanceNm=round(distance, 0), speedKn=round(plan.speed_kn, 1))


def _price(
    plan: OptionPlan, context: VesselContext, measures: Dict[str, Measure], *,
    basis: CostBasis, fx: FxTable, currency: str, at: datetime,
) -> Dict[str, Any]:
    vessel_status = "foreign" if not str(context.lane_code).startswith("COAST") else "coastal"
    grt = context.attrs.get("grt")
    grt_assumed = bool(context.attrs.get("grt_assumed"))
    pricer = Pricer(basis, at=at, currency=currency, fx=fx, scope=plan.destination_port,
                    vessel_status=vessel_status, vessel_type="container")
    eta = measures.get("eta")
    delay_q = None if eta is None or not eta.available else MoneyQuantity(max(0.0, eta.value), HOUR)
    components = [
        pricer.priced("delay", "Cost of delay", "charter_day", delay_q, driver="eta",
                      zero_because="the option adds no time against the current plan"),
    ]
    # Fuel difference: (index - 1) x baseline burn x price. Needs a burn figure
    # and a bunker price; the index alone is a ratio and prices nothing.
    fuel = measures.get("fuel")
    if fuel is None or not fuel.available:
        components.append(pricer.unknown("fuel", "Fuel difference", "the fuel index could not be computed"))
    else:
        burn = basis.lookup("fuel_burn_t_day", at=at, scope=context.attrs.get("vessel_class") or "*")
        if burn.rate is None:
            components.append(pricer.unknown("fuel", "Fuel difference", burn.reason, driver="fuel"))
        else:
            base_days = context.routes.remaining_primary_nm / max(1.0, context.speed_kn) / 24.0
            tonnes = (fuel.value - 1.0) * burn.rate.value * base_days
            components.append(pricer.priced("fuel", "Fuel difference", "bunker_price_t",
                                            MoneyQuantity(tonnes, TONNE), driver="fuel",
                                            zero_because="the option burns the same fuel as the plan"))
    if plan.action in (REROUTE, SPEED_UP):
        components.append(pricer.unknown("action", "Cost of action",
                                         "no canal-transit toll basis is configured, so the toll the "
                                         "diversion avoids cannot be netted"))
    else:
        components.append(pricer.zero("action", "Cost of action", "the option incurs no direct charge"))
    # One entry's dues at the destination. Alongside hours are a port decision,
    # not a routing one, so berth hire is not priced here.
    components.append(_port_dues(pricer, plan, grt, assumed=grt_assumed))
    missed = measures.get("missed_connection")
    if missed is None or not missed.available:
        components.append(pricer.unknown("cargo", "Cargo impact",
                                         None if missed is None else missed.unknown_because or "no consignment linked"))
    else:
        components.append(pricer.priced("cargo", "Cargo impact", "missed_connection_teu",
                                        MoneyQuantity(missed.value, "teu"), driver="missed_connection",
                                        zero_because="no consignment misses its connection"))
    return pricer.evaluation(components).to_dict()


def _port_dues(pricer: Pricer, plan: OptionPlan, grt: Optional[float], *, assumed: bool = False):
    """Port dues for one entry at the option's destination, per GRT.

    A tonnage the operator assumed prices against the real tariff, but the
    component is an assumption all the same: the rate is public, the hull it
    is applied to is not.
    """
    from src.portwatch_os.finance.money import CALL

    if grt is None:
        return pricer.unknown("port", "Port dues at destination",
                              "the hull declares no gross tonnage, so per-GRT dues cannot be computed; "
                              "supply one as a scenario assumption", driver="destination")
    # One entry: the tariff's tonnage arithmetic prices the hull, the quantity
    # is the single call it makes.
    component = pricer.priced("port", "Port dues at destination", "port_dues_grt",
                              MoneyQuantity(1.0, CALL), driver="destination",
                              scope=plan.destination_port, grt=float(grt))
    if assumed and component.state == KNOWN_STATE:
        component.is_assumption = True
        component.basis = f"{component.basis} · GT {float(grt):,.0f} assumed by the operator"
    return component


def evaluate_plan(
    plan: OptionPlan,
    context: VesselContext,
    state: ObservedWorldState,
    *,
    seed: Quantity,
    at: datetime,
    registry: BranchRegistry,
    others_hours: Dict[str, Quantity],
    grid: Any,
    basis: CostBasis,
    fx: FxTable,
    currency: str,
) -> Tuple[DecisionOption, ScenarioBranch]:
    """One plan, simulated on its own branch."""
    forked = registry.create(state, plan.assumptions, now=at)
    forked.actions.append({"action": plan.action, "params": plan.params, "label": plan.label})
    measures: Dict[str, Measure] = {}
    notes: List[str] = list(plan.notes)

    # -- residual risk at the strait, at the instant the option reaches it --
    if plan.hours_to_chokepoint is None:
        risk = known(0.0, "risk", basis="the alternative routing transits no threatened chokepoint",
                     confidence=0.9, chokepoint=context.chokepoint)
    else:
        arrival = at + timedelta(hours=plan.hours_to_chokepoint)
        cascade = propagate(forked.graph, context.event_key, seed, at=arrival)
        exposure = _exposure_of(cascade, context.vessel_id)
        lapsed = context.event_end is not None and arrival > context.event_end
        if exposure is None:
            because = ("the claim lapses before the hull arrives; persistence beyond the claim "
                       "horizon is not modelled") if lapsed else "the cascade does not reach the hull at arrival"
            risk = known(0.0, "risk", basis=f"cascade {context.event_key} at {arrival.isoformat()}",
                         confidence=round(seed.confidence * 0.5, 3), note=because,
                         arrivalAfterClaimHorizon=lapsed, chokepoint=context.chokepoint)
            notes.append(because)
        else:
            risk = known(exposure.value, "risk", basis=f"cascade {context.event_key} at {arrival.isoformat()}",
                         confidence=exposure.confidence, chokepoint=context.chokepoint,
                         arrivalAfterClaimHorizon=False)
    measures["risk"] = risk

    # -- ETA shift ---------------------------------------------------------
    if plan.is_baseline:
        # What doing nothing costs in time: if the strait is closed when the
        # hull arrives, it holds until the claim lapses or diverts from there,
        # whichever is shorter, and that is weighted by how likely the closure
        # is at arrival. An expected value, and labelled as one.
        remaining = context.claim_remaining_hours
        hold = None if remaining is None else max(0.0, remaining + HOLD_MARGIN_HOURS - (context.hours_to_risk or 0.0))
        detour_hours = (
            context.routes.detour_nm / max(1.0, context.speed_kn)
            if context.risk_kind == "chokepoint" and context.routes.alternative_reachable
            and context.routes.detour_nm is not None else None
        )
        candidates = [h for h in (hold, detour_hours) if h is not None]
        if not candidates:
            eta = unknown("hours", "no alternative routing and no claim horizon: the holding time "
                          "under a closure cannot be bounded")
        else:
            response_hours = min(candidates)
            how = "holding until the claim lapses" if response_hours == hold else "diverting from the strait"
            eta = known(risk.value * response_hours, "hours",
                        basis=f"risk at arrival × {response_hours:.0f} h ({how}); the expected arrival "
                              "shift under the event",
                        confidence=round((risk.confidence or 0.5) * 0.8, 3), expected=True,
                        responseHours=round(response_hours, 1), response=how,
                        holdHours=None if hold is None else round(hold, 1),
                        detourHours=None if detour_hours is None else round(detour_hours, 1))
    elif plan.action == CHANGE_DESTINATION_PORT:
        # Arriving earlier at a port the cargo was not booked to is not an
        # earlier arrival for the cargo. Until onward carriage is modelled the
        # ETA objective is unknown here; the passage difference is carried as
        # detail so a reader can still see it.
        eta = unknown("hours", f"arrival at {plan.destination_port} is {plan.delay_hours:+.0f} h against "
                      f"the passage to {context.destination_port}, but delivery of consignments booked "
                      f"to {context.destination_port} from there is not modelled",
                      arrivalShiftAtAlternative=round(plan.delay_hours or 0.0, 1))
    else:
        eta = known(plan.delay_hours or 0.0, "hours", basis=plan.delay_basis,
                    confidence=0.8 if plan.delay_certain else 0.6, certain=plan.delay_certain)
    measures["eta"] = eta

    # -- distance and fuel -------------------------------------------------
    distance = length_nm(plan.geometry)
    measures["distance"] = known(distance, "nm", basis="route geometry (non-navigational)", confidence=0.8)
    measures["fuel"] = _fuel_index(plan, context)
    if measures["fuel"].available:
        measures["emissions"] = known(measures["fuel"].value, "index",
                                      basis="proportional to fuel burn", confidence=0.5)
    else:
        measures["emissions"] = unknown("index", measures["fuel"].unknown_because or "fuel index unknown")

    # -- weather -----------------------------------------------------------
    wave, rough, worst_m, weather_marks = _weather(plan, at, grid)
    measures["weather"] = wave
    measures["wave_hours"] = rough

    # -- constraints -------------------------------------------------------
    constraints = _constraints(plan, context, worst_m)
    forked.constraint_results = [c.to_dict() for c in constraints]
    rejected = [c for c in constraints if c.hard and not c.passed]

    # -- port and cargo consequence through the world engine ------------------
    consequences: List[Dict[str, Any]] = []
    port_key = key(PORT, plan.destination_port)
    own_delay = eta.value if eta.available else None
    if plan.action == CHANGE_DESTINATION_PORT:
        own_delay = 0.0
        notes.append(f"an additional call at {plan.destination_port} is not modelled as arrival bunching; "
                     "the port twin's berth decision evaluates it as an arrival")
    if own_delay is not None and own_delay > 0 and forked.graph.node(port_key) is not None:
        seeded = Quantity(own_delay, HOURS, confidence=eta.confidence or 0.5,
                          attrs={"option": plan.action, "certain": plan.delay_certain})
        own = propagate(forked.graph, key(VESSEL, context.vessel_id), seeded, at=at)
        others = others_hours.get(port_key)
        landed = own.reached.get(port_key)
        own_hours = None if landed is None else landed.quantities.get(HOURS)
        total = own_hours if others is None else (others if own_hours is None else others.combined_with(own_hours))
        if total is not None:
            aggregate = propagate(forked.graph, port_key, total, at=at)
            port_reached = aggregate.reached.get(port_key)
            pressure = None if port_reached is None else port_reached.quantities.get(RATIO)
            money = None if port_reached is None else port_reached.quantities.get(INR)
            measures["yard_pressure"] = (
                known(pressure.value, "ratio", basis="arrival_shift_becomes_pressure on the aggregate shift",
                      confidence=pressure.confidence, aggregateHours=round(total.value, 1),
                      ownHours=round(own_delay, 1), othersHours=None if others is None else round(others.value, 1))
                if pressure is not None else
                unknown("ratio", next((n for n in aggregate.notes if "capacity" in n),
                                      f"{plan.destination_port} yields no pressure figure"))
            )
            consequences.append({
                "node": port_key, "kind": PORT, "label": forked.graph.node(port_key).label,
                "quantities": {
                    "hours": total.to_dict(),
                    **({"ratio": pressure.to_dict()} if pressure else {}),
                    **({"inr": money.to_dict()} if money else {}),
                },
                "steps": [s.to_dict() for s in own.steps] + [s.to_dict() for s in aggregate.steps],
                "notes": own.notes + aggregate.notes,
            })
        for reached in own.by_kind(CARGO):
            teu = reached.quantities.get(TEU)
            consequences.append({"node": reached.node.key, "kind": CARGO, "label": reached.node.label,
                                 "quantities": {u: q.to_dict() for u, q in reached.quantities.items()}})
            if teu is not None:
                measures["missed_connection"] = known(teu.value, "teu", basis="delay_reaches_cargo",
                                                      confidence=teu.confidence)
    elif own_delay is not None and own_delay <= 0:
        others = others_hours.get(port_key)
        if others is not None and forked.graph.node(port_key) is not None:
            aggregate = propagate(forked.graph, port_key, others, at=at)
            port_reached = aggregate.reached.get(port_key)
            pressure = None if port_reached is None else port_reached.quantities.get(RATIO)
            if pressure is not None:
                measures["yard_pressure"] = known(pressure.value, "ratio",
                                                  basis="arrival_shift_becomes_pressure on other hulls' shift",
                                                  confidence=pressure.confidence,
                                                  aggregateHours=round(others.value, 1), ownHours=0.0)
    if "yard_pressure" not in measures:
        measures["yard_pressure"] = unknown(
            "ratio", "no arrival shift lands at the destination under this option, or the port "
                     "declares no capacity index")
    if "missed_connection" not in measures:
        measures["missed_connection"] = unknown(
            "teu",
            f"consignments booked to {context.destination_port} would need onward carriage from "
            f"{plan.destination_port}; not modelled"
            if plan.action == CHANGE_DESTINATION_PORT else
            "no consignment is linked to this hull in the world graph",
        )

    # -- money -------------------------------------------------------------
    financial = _price(plan, context, measures, basis=basis, fx=fx, currency=currency, at=at)
    if financial.get("total") is not None:
        measures["cost"] = known(financial["total"]["amount"], "money", basis="finance.evaluate.Pricer",
                                 confidence=0.5 if financial.get("assumption") else 0.8,
                                 currency=financial["total"]["currency"],
                                 label=financial.get("label"))
    else:
        measures["cost"] = unknown("money", "; ".join(u["reason"] for u in financial.get("unknown", [])) or
                                   "no cost basis")

    # -- uncertainty -------------------------------------------------------
    # Over the objectives the frontier is drawn on, so an option that could
    # not be measured on one of them does not look *more* certain for having
    # fewer numbers. Unknown there is unknown here.
    core = [measures.get(k) for k in FRONTIER_OBJECTIVES]
    if any(m is None or not m.available for m in core):
        missing = [k for k, m in zip(FRONTIER_OBJECTIVES, core) if m is None or not m.available]
        measures["uncertainty"] = unknown("ratio", f"not measured on {', '.join(missing)}")
    else:
        confidences = [m.confidence for m in core if m.confidence is not None]
        measures["uncertainty"] = known(1.0 - min(confidences) if confidences else 1.0, "ratio",
                                        basis="one minus the weakest confidence among the frontier objectives",
                                        confidence=1.0)

    evaluation = DecisionEvaluation(
        objectives=measures, consequences=consequences,
        derived={
            "speedKn": round(plan.speed_kn, 1),
            "destinationPort": plan.destination_port,
            "hoursToChokepoint": None if plan.hours_to_chokepoint is None else round(plan.hours_to_chokepoint, 1),
            "holdHours": round(plan.hold_hours, 1),
            "distanceNm": round(distance, 0),
            "arrivalInHours": round(distance / max(1.0, plan.speed_kn) + plan.hold_hours, 1),
        },
        financial=financial, branch_id=forked.branch_id, notes=notes,
        computed_at=utc().isoformat(timespec="seconds"),
    )
    forked.derived = dict(evaluation.derived)
    forked.consequences = consequences
    forked.metrics = {k: m.to_dict() for k, m in measures.items()}
    forked.provenance = {"routes": context.routes.sources, "disclaimer": ROUTE_DISCLAIMER,
                         "event": context.event_key, "marine": "grid" if grid is not None else None}

    timeline = [
        {"kind": "arrival", "subject": plan.destination_port, "hours": evaluation.derived["arrivalInHours"]},
    ]
    if plan.hours_to_chokepoint is not None:
        timeline.append({"kind": "chokepoint", "subject": context.chokepoint,
                         "hours": round(plan.hours_to_chokepoint, 1)})
    if plan.closes_in_hours is not None:
        timeline.append({"kind": "deadline", "subject": plan.action, "hours": round(plan.closes_in_hours, 1)})
    if context.claim_remaining_hours is not None:
        timeline.append({"kind": "claim_lapses", "subject": context.event_label,
                         "hours": round(context.claim_remaining_hours, 1)})
    timeline.extend(weather_marks)

    option = DecisionOption(
        option_id=f"{plan.action.lower()}" + (f"-{plan.params['portCode']}" if plan.action == CHANGE_DESTINATION_PORT else ""),
        action=plan.action, label=plan.label, actor="", params=plan.params,
        constraints=constraints, status=REJECTED if rejected else FEASIBLE,
        evaluation=evaluation if not rejected else None, is_baseline=plan.is_baseline,
        assumptions=[a.to_dict() for a in plan.assumptions],
        provenance={"branchId": forked.branch_id, "routeSources": context.routes.sources,
                    "disclaimer": ROUTE_DISCLAIMER, "closesInHours": plan.closes_in_hours},
        geometry=[[round(p[0], 4), round(p[1], 4)] for p in plan.geometry], timeline=timeline,
    )
    if rejected:
        option.provenance["rejectedEvaluation"] = evaluation.to_dict()
    return option, forked


# --------------------------------------------------------------------------
# the problem
# --------------------------------------------------------------------------


def build_vessel_problem(
    state: ObservedWorldState,
    *,
    decision_id: str,
    event_key: str,
    seed: Quantity,
    vessel_id: str,
    actor: DecisionActor,
    at: datetime,
    registry: BranchRegistry,
    basis: CostBasis,
    fx: Optional[FxTable] = None,
    currency: str = "USD",
    grid: Any = None,
    attention_item_id: Optional[str] = None,
    attribute_assumptions: Optional[Dict[str, float]] = None,
) -> DecisionProblem:
    """Every option this actor has for this hull, evaluated. Not yet ranked.

    ``attribute_assumptions`` are figures the hull does not declare and the
    operator supplies for this scenario -- its gross tonnage, say. They are
    applied to the context, marked as assumed, and listed in the evidence;
    nothing priced on them leaves the ASSUMPTION label behind.
    """
    context = context_for(state, event_key=event_key, seed=seed, vessel_id=vessel_id, at=at)
    assumed_attrs: Dict[str, float] = {}
    for name, value in (attribute_assumptions or {}).items():
        if name not in ASSUMABLE_ATTRIBUTES:
            raise VesselDecisionError(f"{name!r} is not an attribute an operator may assume for a hull")
        if context.attrs.get(name) is not None:
            continue  # the hull declares it; the declaration wins
        context.attrs[name] = float(value)
        context.attrs[f"{name}_assumed"] = True
        assumed_attrs[name] = float(value)
    plans, catalogue_rows = _plans(context, actor.role)
    if not any(p.is_baseline for p in plans):
        raise VesselDecisionError(f"{actor.role} holds no baseline action for a vessel routing decision")
    others = _others_port_hours(state, context, seed, at)
    table = fx if fx is not None else FxTable()

    executing = executing_actor_for(actor.role)
    options: List[DecisionOption] = []
    for plan in plans:
        option, _branch = evaluate_plan(
            plan, context, state, seed=seed, at=at, registry=registry, others_hours=others,
            grid=grid, basis=basis, fx=table, currency=currency,
        )
        option.actor = executing
        options.append(option)

    baseline = next(o for o in options if o.is_baseline)
    windows = [o.provenance.get("closesInHours") for o in options
               if o.feasible and not o.is_baseline and o.provenance.get("closesInHours") is not None]
    window = min(windows) if windows else context.hours_to_risk
    deadline = None if window is None else (at + timedelta(hours=window)).isoformat()

    exposure = context.exposure
    problem = DecisionProblem(
        decision_id=decision_id,
        created_at=utc().isoformat(timespec="seconds"),
        domain=VESSEL_ROUTING,
        world_revision={
            "mode": state.revision.mode, "eventsStamp": state.revision.events_stamp[:48],
            "fleetStamp": state.revision.fleet_stamp[:48],
            "observedGeneration": state.revision.observed_generation,
            "fingerprint": state.revision.fingerprint,
        },
        world_state_id=state.state_id,
        subject_type=VESSEL, subject_id=vessel_id, subject_label=context.label,
        actor=actor, attention_item_id=attention_item_id, cascade_id=event_key,
        decision_deadline=deadline, decision_window_hours=window, at=at.isoformat(),
        objectives=[OBJECTIVES[k] for k in VESSEL_OBJECTIVES],
        hard_constraints=["speed_envelope", "route_topology", "not_committed", "decision_window",
                          "weather_safety"],
        soft_constraints=["berth_draught"],
        available_actions=catalogue_rows,
        baseline_option_id=baseline.option_id,
        options=options,
        evidence={
            "subject": {
                "source": context.attrs.get("source"),
                "observedAt": context.attrs.get("observed_at"),
                "placementConfidence": context.attrs.get("placement_confidence"),
                "identityConflicts": context.attrs.get("identity_conflicts", 0),
                "mmsi": context.attrs.get("mmsi"),
                "canonicalId": context.attrs.get("canonical_id"),
            },
            "event": {"key": event_key, "label": context.event_label,
                      "claimFrom": None if context.event_start is None else context.event_start.isoformat(),
                      "claimLapsesAt": None if context.event_end is None else context.event_end.isoformat(),
                      "claimRemainingHours": (None if context.claim_remaining_hours is None
                                              else round(context.claim_remaining_hours, 1)),
                      "seed": seed.to_dict()},
            "exposure": exposure.to_dict(),
            # What the robust policy needs to stress the claim: the kind of
            # closure and where the hull meets it.
            "closureModel": {"riskKind": context.risk_kind, "at": context.chokepoint,
                             "hoursToRisk": None if context.hours_to_risk is None else round(context.hours_to_risk, 1),
                             "alreadyEntered": context.already_entered},
            "routes": context.routes.to_dict(),
            "position": {"lat": round(context.routes.position[0], 4), "lon": round(context.routes.position[1], 4),
                         "basis": context.routes.position_basis, "observed": context.observed},
            "othersPortHours": {k: q.to_dict() for k, q in others.items()},
            "marine": {"available": grid is not None},
            "costBasis": basis.coverage(at=at, scope=context.destination_port),
            "fx": table.to_dict(),
            "frontierObjectives": list(FRONTIER_OBJECTIVES),
            "execution": {
                "by": executing, "requestedBy": actor.role,
                "mechanism": "ISSUE_ADVISORY" if executing != actor.role else "OWN_ACTION",
            },
            "attributeAssumptions": {
                name: {"value": value, "label": "ASSUMPTION", "unit": ASSUMABLE_ATTRIBUTES[name]}
                for name, value in assumed_attrs.items()
            },
        },
        headline=f"{context.label} · {context.event_label}",
        do_nothing_statement=_do_nothing(baseline, context),
    )
    if executing != actor.role:
        problem.notes.append(
            f"{actor.role} cannot execute a routing change; the recommendation reaches "
            f"{context.label} as an advisory to {executing}"
        )
    problems = problem.validate()
    if problems:
        raise VesselDecisionError("; ".join(problems))
    return problem


def _do_nothing(baseline: DecisionOption, context: VesselContext) -> str:
    eta = baseline.measure("eta")
    risk = baseline.measure("risk")
    parts = []
    if eta is not None and eta.available:
        parts.append(f"+{eta.value:.0f} h expected arrival shift")
    if risk is not None and risk.available:
        parts.append(f"exposure {risk.value:.2f} at {context.chokepoint}")
    if context.hours_to_risk is not None and not context.already_entered:
        verb = "arrives at" if context.risk_kind == "port_closure" else "enters"
        parts.append(f"{verb} {context.chokepoint} in {context.hours_to_risk:.0f} h")
    return "If unchanged: " + ", ".join(parts) if parts else "If unchanged: no computed consequence"


__all__ = [
    "FRONTIER_OBJECTIVES",
    "HOLD_MARGIN_HOURS",
    "MINIMUM_WINDOW_HOURS",
    "MIN_WEATHER_COVERAGE",
    "OptionPlan",
    "SLOW_STEAM_FLOOR_FRACTION",
    "SPEED_CEILING_KN",
    "SPEED_FLOOR_KN",
    "SPEED_UP_FACTOR",
    "VESSEL_OBJECTIVES",
    "VesselContext",
    "VesselDecisionError",
    "build_vessel_problem",
    "context_for",
    "evaluate_plan",
]
