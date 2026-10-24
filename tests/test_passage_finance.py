"""Dimensional, applicability and unknown-not-zero passage finance contracts."""

from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from src.portwatch_os.decision.passage_finance import (
    evaluate_passage_finance, passage_finance_deltas,
)
from src.portwatch_os.finance.evaluate import avoidable_cost


AT = datetime(2026, 10, 23, 6, tzinfo=timezone.utc)


def declared_inputs():
    # Deliberately selected fictional fixture, never an operational default.
    return {
        "enteredBy": "fictional-fixture-operator", "currency": "USD",
        "consumption": {
            "referenceSpeedKn": 12, "referencePropulsionTonnesPerDay": 24,
            "auxiliaryTonnesPerDay": 6, "anchorageTonnesPerDay": 3,
            "departureHoldTonnesPerDay": 2, "minSpeedKn": 6, "maxSpeedKn": 16,
            "loadCondition": "fictional laden demonstration", "source": "explicit fixture assumption",
            "declaredAt": "2026-10-23T05:00:00Z",
        },
        "fuelPrice": {"amount": 500, "currency": "USD", "per": "tonne",
                      "source": "explicit fixture price assumption",
                      "validFrom": "2026-10-23T00:00:00Z", "validTo": "2026-10-28T00:00:00Z"},
        "elapsedTimeRate": {"amount": 100, "currency": "USD", "per": "hour",
                            "source": "one fictional time-cost contract assumption",
                            "validFrom": "2026-10-23T00:00:00Z", "validTo": "2026-10-28T00:00:00Z",
                            "applicability": "WHOLE_MODELED_ELAPSED"},
    }


def evaluate(inputs=None, *, hours=24, speed=12, anchor=0, hold=0, reference=AT, calculation_at=None, segments=None):
    return evaluate_passage_finance(
        inputs, sailing_hours=hours, speed_kn=speed, anchorage_hours=anchor,
        departure_hold_hours=hold, at=reference, port_code="INNSA", calculation_at=calculation_at,
        sailing_segments=segments,
    )


def by_key(financial):
    return {component.key: component for component in financial.components}


def test_reference_consumption_and_modes_price_typed_tonnes_and_elapsed_once():
    inputs = declared_inputs()
    untouched = deepcopy(inputs)
    financial, fuel = evaluate(inputs, anchor=4, hold=2)
    assert inputs == untouched
    assert fuel["totalTonnes"] == pytest.approx(30 + 3 * 4 / 24 + 2 * 2 / 24)
    assert fuel["modes"]["sailing"]["propulsionTonnes"] == 24
    assert fuel["modes"]["sailing"]["auxiliaryTonnes"] == 6
    components = by_key(financial)
    assert components["sailing_fuel"].quantity.unit == "tonne"
    assert components["sailing_fuel"].money.amount == 15000
    assert components["anchorage_fuel"].money.amount == 250
    assert components["departure_hold_fuel"].money.amount == pytest.approx(500 / 6)
    assert components["elapsed_time"].money.amount == 3000
    assert components["elapsed_time"].quantity.value == 30
    assert components["elapsed_time"].rate["unit"] == "day"
    assert components["elapsed_time"].rate["value"] == 2400
    assert financial.assumption
    assert financial.source_types == ["USER_ASSUMPTION"]
    assert financial.total is None
    assert financial.partial_total.amount == pytest.approx(15000 + 250 + 500 / 6 + 3000)
    assert {u["key"] for u in financial.unknown} == {"common_port_costs", "cargo_costs", "other_costs"}
    assert not avoidable_cost(financial, financial)["available"]


def test_slower_same_window_exposes_component_tradeoff_without_total_savings():
    inputs = declared_inputs()
    baseline, baseline_fuel = evaluate(inputs, hours=12, speed=12, anchor=4)
    slower, slower_fuel = evaluate(inputs, hours=16, speed=9)
    delta = passage_finance_deltas(baseline, slower, baseline_fuel, slower_fuel)
    assert slower_fuel["totalTonnes"] == pytest.approx((24 * (9 / 12) ** 3 + 6) * 16 / 24)
    assert delta["fuelTonnes"]["value"] < 0
    components = {row["key"]: row for row in delta["components"]}
    assert components["sailing_fuel"]["money"]["amount"] < 0
    assert components["anchorage_fuel"]["money"]["amount"] == -250
    assert components["elapsed_time"]["money"]["amount"] == 0
    assert not components["common_port_costs"]["available"]
    assert not delta["completeCostComparison"]
    assert "cheapest" in delta["meaning"]


