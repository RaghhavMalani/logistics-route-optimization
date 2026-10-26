"""Prospective economic dates, retained originals and independent scoring cohorts."""
import copy
import hashlib

import pytest

from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.portwatch_os.learning import economic_feedback as economic
from src.portwatch_os.learning import intelligence_reconciliation as collector
from src.portwatch_os.learning import shared_feedback as feedback


ISSUE = "2026-10-13T10:00:00+00:00"
RECEIVED = "2026-10-19T21:00:00+00:00"
BASELINE = b"observation_date,DEXINUS\n2026-10-12,96.31\n"
OUTCOME = b"observation_date,DEXINUS\n2026-10-14,97.31\n"


def fixture(tmp_path, *, outcome=True):
    store = SqliteLedgerStore(tmp_path / "public.db")
    collector.collect_fx(store, BASELINE, ISSUE, tmp_path)
    item = next(row for row in store.feedback("claim") if row["kind"] == "FORECAST")
    if outcome:
        collector.collect_fx(store, OUTCOME, RECEIVED, tmp_path)
    return store, item


def test_date_only_quote_and_target_use_matching_semantics_not_synthetic_hours(tmp_path):
    store, item = fixture(tmp_path)
    quote = item["inputs"][0]
    assert quote["observedAt"] is None
    assert quote["observationDate"] == "2026-10-12"
    assert quote["measurementTimePrecision"] == "DATE_ONLY"
    assert "at" not in item["target"]
    selected = economic.select_outcome(store, item, RECEIVED, tmp_path)
    assert selected["eligible"] and selected["evidence"]["value"] == 97.31
    assert selected["quoteDate"] == "2026-10-12" and selected["quoteAgeDays"] == 1
    assert selected["evidence"]["observedAt"] is None
    # The original prediction can use an internal due clock, never called an
    # observation or actual provider release in the economic contract.
    assert store.get_prediction(item["id"]).valid_at
    store.close()


def test_new_and_legacy_date_representations_match_without_rewriting_claim(tmp_path):
    store, item = fixture(tmp_path)
    legacy = copy.deepcopy(item)
    legacy["target"].update(at="2026-10-14T16:00:00+00:00", timePrecision="OBSERVATION_DATE_ONLY; eligibility label")
    original = copy.deepcopy(legacy)
    selected = economic.select_outcome(store, legacy, RECEIVED, tmp_path)
    assert selected["eligible"]
    assert legacy == original
    store.close()


def test_unchanged_response_updates_check_not_first_receipt_or_observation(tmp_path):
    store, item = fixture(tmp_path, outcome=False)
    before = copy.deepcopy(store.feedback("evidence"))
    receipt = copy.deepcopy(store.feedback("receipt"))
    collector.collect_fx(store, BASELINE, RECEIVED, tmp_path)
    assert store.feedback("evidence") == before
    assert store.feedback("receipt") == receipt
    assert len(store.feedback("receipt-check")) == 2
    assert len(store.feedback("economic-source-check")) == 2
    assert receipt[0]["requestMetadata"]["series"] == "DEXINUS"
    assert receipt[0]["firstAvailableAt"] == ISSUE
    # Different future target days are forecasts, not invented quote outcomes.
    assert len(store.feedback("evidence")) == 1
    store.close()


@pytest.mark.parametrize("raw", [
    b"observation_date,DEXINUS\n2026-10-12,96.31\n2026-10-13,broken\n",
    b"observation_date,DEXINUS\n2026-10-12,96.31\n2026-99-13,97\n",
    b"observation_date,DEXINUS\n2026-10-12,96.31\n2026-10-12,97.31\n",
    b"DATE,DEXINUS\n2026-10-12,nan\n",
    b"DATE,DEXINUS\n2026-10-12,0\n",
    b"date,USDINR\n2026-10-12,96.31\n",
])
def test_malformed_entire_product_preserves_original_without_partial_ingestion(tmp_path, raw):
    store = SqliteLedgerStore(tmp_path / "public.db")
    with pytest.raises(ValueError):
        collector.collect_fx(store, raw, ISSUE, tmp_path)
    assert not store.feedback("evidence") and not store.feedback("claim")
    digest = hashlib.sha256(raw).hexdigest()
    assert (tmp_path / "shared_feedback" / (digest + ".response")).read_bytes() == raw
    assert store.feedback("economic-source-check")[-1]["status"] == "MALFORMED_RESPONSE"
    store.close()


