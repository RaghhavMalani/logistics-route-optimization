"""Dimensional/time arithmetic for the existing current-arrival adapter."""
import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.portwatch_os.decision import current_arrival
from src.portwatch_os.decision.engine import DecisionEngine
from src.portwatch_os.decision.model import DecisionActor
from src.portwatch_os.sandbox import current_sandbox

AT = datetime(2026, 10, 23, 6, tzinfo=timezone.utc)


def stamp(hours=0):
    return (AT + timedelta(hours=hours)).isoformat()


def declared(**changes):
    return {"schemaVersion": 1, "referenceKind": "AT_SEA", "referenceAt": stamp(),
        "referenceLabel": "Simulated present position; no observed AIS", "declaredAt": stamp(),
        "remainingDistanceNm": 240., "distanceBasis": "Operator simulated scalar passage, no surveyed geometry",
        "baselineSpeedKn": 12., "minSpeedKn": 8., "maxSpeedKn": 16.,
        "alternativeSpeedKn": 10., "baselineArrivalAt": stamp(20), **changes}


def economics(auxiliary=2):
    return {"consumption": {"referenceSpeedKn": 12., "referencePropulsionTonnesPerDay": 24.,
        "auxiliaryTonnesPerDay": auxiliary, "anchorageTonnesPerDay": 2.,
        "minSpeedKn": 8., "maxSpeedKn": 16., "loadCondition": "SIMULATED unchanged load",
        "source": "Named illustrative operator assumption", "declaredAt": stamp()},
        "fuelPrice": {"amount": 600., "currency": "USD", "per": "tonne",
        "source": "Explicit illustrative assumption, not market quote", "validFrom": stamp(-1), "validTo": stamp(100)}}


def solve(monkeypatch, plan=None, *, blocked=True, alter=None):
    data = {"sources": {"surface": {"status": "CURRENT", "source": "fixture simulated weather",
        "snapshotId": "simulated-hourly-v1", "responseSha256": "a"*64, "issuedAt": None,
        "availableAt": stamp()}, "hazards": {"snapshotId": "context-only"}},
        "hourly": [{"validAt": stamp(h), "wind_gusts_10m": 20. if blocked and h < 24 else 10.,
                    "visibility": 10000., "wave_height": 1.} for h in range(20, 61)]}
    if alter:
        alter(data)
    monkeypatch.setattr(current_arrival, "bundle", lambda port: data)
    monkeypatch.setattr(current_arrival, "freeze_activity_context", lambda *args, **kwargs: {})
    vessel = SimpleNamespace(vessel_id="simulated-passage", name="Simulated passage hull", destination_port="INNSA", eta=stamp(20))
    state = SimpleNamespace(state_id="fixture", summary=lambda: {"revision": {"mode": "LIVE"}})
    request = {"plannedArrival": stamp(20), "maxGustKn": 15, "minVisibilityM": 5000}
    if plan is not None:
        request["passagePlan"] = plan
    token = current_sandbox.set(None)
    try:
        p = current_arrival.build_arrival_problem(vessel, request, DecisionActor("SHIPPING_COMPANY"), state, AT)
        return DecisionEngine().finish(p, now=AT)
    finally:
        current_sandbox.reset(token)


def test_slower_physical_passage_reaches_same_gate_with_separate_mode_costs(monkeypatch):
    p = solve(monkeypatch, declared(finance=economics()))
    env = p.evidence["currentEnvironment"]
    base, slow = env["passageComparison"]["options"]
    assert base["sailingHours"] == 20 and slow["sailingHours"] == 24
    assert base["anchorageWaitHours"] == 4 and slow["anchorageWaitHours"] == 0
    assert base["approachClearAt"] == slow["approachClearAt"] == stamp(24)
    assert base["totalElapsedHours"] == slow["totalElapsedHours"] == 24
    assert slow["scheduleShiftHours"] == 0
    assert base["fuel"]["totalTonnes"] == pytest.approx(22.)
    assert slow["fuel"]["totalTonnes"] == pytest.approx(24*(10/12)**3+2)
    assert all(s["finance"]["total"] is None and not s["finance"]["complete"] for s in (base, slow))
    assert "cost" in p.recommendation.ranking_basis["objectivesDropped"]
    assert p.recommendation.option_id == p.options[1].option_id
    assert p.options[1].evaluation.derived["propulsionIndex"] == pytest.approx((10/12)**2)
    assert p.options[1].measure("fuel").unit == "tonne"
    assert env["evidenceVersion"] == "current-weather-passage-v3"
    assert all("hours" in m and m["subject"] == p.subject_id for o in p.options for m in o.timeline)


