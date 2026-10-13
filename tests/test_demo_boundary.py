"""Visitor isolation and the complete cross-role chain using real engines."""
from datetime import timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services.demo_store import DemoStore, utc_now
from src.portwatch_os.clock import get_clock

def setup_demo(tmp_path, monkeypatch):
    store = DemoStore(tmp_path/"demo.sqlite3")
    monkeypatch.setenv("PORTWATCH_IDENTITY_MODE", "verified")
    monkeypatch.setenv("PORTWATCH_AUTH_DB", str(tmp_path/"operational-identity-test.sqlite3"))
    monkeypatch.setattr("backend.app.routes.demo.get_demo_store", lambda:store)
    monkeypatch.setattr("backend.app.routes.demo.public_workspace.workspace", lambda:{"ports":[], "events":[], "weather":[], "cameras":[]})
    return store, TestClient(app)


def test_cross_role_chain_is_durable_and_visitor_owned(tmp_path, monkeypatch):
    store, client = setup_demo(tmp_path, monkeypatch)
    original_clock = get_clock().state
    first = client.post("/api/demo/session",json={"role":"SHIPPING_COMPANY"}).json()
    second = client.post("/api/demo/session",json={"role":"NATIONAL_ADMIN"}).json()
    headers={"Authorization":"Bearer "+first["accessToken"], "X-PortWatch-Role":"NATIONAL_ADMIN"}
    other={"Authorization":"Bearer "+second["accessToken"]}
    assert client.get("/api/demo/session",headers=headers).json()["user"]["role"] == "SHIPPING_COMPANY"
    assert client.post("/api/demo/port-scenario",headers=headers,json={}).status_code == 403
    with patch("src.portwatch_os.ledger.store.get_ledger", side_effect=AssertionError("demo must not open production ledger")):
        compared=client.post("/api/demo/scenario",headers=headers,json={"vesselId":"PWD-001"})
        assert compared.status_code == 200, compared.text
        comparison=compared.json()
        assert len(comparison["result"]["options"]) >= 5
        option=next(o for o in comparison["result"]["options"] if o["feasible"])
        proposed=client.post("/api/demo/proposal",headers=headers,json={"comparisonId":comparison["id"], "optionId":option["optionId"]})
        assert proposed.status_code == 200, proposed.text
        workspace = client.get("/api/demo/workspace",headers=headers).json()
        company_call = next(c for c in workspace["twin"]["calls"] if c["vessel_id"] == "PWD-001")
        assert company_call["effectiveEta"] == 180 + proposed.json()["etaShiftHours"]
        assert client.get("/api/demo/workspace",headers=other).json()["world"]["proposal"] is None
        assert client.post("/api/demo/role",headers=headers,json={"role":"PORT_AUTHORITY"}).status_code == 200
        planning=client.post("/api/demo/port-scenario",headers=headers,json={"weatherImpact":.18})
        assert planning.status_code == 200, planning.text
        assert len(planning.json()["options"]) == 2
        assert planning.json()["proposalInput"] == proposed.json()
        assert all(not p["violations"] for p in planning.json()["options"])
        issued=client.post("/api/demo/advisories",headers=headers,json={"policy":"Constrained lookahead"})
        assert issued.status_code == 200, issued.text
        assert issued.json()["portPlan"]["policy"] == "Constrained lookahead"
        assert issued.json()["portPlan"]["inputs"]["weatherImpact"] == .18
        advisory=issued.json()["id"]
        assert client.post(f"/api/demo/advisories/{advisory}/ack",headers=headers,json={}).status_code == 403
        assert client.post(f"/api/demo/advisories/{advisory}/ack",headers=other,json={}).status_code == 404
        client.post("/api/demo/role",headers=headers,json={"role":"VESSEL_OPERATOR"})
        assert client.post("/api/demo/selection",headers=headers,json={"vesselId":"PWD-002"}).status_code == 403
        assert client.post(f"/api/demo/advisories/{advisory}/ack",headers=headers,json={}).status_code == 200
        client.post("/api/demo/role",headers=headers,json={"role":"PORT_AUTHORITY"})
        resolved=client.post(f"/api/demo/advisories/{advisory}/outcome",headers=headers,json={"reportedWaitingHours":3.4})
        assert resolved.status_code == 200 and resolved.json()["state"] == "RESOLVED"
        # Reload the durable store as after a backend restart; role and story survive.
        reloaded=DemoStore(store.path)
        assert reloaded.read(first["accessToken"])["advisories"][0]["outcome"]["reportedWaitingHours"] == 3.4
        assert reloaded.session(first["accessToken"])["user"]["role"] == "PORT_AUTHORITY"
    assert get_clock().state == original_clock
    client.close()


