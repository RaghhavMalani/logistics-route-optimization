"""Synthetic/doc-schema qualification tests; these do not establish live access."""
from datetime import datetime, timezone
import hashlib
import json

import pytest

from src.portwatch_os.intelligence.oceans_x import (
    MAX_BYTES, MAX_RECORDS, backend_configuration, build_request,
    qualification_status, validate_documented_payload,
)


def sample(product="arrivals"):
    field = "arrivedTime" if product == "arrivals" else "duetoArriveTime"
    return [{"vesselParticulars": {"vesselName": "SYNTHETIC TEST VESSEL", "callSign": "TEST",
        "imoNumber": "9941398", "flag": "TEST"}, field: "2026-10-17 00:00:00",
        "locationFrom": "TEST_FROM", "locationTo": "TEST_TO"}]


def encode(rows):
    return json.dumps(rows).encode()


def test_public_status_is_document_review_not_live_source(monkeypatch):
    monkeypatch.setenv("OCEANS_X_API_KEY", "secret-test-key")
    status = qualification_status()
    assert status["enabled"] is False
    assert status["status"] == "DOCS_REVIEWED_AUTHENTICATED_RESPONSE_UNVERIFIED"
    assert not status["access"]["authenticatedResponseVerified"]
    assert not status["restrictionFeed"] and not status["allFastEvidence"]
    assert not status["outcomeReconciliationEnabled"] and not status["calculationSupported"]
    assert "secret-test-key" not in json.dumps(status)
    assert "credentialConfigured" not in json.dumps(status)
    assert len(status["products"]) == 2
    assert all(p["clockLimits"]["responseClockTimezone"] is None for p in status["products"])
    status["products"][0]["name"] = "mutated by caller"
    assert qualification_status()["products"][0]["name"] != "mutated by caller"


def test_backend_configuration_only_reports_presence(monkeypatch):
    monkeypatch.delenv("OCEANS_X_API_KEY", raising=False)
    assert backend_configuration()["credentialConfigured"] is False
    monkeypatch.setenv("OCEANS_X_API_KEY", "private-test-key")
    status = backend_configuration()
    assert status["credentialConfigured"] is True and not status["enabled"]
    assert "private-test-key" not in json.dumps(status)


@pytest.mark.parametrize("product,path", [("arrivals", "arrivals"), ("due", "duetoarrive")])
def test_request_only_constructs_reviewed_https_operation(monkeypatch, product, path):
    monkeypatch.setenv("OCEANS_X_API_KEY", "private-test-key")
    request = build_request(product, "2026-10-17", at=datetime(2026, 10, 16, 16, tzinfo=timezone.utc))
    assert request.full_url == f"https://oceans-x.mpa.gov.sg/api/v1/vessel/{path}/1.0.0/date/2026-10-17"
    assert request.get_method() == "GET" and request.get_header("Apikey") == "private-test-key"


def test_request_window_uses_singapore_calendar_day(monkeypatch):
    monkeypatch.setenv("OCEANS_X_API_KEY", "test-key")
    # UTC Oct 16 16:00 is already Oct 17 in Singapore.
    at = datetime(2026, 10, 16, 16, tzinfo=timezone.utc)
    assert build_request("arrivals", "2026-10-20", at=at)
    assert build_request("arrivals", "2026-10-14", at=at)
    with pytest.raises(ValueError, match="within three days"):
        build_request("arrivals", "2026-10-13", at=at)
    with pytest.raises(ValueError, match="within three days"):
        build_request("arrivals", "2026-10-21", at=at)


@pytest.mark.parametrize("value", ["2026-02-30", "2026-1-17", "2026-10-17/../../admin", None])
def test_invalid_date_rejected_before_request(monkeypatch, value):
    monkeypatch.setenv("OCEANS_X_API_KEY", "test-key")
    with pytest.raises(ValueError, match="calendar date"):
        build_request("arrivals", value)


