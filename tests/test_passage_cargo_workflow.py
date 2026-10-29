"""Declared cargo through the real passage calculator and visitor workflow.

All schedules, capacities and weather below are deliberately fictional. They
exercise the existing approval ledger, not a booking or an operational target.
"""
import copy
from datetime import datetime, timedelta

import pytest

from tests.test_current_recovery import step
from tests.test_demo_terminal import resources, setup

BASE = "/api/demo/terminal"


def cargo_journey(tmp_path, monkeypatch, *, must_meet=False, same_gate=False):
    store, client = setup(tmp_path, monkeypatch)
    session = store.create("SHIPPING_COMPANY")
    token = session["accessToken"]
    headers = {"Authorization": "Bearer " + token}
    epoch = datetime.fromisoformat(store.read(token)["epoch"])
    hour = epoch.replace(minute=0, second=0, microsecond=0)
    if hour < epoch:
        hour += timedelta(hours=1)
    stamp = lambda h: (epoch + timedelta(hours=h)).isoformat()
    data = {"portCode": "INNSA", "sources": {
        "surface": {"status": "CURRENT", "source": "SIMULATED hourly contract fixture",
            "snapshotId": "cargo-workflow-hourly", "responseSha256": "a" * 64,
            "issuedAt": None, "availableAt": epoch.isoformat()},
        "hazards": {"snapshotId": "unused-regional-context"}},
        "hourly": [{"validAt": (hour + timedelta(hours=h)).isoformat(),
            "wind_gusts_10m": 20. if h < 184 else 10., "visibility": 10000.,
            "wave_height": .8} for h in range(179, 241)]}
    monkeypatch.setattr("src.portwatch_os.decision.current_arrival.bundle", lambda port: data)
    monkeypatch.setattr("src.portwatch_os.decision.current_arrival.freeze_activity_context", lambda *a, **kw: {})
    plan = {"schemaVersion": 1, "declaredAt": stamp(0), "referenceKind": "AT_SEA",
        "referenceAt": stamp(0), "referenceLabel": "Fictional current hull position",
        "distanceBasis": "Declared scalar demonstration passage; no measured AIS",
        "remainingDistanceNm": 2520., "baselineSpeedKn": 14.,
        "minSpeedKn": 8., "maxSpeedKn": 20., "baselineArrivalAt": stamp(180),
        "alternativeSpeedKn": 2520. / (182. if same_gate else 190.),
        "finance": {"consumption": {"referenceSpeedKn": 14.,
            "referencePropulsionTonnesPerDay": 24., "auxiliaryTonnesPerDay": 2.,
            "anchorageTonnesPerDay": 2., "minSpeedKn": 8., "maxSpeedKn": 20.,
            "loadCondition": "Unchanged simulated load", "source": "Explicit illustrative assumption",
            "declaredAt": stamp(0)}}}
    baseline_clear = hour + timedelta(hours=184)
    cutoff = baseline_clear + timedelta(hours=7)
    connection = {"vesselId": "fictional-onward-A", "name": "Fictional onward sailing A",
        "departureAt": (cutoff + timedelta(hours=2)).isoformat(),
        "loadingCutoffAt": cutoff.isoformat(), "onwardPorts": ["SGSIN"],
        "availableTeu": 100., "availableDeadweightT": 1000.,
        "availableReeferPlugs": 30, "acceptsHazardous": True, "acceptsOog": True,
        "basis": "Explicit fictional schedule and unreserved capacity assumption"}
    later = copy.deepcopy(connection)
    later.update(vesselId="fictional-onward-B", name="Fictional later sailing B",
        departureAt=(cutoff + timedelta(hours=26)).isoformat(),
        loadingCutoffAt=(cutoff + timedelta(hours=24)).isoformat())
    commitment = {"schemaVersion": 1, "fictionalShipment": True,
        "voyageId": "PWD-001", "portCode": "INNSA", "declaredAt": stamp(0),
        "basis": "Explicitly created fictional shipment and onward commitment", "mustMeet": must_meet,
        "shipment": {"shipmentId": "fictional-shipment-01", "teu": 24., "cargoClass": "dry",
            "destinationPort": "SGSIN", "weightT": 240.},
        "transfer": {"approachToStartHours": 2.,
            "basis": "Assumed approach-to-inbound-handling start interval, includes no handling stages",
            "acceptedSchematicHandling": True, "gangs": 1, "mode": "DIRECT"},
        "bookedConnection": connection, "laterConnections": [later]}
    request = {"plannedArrival": stamp(180), "maxGustKn": 15., "minVisibilityM": 5000.,
        "passagePlan": plan, "cargoCommitment": commitment}
    body = {"domain": "vessel", "vesselId": "PWD-001", "currentArrival": request}
    created = client.post(BASE + "/decisions/problems", headers=headers, json=body)
    assert created.status_code == 200, created.text
    return store, client, token, headers, created.json(), body, data


