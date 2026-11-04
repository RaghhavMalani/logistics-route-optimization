"""Projection checks over isolated retained originals; no provider requests."""
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.portwatch_os.intelligence import operational_feed as feed
from src.portwatch_os.intelligence import operational_quality as quality
from src.portwatch_os.intelligence.public_ports import (
    CHENNAI_ETA, CHENNAI_POSITION, PublicPilot, record, stamp,
)

NOW = datetime(2026, 10, 22, 10, tzinfo=timezone.utc)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(quality, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(quality, "DATA_DIR", tmp_path / "data")
    return tmp_path


def retained(isolated, *, day="2026-10-15", received=NOW, calls=15):
    archive = feed.AggregateArchive(isolated / "state" / "public_port_pilot")
    payload = json.dumps({"features": [{"attributes": {
        "portid": "port776", "date": day, "portcalls": calls,
        "import": 19, "export": 20}}]}).encode()
    receipt = archive.retain(payload, port="INNSA", url=feed.IMF_ENDPOINT,
        received_at=received)
    return archive, receipt


def aggregate_row(now=NOW):
    return next(row for row in quality.operational_source_rows(now)
        if row["source"].startswith("IMF"))


def write_legacy(isolated, text):
    folder = isolated / "data" / "portwatch"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "port_activity.csv").write_text(text, encoding="utf-8")
    return folder


def test_read_absent_archives_does_not_create_paths_or_collect(isolated):
    with patch.object(feed.AggregateArchive, "__init__", side_effect=AssertionError("write constructor")), \
         patch.object(PublicPilot, "__init__", side_effect=AssertionError("write constructor")), \
         patch.object(feed, "collect_aggregate", side_effect=AssertionError("network read")):
        rows = quality.operational_source_rows(NOW)
    assert len(rows) == 4 and all(row["status"] == "UNAVAILABLE" for row in rows)
    assert list(isolated.iterdir()) == []


def test_retained_aggregate_hash_identity_date_only_mapping_and_unknown_accuracy(isolated):
    _, receipt = retained(isolated)
    row = aggregate_row()
    q = row["sourceQuality"]
    assert q["provenance"]["sourceReceiptId"] == receipt["receiptId"]
    assert q["provenance"]["originalHash"] == receipt["sha256"]
    assert q["provenance"]["originalRef"] == feed.IMF_ENDPOINT
    assert q["semantics"]["originalHashVerified"]
    assert q["coverage"]["portCodes"] == ["INNSA"]
    assert q["coverage"]["variables"] == ["portcalls"]
    assert q["coverage"]["observedThrough"] == "2026-10-15"
    assert q["coverage"]["datePrecision"] == "DATE_ONLY"
    assert q["coverage"]["observationAgeSeconds"] is None
    assert q["quality"]["confidence"] is None
    assert q["semantics"]["physicalPortMapping"] == [{"sourcePortId": "port776", "portCode": "INNSA"}]
    assert row["status"] == "STALE"
    assert q["receipt"]["status"] == "CACHED_LIVE"
    assert q["semantics"]["observationAgeDays"] == 7
    assert "not an individual" in q["semantics"]["meaning"]


def test_check_only_clock_does_not_forge_new_original_receipt_or_frozen_context(isolated):
    archive, receipt = retained(isolated, received=NOW-timedelta(hours=2))
    before = quality.freeze_activity_context("INNSA", now=NOW)
    archive.check("INNSA", NOW+timedelta(minutes=5))
    later = aggregate_row(NOW+timedelta(minutes=6))["sourceQuality"]
    assert later["receipt"]["lastCheckedAt"] == stamp(NOW+timedelta(minutes=5))
    assert later["receipt"]["lastFetchedAt"] == receipt["receivedAt"]
    assert later["semantics"]["firstAvailableAt"] == receipt["receivedAt"]
    assert quality.freeze_activity_context("INNSA", now=NOW+timedelta(minutes=6)) == before


