from datetime import timedelta
from unittest.mock import patch

import pytest

from scripts.arrival_qa_fixtures import seed
from src.portwatch_os.clock import world_now
from src.portwatch_os.intelligence import arrival_model
from src.portwatch_os.intelligence.arrivals import ArrivalWorkflow, stamp
from src.portwatch_os.intelligence.jnpa_public import parse_report, save_report
from src.portwatch_os.ledger.store import SqliteLedgerStore


@pytest.fixture
def service():
    ledger = SqliteLedgerStore(":memory:")
    yield ArrivalWorkflow(ledger)
    ledger.close()


def claim(now, ref="QA-call"):
    return {"operationRef": ref, "mmsi": "419000168", "vesselName": "QA vessel", "recipientOrganisation": "QA shipping",
            "plannedArrivalAt": stamp(now+timedelta(days=1)), "baselineWaitHours": 20, "baselineSource": "QA scheduler",
            "baselineRef": "QA-estimate-1", "baselineEstimatedAt": stamp(now-timedelta(minutes=5)),
            "baselineAvailableAt": stamp(now-timedelta(minutes=1))}


def outcome(now):
    return {"arrivedAt": stamp(now+timedelta(days=1)), "berthedAt": stamp(now+timedelta(days=1, hours=5)),
            "arrivalAvailableAt": stamp(now+timedelta(days=1, minutes=1)),
            "allFastAvailableAt": stamp(now+timedelta(days=1, hours=5, minutes=1)),
            "availableAt": stamp(now+timedelta(days=1, hours=5, minutes=1)), "source": "QA verified log",
            "sourceRef": "QA-log-1", "berthRef": "QA berth", "kind": "port_call_log"}


def test_prospective_freeze_and_independent_outcome_with_record_availability(service):
    now = world_now()
    cohort = service.start_collection("verified operator", now=now)
    assert service.start_collection("another operator", now=now) == cohort
    with pytest.raises(ValueError, match="requires scheduler"):
        service.create({k: v for k, v in claim(now).items() if k != "baselineRef"}, "operator", now=now)
    with pytest.raises(ValueError, match="already exist"):
        service.create({**claim(now), "baselineAvailableAt": stamp(now+timedelta(seconds=1))}, "operator", now=now)
    case = service.create(claim(now), "operator", now=now)
    assert case["cohortId"] == cohort["cohortId"]
    with pytest.raises(ValueError, match="event's availability"):
        service.outcome(case["operationId"], "operator", {**outcome(now), "arrivalAvailableAt": stamp(now)}, now=now+timedelta(days=2))
    resolved = service.outcome(case["operationId"], "operator", outcome(now), now=now+timedelta(days=2))
    assert resolved["outcome"]["waitHours"] == 5
    assert resolved["actualAction"] is None and resolved["advisoryId"] is None
    assert service.ledger.get_decision(case["decisionId"]).status == "open"
    assert service.get(case["operationId"], now=now+timedelta(days=2)-timedelta(microseconds=1))["outcome"] is None
    assert service.collection(now=now+timedelta(days=2))["qualifyingCount"] == 0  # Missing frozen AIS/weather.


def test_quality_duplicate_cancellation_and_stale_ais_cannot_be_repaired(service):
    now = world_now()
    service.start_collection("operator", now=now)
    evidence = {"weather": [], "tracks": [], "matchRationale": "QA", "camera": {"status": "UNAVAILABLE", "reason": "QA"}}
    features = {"wind_speed": 20, "wind_gust": None, "rainfall": None, "wave_height": None, "visibility": None,
                "trackCount": 2, "trackAgeHours": 2, "sogKnots": 0, "observedAnchoredVessels": 0}
    with patch.object(service, "signals", return_value=(evidence, features)):
        first = service.create(claim(now), "operator", now=now)
        duplicate = service.create(claim(now, "alias"), "operator", now=now)
    q = service.collection(now=now+timedelta(days=4))
    assert q["duplicateCandidateCount"] == 2 and q["staleAisCount"] == 2 and q["overdueCount"] == 2
    service.disposition(duplicate["operationId"], "operator", {"reason": "duplicate", "duplicateOf": first["operationId"],
        "source": "QA booking aliases verified", "availableAt": stamp(now)}, now=now)
    q = service.collection(now=now)
    assert q["duplicateCandidateCount"] == 0 and q["excludedCount"] == 1 and q["unresolvedCount"] == 1
    service.outcome(first["operationId"], "operator", outcome(now), now=now+timedelta(days=2))
    with pytest.raises(ValueError, match="prediction error"):
        service.disposition(first["operationId"], "operator", {"reason": "cancelled", "source": "QA", "availableAt": stamp(now)}, now=now+timedelta(days=2))
    assert service.collection(now=now+timedelta(days=2))["qualifyingCount"] == 0


