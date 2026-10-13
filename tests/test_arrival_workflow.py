from datetime import timedelta
from unittest.mock import patch

import pytest

from scripts.arrival_qa_fixtures import seed, tracks
from src.portwatch_os.clock import world_now
from src.portwatch_os.intelligence import arrival_model
from src.portwatch_os.intelligence.arrivals import ArrivalWorkflow, stamp
from src.portwatch_os.ledger.store import LedgerError, SqliteLedgerStore


def planned(now, reference="test-arrival"):
    return {"operationRef": reference, "mmsi": "419000168", "vesselName": "Test vessel", "recipientOrganisation": "Test company",
            "plannedArrivalAt": stamp(now+timedelta(days=1)), "baselineWaitHours": 22, "baselineSource": "Specific FCFS scheduler call 168",
            "routeRevision": "route-168-v1"}


@pytest.fixture
def ledger():
    store = SqliteLedgerStore(":memory:")
    yield store
    store.close()


def test_unavailable_is_not_zero_or_proxy_and_original_is_frozen(ledger):
    now = world_now()
    service = ArrivalWorkflow(ledger)
    case = service.create(planned(now), "controller", now=now)
    assert case["prediction"]["value"] is None
    assert case["predictionId"] is None
    assert not case["evidence"]["tracks"]
    assert any("maximum-wind" in x for x in case["missingEvidence"])
    tracks(ledger, now)
    assert service.get(case["operationId"], now=now)["evidence"]["tracks"] == []
    with pytest.raises(LedgerError, match="immutable"):
        service.create(planned(now), "controller", now=now)
    with pytest.raises(ValueError, match="retrospective"):
        service.create(planned(now-timedelta(days=2)), "controller", now=now)


def test_track_availability_and_recording_are_both_required(ledger):
    now = world_now()
    tracks(ledger, now)
    rows = ledger.arrival_tracks("INNSA", before=stamp(now))
    assert len(rows) == 2
    late = {**rows[0], "id": "late-received", "availableAt": stamp(now+timedelta(seconds=1))}
    recorded_late = {**rows[0], "id": "late-recorded", "recordedAt": stamp(now+timedelta(seconds=1))}
    ledger.record_arrival_track(late)
    ledger.record_arrival_track(recorded_late)
    assert len(ledger.arrival_tracks("INNSA", before=stamp(now))) == 2
    assert len(ledger.arrival_tracks("INNSA", before=stamp(now+timedelta(seconds=2)))) == 4


def test_benchmark_has_disjoint_periods_and_unchanged_holdout(ledger):
    now = world_now()
    report = seed(ledger, now)
    assert ArrivalWorkflow(ledger).evaluate("controller", now=now) == report
    assert report["fitCount"] >= 24 and report["calibrationCount"] >= 10 and report["holdoutCount"] >= 10
    assert not set(report["fitIds"]) & set(report["calibrationIds"])
    assert not set(report["holdoutIds"]) & (set(report["fitIds"]) | set(report["calibrationIds"]))
    rows = ArrivalWorkflow(ledger).training_rows(now=now)
    changed = [dict(r, waitHours=1000) if r["operationId"] in report["holdoutIds"] else r for r in rows]
    altered = arrival_model.evaluate(changed, set())
    assert altered["promotion"] == report["promotion"]
    assert [r["predicted"] for r in altered["holdoutPredictions"]] == [r["predicted"] for r in report["holdoutPredictions"]]
    with pytest.raises(ValueError, match="already been used"):
        arrival_model.evaluate(rows, {report["holdoutIds"][0]})


def test_prediction_resolution_is_atomic_immutable_and_replay_safe(ledger):
    now = world_now()
    seed(ledger, now-timedelta(days=3))
    service = ArrivalWorkflow(ledger)
    issue = now-timedelta(days=2)
    # Forecast/track inputs and model report must already be known before issue.
    report = service.benchmarks(now=now)[0]
    with patch.object(service, "signals", return_value=(
        {"weather": [], "tracks": [], "matchRationale": "QA", "camera": {"status": "UNAVAILABLE", "reason": "QA"}},
        {"wind_speed": 15., "wind_gust": None, "rainfall": None, "wave_height": None, "visibility": None,
         "sogKnots": 2., "trackCount": 2, "trackAgeHours": 0.01, "observedAnchoredVessels": 0})):
        case = service.create(planned(issue), "controller", now=issue)
    assert case["prediction"]["value"] is not None
    key = case["operationId"]
    original = ledger.get_prediction(case["predictionId"]).predicted_value
    service.approve(key, "controller", "Confirmed scheduler review", now=issue+timedelta(hours=1))
    ledger.append_arrival_event(key, "advisory", "INNSA", "controller", {"advisoryId": "qa-issued"}, at=stamp(issue+timedelta(hours=2)))
    service.action(key, "controller", {"actualAction": "Retained scheduled arrival", "actionState": "taken", "source": "QA bridge log",
        "occurredAt": stamp(issue+timedelta(hours=3)), "availableAt": stamp(issue+timedelta(hours=3))}, now=issue+timedelta(hours=4))
    actual = {"arrivedAt": stamp(issue+timedelta(hours=24)), "berthedAt": stamp(issue+timedelta(hours=36)),
              "availableAt": stamp(issue+timedelta(hours=37)), "source": "QA port call log", "kind": "port_call_log", "berthRef": "B1"}
    with patch.object(ledger, "resolve_decision", side_effect=LedgerError("injected failure")):
        with pytest.raises(LedgerError, match="injected"):
            service.outcome(key, "controller", actual, now=now)
    assert ledger.get_prediction(case["predictionId"]).status == "open"
    assert service.get(key, now=now)["outcome"] is None
    resolved = service.outcome(key, "controller", actual, now=now)
    assert resolved["outcome"]["waitHours"] == 12
    assert resolved["errorHours"] == pytest.approx(12-original)
    assert ledger.get_prediction(case["predictionId"]).predicted_value == original
    assert service.get(key, now=now-timedelta(seconds=1))["outcome"] is None
    with pytest.raises(LedgerError, match="immutable"):
        service.outcome(key, "controller", {**actual, "berthedAt": stamp(issue+timedelta(hours=40)),
                        "availableAt": stamp(issue+timedelta(hours=41))}, now=now)


