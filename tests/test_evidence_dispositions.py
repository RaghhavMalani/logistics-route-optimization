"""Synthetic task reviews; no real port event or model skill is asserted."""
import copy
from datetime import timedelta
import pytest

from tests.test_demo_terminal import resources, setup
from tests.test_current_recovery import BASE
from src.portwatch_os.learning.shared_feedback import identifier, instant
from src.portwatch_os.intelligence.evidence_dispositions import TASK_QUESTION


def scenario(tmp_path, monkeypatch, semantic="AGGREGATE_PORT_ACTIVITY", port="INNSA"):
    store, client = setup(tmp_path, monkeypatch)
    session = store.create("SHIPPING_COMPANY")
    token = session["accessToken"]
    headers = {"Authorization": "Bearer " + token}
    at = store.read(token)["epoch"]
    selector = {"product": "IMF_PORTWATCH_DAILY", "receiptId": "synthetic-receipt", "recordId": "synthetic-row", "portCode": port}
    evidence = {"selector": selector, "product": selector["product"], "semanticClass": semantic,
        "portCode": port, "firstAvailableAt": at, "observedAt": at, "sha256": "a" * 64,
        "sourceUrl": "https://fixture.example/port-activity", "originalHashVerified": True,
        "record": {"date": at[:10], "count": 17, "unit": "aggregate reported vessel visits"},
        "meaning": "Synthetic aggregate port context; not individual vessel movement", "status": "CURRENT"}
    selected = {identifier(selector): evidence}
    def resolve(value):
        if identifier(value) not in selected:
            raise ValueError("Retained evidence selector unavailable")
        return copy.deepcopy(selected[identifier(value)])
    monkeypatch.setattr("backend.app.routes.shipping_intelligence._operational_evidence", resolve)
    body = {"vesselId": "PWD-001", "requestId": "context-task-fixture", "operationalEvidence": selector,
        "portContextConfirmed": True}
    task_response = client.post(BASE + "/intelligence/review-tasks", headers=headers, json=body)
    assert task_response.status_code == 200, task_response.text
    return store, client, token, headers, body, task_response.json(), selected


def review_body(selector, **changes):
    return {"requestId": "context-review-fixture", "operationalEvidence": selector,
        "dispositionType": "CONTEXT_REVIEWED", "contextConfirmed": True,
        "note": "Reviewed the published port context, with no individual outcome assertion.", **changes}


def test_context_question_review_freezes_original_and_does_not_resolve_real_claims(tmp_path, monkeypatch):
    store, client, token, h, body, task, selected = scenario(tmp_path, monkeypatch)
    assert task["taskQuestion"] == TASK_QUESTION
    assert task["status"] == "PENDING_VERIFICATION" and not task["createsOperationalTarget"]
    path = BASE + "/intelligence/review-tasks/" + task["id"] + "/dispositions"
    response = client.post(path, headers=h, json=review_body(body["operationalEvidence"]))
    assert response.status_code == 200, response.text
    disposition = response.json()
    assert disposition["originalTask"] == task
    assert disposition["originalTaskSha256"] == identifier(task)
    assert disposition["evidence"] == selected[identifier(body["operationalEvidence"])]
    assert disposition["actor"] == "demo-company" and disposition["role"] == "SHIPPING_COMPANY"
    assert disposition["reviewedAt"] and disposition["answersContextQuestion"]
    assert disposition["taskStatus"] == "CONTEXT_REVIEWED"
    for field in ("newsVerificationChanged", "createsOperationalTarget", "eligibleForRealTarget"):
        assert disposition[field] is False
    assert disposition["realResolvedTargetsAdded"] == 0
    assert disposition["actualExecutionStatus"] == "NOT_OBSERVED"
    assert disposition["sourceClaimStatus"] == "UNRESOLVED"
    assert disposition["calculatedDelayHours"] is None and disposition["calculatedCost"] is None
    assert not client.get(BASE + "/intelligence/feedback/impacts", headers=h).json()["claims"]
    assert client.get(BASE + "/decisions/problems", headers=h).json()["total"] == 0
    projected = client.get(BASE + "/intelligence/review-tasks", headers=h).json()["tasks"][0]
    assert projected["status"] == "CONTEXT_REVIEWED" and projected["dispositions"] == [disposition]
    assert projected["source"] == task["source"] and projected["exposure"] == task["exposure"]
    # Retrying creation returns the immutable original, not a rewritten ledger claim.
    assert client.post(BASE + "/intelligence/review-tasks", headers=h, json=body).json() == task
    client.close(); resources.cache_clear()


