"""Passage contracts through the existing visitor workflow, without providers.

Arithmetic belongs to the passage calculator tests. This synthetic builder
isolates approval, saved evidence, recovery and advisory serialization.
"""
import copy
from datetime import datetime, timedelta
import hashlib
import json
from types import SimpleNamespace

import pytest

from tests.test_current_input_journey import forecast
from tests.test_current_recovery import step
from tests.test_demo_terminal import resources, setup

BASE = "/api/demo/terminal"


def passage_journey(tmp_path, monkeypatch, action="SLOW_STEAM"):
    from src.portwatch_os.decision import current_arrival
    store, client = setup(tmp_path, monkeypatch)
    session = store.create("SHIPPING_COMPANY")
    token = session["accessToken"]
    headers = {"Authorization": "Bearer " + token}
    epoch = datetime.fromisoformat(store.read(token)["epoch"])
    data = forecast(epoch)
    monkeypatch.setattr(current_arrival, "bundle", lambda port: data)
    original_builder = current_arrival.build_arrival_problem
    received = []

    def contract_builder(vessel, request, actor, state, at):
        received.append(copy.deepcopy(request))
        # Keep this workflow test independent of the calculator's input schema.
        legacy = {k: v for k, v in request.items() if k != "passagePlan"}
        problem = original_builder(vessel, legacy, actor, state, at)
        basis = problem.evidence["currentEnvironment"]
        basis["passagePlan"] = copy.deepcopy(request["passagePlan"])
        basis["passageComparison"] = {"version": "workflow-fixture-v1", "options": []}
        basis["evidenceId"] = hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()
        problem.options[0].evaluation.derived["anchorageWaitHours"] = 7.
        selected = problem.options[1]
        selected.action = action
        selected.label = "Synthetic declared passage alternative"
        selected.params.update(speedKn=12., holdHours=1. if action == "DELAY_DEPARTURE" else 0.,
                               passagePlanVersion="workflow-input-v1")
        derived = selected.evaluation.derived
        derived.update(arrivalAt=(epoch + timedelta(hours=184)).isoformat(),
                       approachClearAt=(epoch + timedelta(hours=185)).isoformat(),
                       arrivalShiftHours=4., speedKn=12., sailingHours=20.,
                       holdHours=selected.params["holdHours"], anchorageWaitHours=1.,
                       totalElapsedHours=21., scheduleShiftHours=5., deadlineMet=False,
                       departureAt=(epoch + timedelta(hours=164)).isoformat())
        return problem

    monkeypatch.setattr(current_arrival, "build_arrival_problem", contract_builder)
    plan = {"schemaVersion": 1, "fixture": "Simulated workflow contract only",
            "declaredAt": epoch.isoformat(), "referenceKind": "AT_SEA",
            "referenceLabel": "Simulated position", "distanceBasis": "Declared scalar demo distance",
            "referenceAt": epoch.isoformat(), "remainingDistanceNm": 2520.,
            "baselineArrivalAt": (epoch + timedelta(hours=180)).isoformat(),
            "baselineSpeedKn": 14., "minSpeedKn": 8., "maxSpeedKn": 20.}
    response = client.post(BASE + "/decisions/problems", headers=headers, json={
        "domain": "vessel", "vesselId": "PWD-001", "currentArrival": {
            "plannedArrival": (epoch + timedelta(hours=181)).isoformat(),
            "maxGustKn": 15, "minVisibilityM": 5000, "passagePlan": plan}})
    assert response.status_code == 200, response.text
    return store, client, token, headers, response.json(), received, data