def test_identical_duplicate_rows_are_one_observation_and_missing_is_not_zero(tmp_path):
    store = SqliteLedgerStore(tmp_path / "public.db")
    rows = collector.collect_fx(store, BASELINE + b"2026-10-12,96.31\n2026-10-13,.\n", ISSUE, tmp_path)
    assert len(rows) == 1 and rows[0]["value"] == 96.31
    assert len(store.feedback("economic-missing-observation")) == 1
    assert not any(row["value"] == 0 for row in store.feedback("evidence"))
    assert len(store.predictions()) == 1
    store.close()


@pytest.mark.parametrize(("changes", "code"), [
    ({"unit": "USD/INR"}, "INCOMPATIBLE_UNIT_OR_CURRENCY"),
    ({"baseCurrency": "INR", "quoteCurrency": "USD"}, "INCOMPATIBLE_UNIT_OR_CURRENCY"),
    ({"aggregation": "CLOSING_PRICE"}, "INCOMPATIBLE_STATISTIC"),
    ({"statistic": "DAILY_AVERAGE"}, "INCOMPATIBLE_STATISTIC"),
    ({"productId": "ECB_REFERENCE_RATE"}, "INCOMPATIBLE_PRODUCT"),
    ({"entity": "EUR/INR"}, "INCOMPATIBLE_SCOPE"),
    ({"source": "Unreviewed rate feed"}, "UNSUPPORTED_SOURCE_SEMANTICS"),
    ({"value": 1 / 97.31}, "ORIGINAL_ROW_MISMATCH"),
    ({"target": {"kind": "ECONOMIC_OBSERVATION", "series": "DEXINUS", "date": "2026-10-15"},
      "observationDate": "2026-10-15"}, "INCOMPATIBLE_OBSERVATION_DATE"),
])
def test_wrong_economic_outcome_cannot_settle_target(tmp_path, changes, code):
    store, item = fixture(tmp_path, outcome=False)
    digest = collector.retain_response(store, OUTCOME, collector.URL, RECEIVED, tmp_path)
    evidence = {"id": "isolated-incompatible-outcome", "eventKey": item["eventKey"],
                "target": {"kind": "ECONOMIC_OBSERVATION", "series": "DEXINUS", "date": "2026-10-14"},
                "entity": item["entity"], "geography": item["geography"], "unit": economic.UNIT,
                "aggregation": economic.STATISTIC, "recordKind": "ECONOMIC_OBSERVATION",
                "value": 97.31, "source": economic.SOURCE, "sourceVersion": digest,
                "firstAvailableAt": RECEIVED, "observationDate": "2026-10-14", "observedAt": None,
                "responseSha256": digest, **changes}
    store.append_feedback("evidence", evidence)
    selected = economic.select_outcome(store, item, RECEIVED, tmp_path)
    assert not selected["eligible"]
    assert code in {row["code"] for row in selected["exclusions"]}
    assert store.get_prediction(item["id"]).status == "open"
    store.close()


@pytest.mark.parametrize("change", [
    {"originAt": "2026-10-14T01:00:00+00:00", "firstAvailableAt": "2026-10-14T01:00:00+00:00"},
    {"firstAvailableAt": "2026-10-13T11:00:00+00:00"},
])
def test_date_only_outcome_cannot_prove_intraday_prospectivity_or_late_freeze(tmp_path, change):
    store, item = fixture(tmp_path)
    selected = economic.select_outcome(store, {**item, **change}, RECEIVED, tmp_path)
    assert not selected["eligible"]
    assert "NON_PROSPECTIVE_ISSUE" in {row["code"] for row in selected["exclusions"]}
    store.close()


