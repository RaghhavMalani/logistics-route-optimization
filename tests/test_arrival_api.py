from datetime import timedelta
from pathlib import Path
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.auth_store import AuthStore, get_auth_store
from backend.app.routes import arrivals, advisories
from src.portwatch_os.advisories.store import AdvisoryStore
from src.portwatch_os.clock import get_clock, world_now
from src.portwatch_os.intelligence.arrivals import ArrivalWorkflow, stamp
from src.portwatch_os.ledger.store import SqliteLedgerStore


@pytest.fixture(scope="module")
def auth():
    with tempfile.TemporaryDirectory() as tmp:
        store = AuthStore(Path(tmp)/"auth.db")
        for name, role, ports in (("port", "PORT_AUTHORITY", ("INNSA",)), ("other", "PORT_AUTHORITY", ("INMAA",)),
                                  ("company", "SHIPPING_COMPANY", ())):
            store.provision(f"{name}@qa.invalid", "qa-only-test-password", role=role, display_name=name,
                            ports=ports, organisation="QA Shipping" if name == "company" else "QA Authority")
        yield store


@pytest.fixture
def api(auth):
    ledger, advisory_store = SqliteLedgerStore(":memory:"), AdvisoryStore(":memory:")
    service = ArrivalWorkflow(ledger)
    app.dependency_overrides[arrivals.workflow] = lambda: service
    app.dependency_overrides[get_auth_store] = lambda: auth
    with patch("backend.app.auth_store.get_auth_store", return_value=auth), patch.dict("os.environ", {"PORTWATCH_IDENTITY_MODE": "verified", "PORTWATCH_FRESHNESS_SCHEDULER": "0", "AISSTREAM_API_KEY": ""}), \
         patch.object(arrivals, "get_advisory_store", return_value=advisory_store), \
         patch.object(advisories, "get_advisory_store", return_value=advisory_store), patch.object(advisories, "get_ledger", return_value=ledger):
        with TestClient(app) as client:
            headers = {name: {"Authorization": "Bearer "+auth.login(f"{name}@qa.invalid", "qa-only-test-password", name)["accessToken"]}
                       for name in ("port", "other", "company")}
            yield client, headers, ledger, service
    app.dependency_overrides.pop(arrivals.workflow, None)
    app.dependency_overrides.pop(get_auth_store, None)
    ledger.close()
    advisory_store.close()


def operation():
    return {"operationRef": "QA-API-ARRIVAL", "mmsi": "419000168", "vesselName": "QA vessel", "recipientOrganisation": "QA Shipping",
            "plannedArrivalAt": stamp(world_now()+timedelta(days=1)), "baselineWaitHours": 20, "baselineSource": "QA incumbent schedule"}


def test_identity_membership_replay_and_timestamp_validation(api):
    client, headers, ledger, service = api
    url = "/api/arrivals/operations"
    assert client.post(url, json=operation(), headers={"X-PortWatch-Role": "NATIONAL_ADMIN"}).status_code == 401
    assert client.post(url, json=operation(), headers={**headers["other"], "X-PortWatch-Role": "NATIONAL_ADMIN"}).status_code == 403
    assert client.get("/api/arrivals/workspace", headers=headers["company"]).status_code == 403
    assert client.post(url, json={**operation(), "plannedArrivalAt": "2026-10-08T12:00:00"}, headers=headers["port"]).status_code == 422
    assert client.post(url, json={**operation(), "baselineWaitHours": -1}, headers=headers["port"]).status_code == 422
    with get_clock().pin_replay(world_now()-timedelta(days=1)):
        assert client.post(url, json=operation(), headers=headers["port"]).status_code == 409