@pytest.mark.parametrize("action", ["SLOW_STEAM", "SPEED_UP", "DELAY_DEPARTURE"])
def test_passage_selection_survives_approvals_eviction_and_simulated_outcome(tmp_path, monkeypatch, action):
    store, client, token, headers, company, _, _ = passage_journey(tmp_path, monkeypatch, action)
    env = company["evidence"]["currentEnvironment"]
    selected = company["options"][1]
    choice = selected["optionId"]
    cp = BASE + "/decisions/problems/" + company["decisionId"]
    step(client, cp, headers, "REVIEWED")
    step(client, cp, headers, "APPROVED", choice)
    proposal = store.read(token)["terminalProposal"]
    assert proposal["approvedAction"]["passageCalculation"]["inputs"] == env["passagePlan"]
    assert proposal["approvedAction"]["passageCalculation"]["selected"] == selected["evaluation"]["derived"]
    store.switch(token, "PORT_AUTHORITY")
    review = client.post(BASE + "/decisions/current-proposals/review", headers=headers,
                         json={"decisionId": company["decisionId"]})
    assert review.status_code == 200, review.text
    port = review.json()
    pp = BASE + "/decisions/problems/" + port["decisionId"]
    assert port["evidence"]["currentEnvironment"] == env
    assert port["recommendation"]["policy"] == "declared-passage-comparison-v1"
    assert "does not command navigation" in port["recommendation"]["statement"]
    step(client, pp, headers, "REVIEWED")
    changed = client.post(pp + "/transition", headers=headers,
                          json={"target": "APPROVED", "optionId": company["options"][0]["optionId"]})
    assert changed.status_code == 409 and "Company's selected passage plan" in changed.text
    step(client, pp, headers, "APPROVED", choice)
    handoff = client.post(pp + "/handoff", headers=headers, json={})
    assert handoff.status_code == 200, handoff.text
    rows = handoff.json()["advisories"]
    recommendation = rows[0]["recommendation"]
    assert recommendation["action"] == action
    assert recommendation["recommendedSpeedKn"] == 12
    assert recommendation["passagePlanVersion"] == "workflow-input-v1"
    assert recommendation["deadlineMet"] is False
    resources.cache_clear()
    assert client.post(pp + "/handoff", headers=headers, json={}).json()["advisories"] == rows
    ap = BASE + "/advisories/" + rows[0]["advisoryId"]
    edited = client.post(ap + "/modify", headers=headers, json={
        "changes": {"recommendedSpeedKn": 18.}, "reason": "Try changing the frozen speed"})
    assert edited.status_code == 409 and "linked successor" in edited.text
    assert client.get(ap, headers=headers).json()["recommendation"] == recommendation
    step(client, ap, headers, "under_review")
    step(client, ap, headers, "issued")
    store.switch(token, "VESSEL_OPERATOR")
    step(client, ap, headers, "acknowledged")
    step(client, ap, headers, "accepted")
    store.switch(token, "PORT_AUTHORITY")
    done = client.post(pp + "/demo-outcome", headers=headers, json={})
    assert done.status_code == 200, done.text
    outcome = done.json()["outcome"]
    assert outcome["clearApproachAt"] == selected["evaluation"]["derived"]["approachClearAt"]
    assert outcome["clearApproachAt"] != env["firstClearApproach"]
    assert outcome["selectedPassage"] == selected["evaluation"]["derived"]
    assert outcome["selectedParameters"] == selected["params"]
    assert outcome["totalScheduleShiftHours"] == 5
    assert outcome["baselineAssumedWaitHours"] == 7.
    assert outcome["selectedAssumedWaitHours"] == 1.
    assert outcome["eligibleForRealTarget"] is False
    resources.cache_clear()
    assert client.post(pp + "/demo-outcome", headers=headers, json={}).json() == done.json()
    other = store.create("PORT_AUTHORITY")
    outsider = {"Authorization": "Bearer " + other["accessToken"]}
    assert client.get(pp, headers=outsider).status_code == 404
    assert client.get(ap, headers=outsider).status_code == 404
    client.close()