def test_future_availability_hidden_and_raw_corruption_blocks_new_match(tmp_path):
    store, item = fixture(tmp_path)
    before = economic.select_outcome(store, item, "2026-10-19T20:00:00+00:00", tmp_path)
    assert not before["eligible"] and before["candidates"] == []
    digest = hashlib.sha256(OUTCOME).hexdigest()
    path = tmp_path / "shared_feedback" / (digest + ".response")
    path.write_bytes(b"corrupted source")
    after = economic.select_outcome(store, item, RECEIVED, tmp_path)
    assert not after["eligible"]
    assert "CORRUPT_ORIGINAL" in {row["code"] for row in after["exclusions"]}
    store.close()


def test_missing_input_original_excludes_forecast_even_if_later_outcome_exists(tmp_path):
    store, item = fixture(tmp_path)
    digest = hashlib.sha256(BASELINE).hexdigest()
    (tmp_path / "shared_feedback" / (digest + ".response")).unlink()
    result = economic.select_outcome(store, item, RECEIVED, tmp_path)
    assert not result["eligible"]
    assert "MISSING_ORIGINAL" in {row["code"] for row in result["exclusions"]}
    store.close()


def test_pending_release_missing_row_and_actual_failure_are_distinct(tmp_path):
    store, item = fixture(tmp_path, outcome=False)
    pending = economic.select_outcome(store, item, "2026-10-15T20:00:00+00:00", tmp_path)
    assert pending["status"] == "UNRELEASED_TARGET"
    collector.record_fx_check(store, RECEIVED, "PROVIDER_UNAVAILABLE", reason="Controlled provider outage")
    assert economic.select_outcome(store, item, RECEIVED, tmp_path)["status"] == "PROVIDER_UNAVAILABLE"
    collector.collect_fx(store, b"observation_date,DEXINUS\n2026-10-14,.\n", "2026-10-19T22:00:00+00:00", tmp_path)
    missing = economic.select_outcome(store, item, "2026-10-19T22:00:00+00:00", tmp_path)
    assert missing["status"] == "MISSING_OBSERVATION"
    assert not missing["eligible"]
    store.close()


def test_revisions_and_reversions_keep_first_retained_scoring_vintage(tmp_path):
    store, item = fixture(tmp_path)
    first = economic.select_outcome(store, item, RECEIVED, tmp_path)["evidence"]
    revised_at = "2026-10-20T10:00:00+00:00"
    collector.collect_fx(store, OUTCOME.replace(b"97.31", b"97.50"), revised_at, tmp_path)
    revised = economic.select_outcome(store, item, revised_at, tmp_path)
    assert revised["evidence"]["id"] == first["id"]
    assert revised["revisionState"] == "REVISED_EXCLUDED_FROM_RELIABILITY"
    collector.collect_fx(store, OUTCOME, "2026-10-21T10:00:00+00:00", tmp_path)
    reverted = economic.select_outcome(store, item, "2026-10-21T10:00:00+00:00", tmp_path)
    assert reverted["evidence"]["id"] == first["id"] and len(reverted["candidates"]) == 3
    assert len({row["id"] for row in reverted["candidates"]}) == 3
    store.close()
    store = SqliteLedgerStore(tmp_path / "public.db")
    assert economic.select_outcome(store, item, "2026-10-21T10:00:00+00:00", tmp_path)["evidence"]["id"] == first["id"]
    store.close()


def test_expected_weekly_release_is_a_derived_check_not_measurement_or_publication():
    ordinary = economic.expected_release("2026-10-16")
    assert ordinary["expectedAt"] == "2026-10-19T20:15:00+00:00"
    assert ordinary["actualProviderPublishedAt"] is None
    holiday = economic.expected_release("2026-10-09")
    assert holiday["expectedAt"] == "2026-10-13T20:15:00+00:00"
    winter = economic.expected_release("2026-11-13")
    assert winter["expectedAt"] == "2026-11-16T21:15:00+00:00"


