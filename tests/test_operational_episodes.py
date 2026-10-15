"""Persistent call/action identity in the original visitor-owned role workflow.

Weather products and visitor voyages here are synthetic regression fixtures.
No source provider is contacted and no real execution is asserted.
"""
from datetime import datetime, timedelta

import pytest

from backend.app.services.demo_store import DemoStore
from backend.app.services.demo_terminal import resources
from tests.test_current_recovery import BASE, journey, step
from tests.test_navigation_restrictions import scripted_clock as navigation_clock


@pytest.fixture(autouse=True)
def empty_resource_cache():
    resources.cache_clear()
    yield
    resources.cache_clear()


def restart(store, monkeypatch):
    resources.cache_clear()
    reloaded = DemoStore(store.path)
    monkeypatch.setattr("backend.app.routes.demo.get_demo_store", lambda: reloaded)
    monkeypatch.setattr("backend.app.routes.demo_terminal.get_demo_store", lambda: reloaded)
    return reloaded


def test_call_and_chosen_action_survive_role_handoffs_restart_and_simulation(tmp_path, monkeypatch):
    store, client, token, headers, company, choice, _ = journey(tmp_path, monkeypatch)
    evidence = company["evidence"]["currentEnvironment"]
    episode = evidence["operationalEpisode"]
    assert store.read(token)["fleet"][0]["operationalEpisode"] == episode
    company_path = BASE + "/decisions/problems/" + company["decisionId"]
    step(client, company_path, headers, "REVIEWED")
    step(client, company_path, headers, "APPROVED", choice)
    approved = store.read(token)["terminalProposal"]["approvedAction"]
    assert approved["operationalEpisode"] == episode
    assert approved["actualExecutionStatus"] == "NOT_OBSERVED"
    assert approved["actualExecutionAt"] is None
    action_id = approved["operationalActionId"]

    store = restart(store, monkeypatch)
    assert client.get(company_path, headers=headers).json()["evidence"]["currentEnvironment"] == evidence
    store.switch(token, "PORT_AUTHORITY")
    review = client.post(BASE + "/decisions/current-proposals/review", headers=headers,
                         json={"decisionId": company["decisionId"]})
    assert review.status_code == 200, review.text
    port = review.json()
    assert port["evidence"]["companyProposal"]["approvedAction"] == approved
    assert port["evidence"]["currentEnvironment"]["operationalEpisode"] == episode
    port_path = BASE + "/decisions/problems/" + port["decisionId"]
    step(client, port_path, headers, "REVIEWED")
    step(client, port_path, headers, "APPROVED", choice)
    store = restart(store, monkeypatch)
    handoff = client.post(port_path + "/handoff", headers=headers, json={})
    assert handoff.status_code == 200, handoff.text
    advisory = handoff.json()["advisories"][0]
    action = advisory["evidence"]["approvedAction"]
    assert action["operationalActionId"] == action_id
    assert action["operationalEpisode"] == episode
    assert action["measurementTargets"] == approved["measurementTargets"]
    advisory_path = BASE + "/advisories/" + advisory["advisoryId"]
    step(client, advisory_path, headers, "under_review")
    step(client, advisory_path, headers, "issued")
    store = restart(store, monkeypatch)
    store.switch(token, "VESSEL_OPERATOR")
    assert client.get(advisory_path, headers=headers).json()["evidence"]["approvedAction"] == action
    step(client, advisory_path, headers, "acknowledged")
    step(client, advisory_path, headers, "accepted")
    store = restart(store, monkeypatch)
    store.switch(token, "PORT_AUTHORITY")
    completed = client.post(port_path + "/demo-outcome", headers=headers, json={})
    assert completed.status_code == 200, completed.text
    outcome = completed.json()["outcome"]
    simulated = outcome["simulatedAction"]
    assert outcome["operationalEpisode"] == episode
    assert outcome["operationalActionId"] == action_id
    assert simulated["kind"] == "SIMULATED_DEMO_ACTION"
    assert simulated["recordKind"] == "SIMULATED_OPERATIONAL_RECORD"
    assert simulated["actualExecutionAt"] is None
    assert "executedAt" not in simulated
    assert not simulated["eligibleForRealTarget"] and not outcome["eligibleForRealTarget"]
    assert outcome["realOutcomeStatus"] == "PENDING_ACTUAL_RECORDS"
    store = restart(store, monkeypatch)
    assert client.post(port_path + "/demo-outcome", headers=headers, json={}).json() == completed.json()
    assert store.read(token)["operationalActions"][simulated["id"]] == simulated
    assert client.get(BASE + "/intelligence/feedback/impacts", headers=headers).json()["reliability"]["sampleIds"] == []
    other = store.create("NATIONAL_ADMIN")
    foreign = {"Authorization": "Bearer " + other["accessToken"]}
    assert client.get(advisory_path, headers=foreign).status_code == 404
    assert store.read(other["accessToken"]).get("operationalActions", {}) == {}
    client.close()