def test_passage_refresh_keeps_declared_inputs_without_mutating_saved_approval(tmp_path, monkeypatch):
    store, client, token, headers, company, received, data = passage_journey(tmp_path, monkeypatch)
    cp = BASE + "/decisions/problems/" + company["decisionId"]
    choice = company["options"][1]["optionId"]
    step(client, cp, headers, "REVIEWED")
    step(client, cp, headers, "APPROVED", choice)
    approved = client.get(cp, headers=headers).json()
    later = datetime.fromisoformat(data["sources"]["surface"]["availableAt"]) + timedelta(hours=2)
    monkeypatch.setattr("src.portwatch_os.clock.wall_now", lambda: later)
    data["sources"]["surface"]["availableAt"] = later.isoformat()
    expired = client.post(cp + "/refresh", headers=headers, json={})
    assert expired.status_code == 409 and "explicit current passage declaration" in expired.text
    updated = copy.deepcopy(received[0])
    updated["passagePlan"].update(declaredAt=later.isoformat(), referenceAt=later.isoformat(),
        remainingDistanceNm=2492.)
    refreshed = client.post(cp + "/refresh", headers=headers, json={"currentArrival": updated})
    assert refreshed.status_code == 200, refreshed.text
    successor = refreshed.json()
    assert received[-1]["passagePlan"] == updated["passagePlan"]
    assert successor["workflow"] == "COMPUTED"
    assert successor["evidence"]["predecessorDecisionId"] == company["decisionId"]
    resources.cache_clear()
    original = client.get(cp, headers=headers).json()
    assert original["options"] == approved["options"]
    assert original["humanChoice"] == choice
    assert original["workflowHistory"] == approved["workflowHistory"]
    client.close()


def test_physical_passage_action_identity_changes_with_route_not_price():
    from src.portwatch_os.learning.shared_feedback import operational_action_id
    basis = {
        "operationalEpisode": {"namespace": "visitor-a", "id": "call-a", "vesselId": "PWD-001"},
        "portCode": "INNSA", "plannedArrival": "2026-10-30T12:00:00+00:00",
        "earliestVoyageArrival": "2026-10-30T10:00:00+00:00",
        "passagePlan": {"schemaVersion": 1, "referenceKind": "AT_SEA",
            "referenceAt": "2026-10-23T12:00:00+00:00", "referenceLabel": "Simulated position A",
            "remainingDistanceNm": 240., "distanceBasis": "Operator declared simulated leg",
            "geometry": [[12., 70.], [16., 72.]], "finance": {"bunkerPrice": 500.}},
    }
    option = SimpleNamespace(action="SLOW_STEAM", params={"speedKn": 12., "holdHours": 0.,
        "arrivalAt": basis["plannedArrival"], "passagePlanVersion": "declared-passage-v1"},
        evaluation=SimpleNamespace(derived={"arrivalAt": basis["plannedArrival"]}))
    original = operational_action_id(basis, option)
    price = copy.deepcopy(basis)
    price["passagePlan"]["finance"]["bunkerPrice"] = 900.
    assert operational_action_id(price, option) == original
    geometry = copy.deepcopy(basis)
    geometry["passagePlan"]["geometry"] = [[12., 70.], [14., 72.], [16., 72.]]
    assert operational_action_id(geometry, option) != original
    reference = copy.deepcopy(basis)
    reference["passagePlan"]["referenceAt"] = "2026-10-23T13:00:00+00:00"
    assert operational_action_id(reference, option) != original