def assessment(option):
    return option["evaluation"]["derived"]["cargoAssessment"]


def test_equal_gate_retains_equal_cargo_timing_and_optional_ranking(tmp_path, monkeypatch):
    _store, client, _token, headers, company, body, _data = cargo_journey(
        tmp_path, monkeypatch, same_gate=True)
    baseline, slow = company["options"]
    assert assessment(baseline)["readinessAt"] == assessment(slow)["readinessAt"]
    assert assessment(baseline)["slackHours"] == assessment(slow)["slackHours"]
    assert assessment(baseline)["handlingHours"] == pytest.approx(24 / 24 + 1.5 + 24 / 22)
    assert baseline["evaluation"]["objectives"]["fuel"]["value"] != slow["evaluation"]["objectives"]["fuel"]["value"]
    no_cargo = copy.deepcopy(body)
    no_cargo["currentArrival"].pop("cargoCommitment")
    raw = client.post(BASE + "/decisions/problems", headers=headers, json=no_cargo)
    assert raw.status_code == 200, raw.text
    raw = raw.json()
    chosen = lambda p: next(o["action"] for o in p["options"] if o["optionId"] == p["recommendation"]["optionId"])
    assert chosen(company) == chosen(raw)
    assert [o["status"] for o in company["options"]] == [o["status"] for o in raw["options"]]
    assert "cargoCommitment" not in raw["evidence"]["currentEnvironment"]
    client.close()


def test_explicit_connection_constraint_rejects_lower_fuel_miss_only_when_required(tmp_path, monkeypatch):
    _store, client, _token, headers, company, body, _data = cargo_journey(tmp_path, monkeypatch)
    baseline, slow = company["options"]
    assert assessment(slow)["status"] == "BLOCKED"
    assert assessment(slow)["slackHours"] < 0 < assessment(baseline)["slackHours"]
    assert slow["status"] == "FEASIBLE"  # Optional context cannot veto navigation.
    assert slow["evaluation"]["objectives"]["fuel"]["value"] < baseline["evaluation"]["objectives"]["fuel"]["value"]
    required = copy.deepcopy(body)
    required["currentArrival"]["cargoCommitment"]["shipment"]["shipmentId"] = "fictional-required-02"
    required["currentArrival"]["cargoCommitment"]["mustMeet"] = True
    response = client.post(BASE + "/decisions/problems", headers=headers, json=required)
    assert response.status_code == 200, response.text
    constrained = response.json()
    assert constrained["options"][0]["status"] == "FEASIBLE"
    assert constrained["options"][1]["status"] == "REJECTED"
    assert any(c["key"] == "cargo_commitment" and not c["passed"] for c in constrained["options"][1]["constraints"])
    assert constrained["recommendation"]["optionId"] == constrained["baselineOptionId"]
    # A supported later sailing is a proposal only, not an executed booking.
    assert assessment(constrained["options"][1])["alternatives"]
    client.close()