def test_native_advisory_response_does_not_resolve_actual_outcome(api):
    client, headers, ledger, service = api
    response = client.post("/api/arrivals/operations", json=operation(), headers=headers["port"])
    assert response.status_code == 200, response.text
    case = response.json()
    root = "/api/arrivals/operations/"+case["operationId"]
    action = {"actualAction": "Retained schedule", "actionState": "taken", "source": "QA bridge log",
              "occurredAt": stamp(world_now()), "availableAt": stamp(world_now())}
    assert client.post(root+"/action", json=action, headers=headers["port"]).status_code == 422
    approved = client.post(root+"/approve", json={"note": "Checked frozen evidence and missing inputs"}, headers=headers["port"])
    assert approved.status_code == 200, approved.text
    draft = client.post(root+"/advisory", headers=headers["port"])
    assert draft.status_code == 200, draft.text
    advisory_id = draft.json()["advisoryId"]
    assert client.get("/api/advisories/"+advisory_id, headers=headers["company"]).status_code == 404
    for target in ("under_review", "issued"):
        result = client.post(f"/api/advisories/{advisory_id}/transition", json={"target": target}, headers=headers["port"])
        assert result.status_code == 200, result.text
    assert client.post(f"/api/advisories/{advisory_id}/transition", json={"target": "accepted"}, headers=headers["company"]).status_code == 200
    assert ledger.get_decision(case["decisionId"]).status == "open"
    at = stamp(world_now())
    action.update(occurredAt=at, availableAt=at)
    assert client.post(root+"/action", json=action, headers=headers["port"]).status_code == 200
    resolved = client.post(root+"/outcome", json={"arrivedAt": at, "berthedAt": at, "availableAt": at,
        "source": "QA confirmed zero-wait port-call log", "kind": "port_call_log", "berthRef": "QA berth"}, headers=headers["port"])
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["outcome"]["waitHours"] == 0
    assert resolved.json()["errorHours"] is None  # No fabricated numeric claim without data.
    assert ledger.get_decision(case["decisionId"]).status == "resolved"
    assert client.post(root+"/outcome", json={"arrivedAt": at, "berthedAt": at, "availableAt": at,
        "source": "Attempted overwrite", "kind": "port_call_log", "berthRef": "QA berth"}, headers=headers["port"]).status_code == 409
    with get_clock().pin_replay(world_now()-timedelta(minutes=1)):
        replay = client.get("/api/arrivals/workspace", headers=headers["port"])
        assert replay.status_code == 200
        assert replay.json()["operations"] == []


def test_verified_csv_preview_atomic_commit_and_call_identity(api):
    import csv
    import io
    client, headers, ledger, service = api
    def csv_text(rows):
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue()
    assert client.post("/api/arrivals/collection", headers=headers["other"]).status_code == 403
    assert client.post("/api/arrivals/collection", headers=headers["port"]).status_code == 200
    row = {**operation(), "baselineRef": "QA-estimate-api", "baselineEstimatedAt": stamp(world_now()-timedelta(minutes=2)),
           "baselineAvailableAt": stamp(world_now()-timedelta(minutes=1))}
    data = {"recordType": "operations", "csvText": csv_text([row]), "commit": False}
    preview = client.post("/api/arrivals/import", json=data, headers=headers["port"])
    assert preview.status_code == 200 and preview.json()["status"] == "PREVIEW"
    assert service.cases() == []
    duplicate_batch = client.post("/api/arrivals/import", json={**data, "csvText": csv_text([row, row]), "commit": True}, headers=headers["port"])
    assert duplicate_batch.status_code == 422 and "rolled back" in duplicate_batch.text
    assert service.cases() == [] and not ledger.decisions()
    committed = client.post("/api/arrivals/import", json={**data, "commit": True}, headers=headers["port"])
    assert committed.status_code == 200 and len(service.cases()) == 1
    at = stamp(world_now())
    result = {"operationRef": row["operationRef"], "mmsi": "419000169", "arrivedAt": at, "berthedAt": at,
              "arrivalAvailableAt": at, "allFastAvailableAt": at, "availableAt": at, "source": "QA operator log",
              "sourceRef": "QA-log-api", "kind": "operator_confirmed", "berthRef": "QA-1"}
    rejected = client.post("/api/arrivals/import", json={"recordType": "outcomes", "csvText": csv_text([result]), "commit": True}, headers=headers["port"])
    assert rejected.status_code == 422 and "MMSI differs" in rejected.text
    assert service.cases()[0]["outcome"] is None
    result["mmsi"] = row["mmsi"]
    assert client.post("/api/arrivals/import", json={"recordType": "outcomes", "csvText": csv_text([result]), "commit": True}, headers=headers["port"]).status_code == 200
    state = client.get("/api/arrivals/workspace", headers=headers["port"]).json()
    assert state["collection"]["confirmedCount"] == 1 and state["collection"]["qualifyingCount"] == 0
    exported = client.get("/api/arrivals/dataset", headers=headers["port"])
    assert exported.status_code == 200 and len(exported.json()["operations"]) == 1
    assert exported.json()["operations"][0]["actualAction"] is None
    assert client.get("/api/arrivals/dataset", headers=headers["other"]).status_code == 403
    with get_clock().pin_replay(world_now()-timedelta(minutes=1)):
        assert client.post("/api/arrivals/import", json=data, headers=headers["port"]).status_code == 409