def test_edited_successors_are_scoped_retry_safe_and_keep_prior_approval(tmp_path, monkeypatch):
    store, client, token, headers, company, received, _ = passage_journey(tmp_path, monkeypatch)
    cp = BASE + "/decisions/problems/" + company["decisionId"]
    choice = company["options"][1]["optionId"]
    step(client, cp, headers, "REVIEWED")
    step(client, cp, headers, "APPROVED", choice)
    approved = client.get(cp, headers=headers).json()
    edited = copy.deepcopy(received[0])
    edited["passagePlan"]["alternativeSpeedKn"] = 11.
    body = {"domain": "vessel", "vesselId": "PWD-001", "currentArrival": edited,
            "predecessorDecisionId": company["decisionId"]}
    first = client.post(BASE + "/decisions/problems", headers=headers, json=body)
    assert first.status_code == 200, first.text
    successor = first.json()
    assert successor["workflow"] == "COMPUTED"
    assert successor["evidence"]["predecessorDecisionId"] == company["decisionId"]
    resources.cache_clear()
    assert client.post(BASE + "/decisions/problems", headers=headers, json=body).json()["decisionId"] == successor["decisionId"]
    original = client.get(cp, headers=headers).json()
    assert original["options"] == approved["options"]
    assert original["humanChoice"] == choice and original["workflowHistory"] == approved["workflowHistory"]
    assert original["evidence"]["successorDecisionIds"] == [successor["decisionId"]]
    edited["passagePlan"]["alternativeSpeedKn"] = 10.
    changed = client.post(cp + "/refresh", headers=headers, json={"currentArrival": edited})
    assert changed.status_code == 200, changed.text
    assert changed.json()["decisionId"] != successor["decisionId"]
    assert len(client.get(cp, headers=headers).json()["evidence"]["successorDecisionIds"]) == 2
    other = store.create("SHIPPING_COMPANY")
    outsiders = {"Authorization": "Bearer " + other["accessToken"]}
    assert client.post(BASE + "/decisions/problems", headers=outsiders, json=body).status_code == 404
    store.switch(token, "PORT_AUTHORITY")
    assert client.post(BASE + "/decisions/problems", headers=headers, json=body).status_code == 403
    client.close()


