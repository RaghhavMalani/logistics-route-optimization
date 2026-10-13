from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.portwatch_os.intelligence.public_ports import (
    CHENNAI_ETA, CHENNAI_POSITION, PARADIP_INDEX, PublicPilot,
    ReportLinks, approved, parse_pdf, record, stamp, timestamp,
)

ROOT = Path(__file__).parent/"fixtures"/"public_ports"
NOW = datetime(2026, 10, 7, 10, tzinfo=timezone.utc)
PARADIP_URL = "https://www.paradipport.gov.in/uploads/2026/10/dtr0610.pdf"


@pytest.fixture
def pilot(tmp_path):
    store = PublicPilot(tmp_path)
    yield store
    store.close()


def test_real_reports_layout_and_event_semantics():
    p = parse_pdf((ROOT/"paradip-2026-10-06.pdf").read_bytes(), "INPRT", "traffic")
    assert p["reportDate"] == "2026-10-06"
    assert len([r for r in p["records"] if r["kind"] == "reported"]) == 39
    assert len([r for r in p["records"] if r["kind"] == "expected"]) == 16
    assert len([r for r in p["records"] if r["kind"] == "planned_movement"]) == 22
    babylon = next(r for r in p["records"] if r["vesselName"] == "MT. BABYLON")
    assert babylon["arrivalAt"] == "2026-09-27T07:32:00.000000Z"
    assert babylon["berthAt"] == "2026-10-05T07:12:00.000000Z"
    assert not any(r["arrivalAt"] or r["berthAt"] for r in p["records"] if r["kind"] == "planned_movement")
    assert next(r for r in p["records"] if r["vesselName"] == "MV. CL DIYIN HE")["loa"] == 199.99
    c = parse_pdf((ROOT/"chennai-position-2026-10-07.pdf").read_bytes(), "INMAA", "position")
    assert len(c["records"]) == 28
    glovis = next(r for r in c["records"] if r["vesselName"] == "GLOVIS SUPERIOR")
    assert glovis["arrivalAt"] == "2026-10-05T20:51:00.000000Z"
    assert glovis["berthAt"] == "2026-10-05T22:25:00.000000Z"
    aliya = next(r for r in c["records"] if r["vesselName"] == "ALIYA")
    assert aliya["arrivalAt"] is None and aliya["berthAt"] is None
    assert "berthAt:MISSING_CLOCK" in aliya["flags"]
    e = parse_pdf((ROOT/"chennai-eta-2026-10-07.pdf").read_bytes(), "INMAA", "expected")
    assert len(e["records"]) == 40
    assert e["issues"][0]["code"] == "CONFLICTING_DATE_HEADINGS"
    assert next(r for r in e["records"] if r["vesselName"] == "MINERVAGRACHT")["etaAt"] is None
    assert next(r for r in e["records"] if r["vesselName"] == "HOANG ANH 10")["etaAt"] == "2026-10-07T22:30:00.000000Z"


def test_chennai_conflicting_printed_dates_are_separated_but_not_guessed():
    report = parse_pdf((ROOT/"chennai-eta-2026-10-08.pdf").read_bytes(), "INMAA", "expected")
    issue = next(i for i in report["issues"] if i["code"] == "CONFLICTING_DATE_HEADINGS")
    assert issue["candidates"] == ["08/10/2026", "12/10/2026"] and issue["page"] == 2
    affected = [r for r in report["records"] if r.get("dateHeadingEvidence")]
    assert {r["vesselName"] for r in affected} == {"SJ LILY", "WAN HAI 329", "MINERVAGRACHT", "LAN HAI CHANG AN"}
    assert all(r["etaAt"] is None and "etaAt:CONFLICTING_DATE_HEADINGS" in r["flags"] for r in affected)


def test_identical_overlapping_dates_recover_only_when_every_glyph_agrees():
    from src.portwatch_os.intelligence.public_ports import date_heading
    chars = [{"text": c, "top": y, "x0": i*3} for y in (96.4,98.2) for i,c in enumerate("12/10/2026")]
    assert date_heading({"chars":chars}) == ("12/10/2026", ["12/10/2026"])
    assert date_heading({"chars":chars+[{"text":"?", "top":99, "x0":40}]}) == (None, [])


