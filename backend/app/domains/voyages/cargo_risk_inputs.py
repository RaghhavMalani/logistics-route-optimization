"""Projection of an owned decision into an explicitly conditional cargo study."""

from datetime import timedelta
from decimal import Decimal
from math import isfinite

from backend.app.services import cache_service
from src.portwatch_os.decision import cargo_market
from src.portwatch_os.decision.actions import CHANGE_DESTINATION_PORT, REROUTE, SPEED_UP
from src.portwatch_os.decision.cargo_sampling import ClosureBasis, RiskOption, RiskStudy
from src.portwatch_os.decision.commercial import CommercialContext, Consignment, instant
from src.portwatch_os.decision.outcome import option_derived
from src.portwatch_os.freshness.source_snapshots import configured_store

DEMO_OFFSET = Decimal(156)


def number(value):
    if type(value) in (int, float) and isfinite(value) and value >= 0:
        return float(value)
    return None


def _hours(value, at):
    return None if value is None else number((instant(value) - at).total_seconds() / 3600)


def _active(basis, at):
    return basis.firstAvailableAt <= at and basis.applicableFrom <= at <= basis.applicableThrough


def _commercial_input(engine, problem, at):
    for record in engine.ledger.decisions(kind="commercial_shadow", subject=problem.decision_id):
        context = CommercialContext.model_validate(record.recommendation["context"])
        if context.voyageId == problem.subject_id and context.consignments and _active(context.basis, at):
            return context
    return None


def _forecast(port, at, arrival):
    if not port:
        return None
    try:
        rows = cache_service.get_port_forecast(port)
    except (KeyError, cache_service.CacheNotReadyError):
        return None
    return cargo_market.retained_port_quantiles(rows, at, arrival)


def _option(option, passage, store, at, route_area, demo):
    derived = option_derived(option)
    to_destination = number(derived.get("arrivalInHours"))
    hours = _hours(derived.get("approachClearAt"), at) if passage else to_destination
    if hours is None:
        return None
    destination = derived.get("destinationPort")
    arrival = at + timedelta(hours=hours)
    transit_hour = derived.get("hoursToChokepoint")
    bypass = option.action in {REROUTE, SPEED_UP} and transit_hour is None
    # The alternative route geometry names a bypass of this area only.
    # Other required/excluded areas cannot be silently treated as absent.
    areas = () if demo and (passage or bypass) else (route_area,) if demo and route_area and transit_hour is not None else None
    fuel_measure = option.measure("fuel")
    tonnes = number(fuel_measure.value) if fuel_measure and fuel_measure.available and fuel_measure.unit == "tonne" else None
    if tonnes is None and passage:
        fuel = next((row.get("fuel") for row in passage.get("options", []) if row.get("optionId") == option.option_id), None)
        tonnes = number((fuel or {}).get("totalTonnes"))
    return RiskOption(
        id=option.option_id, action=option.action, label=option.label, cleanDeliveryHours=hours,
        reachClosureHour=None if passage else transit_hour, areas=areas,
        weather=None if passage else cargo_market.retained_weather(store, at, destination, arrival) if destination else None,
        port=None if passage else _forecast(destination, at, arrival),
        # A passage clock already incorporates the frozen hourly approach gate.
        weatherExposure=0 if passage else 1, berthExposure=0 if passage else 1,
        dwellHours=20 if demo else None, detentionHours=18 if demo else None,
        unpoweredHours=1 if demo else None, fuelTonnes=tonnes,
        latestStartHour=number(option.provenance.get("closesInHours")),
        source=("ASSUMPTION · frozen S10 gate; illustrative dwell 20 h, detention 18 h and reefer power gap 1 h"
                if demo and passage else "ASSUMPTION · frozen route clock and illustrative terminal clocks"
                if demo else "Frozen decision comparison; no additional terminal or insurance clocks declared"),
    )