def test_demo_credentials_never_authenticate_operations_and_reset_is_local(tmp_path, monkeypatch):
    store, client = setup_demo(tmp_path, monkeypatch)
    session=client.post("/api/demo/session",json={"role":"NATIONAL_ADMIN"}).json()
    other=store.create("SHIPPING_COMPANY")
    token=session["accessToken"]
    headers={"Authorization":"Bearer "+token,"X-PortWatch-Role":"NATIONAL_ADMIN"}
    for path in ("/api/intelligence/cameras","/api/auth/session","/api/admin/state"):
        assert client.get(path,headers=headers).status_code == 401
    for path in ("/api/public-arrivals/refresh?portCode=INMAA","/api/world/clock","/api/decisions/approve"):
        assert client.post(path,headers=headers,json={}).status_code == 401
    assert client.get("/api/demo/workspace",headers={"X-PortWatch-Role":"NATIONAL_ADMIN"}).status_code == 401
    assert client.get("/api/demo/workspace",headers={"Authorization":"Bearer production-token"}).status_code == 401
    for payload in ({"vesselId":"PRIVATE"},{"vesselId":"PWD-001","speedKn":"NaN"},{"vesselId":"PWD-001","waveM":100}):
        assert client.post("/api/demo/scenario",headers=headers,json=payload).status_code == 422
    store.update(other["accessToken"],lambda w:w.update(selectedVessel="PWD-002"))
    assert client.post("/api/demo/reset",headers=headers,json={}).status_code == 200
    assert store.read(other["accessToken"])["selectedVessel"] == "PWD-002"
    with store.connect() as db:
        db.execute("UPDATE sessions SET expires=? WHERE token_hash=?",((utc_now()-timedelta(seconds=1)).isoformat(),store.digest(token)))
    assert client.get("/api/demo/session",headers=headers).status_code == 401
    next_session=store.create("NATIONAL_ADMIN")
    h={"Authorization":"Bearer "+next_session["accessToken"]}
    assert client.post("/api/demo/logout",headers=h,json={}).status_code == 200
    assert client.get("/api/demo/session",headers=h).status_code == 401
    stored_text=store.path.read_bytes()
    assert token.encode() not in stored_text
    client.close()


def test_changed_proposal_requires_new_review_and_bridge_assignment_is_enforced(tmp_path, monkeypatch):
    store, client = setup_demo(tmp_path, monkeypatch)
    session = store.create("SHIPPING_COMPANY")
    headers = {"Authorization": "Bearer " + session["accessToken"]}
    comparison = client.post("/api/demo/scenario", headers=headers,
        json={"vesselId": "PWD-002", "hoursToRisk": -8}).json()
    choices = [o for o in comparison["result"]["options"] if o["feasible"]]
    assert len(choices) >= 2
    def propose(choice):
        return client.post("/api/demo/proposal", headers=headers, json={
            "comparisonId": comparison["id"], "optionId": choice["optionId"]})
    assert propose(choices[0]).status_code == 200
    store.switch(session["accessToken"], "PORT_AUTHORITY")
    assert client.post("/api/demo/port-scenario", headers=headers, json={}).status_code == 200
    store.switch(session["accessToken"], "SHIPPING_COMPANY")
    assert propose(choices[1]).status_code == 409  # Another destination is not a JNPA arrival.
    comparison = client.post("/api/demo/scenario", headers=headers,
        json={"vesselId": "PWD-002", "hoursToRisk": 8, "closureHours": 120}).json()
    assert propose(comparison["result"]["options"][0]).status_code == 200
    store.switch(session["accessToken"], "PORT_AUTHORITY")
    assert client.post("/api/demo/advisories", headers=headers, json={}).status_code == 409
    assert client.post("/api/demo/port-scenario", headers=headers, json={}).status_code == 200
    advisory = client.post("/api/demo/advisories", headers=headers, json={}).json()
    store.switch(session["accessToken"], "VESSEL_OPERATOR")
    assert store.read(session["accessToken"])["selectedVessel"] == "PWD-001"
    assert client.post(f"/api/demo/advisories/{advisory['id']}/ack", headers=headers, json={}).status_code == 403
    assert client.post("/api/demo/scenario", headers=headers, json={"vesselId":"PWD-002"}).status_code == 403
    client.close()