def test_late_outcomes_purged_and_missing_signals_withhold_model(ledger):
    now = world_now()
    report = seed(ledger, now)
    service = ArrivalWorkflow(ledger)
    rows = service.training_rows(now=now)
    for row in rows[:36]:
        row["recordedAt"] = stamp(now)
    with pytest.raises(ValueError, match="purging"):
        arrival_model.evaluate(rows, set())
    prediction = arrival_model.predict({"baselineWaitHours": 22, "wind_speed": None, "trackCount": 0}, [], report)
    assert prediction["value"] is None and prediction["low"] is None


def test_changed_model_code_requires_new_evaluation(ledger):
    now = world_now()
    report = seed(ledger, now)
    features = {"wind_speed": 17., "trackCount": 2, "trackAgeHours": 0.01, "baselineWaitHours": 22.}
    prediction = arrival_model.predict(features, ArrivalWorkflow(ledger).training_rows(now=now), {**report, "codeHash": "old-code"})
    assert prediction["value"] is None
    assert any("code/dependency" in reason for reason in prediction["missing"])


def test_repeated_call_references_cannot_inflate_measured_training_labels(ledger):
    now = world_now()
    seed(ledger, now)
    service = ArrivalWorkflow(ledger)
    original = service.cases(now=now)[0]
    # A pre-existing imported duplicate must still count once for calibration.
    body = next(e["body"] for e in original["events"] if e["kind"] == "created")
    ledger.append_arrival_event("duplicate-ref", "created", "INNSA", "QA", body, at=original["issuedAt"])
    ledger.append_arrival_event("duplicate-ref", "outcome", "INNSA", "QA", original["outcome"], at=stamp(now))
    assert len(service.training_rows(now=now)) == 60


def test_overlapping_measured_arrival_is_refused(ledger):
    from src.portwatch_os.learning.weather_feedback import instant
    now = world_now()
    seed(ledger, now)
    service = ArrivalWorkflow(ledger)
    original = service.cases(now=now)[0]
    issue = instant(original["issuedAt"])
    case = service.create(planned(issue, "alternate-booking"), "controller", now=issue)
    key = case["operationId"]
    service.approve(key, "controller", "Reviewed another booking", now=issue+timedelta(minutes=1))
    ledger.append_arrival_event(key, "advisory", "INNSA", "controller", {"advisoryId": "QA-duplicate-call"}, at=stamp(issue+timedelta(minutes=2)))
    service.action(key, "controller", {"actualAction": "Retained plan", "actionState": "taken", "source": "QA log",
        "occurredAt": stamp(issue+timedelta(minutes=3)), "availableAt": stamp(issue+timedelta(minutes=3))}, now=issue+timedelta(minutes=4))
    with pytest.raises(ValueError, match="overlapping"):
        service.outcome(key, "controller", original["outcome"], now=now)
    assert service.get(key, now=now)["outcome"] is None


def test_forecast_recorded_later_cannot_join_earlier_operation(ledger):
    import pandas as pd
    from src.portwatch_os.learning.weather_feedback import WeatherFeedback
    now = world_now()
    tomorrow = now+timedelta(days=1)
    with patch("src.portwatch_os.ledger.store.utc_now", return_value=stamp(now+timedelta(seconds=1))):
        WeatherFeedback(ledger).record_frame(pd.DataFrame([{"port_id": "INNSA", "date": tomorrow.date(), "wind_speed": 19.}]),
            issued_at=now-timedelta(minutes=1), provider="QA forecast", source_state="QA_FIXTURE", now=now)
    evidence, features = ArrivalWorkflow(ledger).signals("419000168", tomorrow, now=now)
    assert evidence["weather"] == [] and features["wind_speed"] is None
    evidence, features = ArrivalWorkflow(ledger).signals("419000168", tomorrow, now=now+timedelta(seconds=2))
    assert len(evidence["weather"]) == 1 and features["wind_speed"] == 19.