def test_eta_edit_and_source_successor_remain_one_call(tmp_path, monkeypatch):
    store, client, token, headers, company, choice, data = journey(tmp_path, monkeypatch)
    original = company["evidence"]["currentEnvironment"]
    episode = original["operationalEpisode"]
    path = BASE + "/decisions/problems/" + company["decisionId"]
    step(client, path, headers, "REVIEWED")
    store.update(token, lambda world: world["fleet"][0].update(etaHours=181))
    blocked = client.post(path + "/transition", headers=headers,
                          json={"target": "APPROVED", "optionId": choice})
    assert blocked.status_code == 409 and "ETA has changed" in blocked.text
    assert store.read(token)["fleet"][0]["operationalEpisode"] == episode
    data["sources"]["surface"]["snapshotId"] = "refreshed-synthetic-source"
    refreshed = client.post(path + "/refresh", headers=headers, json={})
    assert refreshed.status_code == 200, refreshed.text
    successor = refreshed.json()
    assert successor["evidence"]["currentEnvironment"]["operationalEpisode"] == episode
    assert successor["evidence"]["predecessorDecisionId"] == company["decisionId"]
    store = restart(store, monkeypatch)
    recovered = client.get(path, headers=headers).json()
    assert recovered["evidence"]["currentEnvironment"] == original
    assert recovered["evidence"]["successorDecisionId"] == successor["decisionId"]
    assert client.post(path + "/refresh", headers=headers, json={}).json()["decisionId"] == successor["decisionId"]
    client.close()


