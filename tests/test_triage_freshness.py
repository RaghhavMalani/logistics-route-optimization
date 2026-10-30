"""Retained-input freshness never fetches, writes, advances clocks or learns."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from src.portwatch_os.decision.triage_freshness import (
    collect_retained_dependencies, evaluate_freshness,
)

NOW = datetime(2026, 10, 29, 9, tzinfo=timezone.utc)
RAW = b"retained original hourly weather response"
DIGEST = hashlib.sha256(RAW).hexdigest()


def stamp(hours=0):
    return (NOW + timedelta(hours=hours)).isoformat()


def fixture():
    episode = {"id": "call-owned", "voyageLegId": "leg-owned", "vesselId": "PWD-001", "portCode": "INNSA"}
    world = {"epoch": stamp(), "fleet": [{"id": "PWD-001", "portCode": "INNSA", "etaHours": 20., "operationalEpisode": episode}]}
    basis = {"operationalEpisode": deepcopy(episode), "portCode": "INNSA", "voyageId": "PWD-001",
        "evidenceId": "evidence-owned", "source": "Open-Meteo public hourly forecast",
        "responseSha256": DIGEST, "availableAt": stamp(-.5), "plannedArrival": stamp(20),
        "earliestVoyageArrival": stamp(20)}
    problem = {"decisionId": "owned-comparison", "subject": {"id": "PWD-001"}, "evidence": {"currentEnvironment": basis}}
    retained = {"originalStatuses": {DIGEST: "AVAILABLE"}, "restrictions": {}, "feedbackStatus": {}}
    return problem, world, retained


def codes(result):
    return {r["code"] for r in result["reasons"]}


def test_current_projection_has_no_mutation_and_ignores_unconsumed_global_context():
    problem, world, retained = fixture()
    original = deepcopy((problem, world, retained))
    first = evaluate_freshness(problem, world, as_of=NOW, retained=retained)
    world.update(newsCount=999, reliabilityCounts={"global": 9999}, unusedEconomicVersion="new")
    world["cargoCommitments"] = {"other-shipment": {"inputVersion": "new"}}
    assert evaluate_freshness(problem, world, as_of=NOW, retained=retained) == first
    assert first["status"] == "CURRENT" and not first["reasons"]
    assert problem == original[0] and retained == original[2]


@pytest.mark.parametrize("change,code", [
    (lambda p, w: p["evidence"]["currentEnvironment"].update(availableAt=stamp(-2)), "CONSUMED_RECEIPT_EXPIRED"),
    (lambda p, w: p["evidence"]["currentEnvironment"].update(plannedArrival=stamp(-1)), "REQUESTED_ARRIVAL_ELAPSED"),
    (lambda p, w: w["fleet"][0].update(etaHours=21), "VOYAGE_ETA_CHANGED"),
    (lambda p, w: w["fleet"][0].update(portCode="INMAA"), "VOYAGE_DESTINATION_CHANGED"),
    (lambda p, w: w["fleet"][0]["operationalEpisode"].update(id="new-call"), "CURRENT_CALL_CHANGED"),
    (lambda p, w: w["fleet"][0]["operationalEpisode"].update(voyageLegId="new-leg"), "CURRENT_CALL_CHANGED"),
])
def test_only_consumed_expiry_voyage_or_call_changes_need_reassessment(change, code):
    problem, world, retained = fixture()
    change(problem, world)
    result = evaluate_freshness(problem, world, as_of=NOW, retained=retained)
    assert result["status"] == "REASSESSMENT" and code in codes(result)


def test_eta_edit_is_not_call_creation_and_offsets_compare_by_instant():
    problem, world, retained = fixture()
    basis = problem["evidence"]["currentEnvironment"]
    basis["earliestVoyageArrival"] = (NOW+timedelta(hours=20)).astimezone(timezone(timedelta(hours=5, minutes=30))).isoformat()
    assert evaluate_freshness(problem, world, as_of=NOW, retained=retained)["status"] == "CURRENT"
    world["fleet"][0]["etaHours"] = 22
    result = evaluate_freshness(problem, world, as_of=NOW, retained=retained)
    assert "VOYAGE_ETA_CHANGED" in codes(result) and "CURRENT_CALL_CHANGED" not in codes(result)


def test_traffic_replay_is_independent_of_operational_clock():
    problem, world, retained = fixture()
    world["trafficReplay"] = {"at": stamp(-999), "mode": "REPLAY"}
    assert evaluate_freshness(problem, world, as_of=NOW, retained=retained)["status"] == "CURRENT"
    result = evaluate_freshness(problem, world, as_of=NOW, retained=retained, clock_mode="REPLAY")
    assert "OPERATIONAL_CLOCK_NOT_LIVE" in codes(result)


@pytest.mark.parametrize("status,code", [("MISSING", "MISSING_REQUIRED_ORIGINAL"), ("CORRUPT", "CORRUPT_REQUIRED_ORIGINAL"), (None, "REQUIRED_ORIGINAL_UNCHECKED")])
def test_missing_and_corrupt_originals_remain_distinct(status, code):
    problem, world, retained = fixture()
    retained["originalStatuses"][DIGEST] = status
    result = evaluate_freshness(problem, world, as_of=NOW, retained=retained)
    assert result["status"] == "UNKNOWN" and code in codes(result)
    assert all("path" not in r and "token" not in r for r in result["reasons"])


def test_unsupported_legacy_and_malformed_records_are_unknown_not_clear():
    problem, world, retained = fixture()
    result = evaluate_freshness({"decisionId": "old", "subject": {"id": "PWD-001"}, "evidence": {}}, world, as_of=NOW, retained=retained)
    assert result["status"] == "UNKNOWN" and "UNSUPPORTED_LEGACY_EVIDENCE" in codes(result)
    basis = problem["evidence"]["currentEnvironment"]
    basis.update(availableAt="naive-invalid", plannedArrival=None, earliestVoyageArrival="2026-10-29T10:00:00", responseSha256=None,
        cargoCommitment={"shipment": {"shipmentId": ["malformed"]}}, feedbackConsumption={"id": [], "inputs": None})
    result = evaluate_freshness(problem, world, as_of=NOW, retained=retained)
    assert result["status"] == "UNKNOWN"
    assert {"SOURCE_RECEIPT_UNAVAILABLE", "REQUESTED_ARRIVAL_UNAVAILABLE", "LEGACY_ORIGINAL_IDENTITY_UNAVAILABLE", "CARGO_COMMITMENT_MALFORMED"} <= codes(result)


def test_cargo_version_check_ignores_conversion_origin_but_detects_consumed_edit():
    from src.portwatch_os.decision.passage_cargo_integration import declaration_identity
    problem, world, retained = fixture()
    cargo = {"shipment": {"shipmentId": "owned-shipment"}, "mustMeet": True,
        "bookedConnection": {"loadingCutoffAt": stamp(30)}, "conversionReferenceAt": stamp(-1), "inputVersion": "old"}
    problem["evidence"]["currentEnvironment"]["cargoCommitment"] = cargo
    world["cargoCommitments"] = {"owned-shipment": {"inputVersion": declaration_identity(cargo)}}
    assert evaluate_freshness(problem, world, as_of=NOW, retained=retained)["status"] == "CURRENT"
    cargo.update(conversionReferenceAt=stamp(-2), inputVersion="different-comparison-origin")
    assert evaluate_freshness(problem, world, as_of=NOW, retained=retained)["status"] == "CURRENT"
    world["cargoCommitments"]["owned-shipment"]["inputVersion"] = "revised-shipment"
    result = evaluate_freshness(problem, world, as_of=NOW, retained=retained)
    assert "CARGO_COMMITMENT_CHANGED" in codes(result)


def restriction_fixture():
    problem, world, retained = fixture()
    basis = problem["evidence"]["currentEnvironment"]
    plan = {"id": "declared-passage", "areaId": "WRIGHTSVILLE_SR74", "route": ["WRIGHTSVILLE_SR74"],
        "passageAt": stamp(3.5), "openingRequired": True, "emergencyTransit": False, "timezoneAssumption": "America/New_York"}
    window = {"start": stamp(3), "end": stamp(4), "timeZone": "America/New_York"}
    notice = {"noticeId": "NAVCEN_MSI:53842", "providerNoticeId": "53842", "sourceFamily": "NAVCEN_MSI",
        "revisionId": "revision-original", "sourceStatus": "CURRENT", "status": "SCHEDULED", "checkedAt": stamp(-1),
        "areaId": plan["areaId"], "windows": [window], "responseSha256": DIGEST}
    basis.update(kind="NOTICE_RESTRICTION", reportedFact=deepcopy(notice), restriction={"sourceFamily": "NAVCEN_MSI",
        "revisionId": notice["revisionId"], "plan": deepcopy(plan)})
    world["fleet"][0]["declaredPassages"] = {plan["areaId"]: deepcopy(plan)}
    retained["restrictions"]["NAVCEN_MSI:53842"] = notice
    return problem, world, retained


def test_retained_restriction_revision_and_applicability_without_refresh():
    problem, world, retained = restriction_fixture()
    assert evaluate_freshness(problem, world, as_of=NOW, retained=retained)["status"] == "CURRENT"
    retained["restrictions"]["NAVCEN_MSI:53842"].update(revisionId="revised", sourceStatus="UNAVAILABLE")
    result = evaluate_freshness(problem, world, as_of=NOW, retained=retained)
    assert {"RESTRICTION_REVISION_CHANGED", "RESTRICTION_SOURCE_UNAVAILABLE_OR_WITHDRAWN"} <= codes(result)
    assert result["status"] == "REASSESSMENT"


def test_restriction_effective_end_and_unknown_catalogue_do_not_establish_occurrence():
    problem, world, retained = restriction_fixture()
    retained["restrictions"]["NAVCEN_MSI:53842"]["productThrough"] = stamp(-.5)
    result = evaluate_freshness(problem, world, as_of=NOW, retained=retained)
    assert "RESTRICTION_EFFECTIVE_PERIOD_ELAPSED" in codes(result)
    assert "actual occurrence remains unknown" in " ".join(r["text"] for r in result["reasons"])
    retained["restrictions"] = {}
    result = evaluate_freshness(problem, world, as_of=NOW, retained=retained)
    assert result["status"] == "UNKNOWN" and "RESTRICTION_CATALOGUE_UNAVAILABLE" in codes(result)


def test_reader_uses_exact_hashes_and_does_not_create_missing_database_or_directories(tmp_path):
    problem, _world, _retained = fixture()
    root, missing_db = tmp_path/"never-created", tmp_path/"no-db"/"public.sqlite3"
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    result = collect_retained_dependencies([problem], environment_root=root, public_feedback_db=missing_db, as_of=NOW)
    assert result["originalStatuses"][DIGEST] == "MISSING"
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before
    folder = root/"archive"; folder.mkdir(parents=True)
    original = folder/(DIGEST+".response"); original.write_bytes(b"changed bytes")
    result = collect_retained_dependencies([problem], environment_root=root, public_feedback_db=missing_db, as_of=NOW)
    assert result["originalStatuses"][DIGEST] == "CORRUPT"
    original.write_bytes(RAW)
    assert collect_retained_dependencies([problem], environment_root=root, public_feedback_db=missing_db, as_of=NOW)["originalStatuses"][DIGEST] == "AVAILABLE"


def feedback_fixture(tmp_path):
    problem, world, _ = fixture()
    root = tmp_path/"public"; (root/"archive").mkdir(parents=True)
    (root/"archive"/(DIGEST+".response")).write_bytes(RAW)
    claim = {"id": "fx-claim", "kind": "FORECAST", "target": {"kind": "ECONOMIC_OBSERVATION", "date": "2026-10-30"},
        "entity": "USD/INR", "geography": "India", "source": "persistence baseline", "unit": "INR/USD", "aggregation": "DAILY",
        "responseSha256": DIGEST, "firstAvailableAt": stamp(-1), "sourceVersion": "v1", "inputs": []}
    consumed = {"id": "consumption-owned", "inputs": [{"claim": claim, "assessment": None}],
        "reliabilityVersion": {"counts": 2}}
    problem["evidence"]["currentEnvironment"]["feedbackConsumption"] = consumed
    db = tmp_path/"public.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE shared_feedback(kind TEXT, id TEXT, body TEXT)")
        conn.execute("INSERT INTO shared_feedback VALUES(?,?,?)", ("claim", claim["id"], json.dumps(claim)))
    return problem, world, root, db


def test_consumer_feedback_reads_existing_predicates_without_writes_or_global_count_dependency(tmp_path):
    problem, world, root, db = feedback_fixture(tmp_path)
    before = db.read_bytes()
    first = collect_retained_dependencies([problem], environment_root=root, public_feedback_db=db, as_of=NOW)
    assert first["feedbackStatus"]["consumption-owned"]["status"] == "CURRENT"
    assert evaluate_freshness(problem, world, as_of=NOW, retained=first)["status"] == "CURRENT"
    assert db.read_bytes() == before
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO shared_feedback VALUES(?,?,?)", ("version", "unused-global-version", json.dumps({"counts": 999})))
    second = collect_retained_dependencies([problem], environment_root=root, public_feedback_db=db, as_of=NOW)
    assert second["feedbackStatus"] == first["feedbackStatus"]


def test_relevant_feedback_assessment_change_is_reassessment(tmp_path):
    problem, world, root, db = feedback_fixture(tmp_path)
    assessment = {"id": "assessment-new", "claimId": "fx-claim", "assessedAt": stamp(-.1),
        "verdict": "CORROBORATED", "applicability": "AS_REPORTED", "evidenceIds": ["later-authority-record"]}
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO shared_feedback VALUES(?,?,?)", ("assessment", assessment["id"], json.dumps(assessment)))
    result = collect_retained_dependencies([problem], environment_root=root, public_feedback_db=db, as_of=NOW)
    assert result["feedbackStatus"]["consumption-owned"]["status"] == "CHANGED"
    assert "CONSUMED_FEEDBACK_CHANGED" in codes(evaluate_freshness(problem, world, as_of=NOW, retained=result))


def test_future_assessment_is_not_yet_a_consumed_change(tmp_path):
    problem, _world, root, db = feedback_fixture(tmp_path)
    assessment = {"id": "future", "claimId": "fx-claim", "assessedAt": stamp(1), "verdict": "CORROBORATED"}
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO shared_feedback VALUES(?,?,?)", ("assessment", "future", json.dumps(assessment)))
    result = collect_retained_dependencies([problem], environment_root=root, public_feedback_db=db, as_of=NOW)
    assert result["feedbackStatus"]["consumption-owned"]["status"] == "CURRENT"


def test_only_a_bound_applied_policy_is_a_dependency(tmp_path):
    from src.portwatch_os.learning.shared_feedback import neutral_dependency
    problem, _world, root, db = feedback_fixture(tmp_path)
    consumed = problem["evidence"]["currentEnvironment"]["feedbackConsumption"]
    claim = consumed["inputs"][0]["claim"]
    neutral = neutral_dependency(claim)
    policy = {"id": "new-policy", "contextKey": neutral["contextKey"], "calculationConsumer": "explicit-shipping-consumer",
        "status": "VALIDATED_APPLIED", "firstAvailableAt": stamp(-.1), "weight": .8, "correction": None}
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO shared_feedback VALUES(?,?,?)", ("applied-policy", policy["id"], json.dumps(policy)))
    unbound = collect_retained_dependencies([problem], environment_root=root, public_feedback_db=db, as_of=NOW)
    assert unbound["feedbackStatus"]["consumption-owned"]["status"] == "CURRENT"
    consumed["appliedDependencies"] = [{**neutral, "calculationConsumer": policy["calculationConsumer"]}]
    bound = collect_retained_dependencies([problem], environment_root=root, public_feedback_db=db, as_of=NOW)
    assert bound["feedbackStatus"]["consumption-owned"]["status"] == "CHANGED"


def test_semantic_passage_edit_cannot_hide_behind_reused_declaration_id():
    problem, world, retained = restriction_fixture()
    world["fleet"][0]["declaredPassages"]["WRIGHTSVILLE_SR74"]["openingRequired"] = False
    result = evaluate_freshness(problem, world, as_of=NOW, retained=retained)
    assert "RESTRICTION_DECLARATION_CHANGED" in codes(result)


def test_read_only_feedback_snapshot_sees_committed_wal_records(tmp_path):
    problem, _world, root, db = feedback_fixture(tmp_path)
    writer = sqlite3.connect(db)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        assessment = {"id": "wal-new", "claimId": "fx-claim", "assessedAt": stamp(-.1), "verdict": "CORROBORATED"}
        writer.execute("INSERT INTO shared_feedback VALUES(?,?,?)", ("assessment", "wal-new", json.dumps(assessment)))
        writer.commit()
        result = collect_retained_dependencies([problem], environment_root=root, public_feedback_db=db, as_of=NOW)
        assert result["feedbackStatus"]["consumption-owned"]["status"] == "CHANGED"
    finally:
        writer.close()


def test_missing_or_malformed_feedback_database_is_unknown_not_reset_or_repaired(tmp_path):
    problem, world, root, db = feedback_fixture(tmp_path)
    missing = tmp_path/"absent"/"public.sqlite3"
    result = collect_retained_dependencies([problem], environment_root=root, public_feedback_db=missing, as_of=NOW)
    assert not missing.exists() and result["feedbackStatus"]["consumption-owned"]["status"] == "UNAVAILABLE"
    assert "CONSUMED_FEEDBACK_UNAVAILABLE" in codes(evaluate_freshness(problem, world, as_of=NOW, retained=result))
    db.write_bytes(b"bad sqlite bytes")
    assert collect_retained_dependencies([problem], environment_root=root, public_feedback_db=db, as_of=NOW)["feedbackStatus"]["consumption-owned"]["status"] == "UNAVAILABLE"
    assert db.read_bytes() == b"bad sqlite bytes"


def test_retained_notice_catalogue_reader_does_not_fetch_or_rewrite(tmp_path):
    problem, _world, _ = restriction_fixture()
    root = tmp_path/"public"; (root/"operational_notices").mkdir(parents=True)
    original = root/"operational_notices"/(DIGEST+".response"); original.write_bytes(RAW)
    latest = root/"operational_notices"/"navcen-catalogue-latest.json"
    notice = problem["evidence"]["currentEnvironment"]["reportedFact"]
    latest.write_text(json.dumps({"notices": [notice]}))
    before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = collect_retained_dependencies([problem], environment_root=root, public_feedback_db=tmp_path/"absent.sqlite3", as_of=NOW)
    assert result["restrictions"]["NAVCEN_MSI:53842"] == notice
    assert before == {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_malformed_feedback_semantics_are_unavailable_rather_than_claiming_revision(tmp_path):
    problem, world, root, db = feedback_fixture(tmp_path)
    claim = problem["evidence"]["currentEnvironment"]["feedbackConsumption"]["inputs"][0]["claim"]
    claim["target"] = {"kind": "ANNOUNCEMENT"}
    claim["firstAvailableAt"] = "not-a-date"
    result = collect_retained_dependencies([problem], environment_root=root, public_feedback_db=db, as_of=NOW)
    assert result["feedbackStatus"]["consumption-owned"]["status"] == "UNAVAILABLE"
    assert "CONSUMED_FEEDBACK_UNAVAILABLE" in codes(evaluate_freshness(problem, world, as_of=NOW, retained=result))


def test_original_status_hook_avoids_implicit_source_module_or_filesystem_read(monkeypatch):
    from src.portwatch_os.learning.shared_feedback import retained_original_status
    calls = []
    class Snapshot:
        def retained_original_status(self, record):
            calls.append(record)
            return "CORRUPT_ORIGINAL"
    monkeypatch.setattr(Path, "read_bytes", lambda *_: pytest.fail("original hook must use its frozen snapshot"))
    record = {"responseSha256": DIGEST}
    assert retained_original_status(Snapshot(), record) == "CORRUPT_ORIGINAL"
    assert calls == [record]
