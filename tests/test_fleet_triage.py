"""Fleet product rules over frozen fictional records, independent of providers."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from src.portwatch_os.decision.fleet_triage import CATEGORY_ORDER, project_fleet_triage

AS_OF = datetime(2026, 10, 29, 8, tzinfo=timezone.utc)


def stamp(hours=0):
    return (AS_OF + timedelta(hours=hours)).isoformat()


def world():
    return {"organisation": "PortWatch Demo Shipping", "epoch": stamp(-10), "fleet": [
        {"id": "PWD-001", "name": "Fictional one", "portCode": "INNSA", "etaHours": 20,
         "operationalEpisode": {"id": "call-one", "voyageLegId": "leg-one", "vesselId": "PWD-001", "namespace": "visitor-one", "portCode": "INNSA"}},
        {"id": "PWD-002", "name": "Fictional two", "portCode": "INMAA", "etaHours": 30,
         "operationalEpisode": {"id": "call-two", "voyageLegId": "leg-two", "vesselId": "PWD-002", "namespace": "visitor-one", "portCode": "INMAA"}},
        {"id": "PWD-003", "name": "Fictional three", "portCode": "INPRT", "etaHours": 40}],
        "weatherJourneys": {}}


def problem(identity="comparison-one", *, vessel_id="PWD-001", must_meet=True, baseline="COMPATIBLE_UNDER_ASSUMPTIONS",
            alternative="BLOCKED", human_choice=None, workflow="COMPUTED"):
    w = world()
    vessel = next(v for v in w["fleet"] if v["id"] == vessel_id)
    episode = deepcopy(vessel["operationalEpisode"])
    def option(name, status, base):
        cargo = {"status": status, "timingStatus": "MISSES" if status == "BLOCKED" else "FITS",
                 "slackHours": -3.5 if status == "BLOCKED" else 2., "cutoffAt": stamp(5),
                 "reasons": ["Loading completes 3.5 h after the declared cutoff"] if status == "BLOCKED" else [],
                 "missing": ["connection.availableTeu"] if status == "UNKNOWN" else []}
        return {"optionId": identity + ":" + name, "label": "Fictional " + name, "isBaseline": base,
                "status": "REJECTED" if must_meet and status in {"BLOCKED", "UNKNOWN"} else "FEASIBLE",
                "evaluation": {"derived": {"cargoAssessment": cargo}}}
    options = [option("current", baseline, True), option("slower", alternative, False)]
    return {"decisionId": identity, "actor": {"role": "SHIPPING_COMPANY", "organisation": w["organisation"]},
        "subject": {"id": vessel_id, "type": "vessel", "label": vessel["name"]}, "workflow": workflow,
        "humanChoice": identity + ":" + human_choice if human_choice else None,
        "baselineOptionId": options[0]["optionId"], "options": options,
        "recommendation": {"optionId": options[1]["optionId"]}, "decisionDeadline": stamp(2),
        "evidence": {"currentEnvironment": {"evidenceId": "evidence-" + identity,
            "operationalEpisode": episode, "portCode": vessel["portCode"], "voyageId": vessel_id,
            "earliestVoyageArrival": stamp(10), "availableAt": stamp(-.1), "plannedArrival": stamp(10),
            "cargoCommitment": {"mustMeet": must_meet, "shipment": {"shipmentId": identity + ":shipment"}}}}}


def approve(w, p, *, active=True):
    p["workflow"] = "APPROVED"
    p["humanChoice"] = p["humanChoice"] or p["baselineOptionId"]
    proposal = {"decisionId": p["decisionId"], "optionId": p["humanChoice"], "vesselId": p["subject"]["id"],
                "environmentEvidenceId": p["evidence"]["currentEnvironment"]["evidenceId"]}
    w["weatherJourneys"][p["decisionId"]] = {"proposal": proposal}
    if active:
        w["terminalProposal"] = proposal
    return p


def review(w, p, *, state="COMPUTED", advisory_state=None):
    port = deepcopy(p)
    port["decisionId"] += "-port"
    port["actor"] = {"role": "PORT_AUTHORITY", "portCode": "INNSA"}
    port["workflow"] = state
    port["humanChoice"] = p["humanChoice"] if state != "COMPUTED" else None
    port["evidence"]["companyProposal"] = {"decisionId": p["decisionId"], "optionId": p["humanChoice"],
        "environmentEvidenceId": p["evidence"]["currentEnvironment"]["evidenceId"]}
    w["weatherJourneys"][p["decisionId"]]["reviewDecisionId"] = port["decisionId"]
    advisory = None
    if advisory_state:
        port["evidence"]["advisories"] = ["advisory-one"]
        advisory = {"advisoryId": "advisory-one", "state": advisory_state, "recipientVesselId": p["subject"]["id"],
            "validUntil": stamp(3), "evidence": {"decisionId": port["decisionId"],
                "currentEnvironment": deepcopy(p["evidence"]["currentEnvironment"])}}
    return port, advisory


def project(w=None, decisions=None, advisories=None, *, statuses=None, consistent=True):
    decisions = decisions or []
    fresh = {p["decisionId"]: {"status": "CURRENT", "reasons": []} for p in decisions if isinstance(p, dict) and p.get("decisionId")}
    fresh.update(statuses or {})
    return project_fleet_triage(w or world(), decisions, advisories or [], as_of=AS_OF, freshness=fresh, snapshot_consistent=consistent)


def first(result, vessel_id="PWD-001"):
    return next(row for row in result["rows"] if row["vessel"]["id"] == vessel_id)


def codes(row):
    return {reason["code"] for reason in row["reasons"]}


def test_required_failing_baseline_not_replaced_by_engine_recommendation():
    p = problem(baseline="BLOCKED", alternative="COMPATIBLE_UNDER_ASSUMPTIONS")
    row = first(project(decisions=[p]))
    assert row["primaryCategory"] == "CURRENT_CONDITIONAL_FAILURE"
    assert row["currentPlan"]["basis"] == "BASELINE_NOT_APPROVED"
    assert row["currentPlan"]["optionId"] == p["baselineOptionId"] != row["recommendation"]["optionId"]
    assert row["cargo"]["slackHours"] == -3.5
    assert "REQUIRED_CARGO_CONNECTION_BLOCKED" in codes(row)


def test_rejected_slower_alternative_never_creates_current_plan_failure():
    p = problem()
    row = first(project(decisions=[p]))
    assert row["primaryCategory"] == "COMPANY_ACTION"
    assert row["cargo"]["status"] == "COMPATIBLE_UNDER_ASSUMPTIONS"
    assert "REQUIRED_CARGO_CONNECTION_BLOCKED" not in codes(row)
    assert row["workflow"]["nextRole"] == "SHIPPING_COMPANY"


def test_human_choice_is_option_identity_not_recommendation_or_highlight():
    w, p = world(), problem(alternative="COMPATIBLE_UNDER_ASSUMPTIONS")
    approve(w, p)
    p["highlightedOptionId"] = p["options"][1]["optionId"]
    row = first(project(w, [p]))
    assert row["currentPlan"]["optionId"] == p["humanChoice"] == p["baselineOptionId"]
    assert row["recommendation"]["optionId"] == p["options"][1]["optionId"]
    assert row["workflow"]["stage"] == "PORT_REVIEW_PENDING"


@pytest.mark.parametrize("status", ["BLOCKED", "UNKNOWN"])
def test_optional_cargo_context_never_becomes_required_block(status):
    row = first(project(decisions=[problem(must_meet=False, baseline=status)]))
    assert row["primaryCategory"] == "COMPANY_ACTION"
    assert "OPTIONAL_CARGO_CONTEXT" in codes(row)
    assert "REQUIRED_CARGO_CONNECTION_BLOCKED" not in codes(row)


def test_missing_required_capacity_is_incomplete_not_fabricated_miss():
    row = first(project(decisions=[problem(baseline="UNKNOWN")]))
    assert row["primaryCategory"] == "INCOMPLETE_ASSESSMENT"
    assert "REQUIRED_CARGO_ASSESSMENT_INCOMPLETE" in codes(row)
    assert "connection.availableTeu" in row["missingCoverage"]


@pytest.mark.parametrize("code", ["SOURCE_RECEIPT_EXPIRED", "CARGO_DECLARATION_CHANGED", "VOYAGE_ETA_CHANGED", "RESTRICTION_REVISION_CHANGED", "CONSUMED_FEEDBACK_CHANGED"])
def test_stale_selected_failure_is_reassessment_not_fresh_failure(code):
    p = problem(baseline="BLOCKED")
    statuses = {p["decisionId"]: {"status": "REASSESSMENT", "reasons": [{"code": code, "text": "Consumed input changed", "basis": "frozen input"}]}}
    row = first(project(decisions=[p], statuses=statuses))
    assert row["primaryCategory"] == "REASSESSMENT"
    assert "REQUIRED_CARGO_CONNECTION_BLOCKED" not in codes(row)
    assert "FROZEN_CARGO_CONCLUSION_NOT_CURRENT" in codes(row)
    assert row["currentPlan"]["decisionId"] == p["decisionId"]
    assert row["cargo"]["slackHours"] == -3.5 and row["workflow"]["nextRole"] == "SHIPPING_COMPANY"


def test_unrelated_world_counts_news_and_other_shipment_do_not_change_projection():
    w, p = world(), problem()
    before = project(w, [p])
    w.update(newsCount=999, weatherErrorCount=123, unrelatedEconomics={"USDINR": 100})
    w["cargoCommitments"] = {"unconsumed-shipment": {"inputVersion": "changed"}}
    assert project(w, [p]) == before


@pytest.mark.parametrize("state,stage,role", [
    ("draft", "PORT_ISSUE_PENDING", "PORT_AUTHORITY"),
    ("under_review", "PORT_ISSUE_PENDING", "PORT_AUTHORITY"),
    ("issued", "VESSEL_RESPONSE_PENDING", "VESSEL_OPERATOR"),
    ("acknowledged", "VESSEL_RESPONSE_PENDING", "VESSEL_OPERATOR"),
    ("accepted", "VESSEL_ACCEPTED_DEMO_OUTCOME_PENDING", "PORT_AUTHORITY"),
    ("queried", "PORT_RESPONSE_PENDING", "PORT_AUTHORITY"),
    ("declined", "PROPOSAL_RETURNED", "SHIPPING_COMPANY"),
    ("withdrawn", "PROPOSAL_RETURNED", "SHIPPING_COMPANY"),
    ("expired", "ADVISORY_EXPIRED", "SHIPPING_COMPANY")])
def test_linked_advisory_drives_next_role_not_company_workflow(state, stage, role):
    w, p = world(), problem(alternative="COMPATIBLE_UNDER_ASSUMPTIONS", human_choice="slower")
    approve(w, p)
    port, advisory = review(w, p, state="PROPOSED", advisory_state=state)
    result = project(w, [p, port], [advisory])
    row = first(result)
    assert row["workflow"]["stage"] == stage and row["workflow"]["nextRole"] == role
    assert len(result["rows"]) == 3 and sum(result["counts"].values()) == 3
    assert result["coverage"]["retainedComparisons"] == 1
    assert row["workflow"]["companyDecisionId"] == p["decisionId"]
    assert row["workflow"]["portDecisionId"] == port["decisionId"]
    if state == "issued":
        assert row["deadline"]["kind"] == "ADVISORY_VALID_UNTIL" and row["deadline"]["hoursRemaining"] == 3


def test_unapproved_successor_does_not_replace_approved_active_choice():
    w, p = world(), problem()
    approve(w, p)
    successor = problem("successor", baseline="BLOCKED")
    successor["evidence"]["predecessorDecisionId"] = p["decisionId"]
    p["evidence"]["successorDecisionIds"] = [successor["decisionId"]]
    row = first(project(w, [successor, p]))
    assert row["currentPlan"]["decisionId"] == p["decisionId"]
    assert row["candidateComparisons"][0]["decisionId"] == "successor"
    assert row["primaryCategory"] == "WAITING_OTHER_ROLE"


def test_incompatible_approved_without_explicit_active_relationship_is_ambiguous():
    w, one, two = world(), problem("one"), problem("two")
    approve(w, one, active=False); approve(w, two, active=False)
    row = first(project(w, [one, two]))
    assert row["currentPlan"]["basis"] == "AMBIGUOUS" and row["currentPlan"]["optionId"] is None
    assert row["primaryCategory"] == "INCOMPLETE_ASSESSMENT"
    assert "AMBIGUOUS_APPROVED_PLAN" in codes(row)


def test_explicit_active_approval_and_verified_approved_successor_relationship():
    w, one, two = world(), problem("one"), problem("two")
    approve(w, one, active=False); approve(w, two)
    assert first(project(w, [one, two]))["currentPlan"]["decisionId"] == "two"
    w.pop("terminalProposal")
    two["evidence"]["predecessorDecisionId"] = "one"
    one["evidence"]["successorDecisionIds"] = ["two"]
    assert first(project(w, [two, one]))["currentPlan"]["decisionId"] == "two"


def test_unique_unapproved_successor_baseline_and_separate_pending_ambiguity():
    w, one, two = world(), problem("one"), problem("two")
    two["evidence"]["predecessorDecisionId"] = "one"
    one["evidence"]["successorDecisionId"] = "two"
    assert first(project(w, [one, two]))["currentPlan"]["decisionId"] == "two"
    two["evidence"].pop("predecessorDecisionId")
    assert first(project(w, [two, one]))["currentPlan"]["basis"] == "AMBIGUOUS"


@pytest.mark.parametrize("approved", [False, True])
@pytest.mark.parametrize("leaf_linked_to_cycle", [False, True])
def test_cyclic_comparisons_cannot_disappear_behind_a_unique_leaf(approved, leaf_linked_to_cycle):
    w = world()
    one, two, leaf = (problem(identity) for identity in ("one", "two", "leaf"))
    one["evidence"].update(predecessorDecisionId="two", successorDecisionIds=["two"])
    two["evidence"].update(predecessorDecisionId="one", successorDecisionIds=["one"])
    if leaf_linked_to_cycle:
        leaf["evidence"]["predecessorDecisionId"] = "two"
        two["evidence"]["successorDecisionIds"].append("leaf")
    if approved:
        for comparison in (one, two, leaf):
            approve(w, comparison, active=False)
    for comparisons in ([one, two, leaf], [leaf, two, one]):
        row = first(project(w, comparisons))
        assert row["currentPlan"]["basis"] == "AMBIGUOUS"
        assert row["currentPlan"]["decisionId"] is None
        assert row["primaryCategory"] == "INCOMPLETE_ASSESSMENT"
        assert ("AMBIGUOUS_APPROVED_PLAN" if approved else "AMBIGUOUS_CURRENT_COMPARISON") in codes(row)


def test_new_current_call_excludes_prior_same_vessel_and_eta_edit_does_not_create_call():
    w, p = world(), problem(baseline="BLOCKED")
    w["fleet"][0]["etaHours"] = 21
    assert first(project(w, [p]))["currentPlan"]["decisionId"] == p["decisionId"]
    w["fleet"][0]["operationalEpisode"].update(id="next-call", voyageLegId="next-leg")
    row = first(project(w, [p]))
    assert row["currentPlan"]["decisionId"] is None and "NEEDS_ASSESSMENT" in codes(row)


def test_completed_journey_never_reopens_merely_from_old_forecast_or_cutoff():
    w, p = world(), problem(baseline="BLOCKED")
    approve(w, p)
    port, advisory = review(w, p, state="ACCEPTED", advisory_state="completed")
    outcome = {"kind": "SIMULATED_DEMO_OUTCOME", "eligibleForRealTarget": False}
    w["weatherJourneys"][p["decisionId"]]["outcome"] = outcome
    advisory["evidence"]["demoOutcome"] = outcome
    p["options"][0]["evaluation"]["derived"]["cargoAssessment"]["cutoffAt"] = stamp(-10)
    row = first(project(w, [p, port], [advisory], statuses={p["decisionId"]: {"status": "REASSESSMENT", "reasons": [{"code": "EXPIRED", "text": "Old forecast"}]}}))
    assert row["primaryCategory"] == "MONITORED" and row["workflow"]["nextRole"] is None
    assert row["freshness"]["status"] == "NOT_REQUIRED_COMPLETED" and row["deadline"] is None
    assert codes(row) == {"SIMULATION_JOURNEY_COMPLETED"}


def test_full_retained_dataset_and_order_independence_not_top_twenty_or_eight():
    w = world()
    all_records = [problem("old-" + str(i)) for i in range(30)]
    for p in all_records:
        p["evidence"]["currentEnvironment"]["operationalEpisode"]["id"] = "prior-call"
    current = problem("current-21st", baseline="BLOCKED")
    all_records.insert(21, current)
    before = project(w, all_records)
    after = project(w, list(reversed(all_records)))
    assert before == after
    assert first(before)["currentPlan"]["decisionId"] == current["decisionId"]
    assert before["coverage"]["retainedComparisons"] == 31 and before["counts"]["CURRENT_CONDITIONAL_FAILURE"] == 1
    ten = world()
    prototype = deepcopy(ten["fleet"][0])
    ten["fleet"] = [{**deepcopy(prototype), "id": f"owned-{i:02}", "operationalEpisode": None} for i in range(12)]
    result = project(ten)
    assert len(result["rows"]) == result["coverage"]["ownedVoyages"] == result["counts"]["INCOMPLETE_ASSESSMENT"] == 12


def test_repeated_projection_is_read_only_and_missing_call_remains_missing():
    w, p = world(), problem()
    data, decisions = deepcopy(w), deepcopy([p])
    one, two = project(w, [p]), project(w, [p])
    assert one == two and w == data and [p] == decisions
    assert "operationalEpisode" not in w["fleet"][2]
    assert first(one, "PWD-003")["currentPlan"]["basis"] == "MISSING"


def test_overdue_signed_time_and_offset_instant_known_before_unknown():
    one, two = problem("one"), problem("two", vessel_id="PWD-002")
    one["decisionDeadline"] = "2026-10-29T08:30:00+05:30"  # 03:00Z, overdue by five hours.
    two["decisionDeadline"] = None
    two["evidence"]["currentEnvironment"]["cargoCommitment"]["mustMeet"] = False
    result = project(decisions=[two, one])
    row = first(result)
    assert row["deadline"]["hoursRemaining"] == -5 and row["deadline"]["kind"] == "COMPARISON_ACTION_DEADLINE"
    assert result["rows"][0]["vessel"]["id"] == "PWD-001"
    assert first(result, "PWD-002")["deadline"] is None


def test_elapsed_scheduled_cutoff_is_not_an_actual_missed_shipment():
    p = problem(baseline="BLOCKED")
    p["options"][0]["evaluation"]["derived"]["cargoAssessment"]["cutoffAt"] = stamp(-1)
    row = first(project(decisions=[p]))
    assert row["primaryCategory"] == "REASSESSMENT"
    assert "SCHEDULED_CUTOFF_ELAPSED" in codes(row) and "REQUIRED_CARGO_CONNECTION_BLOCKED" not in codes(row)
    assert row["cargo"]["slackHours"] == -3.5


def test_legacy_malformed_optional_and_inconsistent_linked_records_are_honest():
    w, p = world(), problem()
    legacy = deepcopy(p); legacy["decisionId"] = "legacy"
    legacy["evidence"]["currentEnvironment"].pop("operationalEpisode")
    p["options"][0]["evaluation"]["derived"]["cargoAssessment"].update(reasons=None, missing=None, slackHours="unknown", cutoffAt="bad-time")
    row = first(project(w, [p, legacy, None, {"decisionId": "malformed"}]))
    assert row["cargo"]["slackHours"] is None and "LEGACY_CALL_IDENTITY_UNAVAILABLE" in codes(row)
    approve(w, p)
    port, advisory = review(w, p, state="PROPOSED", advisory_state="issued")
    port["evidence"]["companyProposal"]["optionId"] = "wrong-option"
    row = first(project(w, [p, port], [advisory]))
    assert row["primaryCategory"] == "INCOMPLETE_ASSESSMENT"
    assert row["workflow"]["stage"] == "UPDATING_LINKED_STATE" and row["workflow"]["nextRole"] is None


def test_owned_fleet_membership_and_namespace_are_not_vessel_name_matches():
    w, p = world(), problem()
    foreign = deepcopy(p)
    foreign["actor"]["organisation"] = "Foreign company"
    foreign["decisionId"] = "foreign-org"
    foreign_call = deepcopy(p)
    foreign_call["decisionId"] = "foreign-visitor"
    foreign_call["evidence"]["currentEnvironment"]["operationalEpisode"]["namespace"] = "other-visitor"
    result = project(w, [foreign, foreign_call])
    assert first(result)["currentPlan"]["decisionId"] is None
    assert not any("foreign" in json.dumps(row) for row in result["rows"])


def test_unknown_freshness_and_updating_snapshot_cannot_reassure():
    p = problem()
    result = project_fleet_triage(world(), [p], [], as_of=AS_OF)
    assert first(result)["primaryCategory"] == "INCOMPLETE_ASSESSMENT"
    result = project(decisions=[p], consistent=False)
    assert all(r["primaryCategory"] == "INCOMPLETE_ASSESSMENT" for r in result["rows"])
    assert result["coverage"]["snapshotConsistent"] is False


def test_counts_are_disjoint_rows_with_overlapping_reason_counts():
    p = problem(baseline="BLOCKED")
    result = project(decisions=[p])
    assert sum(result["counts"].values()) == len(result["rows"]) == 3
    assert result["reasonCountsOverlap"] is True
    assert result["reasonCounts"]["REQUIRED_CARGO_CONNECTION_BLOCKED"] == 1
    assert result["categoryOrder"] == list(CATEGORY_ORDER)
    with pytest.raises(ValueError):
        project_fleet_triage(world(), [p], [], as_of=AS_OF.replace(tzinfo=None))


def test_retry_representations_collapse_without_inflating_plan_or_counts():
    w, p = world(), problem(human_choice="slower", alternative="COMPATIBLE_UNDER_ASSUMPTIONS")
    approve(w, p)
    port, advisory = review(w, p, state="PROPOSED", advisory_state="issued")
    one = project(w, [p, port], [advisory])
    assert project(w, [deepcopy(port), p, deepcopy(p), port], [advisory, deepcopy(advisory)]) == one


@pytest.mark.parametrize("mutation", [
    lambda a: a.update(status="COMPATIBLE_UNDER_ASSUMPTIONS", slackHours=None),
    lambda a: a.update(status="COMPATIBLE_UNDER_ASSUMPTIONS", cutoffAt="bad"),
    lambda a: a.update(status="BLOCKED", reasons=None)])
def test_malformed_required_assessment_is_unknown_not_confirmed_or_false_failure(mutation):
    p = problem()
    mutation(p["options"][0]["evaluation"]["derived"]["cargoAssessment"])
    row = first(project(decisions=[p]))
    assert row["primaryCategory"] == "INCOMPLETE_ASSESSMENT" and row["cargo"]["status"] == "UNKNOWN"
    assert "REQUIRED_CARGO_CONNECTION_BLOCKED" not in codes(row)


def test_elapsed_advisory_validity_does_not_mutate_state_or_keep_waiting_on_vessel():
    w, p = world(), problem(human_choice="slower", alternative="COMPATIBLE_UNDER_ASSUMPTIONS")
    approve(w, p)
    port, advisory = review(w, p, state="PROPOSED", advisory_state="issued")
    advisory["validUntil"] = stamp(-2)
    row = first(project(w, [p, port], [advisory]))
    assert row["primaryCategory"] == "REASSESSMENT"
    assert row["workflow"]["nextRole"] == "SHIPPING_COMPANY"
    assert row["deadline"]["hoursRemaining"] == -2 and advisory["state"] == "issued"
    assert "ADVISORY_RESPONSE_WINDOW_ELAPSED" in codes(row)


def test_freshness_dto_drops_noncontract_private_fields():
    p = problem()
    row = first(project(decisions=[p], statuses={p["decisionId"]: {"status": "UNKNOWN", "reasons": [
        {"code": "MISSING", "text": "Original unavailable", "basis": "Consumed hash", "path": "private-file", "token": "secret"}]}}))
    assert "private-file" not in json.dumps(row) and "secret" not in json.dumps(row)


def test_active_proposal_copy_cannot_silently_override_approved_choice():
    w, p = world(), problem()
    approve(w, p)
    w["terminalProposal"] = deepcopy(w["terminalProposal"])
    w["terminalProposal"]["optionId"] = p["options"][1]["optionId"]
    row = first(project(w, [p]))
    assert row["currentPlan"]["basis"] == "AMBIGUOUS"
    assert "ACTIVE_PROPOSAL_BASIS_INCONSISTENT" in codes(row)


def test_conflicting_duplicate_advisory_states_report_updating_not_next_role_guess():
    w, p = world(), problem(human_choice="slower", alternative="COMPATIBLE_UNDER_ASSUMPTIONS")
    approve(w, p)
    port, advisory = review(w, p, state="PROPOSED", advisory_state="issued")
    conflicting = deepcopy(advisory)
    conflicting["state"] = "accepted"
    row = first(project(w, [p, port], [advisory, conflicting]))
    assert row["workflow"]["stage"] == "UPDATING_LINKED_STATE" and row["workflow"]["nextRole"] is None
    assert row["primaryCategory"] == "INCOMPLETE_ASSESSMENT"


@pytest.mark.parametrize("with_call", [True, False])
def test_missing_active_approved_comparison_cannot_fall_back_to_another_baseline(with_call):
    w, active, saved = world(), problem("active"), problem("other-saved")
    approve(w, active)
    if with_call:
        w["terminalProposal"]["operationalEpisode"] = deepcopy(w["fleet"][0]["operationalEpisode"])
    row = first(project(w, [saved]))
    assert row["primaryCategory"] == "INCOMPLETE_ASSESSMENT"
    assert row["currentPlan"]["basis"] == "AMBIGUOUS" and row["currentPlan"]["decisionId"] is None
    assert row["reasons"][0]["code"] == ("ACTIVE_APPROVED_COMPARISON_UNAVAILABLE" if with_call else "ACTIVE_PROPOSAL_CURRENT_CALL_UNAVAILABLE")
    assert row["candidateComparisons"][0]["decisionId"] == "other-saved"


def test_explicit_previous_call_active_pointer_does_not_hide_current_baseline():
    w, old, current = world(), problem("old-active"), problem("current-baseline")
    approve(w, old)
    w["terminalProposal"]["operationalEpisode"] = {**deepcopy(w["fleet"][0]["operationalEpisode"]), "id": "previous-call", "voyageLegId": "previous-leg"}
    row = first(project(w, [current]))
    assert row["currentPlan"]["basis"] == "BASELINE_NOT_APPROVED"
    assert row["currentPlan"]["decisionId"] == "current-baseline"


def test_primary_reason_describes_reassessment_ahead_of_frozen_cargo_and_workflow():
    p = problem(baseline="BLOCKED")
    p["options"][0]["evaluation"]["derived"]["cargoAssessment"]["cutoffAt"] = stamp(-2)
    row = first(project(decisions=[p]))
    assert row["primaryCategory"] == "REASSESSMENT"
    assert row["reasons"][0]["code"] == row["primaryReason"]["code"] == "SCHEDULED_CUTOFF_ELAPSED"
