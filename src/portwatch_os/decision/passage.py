"""Declared remaining-passage adapter for the existing hourly arrival decision.

This enumerates supported catalogue actions, not a second route optimiser.
All positions, speed envelopes and consumption are operator demo assumptions.
The existing frontier, Critic and approval ledger still choose/carry the plan.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

from .actions import CATALOGUE, KEEP_PLAN, SLOW_STEAM, SPEED_UP, DELAY_DEPARTURE, DELAY_ARRIVAL
from .model import (ConstraintResult, DecisionEvaluation, DecisionObjective, DecisionOption,
                    FEASIBLE, REJECTED, known, unknown)
from .routing import length_nm, sailing_hours, ROUTE_DISCLAIMER
from .vessel import relative_passage_fuel_index, SPEED_FLOOR_KN, SPEED_CEILING_KN
from src.portwatch_os.intelligence.current_environment import finite, instant

VERSION = "declared-passage-v1"


def _time(value, label):
    if not isinstance(value, str):
        raise ValueError(label + " must be a UTC/offset timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise ValueError(label + " must include a valid timezone") from None


def _number(value, label, low, high):
    if not finite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be finite and between {low} and {high}")
    return float(value)


def validate_plan(raw, *, at, voyage_eta):
    if not isinstance(raw, dict) or type(raw.get("schemaVersion")) is not int or raw.get("schemaVersion") != 1:
        raise ValueError("Declare passage schemaVersion 1")
    plan = deepcopy(raw)
    # Refuse non-JSON/nonfinite assumptions before any identity is frozen.
    try:
        json.dumps(plan, allow_nan=False)
    except (ValueError, TypeError):
        raise ValueError("Passage assumptions must contain finite JSON values") from None
    reference = _time(plan.get("referenceAt"), "Passage reference")
    declared = _time(plan.get("declaredAt"), "Declaration time")
    if declared > at or at - declared > timedelta(hours=1):
        raise ValueError("Passage declaration must have been made within the last hour")
    kind = plan.get("referenceKind")
    if kind == "AT_SEA":
        if reference > at or at - reference > timedelta(hours=1):
            raise ValueError("At-sea reference must be a present-position declaration within the last hour")
    elif kind == "NOT_DEPARTED":
        if reference < at or reference > at + timedelta(hours=72):
            raise ValueError("Undeparted reference must be a declared future departure within 72 hours")
    else:
        raise ValueError("Declare whether the vessel is AT_SEA or NOT_DEPARTED")
    for field in ("referenceLabel", "distanceBasis"):
        if not isinstance(plan.get(field), str) or not plan[field].strip():
            raise ValueError(field + " is required; demo positions/distance are assumptions, not observed AIS")
    distance = _number(plan.get("remainingDistanceNm"), "Remaining distance nm", .01, 20000)
    low = _number(plan.get("minSpeedKn"), "Declared minimum speed kn", SPEED_FLOOR_KN, SPEED_CEILING_KN)
    high = _number(plan.get("maxSpeedKn"), "Declared maximum speed kn", low, SPEED_CEILING_KN)
    speed = _number(plan.get("baselineSpeedKn"), "Baseline speed kn", low, high)
    baseline_arrival = reference + timedelta(hours=sailing_hours(distance, speed))
    declared_arrival = _time(plan.get("baselineArrivalAt", voyage_eta), "Baseline arrival")
    if abs((baseline_arrival - declared_arrival).total_seconds()) > 60 or abs((declared_arrival - instant(voyage_eta)).total_seconds()) > 60:
        raise ValueError("Contradictory distance, baseline speed, reference or voyage ETA (over one minute); correct the declaration")
    if kind == "AT_SEA" and distance <= (at-reference).total_seconds()/3600*speed:
        raise ValueError("Declared passage has already elapsed under its baseline; a new position and remaining distance are required")
    if plan.get("deadlineAt"):
        _time(plan["deadlineAt"], "Approach deadline")
    geometry = plan.get("geometry")
    if geometry is not None:
        if not isinstance(geometry, list) or not 2 <= len(geometry) <= 1000 or any(
            not isinstance(p, list) or len(p) != 2 or not finite(p[0]) or not finite(p[1])
            or not -90 <= p[0] <= 90 or not -180 <= p[1] <= 180 for p in geometry
        ):
            raise ValueError("Geometry must be finite [latitude, longitude] points")
        measured = length_nm(geometry)
        if abs(measured - distance) > max(1., distance * .01):
            raise ValueError("Declared distance contradicts the supplied polyline length by more than 1% or 1 nm")
    return plan, reference, baseline_arrival


def approach_gate(hourly, arrival, requested, gust_limit, visibility_limit):
    """Find the first supported two-hour gate at this option's own arrival.

    Coverage gaps/missing variables before that gate make it unknown. A later
    clear row cannot establish what happened during a missing earlier hour.
    """
    start = max(arrival, requested)
    rows = sorted((deepcopy(r) for r in hourly if instant(r["validAt"]) >= start),
                  key=lambda r: instant(r["validAt"]))
    first_hour = start.replace(minute=0, second=0, microsecond=0)
    if first_hour < start:
        first_hour += timedelta(hours=1)
    if len(rows) < 2 or instant(rows[0]["validAt"]) != first_hour:
        return None, [], "Arrival lies outside supported hourly forecast coverage"
    consumed = []
    for i, row in enumerate(rows):
        if instant(row["validAt"]) - start > timedelta(hours=48):
            break
        if i and instant(row["validAt"]) - instant(rows[i-1]["validAt"]) != timedelta(hours=1):
            return None, consumed, "Hourly coverage has a gap or duplicate before a supported approach gate"
        consumed.append(row)
        if not finite(row.get("wind_gusts_10m")) or not finite(row.get("visibility")):
            return None, consumed, "Gust or visibility is missing before the approach can be evaluated"
        if i and all(r["wind_gusts_10m"] <= gust_limit and r["visibility"] >= visibility_limit
                     for r in (rows[i-1], row)):
            return instant(rows[i-1]["validAt"]), consumed, None
    return None, consumed, "No supported two-hour clear gate within 48 hours of this option's arrival"


def _identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def extend_arrival_problem(problem, raw_plan, data, *, at):
    """Replace only this new comparison's arrival-only options when supported.

    Invalid declarations leave the old bounded comparison usable, with an
    explicit rejected speed/departure basis. No old ledger record is migrated.
    """
    from .passage_finance import evaluate_passage_finance, passage_finance_deltas
    env = problem.evidence["currentEnvironment"]
    received = _time(env.get("availableAt"), "Hourly forecast availability")
    if received > at or at - received > timedelta(hours=1):
        raise ValueError("A current hourly receipt within the last hour is required; future or expired receipts cannot drive passage planning")
    try:
        plan, reference, baseline_arrival = validate_plan(raw_plan, at=at, voyage_eta=env["earliestVoyageArrival"])
    except ValueError as exc:
        problem.evidence["passagePlanningUnavailable"] = {
            "version": VERSION, "reason": str(exc), "fallback": "ARRIVAL_WINDOW_ONLY",
            "meaning": "Requested time change alone does not establish a physical sailing plan"}
        problem.available_actions.extend([{**CATALOGUE[a].to_dict(), "availability": {
            "status": "INSUFFICIENT_DATA", "reason": str(exc)}} for a in (SLOW_STEAM, SPEED_UP, DELAY_DEPARTURE)])
        problem.notes.append("Physical passage planning unavailable: " + str(exc))
        return problem
    requested = instant(env["plannedArrival"])
    common_hours = (at-reference).total_seconds()/3600 if plan["referenceKind"] == "AT_SEA" else 0.
    common_distance = common_hours * plan["baselineSpeedKn"]
    remaining_distance = plan["remainingDistanceNm"] - common_distance
    input_hash = _identity({"plan": plan, "snapshot": env["snapshotId"], "requested": env["plannedArrival"],
                            "assumptions": env["assumptions"], "calculationAt": at.isoformat()})
    basis_hash = input_hash[:20]
    candidates = [(KEEP_PLAN, "Continue current passage plan", plan["baselineSpeedKn"], 0.)]
    unavailable = {}
    alternative = plan.get("alternativeSpeedKn")
    if finite(alternative) and .1 <= alternative <= 100 and alternative != plan["baselineSpeedKn"]:
        action = SLOW_STEAM if alternative < plan["baselineSpeedKn"] else SPEED_UP
        candidates.append((action, f"Propose {alternative:g} kn on the declared passage", alternative, 0.))
    else:
        action = None
    for speed_action in (SLOW_STEAM, SPEED_UP):
        if speed_action != action:
            unavailable[speed_action] = "No distinct finite alternative speed within the calculation range (0.1–100 kn) supplied for this action"
    delay = plan.get("departureDelayHours")
    if plan["referenceKind"] == "AT_SEA":
        unavailable[DELAY_DEPARTURE] = "Vessel is already at sea; its original departure cannot be delayed"
    elif plan.get("departureHoldPermitted") is not True or not isinstance(plan.get("departureHoldLocation"), str) or not plan["departureHoldLocation"].strip():
        unavailable[DELAY_DEPARTURE] = "A declared permitted departure holding location is required"
    elif not finite(delay) or not 0 < delay <= 72:
        unavailable[DELAY_DEPARTURE] = "Declare a departure delay above zero and at most 72 hours"
    else:
        candidates.append((DELAY_DEPARTURE, f"Propose departure {delay:g} h later", plan["baselineSpeedKn"], delay))
    unavailable[DELAY_ARRIVAL] = "A requested window alone is not a physical passage option; select a supported speed or departure plan"
    options, summaries, financials, fuels = [], [], [], []
    deadline = _time(plan["deadlineAt"], "Approach deadline") if plan.get("deadlineAt") else None
    baseline_clear = None
    for action, label, speed, hold in candidates:
        baseline = action == KEEP_PLAN
        option_id = "passage-" + action.lower() + "-" + basis_hash
        departure = reference + timedelta(hours=hold)
        future_sailing = sailing_hours(remaining_distance, speed)
        sailing = common_hours + future_sailing
        arrival = departure + timedelta(hours=sailing)
        clear_at, consumed, missing = approach_gate(data["hourly"], arrival, requested,
            env["assumptions"]["maxGustKn"], env["assumptions"]["minVisibilityM"])
        if baseline:
            baseline_clear = clear_at
        wait = None if clear_at is None else (clear_at - arrival).total_seconds()/3600
        requested_wait = max(0., (requested-arrival).total_seconds()/3600)
        forecast_wait = None if wait is None else wait-requested_wait
        elapsed = None if clear_at is None else (clear_at-reference).total_seconds()/3600
        shift = None if clear_at is None or baseline_clear is None else (clear_at-baseline_clear).total_seconds()/3600
        met = None if deadline is None or clear_at is None else clear_at <= deadline
        envelope = plan["minSpeedKn"] <= speed <= plan["maxSpeedKn"]
        constraints = [ConstraintResult("speed_envelope", "Declared operating speed envelope", envelope, True,
            f"{speed:g} kn against declared {plan['minSpeedKn']:g}–{plan['maxSpeedKn']:g} kn",
            "currentEnvironment.passagePlan"), ConstraintResult("hourly_approach_coverage", "Hourly approach coverage",
            clear_at is not None, True, missing or "Each option uses its own approach hours; not whole-route safety",
            "passageComparison.options[].consumedForecasts")]
        if deadline is not None:
            constraints.append(ConstraintResult("approach_deadline", "Declared latest clear approach", met is True, True,
                f"Clear approach {clear_at.isoformat() if clear_at else 'unknown'}; deadline {deadline.isoformat()}",
                "currentEnvironment.passagePlan.deadlineAt"))
        status = REJECTED if not envelope or met is False or missing else FEASIBLE
        reason = "; ".join(c.detail for c in constraints if not c.passed) or None
        finance, fuel = evaluate_passage_finance(plan.get("finance") or {}, sailing_hours=sailing,
            speed_kn=speed, anchorage_hours=wait, departure_hold_hours=hold, at=reference,
            port_code=env["portCode"], calculation_at=at,
            sailing_segments=[{"hours": common_hours, "speedKn": plan["baselineSpeedKn"]},
                              {"hours": future_sailing, "speedKn": speed}])
        financials.append(finance); fuels.append(fuel)
        fuel_measure = known(fuel["totalTonnes"], "tonne", basis="Declared propulsion relation plus separately modeled active modes; assumption", confidence=None) if fuel.get("available") else unknown("tonne", "; ".join(fuel.get("missingInputs", [])) or "Declared complete consumption basis unavailable")
        derived = {"destinationPort": env["portCode"], "arrivalAt": arrival.isoformat(),
            "approachClearAt": None if clear_at is None else clear_at.isoformat(),
            "arrivalShiftHours": (arrival-baseline_arrival).total_seconds()/3600,
            "holdHours": hold, "departureAt": departure.isoformat(), "speedKn": speed,
            "sailingHours": sailing, "anchorageWaitHours": wait, "totalElapsedHours": elapsed,
            "commonElapsedSailingHours": common_hours, "futureSailingHours": future_sailing,
            "speedChangeAt": (at if plan["referenceKind"] == "AT_SEA" else departure).isoformat(),
            "requestedWindowWaitHours": requested_wait, "forecastGateWaitHours": forecast_wait,
            "scheduleShiftHours": shift, "deadlineMet": met, "passagePlanVersion": VERSION,
            "propulsionIndex": common_distance/plan["remainingDistanceNm"] + relative_passage_fuel_index(remaining_distance, speed,
                plan["remainingDistanceNm"], plan["baselineSpeedKn"]),
            "propulsionIndexMeaning": "Hull-agnostic propulsion index only; excludes auxiliary and holding; not tonnes or savings"}
        timeline = [{"at": reference.isoformat(), "hours": 0., "subject": problem.subject_id,
            "kind": "position" if plan["referenceKind"] == "AT_SEA" else "departure_reference", "label": plan["referenceLabel"]},
            {"at": departure.isoformat(), "hours": hold, "subject": problem.subject_id,
             "kind": "departure", "label": "Remaining sailing starts"},
            {"at": arrival.isoformat(), "hours": hold+sailing, "subject": problem.subject_id,
             "kind": "arrival", "label": "Physical approach arrival"}]
        if common_hours:
            timeline.append({"at": at.isoformat(), "hours": common_hours, "subject": problem.subject_id,
                "kind": "position", "label": "Assumed speed choice starts now; elapsed sailing is unchanged"})
        if clear_at is not None:
            timeline.append({"at": clear_at.isoformat(), "hours": elapsed, "subject": problem.subject_id,
                "kind": "weather", "label": "Conditional forecast-clear approach"})
        if deadline is not None:
            timeline.append({"at": deadline.isoformat(), "hours": (deadline-reference).total_seconds()/3600,
                "subject": problem.subject_id, "kind": "deadline", "label": "Declared approach deadline"})
        summary = {"optionId": option_id, "label": label, "status": status, "reason": reason,
            **{k: derived[k] for k in ("speedKn", "departureAt", "arrivalAt", "approachClearAt", "sailingHours",
                "anchorageWaitHours", "requestedWindowWaitHours", "forecastGateWaitHours", "totalElapsedHours", "scheduleShiftHours", "deadlineMet", "commonElapsedSailingHours", "futureSailingHours", "speedChangeAt")},
            "departureHoldHours": hold, "deadlineAt": plan.get("deadlineAt"), "fuel": fuel,
            "finance": finance.to_dict(), "consumedForecasts": consumed}
        summaries.append(summary)
        options.append(DecisionOption(option_id=option_id, action=action, label=label,
            actor=problem.actor.role, status=status, is_baseline=baseline,
            params={"arrivalAt": arrival.isoformat(), "speedKn": speed, "holdHours": hold,
                "departureAt": departure.isoformat(), "speedChangeAt": derived["speedChangeAt"], "passagePlanVersion": VERSION},
            constraints=constraints, assumptions=[env["assumptions"], {"kind": "OPERATOR_DEMO_DECLARED_PASSAGE", "plan": plan}],
            provenance={"source": "CURRENT_FORECAST_DEMO", "passagePlanVersion": VERSION},
            evaluation=DecisionEvaluation(objectives={
                "eta": known(shift, "hours", basis="Option conditional clear approach minus baseline conditional clear approach", confidence=None) if shift is not None else unknown("hours", missing or "Baseline clear approach unavailable"),
                "port_wait": known(wait, "hours", basis="Conditional clear approach minus physical arrival; waiting at assumed anchorage", confidence=None) if wait is not None else unknown("hours", missing),
                "fuel": fuel_measure, "cost": unknown("money", "Incomplete costs; partial components are not a total or cheapest objective"),
                "risk": unknown("risk", "No calibrated closure or whole-route risk model"),
                "weather": unknown("m", "Only port-approach gust/visibility evaluated; no whole-route safety objective")},
                derived=derived, financial=finance.to_dict(), notes=["Modeled under declared demo inputs, not measured operational savings"], computed_at=at.isoformat()),
            geometry=deepcopy(plan.get("geometry")), timeline=timeline))
    for i, summary in enumerate(summaries):
        summary["delta"] = passage_finance_deltas(financials[0], financials[i], fuels[0], fuels[i])
    comparison = {"version": VERSION, "inputVersion": "passage-inputs-" + input_hash, "referenceAt": reference.isoformat(),
        "calculationAt": at.isoformat(), "commonElapsedSailingHours": common_hours,
        "commonElapsedDistanceNm": common_distance, "remainingDistanceAtCalculationNm": remaining_distance,
        "projectionBasis": "For at-sea declarations, elapsed sailing to calculation time is shared at baseline speed. Alternatives change only the future remaining segment. This is a simulated projection, not a later observed position.",
        "requestedApproachAt": requested.isoformat(), "distanceNm": plan["remainingDistanceNm"],
        "distanceBasis": plan["distanceBasis"], "baselineArrivalAt": baseline_arrival.isoformat(),
        "geometryBasis": ("Operator-declared simulated polyline. " + ROUTE_DISCLAIMER) if plan.get("geometry") else "No declared geometry; scalar distance assumption only. Original traffic remains simulated.",
        "options": summaries, "limitations": ["Port approach only; no clearance, berth or whole-route safety claim",
            "Requested approach time is an operator assumption, not an official restriction",
            "Hourly resolution: the next whole forecast hour starts a two-consecutive-hour gate; no continuous-time interpolation",
            "Unknown common port/cargo/other costs prevent a total or cheapest recommendation",
            "No onward delivery commitment or measured saving is established"]}
    env.update(evidenceVersion="current-weather-passage-v3", passagePlan=plan, passageComparison=comparison)
    env.pop("evidenceId", None)
    env["evidenceId"] = _identity(env)
    problem.decision_id = "dec-arrival-" + _identity({"evidence": env["evidenceId"], "actor": problem.actor.to_dict(), "at": at.isoformat()})[:20]
    problem.world_state_id = problem.world_state_id.split(":")[0] + ":" + env["evidenceId"]
    for option in options:
        option.provenance["evidenceId"] = env["evidenceId"]
    problem.options = options
    problem.baseline_option_id = options[0].option_id
    problem.objectives = [DecisionObjective("eta", "Clear approach shift", "hours"),
                          DecisionObjective("port_wait", "Assumed anchorage wait", "hours"),
                          DecisionObjective("fuel", "Modeled fuel", "tonne")]
    # The frontier needs only universally known dimensions. Unknown fuel stays
    # explicitly dropped by the existing ranking, rather than blocking schedule.
    problem.evidence["frontierObjectives"] = ["eta", "port_wait"] + (["fuel"] if all(o.measure("fuel").available for o in options if o.feasible) and any(o.feasible for o in options) else [])
    problem.available_actions = [{**CATALOGUE[a].to_dict(),
        "label": {SLOW_STEAM: "Reduce declared passage speed", SPEED_UP: "Increase declared passage speed",
                  DELAY_DEPARTURE: "Delay permitted departure"}.get(a, CATALOGUE[a].label),
        "description": "Bounded same-passage action under declared operating assumptions",
        "availability": {"status": "UNAVAILABLE" if a == DELAY_DEPARTURE and plan["referenceKind"] == "AT_SEA" else "INSUFFICIENT_DATA", "reason": unavailable[a]} if a in unavailable else {"status": "AVAILABLE", "reason": "Declared passage evaluated; inspect constraints for feasibility"}}
        for a in (KEEP_PLAN, SLOW_STEAM, SPEED_UP, DELAY_DEPARTURE, DELAY_ARRIVAL)]
    problem.headline = f"{problem.subject_label}: declared passage to the {env['portCode']} approach window"
    wait_label = "unavailable" if summaries[0]["anchorageWaitHours"] is None else f"{summaries[0]['anchorageWaitHours']:.2f} h"
    problem.do_nothing_statement = f"Continue at {plan['baselineSpeedKn']:g} kn; approach {baseline_arrival.isoformat()}; conditional wait {wait_label}."
    problem.notes.extend(comparison["limitations"])
    return problem