def test_deadline_rejects_slower_option_even_when_fuel_is_less(monkeypatch):
    p = solve(monkeypatch, declared(alternativeSpeedKn=8, deadlineAt=stamp(26), finance=economics()))
    slow = p.options[1]
    assert slow.status == "REJECTED"
    assert slow.evaluation.derived["deadlineMet"] is False
    assert slow.evaluation.derived["scheduleShiftHours"] == 6
    assert p.recommendation.kind == "KEEP_CURRENT_PLAN"
    assert p.recommendation.option_id == p.baseline_option_id


def test_longer_auxiliary_demand_can_make_baseline_win_same_gate(monkeypatch):
    p = solve(monkeypatch, declared(finance=economics(auxiliary=200)))
    assert p.options[1].measure("fuel").value > p.baseline.measure("fuel").value
    assert p.recommendation.kind == "KEEP_CURRENT_PLAN"


def test_price_without_consumption_cannot_create_fuel_or_cheapest(monkeypatch):
    p = solve(monkeypatch, declared(finance={"fuelPrice": economics()["fuelPrice"]}))
    assert all(o.status == "FEASIBLE" for o in p.options)
    assert all(not o.measure("fuel").available and not o.measure("cost").available for o in p.options)
    assert p.recommendation.kind == "ACT"  # Existing frontier can prefer less anchorage wait; no fuel/cost claim.
    assert "fuel" in p.recommendation.ranking_basis["objectivesDropped"]
    assert "LOWEST_COST" not in p.frontier.picks


def test_no_approach_delay_keeps_plan_without_invented_hold(monkeypatch):
    p = solve(monkeypatch, declared(finance=economics()), blocked=False)
    assert p.baseline.evaluation.derived["anchorageWaitHours"] == 0
    assert p.options[1].evaluation.derived["scheduleShiftHours"] == 4
    assert all(o.params["holdHours"] == 0 for o in p.options)
    assert p.recommendation.kind == "KEEP_CURRENT_PLAN"
    unavailable = {a["kind"]: a["availability"] for a in p.available_actions}
    assert unavailable["DELAY_DEPARTURE"]["status"] == "UNAVAILABLE"
    assert "at sea" in unavailable["DELAY_DEPARTURE"]["reason"]


@pytest.mark.parametrize("changes,reason", [
    ({"remainingDistanceNm": 300}, "Contradictory"),
    ({"referenceAt": stamp(-2)}, "present-position"),
    ({"referenceAt": stamp(1)}, "present-position"),
    ({"distanceBasis": ""}, "distanceBasis"),
    ({"minSpeedKn": 1}, "minimum speed"),
    ({"declaredAt": stamp(-2)}, "last hour"),
    ({"referenceAt": "2026-10-23T06:00:00"}, "timezone"),
])
def test_unsupported_physical_declaration_preserves_bounded_arrival(monkeypatch, changes, reason):
    p = solve(monkeypatch, declared(**changes))
    assert reason in p.evidence["passagePlanningUnavailable"]["reason"]
    assert [o.action for o in p.options] == ["KEEP_PLAN", "DELAY_ARRIVAL"]
    assert "passagePlan" not in p.evidence["currentEnvironment"]


def test_each_option_uses_own_hours_and_out_of_horizon_is_not_evaluated(monkeypatch):
    p = solve(monkeypatch, declared(alternativeSpeedKn=8), alter=lambda d: d.update(hourly=d["hourly"][:9]))
    assert p.baseline.status == "FEASIBLE"
    assert p.options[1].status == "REJECTED"
    assert p.options[1].evaluation.derived["approachClearAt"] is None
    assert not p.options[1].measure("eta").available
    assert p.recommendation.kind == "KEEP_CURRENT_PLAN"


def test_option_coverage_gap_cannot_be_skipped_to_later_clear_hours(monkeypatch):
    p = solve(monkeypatch, declared(alternativeSpeedKn=8), alter=lambda d: d.update(hourly=[r for r in d["hourly"] if r["validAt"] != stamp(31)]))
    assert p.baseline.status == "FEASIBLE"
    assert p.options[1].status == "REJECTED"
    assert "gap" in p.options[1].rejected_by[0].detail