def build_study(scoped, engine, problem):
    at = instant(problem.at or problem.created_at)
    evidence = problem.evidence
    env = evidence.get("currentEnvironment") or {}
    passage = env.get("passageComparison") or evidence.get("passageComparison")
    context = _commercial_input(engine, problem, at)
    demo = context is None
    cargo = tuple(context.consignments) if context else tuple(
        Consignment.model_validate(row) for row in scoped.world.get("cargoRiskConsignments", {}).get(problem.subject_id, [])
    )
    cargo = tuple(item for item in cargo if _active(item.basis, at))
    if not cargo:
        raise ValueError("No as-of owned consignments are available for this comparison.")
    if passage and demo:
        cargo = tuple(item.model_copy(update={
            "deliveryOffsetHours": DEMO_OFFSET, "offsetBasis": "DEMO ASSUMPTION · 156 h of onward delivery after the modelled approach",
        }) for item in cargo)
    elif not demo:
        for item in cargo:
            if item.event == "DECLARED_FINAL_DELIVERY" and (item.deliveryOffsetHours is None or not item.offsetBasis):
                raise ValueError(f"{item.id} requires a declared onward delivery clock.")
            if item.event == "CONDITIONAL_CARGO_READY":
                raise ValueError(f"{item.id} requires a bound cargo-ready clock for each feasible option.")

    store = configured_store()
    event = evidence.get("event") or {}
    seed = event.get("seed") or {}
    closure_model = evidence.get("closureModel") or {}
    choke = closure_model.get("at")
    route_area = "RED_SEA" if choke in {"SUEZ", "BAB_EL_MANDEB"} else choke
    severity = min(1, number(seed.get("probability")) or .5)
    confidence = min(1, number(seed.get("confidence")) or 0)
    started = (instant(event["claimFrom"]) - at).total_seconds() / 3600 if event.get("claimFrom") else 0
    closure = ClosureBasis(
        startedHour=max(-8760, min(0, started)), medianHours=0 if passage else 12 + 150 * severity**2,
        logSigma=0 if passage else .55, fizzleProbability=0 if passage else .5 * (1 - confidence),
        source="Frozen passage gate · no modelled route closure" if passage else
               "ASSUMPTION · frozen benchmark closure prior applied to the available event claim",
    )
    options, excluded = [], []
    for option in problem.options:
        if not option.feasible:
            continue
        converted = None if option.action == CHANGE_DESTINATION_PORT else _option(option, passage, store, at, route_area, demo)
        if converted is None:
            excluded.append({"label": option.label, "reason": "Onward delivery clock unavailable"})
        else:
            options.append(converted)
    keep = next((option for option in options if option.id == problem.baseline_option_id), None)
    if keep is None or len(options) < 2:
        raise ValueError("This comparison needs a current plan and one alternative with modelled delivery clocks.")
    currency = context.currency if context else "USD"
    if currency not in ("USD", "INR", "EUR"):
        raise ValueError("This study needs a USD, INR or EUR reporting basis.")
    study = RiskStudy(
        problemId=problem.decision_id, at=at, keepOptionId=keep.id, plannedDeliveryHours=keep.cleanDeliveryHours,
        reportingCurrency=currency, options=options, consignments=cargo, closure=closure,
        handling={"kind": "TRIANGULAR", "minimum": 0, "mode": 1.2, "maximum": 5,
                  "declaration": "ASSUMPTION · triangular additional handling (0 / 1.2 / 5 h)"},
        fuel={"low": 450, "high": 650, "currency": "USD",
              "source": "DEMO ASSUMPTION · 450–650 USD per tonne"} if demo else None,
        fx=cargo_market.retained_fx(store, at),
        scope="DEMO ASSUMPTION · Company-private fictional cargo" if demo else "Company-private modelled cargo, shadow comparison",
    )
    declarations = [{
        "id": item.id,
        "name": item.goodsClass,
        "handlingClass": item.riskTerms.handlingClass.model_dump(mode="json") if item.riskTerms and item.riskTerms.handlingClass else None,
        "deadline": item.riskTerms.deliveryDeadline.value.isoformat() if item.riskTerms and item.riskTerms.deliveryDeadline
                    else item.deadline.isoformat() if item.deadline else None,
        "deliveryClock": item.offsetBasis,
        "source": item.basis.source,
    } for item in cargo]
    return study, declarations, excluded