def test_real_parser_revision_preserves_first_seen_cases_and_fact_availability(pilot):
    import copy
    payload = (ROOT/"chennai-eta-2026-10-08.pdf").read_bytes()
    before = copy.deepcopy(parse_pdf(payload, "INMAA", "expected"))
    for row in before["records"]:
        row.pop("dateHeadingEvidence", None)
        row["flags"] = [f for f in row["flags"] if f != "etaAt:CONFLICTING_DATE_HEADINGS"]
    before["issues"] = [{"page":2, "code":"MALFORMED_DATE_HEADING", "raw":"0182//1100//22002266"}]
    first = NOW + timedelta(days=1)
    with patch("src.portwatch_os.intelligence.public_ports.VERSION", "public-port-report-v1.1"), patch("src.portwatch_os.intelligence.public_ports.parse_pdf", return_value=before):
        pilot.import_pdf("INMAA", "expected", CHENNAI_ETA, payload, collected=first, actor="test")
    original = pilot.workspace("INMAA", first)
    assert original["cases"]
    later = first+timedelta(hours=2)
    assert pilot.import_pdf("INMAA", "expected", CHENNAI_ETA, payload, collected=later, actor="revision")["reparsed"]
    revised = pilot.workspace("INMAA", later)
    assert revised["cases"] == original["cases"]
    snapshot = revised["snapshots"][0]
    assert snapshot["firstSeenAt"] == stamp(first) and snapshot["parsedAt"] == stamp(later)
    assert len(snapshot["parseHistory"]) == 2
    assert all(r["recordAvailableAt"] == stamp(later) for r in snapshot["records"] if r.get("dateHeadingEvidence"))
    assert all(r["recordAvailableAt"] == stamp(first) for r in snapshot["records"] if not r.get("dateHeadingEvidence"))
    assert pilot.workspace("INMAA", later-timedelta(seconds=1))["snapshots"][0]["parserVersion"] == "public-port-report-v1.1"


def test_real_idempotency_first_seen_future_freeze_and_replay(pilot):
    payload = (ROOT/"chennai-eta-2026-10-07.pdf").read_bytes()
    first = pilot.import_pdf("INMAA", "expected", CHENNAI_ETA, payload, collected=NOW, actor="collector")
    original = pilot.workspace("INMAA", NOW)
    assert original["counts"]["frozen"] > 0
    assert all(datetime.fromisoformat(c["etaAt"].replace("Z", "+00:00")) > NOW for c in original["cases"])
    repeat = pilot.import_pdf("INMAA", "expected", CHENNAI_ETA, payload, collected=NOW+timedelta(days=1), actor="later")
    assert not repeat["new"] and repeat["snapshotId"] == first["snapshotId"]
    assert pilot.workspace("INMAA", NOW+timedelta(days=1))["snapshots"][0]["firstSeenAt"] == stamp(NOW)
    assert pilot.workspace("INMAA", NOW-timedelta(seconds=1))["counts"]["frozen"] == 0
    with pytest.raises(ValueError):
        pilot.evidence("INMAA", first["snapshotId"], NOW-timedelta(seconds=1))
    assert pilot.evidence("INMAA", first["snapshotId"], NOW).read_bytes() == payload


def test_stale_historical_source_cannot_create_prospective_calls(pilot):
    pilot.import_pdf("INMAA", "expected", CHENNAI_ETA, (ROOT/"chennai-eta-2026-10-07.pdf").read_bytes(),
                     collected=NOW+timedelta(days=30), actor="collector")
    assert pilot.workspace("INMAA", NOW+timedelta(days=30))["counts"]["frozen"] == 0


def parsed(rows):
    for n, row in enumerate(rows):
        row["recordId"] = f"test-record-{n}"
    return {"reportDate": "2026-10-07", "records": rows, "issues": []}


def expected(name="TEST SHIP", at="08/10/2026 12:00"):
    return record("expected", name, "190", "32", "9", "A1", {"etaAt": at}, NOW.date(), 0)


def observed(name="TEST SHIP", arrival="08/10/2026 13:00", berth="08/10/2026 15:00"):
    r = record("reported", name, "190", "32", "10", "A1", {"arrivalAt": arrival, "berthAt": berth},
               (NOW+timedelta(days=1)).date(), 0)
    return r


