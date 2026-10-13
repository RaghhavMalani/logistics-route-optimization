"""Original-screen contracts, real decisions and negative isolation cases."""
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services.demo_store import DemoStore
from backend.app.services.demo_terminal import resources


def setup(tmp_path, monkeypatch):
    store = DemoStore(tmp_path / "demo" / "sessions.sqlite3")
    monkeypatch.setenv("PORTWATCH_IDENTITY_MODE", "verified")
    monkeypatch.setenv("PORTWATCH_AUTH_DB", str(tmp_path / "identity.sqlite3"))
    monkeypatch.setenv("PORTWATCH_FLEET_PROVIDER", str(tmp_path / "private-fleet.json"))
    (tmp_path / "private-fleet.json").write_text('{"name":"PRIVATE CARRIER"}')
    monkeypatch.setenv("AISSTREAM_API_KEY", "private-key-must-not-enter-demo")
    monkeypatch.setattr("backend.app.routes.demo.get_demo_store", lambda: store)
    monkeypatch.setattr("backend.app.routes.demo_terminal.get_demo_store", lambda: store)
    return store, TestClient(app)


def test_original_contracts_and_scope(tmp_path, monkeypatch):
    store, client = setup(tmp_path, monkeypatch)
    session = store.create("SHIPPING_COMPANY")
    headers = {"Authorization": "Bearer " + session["accessToken"], "X-PortWatch-Role": "NATIONAL_ADMIN"}
    base = "/api/demo/terminal"
    for path in ("/ports", "/ports/registry", "/weather", "/weather/intelligence", "/model/INNSA/forecast",
                 "/company/fleet", "/company/risk", "/company/routes", "/company/cargo?port_code=INNSA",
                 "/global-eye/events", "/world/cascades", "/world/state", "/world/clock", "/fabric/health",
                 "/world/ais/tracks", "/port-twin/INNSA", "/port-twin/INNSA/simulate", "/advisories",
                 "/weather/feedback?variable=wind_speed&portCode=INNSA&limit=100", "/learning/experiments", "/intelligence/context?portCode=INNSA"):
        response = client.get(base + path, headers=headers)
        assert response.status_code == 200, (path, response.text)
    fleet = client.get(base + "/company/fleet", headers=headers).json()
    assert len(fleet["vessels"]) == 3 and fleet["vessels"][0]["name"] == "PW Meridian"
    assert "PRIVATE" not in str(fleet)
    assert client.get(base + "/company/fleet?company_id=private", headers=headers).status_code == 404
    assert client.get(base + "/learning/policies", headers=headers).status_code == 403
    assert client.post(base + "/admin/freshness/port_forecast/refresh", headers=headers, json={}).status_code == 404
    assert client.get(base + "/intelligence/cameras", headers=headers).json()["cameras"] == []
    assert client.post(base + "/intelligence/cameras", headers=headers, json={}).status_code in (404,405)
    assert client.post(base + "/finance/assumptions", headers=headers, json={}).status_code in (404,405)
    assert client.get(base + "/agents/runs", headers=headers).json()["total"] == 0
    health=client.get(base+"/health",headers=headers).json()
    assert health["durableStores"]["scope"] == "visitor-owned demo"
    assert health["licenceMode"]["mode"] == "DEMO"
    assert client.get("/api/company/fleet", headers=headers).status_code == 401
    store.switch(session["accessToken"], "PORT_AUTHORITY")
    assert client.post(base + "/decisions/problems", headers=headers, json={
        "domain": "port", "portCode": "INNSA", "cameraPlanning": {
            "evidenceId": "private-observation", "berthId": "B1", "holdHours": 2}}).status_code == 401
    client.close()