def test_context_review_retries_recovery_and_visitor_isolation(tmp_path, monkeypatch):
    store, client, token, h, body, task, _ = scenario(tmp_path, monkeypatch)
    path = BASE + "/intelligence/review-tasks/" + task["id"] + "/dispositions"
    payload = review_body(body["operationalEvidence"])
    first = client.post(path, headers=h, json=payload)
    assert first.status_code == 200, first.text
    resources.cache_clear()
    # Retry must recover a completed write even when the provider later fails.
    monkeypatch.setattr("backend.app.routes.shipping_intelligence._operational_evidence",
        lambda selector: (_ for _ in ()).throw(ValueError("provider unavailable")))
    assert client.post(path, headers=h, json=payload).json() == first.json()
    assert client.post(path, headers=h, json={**payload, "note": "changed"}).status_code == 409
    current = client.get(BASE + "/intelligence/review-tasks", headers=h).json()["tasks"][0]
    assert current["dispositions"] == [first.json()]
    other = store.create("SHIPPING_COMPANY")
    oh = {"Authorization": "Bearer " + other["accessToken"]}
    assert client.post(path, headers=oh, json=payload).status_code == 404
    assert client.get(BASE + "/intelligence/review-tasks", headers=oh).json()["tasks"] == []
    store.switch(token, "VESSEL_OPERATOR")
    assert client.post(path, headers=h, json=payload).status_code == 403
    assert len(client.get(BASE + "/intelligence/review-tasks", headers=h).json()["tasks"]) == 1
    store.switch(token, "NATIONAL_ADMIN")
    assert client.post(path, headers=h, json=payload).status_code == 403
    store.switch(token, "PORT_AUTHORITY")
    # Permission is checked before retry lookup, including role-owned physical port.
    assert client.post(path, headers=h, json=payload).json() == first.json()
    store.update(token, lambda world: world["intelligenceReviewTasks"][task["id"]].update(portCode="INMAA"))
    assert client.post(path, headers=h, json=payload).status_code == 403
    client.close(); resources.cache_clear()


def test_context_review_rejects_future_unretained_simulated_and_arbitrary_outcomes(tmp_path, monkeypatch):
    store, client, token, h, body, task, selected = scenario(tmp_path, monkeypatch)
    path = BASE + "/intelligence/review-tasks/" + task["id"] + "/dispositions"
    selector = body["operationalEvidence"]
    original = copy.deepcopy(selected[identifier(selector)])
    payload = review_body(selector)
    assert client.post(path, headers=h, json={**payload, "observedValue": 2.25}).status_code == 422
    assert client.post(path, headers=h, json={**payload, "dispositionType": "CORROBORATED"}).status_code == 422
    assert client.post(path, headers=h, json={**payload, "contextConfirmed": False}).status_code == 422
    for changes in ({"firstAvailableAt": (instant(original["firstAvailableAt"]) + timedelta(days=30)).isoformat()},
            {"originalHashVerified": False}, {"semanticClass": "ACTUAL_OPERATIONAL_RECORD"},
            {"record": {"recordKind": "SIMULATED_OUTCOME"}}, {"isSimulated": True},
            {"record": []}, {"selector": "unretained"},
            {"firstAvailableAt": original["firstAvailableAt"][:19]},
            {"observedAt": (instant(original["firstAvailableAt"]) + timedelta(days=1)).isoformat()},
            {"publishedAt": (instant(original["firstAvailableAt"]) + timedelta(days=1)).isoformat()},
            {"checkedAt": (instant(original["firstAvailableAt"]) + timedelta(days=1)).isoformat()}):
        selected[identifier(selector)] = {**original, **changes}
        result = client.post(path, headers=h, json=payload)
        assert result.status_code == 409, result.text
    assert not client.get(BASE + "/intelligence/review-tasks", headers=h).json()["tasks"][0].get("dispositions")
    client.close(); resources.cache_clear()