def insert(pilot, rows, content, at, kind="expected"):
    with patch("src.portwatch_os.intelligence.public_ports.parse_pdf", return_value=parsed(rows)):
        pilot.import_pdf("INMAA", kind, CHENNAI_ETA if kind == "expected" else CHENNAI_POSITION,
                         b"%PDF-"+content, collected=at, actor="test collector")


def test_reconciliation_preserves_original_and_label_availability(pilot):
    insert(pilot, [expected()], b"first", NOW)
    frozen = pilot.workspace("INMAA", NOW)["cases"][0]
    insert(pilot, [expected(at="08/10/2026 14:00")], b"revision", NOW+timedelta(hours=1))
    assert pilot.workspace("INMAA", NOW+timedelta(hours=1))["counts"]["frozen"] == 1
    outcome_at = NOW+timedelta(days=1, hours=1)
    insert(pilot, [observed()], b"outcome", outcome_at, "position")
    case = pilot.workspace("INMAA", outcome_at)["cases"][0]
    assert case["etaAt"] == frozen["etaAt"] and case["frozenAt"] == frozen["frozenAt"]
    assert case["outcome"]["arrivalErrorHours"] == 1
    assert case["outcome"]["waitingHours"] == 2
    assert case["outcome"]["arrivalAvailableAt"] == stamp(outcome_at)
    assert pilot.workspace("INMAA", outcome_at-timedelta(seconds=1))["cases"][0]["status"] == "PENDING"


def test_ambiguous_arrivals_and_conflicting_berths_withhold(pilot):
    insert(pilot, [expected()], b"first", NOW)
    at = NOW+timedelta(days=1, hours=2)
    insert(pilot, [observed(), observed(arrival="08/10/2026 14:00")], b"ambiguous", at, "position")
    case = pilot.workspace("INMAA", at)["cases"][0]
    assert case["status"] == "AMBIGUOUS" and case["outcome"] is None


def test_conflicting_berth_and_future_or_missing_events(pilot):
    insert(pilot, [expected()], b"first", NOW)
    at = NOW+timedelta(days=1, hours=2)
    insert(pilot, [observed(), observed(berth="08/10/2026 16:00")], b"conflict", at, "position")
    case = pilot.workspace("INMAA", at)["cases"][0]
    assert case["outcome"]["arrivalErrorHours"] == 1 and case["outcome"]["waitingHours"] is None
    assert "CONFLICTING_REPORTED_BERTH_TIMES" in case["exclusions"]
    assert timestamp("08/10/2026", NOW.date())[0] is None
    assert timestamp("31/02/2026 12:00", NOW.date())[0] is None
    assert timestamp("08/10/2026 25:00", NOW.date())[0] is None


def test_changed_layout_is_archived_not_invented(pilot):
    with pytest.raises(ValueError, match="LAYOUT_CHANGED"):
        parse_pdf((ROOT/"chennai-position-2026-10-07.pdf").read_bytes(), "INPRT", "traffic")
    with patch("src.portwatch_os.intelligence.public_ports.parse_pdf", side_effect=ValueError("LAYOUT_CHANGED")):
        result = pilot.import_pdf("INMAA", "expected", CHENNAI_ETA, b"%PDF-unrecognized", collected=NOW, actor="collector")
    ws = pilot.workspace("INMAA", NOW)
    assert ws["counts"]["records"] == 0 and ws["issues"][0]["raw"] == "LAYOUT_CHANGED"
    assert pilot.evidence("INMAA", result["snapshotId"], NOW).read_bytes() == b"%PDF-unrecognized"
    assert pilot.evaluate("INMAA", NOW, "collector")["targets"]["arrival"]["status"] == "UNAVAILABLE"