def test_revision_and_restart_keep_first_original_and_new_receipts_distinct(isolated):
    archive, first = retained(isolated, received=NOW-timedelta(hours=2))
    repeated = archive.retain((archive.root/(first["sha256"]+".response")).read_bytes(),
        port="INNSA", url=feed.IMF_ENDPOINT, received_at=NOW-timedelta(hours=1))
    q = aggregate_row()["sourceQuality"]
    assert q["provenance"]["sourceReceiptId"] == repeated["receiptId"]
    assert q["semantics"]["firstAvailableAt"] == first["receivedAt"]
    _, revision = retained(isolated, calls=16)
    q2 = aggregate_row()["sourceQuality"]
    assert q2["semantics"]["firstAvailableAt"] == revision["receivedAt"]
    assert len(q2["semantics"]["receiptHistory"]) == 3
    assert q2["semantics"]["revisionLineage"] is None
    assert aggregate_row()["sourceQuality"] == q2


@pytest.mark.parametrize("kind", ["bytes", "receipt", "parsed"])
def test_bad_aggregate_original_or_metadata_does_not_claim_coverage(isolated, kind):
    archive, receipt = retained(isolated)
    if kind == "bytes":
        (archive.root/(receipt["sha256"]+".response")).write_bytes(b"tampered")
    else:
        if kind == "receipt":
            receipt["receivedAt"] = stamp(NOW-timedelta(minutes=1))
        else:
            receipt["records"][0]["portcalls"] = 999
        (archive.root/(receipt["receiptId"]+".json")).write_text(json.dumps(receipt), encoding="utf-8")
    row = aggregate_row()
    assert row["status"] == "UNAVAILABLE"
    q = row["sourceQuality"]
    assert q["provenance"]["originalHash"] is None
    assert q["coverage"]["portCodes"] == []
    assert "RETAINED_EVIDENCE_UNVERIFIED" in q["quality"]["issues"]
    assert str(isolated) not in json.dumps(row)


def test_failed_provider_check_preserves_last_successful_original(isolated):
    archive, first = retained(isolated, received=NOW-timedelta(hours=1))
    archive.check("INNSA", NOW, "secret local C:/private/state path")
    q = aggregate_row()["sourceQuality"]
    assert q["provenance"]["originalHash"] == first["sha256"]
    assert q["semantics"]["sourceCheckStatus"] == "FAILED"
    assert "secret" not in json.dumps(q) and "C:/private" not in json.dumps(q)


def test_future_receipt_is_not_available_on_read(isolated):
    retained(isolated, received=NOW+timedelta(minutes=1))
    assert aggregate_row()["sourceQuality"]["provenance"]["originalHash"] is None


def test_legacy_csv_actual_partial_coverage_no_manufactured_receipt_or_hash(isolated):
    write_legacy(isolated, "date,portid,portcalls,import,export\n"
        "2026-10-15,port776,15,,NaN\n"
        "2026-10-15,port235,,12,\n"
        "2026-10-15,port207,3,,\n"
        "2026-10-15,port442,4,,\n"
        "2026-10-15,port883,,,\n"
        "2026-10-15,port2038,5,6,7\n"
        "2026-10-23,port777,5,6,7\n")
    with patch.object(quality, "_now", return_value=NOW):
        q = quality.quality_for_activity_source("AIS / vessel activity", {
            "status": "CACHED_LIVE", "provider": "IMF PortWatch (satellite-AIS)",
            "fetched_at": stamp(NOW), "confidence": .9, "rows": 999})
    assert q["coverage"]["portCodes"] == ["INCCU", "INMAA", "INNSA"]
    assert q["coverage"]["variables"] == ["import", "portcalls"]
    assert q["quality"]["rowCount"] == 4
    assert q["quality"]["confidence"] is None
    assert q["receipt"]["lastFetchedAt"] is None
    assert q["receipt"]["lastCheckedAt"] is None
    assert q["provenance"]["originalHash"] is None
    assert q["provenance"]["sourceReceiptId"] is None
    assert q["semantics"]["firstAvailableAt"] is None
    assert q["semantics"]["suppliedValueCounts"] == {"import": 1, "portcalls": 3}
    assert "proxy" in q["semantics"]["derivations"]["delay_hours"]
    json.dumps(q, allow_nan=False)