def test_explicit_new_call_without_reset_is_distinct_and_retry_safe(tmp_path, monkeypatch):
    store, client, token, headers, company, choice, _ = journey(tmp_path, monkeypatch)
    original = company["evidence"]["currentEnvironment"]["operationalEpisode"]
    path = BASE + "/decisions/problems/" + company["decisionId"]
    step(client, path, headers, "REVIEWED")
    step(client, path, headers, "APPROVED", choice)
    epoch = store.read(token)["epoch"]
    arrival = (datetime.fromisoformat(epoch) + timedelta(hours=180)).isoformat()
    payload = {"vesselId": "PWD-001", "requestedArrival": arrival,
               "newCallConfirmed": True, "requestId": "new-call-intent-1"}
    endpoint = BASE + "/intelligence/operational-calls"
    result = client.post(endpoint, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    next_episode = result.json()["episode"]
    assert next_episode["id"] != original["id"]
    assert next_episode["voyageLegId"] != original["voyageLegId"]
    assert next_episode["namespace"] == original["namespace"]
    assert store.read(token)["epoch"] == epoch
    assert "terminalProposal" not in store.read(token)
    assert store.read(token)["weatherJourneys"][company["decisionId"]]["proposal"]["operationalEpisode"] == original
    store = restart(store, monkeypatch)
    assert client.post(endpoint, headers=headers, json=payload).json() == result.json()
    conflicting = {**payload, "requestedArrival": (datetime.fromisoformat(arrival) + timedelta(hours=1)).isoformat()}
    assert client.post(endpoint, headers=headers, json=conflicting).status_code == 422
    another = client.post(endpoint, headers=headers, json={**payload, "requestId": "new-call-intent-2"})
    assert another.status_code == 200, another.text
    assert another.json()["episode"]["id"] != next_episode["id"]
    assert len(store.read(token)["operationalEpisodes"]) == 3
    assert client.get(path, headers=headers).json()["humanChoice"] == choice
    store.switch(token, "PORT_AUTHORITY")
    blocked = client.post(BASE + "/decisions/current-proposals/review", headers=headers,
                          json={"decisionId": company["decisionId"]})
    assert blocked.status_code == 409 and "another operational call" in blocked.text
    client.close()


def test_new_call_declaration_is_role_owned_and_requires_explicit_intent(tmp_path, monkeypatch):
    store, client, token, headers, company, _, _ = journey(tmp_path, monkeypatch)
    arrival = company["evidence"]["currentEnvironment"]["plannedArrival"]
    endpoint = BASE + "/intelligence/operational-calls"
    payload = {"vesselId": "PWD-001", "requestedArrival": arrival,
               "newCallConfirmed": True, "requestId": "owned-call-intent"}
    assert client.post(endpoint, headers=headers, json={**payload, "newCallConfirmed": False}).status_code == 422
    assert client.post(endpoint, headers=headers, json={**payload, "requestId": None}).status_code == 422
    assert client.post(endpoint, headers=headers, json={**payload, "vesselId": "PRIVATE-VESSEL"}).status_code == 404
    store.switch(token, "VESSEL_OPERATOR")
    assert client.post(endpoint, headers=headers, json=payload).status_code == 403
    store.switch(token, "PORT_AUTHORITY")
    assert client.post(endpoint, headers=headers, json=payload).status_code == 403
    other = store.create("SHIPPING_COMPANY")
    foreign = {"Authorization": "Bearer " + other["accessToken"]}
    created = client.post(endpoint, headers=foreign, json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["episode"]["namespace"] != company["evidence"]["currentEnvironment"]["operationalEpisode"]["namespace"]
    assert store.read(token)["fleet"][0]["operationalEpisode"] == company["evidence"]["currentEnvironment"]["operationalEpisode"]
    client.close()


def test_navigation_refresh_uses_its_reviewed_family_and_preserves_call(tmp_path, monkeypatch, navigation_clock):
    import copy
    from tests.test_demo_terminal import setup
    from tests.test_navigation_restrictions import retained, plan
    from src.portwatch_os.intelligence import navigation_restrictions as notices
    store, client = setup(tmp_path, monkeypatch)
    source = retained(tmp_path, monkeypatch)
    session = store.create("SHIPPING_COMPANY")
    token = session["accessToken"]
    headers = {"Authorization": "Bearer " + token}
    declared = client.post(BASE + "/intelligence/navigation-passage-plan", headers=headers, json=plan())
    assert declared.status_code == 200, declared.text
    comparison = client.post(BASE + "/intelligence/navigation-comparison", headers=headers,
                             json={"vesselId": "PWD-001", "revisionId": source["revisionId"]})
    assert comparison.status_code == 200, comparison.text
    original = comparison.json()
    basis = original["evidence"]["intelligenceBasis"]
    path = BASE + "/decisions/problems/" + original["decisionId"]
    choice = next(o["optionId"] for o in original["options"] if not o["isBaseline"])
    step(client, path, headers, "REVIEWED")
    step(client, path, headers, "APPROVED", choice)
    updated = {**source, "revisionId": "synthetic-reviewed-revision-2", "previousRevisionId": source["revisionId"]}
    monkeypatch.setattr(notices, "refresh", lambda *args, **kwargs: copy.deepcopy(updated))
    def wrong_family(*args, **kwargs):
        raise AssertionError("Bridge evidence must not refresh through the Eastham adapter")
    monkeypatch.setattr("src.portwatch_os.intelligence.operational_notices.refresh", wrong_family)
    refreshed = client.post(path + "/refresh", headers=headers, json={})
    assert refreshed.status_code == 200, refreshed.text
    successor = refreshed.json()
    next_basis = successor["evidence"]["intelligenceBasis"]
    assert next_basis["restriction"]["sourceFamily"] == "NAVCEN_MSI"
    assert next_basis["restriction"]["revisionId"] == updated["revisionId"]
    assert next_basis["operationalEpisode"] == basis["operationalEpisode"]
    assert successor["evidence"]["predecessorDecisionId"] == original["decisionId"]
    store = restart(store, monkeypatch)
    saved = client.get(path, headers=headers).json()
    assert saved["evidence"]["intelligenceBasis"] == basis and saved["humanChoice"] == choice
    assert client.post(path + "/refresh", headers=headers, json={}).json()["decisionId"] == successor["decisionId"]
    client.close()