@pytest.mark.parametrize("separate_reports", [False, True])
def test_same_berth_time_conflicting_references_are_preserved(pilot, separate_reports):
    insert(pilot, [expected()], b"eta", NOW)
    at = NOW+timedelta(days=1, hours=2)
    first, conflicting = observed(), observed()
    conflicting["berthRef"] = "B2"
    if separate_reports:
        insert(pilot, [first], b"first berth", at, "position")
        insert(pilot, [conflicting], b"conflicting berth", at+timedelta(minutes=1), "position")
        before = pilot.workspace("INMAA", at)["cases"][0]
        assert before["outcome"]["waitingHours"] == 2
        assert len(before["berthEvidence"]) == 1
    else:
        insert(pilot, [first, conflicting], b"conflicting berths", at, "position")
    # A repeat fact cannot hide the contradiction or duplicate the evidence fact.
    insert(pilot, [observed()], b"repeat berth", at+timedelta(minutes=2), "position")
    ws = pilot.workspace("INMAA", at+timedelta(minutes=2))
    case = ws["cases"][0]
    assert len(ws["historicalObservations"]) == 2
    assert case["outcome"]["arrivalErrorHours"] == 1
    assert case["outcome"]["waitingHours"] is None
    assert case["outcome"]["berthSnapshotId"] is None
    assert "CONFLICTING_REPORTED_BERTH_REFERENCES" in case["exclusions"]
    assert "CONFLICTING_REPORTED_BERTH_TIMES" not in case["exclusions"]
    assert {b["berthRef"] for b in case["berthEvidence"]} == {"A1", "B2"}
    assert all(b["snapshotId"] and b["rawTimestamps"]["berthAt"] for b in case["berthEvidence"])


def test_enrollment_cutoff_membership_replay_and_successor(pilot):
    insert(pilot, [expected()], b"initial", NOW)
    created = NOW+timedelta(minutes=1)
    cohort = pilot.start_cohort("INMAA", created, "collector", enrollment_days=1)
    assert len(cohort["caseIds"]) == 1
    assert pilot.workspace("INMAA", NOW)["cohorts"] == []
    with pytest.raises(ValueError, match="already has"):
        pilot.start_cohort("INMAA", created+timedelta(minutes=1), "collector")
    insert(pilot, [expected("EARLY SHIP")], b"early", created+timedelta(hours=1))
    end = created+timedelta(days=1)
    insert(pilot, [expected("LATER SHIP", "10/10/2026 12:00")], b"after cutoff", end)
    closed = pilot.workspace("INMAA", end)
    assert closed["cohorts"][0]["status"] == "CLOSED"
    assert len(closed["cohorts"][0]["caseIds"]) == 2 and closed["unassignedCases"] == 1
    successor = pilot.start_cohort("INMAA", end, "collector")
    assert len(successor["caseIds"]) == 1
    assert not set(successor["caseIds"]) & set(closed["cohorts"][0]["caseIds"])
    assert len(pilot.workspace("INMAA", created)["cohorts"][0]["caseIds"]) == 1
    assert pilot.evaluate("INMAA", created, "collector", cohort_id=cohort["cohortId"])["targets"]["arrival"]["status"] == "UNAVAILABLE"
    with pytest.raises(ValueError, match="unavailable"):
        pilot.evaluate("INPRT", end, "collector", cohort_id=cohort["cohortId"])


def test_partitions_use_all_enrollment_not_successful_labels(pilot):
    cases = []
    for i in range(65):
        issued = NOW+timedelta(days=i)
        outcome = None if 1 <= i <= 4 else {"arrivalErrorHours": 1, "waitingHours": 2,
            "arrivalAvailableAt": stamp(issued+timedelta(hours=1)), "berthAvailableAt": stamp(issued+timedelta(hours=2))}
        cases.append({"caseId": str(i), "status": "MATCHED" if outcome else "UNRESOLVED", "frozenAt": stamp(issued), "outcome": outcome})
    cohort = {"cohortId": "fixed", "status": "CLOSED", "caseIds": [c["caseId"] for c in cases]}
    ws = {"cases": cases, "cohorts": [cohort], "benchmarks": [], "evaluationReason": "threshold"}
    with patch.object(pilot, "workspace", return_value=ws):
        result = pilot.evaluate("INMAA", NOW+timedelta(days=70), "test evaluator")
    arrival = result["targets"]["arrival"]
    assert arrival["status"] == "AVAILABLE"
    assert arrival["calibrationIds"] == [str(i) for i in range(39, 52)]
    assert arrival["holdoutIds"] == [str(i) for i in range(52, 65)]
    assert result["excludedCaseIds"] == [str(i) for i in range(1, 5)]
    assert len(result["datasetCases"]) == 65