def test_qualification_clock_hides_later_score_and_keeps_one_error_convention(tmp_path):
    store, item = fixture(tmp_path)
    assessed = "2026-10-19T23:00:00+00:00"
    resolved, pending = feedback.reconcile(store, assessed)
    assert resolved == 1
    before = economic.inspect_economics(store, "2026-10-19T22:00:00+00:00", tmp_path)
    row = next(row for row in before["targets"] if row["claimId"] == item["id"])
    assert row["matchedObservation"]["firstAvailableAt"] == RECEIVED
    assert row["error"] is None and before["counts"]["eligibleMatches"] == 0
    after = economic.inspect_economics(store, assessed, tmp_path)
    row = next(row for row in after["targets"] if row["claimId"] == item["id"])
    assert row["error"] == pytest.approx(1)
    assert row["absoluteError"] == pytest.approx(1)
    assert row["assessmentAvailableAt"] == assessed
    assert row["errorConvention"] == "observed minus predicted"
    assert after["slices"][0]["bias"] == pytest.approx(1)
    assert after["slices"][0]["meanAbsoluteError"] == pytest.approx(1)
    assert after["selectedClaimIds"] == [item["id"]]
    match = copy.deepcopy(store.feedback("match"))
    feedback.reconcile(store, assessed)
    assert store.feedback("match") == match
    store.close()


def test_legacy_score_remains_unchanged_and_new_qualification_is_available_only_now(tmp_path):
    from src.portwatch_os.learning.outcome_agent import score_prediction
    store, item = fixture(tmp_path)
    outcome = economic.select_outcome(store, item, RECEIVED, tmp_path)["evidence"]
    prediction = store.get_prediction(item["id"])
    store.resolve_prediction(item["id"], 97.31, RECEIVED, economic.SOURCE, score_prediction(prediction, 97.31))
    legacy_match = {"id": item["id"], "claimId": item["id"], "evidenceId": outcome["id"],
                    "availableAt": RECEIVED, "scoringVintage": "FIRST_RETAINED_OUTCOME"}
    store.append_feedback("match", legacy_match)
    old_prediction = copy.deepcopy(store.get_prediction(item["id"]).__dict__)
    before = economic.inspect_economics(store, RECEIVED, tmp_path)
    assert before["counts"]["eligibleMatches"] == 0
    assert next(row for row in before["targets"] if row["claimId"] == item["id"])["legacyStoredScore"]["error"] == pytest.approx(1)
    qualification_at = "2026-10-20T10:00:00+00:00"
    feedback.reconcile(store, qualification_at)
    assert store.feedback("match", item["id"])[0] == legacy_match
    assert store.get_prediction(item["id"]).__dict__ == old_prediction
    assert economic.inspect_economics(store, qualification_at, tmp_path)["counts"]["eligibleMatches"] == 1
    assert economic.inspect_economics(store, RECEIVED, tmp_path)["counts"]["eligibleMatches"] == 0
    store.close()


def test_complete_export_and_independent_counts_do_not_use_visible_hundred_claims(tmp_path):
    from datetime import timedelta
    store, original = fixture(tmp_path, outcome=False)
    ids = [original["id"]]
    for index in range(104):
        origin = (feedback.instant(ISSUE)+timedelta(seconds=index+1)).isoformat()
        body = {key: value for key, value in original.items() if key not in ("id", "contractVersion")}
        item = feedback.claim(store, {**body, "originAt": origin, "firstAvailableAt": origin})
        feedback.register_prediction(store, item, "economic_persistence")
        ids.append(item["id"])
    digest = collector.retain_response(store, OUTCOME, collector.URL, RECEIVED, tmp_path)
    quote = original["inputs"][0]
    feedback.evidence(store, {**{key: value for key, value in quote.items() if key != "id"},
        "eventKey": original["eventKey"], "target": original["target"], "observationDate": "2026-10-14",
        "sourceVersion": digest, "responseSha256": digest, "value": 97.31, "firstAvailableAt": RECEIVED})
    feedback.reconcile(store, RECEIVED)
    view = economic.inspect_economics(store, RECEIVED, tmp_path)
    assert view["dataset"]["complete"] is True and view["dataset"]["claimCount"] == 105
    assert len(view["targets"]) == 105
    assert view["counts"]["forecastVintages"] == 105
    assert view["counts"]["independentForecastTargets"] == 1
    assert view["counts"]["eligibleMatches"] == 1
    assert view["slices"][0]["independentTargets"] == 1
    assert view["selectedClaimIds"] == [original["id"]]
    before = copy.deepcopy(view)
    store.close()
    store = SqliteLedgerStore(tmp_path / "public.db")
    assert economic.inspect_economics(store, RECEIVED, tmp_path) == before
    assert not store.feedback("consumption")
    store.close()