def test_high_auxiliary_demand_can_make_slower_sailing_use_more_fuel():
    inputs = declared_inputs()
    inputs["consumption"]["auxiliaryTonnesPerDay"] = 80
    _, baseline = evaluate(inputs, hours=12, speed=12)
    _, slower = evaluate(inputs, hours=16, speed=9)
    assert slower["totalTonnes"] > baseline["totalTonnes"]
    assert slower["modes"]["sailing"]["propulsionTonnes"] < baseline["modes"]["sailing"]["propulsionTonnes"]


def test_rate_alone_does_not_create_fuel_and_no_unknown_dollar_zero():
    inputs = declared_inputs()
    del inputs["consumption"]
    del inputs["elapsedTimeRate"]
    financial, fuel = evaluate(inputs)
    assert not fuel["available"]
    assert fuel["totalTonnes"] is None
    assert "consumption" in fuel["modes"]["sailing"]["unknownBecause"]
    assert by_key(financial)["sailing_fuel"].state == "UNKNOWN"
    assert by_key(financial)["anchorage_fuel"].state == "ZERO"
    assert by_key(financial)["departure_hold_fuel"].state == "ZERO"
    assert financial.partial_total is None
    assert financial.total is None


def test_consumption_without_prices_retains_tonnes_with_unknown_cost():
    financial, fuel = evaluate({"consumption": declared_inputs()["consumption"]}, anchor=4)
    assert fuel["available"]
    assert fuel["totalTonnes"] == 30.5
    assert by_key(financial)["sailing_fuel"].state == "UNKNOWN"
    assert "price" in by_key(financial)["sailing_fuel"].reason
    assert financial.partial_total is None


def test_unknown_later_wait_preserves_independent_sailing_fuel_and_price():
    financial, fuel = evaluate(declared_inputs(), anchor=None)
    assert not fuel["available"]
    assert fuel["totalTonnes"] is None
    assert fuel["modes"]["sailing"]["tonnes"] == 30
    assert fuel["modes"]["anchorage"]["hours"] is None
    assert by_key(financial)["sailing_fuel"].money.amount == 15000
    assert by_key(financial)["anchorage_fuel"].state == "UNKNOWN"
    assert by_key(financial)["elapsed_time"].state == "UNKNOWN"
    assert financial.partial_total.amount == 15000


@pytest.mark.parametrize("field,value,expected", [
    ("source", "", "source"),
    ("loadCondition", "", "load condition"),
    ("declaredAt", "2026-10-23T07:00:00Z", "later"),
    ("declaredAt", "2026-10-23T05:00:00", "timezone-aware"),
    ("referencePropulsionTonnesPerDay", True, "finite number"),
    ("auxiliaryTonnesPerDay", float("nan"), "finite number"),
    ("auxiliaryTonnesPerDay", -1, "non-negative"),
    ("maxSpeedKn", 10, "reference speed"),
])
def test_invalid_consumption_blocks_optional_fuel_only(field, value, expected):
    inputs = declared_inputs()
    inputs["consumption"][field] = value
    financial, fuel = evaluate(inputs)
    assert not fuel["available"]
    assert expected in fuel["modes"]["sailing"]["unknownBecause"]
    # Explicit elapsed-time arithmetic remains usable independently.
    assert by_key(financial)["elapsed_time"].money.amount == 2400


def test_speed_applicability_and_missing_active_mode_do_not_fill_zero():
    financial, fuel = evaluate(declared_inputs(), speed=17, anchor=4)
    assert not fuel["available"]
    assert fuel["modes"]["anchorage"]["tonnes"] == 0.5
    assert "outside" in fuel["modes"]["sailing"]["unknownBecause"]
    inputs = declared_inputs()
    del inputs["consumption"]["anchorageTonnesPerDay"]
    financial, fuel = evaluate(inputs, anchor=4)
    assert fuel["modes"]["sailing"]["available"]
    assert not fuel["available"]
    assert by_key(financial)["anchorage_fuel"].state == "UNKNOWN"
    assert by_key(financial)["sailing_fuel"].state == "KNOWN"
    assert financial.total is None


