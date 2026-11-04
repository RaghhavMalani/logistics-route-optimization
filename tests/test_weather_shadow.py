"""Synthetic fixtures test research guards; they are not forecast skill evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from src.portwatch_os.learning.weather_feedback import STATISTICS, VARIABLES, season
from src.portwatch_os.learning.weather_reconciliation import WeatherEvidenceStore, outcome_key, sampling_window
from src.portwatch_os.learning.weather_shadow import WeatherShadowAnalysis, evaluate_shadow
from src.portwatch_os.ledger.schema import PredictionContext, PredictionRecord
from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.utils import port_registry

UTC = timezone.utc
START = datetime(2025, 6, 1, 8, tzinfo=UTC)
NOW = datetime(2025, 10, 1, tzinfo=UTC)
FIELDS = {"wind_speed": ("wind_speed_10m", "kn"), "wind_gust": ("wind_gusts_10m", "kn"),
          "rainfall": ("precipitation", "mm"), "visibility": ("visibility", "m")}


@pytest.fixture
def state(tmp_path):
    ledger = SqliteLedgerStore(tmp_path/"weather.db")
    evidence = WeatherEvidenceStore(tmp_path/"weather.db")
    root = tmp_path/"sources"
    (root/"archive").mkdir(parents=True)
    (root/"outcomes").mkdir()
    yield ledger, evidence, root
    evidence.close()
    ledger.close()


def _raw(day, variable, value, location=None):
    field, unit = FIELDS[variable]
    hourly_value = value/24 if variable == "rainfall" else value*1000 if variable == "visibility" else value
    location = location or {"lat": port_registry.resolve("INNSA").lat, "lon": port_registry.resolve("INNSA").lon}
    return {"latitude": location["lat"], "longitude": location["lon"], "utc_offset_seconds": 0, "hourly_units": {field: unit},
            "hourly": {"time": [day+f"T{h:02}:00" for h in range(24)], field: [hourly_value]*24}}


def add(state, index=0, *, port="INNSA", variable="wind_speed", raw=10., observed=15.,
        horizon=5, issue_minutes=0, provider="Open-Meteo surface", outcome_kind="reanalysis",
        outcome_source="Open-Meteo ERA5 archive", lag=6):
    ledger, evidence, root = state
    issued = START+timedelta(days=index, minutes=issue_minutes)
    day = (issued+timedelta(days=horizon)).date().isoformat()
    start = datetime.fromisoformat(day).replace(tzinfo=UTC)
    valid, available = start+timedelta(days=1), start+timedelta(days=1+lag)
    location = {"lat": port_registry.resolve(port).lat, "lon": port_registry.resolve(port).lon}
    body = _raw(day, variable, raw, location)
    raw_bytes = json.dumps(body).encode()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    (root/"archive"/(digest+".response")).write_bytes(raw_bytes)
    snapshot = {"portCode": port, "kind": "surface", "availableAt": issued.isoformat(),
                "responseSha256": digest, "request": {"latitude": location["lat"], "longitude": location["lon"]}}
    snapshot_id = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    snapshot["snapshotId"] = snapshot_id
    (root/"archive"/(snapshot_id+".json")).write_text(json.dumps(snapshot), encoding="utf-8")
    prediction_id = f"test-{port}-{variable}-{provider}-{index}-{horizon}-{issue_minutes}"
    row = PredictionRecord(prediction_id=prediction_id, domain="weather", kind="continuous",
        target=variable, subject=port, model=provider, model_version="weather-residual-v3",
        issued_at=issued.isoformat(), valid_at=valid.isoformat(), predicted_value=raw,
        context=PredictionContext(port_code=port, season=season(issued), extra={
            "horizonDays": horizon, "targetDate": day, "unit": VARIABLES[variable],
            "aggregation": "daily", "statistic": STATISTICS[variable]}),
        provenance={"responseSha256": digest, "snapshotId": snapshot_id})
    ledger.record_prediction(row)
    ledger.resolve_prediction(prediction_id, observed, available.isoformat(), f"{outcome_kind}: {outcome_source}")
    annotation = {"snapshotId": snapshot_id, "responseSha256": digest,
        "requestLocation": location, "complete": True, "completeHours": 24,
        "aggregation": "daily UTC", "statistic": STATISTICS[variable],
        "targetStart": start.isoformat(), "targetEnd": valid.isoformat(),
        "measurementWindow": sampling_window(day, variable)}
    evidence.put("weather_forecast_annotations", prediction_id, annotation)
    outcome_body = _raw(day, variable, observed, location)
    outcome_bytes = json.dumps(outcome_body).encode()
    outcome_digest = hashlib.sha256(outcome_bytes).hexdigest()
    (root/"outcomes"/(outcome_digest+".response")).write_bytes(outcome_bytes)
    key = outcome_key(port, variable, valid.isoformat(), source=outcome_source)
    outcome = {"id": key, "portCode": port, "variable": variable, "value": observed,
        "unit": VARIABLES[variable], "aggregation": "daily UTC", "statistic": STATISTICS[variable],
        "targetStart": start.isoformat(), "validAt": valid.isoformat(), "availableAt": available.isoformat(),
        "measurementWindow": sampling_window(day, variable), "kind": outcome_kind, "source": outcome_source,
        "url": "https://archive-api.open-meteo.com/v1/archive", "model": "era5", "request": {"models": "era5"},
        "responseSha256": outcome_digest, "location": location, "requestedLocation": location, "completeHours": 24}
    evidence.put("weather_outcome_evidence", key, outcome)
    return prediction_id, annotation, outcome


def report(state, **kwargs):
    return WeatherShadowAnalysis(*state).report(now=NOW, **kwargs)


def update(evidence, table, key, body):
    with evidence.conn:
        evidence.conn.execute(f"UPDATE {table} SET body=? WHERE id=?", (json.dumps(body), key))


def test_independent_targets_refresh_selection_sign_and_reproducibility(state):
    add(state)
    latest, _, _ = add(state, issue_minutes=10, raw=11.)
    data = report(state)
    assert data["mode"] == "SHADOW_ONLY" and data["decisionEligible"] is False
    assert data["summary"]["qualifiedSnapshots"] == 2
    assert data["summary"]["independentTargets"] == 1
    assert data["summary"]["duplicateSnapshots"] == 1
    cell = data["contexts"][0]
    assert cell["targets"][0]["predictionId"] == latest
    assert cell["metrics"]["bias"] == -4 and cell["metrics"]["mae"] == cell["metrics"]["rmse"] == 4
    assert cell["systematicMiss"]["direction"] == "UNDERPREDICTION"
    assert cell["systematicMiss"]["descriptiveOnly"] is True
    assert cell["shadow"]["status"] == "COLLECTING"
    assert cell["readiness"]["independentTargetShortfall"] == 31
    assert data["reportId"] == report(state)["reportId"]


def test_provider_horizon_memberships_do_not_inflate_global_outcomes(state):
    add(state)
    # Same target date, with a different original origin/horizon.
    add(state, index=1, horizon=4)
    add(state, provider="Open-Meteo marine")
    data = report(state)
    assert data["summary"]["independentTargets"] == 1
    assert data["summary"]["cohortMemberships"] == 2
    assert data["summary"]["contexts"] == 2
    assert data["summary"]["exclusionReasons"] == {"forecast_provider_product_variable_mismatch": 1}
    assert data["summary"]["targetDates"] == 1
    assert len(report(state, horizon=4)["contexts"]) == 1


def test_dimensions_outcome_sources_and_locations_remain_separate(state):
    add(state)
    add(state, port="INMAA")
    add(state, variable="wind_gust")
    add(state, index=1, outcome_kind="station", outcome_source="test station")
    data = report(state)
    assert data["summary"]["contexts"] == 3
    assert data["summary"]["independentTargets"] == 3
    assert data["summary"]["exclusionReasons"] == {"outcome_adapter_not_qualified_for_shadow": 1}


def test_outcome_is_not_visible_before_actual_first_receipt(state):
    _, _, outcome = add(state)
    data = WeatherShadowAnalysis(*state).report(now=datetime.fromisoformat(outcome["availableAt"])-timedelta(seconds=1))
    assert data["summary"]["qualifiedSnapshots"] == 0
    assert data["summary"]["resolvedSnapshots"] == 0
    assert data["summary"]["pendingSnapshots"] == 1
    assert data["summary"]["exclusionReasons"] == {}


def test_future_forecast_is_absent_even_from_pending_counts_and_exclusions(state):
    add(state)
    data = WeatherShadowAnalysis(*state).report(now=START-timedelta(seconds=1))
    assert data["summary"]["resolvedSnapshots"] == data["summary"]["pendingSnapshots"] == 0
    assert data["exclusions"] == [] and data["contexts"] == []


@pytest.mark.parametrize("field,value", [("issued_at", 0), ("issued_at", "bad timestamp"),
    ("observed_at", 0), ("observed_at", "bad timestamp"), ("observed_at", "0001-01-01T00:00:00+14:00")])
def test_corrupt_retained_timestamps_cannot_crash_report_or_expose_unknown_origin(state, field, value):
    prediction_id, _, _ = add(state)
    with state[1].conn:
        state[1].conn.execute(f"UPDATE predictions SET {field}=? WHERE prediction_id=?", (value, prediction_id))
    data = report(state)
    assert data["summary"]["qualifiedSnapshots"] == 0
    if field == "issued_at":
        assert data["summary"]["unreadableIssueTimestampSnapshots"] == 1
        assert data["exclusions"] == []
    else:
        assert data["summary"]["exclusionReasons"] == {"invalid_outcome_availability_timestamp": 1}


def test_future_outcome_revision_cannot_rewrite_an_earlier_analysis(state):
    _, _, original = add(state)
    before = report(state)
    later = deepcopy(original)
    later["id"] = "later-revision"
    later["availableAt"] = (NOW+timedelta(days=1)).isoformat()
    later["value"] = 100.
    state[1].put("weather_outcome_evidence", later["id"], later)
    after = report(state)
    assert before["reportId"] == after["reportId"]
    assert after["contexts"][0]["targets"][0]["outcome"] == 15.


def test_response_cache_does_not_hide_corruption_between_reports(state):
    _, annotation, _ = add(state)
    analysis = WeatherShadowAnalysis(*state)
    assert analysis.report(now=NOW)["summary"]["qualifiedSnapshots"] == 1
    (state[2]/"archive"/(annotation["responseSha256"]+".response")).write_bytes(b"changed")
    assert analysis.report(now=NOW)["summary"]["qualifiedSnapshots"] == 0


@pytest.mark.parametrize("problem", ["missing_original", "corrupt_original", "missing_outcome", "wrong_unit",
    "wrong_statistic", "wrong_window", "wrong_location", "forecast_as_outcome", "newer_forecast", "partial_original"])
def test_provenance_or_alignment_failure_never_enters_learning(state, problem):
    prediction_id, annotation, outcome = add(state)
    ledger, evidence, root = state
    if problem == "missing_original": (root/"archive"/(annotation["responseSha256"]+".response")).unlink()
    if problem == "corrupt_original": (root/"archive"/(annotation["responseSha256"]+".response")).write_bytes(b"wrong bytes")
    if problem == "missing_outcome": (root/"outcomes"/(outcome["responseSha256"]+".response")).unlink()
    if problem == "wrong_unit": outcome["unit"] = "m/s"
    if problem == "wrong_statistic": outcome["statistic"] = "mean"
    if problem == "wrong_window": outcome["measurementWindow"]["from"] = outcome["validAt"]
    if problem == "wrong_location": outcome["requestedLocation"] = {"lat": 0., "lon": 0.}
    if problem == "forecast_as_outcome": outcome["kind"] = "forecast"
    if problem == "partial_original": annotation["completeHours"] = 23
    if problem == "newer_forecast":
        receipt_path = root/"archive"/(annotation["snapshotId"]+".json")
        receipt = json.loads(receipt_path.read_text())
        receipt["availableAt"] = outcome["availableAt"]
        receipt_path.write_text(json.dumps(receipt))
    update(evidence, "weather_forecast_annotations", prediction_id, annotation)
    update(evidence, "weather_outcome_evidence", outcome["id"], outcome)
    data = report(state)
    assert data["summary"]["qualifiedSnapshots"] == 0
    assert data["summary"]["excludedSnapshots"] == 1
    assert data["contexts"] == []


def test_precipitation_window_and_raw_recomputation(state):
    _, _, outcome = add(state, variable="rainfall", raw=12., observed=24.)
    data = report(state)
    cell = data["contexts"][0]
    assert cell["unit"] == "mm/day" and cell["statistic"] == "sum"
    assert cell["targets"][0]["error"] == -12.
    assert cell["targets"][0]["measurementWindow"]["from"] == "2025-06-05T23:00:00+00:00"
    assert "not a midnight-to-midnight" in outcome["measurementWindow"]["definition"]


def test_qualified_metadata_cannot_hide_a_different_original_value(state):
    prediction_id, annotation, _ = add(state)
    _, evidence, root = state
    wrong = json.dumps(_raw("2025-06-06", "wind_speed", 999.)).encode()
    digest = hashlib.sha256(wrong).hexdigest()
    (root/"archive"/(digest+".response")).write_bytes(wrong)
    annotation["responseSha256"] = digest
    update(evidence, "weather_forecast_annotations", prediction_id, annotation)
    assert report(state)["summary"]["qualifiedSnapshots"] == 0


@pytest.mark.parametrize("problem", ["raw_location", "hourly_null", "units_list", "json_list", "request_null"])
def test_hash_valid_but_unqualified_outcome_shapes_are_excluded_not_crashes(state, problem):
    _, _, outcome = add(state)
    _, evidence, root = state
    body = _raw("2025-06-06", "wind_speed", 15.)
    if problem == "raw_location": body["latitude"], body["longitude"] = 0., 0.
    if problem == "hourly_null": body["hourly"] = None
    if problem == "units_list": body["hourly_units"] = []
    if problem == "json_list": body = []
    if problem == "request_null": outcome["request"] = None
    raw = json.dumps(body).encode()
    digest = hashlib.sha256(raw).hexdigest()
    (root/"outcomes"/(digest+".response")).write_bytes(raw)
    outcome["responseSha256"] = digest
    update(evidence, "weather_outcome_evidence", outcome["id"], outcome)
    data = report(state)
    assert data["summary"]["qualifiedSnapshots"] == 0
    assert data["summary"]["excludedSnapshots"] == 1


def test_legacy_missing_statistic_is_derived_and_does_not_modify_frozen_claim(state):
    prediction_id, annotation, _ = add(state)
    ledger, evidence, _ = state
    row = ledger.get_prediction(prediction_id)
    context = row.context.to_dict()
    del context["extra"]["statistic"]
    with evidence.conn:
        evidence.conn.execute("UPDATE predictions SET context=? WHERE prediction_id=?", (json.dumps(context), prediction_id))
    del annotation["measurementWindow"]
    update(evidence, "weather_forecast_annotations", prediction_id, annotation)
    target = report(state)["contexts"][0]["targets"][0]
    assert target["statisticBasis"].startswith("derived")
    assert target["forecastWindowBasis"].startswith("derived")
    assert "statistic" not in ledger.get_prediction(prediction_id).context.extra


def test_nominal_32_targets_remain_collecting_after_lag_purging(state):
    for i in range(32): add(state, i)
    cell = report(state)["contexts"][0]
    assert cell["independentTargets"] == 32
    assert cell["readiness"]["purged"] > 0
    assert cell["readiness"]["partitions"]["fitting"] < 8
    assert cell["shadow"]["status"] == "COLLECTING"
    assert cell["shadow"]["biasAdjustment"] is None


def test_daily_shadow_uses_frozen_four_partitions_without_adopting(state):
    for i in range(80): add(state, i)
    cell = report(state)["contexts"][0]
    shadow, readiness = cell["shadow"], cell["readiness"]
    assert shadow["status"] == "SHADOW_VALIDATED"
    assert shadow["decisionEligible"] is False
    assert shadow["biasAdjustment"] == 5.
    assert shadow["validation"]["raw"]["mae"] == 5
    assert shadow["validation"]["corrected"]["mae"] == 0
    assert shadow["evaluation"]["corrected"]["mae"] == 0
    assert shadow["evaluation"]["corrected"]["intervalCoverage"] == 1
    assert all(count >= 8 for count in readiness["partitions"].values())
    ids = [target for targets in shadow["targetIds"].values() for target in targets]
    assert len(ids) == len(set(ids))
    by_id = {r["predictionId"]: r for r in cell["targets"]}
    for before, after in (("fitting", "validation"), ("validation", "calibration"), ("calibration", "evaluation")):
        first_origin = min(by_id[i]["issuedAt"] for i in readiness["predictionIds"][after])
        assert all(by_id[i]["availableAt"] < first_origin for i in readiness["predictionIds"][before])
    assert shadow["correctionId"] == report(state)["contexts"][0]["shadow"]["correctionId"]
    assert all(r.context.extra.get("correctedValue") is None for r in state[0].predictions(domain="weather"))


def test_calibration_and_evaluation_do_not_change_fitted_adjustment(state):
    for i in range(80): add(state, i, observed=35. if 40 <= i < 60 else 10. if i >= 60 else 15.)
    shadow = report(state)["contexts"][0]["shadow"]
    assert shadow["biasAdjustment"] == 5
    assert shadow["validation"]["corrected"]["mae"] == 0
    assert shadow["calibration"]["residualRadius"] == 20
    assert shadow["status"] == "REJECTED"
    assert shadow["evaluation"]["passes"] is False
    assert shadow["decisionEligible"] is False


def test_strict_two_percent_boundary_and_zero_baseline_reject():
    rows = []
    for i in range(40):
        issue = START+timedelta(days=i*20)
        rows.append({"targetId": str(i), "predictionId": str(i), "issuedAt": issue.isoformat(),
            "validAt": (issue+timedelta(days=1)).isoformat(), "availableAt": (issue+timedelta(days=2)).isoformat(),
            "raw": 50., "outcome": 49. if i < 10 else 0.,
            "forecastResponseSha256": "a"*64, "outcomeResponseSha256": "b"*64})
    _, shadow = evaluate_shadow(rows)
    assert shadow["validation"]["raw"]["mae"] == 50
    assert shadow["validation"]["corrected"]["mae"] == 49
    assert shadow["status"] == "REJECTED"  # exactly 2% is insufficient
    for row in rows: row["outcome"] = row["raw"]
    _, shadow = evaluate_shadow(rows)
    assert shadow["status"] == "REJECTED"