def test_saved_cargo_basis_is_immutable_and_linked_edits_require_fresh_review(tmp_path, monkeypatch):
    store, client, token, headers, company, body, _data = cargo_journey(tmp_path, monkeypatch)
    path = BASE + "/decisions/problems/" + company["decisionId"]
    choice = company["baselineOptionId"]
    step(client, path, headers, "REVIEWED")
    step(client, path, headers, "APPROVED", choice)
    frozen = client.get(path, headers=headers).json()
    edited = copy.deepcopy(body)
    edited["currentArrival"]["cargoCommitment"]["bookedConnection"]["availableTeu"] = 10.
    # Same declared shipment must fork the consumed commitment explicitly.
    unlinked = client.post(BASE + "/decisions/problems", headers=headers, json=edited)
    assert unlinked.status_code == 409, unlinked.text
    edited["predecessorDecisionId"] = company["decisionId"]
    successor = client.post(BASE + "/decisions/problems", headers=headers, json=edited)
    assert successor.status_code == 200, successor.text
    successor = successor.json()
    assert successor["workflow"] == "COMPUTED"
    assert successor["evidence"]["predecessorDecisionId"] == company["decisionId"]
    assert assessment(successor["options"][0])["status"] == "BLOCKED"
    resources.cache_clear()
    retry = client.post(BASE + "/decisions/problems", headers=headers, json=edited)
    assert retry.status_code == 200 and retry.json()["decisionId"] == successor["decisionId"]
    old = client.get(path, headers=headers).json()
    assert old["options"] == frozen["options"]
    assert old["evidence"]["currentEnvironment"] == frozen["evidence"]["currentEnvironment"]
    assert old["workflowHistory"] == frozen["workflowHistory"] and old["humanChoice"] == choice
    outsider = store.create("SHIPPING_COMPANY")
    other_headers = {"Authorization": "Bearer " + outsider["accessToken"]}
    assert client.get(path, headers=other_headers).status_code == 404
    assert client.post(BASE + "/decisions/problems", headers=other_headers, json=edited).status_code == 404
    # The original approval remains inspectable but cannot be continued using
    # a superseded consumed connection version.
    store.switch(token, "PORT_AUTHORITY")
    review = client.post(BASE + "/decisions/current-proposals/review", headers=headers,
        json={"decisionId": company["decisionId"]})
    assert review.status_code == 409, review.text
    client.close()


def test_cargo_evidence_survives_role_handoffs_without_booking_or_real_target(tmp_path, monkeypatch):
    store, client, token, headers, company, _body, _data = cargo_journey(tmp_path, monkeypatch, same_gate=True)
    env = copy.deepcopy(company["evidence"]["currentEnvironment"])
    selected = company["options"][1]
    choice = selected["optionId"]
    path = BASE + "/decisions/problems/" + company["decisionId"]
    step(client, path, headers, "REVIEWED")
    step(client, path, headers, "APPROVED", choice)
    approved = store.read(token)["terminalProposal"]["approvedAction"]
    assert approved["cargoCalculation"]["selected"] == assessment(selected)
    resources.cache_clear()
    store.switch(token, "PORT_AUTHORITY")
    review = client.post(BASE + "/decisions/current-proposals/review", headers=headers,
        json={"decisionId": company["decisionId"]})
    assert review.status_code == 200, review.text
    port = review.json()
    assert port["evidence"]["currentEnvironment"] == env
    port_path = BASE + "/decisions/problems/" + port["decisionId"]
    step(client, port_path, headers, "REVIEWED")
    step(client, port_path, headers, "APPROVED", choice)
    issued = client.post(port_path + "/handoff", headers=headers, json={})
    assert issued.status_code == 200, issued.text
    advisory = issued.json()["advisories"][0]
    assert advisory["evidence"]["currentEnvironment"] == env
    assert advisory["evidence"]["approvedAction"]["cargoCalculation"]["selected"] == assessment(selected)
    advisory_path = BASE + "/advisories/" + advisory["advisoryId"]
    step(client, advisory_path, headers, "under_review")
    step(client, advisory_path, headers, "issued")
    store.switch(token, "VESSEL_OPERATOR")
    step(client, advisory_path, headers, "acknowledged")
    step(client, advisory_path, headers, "accepted")
    assert client.post(port_path + "/demo-outcome", headers=headers, json={}).status_code == 403
    store.switch(token, "PORT_AUTHORITY")
    completed = client.post(port_path + "/demo-outcome", headers=headers, json={})
    assert completed.status_code == 200, completed.text
    outcome = completed.json()["outcome"]
    assert outcome["kind"] == "SIMULATED_DEMO_OUTCOME" and outcome["eligibleForRealTarget"] is False
    assert outcome["selectedPassage"]["cargoAssessment"] == assessment(selected)
    resources.cache_clear()
    assert client.post(port_path + "/demo-outcome", headers=headers, json={}).json() == completed.json()
    store.switch(token, "SHIPPING_COMPANY")
    assert client.get(path, headers=headers).json()["evidence"]["currentEnvironment"] == env
    # Only the inbound navigation ETA is simulated; no cargo reservation or
    # cargo execution is created in the visitor world or this advisory.
    world = store.read(token)
    assert not world.get("cargoBookings") and not world.get("cargoExecutions")
    assert advisory["kind"] == "arrival_window"
    client.close()