@pytest.mark.parametrize("field,value,expected", [
    ("amount", True, "finite number"),
    ("amount", float("inf"), "finite number"),
    ("amount", -2, "positive"),
    ("per", "hour", "per tonne"),
    ("currency", "usd", "currency"),
    ("source", "", "source"),
    ("validFrom", "2026-10-23", "timezone-aware"),
    ("validTo", "2026-10-23T08:00:00Z", "outside"),
    ("scope", "INMAA", "scope"),
])
def test_malformed_or_inapplicable_price_preserves_fuel_and_schedule_basis(field, value, expected):
    inputs = declared_inputs()
    inputs["fuelPrice"][field] = value
    financial, fuel = evaluate(inputs)
    assert fuel["available"]
    assert by_key(financial)["sailing_fuel"].state == "UNKNOWN"
    assert expected in by_key(financial)["sailing_fuel"].reason
    assert by_key(financial)["elapsed_time"].money.amount == 2400


def test_rate_validity_is_checked_for_each_actual_operating_interval():
    inputs = declared_inputs()
    inputs["fuelPrice"]["validTo"] = "2026-10-24T07:00:00Z"
    financial, fuel = evaluate(inputs, anchor=4)
    assert fuel["available"]
    assert by_key(financial)["sailing_fuel"].state == "KNOWN"
    assert by_key(financial)["anchorage_fuel"].state == "UNKNOWN"
    assert "outside" in by_key(financial)["anchorage_fuel"].reason


def test_elapsed_rate_requires_scope_and_uses_day_hour_conversion_once():
    inputs = declared_inputs()
    inputs["elapsedTimeRate"]["amount"] = 2400
    inputs["elapsedTimeRate"]["per"] = "day"
    financial, _ = evaluate(inputs, hours=12, anchor=4, hold=2)
    assert by_key(financial)["elapsed_time"].money.amount == 1800
    inputs["elapsedTimeRate"]["applicability"] = "UNSPECIFIED"
    financial, fuel = evaluate(inputs)
    assert fuel["available"]
    assert by_key(financial)["elapsed_time"].state == "UNKNOWN"
    assert "applicability" in by_key(financial)["elapsed_time"].reason


def test_cross_currency_components_stay_visible_without_invented_fx():
    inputs = declared_inputs()
    inputs["elapsedTimeRate"]["currency"] = "INR"
    financial, _ = evaluate(inputs)
    assert by_key(financial)["sailing_fuel"].money.currency == "USD"
    assert by_key(financial)["elapsed_time"].money.currency == "INR"
    assert financial.partial_total is None
    assert financial.total is None
    assert any(row["key"] == "fx" for row in financial.unknown)
    assert financial.fx_used == []


def test_deltas_do_not_subtract_components_in_different_currencies():
    inputs = declared_inputs()
    baseline, baseline_fuel = evaluate(inputs)
    inputs["fuelPrice"]["currency"] = "INR"
    changed, changed_fuel = evaluate(inputs)
    delta = passage_finance_deltas(baseline, changed, baseline_fuel, changed_fuel)
    assert delta["fuelTonnes"]["value"] == 0
    sailing = next(row for row in delta["components"] if row["key"] == "sailing_fuel")
    assert not sailing["available"]
    assert "FX" in sailing["unknownBecause"]


def test_zero_duration_modes_need_neither_consumption_nor_prices():
    financial, fuel = evaluate(None, hours=0, speed=None, anchor=0, hold=0)
    assert fuel["available"]
    assert fuel["totalTonnes"] == 0
    assert all(component.state == "ZERO" for component in financial.components[:4])
    assert financial.total is None  # Unknown common/cargo costs still exist.