def test_complete_chain_requires_fields_from_hash_checked_originals(pilot):
    import json
    from scripts.collect_public_port_pilot import prepare_audit, verify_chain
    insert(pilot, [expected()], b"eta archive", NOW)
    at = NOW+timedelta(days=1, hours=2)
    insert(pilot, [observed()], b"outcome archive", at, "position")
    ws = pilot.workspace("INMAA", at)
    case = ws["cases"][0]
    with patch("src.portwatch_os.intelligence.public_collection.parse_pdf", return_value=parsed([expected(), observed()])):
        checked = verify_chain(pilot, ws, case)
    assert checked["status"] == "ORIGINAL_FIELDS_VERIFIED"
    assert checked["frozenAt"] == stamp(NOW)
    assert checked["arrivalErrorHours"] == 1 and checked["waitingHours"] == 2
    assert checked["identity"]["loaMetres"] == 190 and checked["identity"]["mmsi"] is None
    assert [r["event"] for r in checked["evidence"]] == ["frozenEta", "reportedArrival", "reportedBerth"]
    assert checked["evidence"][0]["rawTimestamps"]["etaAt"] == "08/10/2026 12:00"
    assert checked["evidence"][1]["availableAt"] == stamp(at)
    audit = prepare_audit(pilot.root, checked, ws["asOf"])
    path = Path(audit["json"])
    content = json.loads(path.read_text())
    assert content["visualReview"]["status"] == "PENDING"
    assert "Visual review: PENDING" in Path(audit["markdown"]).read_text(encoding="utf-8")
    content["visualReview"]["status"] = "IN_PROGRESS"
    path.write_text(json.dumps(content), encoding="utf-8")
    repeated = prepare_audit(pilot.root, checked, stamp(at+timedelta(hours=1)))
    assert repeated["json"] == audit["json"] and repeated["visualReviewStatus"] == "IN_PROGRESS"
    assert json.loads(path.read_text())["preparedAt"] == ws["asOf"]
    with patch("src.portwatch_os.intelligence.public_collection.parse_pdf", return_value={"records": []}):
        with pytest.raises(ValueError, match="Original frozenEta fields"):
            verify_chain(pilot, ws, case)


def test_collection_quality_tracks_unmatched_ambiguous_and_incomplete(pilot):
    from scripts.collect_public_port_pilot import collection_quality
    insert(pilot, [expected()], b"quality eta", NOW)
    at = NOW+timedelta(days=1, hours=2)
    insert(pilot, [observed()], b"quality outcome", at, "position")
    complete = pilot.workspace("INMAA", at)["cases"][0]
    cases = [complete, {**complete, "caseId": "pending", "status": "PENDING", "outcome": None},
             {**complete, "caseId": "expired", "status": "UNRESOLVED", "outcome": None},
             {**complete, "caseId": "ambiguous", "status": "AMBIGUOUS", "outcome": None},
             {**complete, "caseId": "incomplete", "outcome": {**complete["outcome"], "waitingHours": None}}]
    quality = collection_quality({"cases": cases})
    assert {k: v["count"] for k, v in quality.items()} == {"unmatched": 2, "ambiguous": 1, "incomplete": 1, "complete": 1}
    assert {c["caseId"] for c in quality["unmatched"]["cases"]} == {"pending", "expired"}


def test_approved_urls_and_index_are_bounded():
    for bad in ["http://paradipport.gov.in/traffic/", "https://evil.invalid/a.pdf", CHENNAI_ETA+"?file=x", "https://paradipport.gov.in/uploads/../../a.pdf", "https://user:pass@paradipport.gov.in/uploads/2026/10/dtr0610.pdf"]:
        assert not approved(bad, index=True)
    parser = ReportLinks()
    parser.feed('<a href="https://evil.invalid/a.pdf">x</a><a href="https://www.paradipport.gov.in/uploads/2026/10/dtr0610.pdf">report</a>')
    assert parser.urls == [PARADIP_URL]
    assert approved(PARADIP_INDEX, index=True)