def test_other_port_requires_explicit_context_and_cannot_be_swapped_after_task_freeze(tmp_path, monkeypatch):
    store, client, token, h, body, task, selected = scenario(tmp_path, monkeypatch, port="INPRT")
    assert task["portCode"] == "INNSA" and task["source"]["contextDeclaration"]["portCode"] == "INPRT"
    endpoint = BASE + "/intelligence/review-tasks"
    missing_confirmation = {**body, "requestId": "other-context-unconfirmed", "portContextConfirmed": False}
    assert client.post(endpoint, headers=h, json=missing_confirmation).status_code == 409
    wrong_selector = {**body["operationalEvidence"], "portCode": "INMAA"}
    evidence = selected[identifier(body["operationalEvidence"])]
    selected[identifier(wrong_selector)] = {**evidence, "portCode": "INMAA", "selector": wrong_selector}
    path = endpoint + "/" + task["id"] + "/dispositions"
    result = client.post(path, headers=h, json=review_body(wrong_selector))
    assert result.status_code == 409 and "physical-port" in result.text
    assert task["source"]["contextDeclaration"]["meaning"].startswith("Context selection only")
    client.close(); resources.cache_clear()


def test_individual_publisher_record_review_does_not_associate_fictional_hull_or_allfast(tmp_path, monkeypatch):
    store, client, token, h, body, task, selected = scenario(tmp_path, monkeypatch, semantic="REPORTED_PORT_ARRIVAL", port="INMAA")
    path = BASE + "/intelligence/review-tasks/" + task["id"] + "/dispositions"
    result = client.post(path, headers=h, json=review_body(body["operationalEvidence"]))
    assert result.status_code == 200, result.text
    assert result.json()["eligibleForRealTarget"] is False
    world = store.read(token)
    assert world["fleet"][0]["mmsi"] is None
    assert not world["fleet"][0].get("realVesselAssociation")
    assert not world.get("currentArrivalOutcome")
    assert "all-fast" in result.json()["meaning"]
    client.close(); resources.cache_clear()


def test_stale_context_and_future_expected_target_keep_their_exact_semantics(tmp_path, monkeypatch):
    store, client, token, h, body, task, selected = scenario(tmp_path, monkeypatch,
        semantic="PUBLISHED_EXPECTED_ARRIVAL", port="INMAA")
    selector = body["operationalEvidence"]
    original = selected[identifier(selector)]
    original.update(status="STALE", reportAgeDays=7, publishedAt=None, observedAt=None,
        record={"expectedArrivalAt": (instant(original["firstAvailableAt"]) + timedelta(days=3)).isoformat(),
                "meaning": "Publisher expected arrival; no observed arrival"})
    response = client.post(BASE + "/intelligence/review-tasks/" + task["id"] + "/dispositions",
        headers=h, json=review_body(selector))
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["evidence"]["status"] == "STALE"
    assert reviewed["evidence"]["publishedAt"] is None
    assert reviewed["evidence"]["observedAt"] is None
    assert reviewed["evidence"]["record"] == original["record"]
    assert reviewed["evidencePortCode"] == "INMAA" and reviewed["portCode"] == "INNSA"
    assert reviewed["actualExecutionStatus"] == "NOT_OBSERVED"
    assert reviewed["realResolvedTargetsAdded"] == 0
    client.close(); resources.cache_clear()


