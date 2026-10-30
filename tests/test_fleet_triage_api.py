"""Real visitor boundary and durable read-only fleet worklist contracts."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from tests.test_demo_terminal import setup, resources
from tests.test_passage_cargo_workflow import cargo_journey
from tests.test_current_recovery import step

PATH = "/api/demo/terminal/company/decision-triage"


def get_rows(response):
    assert response.status_code == 200, response.text
    return response.json()


def hashes(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file() and not str(path).endswith(("-shm", "-wal"))}


def test_empty_owned_fleet_is_complete_missing_basis_without_creating_domain_stores(tmp_path, monkeypatch):
    store, client = setup(tmp_path, monkeypatch)
    session = store.create("SHIPPING_COMPANY")
    headers = {"Authorization": "Bearer " + session["accessToken"]}
    original = copy.deepcopy(store.read(session["accessToken"]))
    monkeypatch.setenv("PORTWATCH_CURRENT_ENVIRONMENT_DIR", str(tmp_path / "absent-public"))
    monkeypatch.setenv("PORTWATCH_PUBLIC_FEEDBACK_DB", str(tmp_path / "absent-feedback.sqlite3"))
    def forbidden(*args, **kwargs):
        raise AssertionError("Triage must not create a call, engine, ledger, advisory store or provider request")
    monkeypatch.setattr("src.portwatch_os.decision.episodes.ensure_episode", forbidden)
    monkeypatch.setattr("src.portwatch_os.decision.engine.get_engine", forbidden)
    monkeypatch.setattr("src.portwatch_os.ledger.store.get_ledger", forbidden)
    monkeypatch.setattr("src.portwatch_os.advisories.store.get_advisory_store", forbidden)
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    before = hashes(tmp_path)
    first = get_rows(client.get(PATH, headers=headers))
    second = get_rows(client.get(PATH, headers=headers))
    assert first["coverage"]["ownedVoyages"] == len(original["fleet"]) == 3
    assert first["coverage"]["currentCalls"] == 0
    assert len(first["rows"]) == 3 and sum(first["counts"].values()) == 3
    assert all(r["currentPlan"]["basis"] == "MISSING" for r in first["rows"])
    assert all(r["primaryCategory"] == "INCOMPLETE_ASSESSMENT" for r in first["rows"])
    assert first["coverage"] == second["coverage"]
    assert store.read(session["accessToken"]) == original
    assert hashes(tmp_path) == before
    client.close()


@pytest.mark.parametrize("role", ["PORT_AUTHORITY", "VESSEL_OPERATOR", "NATIONAL_ADMIN"])
def test_worklist_refuses_non_company_role_and_scope_injection(tmp_path, monkeypatch, role):
    store, client = setup(tmp_path, monkeypatch)
    session = store.create(role)
    headers = {"Authorization": "Bearer " + session["accessToken"], "X-PortWatch-Role": "SHIPPING_COMPANY"}
    assert client.get(PATH, headers=headers).status_code == 403
    store.switch(session["accessToken"], "SHIPPING_COMPANY")
    for query in ("companyId=foreign", "vesselId=PWD-001", "decisionId=foreign", "callId=foreign", "asOf=2020-01-01"):
        assert client.get(PATH + "?" + query, headers=headers).status_code == 400
    assert client.get(PATH).status_code == 401
    client.close()


def test_projection_recovers_complete_durable_dataset_and_never_reranks(tmp_path, monkeypatch):
    store, client, token, headers, company, _body, _data = cargo_journey(tmp_path, monkeypatch, same_gate=True)
    monkeypatch.setenv("PORTWATCH_CURRENT_ENVIRONMENT_DIR", str(tmp_path / "public"))
    monkeypatch.setenv("PORTWATCH_PUBLIC_FEEDBACK_DB", str(tmp_path / "feedback.sqlite3"))
    world = store.read(token)
    session = store.session(token)
    generation = hashlib.sha256(world["epoch"].encode()).hexdigest()[:16]
    root = store.path.parent / "terminal" / session["demoId"] / generation
    ledger = root / "ledger.sqlite3"
    # Add 25 real durable representations with incomplete legacy call identity.
    # They are all inspected, never mistaken for today's active plan.
    with sqlite3.connect(ledger) as db:
        for n in range(25):
            legacy = copy.deepcopy(company)
            legacy["decisionId"] = f"legacy-fixture-{n}"
            legacy["evidence"]["currentEnvironment"].pop("operationalEpisode")
            db.execute("INSERT INTO decision_problems SELECT ?,domain,subject,actor,issued_at,world_state_id,world_revision,at,?,recommended_option,baseline_option,options_evaluated,options_rejected,critic_verdict,workflow,human_choice,actual_action,status,observed_outcome,observed_at,notes FROM decision_problems WHERE problem_id=?",
                (legacy["decisionId"], json.dumps(legacy), company["decisionId"]))
    resources.cache_clear()
    def forbidden(*args, **kwargs):
        raise AssertionError("No reranking, rehydration writer or provider access on a worklist GET")
    monkeypatch.setattr("src.portwatch_os.decision.engine.get_engine", forbidden)
    monkeypatch.setattr("src.portwatch_os.decision.engine.DecisionEngine.finish", forbidden)
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    before = hashes(root)
    report = get_rows(client.get(PATH, headers=headers))
    assert report["coverage"]["retainedComparisons"] == 26
    assert report["coverage"]["legacyComparisons"] == 25
    row = next(r for r in report["rows"] if r["vessel"]["id"] == "PWD-001")
    assert row["currentPlan"]["decisionId"] == company["decisionId"]
    assert row["currentPlan"]["optionId"] == company["baselineOptionId"]
    assert row["freshness"]["status"] == "UNKNOWN"  # No invented original for synthetic a*64 digest.
    assert "MISSING_REQUIRED_ORIGINAL" in {r["code"] for r in row["reasons"]}
    assert hashes(root) == before
    assert store.read(token) == world
    other = store.create("SHIPPING_COMPANY")
    outsiders = {"Authorization": "Bearer " + other["accessToken"]}
    empty = get_rows(client.get(PATH, headers=outsiders))
    assert empty["coverage"]["retainedComparisons"] == 0
    assert company["decisionId"] not in json.dumps(empty)
    assert client.get("/api/demo/terminal/decisions/problems/"+company["decisionId"], headers=outsiders).status_code == 404
    client.close()


def test_projection_follows_actual_cross_role_links_after_cache_eviction(tmp_path, monkeypatch):
    store, client, token, headers, company, _body, _data = cargo_journey(tmp_path, monkeypatch, same_gate=True)
    monkeypatch.setenv("PORTWATCH_CURRENT_ENVIRONMENT_DIR", str(tmp_path / "public"))
    cp = "/api/demo/terminal/decisions/problems/" + company["decisionId"]
    choice = company["options"][1]["optionId"]
    step(client, cp, headers, "REVIEWED"); step(client, cp, headers, "APPROVED", choice)
    row = next(r for r in get_rows(client.get(PATH, headers=headers))["rows"] if r["vessel"]["id"] == "PWD-001")
    assert row["currentPlan"]["optionId"] == choice and row["workflow"]["nextRole"] == "PORT_AUTHORITY"
    store.switch(token, "PORT_AUTHORITY")
    port = client.post("/api/demo/terminal/decisions/current-proposals/review", headers=headers,
        json={"decisionId": company["decisionId"]}).json()
    pp = "/api/demo/terminal/decisions/problems/" + port["decisionId"]
    step(client, pp, headers, "REVIEWED"); step(client, pp, headers, "APPROVED", choice)
    handoff = client.post(pp+"/handoff", headers=headers, json={})
    assert handoff.status_code == 200, handoff.text
    advisory = handoff.json()["advisories"][0]
    ap = "/api/demo/terminal/advisories/" + advisory["advisoryId"]
    step(client, ap, headers, "under_review"); step(client, ap, headers, "issued")
    store.switch(token, "SHIPPING_COMPANY"); resources.cache_clear()
    report = get_rows(client.get(PATH, headers=headers))
    row = next(r for r in report["rows"] if r["vessel"]["id"] == "PWD-001")
    assert report["coverage"]["ownedVoyages"] == len(report["rows"]) == 3
    assert row["currentPlan"]["decisionId"] == company["decisionId"]
    assert row["workflow"]["portDecisionId"] == port["decisionId"]
    assert row["workflow"]["nextRole"] == "VESSEL_OPERATOR"
    store.switch(token, "VESSEL_OPERATOR")
    step(client, ap, headers, "acknowledged"); step(client, ap, headers, "accepted")
    store.switch(token, "PORT_AUTHORITY")
    done = client.post(pp+"/demo-outcome", headers=headers, json={})
    assert done.status_code == 200, done.text
    store.switch(token, "SHIPPING_COMPANY"); resources.cache_clear()
    completed = get_rows(client.get(PATH, headers=headers))
    row = next(r for r in completed["rows"] if r["vessel"]["id"] == "PWD-001")
    assert row["primaryCategory"] == "MONITORED"
    assert row["workflow"]["stage"] == "SIMULATED_OUTCOME_COMPLETED" and row["workflow"]["nextRole"] is None
    assert row["freshness"]["status"] == "NOT_REQUIRED_COMPLETED"
    assert store.read(token).get("cargoBookings") is None
    client.close()


def test_corrupt_store_is_an_explicit_failure_without_repair_or_empty_clear_fleet(tmp_path, monkeypatch):
    store, client = setup(tmp_path, monkeypatch)
    session = store.create("SHIPPING_COMPANY")
    token = session["accessToken"]
    world = store.read(token)
    generation = hashlib.sha256(world["epoch"].encode()).hexdigest()[:16]
    root = store.path.parent / "terminal" / session["demoId"] / generation
    root.mkdir(parents=True)
    ledger = root / "ledger.sqlite3"
    ledger.write_bytes(b"not a database; must not be reset")
    result = client.get(PATH, headers={"Authorization": "Bearer " + token})
    assert result.status_code == 503
    assert str(root) not in result.text and "rows" not in result.text
    assert ledger.read_bytes() == b"not a database; must not be reset"
    client.close()


def test_snapshot_concurrency_retry_is_bounded_and_reports_updating(tmp_path):
    from types import SimpleNamespace
    from backend.app.identity import Identity
    from backend.app.services.fleet_triage import retained_snapshot
    world = {"epoch": "2026-10-29T00:00:00+00:00", "organisation": "Owned", "fleet": []}
    scoped = SimpleNamespace(root=tmp_path, world=world)
    identity = Identity(role="SHIPPING_COMPANY", actor="company", organisation="Owned")
    class Changing:
        reads = 0
        def read(self, _credential):
            self.reads += 1
            return {**world, "comparisonRevision": self.reads}
    store = Changing()
    result, consistent = retained_snapshot(scoped, store, "test-only", identity)
    assert not consistent and store.reads == 3
    assert result["world"]["comparisonRevision"] == 3
    assert not list(tmp_path.iterdir())


def test_malformed_optional_source_lead_does_not_remove_owned_fleet(tmp_path, monkeypatch):
    store, client = setup(tmp_path, monkeypatch)
    session = store.create("SHIPPING_COMPANY")
    root = tmp_path / "sources"
    path = root / "operational_notices/navcen-catalogue-latest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"notices": [None, {"title": ["malformed optional title"], "windows": None}]}))
    monkeypatch.setenv("PORTWATCH_CURRENT_ENVIRONMENT_DIR", str(root))
    before = path.read_bytes()
    report = get_rows(client.get(PATH, headers={"Authorization": "Bearer " + session["accessToken"]}))
    assert len(report["rows"]) == 3 and report["sourceLeadCoverage"]["status"] == "MALFORMED"
    assert report["sourceLeads"] == [] and path.read_bytes() == before
    client.close()


@pytest.mark.parametrize("broken", ["actor", "continuation"])
def test_malformed_retained_optional_state_is_reported_per_record(tmp_path, monkeypatch, broken):
    store, client, token, headers, company, _body, _data = cargo_journey(tmp_path, monkeypatch, same_gate=True)
    monkeypatch.setenv("PORTWATCH_CURRENT_ENVIRONMENT_DIR", str(tmp_path / "public"))
    world, session = store.read(token), store.session(token)
    root = store.path.parent / "terminal" / session["demoId"] / hashlib.sha256(world["epoch"].encode()).hexdigest()[:16]
    bad_body = copy.deepcopy(company)
    bad_body["actor"]["organisation"] = {"unsupported": "optional malformed value"}
    with sqlite3.connect(root / "ledger.sqlite3") as db:
        db.execute("UPDATE decision_continuations SET state=? WHERE problem_id=?",
            (json.dumps(bad_body) if broken == "actor" else "{broken-json", company["decisionId"]))
    report = get_rows(client.get(PATH, headers=headers))
    assert len(report["rows"]) == 3 and report["coverage"]["malformedRetainedRecords"] == 1
    target = next(r for r in report["rows"] if r["vessel"]["id"] == "PWD-001")
    assert target["primaryCategory"] == "INCOMPLETE_ASSESSMENT"
    if broken == "continuation":
        assert "MALFORMED_RETAINED_CONTINUATION" in {reason["code"] for reason in target["reasons"]}
    client.close()
