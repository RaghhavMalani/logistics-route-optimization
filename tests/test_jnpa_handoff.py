"""Synthetic source files only; these tests never populate an operational ledger."""
import copy
import csv
import io
import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from scripts.arrival_qa_fixtures import tracks
from scripts.reconcile_jnpa_call import AGREEMENT_FIELDS, file_hash, reconcile
from src.portwatch_os.clock import world_now
from src.portwatch_os.intelligence.arrivals import ArrivalWorkflow, stamp
from src.portwatch_os.learning.weather_feedback import WeatherFeedback
from src.portwatch_os.ledger.store import SqliteLedgerStore


@pytest.fixture
def packet(tmp_path):
    ledger = SqliteLedgerStore(":memory:")
    service = ArrivalWorkflow(ledger)
    issue = world_now()-timedelta(days=3)
    planned = issue+timedelta(days=1)
    service.start_collection("QA synthetic operator", now=issue-timedelta(minutes=10))
    tracks(ledger, issue)
    with patch("src.portwatch_os.ledger.store.utc_now", return_value=stamp(issue-timedelta(minutes=1))):
        WeatherFeedback(ledger).record_frame(pd.DataFrame([{"port_id": "INNSA", "date": planned.date(), "wind_speed": 16.}]),
            issued_at=issue-timedelta(minutes=2), provider="QA synthetic forecast", source_state="QA_FIXTURE", now=issue)
    baseline = {"operationRef": "QA-future-handoff", "mmsi": "419000168", "vesselName": "QA synthetic vessel",
        "recipientOrganisation": "QA Shipping", "plannedArrivalAt": stamp(planned), "baselineWaitHours": 8,
        "baselineSource": "QA synthetic scheduler", "baselineRef": "QA-scheduler-1",
        "baselineEstimatedAt": stamp(issue-timedelta(minutes=5)), "baselineAvailableAt": stamp(issue-timedelta(minutes=1)),
        "routeRevision": "QA-route-1"}
    case = service.create(baseline, "QA synthetic operator", now=issue)
    def export(at):
        return {"portCode": "INNSA", "asOf": stamp(at), "collection": service.collection(now=at),
                "operations": service.cases(now=at), "benchmarks": []}
    frozen = export(issue+timedelta(minutes=2))
    all_fast = planned+timedelta(hours=5)
    available, recorded = all_fast+timedelta(minutes=1), all_fast+timedelta(minutes=2)
    confirmed = {"arrivedAt": stamp(planned), "berthedAt": stamp(all_fast), "arrivalAvailableAt": stamp(planned+timedelta(minutes=1)),
        "allFastAvailableAt": stamp(available), "availableAt": stamp(available), "source": "QA synthetic port-call log",
        "sourceRef": "QA-outcome-1", "kind": "operator_confirmed", "berthRef": "QA berth"}
    service.outcome(case["operationId"], "QA synthetic operator", confirmed, now=recorded)
    final = export(recorded+timedelta(minutes=1))
    source_outcome = {"operationRef": baseline["operationRef"], "mmsi": baseline["mmsi"], **confirmed}
    def write_csv(path, row):
        text = io.StringIO()
        writer = csv.DictWriter(text, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
        path.write_text(text.getvalue(), encoding="utf-8")
    write_csv(tmp_path/"operator-arrival.csv", baseline)
    write_csv(tmp_path/"operator-outcome.csv", source_outcome)
    (tmp_path/"agreement.txt").write_text("QA synthetic agreement, never an actual operator confirmation", encoding="utf-8")
    (tmp_path/"identity.txt").write_text("QA synthetic vessel/MMSI identity record", encoding="utf-8")
    template = Path("docs/first_call_handoff/handoff.json")
    manifest = json.loads(template.read_text(encoding="utf-8"))
    manifest["sourceAgreement"].update({k: "QA synthetic "+k for k in AGREEMENT_FIELDS})
    manifest["sourceAgreement"].update(confirmedAt=stamp(issue-timedelta(hours=1)), confirmationRef="QA-agreement-1",
        mmsiVerificationSourceRef="QA-identity-1", sourceTimezone="UTC")
    manifest["call"] = {k: baseline[k] for k in ("operationRef", "mmsi", "vesselName")}
    for role, filename, reference in (("agreement", "agreement.txt", "QA-agreement-1"), ("identity", "identity.txt", "QA-identity-1"),
          ("scheduler", "operator-arrival.csv", "QA-scheduler-1"), ("outcome", "operator-outcome.csv", "QA-outcome-1")):
        manifest["evidenceDocuments"][role] = {"path": filename, "sha256": file_hash(tmp_path/filename), "sourceRef": reference}
    manifest["reconciliation"] = {"confirmedBy": "QA synthetic operator", "confirmedAt": stamp(recorded+timedelta(minutes=2)),
                                  "confirmationRef": "QA-reconciliation-1"}
    yield tmp_path, manifest, frozen, final
    ledger.close()


def test_frozen_and_final_source_chain_reconciles_without_changing_inputs(packet):
    root, manifest, frozen, final = packet
    original = copy.deepcopy(final)
    first = reconcile(frozen, manifest, root, phase="frozen")
    assert first["status"] == "FROZEN_INPUTS_RECONCILED", first["blockers"]
    assert "outcome" not in first["documents"]
    complete = reconcile(final, manifest, root, frozen=frozen)
    assert complete["status"] == "QUALIFICATION_RECONCILED", complete["blockers"]
    assert complete["observedWaitHours"] == 5
    assert complete["documents"]["scheduler"]["sourceRef"] == "QA-scheduler-1"
    assert final == original and final["operations"][0]["prediction"]["value"] is None


def test_modified_original_and_retrospective_export_are_blocked(packet):
    root, manifest, frozen, final = packet
    changed = copy.deepcopy(final)
    changed["operations"][0]["baselineWaitHours"] = 7
    result = reconcile(changed, manifest, root, frozen=frozen)
    assert any("Frozen original changed: baselineWaitHours" in x for x in result["blockers"])
    assert any("Individual scheduler estimate differs" in x for x in result["blockers"])
    old_export = copy.deepcopy(frozen)
    old_export["asOf"] = final["asOf"]
    result = reconcile(final, manifest, root, frozen=old_export)
    assert any("not captured before actual arrival" in x for x in result["blockers"])


def test_unagreed_identity_late_source_and_missing_acknowledgment_are_blocked(packet):
    root, manifest, frozen, final = packet
    bad = copy.deepcopy(manifest)
    bad["call"]["mmsi"] = "419000169"
    bad["sourceAgreement"]["confirmedAt"] = final["asOf"]
    bad["reconciliation"] = {}
    result = reconcile(final, bad, root, frozen=frozen)
    assert any("vessel identity differs" in x for x in result["blockers"])
    assert any("confirmed after the frozen claim" in x for x in result["blockers"])
    assert any("acknowledgment is missing" in x for x in result["blockers"])


def test_changed_source_bytes_escaped_paths_and_late_wind_are_blocked(packet):
    root, manifest, frozen, final = packet
    (root/"operator-outcome.csv").write_text("changed source bytes", encoding="utf-8")
    bad = copy.deepcopy(manifest)
    bad["evidenceDocuments"]["identity"]["path"] = "../outside.txt"
    modified = copy.deepcopy(final)
    modified["operations"][0]["evidence"]["weather"][0]["recordedAt"] = final["asOf"]
    result = reconcile(modified, bad, root, frozen=frozen)
    assert any("retained file hash differs" in x for x in result["blockers"])
    assert any("inside the handoff directory" in x for x in result["blockers"])
    assert any("Wind forecast became known after freezing" in x for x in result["blockers"])


def test_blank_pack_and_completed_record_cannot_pass_the_frozen_phase(packet):
    root, manifest, frozen, final = packet
    blank = json.loads(Path("docs/first_call_handoff/handoff.json").read_text(encoding="utf-8"))
    assert reconcile(final, blank, root)["status"] == "HANDOFF_REQUIRED"
    result = reconcile(final, manifest, root, phase="frozen")
    assert any("already contains an outcome" in x for x in result["blockers"])