def test_legacy_dedup_keeps_actual_history_values_without_dense_grid_fill(isolated):
    folder = write_legacy(isolated, "date,portid,portcalls,import,export\n2026-10-15,port776,9,5,6\n2026-10-17,port776,2,3,4\n")
    (folder/"history").mkdir()
    (folder/"history"/"port776.csv").write_text("date,portcalls,import,export\n2026-10-15,3,,\n", encoding="utf-8")
    rows = quality._legacy_activity_rows(NOW)
    assert len(rows) == 2
    assert next(r for r in rows if r["date"] == "2026-10-15")["values"] == {"portcalls": 3.0}


@pytest.mark.parametrize("name,provider,status", [
    ("AIS / vessel activity", "AISStream", "LIVE"),
    ("AIS / vessel activity", "IMF PortWatch", "SYNTHETIC"),
    ("Weather", "IMF PortWatch", "CACHED_LIVE"),
    ("Chokepoints (IMF PortWatch)", "", "LIVE"),
])
def test_unrelated_or_synthetic_products_are_not_relabelled(name, provider, status):
    assert quality.quality_for_activity_source(name, {"provider": provider, "status": status}) is None


def test_frozen_legacy_context_selects_physical_port_and_survives_unrelated_refresh(isolated):
    folder = write_legacy(isolated, "date,portid,portcalls,import,export\n2026-10-15,port776,12,,\n2026-10-20,port235,3,,\n")
    frozen = quality.freeze_activity_context("JNPT", now=NOW)
    assert frozen["observationDate"] == "2026-10-15"
    assert frozen["portCode"] == "INNSA" and frozen["datePrecision"] == "DATE_ONLY"
    assert frozen["calculationEffect"] == "NONE" and frozen["operationalUse"] == "CONTEXT_ONLY"
    assert frozen["unknownReason"] and frozen["originalHash"] is None
    with (folder/"port_activity.csv").open("a", encoding="utf-8") as stream:
        stream.write("2026-10-22,port883,9,,\n")
    assert quality.freeze_activity_context("INNSA", now=NOW+timedelta(hours=1)) == frozen
    assert quality.freeze_activity_context("INBOM", now=NOW)["observationDate"] is None


def test_public_pdf_source_uses_original_and_keeps_eta_arrival_berth_distinct(isolated):
    store = PublicPilot(isolated/"state"/"public_port_pilot")
    eta = record("expected", "TEST SHIP", "190", "32", "9", "A1",
        {"etaAt": "23/10/2026 12:00"}, NOW.date(), 0)
    eta["recordId"] = "eta-record"
    reported = record("reported", "TEST SHIP", "190", "32", "9", "A1",
        {"arrivalAt": "21/10/2026 12:00", "berthAt": "22/10/2026 11:00"}, NOW.date(), 0)
    reported["recordId"] = "arrival-record"
    bodies = {"expected": {"reportDate": "2026-10-22", "records": [eta], "issues": []},
        "position": {"reportDate": "2026-10-22", "records": [reported], "issues": []}}
    def parse(raw, port, kind):
        return copy.deepcopy(bodies[kind])
    with patch("src.portwatch_os.intelligence.public_ports.parse_pdf", side_effect=parse):
        first = store.import_pdf("INMAA", "expected", CHENNAI_ETA, b"%PDF-eta", collected=NOW, actor="test")
        store.import_pdf("INMAA", "position", CHENNAI_POSITION, b"%PDF-position", collected=NOW, actor="test")
    store.close()
    before = {path: path.read_bytes() for path in (isolated/"state").rglob("*") if path.is_file()}
    with patch.object(quality, "parse_pdf", side_effect=parse), \
         patch.object(PublicPilot, "__init__", side_effect=AssertionError("read mutation")):
        rows = quality.operational_source_rows(NOW)
    expected = next(row["sourceQuality"] for row in rows if row["source"] == "Chennai published expected arrivals")
    actual = next(row["sourceQuality"] for row in rows if row["source"] == "Chennai published vessel position")
    assert expected["temporalRole"] == "FORECAST" and expected["valueKinds"] == ["FORECAST"]
    assert expected["provenance"]["sourceReceiptId"] == first["snapshotId"]
    assert expected["coverage"]["observedThrough"] is None
    assert expected["coverage"]["forecastOriginAt"] is None
    assert expected["coverage"]["targetFrom"] == "2026-10-23T06:30:00+00:00"
    assert actual["coverage"]["observedThrough"] == "2026-10-22T05:30:00+00:00"
    assert actual["coverage"]["datePrecision"] == "INSTANT"
    assert actual["semantics"]["reportDatePrecision"] == "DATE_ONLY"
    assert actual["semantics"]["eventPeriods"]["arrivalAt"]["from"] != actual["semantics"]["eventPeriods"]["berthAt"]["from"]
    assert actual["semantics"]["confirmedAllFast"] is False
    assert "etaAt" not in actual["coverage"]["variables"]
    assert before == {path: path.read_bytes() for path in (isolated/"state").rglob("*") if path.is_file()}
    assert str(isolated) not in json.dumps(rows)