def test_parser_revision_is_available_later_without_rewriting_first_seen(pilot):
    insert(pilot, [expected()], b"first", NOW)
    original = pilot.workspace("INMAA", NOW)
    later = NOW+timedelta(hours=1)
    with patch("src.portwatch_os.intelligence.public_ports.VERSION", "test-parser-v2"):
        insert(pilot, [expected(at="08/10/2026 14:00")], b"first", later)
        latest = pilot.workspace("INMAA", later)
        assert latest["snapshots"][0]["firstSeenAt"] == original["snapshots"][0]["firstSeenAt"]
        assert latest["snapshots"][0]["parsedAt"] == stamp(later)
        assert latest["snapshots"][0]["parserVersion"] == "test-parser-v2"
        assert latest["cases"][0]["etaAt"] == original["cases"][0]["etaAt"]
        assert pilot.workspace("INMAA", later-timedelta(seconds=1))["snapshots"][0]["parserVersion"] != "test-parser-v2"


def test_baselines_fit_and_calibrate_before_untouched_holdout(pilot):
    cases = []
    for i in range(60):
        issued = NOW+timedelta(days=i)
        cases.append({"caseId": str(i), "status": "MATCHED", "frozenAt": stamp(issued),
            "outcome": {"arrivalErrorHours": 2 if i<36 else 3 if i<48 else 7,
                "waitingHours": 4 if i<36 else 5 if i<48 else 1000,
                "arrivalAvailableAt": stamp(issued+timedelta(hours=1)), "berthAvailableAt": stamp(issued+timedelta(hours=2))}})
    closed = {"cohortId": "closed", "status": "CLOSED", "enrollmentEndAt": stamp(NOW+timedelta(days=60)),
              "caseIds": [c["caseId"] for c in cases]}
    pending = {"caseId": "new-pending", "status": "PENDING", "frozenAt": stamp(NOW+timedelta(days=61)),
               "etaAt": stamp(NOW+timedelta(days=62)), "outcome": None}
    enrolling = {"cohortId": "next", "status": "ENROLLING", "caseIds": [pending["caseId"]]}
    ws = {"cases": cases+[pending], "cohorts": [closed, enrolling], "benchmarks": [], "evaluationReason": "minimum cohort"}
    with patch.object(pilot, "workspace", return_value=ws):
        report = pilot.evaluate("INMAA", NOW+timedelta(days=61), "test evaluator")
    arrival = report["targets"]["arrival"]
    waiting = report["targets"]["waiting"]
    assert report["cohortId"] == "closed" and len(report["datasetCases"]) == 60
    assert "new-pending" not in report["excludedCaseIds"]
    assert len(arrival["fitIds"]) == 36 and arrival["holdoutIds"] == [str(i) for i in range(48,60)]
    assert arrival["metrics"]["fittingMedianEtaCorrection"]["MAE"] == 5
    assert arrival["metrics"]["publishedEta"]["signedBias"] == 7
    assert waiting["metrics"]["fittingHistoricalMedianWait"]["MAE"] == 996
    assert waiting["metrics"]["fittingHistoricalMedianWait"]["intervalRadiusHours"] == 1
    assert waiting["metrics"]["fittingHistoricalMedianWait"]["intervalCoverage"] == 0
    ws["benchmarks"] = [report]
    ws["cases"].append({**pending, "caseId": "another-new-call"})
    with patch.object(pilot, "workspace", return_value=ws):
        assert pilot.evaluate("INMAA", NOW+timedelta(days=62), "again") == report
        assert pilot.evaluate("INMAA", NOW+timedelta(days=62), "open", cohort_id="next")["targets"]["arrival"]["status"] == "UNAVAILABLE"
        # Sealing is keyed to the cohort, not the whole port's first report.
        enrolling["status"] = "CLOSED"
        later = pilot.evaluate("INMAA", NOW+timedelta(days=66), "next", cohort_id="next")
        assert later["cohortId"] == "next" and later["targets"]["arrival"]["status"] == "UNAVAILABLE"
    ws["benchmarks"] = []
    for c in cases[:36]:
        c["outcome"]["arrivalAvailableAt"] = stamp(NOW+timedelta(days=40))
    with patch.object(pilot, "workspace", return_value=ws):
        assert pilot.evaluate("INMAA", NOW+timedelta(days=63), "purged")["targets"]["arrival"]["status"] == "UNAVAILABLE"