def test_declaration_availability_uses_calculation_time_separately_from_position_and_departure():
    inputs = declared_inputs()
    inputs["consumption"]["declaredAt"] = "2026-10-23T05:59:55Z"
    reference = datetime(2026, 10, 23, 5, 59, 50, tzinfo=timezone.utc)
    financial, fuel = evaluate(inputs, reference=reference, calculation_at=AT)
    assert fuel["available"]
    assert by_key(financial)["sailing_fuel"].state == "KNOWN"
    # Future departure does not permit an unavailable future declaration.
    reference = datetime(2026, 10, 23, 8, tzinfo=timezone.utc)
    inputs["consumption"]["declaredAt"] = "2026-10-23T07:00:00Z"
    _, fuel = evaluate(inputs, reference=reference, calculation_at=AT)
    assert not fuel["available"]
    assert "later than" in fuel["modes"]["sailing"]["unknownBecause"]


def test_common_elapsed_sailing_preserves_its_speed_and_fuel_before_proposed_change():
    inputs = declared_inputs()
    _, baseline = evaluate(inputs, hours=21, segments=[{"hours": 1, "speedKn": 12}, {"hours": 20, "speedKn": 12}])
    financial, alternative = evaluate(inputs, hours=31, speed=8,
        segments=[{"hours": 1, "speedKn": 12}, {"hours": 30, "speedKn": 8}])
    base_segments = baseline["modes"]["sailing"]["segments"]
    alt_segments = alternative["modes"]["sailing"]["segments"]
    assert base_segments[0] == alt_segments[0]
    assert alt_segments[0]["tonnes"] == pytest.approx(30 / 24)
    assert alt_segments[1]["tonnes"] == pytest.approx((24 * (8 / 12) ** 3 + 6) * 30 / 24)
    assert alternative["totalTonnes"] == pytest.approx(sum(segment["tonnes"] for segment in alt_segments))
    assert by_key(financial)["sailing_fuel"].quantity.value == alternative["totalTonnes"]
    assert "no average-speed" in alternative["modes"]["sailing"]["basis"]


def test_unknown_or_inapplicable_segment_does_not_get_averaged_into_supported_range():
    inputs = declared_inputs()
    financial, fuel = evaluate(inputs, hours=24,
        segments=[{"hours": 12, "speedKn": 12}, {"hours": 12, "speedKn": 20}])
    assert not fuel["available"]
    assert fuel["modes"]["sailing"]["segments"][0]["available"]
    assert not fuel["modes"]["sailing"]["segments"][1]["available"]
    assert "outside" in fuel["modes"]["sailing"]["unknownBecause"]
    assert by_key(financial)["sailing_fuel"].state == "UNKNOWN"
    financial, fuel = evaluate(inputs, hours=24,
        segments=[{"hours": 12, "speedKn": 12}, {"hours": 12}])
    assert not fuel["available"]
    assert "finite number" in fuel["modes"]["sailing"]["unknownBecause"]


def test_contradictory_segment_duration_stays_unknown_instead_of_overwriting_timeline():
    financial, fuel = evaluate(declared_inputs(), hours=24,
        segments=[{"hours": 1, "speedKn": 12}, {"hours": 24, "speedKn": 8}])
    assert not fuel["available"]
    assert fuel["modes"]["sailing"]["hours"] == 24
    assert "do not sum" in fuel["modes"]["sailing"]["unknownBecause"]
    assert by_key(financial)["elapsed_time"].quantity.value == 24


def test_extreme_finite_input_never_serializes_nonfinite_result():
    inputs = declared_inputs()
    inputs["consumption"]["referencePropulsionTonnesPerDay"] = 1e308
    inputs["fuelPrice"]["amount"] = 1e308
    financial, fuel = evaluate(inputs)
    assert not fuel["available"]
    json.dumps({"fuel": fuel, "financial": financial.to_dict()}, allow_nan=False)
    inputs["consumption"]["referencePropulsionTonnesPerDay"] = 1e300
    financial, fuel = evaluate(inputs)
    assert fuel["available"]
    assert by_key(financial)["sailing_fuel"].state == "UNKNOWN"
    json.dumps({"fuel": fuel, "financial": financial.to_dict()}, allow_nan=False)
