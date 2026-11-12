"""Vectorised conditional cargo losses in a single declared reporting currency.

The incumbent feasibility engine decides which options exist. This module prices
the consequences of those options on aligned, externally supplied futures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from .commercial import Amount, CargoRiskTerms, Consignment, Sourced, insured_value_for_risk, instant

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
CARGO_COMPONENTS = (
    "late_penalty", "demurrage", "detention", "inventory_carrying", "spoilage",
    "cargo_premium", "war_risk_premium", "deductible_exposure", "general_average",
)


@dataclass(frozen=True)
class CostState:
    arrival_hours: FloatArray
    planned_arrival_hours: float
    demurrage_hours: FloatArray | None = None
    detention_hours: FloatArray | None = None
    unpowered_hours: FloatArray | None = None
    route_areas: tuple[str, ...] | None = None
    deductible_uniform: FloatArray | None = None
    general_average_uniform: FloatArray | None = None
    fx_to_reporting: Mapping[str, FloatArray | float] = field(default_factory=dict)


@dataclass(frozen=True)
class CostBreakdown:
    samples: int
    components: dict[str, FloatArray]
    unknown: dict[str, str]
    basis: dict[str, tuple[str, ...]]

    @property
    def known_subtotal(self) -> FloatArray | None:
        if not self.components:
            return None
        return sum(self.components.values(), np.zeros(self.samples))

    @property
    def total(self) -> FloatArray | None:
        return self.known_subtotal if not self.unknown else None


@dataclass(frozen=True)
class ConsignmentLoss:
    consignment_id: str
    costs: CostBreakdown
    on_time: BoolArray | None
    priority: int | None
    spoilage: BoolArray | None
    insured_value: Sourced[Amount] | None
    excluded_areas: tuple[str, ...] | None
    deadline_basis: str | None


def describe(term: Sourced) -> str:
    return f"{term.basis.upper()} · {term.source}"


def cvar(losses: FloatArray, alpha: float = 0.95) -> float:
    """Upper expected shortfall with fractional mass at the VaR boundary."""
    if losses.ndim != 1 or not len(losses) or not 0 < alpha < 1:
        raise ValueError("CVaR requires a nonempty loss vector and 0 < alpha < 1")
    index = max(0, int(np.ceil(alpha * len(losses))) - 1)
    var = np.partition(losses, index)[index]
    return float(var + np.maximum(losses - var, 0).mean() / (1 - alpha))


def summarize_cost(costs: CostBreakdown) -> dict:
    subtotal = costs.known_subtotal
    stats = None if subtotal is None else {
        "expected": float(subtotal.mean()),
        "cvar95": cvar(subtotal),
    }
    return {
        "scope": "complete declared cost" if not costs.unknown else "known subtotal; excludes unknowns",
        "expected": None if costs.unknown or stats is None else stats["expected"],
        "cvar95": None if costs.unknown or stats is None else stats["cvar95"],
        "knownSubtotal": stats,
        "unknown": dict(costs.unknown),
    }


def combine_costs(breakdowns: Mapping[str, CostBreakdown], samples: int) -> CostBreakdown:
    """Sum aligned sample rows before taking any expectation or tail statistic."""
    components, unknown, basis = {}, {}, {}
    for label, costs in breakdowns.items():
        if costs.samples != samples:
            raise ValueError("Rollups require aligned futures of the same size")
        components.update({f"{label}/{key}": value for key, value in costs.components.items()})
        unknown.update({f"{label}/{key}": reason for key, reason in costs.unknown.items()})
        basis.update({f"{label}/{key}": items for key, items in costs.basis.items()})
    return CostBreakdown(samples, components, unknown, basis)


def evaluate_consignment(
    shipment: Consignment, state: CostState, at: datetime, reporting_currency: str,
) -> ConsignmentLoss:
    at = instant(at)
    basis = shipment.basis
    if basis.firstAvailableAt > at or not basis.applicableFrom <= at <= basis.applicableThrough:
        raise ValueError(f"Terms for {shipment.id} were unavailable at the study instant")
    terms = shipment.riskTerms or CargoRiskTerms()
    components: dict[str, FloatArray] = {}
    sources: dict[str, tuple[str, ...]] = {}
    unknown: dict[str, str] = {}
    zero = np.zeros_like(state.arrival_hours, dtype=float)
    shipment_source = ("ASSUMPTION" if basis.kind == "SIMULATION" else "DECLARED") + " · " + basis.source

    def known(key, value, *labels):
        components[key] = np.broadcast_to(value, zero.shape)
        sources[key] = tuple(labels)

    def convert(money: Amount) -> FloatArray | float | None:
        if money.currency == reporting_currency:
            return float(money.amount)
        fx = state.fx_to_reporting.get(money.currency)
        return float(money.amount) * fx if fx is not None else None

    def price(key, money, multiplier, reason, *labels):
        if money is None or multiplier is None:
            unknown[key] = reason
            return
        converted = convert(money)
        if converted is None:
            unknown[key] = f"No {money.currency}/{reporting_currency} FX basis"
            return
        known(key, converted * multiplier, *labels)

    deadline = terms.deliveryDeadline.value if terms.deliveryDeadline else shipment.deadline
    deadline_source = describe(terms.deliveryDeadline) if terms.deliveryDeadline else shipment_source if deadline else None
    hours_late = state.arrival_hours - (deadline - at).total_seconds() / 3600 if deadline else None
    on_time = hours_late <= 0 if hours_late is not None else None
    charge = terms.latePenalty
    if charge is None or hours_late is None:
        unknown["late_penalty"] = "Delivery deadline or late-penalty terms unavailable"
    else:
        late = np.maximum(hours_late, 0) / 24 if charge.value.unit == "per_day" else hours_late > 0
        price("late_penalty", charge.value.amount, late, "", describe(charge), deadline_source)

    for key, clock, free, rate in (
        ("demurrage", state.demurrage_hours, terms.freeTimeHours, terms.demurrageRatePerDay),
        ("detention", state.detention_hours, terms.detentionFreeHours, terms.detentionRatePerDay),
    ):
        if clock is None or free is None or rate is None:
            unknown[key] = f"{key.capitalize()} clock, free time or rate unavailable"
        else:
            billable_days = np.maximum(clock - float(free.value), 0) / 24
            price(key, rate.value, billable_days, "", describe(free), describe(rate))

    declared_value = terms.cifValue
    cargo_value = declared_value.value if declared_value else shipment.replacementValue or shipment.invoiceValue
    value_source = describe(declared_value) if declared_value else shipment_source
    annual = terms.annualInventoryRate
    delay = np.maximum(state.arrival_hours - state.planned_arrival_hours, 0)
    price("inventory_carrying", cargo_value,
          float(annual.value) * delay / 8760 if annual else None,
          "Cargo value or annual carrying rate unavailable",
          value_source, describe(annual) if annual else "")

    spoilage = None
    reefer = bool(terms.handlingClass and terms.handlingClass.value == "reefer")
    shelf_term = terms.remainingShelfLifeHours
    shelf = shelf_term.value if shelf_term else shipment.remainingShelfLifeHours
    if terms.perishable and not terms.perishable.value and not reefer and shelf is None:
        spoilage = np.zeros_like(zero, dtype=bool)
        known("spoilage", zero, describe(terms.perishable))
    elif shelf is not None and (not reefer or (terms.maxUnpoweredHours and state.unpowered_hours is not None)):
        shelf_at = shipment.shelfLifeReferenceAt or (at if shelf_term else None)
        if shelf_at is None:
            unknown["spoilage"] = "Shelf-life reference time unavailable"
        else:
            transit = state.arrival_hours + (at - shelf_at).total_seconds() / 3600
            spoilage = transit > float(shelf)
            labels = [describe(shelf_term) if shelf_term else shipment_source]
            if reefer:
                spoilage = spoilage | (state.unpowered_hours > float(terms.maxUnpoweredHours.value))
                labels.append(describe(terms.maxUnpoweredHours))
            price("spoilage", cargo_value, spoilage, "Cargo value unavailable", value_source, *labels)
    else:
        unknown["spoilage"] = "Perishability, shelf life or reefer power exposure unavailable"

    insured = insured_value_for_risk(shipment)
    policy = terms.cargoPolicyRate
    price("cargo_premium", insured.value if insured else None, float(policy.value) if policy else None,
          "Insured value or cargo policy rate unavailable",
          describe(insured) if insured else "", describe(policy) if policy else "")

    route = None if state.route_areas is None else {area.strip().casefold() for area in state.route_areas}
    war = terms.warRiskAreas
    if war is None or route is None:
        unknown["war_risk_premium"] = "Route areas or declared war-risk requirements unavailable"
    else:
        required = [entry for entry in war.value if entry.area.strip().casefold() in route and entry.required.value]
        if not required:
            known("war_risk_premium", zero, describe(war))
        elif any(entry.premiumRate is None for entry in required):
            unknown["war_risk_premium"] = "Premium unavailable for a required war-risk area"
        else:
            price("war_risk_premium", insured.value if insured else None,
                  sum(float(entry.premiumRate.value) for entry in required), "Insured value unavailable",
                  describe(war), *(describe(entry.premiumRate) for entry in required))

    exclusions = terms.excludedAreas
    excluded = None if exclusions is None or route is None else tuple(sorted(
        area for area in exclusions.value if area.strip().casefold() in route
    ))
    incident = terms.separateDeductibleEventProbability
    deductible = terms.deductible
    if excluded:
        unknown["deductible_exposure"] = "A declared exclusion intersects the route; uninsured event loss unavailable"
    elif excluded is None or deductible is None or incident is None or state.deductible_uniform is None or insured is None:
        unknown["deductible_exposure"] = "Exclusions, deductible, insured value or separate incident basis unavailable"
    else:
        retention, cap = convert(deductible.value), convert(insured.value)
        if retention is None or cap is None:
            unknown["deductible_exposure"] = "FX basis unavailable for the deductible or insured value"
        else:
            # The declared event is separate from spoilage, which is already priced gross.
            known("deductible_exposure", np.minimum(retention, cap) * (state.deductible_uniform < float(incident.value)),
                  describe(deductible), describe(incident), describe(exclusions), describe(insured))

    exposed = terms.generalAverageExposed
    contribution, probability = terms.generalAverageContribution, terms.generalAverageEventProbability
    if exposed is not None and not exposed.value:
        known("general_average", zero, describe(exposed))
    elif exposed is None or contribution is None or probability is None or state.general_average_uniform is None:
        unknown["general_average"] = "Exposure, declared contribution or event basis unavailable"
    else:
        price("general_average", contribution.value, state.general_average_uniform < float(probability.value),
              "", describe(exposed), describe(contribution), describe(probability))

    return ConsignmentLoss(
        shipment.id, CostBreakdown(len(zero), components, unknown, sources), on_time,
        terms.priority.value if terms.priority else None, spoilage, insured, excluded, deadline_source,
    )