def test_new_evidence_review_keeps_original_receipt_and_each_review_immutable(tmp_path, monkeypatch):
    store, client, token, h, body, task, selected = scenario(tmp_path, monkeypatch)
    first_selector = body["operationalEvidence"]
    next_selector = {**first_selector, "receiptId": "synthetic-new-receipt", "recordId": "synthetic-new-row"}
    selected[identifier(next_selector)] = {**copy.deepcopy(selected[identifier(first_selector)]),
        "selector": next_selector, "sha256": "b" * 64, "record": {"count": 18}}
    path = BASE + "/intelligence/review-tasks/" + task["id"] + "/dispositions"
    first = client.post(path, headers=h, json=review_body(first_selector))
    second = client.post(path, headers=h, json=review_body(next_selector, requestId="next-context-review"))
    assert first.status_code == second.status_code == 200
    resources.cache_clear()
    projected = client.get(BASE + "/intelligence/review-tasks", headers=h).json()["tasks"][0]
    assert len(projected["dispositions"]) == 2
    assert projected["source"]["operationalEvidence"]["selector"] == first_selector
    assert all(row["originalTask"] == task for row in projected["dispositions"])
    assert {row["evidence"]["sha256"] for row in projected["dispositions"]} == {"a" * 64, "b" * 64}
    assert sum(row["realResolvedTargetsAdded"] for row in projected["dispositions"]) == 0
    assert client.post(path, headers=h, json=review_body(first_selector)).json() == first.json()
    client.close(); resources.cache_clear()


def test_interruption_after_ledger_write_recovers_without_world_pointer(tmp_path, monkeypatch):
    store, client, token, h, body, task, selected = scenario(tmp_path, monkeypatch)
    from backend.app.routes import shipping_intelligence as routes
    original_scope = routes.scoped_world
    def interrupted_scope():
        scoped = original_scope()
        scoped.save_world = lambda change: (_ for _ in ()).throw(RuntimeError("interrupted world pointer"))
        return scoped
    path = BASE + "/intelligence/review-tasks/" + task["id"] + "/dispositions"
    payload = review_body(body["operationalEvidence"])
    monkeypatch.setattr(routes, "scoped_world", interrupted_scope)
    with pytest.raises(RuntimeError, match="interrupted world pointer"):
        client.post(path, headers=h, json=payload)
    assert not store.read(token)["intelligenceReviewTasks"][task["id"]].get("dispositionIds")
    monkeypatch.setattr(routes, "scoped_world", original_scope)
    resources.cache_clear()
    selected.clear()  # A recorded review remains available after provider failure.
    projected = client.get(BASE + "/intelligence/review-tasks", headers=h).json()["tasks"][0]
    assert projected["status"] == "CONTEXT_REVIEWED" and len(projected["dispositions"]) == 1
    assert client.post(path, headers=h, json=payload).json() == projected["dispositions"][0]
    client.close(); resources.cache_clear()


def test_port_context_review_does_not_complete_an_original_news_verification_question(tmp_path, monkeypatch):
    store, client, token, h, body, context_task, selected = scenario(tmp_path, monkeypatch)
    source = {"id": "c" * 64, "category": "news", "title": "Synthetic reported announcement",
        "fact": "Synthetic report still requires independent authority verification",
        "source": "https://fixture.example/announcement", "responseSha256": "d" * 64,
        "availableAt": store.read(token)["epoch"], "status": "UNRESOLVED", "portCodes": ["INNSA"]}
    monkeypatch.setattr("backend.app.routes.shipping_intelligence._task_source", lambda *args, **kwargs: source)
    response = client.post(BASE + "/intelligence/review-tasks", headers=h,
        json={"vesselId": "PWD-001", "requestId": "synthetic-news-task", "signalId": source["id"]})
    assert response.status_code == 200, response.text
    news_task = response.json()
    reviewed = client.post(BASE + "/intelligence/review-tasks/" + news_task["id"] + "/dispositions",
        headers=h, json=review_body(body["operationalEvidence"]))
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["answersContextQuestion"] is False
    assert reviewed.json()["taskStatus"] == "PENDING_VERIFICATION"
    tasks = client.get(BASE + "/intelligence/review-tasks", headers=h).json()["tasks"]
    projected = next(row for row in tasks if row["id"] == news_task["id"])
    assert projected["status"] == "PENDING_VERIFICATION"
    assert projected["sourceClaimStatus"] == "UNRESOLVED" and projected["actualExecutionStatus"] == "NOT_OBSERVED"
    assert projected["source"] == news_task["source"]
    client.close(); resources.cache_clear()