def test_predeclared_cohort_metrics_and_all_ablations_keep_holdout_untouched(service):
    now = world_now()
    report = seed(service.ledger, now, prospective=True)
    assert report["cohortId"] and len(report["enrolledIds"]) == 60
    assert report["protocol"]["minimumQualifyingCalls"] == 60
    assert service.collection(now=now)["cohort"]["status"] == "SEALED"
    assert service.evaluate("operator", now=now) == report
    assert len(report["metrics"]) == 6
    assert report["metrics"]["scheduler"]["signedBiasHours"] < 0
    for key, metrics in report["metrics"].items():
        predictions = report["holdoutPredictions"]
        assert metrics["signedBiasHours"] == pytest.approx(sum(r["observed"]-r["comparisons"][key]["point"] for r in predictions)/len(predictions))
        assert metrics["intervalCoverage"] == pytest.approx(sum(r["comparisons"][key]["low"] <= r["observed"] <= r["comparisons"][key]["high"] for r in predictions)/len(predictions))
    rows = service.training_rows(now=now)
    changed = [dict(r, waitHours=1000) if r["operationId"] in report["holdoutIds"] else r for r in rows]
    altered = arrival_model.evaluate(changed, set())
    assert [r["comparisons"] for r in altered["holdoutPredictions"]] == [r["comparisons"] for r in report["holdoutPredictions"]]
    assert altered["promotion"] == report["promotion"]
    assert set(report["config"]["ablationFeatures"]["scheduler_only_gbm"]) == {"baselineWaitHours"}


def test_public_report_rowspans_missing_fields_and_first_seen_are_preserved(tmp_path):
    html = '<h2>Daily Berthing Report as on 07-10-2026</h2><table><tr>'+''.join(f'<th>{h}</th>' for h in
        ("Terminal", "Berth No.", "VIA No", "Vessel Name", "Cargo-Commodity", "Berthed on", "Expected Completion", "Terminal Daily Report Link"))+'</tr>'
    html += '<tr><td rowspan="2">NSFT</td><td>CB01</td><td>S1</td><td>QA ONE</td><td>CONTAINER</td><td>06-10-2026 10:00:00</td><td>07-10-2026 10:00:00</td><td rowspan="2">Report</td></tr>'
    html += '<tr><td>CB02</td><td>S2</td><td>QA TWO</td><td>CONTAINER</td><td>06-10-2026 12:00:00</td><td>07-10-2026 12:00:00</td></tr></table>'
    first = parse_report(html, "2026-10-07T10:00:00+00:00")
    assert len(first["records"]) == 2 and first["records"][1]["terminal"] == "NSFT"
    assert all(not r["qualifying"] and "Timestamp timezone" in r["missing"] for r in first["records"])
    file = save_report(first, tmp_path)
    later = parse_report(html.replace("Report</td>", "Report </td>"), "2026-10-08T10:00:00+00:00")
    assert save_report(later, tmp_path) == file
    assert '2026-10-07T10:00:00+00:00' in file.read_text()
    with pytest.raises(ValueError, match="date missing"):
        parse_report("<table></table>", "2026-10-07T10:00:00+00:00")