def test_same_availability_conflicting_values_are_not_resolved_by_insert_order(tmp_path):
    store, item = fixture(tmp_path)
    collector.collect_fx(store, OUTCOME.replace(b"97.31", b"97.50"), RECEIVED, tmp_path)
    result = economic.select_outcome(store, item, RECEIVED, tmp_path)
    assert result["status"] == "CONFLICTING_OUTCOMES" and not result["eligible"]
    assert feedback.reconcile(store, RECEIVED)[0] == 0
    store.close()


@pytest.mark.parametrize(("change", "code"), [
    ({"sourceVersion": "unreviewed-model-v7"}, "UNSUPPORTED_FORECAST_POLICY"),
    ({"source": "Unreviewed model"}, "UNSUPPORTED_FORECAST_POLICY"),
])
def test_unreviewed_forecast_policy_does_not_enter_persistence_metrics(tmp_path, change, code):
    store, item = fixture(tmp_path)
    result = economic.select_outcome(store, {**item, **change}, RECEIVED, tmp_path)
    assert not result["eligible"]
    assert code in {row["code"] for row in result["exclusions"]}
    store.close()


@pytest.mark.parametrize(("change", "code"), [
    ({"source": "ECB or operator proxy"}, "UNSUPPORTED_SOURCE_SEMANTICS"),
    ({"recordKind": "SIMULATED"}, "INPUT_QUOTE_NOT_OBSERVATION"),
    ({"firstAvailableAt": "2026-10-12T10:00:00+00:00"}, "UNVERIFIED_FIRST_AVAILABILITY"),
])
def test_quote_requires_actual_retained_product_receipt_and_observation_kind(tmp_path, change, code):
    store, item = fixture(tmp_path)
    changed = copy.deepcopy(item)
    changed["inputs"][0].update(change)
    result = economic.select_outcome(store, changed, RECEIVED, tmp_path)
    assert not result["eligible"]
    assert code in {row["code"] for row in result["exclusions"]}
    store.close()


def test_revision_keeps_stored_error_but_leaves_reliability_and_earlier_audit_unchanged(tmp_path):
    store, item = fixture(tmp_path)
    feedback.reconcile(store, RECEIVED)
    before = copy.deepcopy(economic.inspect_economics(store, RECEIVED, tmp_path))
    original_score = copy.deepcopy(store.get_prediction(item["id"]).__dict__)
    revised_at = "2026-10-20T10:00:00+00:00"
    collector.collect_fx(store, OUTCOME.replace(b"97.31", b"97.50"), revised_at, tmp_path)
    feedback.reconcile(store, revised_at)
    after = economic.inspect_economics(store, revised_at, tmp_path)
    assert after["counts"]["revisedTargets"] == 1
    assert after["counts"]["excludedTargets"] == 1
    assert after["counts"]["eligibleIndependentTargets"] == 0
    assert after["slices"] == []
    row = next(row for row in after["targets"] if row["claimId"] == item["id"])
    assert row["error"] == pytest.approx(1)
    assert row["matchedObservation"]["value"] == 97.31
    assert row["revisionState"] == "REVISED_EXCLUDED_FROM_RELIABILITY"
    assert store.get_prediction(item["id"]).__dict__ == original_score
    assert economic.inspect_economics(store, RECEIVED, tmp_path) == before
    store.close()