def test_original_company_proposal_port_plan_and_advisory_chain(tmp_path,monkeypatch):
    store,client=setup(tmp_path,monkeypatch)
    session=store.create("SHIPPING_COMPANY"); credential=session["accessToken"]
    headers={"Authorization":"Bearer "+credential};base="/api/demo/terminal"
    world=store.read(credential)
    response=client.post(base+"/decisions/problems",headers=headers,json={"domain":"vessel","vesselId":"PWD-001","eventId":world["event"]["id"],"mode":"DEMO"})
    assert response.status_code==200,response.text
    p=response.json(); path=base+"/decisions/problems/"+p["decisionId"]
    assert client.post(path+"/transition",headers=headers,json={"target":"REVIEWED"}).status_code==200
    choice=p["recommendation"]["optionId"] if p.get("recommendation") else p["options"][0]["optionId"]
    approval=client.post(path+"/transition",headers=headers,json={"target":"APPROVED","optionId":choice,"acknowledgeMovedWorld":True})
    assert approval.status_code==200,approval.text
    proposal=store.read(credential)["terminalProposal"]
    assert proposal["decisionId"]==p["decisionId"] and proposal["vesselId"]=="PWD-001"
    fleet=client.get(base+"/fleet",headers=headers).json()
    assert fleet[0]["intendedArrivalDay"] == (world["fleet"][0]["etaHours"]+(proposal["etaShiftHours"] or 0))/24
    store.switch(credential,"PORT_AUTHORITY")
    problem=client.post(base+"/decisions/problems",headers=headers,json={"domain":"port","portCode":"INNSA","bunchArrivals":3,"mode":"DEMO"})
    assert problem.status_code==200,problem.text
    p=problem.json();path=base+"/decisions/problems/"+p["decisionId"]
    assert client.post(path+"/transition",headers=headers,json={"target":"REVIEWED"}).status_code==200
    assert client.post(path+"/transition",headers=headers,json={"target":"APPROVED","optionId":p["recommendation"]["optionId"],"acknowledgeMovedWorld":True}).status_code==200
    handoff=client.post(path+"/handoff",headers=headers,json={})
    assert handoff.status_code==200,handoff.text
    rows=handoff.json()["advisories"]
    advisory=next(a for a in rows if a["recipientVesselId"]=="PWD-001")
    ap=base+"/advisories/"+advisory["advisoryId"]
    for target in ("under_review","issued"):
        r=client.post(ap+"/transition",headers=headers,json={"target":target});assert r.status_code==200,r.text
    store.switch(credential,"SHIPPING_COMPANY")
    visible=client.get(base+"/advisories",headers=headers)
    assert visible.status_code==200 and any(a["advisoryId"]==advisory["advisoryId"] for a in visible.json()["advisories"])
    store.switch(credential,"VESSEL_OPERATOR")
    assert len(client.get(base+"/fleet",headers=headers).json())==1
    r=client.post(ap+"/transition",headers=headers,json={"target":"acknowledged"});assert r.status_code==200,r.text
    r=client.post(ap+"/transition",headers=headers,json={"target":"accepted"});assert r.status_code==200,r.text
    stranger=store.create("NATIONAL_ADMIN")
    assert client.get(ap,headers={"Authorization":"Bearer "+stranger["accessToken"]}).status_code in (403,404)
    store.switch(credential,"PORT_AUTHORITY")
    r=client.post(ap+"/transition",headers=headers,json={"target":"completed"});assert r.status_code==200,r.text
    client.close()


def test_original_decisions_are_visitor_owned_resettable_and_durable(tmp_path, monkeypatch):
    store, client = setup(tmp_path, monkeypatch)
    first, other = store.create("PORT_AUTHORITY"), store.create("NATIONAL_ADMIN")
    headers = {"Authorization": "Bearer " + first["accessToken"]}
    second = {"Authorization": "Bearer " + other["accessToken"]}
    base = "/api/demo/terminal"
    from src.portwatch_os.decision import engine
    from src.portwatch_os.ledger import store as ledger
    from src.portwatch_os.advisories import store as advisories
    # Sentinels make any accidental operational singleton access fail.
    monkeypatch.setattr(engine, "_ENGINE", object())
    monkeypatch.setattr(ledger, "_DEFAULT", object())
    monkeypatch.setattr(advisories, "_DEFAULT", object())
    problem = client.post(base + "/decisions/problems", headers=headers,
                          json={"domain": "port", "portCode": "INNSA", "bunchArrivals": 3})
    assert problem.status_code == 200, problem.text
    p = problem.json()
    decision_id = p["decisionId"]
    path = base + "/decisions/problems/" + decision_id
    assert client.get(path, headers=second).status_code == 404
    reviewed = client.post(path + "/transition", headers=headers, json={"target": "REVIEWED"})
    assert reviewed.status_code == 200, reviewed.text
    approved = client.post(path + "/transition", headers=headers,
        json={"target": "APPROVED", "optionId": p["recommendation"]["optionId"]})
    assert approved.status_code == 200, approved.text
    handoff = client.post(path + "/handoff", headers=headers, json={})
    assert handoff.status_code == 200, handoff.text
    assert handoff.json()["advisories"]
    assert client.get(base + "/advisories", headers=second).json()["advisories"] == []
    assert client.get(base + "/decisions/problems", headers=headers).json()["total"] == 1
    store.switch(first["accessToken"], "NATIONAL_ADMIN")
    # A store reload leaves the visitor's namespace identity stable.
    reloaded = DemoStore(store.path)
    assert reloaded.session(first["accessToken"])["demoId"] == first["demoId"]
    assert client.post("/api/demo/reset", headers=headers, json={}).status_code == 200
    assert client.get(base + "/decisions/problems", headers=headers).json()["total"] == 0
    assert client.get(base + "/advisories", headers=headers).json()["advisories"] == []
    assert client.get(path, headers=headers).status_code == 404
    client.close()
