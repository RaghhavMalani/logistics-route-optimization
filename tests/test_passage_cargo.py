"""Deterministic connection arithmetic; all inputs here are fictional assumptions."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from src.portwatch_os.cargo.model import Shipment, total_handling_hours
from src.portwatch_os.decision.passage_cargo import evaluate_commitment, validate_commitment

AT = datetime(2026, 10, 29, 18, 30, tzinfo=timezone.utc)


def stamp(hours=0):
    return (AT + timedelta(hours=hours)).isoformat()


def declaration():
    return {"schemaVersion": 1, "fictionalShipment": True, "voyageId": "OWN-001", "portCode": "INNSA",
        "declaredAt": stamp(), "basis": "Explicit fictional cargo scenario; no commercial manifest", "mustMeet": False,
        "shipment": {"shipmentId": "fictional-connection-001", "teu": 24., "cargoClass": "dry",
            "destinationPort": "SGSIN", "weightT": 240.},
        "transfer": {"approachToStartHours": 2., "basis": "Assumed berth/access interval before discharge starts",
            "acceptedSchematicHandling": True, "gangs": 1, "mode": "DIRECT"},
        "bookedConnection": {"vesselId": "fictional-booked-001", "name": "Fictional booked sailing",
            "departureAt": stamp(12), "loadingCutoffAt": stamp(10), "onwardPorts": ["SGSIN"],
            "availableTeu": 100., "availableDeadweightT": 1000., "availableReeferPlugs": 30,
            "acceptsHazardous": True, "acceptsOog": True, "basis": "Operator-declared fictional sailing/capacity"},
        "laterConnections": []}


def normalize(raw=None):
    return validate_commitment(raw or declaration(), voyage_id="OWN-001", port_code="INNSA", at=AT)


def assess(raw=None, clear=4, option="passage-current"):
    return evaluate_commitment(normalize(raw), clear_approach_at=stamp(clear) if clear is not None else None,
        option_id=option, source_passage_id="passage-inputs-fixture")


def test_same_gate_means_same_cargo_readiness_not_less_anchorage_benefit():
    baseline, slow = assess(option="baseline"), assess(option="slow")
    for key in ("startAt", "readinessAt", "slackHours", "handlingHours", "stages"):
        assert baseline[key] == slow[key]
    assert baseline["status"] == "COMPATIBLE_UNDER_ASSUMPTIONS"
    assert baseline["startAt"] == stamp(6)
    expected = 24 / 24 + 1.5 + 24 / 22
    assert baseline["handlingHours"] == pytest.approx(expected)
    assert baseline["slackHours"] == pytest.approx(10 - 6 - expected)
    assert baseline["readinessAt"] == (AT + timedelta(hours=6 + expected)).isoformat()
    assert baseline["requiredConstraint"]["required"] is False
    assert baseline["financial"]["available"] is False
    assert baseline["finalDeliveryEta"]["available"] is False


def test_later_gate_misses_required_cutoff_and_alternative_is_only_proposal():
    raw = declaration()
    raw["mustMeet"] = True
    later = deepcopy(raw["bookedConnection"])
    later.update(vesselId="fictional-later", name="Declared later sailing", departureAt=stamp(20), loadingCutoffAt=stamp(18))
    raw["laterConnections"] = [later]
    baseline = assess(raw)
    missed = assess(raw, clear=6, option="lower-fuel-later-gate")
    assert baseline["requiredConstraint"] ["passed"] is True
    assert missed["status"] == "BLOCKED"
    assert missed["timingStatus"] == "MISSES"
    assert missed["requiredConstraint"]["passed"] is False
    assert missed["slackHours"] < 0
    assert "closes loading" in " ".join(missed["reasons"])
    alternative = missed["alternatives"][0]
    assert alternative["action"] == "TRANSFER_TO_VESSEL"
    assert alternative["bookingStatus"] == "NOT_RESERVED"
    assert alternative["departureShiftHours"] == 8
    assert alternative["sourcePassageOptionId"] == "lower-fuel-later-gate"
    assert alternative["sourcePassageId"] == "passage-inputs-fixture"


@pytest.mark.parametrize("object_key,key", [("bookedConnection", "loadingCutoffAt"), ("transfer", "approachToStartHours"),
    ("bookedConnection", "availableTeu"), ("bookedConnection", "availableDeadweightT"), ("transfer", "basis")])
def test_missing_inputs_are_unknown_without_implicit_cutoff_or_zero_release(object_key, key):
    raw = declaration()
    del raw[object_key][key]
    result = assess(raw)
    assert result["status"] == "UNKNOWN"
    assert result["requiredConstraint"]["passed"] is None
    assert result["missing"]
    if key == "loadingCutoffAt":
        assert result["cutoffHour"] is None and result["cutoffAt"] is None
        assert result["slackHours"] is None and result["readinessAt"] is None
    if key == "approachToStartHours":
        assert result["startAt"] is None and result["readinessAt"] is None
    if key in ("availableTeu", "availableDeadweightT"):
        assert result["timingStatus"] == "FITS"


@pytest.mark.parametrize("cargo_class,change,reason", [
    ("dry", {"availableTeu": 20.}, "TEU"),
    ("reefer", {"availableReeferPlugs": 10}, "reefer plugs"),
    ("hazardous", {"acceptsHazardous": False}, "IMDG"),
    ("oog", {"acceptsOog": False}, "out-of-gauge"),
    ("dry", {"availableDeadweightT": 200}, "deadweight"),
    ("dry", {"onwardPorts": ["AEJEA"]}, "does not call"),
])
def test_existing_capacity_eligibility_rules_block_even_with_timing_fit(cargo_class, change, reason):
    raw = declaration()
    raw["shipment"]["cargoClass"] = cargo_class
    raw["bookedConnection"].update(change, loadingCutoffAt=stamp(20), departureAt=stamp(22))
    result = assess(raw)
    assert result["timingStatus"] == "FITS"
    assert result["status"] == "BLOCKED"
    assert reason in " ".join(result["reasons"])


def test_missing_class_specific_eligibility_keeps_unknown():
    raw = declaration()
    raw["shipment"]["cargoClass"] = "hazardous"
    del raw["bookedConnection"]["acceptsHazardous"]
    raw["bookedConnection"].update(loadingCutoffAt=stamp(20), departureAt=stamp(22))
    result = assess(raw)
    assert result["timingStatus"] == "FITS"
    assert result["status"] == "UNKNOWN"
    assert "connection.acceptsHazardous" in result["missing"]


@pytest.mark.parametrize("cargo_class,key", [("hazardous", "acceptsHazardous"), ("oog", "acceptsOog")])
def test_explicit_null_eligibility_is_unknown_not_a_known_rejection(cargo_class, key):
    raw = declaration()
    raw["shipment"]["cargoClass"] = cargo_class
    raw["bookedConnection"].update(loadingCutoffAt=stamp(20), departureAt=stamp(22))
    raw["bookedConnection"][key] = None
    result = assess(raw)
    assert result["status"] == "UNKNOWN" and not result["reasons"]


def test_offset_and_day_boundary_share_exact_utc_hour_reference():
    raw = declaration()
    raw["declaredAt"] = "2026-10-30T00:00:00+05:30"
    raw["bookedConnection"]["loadingCutoffAt"] = "2026-10-30T10:00:00+05:30"
    normalized = normalize(raw)
    assert normalized["conversionReferenceAt"] == stamp()
    result = evaluate_commitment(normalized, clear_approach_at="2026-10-30T04:00:00+05:30", option_id="same-clock")
    assert result["startAt"] == stamp(6)
    assert result["cutoffHour"] == 10


def test_yard_handling_counted_once_and_unknown_yard_does_not_mean_direct():
    raw = declaration()
    raw["transfer"].update(mode="YARD", zone={"zoneId": "fictional-yard", "name": "Declared demonstration yard",
        "freeTeu": 100, "capacityTeu": 200, "quayTransferMinutesPerTeu": 1.25})
    raw["bookedConnection"].update(loadingCutoffAt=stamp(20), departureAt=stamp(22))
    result = assess(raw)
    assert result["stages"]["yardMovesHours"] == 1
    assert result["handlingHours"] == pytest.approx(total_handling_hours(Shipment("s", 24, "dry", "SGSIN"), None) + 1)
    assert sum(v for k, v in result["stages"].items() if k != "totalHandlingHours") == pytest.approx(result["handlingHours"])
    del raw["transfer"]["zone"]
    unknown = assess(raw)
    assert unknown["status"] == "UNKNOWN" and unknown["handlingHours"] is None


def test_latest_departure_is_independent_of_loading_slack():
    raw = declaration()
    raw["shipment"]["latestDepartureAt"] = stamp(11)
    result = assess(raw)
    assert result["timingStatus"] == "FITS" and result["status"] == "BLOCKED"
    assert "commitment" in " ".join(result["reasons"])


def test_other_gang_counts_do_not_silently_use_single_gang_alternative_engine():
    raw = declaration()
    raw["transfer"]["gangs"] = 2
    raw["bookedConnection"].update(loadingCutoffAt=stamp(7), departureAt=stamp(9))
    later = deepcopy(raw["bookedConnection"])
    later.update(vesselId="later", loadingCutoffAt=stamp(20), departureAt=stamp(22))
    raw["laterConnections"] = [later]
    result = assess(raw)
    assert result["status"] == "BLOCKED"
    assert result["handlingHours"] == pytest.approx(24 / 24 / 2 + 1.5 + 24 / 22 / 2)
    assert result["alternatives"] == []
    assert "single-gang" in result["alternativesUnavailableBecause"]


def test_immutable_input_and_result_identity_no_wall_clock_consumption():
    raw = declaration()
    original = deepcopy(raw)
    one, two = assess(raw), assess(raw)
    assert raw == original and one == two
    assert len(one["assessmentId"].split("-")[-1]) == 64
    changed = deepcopy(raw)
    changed["bookedConnection"]["availableTeu"] = 50
    assert assess(changed)["inputVersion"] != one["inputVersion"]


def test_normalized_declaration_retry_discards_derived_fields_before_identity():
    first = normalize()
    assert normalize(first) == first
    carried = deepcopy(first)
    carried["inputVersion"] = "untrusted-old-version"
    carried["conversionReferenceAt"] = stamp(-5)
    carried["version"] = "untrusted-old-version"
    assert normalize(carried) == first


def test_missing_destination_is_unknown_not_placeholder_incompatibility():
    raw = declaration()
    del raw["shipment"]["destinationPort"]
    result = assess(raw)
    assert result["status"] == "UNKNOWN"
    assert result["timingStatus"] == "FITS"
    assert not result["reasons"]


@pytest.mark.parametrize("mutation", [lambda r: r.update(voyageId="another-visitor"), lambda r: r.update(portCode="INMAA"),
    lambda r: r.update(fictionalShipment=False), lambda r: r.update(mustMeet="yes"),
    lambda r: r["bookedConnection"].update(loadingCutoffAt=stamp(13)),
    lambda r: r["shipment"].update(teu=float("nan")), lambda r: r["transfer"].update(gangs=0),
    lambda r: r["bookedConnection"].update(departureAt="2026-10-30T04:00:00")])
def test_invalid_binding_values_and_naive_times_refused(mutation):
    raw = declaration()
    mutation(raw)
    with pytest.raises(ValueError):
        normalize(raw)


def test_missing_approach_never_claims_timing_or_required_pass():
    raw = declaration()
    raw["mustMeet"] = True
    result = assess(raw, clear=None)
    assert result["status"] == "UNKNOWN" and result["requiredConstraint"]["passed"] is None
    assert result["startAt"] is None and result["readinessAt"] is None
    assert result["alternatives"] == []
