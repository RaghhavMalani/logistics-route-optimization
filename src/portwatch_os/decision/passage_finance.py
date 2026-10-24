"""Conditional fuel and component pricing for a declared remaining passage.

This is an adapter to the existing typed financial twin, not a hull model or
another optimiser. Every consumption figure and rate is an operator scenario
assumption. The generic vessel fuel index is never converted into tonnes here.
Unknown common, cargo and other costs keep the monetary result partial.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

from src.portwatch_os.finance.basis import CostBasis, CostRate, USER_ASSUMPTION
from src.portwatch_os.finance.evaluate import (
    CostComponent, FinancialEvaluation, KNOWN, Pricer, ZERO,
)
from src.portwatch_os.finance.money import DAY, HOUR, Money, Quantity, TONNE


VERSION = "declared-passage-finance-v1"
FORMULA = (
    "Sailing tonnes = [reference propulsion tonnes/day × "
    "(speed kn / reference speed kn)^3 + auxiliary tonnes/day] × sailing hours / 24. "
    "Anchorage and departure-hold tonnes = their separately declared tonnes/day × hours / 24."
)
_MODES = (
    ("sailing", "sailing_fuel", "Sailing fuel", None),
    ("anchorage", "anchorage_fuel", "Anchorage fuel", "anchorageTonnesPerDay"),
    ("departureHold", "departure_hold_fuel", "Departure-hold fuel", "departureHoldTonnesPerDay"),
)


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'non-negative'}")
    return float(value)


def _instant(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be an explicit timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an explicit timezone-aware timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be an explicit timezone-aware timestamp")
    return parsed.astimezone(timezone.utc)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be declared")
    return value.strip()


def _metadata(model: Any, at: datetime) -> Tuple[Dict[str, Any], Optional[str]]:
    if not isinstance(model, Mapping):
        return {}, "no declared vessel consumption model"
    try:
        source = _text(model.get("source"), "consumption source")
        load = _text(model.get("loadCondition"), "applicable load condition")
        declared = _instant(model.get("declaredAt"), "consumption declaredAt")
        if declared > at:
            raise ValueError("consumption declaredAt is later than the comparison calculation time")
        return {
            "source": source, "loadCondition": load, "declaredAt": model["declaredAt"],
            "sourceType": USER_ASSUMPTION,
        }, None
    except ValueError as exc:
        return {}, str(exc)


def _fuel_mode(
    name: str, hours: Any, model: Any, metadata_error: Optional[str], speed_kn: Any,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"available": False, "tonnes": None, "hours": None,
                           "unit": TONNE, "sourceType": USER_ASSUMPTION}
    try:
        duration = _number(hours, f"{name} hours")
        out["hours"] = duration
        if duration == 0:
            return {**out, "available": True, "tonnes": 0.0,
                    "basis": "No time in this operating mode; no fuel quantity or price is assumed."}
        if metadata_error:
            raise ValueError(metadata_error)
        if name == "sailing":
            speed = _number(speed_kn, "sailing speed kn", positive=True)
            floor = _number(model.get("minSpeedKn"), "consumption minSpeedKn", positive=True)
            ceiling = _number(model.get("maxSpeedKn"), "consumption maxSpeedKn", positive=True)
            reference = _number(model.get("referenceSpeedKn"), "referenceSpeedKn", positive=True)
            if not floor <= reference <= ceiling:
                raise ValueError("reference speed is outside the declared consumption speed range")
            if not floor <= speed <= ceiling:
                raise ValueError("option speed is outside the declared consumption speed range")
            propulsion = _number(model.get("referencePropulsionTonnesPerDay"),
                                 "referencePropulsionTonnesPerDay", positive=True)
            auxiliary = _number(model.get("auxiliaryTonnesPerDay"), "auxiliaryTonnesPerDay")
            propulsion_tonnes = propulsion * (speed / reference) ** 3 * duration / 24.0
            auxiliary_tonnes = auxiliary * duration / 24.0
            tonnes = propulsion_tonnes + auxiliary_tonnes
            if not all(math.isfinite(value) for value in (propulsion_tonnes, auxiliary_tonnes, tonnes)):
                raise ValueError("sailing fuel arithmetic is outside the finite calculation range")
            out.update({"propulsionTonnes": propulsion_tonnes, "auxiliaryTonnes": auxiliary_tonnes,
                        "applicableSpeedRangeKn": {"min": floor, "max": ceiling},
                        "referenceSpeedKn": reference,
                        "basis": "Declared cubic propulsion relation plus separately declared auxiliary demand."})
        else:
            field = next(field for mode, _, _, field in _MODES if mode == name)
            rate = _number(model.get(field), str(field))
            tonnes = rate * duration / 24.0
            out.update({"tonnesPerDay": rate, "basis": f"Declared {field} × hours / 24."})
        if not math.isfinite(tonnes):
            raise ValueError(f"{name} fuel arithmetic is outside the finite calculation range")
        return {**out, "available": True, "tonnes": tonnes}
    except (ValueError, TypeError, OverflowError) as exc:
        reason = f"{name} fuel arithmetic is outside the finite calculation range" if isinstance(exc, OverflowError) else str(exc)
        return {**out, "unknownBecause": reason}


def _priced_component(pricer: Pricer, key: str, label: str, primitive: str,
                      quantity: Quantity, driver: str) -> CostComponent:
    component = pricer.priced(key, label, primitive, quantity, driver=driver)
    if component.money is not None and not math.isfinite(component.money.amount):
        return pricer.unknown(key, label, "priced component is outside the finite calculation range", driver=driver)
    return component


def _segmented_sailing(hours: Any, segments: Any, model: Any,
                       metadata_error: Optional[str]) -> Dict[str, Any]:
    """Preserve already-elapsed sailing at its actual declared baseline speed.

    Averaging speeds before applying the cubic law would erase the distinct
    propulsion demand of the common prefix and a proposed future segment.
    """
    out: Dict[str, Any] = {"available": False, "tonnes": None, "hours": None,
                           "unit": TONNE, "sourceType": USER_ASSUMPTION, "segments": []}
    try:
        duration = _number(hours, "sailing hours")
        out["hours"] = duration
        if not isinstance(segments, list) or not segments or len(segments) > 16:
            raise ValueError("sailing segments must be a nonempty list of at most 16 declared segments")
        segment_hours = []
        for segment in segments:
            if not isinstance(segment, Mapping):
                raise ValueError("each sailing segment must declare hours and speedKn")
            segment_hours.append(_number(segment.get("hours"), "sailing segment hours"))
        if not math.isclose(sum(segment_hours), duration, rel_tol=1e-9, abs_tol=1e-7):
            raise ValueError("sailing segment hours do not sum to the declared total sailing hours")
        for index, (segment, segment_duration) in enumerate(zip(segments, segment_hours)):
            result = _fuel_mode("sailing", segment_duration, model, metadata_error, segment.get("speedKn"))
            raw_speed = segment.get("speedKn")
            result.update(index=index, speedKn=(float(raw_speed) if not isinstance(raw_speed, bool)
                          and isinstance(raw_speed, (int, float)) and math.isfinite(raw_speed) else None))
            out["segments"].append(result)
        unsupported = [segment["unknownBecause"] for segment in out["segments"] if not segment["available"]]
        if unsupported:
            raise ValueError("Sailing segment unavailable: " + "; ".join(sorted(set(unsupported))))
        tonnes = sum(segment["tonnes"] for segment in out["segments"])
        propulsion = sum(segment.get("propulsionTonnes", 0.) for segment in out["segments"])
        auxiliary = sum(segment.get("auxiliaryTonnes", 0.) for segment in out["segments"])
        if not all(math.isfinite(value) for value in (tonnes, propulsion, auxiliary)):
            raise ValueError("segmented sailing fuel arithmetic is outside the finite calculation range")
        return {**out, "available": True, "tonnes": tonnes, "propulsionTonnes": propulsion,
                "auxiliaryTonnes": auxiliary,
                "basis": "Sum of separately evaluated sailing segments; elapsed common sailing is unchanged, no average-speed substitution."}
    except (ValueError, TypeError, OverflowError) as exc:
        return {**out, "unknownBecause": str(exc)}


def _cost_rate(
    raw: Any, *, primitive: str, start: datetime, end: datetime,
    port_code: str, entered_by: str,
) -> Tuple[Optional[CostRate], Optional[str]]:
    if not isinstance(raw, Mapping):
        return None, "no declared fuel price" if primitive == "bunker_price_t" else "no declared elapsed-time rate"
    try:
        amount = _number(raw.get("amount"), "rate amount", positive=True)
        currency = raw.get("currency")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("rate currency must be an uppercase three-letter currency code")
        source = _text(raw.get("source"), "rate source")
        unit = raw.get("per")
        if primitive == "bunker_price_t":
            if unit != TONNE:
                raise ValueError("fuel price must be per tonne")
            native_unit = TONNE
            converted_amount = amount
        else:
            if unit not in (HOUR, DAY):
                raise ValueError("elapsed-time rate must be per hour or per day")
            if raw.get("applicability") != "WHOLE_MODELED_ELAPSED":
                raise ValueError("elapsed-time rate requires explicit WHOLE_MODELED_ELAPSED applicability")
            native_unit = DAY
            converted_amount = amount * 24.0 if unit == HOUR else amount
        valid_from = _instant(raw.get("validFrom"), "rate validFrom")
        valid_to = _instant(raw.get("validTo"), "rate validTo")
        if valid_from > valid_to:
            raise ValueError("rate validity window is contradictory")
        if start < valid_from or end > valid_to:
            raise ValueError("rate is outside its declared validity for this operating interval; not used")
        supplied_scope = raw.get("scope", port_code)
        if supplied_scope not in ("*", port_code):
            raise ValueError("rate scope does not apply to this destination")
        return CostRate(
            primitive=primitive, value=converted_amount, currency=currency, unit=native_unit,
            scope=supplied_scope, valid_from=raw["validFrom"], valid_to=raw["validTo"],
            source=source, source_type=USER_ASSUMPTION, confidence=0.5,
            provenance={"enteredBy": entered_by, "purpose": "declared remaining-passage scenario",
                        "originalRate": {"amount": amount, "currency": currency, "per": unit},
                        "applicability": raw.get("applicability", "MODELED_FUEL_QUANTITY"),
                        "pricedFrom": start.isoformat(), "pricedTo": end.isoformat()},
        ), None
    except (ValueError, TypeError, OverflowError) as exc:
        return None, str(exc)


def evaluate_passage_finance(
    inputs: Any, *, sailing_hours: Any, speed_kn: Any, anchorage_hours: Any,
    departure_hold_hours: Any, at: datetime, port_code: str,
    calculation_at: Optional[datetime] = None,
    sailing_segments: Optional[list] = None,
) -> Tuple[FinancialEvaluation, Dict[str, Any]]:
    """Return a partial financial twin and independently supported fuel modes.

    ``at`` is the option's position/departure reference, before any declared
    departure hold. Sailing then anchorage follow. Prices must cover each
    interval that they actually price. ``calculation_at`` is when the inputs
    became available for the comparison; it can follow a declared present
    position or precede a future departure. Invalid optional financial input
    does not raise or prevent the caller's schedule comparison.
    """
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("passage finance reference must be timezone-aware")
    at = at.astimezone(timezone.utc)
    known_at = calculation_at or at
    if known_at.tzinfo is None or known_at.utcoffset() is None:
        raise ValueError("passage finance calculation time must be timezone-aware")
    known_at = known_at.astimezone(timezone.utc)
    supplied = inputs if isinstance(inputs, Mapping) else {}
    model = supplied.get("consumption")
    metadata, metadata_error = _metadata(model, known_at)
    modes = {
        name: _fuel_mode(name, hours, model, metadata_error, speed_kn)
        for name, hours in (("sailing", sailing_hours), ("anchorage", anchorage_hours),
                            ("departureHold", departure_hold_hours))
    }
    if sailing_segments is not None:
        modes["sailing"] = _segmented_sailing(sailing_hours, sailing_segments, model, metadata_error)
    complete_fuel = all(mode["available"] for mode in modes.values())
    fuel: Dict[str, Any] = {
        "version": VERSION, "available": complete_fuel,
        "totalTonnes": sum(m["tonnes"] for m in modes.values()) if complete_fuel else None,
        "unit": TONNE, "modes": modes, "formula": FORMULA, "consumption": metadata,
        "missingInputs": sorted({m["unknownBecause"] for m in modes.values() if not m["available"]}),
        "meaning": "Modeled under declared scenario inputs; not measured fuel or operational savings.",
        "assumptions": [
            "Constant declared speed and load over the remaining sailing period; no whole-route weather or hull validation.",
            "Cubic propulsion is a simplified operator-selected scenario relation, not a calibrated vessel curve.",
            "Auxiliary demand is separate; anchorage and departure-hold rates are separate operating modes.",
        ],
    }
    if complete_fuel and not math.isfinite(fuel["totalTonnes"]):
        fuel.update({"available": False, "totalTonnes": None,
                     "missingInputs": ["total fuel is outside the finite calculation range"]})

    candidate_currencies = (supplied.get("currency"),
                            (supplied.get("fuelPrice") or {}).get("currency") if isinstance(supplied.get("fuelPrice"), Mapping) else None,
                            (supplied.get("elapsedTimeRate") or {}).get("currency") if isinstance(supplied.get("elapsedTimeRate"), Mapping) else None)
    currency = next((v for v in candidate_currencies if isinstance(v, str) and re.fullmatch(r"[A-Z]{3}", v)), "USD")
    entered_by = supplied.get("enteredBy")
    entered_by = entered_by.strip() if isinstance(entered_by, str) and entered_by.strip() else "comparison operator"
    pricer = Pricer(CostBasis(), at=at, currency=currency, scope=port_code)
    components = []
    durations_valid = all(m["hours"] is not None for m in modes.values())
    intervals: Dict[str, Tuple[datetime, datetime]] = {}
    cursor: Optional[datetime] = at
    for name in ("departureHold", "sailing", "anchorage"):
        if cursor is None or modes[name]["hours"] is None:
            cursor = None
            continue
        try:
            end = cursor + timedelta(hours=modes[name]["hours"])
            intervals[name] = (cursor, end)
            cursor = end
        except (OverflowError, ValueError):
            durations_valid = False
            cursor = None
    for name, key, label, _ in _MODES:
        mode = modes[name]
        if mode["available"] and mode["tonnes"] == 0:
            components.append(pricer.zero(key, label, mode["basis"], driver=f"fuel.{name}"))
        elif not mode["available"]:
            components.append(pricer.unknown(key, label, mode["unknownBecause"], driver=f"fuel.{name}"))
        elif name not in intervals:
            components.append(pricer.unknown(key, label, "operating interval cannot be established", driver=f"fuel.{name}"))
        else:
            start, end = intervals[name]
            rate, reason = _cost_rate(supplied.get("fuelPrice"), primitive="bunker_price_t",
                                      start=start, end=end, port_code=port_code, entered_by=entered_by)
            if rate is None:
                components.append(pricer.unknown(key, label, reason, driver=f"fuel.{name}"))
            else:
                mode_pricer = Pricer(CostBasis([rate]), at=start, currency=currency, scope=port_code)
                components.append(_priced_component(mode_pricer, key, label, "bunker_price_t",
                                                     Quantity(mode["tonnes"], TONNE), f"fuel.{name}"))

    elapsed = sum(m["hours"] for m in modes.values()) if durations_valid and cursor is not None else None
    if elapsed == 0:
        components.append(pricer.zero("elapsed_time", "Declared elapsed-time cost", "No modeled elapsed hours.", driver="totalElapsedHours"))
    elif elapsed is None:
        components.append(pricer.unknown("elapsed_time", "Declared elapsed-time cost", "modeled elapsed duration is unavailable", driver="totalElapsedHours"))
    else:
        rate, reason = _cost_rate(supplied.get("elapsedTimeRate"), primitive="charter_day",
                                  start=at, end=cursor, port_code=port_code, entered_by=entered_by)
        if rate is None:
            components.append(pricer.unknown("elapsed_time", "Declared elapsed-time cost", reason, driver="totalElapsedHours"))
        else:
            time_pricer = Pricer(CostBasis([rate]), at=at, currency=currency, scope=port_code)
            components.append(_priced_component(time_pricer, "elapsed_time", "Declared elapsed-time cost", "charter_day",
                                                 Quantity(elapsed, HOUR), "totalElapsedHours"))
    components.extend([
        pricer.unknown("common_port_costs", "Common port charges", "port-call quantities and applicable terms are unavailable; common costs are not assumed to cancel"),
        pricer.unknown("cargo_costs", "Cargo and onward-commitment cost", "cargo exposure and applicable terms are unavailable"),
        pricer.unknown("other_costs", "Other contractual or operating costs", "unmodeled contractual, berth and other operating costs remain unavailable"),
    ])
    financial = pricer.evaluation(components, notes=[
        "PARTIAL: modeled fuel and one explicitly applicable elapsed-time charge only; no complete total, cheapest plan or percentage saving is available.",
        "Elapsed-time pricing covers sailing, anchorage and departure hold once. No separate charter, delay or holding charge is added.",
        "Common port, cargo and other unknown costs are not treated as zero or cancelled between options.",
        "Cross-currency aggregation is unavailable without a retained applicable FX observation; quotes or headlines are not substituted.",
        "All supplied rates and consumption figures are operator scenario assumptions, not measured operational savings.",
    ])
    # Pricer's generic empty-known-set sum is mathematically zero. Here that
    # would look like a USD 0 scenario despite missing consumption/prices.
    if not any(c.state == KNOWN and c.money is not None for c in components):
        financial.partial_total = None
    elif financial.partial_total is not None and not math.isfinite(financial.partial_total.amount):
        financial.partial_total = None
        financial.unknown.append({"key": "partial_sum", "label": "Partial monetary aggregate",
                                  "reason": "aggregate is outside the finite calculation range"})
    return financial, fuel


def passage_finance_deltas(
    baseline_financial: FinancialEvaluation, option_financial: FinancialEvaluation,
    baseline_fuel: Mapping[str, Any], option_fuel: Mapping[str, Any],
) -> Dict[str, Any]:
    """Signed option-minus-baseline component deltas; never a complete saving."""
    baseline = {c.key: c for c in baseline_financial.components}
    deltas = []
    for component in option_financial.components:
        other = baseline.get(component.key)
        row: Dict[str, Any] = {"key": component.key, "label": component.label, "available": False}
        if other is None or component.state not in (KNOWN, ZERO) or other.state not in (KNOWN, ZERO):
            row["unknownBecause"] = "component is unavailable on at least one side; unknown costs are not cancelled"
        else:
            option_money = component.money if component.state == KNOWN else None
            base_money = other.money if other.state == KNOWN else None
            if option_money and base_money and option_money.currency != base_money.currency:
                row["unknownBecause"] = "component currencies differ and no retained applicable FX conversion was supplied"
            else:
                currency = option_money.currency if option_money else (base_money.currency if base_money else option_financial.currency)
                difference = Money((option_money.amount if option_money else 0.0) -
                                   (base_money.amount if base_money else 0.0), currency)
                row.update({"available": True, "money": difference.to_dict(),
                            "basis": "modeled option minus baseline; component only"})
        deltas.append(row)
    fuel_known = bool(baseline_fuel.get("available") and option_fuel.get("available"))
    return {
        "basis": "OPTION_MINUS_BASELINE", "completeCostComparison": False,
        "fuelTonnes": ({"available": True, "value": option_fuel["totalTonnes"] - baseline_fuel["totalTonnes"], "unit": TONNE}
                       if fuel_known else {"available": False, "unit": TONNE, "unknownBecause": "total fuel is unavailable on at least one side"}),
        "components": deltas,
        "meaning": "Conditional modeled component differences; partial costs do not establish total savings or a cheapest option.",
    }


__all__ = ["VERSION", "FORMULA", "evaluate_passage_finance", "passage_finance_deltas"]