def test_public_bad_optional_metadata_or_hash_is_unavailable_without_path_leak(isolated):
    store = PublicPilot(isolated/"state"/"public_port_pilot")
    body = {"reportDate": "2026-10-22", "records": [], "issues": []}
    with patch("src.portwatch_os.intelligence.public_ports.parse_pdf", return_value=body):
        stored = store.import_pdf("INMAA", "expected", CHENNAI_ETA, b"%PDF-bad", collected=NOW, actor="test")
    store.close()
    (isolated/"state"/"public_port_pilot"/"evidence"/(quality.digest(b"%PDF-bad")+".pdf")).write_bytes(b"broken")
    rows = quality.operational_source_rows(NOW)
    row = next(row for row in rows if row["source"] == "Chennai published expected arrivals")
    assert row["status"] == "UNAVAILABLE"
    assert row["sourceQuality"]["provenance"]["originalHash"] is None
    assert str(isolated) not in json.dumps(rows)


def test_late_malformed_public_metadata_clears_partly_projected_identity(isolated):
    store = PublicPilot(isolated/"state"/"public_port_pilot")
    body = {"reportDate": "2026-10-22", "records": [], "issues": []}
    with patch("src.portwatch_os.intelligence.public_ports.parse_pdf", return_value=body):
        stored = store.import_pdf("INMAA", "position", CHENNAI_POSITION, b"%PDF-malformed", collected=NOW, actor="test")
    body["issues"] = None
    store.db.execute("UPDATE snapshots SET body=? WHERE id=?", (json.dumps(body), stored["snapshotId"]))
    store.db.commit()
    store.close()
    with patch.object(quality, "parse_pdf", return_value=body):
        rows = quality.operational_source_rows(NOW)
    q = next(row["sourceQuality"] for row in rows if row["source"] == "Chennai published vessel position")
    assert q["receipt"]["status"] == "UNAVAILABLE"
    assert q["provenance"]["sourceReceiptId"] is None
    assert q["provenance"]["originalHash"] is None
    assert q["coverage"]["portCodes"] == []


def test_future_reported_actual_is_not_projected_as_current_observed_period(isolated):
    store = PublicPilot(isolated/"state"/"public_port_pilot")
    reported = record("reported", "FUTURE SHIP", "190", "32", "9", "A1",
        {"arrivalAt": "22/10/2026 22:00"}, NOW.date(), 0)
    reported["recordId"] = "future-arrival-record"
    body = {"reportDate": "2026-10-22", "records": [reported], "issues": []}
    with patch("src.portwatch_os.intelligence.public_ports.parse_pdf", return_value=body):
        store.import_pdf("INMAA", "position", CHENNAI_POSITION, b"%PDF-future", collected=NOW, actor="test")
    store.close()
    with patch.object(quality, "parse_pdf", return_value=body):
        rows = quality.operational_source_rows(NOW)
    q = next(row["sourceQuality"] for row in rows if row["source"] == "Chennai published vessel position")
    assert q["coverage"]["observedThrough"] is None
    assert q["semantics"]["eventPeriods"]["arrivalAt"] is None
    assert any("FUTURE_REPORTED_EVENT_WITHHELD" in issue for issue in q["quality"]["issues"])