def test_only_the_consumed_commitment_version_blocks_a_new_approval(tmp_path, monkeypatch):
    store, client, token, headers, company, _body, _data = cargo_journey(tmp_path, monkeypatch)
    path = BASE + "/decisions/problems/" + company["decisionId"]
    step(client, path, headers, "REVIEWED")
    # An unrelated shipment and contextual source counts are not calculation
    # dependencies, even though they are retained in this visitor's world.
    def unrelated(world):
        world.setdefault("cargoCommitments", {})["unrelated-fictional-shipment"] = {
            "inputVersion": "different-unconsumed-version", "voyageId": "PWD-003"}
        world["contextualSourceCount"] = 999
    store.update(token, unrelated)
    approved = client.post(path + "/transition", headers=headers,
        json={"target": "APPROVED", "optionId": company["baselineOptionId"]})
    assert approved.status_code == 200, approved.text
    old_env = approved.json()["evidence"]["currentEnvironment"]
    store.update(token, lambda world: world["cargoCommitments"]["fictional-shipment-01"].update(
        inputVersion="changed-consumed-version"))
    store.switch(token, "PORT_AUTHORITY")
    blocked = client.post(BASE + "/decisions/current-proposals/review", headers=headers,
        json={"decisionId": company["decisionId"]})
    assert blocked.status_code == 409 and "shipment or connection" in blocked.text
    store.switch(token, "SHIPPING_COMPANY")
    assert client.get(path, headers=headers).json()["evidence"]["currentEnvironment"] == old_env
    client.close()


def test_failed_decision_finish_cannot_orphan_the_shipment_registry(tmp_path, monkeypatch):
    store, client, token, headers, _company, body, _data = cargo_journey(tmp_path, monkeypatch)
    original = copy.deepcopy(store.read(token)["cargoCommitments"])
    body["currentArrival"]["cargoCommitment"]["shipment"]["shipmentId"] = "unrecorded-fictional-shipment"
    def refusal(*_args, **_kwargs):
        raise ValueError("Synthetic decision validation refusal")
    monkeypatch.setattr("src.portwatch_os.decision.engine.DecisionEngine.finish", refusal)
    response = client.post(BASE + "/decisions/problems", headers=headers, json=body)
    assert response.status_code == 400 and "validation refusal" in response.text
    assert store.read(token)["cargoCommitments"] == original
    resources.cache_clear()
    assert store.read(token)["cargoCommitments"] == original
    client.close()


@pytest.mark.parametrize("missing", ["cutoff", "start", "capacity"])
def test_unknown_required_connection_basis_never_becomes_approvable(tmp_path, monkeypatch, missing):
    _store, client, _token, headers, _company, body, _data = cargo_journey(tmp_path, monkeypatch, same_gate=True)
    commitment = body["currentArrival"]["cargoCommitment"]
    commitment["shipment"]["shipmentId"] = "unknown-required-" + missing
    commitment["mustMeet"] = True
    if missing == "cutoff":
        commitment["bookedConnection"].pop("loadingCutoffAt")
    elif missing == "start":
        commitment["transfer"].pop("approachToStartHours")
    else:
        commitment["bookedConnection"].pop("availableTeu")
    created = client.post(BASE + "/decisions/problems", headers=headers, json=body)
    assert created.status_code == 200, created.text
    problem = created.json()
    assert all(o["status"] == "REJECTED" for o in problem["options"])
    assert all(assessment(o)["status"] == "UNKNOWN" for o in problem["options"])
    if missing == "cutoff":
        assert all(assessment(o)["cutoffAt"] is None for o in problem["options"])
    path = BASE + "/decisions/problems/" + problem["decisionId"]
    step(client, path, headers, "REVIEWED")
    approval = client.post(path + "/transition", headers=headers,
        json={"target": "APPROVED", "optionId": problem["baselineOptionId"]})
    assert approval.status_code == 400, approval.text
    client.close()


@pytest.mark.parametrize("field,value", [("voyageId", "someone-elses-voyage"), ("portCode", "SGSIN"),
    ("fictionalShipment", False)])
def test_commitment_identity_cannot_bind_unowned_or_uncreated_shipment(tmp_path, monkeypatch, field, value):
    _store, client, _token, headers, _company, body, _data = cargo_journey(tmp_path, monkeypatch)
    body["currentArrival"]["cargoCommitment"][field] = value
    response = client.post(BASE + "/decisions/problems", headers=headers, json=body)
    assert response.status_code == 400, response.text
    client.close()
