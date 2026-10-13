"""Durable, visitor-scoped continuation; every provider is mocked."""
from datetime import datetime, timedelta
import hashlib
import pytest
from tests.test_demo_terminal import setup, resources
from tests.test_current_input_journey import forecast

BASE = "/api/demo/terminal"


def journey(tmp_path, monkeypatch):
    store, client = setup(tmp_path, monkeypatch)
    session = store.create("SHIPPING_COMPANY")
    token = session["accessToken"]
    headers = {"Authorization":"Bearer " + token}
    epoch = datetime.fromisoformat(store.read(token)["epoch"])
    data = forecast(epoch)
    monkeypatch.setattr("src.portwatch_os.decision.current_arrival.bundle", lambda port: data)
    r = client.post(BASE+"/decisions/problems",headers=headers,json={"domain":"vessel","vesselId":"PWD-001",
        "currentArrival":{"plannedArrival":(epoch+timedelta(hours=181)).isoformat(),"maxGustKn":15,"minVisibilityM":5000}})
    assert r.status_code == 200, r.text
    company = r.json()
    choice = next(o["optionId"] for o in company["options"] if not o["isBaseline"])
    return store, client, token, headers, company, choice, data


def step(client, path, headers, target, choice=None):
    r = client.post(path+"/transition",headers=headers,json={"target":target,"optionId":choice})
    assert r.status_code == 200, r.text
    resources.cache_clear()
    return r.json()


def test_recovery_at_every_boundary_and_idempotent_retries(tmp_path, monkeypatch):
    store, client, token, h, company, choice, data = journey(tmp_path,monkeypatch)
    cp = BASE+"/decisions/problems/"+company["decisionId"]
    step(client,cp,h,"REVIEWED")
    approved = step(client,cp,h,"APPROVED",choice)
    recovered = client.get(cp,headers=h).json()
    assert recovered["options"] == company["options"]
    assert recovered["workflowHistory"] == approved["workflowHistory"]
    assert recovered["humanChoice"] == choice
    store.switch(token,"PORT_AUTHORITY")
    assert len(client.get(BASE+"/decisions/current-proposals",headers=h).json()["proposals"]) == 1
    port = client.post(BASE+"/decisions/current-proposals/review",headers=h,json={"decisionId":company["decisionId"]}).json()
    pp = BASE+"/decisions/problems/"+port["decisionId"]
    step(client,pp,h,"REVIEWED"); step(client,pp,h,"APPROVED",choice)
    issued = client.post(pp+"/handoff",headers=h,json={})
    assert issued.status_code == 200, issued.text
    rows = issued.json()["advisories"]
    resources.cache_clear()
    assert client.post(pp+"/handoff",headers=h,json={}).json()["advisories"] == rows
    ap = BASE+"/advisories/"+rows[0]["advisoryId"]
    step(client,ap,h,"under_review"); step(client,ap,h,"issued")
    store.switch(token,"VESSEL_OPERATOR")
    step(client,ap,h,"acknowledged"); accepted = step(client,ap,h,"accepted")
    assert client.post(ap+"/transition",headers=h,json={"target":"accepted"}).json() == accepted
    store.switch(token,"PORT_AUTHORITY")
    world = store.read(token)
    resource = resources(str(store.path.parent),store.session(token)["demoId"],hashlib.sha256(world["epoch"].encode()).hexdigest()[:16])
    engine = resource.resources["decisions"] if "decisions" in resource.resources else None
    # Recreate the engine after acceptance cache eviction, then interrupt
    # between closing durable advisories and updating the decision/world.
    client.get(pp,headers=h)
    engine = resource.resources["decisions"]
    original_transition = engine.transition
    def interrupt(*args, **kwargs):
        if args[1] == "ISSUED": raise RuntimeError("simulated process interruption")
        return original_transition(*args,**kwargs)
    monkeypatch.setattr(engine,"transition",interrupt)
    with pytest.raises(RuntimeError,match="simulated process interruption"):
        client.post(pp+"/demo-outcome",headers=h,json={})
    resources.cache_clear()
    done = client.post(pp+"/demo-outcome",headers=h,json={})
    assert done.status_code == 200, done.text
    resources.cache_clear()
    assert client.post(pp+"/demo-outcome",headers=h,json={}).json() == done.json()
    final = client.get(pp,headers=h).json()
    assert final["evidence"]["advisories"] == [rows[0]["advisoryId"]]
    assert final["evidence"]["demoOutcome"] == done.json()["outcome"]
    other = store.create("PORT_AUTHORITY"); oh={"Authorization":"Bearer "+other["accessToken"]}
    assert client.get(pp,headers=oh).status_code == 404
    assert client.post(pp+"/handoff",headers=oh,json={}).status_code == 404
    assert client.get(ap,headers=oh).status_code == 404
    client.close()


def test_expiration_explicit_successor_preserves_frozen_approval(tmp_path,monkeypatch):
    store, client, token, h, company, choice, data = journey(tmp_path,monkeypatch)
    cp = BASE+"/decisions/problems/"+company["decisionId"]
    step(client,cp,h,"REVIEWED"); step(client,cp,h,"APPROVED",choice)
    approved = client.get(cp,headers=h).json()
    later = datetime.fromisoformat(data["sources"]["surface"]["availableAt"])+timedelta(hours=2)
    monkeypatch.setattr("src.portwatch_os.clock.wall_now",lambda:later)
    store.switch(token,"PORT_AUTHORITY")
    assert client.post(BASE+"/decisions/current-proposals/review",headers=h,json={"decisionId":company["decisionId"]}).status_code == 409
    store.switch(token,"SHIPPING_COMPANY")
    data["sources"]["surface"]["availableAt"] = later.isoformat()
    successor = client.post(cp+"/refresh",headers=h,json={})
    assert successor.status_code == 200, successor.text
    next_problem = successor.json()
    assert next_problem["decisionId"] != company["decisionId"] and next_problem["workflow"] == "COMPUTED"
    assert next_problem["evidence"]["predecessorDecisionId"] == company["decisionId"]
    resources.cache_clear()
    original = client.get(cp,headers=h).json()
    assert original["options"] == approved["options"] and original["humanChoice"] == choice
    assert original["workflowHistory"] == approved["workflowHistory"]
    assert client.post(cp+"/refresh",headers=h,json={}).json()["decisionId"] == next_problem["decisionId"]
    client.close()


def test_consumed_voyage_change_blocks_continuation(tmp_path,monkeypatch):
    store, client, token, h, company, choice, data = journey(tmp_path,monkeypatch)
    cp = BASE+"/decisions/problems/"+company["decisionId"]
    step(client,cp,h,"REVIEWED")
    store.update(token,lambda world: world["fleet"][0].update(etaHours=181))
    r = client.post(cp+"/transition",headers=h,json={"target":"APPROVED","optionId":choice})
    assert r.status_code == 409 and "ETA has changed" in r.text
    client.close()