def test_missing_first_option_hour_cannot_be_skipped(monkeypatch):
    p = solve(monkeypatch, declared(alternativeSpeedKn=8), alter=lambda d: d.update(hourly=[r for r in d["hourly"] if r["validAt"] != stamp(30)]))
    assert p.baseline.status == "FEASIBLE"
    assert p.options[1].status == "REJECTED"
    assert "outside supported hourly" in p.options[1].rejected_by[0].detail


@pytest.mark.parametrize("receipt", [stamp(-2), stamp(1)])
def test_receipt_status_alone_does_not_establish_freshness(monkeypatch, receipt):
    with pytest.raises(ValueError, match="future or expired"):
        solve(monkeypatch, declared(), alter=lambda d: d["sources"]["surface"].update(availableAt=receipt))


def test_speed_outside_declared_envelope_remains_rejected(monkeypatch):
    p = solve(monkeypatch, declared(alternativeSpeedKn=7))
    assert p.options[1].status == "REJECTED"
    assert p.options[1].rejected_by[0].key == "speed_envelope"


def test_undeparted_delay_has_distinct_location_and_timeline(monkeypatch):
    plan = declared(referenceKind="NOT_DEPARTED", referenceAt=stamp(2), remainingDistanceNm=216,
        departureDelayHours=4, departureHoldPermitted=True, departureHoldLocation="Declared demo origin anchorage")
    p = solve(monkeypatch, plan)
    delayed = next(o for o in p.options if o.action == "DELAY_DEPARTURE")
    assert delayed.evaluation.derived["departureAt"] == stamp(6)
    assert delayed.evaluation.derived["sailingHours"] == 18
    assert delayed.evaluation.derived["arrivalAt"] == stamp(24)
    assert delayed.evaluation.derived["holdHours"] == 4
    assert delayed.evaluation.derived["anchorageWaitHours"] == 0
    assert delayed.evaluation.derived["totalElapsedHours"] == 22
    assert delayed.timeline[1]["hours"] == 4


def test_edited_input_creates_new_frozen_version_without_mutating_old(monkeypatch):
    first = solve(monkeypatch, declared(finance=economics()))
    frozen = copy.deepcopy(first.to_dict())
    next_inputs = economics(); next_inputs["fuelPrice"]["amount"] = 650
    second = solve(monkeypatch, declared(finance=next_inputs))
    assert first.to_dict() == frozen
    assert first.decision_id != second.decision_id
    assert first.evidence["currentEnvironment"]["evidenceId"] != second.evidence["currentEnvironment"]["evidenceId"]
    assert first.baseline.option_id != second.baseline.option_id
    assert first.baseline.params == second.baseline.params


def test_speed_choice_preserves_elapsed_common_sailing(monkeypatch):
    p = solve(monkeypatch, declared(referenceAt=stamp(-1), remainingDistanceNm=252,
        alternativeSpeedKn=8, deadlineAt=stamp(30.25), finance=economics()))
    slow = p.options[1]
    d = slow.evaluation.derived
    assert d["commonElapsedSailingHours"] == 1
    assert d["futureSailingHours"] == 30  # 12 nm already sailed at 12 kn; 240 nm remain.
    assert d["sailingHours"] == 31
    assert d["arrivalAt"] == stamp(30)
    assert d["approachClearAt"] == stamp(30)
    assert d["deadlineMet"] is True and slow.status == "FEASIBLE"
    summary = p.evidence["currentEnvironment"]["passageComparison"]["options"][1]
    segments = summary["fuel"]["modes"]["sailing"]["segments"]
    assert segments[0]["speedKn"] == 12 and segments[0]["hours"] == 1
    assert segments[1]["speedKn"] == 8 and segments[1]["hours"] == 30
    assert summary["fuel"]["totalTonnes"] == pytest.approx(26/24 + (24*(8/12)**3+2)*30/24)
    assert p.evidence["currentEnvironment"]["passagePlan"]["remainingDistanceNm"] == 252


def test_malformed_departure_hold_location_cannot_enable_action(monkeypatch):
    p = solve(monkeypatch, declared(referenceKind="NOT_DEPARTED", referenceAt=stamp(2),
        remainingDistanceNm=216, departureDelayHours=4, departureHoldPermitted=True,
        departureHoldLocation={"not": "a declared location"}))
    assert all(o.action != "DELAY_DEPARTURE" for o in p.options)
    action = next(a for a in p.available_actions if a["kind"] == "DELAY_DEPARTURE")
    assert action["availability"]["status"] == "INSUFFICIENT_DATA"