def test_actual_passage_builder_reaches_original_advisory_contract(tmp_path, monkeypatch):
    """The real calculator must integrate, beyond the synthetic contract cases."""
    store, client = setup(tmp_path, monkeypatch)
    session = store.create("SHIPPING_COMPANY")
    token = session["accessToken"]
    headers = {"Authorization": "Bearer " + token}
    epoch = datetime.fromisoformat(store.read(token)["epoch"])
    data = forecast(epoch)
    for row in data["hourly"]:
        valid = datetime.fromisoformat(row["validAt"])
        whole = valid.replace(minute=0, second=0, microsecond=0)
        row["validAt"] = (whole if valid == whole else whole + timedelta(hours=1)).isoformat()
    monkeypatch.setattr("src.portwatch_os.decision.current_arrival.bundle", lambda port: data)
    plan = {"schemaVersion": 1, "declaredAt": epoch.isoformat(),
        "referenceKind": "AT_SEA", "referenceAt": epoch.isoformat(),
        "referenceLabel": "Simulated remaining-passage position",
        "distanceBasis": "Explicit scalar demo distance; no measured AIS route",
        "remainingDistanceNm": 2520., "baselineSpeedKn": 14., "minSpeedKn": 8., "maxSpeedKn": 20.,
        "baselineArrivalAt": (epoch + timedelta(hours=180)).isoformat(),
        "alternativeSpeedKn": 2520. / 182., "deadlineAt": (epoch + timedelta(hours=185)).isoformat()}
    created = client.post(BASE + "/decisions/problems", headers=headers, json={
        "domain": "vessel", "vesselId": "PWD-001", "currentArrival": {
            "plannedArrival": (epoch + timedelta(hours=181)).isoformat(),
            "maxGustKn": 15., "minVisibilityM": 5000., "passagePlan": plan}})
    assert created.status_code == 200, created.text
    company = created.json()
    env = company["evidence"]["currentEnvironment"]
    assert env["passagePlan"] == plan
    selected = next(option for option in company["options"] if option["action"] == "SLOW_STEAM")
    assert selected["status"] == "FEASIBLE", selected
    assert selected["evaluation"]["derived"]["sailingHours"] == pytest.approx(182.)
    assert selected["evaluation"]["objectives"]["fuel"]["available"] is False
    assert selected["evaluation"]["financial"]["complete"] is False
    cp = BASE + "/decisions/problems/" + company["decisionId"]
    choice = selected["optionId"]
    step(client, cp, headers, "REVIEWED")
    step(client, cp, headers, "APPROVED", choice)
    store.switch(token, "PORT_AUTHORITY")
    review = client.post(BASE + "/decisions/current-proposals/review", headers=headers,
                         json={"decisionId": company["decisionId"]})
    assert review.status_code == 200, review.text
    port = review.json()
    pp = BASE + "/decisions/problems/" + port["decisionId"]
    for copied, original in zip(port["options"], company["options"]):
        assert copied["actor"] == "PORT_AUTHORITY"
        assert copied["params"] == original["params"]
        assert copied["evaluation"] == original["evaluation"]
    step(client, pp, headers, "REVIEWED")
    step(client, pp, headers, "APPROVED", choice)
    handoff = client.post(pp + "/handoff", headers=headers, json={})
    assert handoff.status_code == 200, handoff.text
    advisory = handoff.json()["advisories"][0]
    assert advisory["evidence"]["currentEnvironment"] == env
    assert advisory["evidence"]["approvedAction"]["passageCalculation"]["selected"] == selected["evaluation"]["derived"]
    assert advisory["recommendation"]["recommendedSpeedKn"] == pytest.approx(2520. / 182.)
    assert advisory["recommendation"]["sailingHours"] == pytest.approx(182.)
    ap = BASE + "/advisories/" + advisory["advisoryId"]
    step(client, ap, headers, "under_review")
    step(client, ap, headers, "issued")
    store.switch(token, "VESSEL_OPERATOR")
    step(client, ap, headers, "acknowledged")
    step(client, ap, headers, "accepted")
    store.switch(token, "PORT_AUTHORITY")
    completed = client.post(pp + "/demo-outcome", headers=headers, json={})
    assert completed.status_code == 200, completed.text
    outcome = completed.json()["outcome"]
    clear_at = datetime.fromisoformat(selected["evaluation"]["derived"]["approachClearAt"])
    assert outcome["baselineAssumedWaitHours"] == pytest.approx((clear_at-epoch).total_seconds()/3600.-180.)
    assert outcome["selectedAssumedWaitHours"] == pytest.approx((clear_at-epoch).total_seconds()/3600.-182.)
    assert outcome["totalScheduleShiftHours"] == pytest.approx(0.)
    assert outcome["selectedPassage"] == selected["evaluation"]["derived"]
    assert outcome["eligibleForRealTarget"] is False
    # A simulated outcome changes the visitor's current ETA. Refresh must
    # validate against that current world, rather than the predecessor's ETA:
    # old inputs cannot silently degrade, explicit consistent inputs can fork.
    store.switch(token, "SHIPPING_COMPANY")
    old_inputs = client.post(cp + "/refresh", headers=headers, json={})
    assert old_inputs.status_code == 409 and "current passage declaration" in old_inputs.text
    from backend.app.services.demo_terminal import company_for
    current_eta = company_for(store.read(token)).vessel("PWD-001").eta
    revised_plan = copy.deepcopy(plan)
    revised_plan["baselineArrivalAt"] = current_eta
    revised_plan["remainingDistanceNm"] = (datetime.fromisoformat(current_eta)-epoch).total_seconds()/3600.*14.
    revised = client.post(cp + "/refresh", headers=headers, json={"currentArrival": {
        "plannedArrival": current_eta, "maxGustKn": 15., "minVisibilityM": 5000., "passagePlan": revised_plan}})
    assert revised.status_code == 200, revised.text
    assert revised.json()["evidence"]["currentEnvironment"]["passagePlan"] == revised_plan
    assert revised.json()["evidence"]["predecessorDecisionId"] == company["decisionId"]
    assert client.get(cp, headers=headers).json()["humanChoice"] == choice
    client.close()