def test_missing_or_invalid_private_key_rejected_without_echo(monkeypatch):
    at = datetime(2026, 10, 17, tzinfo=timezone.utc)
    monkeypatch.delenv("OCEANS_X_API_KEY", raising=False)
    with pytest.raises(ValueError, match="issued backend API key"):
        build_request("arrivals", "2026-10-17", at=at)
    for key in ("bad\r\nkey", "bad key", "x" * 8193):
        monkeypatch.setenv("OCEANS_X_API_KEY", key)
        with pytest.raises(ValueError) as error:
            build_request("arrivals", "2026-10-17", at=at)
        assert key not in str(error.value)
    monkeypatch.setenv("OCEANS_X_API_KEY", "valid-key")
    with pytest.raises(ValueError, match="timezone-aware"):
        build_request("arrivals", "2026-10-17", at=datetime(2026, 10, 17))
    with pytest.raises(ValueError, match="Unsupported"):
        build_request("https://unreviewed.invalid", "2026-10-17", at=at)


@pytest.mark.parametrize("product", ["arrivals", "due"])
def test_documented_layout_preserves_raw_clock_but_assigns_no_actual_meaning(product):
    raw = encode(sample(product))
    result = validate_documented_payload(raw, product)
    assert result["sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["status"] == "LAYOUT_VALIDATED_SEMANTICS_UNVERIFIED"
    record = result["records"][0]
    assert record["documentedFields"] == sample(product)[0]
    assert record["rawEventTime"] == "2026-10-17 00:00:00"
    assert record["eventAt"] is None and record["timezone"] is None
    assert record["portCallId"] is None and record["allFastAt"] is None
    assert record["sourcePublicationAt"] is None
    assert record["eligibleForRealOutcome"] is False
    assert not result["calculationSupported"] and not result["outcomeReconciliationEnabled"]


@pytest.mark.parametrize("raw", [b"", b"null", b"{}", b"not json", b"\xff", b" " * (MAX_BYTES + 1)],
    ids=["empty", "null", "object", "invalid-json", "invalid-utf8", "oversize"])
def test_non_documented_or_unbounded_body_rejected(raw):
    with pytest.raises(ValueError):
        validate_documented_payload(raw, "arrivals")


def test_too_many_records_rejected():
    with pytest.raises(ValueError, match="bounded vessel array"):
        validate_documented_payload(encode(sample() * (MAX_RECORDS + 1)), "arrivals")


@pytest.mark.parametrize("change", ["extra_field", "wrong_product", "missing_vessel", "null_imo", "clock_offset", "clock_invalid", "clock_loose", "control_text"])
def test_schema_or_clock_drift_requires_review(change):
    rows = sample()
    if change == "extra_field": rows[0]["allFastAt"] = "2026-10-17T00:00:00Z"
    elif change == "wrong_product": rows = sample("due")
    elif change == "missing_vessel": del rows[0]["vesselParticulars"]["callSign"]
    elif change == "null_imo": rows[0]["vesselParticulars"]["imoNumber"] = None
    elif change == "clock_offset": rows[0]["arrivedTime"] = "2026-10-17T00:00:00+08:00"
    elif change == "clock_invalid": rows[0]["arrivedTime"] = "2026-02-30 00:00:00"
    elif change == "clock_loose": rows[0]["arrivedTime"] = "2026-10-7 0:00:00"
    else: rows[0]["locationFrom"] = "TEST\nLOCATION"
    with pytest.raises(ValueError):
        validate_documented_payload(encode(rows), "arrivals")


def test_bad_imo_is_preserved_with_flag_not_silently_corrected():
    rows = sample()
    rows[0]["vesselParticulars"]["imoNumber"] = "9941399"
    record = validate_documented_payload(encode(rows), "arrivals")["records"][0]
    assert record["documentedFields"]["vesselParticulars"]["imoNumber"] == "9941399"
    assert "IMO_CHECK_DIGIT_UNVERIFIED_OR_INVALID" in record["flags"]
    assert record["eligibleForRealOutcome"] is False


def test_empty_documented_array_is_not_an_arrival():
    result = validate_documented_payload(b"[]", "arrivals")
    assert result["records"] == [] and result["outcomeReconciliationEnabled"] is False
