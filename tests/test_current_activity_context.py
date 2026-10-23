"""Activity is frozen context, never an input or freshness dependency of the gate."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace

from src.portwatch_os.decision import current_arrival
from src.portwatch_os.decision.model import DecisionActor
from tests.test_current_input_journey import forecast
from tests.test_current_recovery import BASE, journey, step
from tests.test_demo_terminal import resources


def activity(**changes):
    return {
        "schemaVersion": 1, "projectionVersion": "test-retained-activity-v1",
        "operationalUse": "CONTEXT_ONLY", "calculationEffect": "NONE",
        "portCode": "INNSA", "provider": "IMF PortWatch",
        "sourceProductId": "imf-portwatch-daily", "sourceVersion": "daily-series-v1",
        "observationDate": "2026-10-17", "observedFrom": "2026-10-16",
        "observedThrough": "2026-10-17", "datePrecision": "DATE",
        "sourceReceiptId": "receipt-original", "originalRef": "public-original-selector",
        "originalHash": "a" * 64, "firstAvailableAt": "2026-10-18T09:35:00Z",
        "unknownReason": None, **changes,
    }


def option_calculations(problem):
    return [{key: row[key] for key in ("action", "params", "evaluation", "timeline", "constraints")}
            for row in problem["options"]]


def test_activity_context_changes_evidence_identity_without_changing_hourly_math(monkeypatch):
    at = datetime(2026, 10, 22, 9, tzinfo=timezone.utc)
    metadata = activity()
    monkeypatch.setattr(current_arrival, "bundle", lambda port: forecast(at))
    monkeypatch.setattr(current_arrival, "freeze_activity_context", lambda port, now=None: copy.deepcopy(metadata))
    from src.portwatch_os.sandbox import current_sandbox
    token = current_sandbox.set(None)
    try:
        vessel = SimpleNamespace(destination_port="INNSA", eta=(at + timedelta(hours=180)).isoformat(),
                                 vessel_id="fixture-hull", name="Fictional test hull")
        state = SimpleNamespace(state_id="fixture-world", summary=lambda: {"revision": {"mode": "LIVE"}})
        request = {"plannedArrival": (at + timedelta(hours=181)).isoformat(), "maxGustKn": 15, "minVisibilityM": 5000}
        actor = DecisionActor(role="SHIPPING_COMPANY")
        first = current_arrival.build_arrival_problem(vessel, request, actor, state, at).to_dict()
        metadata.update(observationDate=None, observedFrom=None, observedThrough=None,
                        datePrecision=None, sourceReceiptId=None, originalRef=None, originalHash=None,
                        firstAvailableAt=None, unknownReason="No retained activity observation for this physical port")
        second = current_arrival.build_arrival_problem(vessel, request, actor, state, at).to_dict()
    finally:
        current_sandbox.reset(token)
    a, b = (p["evidence"]["currentEnvironment"] for p in (first, second))
    assert a["evidenceVersion"] == "current-weather-approach-v2"
    assert "activityObservation" not in a
    assert a["activityContext"]["observedThrough"] == "2026-10-17"
    assert a["activityContext"]["datePrecision"] == "DATE"
    assert "T" not in a["activityContext"]["observedThrough"]
    assert b["activityContext"]["observationDate"] is None and b["activityContext"]["unknownReason"]
    assert a["evidenceId"] != b["evidenceId"] and first["decisionId"] != second["decisionId"]
    assert option_calculations(first) == option_calculations(second)
    assert a["consumedForecasts"] == b["consumedForecasts"]
    assert a["assumptions"] == b["assumptions"]
    assert [o["evaluation"]["objectives"]["port_wait"]["value"] for o in first["options"]] == [2, 0]
    assert [o["evaluation"]["objectives"]["eta"]["value"] for o in first["options"]] == [3, 3]
    assert [o["evaluation"]["derived"]["arrivalShiftHours"] for o in first["options"]] == [1, 3]
    assert [o["params"]["holdHours"] for o in first["options"]] == [0, 2]
    assert all(o["evaluation"]["objectives"]["fuel"]["value"] is None for o in first["options"])


def test_metadata_refresh_does_not_recheck_or_rewrite_approved_context(tmp_path, monkeypatch):
    original = activity()
    monkeypatch.setattr(current_arrival, "freeze_activity_context", lambda port, now=None: copy.deepcopy(original))
    store, client, token, headers, company, choice, _ = journey(tmp_path, monkeypatch)
    cp = BASE + "/decisions/problems/" + company["decisionId"]
    step(client, cp, headers, "REVIEWED")
    approved = step(client, cp, headers, "APPROVED", choice)
    frozen_bytes = json.dumps(approved["evidence"]["currentEnvironment"], sort_keys=True).encode()
    # A collector can change metadata independently. Continuing a weather gate
    # must not fetch, compare or substitute the newer activity snapshot.
    monkeypatch.setattr(current_arrival, "freeze_activity_context", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("Frozen activity must not be fetched during continuation")))
    resources.cache_clear()
    store.switch(token, "PORT_AUTHORITY")
    response = client.post(BASE + "/decisions/current-proposals/review", headers=headers,
                           json={"decisionId": company["decisionId"]})
    assert response.status_code == 200, response.text
    port = response.json()
    assert json.dumps(port["evidence"]["currentEnvironment"], sort_keys=True).encode() == frozen_bytes
    pp = BASE + "/decisions/problems/" + port["decisionId"]
    step(client, pp, headers, "REVIEWED")
    step(client, pp, headers, "APPROVED", choice)
    response = client.post(pp + "/handoff", headers=headers, json={})
    assert response.status_code == 200, response.text
    advisory = response.json()["advisories"][0]
    assert json.dumps(advisory["evidence"]["currentEnvironment"], sort_keys=True).encode() == frozen_bytes
    resources.cache_clear()
    store.switch(token, "SHIPPING_COMPANY")
    response = client.get(cp, headers=headers)
    assert response.status_code == 200, response.text
    recovered = response.json()
    assert recovered["workflowHistory"] == approved["workflowHistory"]
    assert recovered["humanChoice"] == choice
    assert json.dumps(recovered["evidence"]["currentEnvironment"], sort_keys=True).encode() == frozen_bytes
    client.close()


def test_legacy_stored_activity_wording_and_problem_bytes_survive_recovery(tmp_path, monkeypatch):
    builder = current_arrival.build_arrival_problem
    legacy_wording = "2026-10-02; not refreshed or used as current approach weather"

    def legacy_fixture(*args, **kwargs):
        # Seed an earlier frozen shape at initial creation, before it is stored.
        # The application never migrates or rewrites an existing evidence body.
        problem = builder(*args, **kwargs)
        env = problem.evidence["currentEnvironment"]
        env.pop("activityContext"); env.pop("evidenceVersion")
        env["activityObservation"] = legacy_wording
        env.pop("evidenceId")
        env["evidenceId"] = hashlib.sha256(json.dumps(env, sort_keys=True).encode()).hexdigest()
        return problem

    monkeypatch.setattr(current_arrival, "freeze_activity_context", lambda port, now=None: activity())
    monkeypatch.setattr(current_arrival, "build_arrival_problem", legacy_fixture)
    store, client, token, headers, company, choice, _ = journey(tmp_path, monkeypatch)
    cp = BASE + "/decisions/problems/" + company["decisionId"]
    epoch = store.read(token)["epoch"]
    resource = resources(str(store.path.parent), store.session(token)["demoId"],
                         hashlib.sha256(epoch.encode()).hexdigest()[:16])
    ledger = resource.resources["decisions"].ledger
    before = ledger._conn.execute("SELECT problem FROM decision_problems WHERE problem_id=?",
                                  (company["decisionId"],)).fetchone()[0]
    step(client, cp, headers, "REVIEWED")
    step(client, cp, headers, "APPROVED", choice)
    monkeypatch.setattr(current_arrival, "freeze_activity_context", lambda port, now=None: activity(
        observationDate="2026-10-21", sourceReceiptId="new-receipt"))
    resources.cache_clear()
    recovered = client.get(cp, headers=headers).json()
    assert recovered["evidence"]["currentEnvironment"] == company["evidence"]["currentEnvironment"]
    assert recovered["evidence"]["currentEnvironment"]["activityObservation"] == legacy_wording
    resource = resources(str(store.path.parent), store.session(token)["demoId"],
                         hashlib.sha256(epoch.encode()).hexdigest()[:16])
    after = resource.resources["decisions"].ledger._conn.execute(
        "SELECT problem FROM decision_problems WHERE problem_id=?", (company["decisionId"],)).fetchone()[0]
    assert after == before
    client.close()
