from datetime import datetime, timedelta, timezone
import copy
from unittest.mock import Mock
import pytest
import requests
from tests.test_demo_terminal import setup
from src.portwatch_os.intelligence import current_environment as environment


def forecast(at):
    return {"portCode":"INNSA","sources":{
        "surface":{"status":"CURRENT","source":"https://api.open-meteo.com/v1/forecast",
                   "snapshotId":"forecast-snapshot","responseSha256":"response-hash", "issuedAt":None,"availableAt":at.isoformat()},
        "hazards":{"snapshotId":"hazard-snapshot"}},
        "hourly":[{"validAt":(at+timedelta(hours=181+i)).isoformat(),"wind_gusts_10m":gust,
                   "visibility":10000.,"wave_height":.8} for i,gust in enumerate((18.,19.,10.,9.,8.))]}


def test_current_signal_frozen_through_original_demo_workflow(tmp_path, monkeypatch):
    store, client = setup(tmp_path,monkeypatch)
    session = store.create("SHIPPING_COMPANY"); credential = session["accessToken"]
    header = {"Authorization":"Bearer "+credential}; base = "/api/demo/terminal"
    epoch = datetime.fromisoformat(store.read(credential)["epoch"])
    monkeypatch.setattr("src.portwatch_os.decision.current_arrival.bundle", lambda port: forecast(epoch))
    planned = (epoch+timedelta(hours=181)).isoformat()
    result = client.post(base+"/decisions/problems",headers=header,json={"domain":"vessel","vesselId":"PWD-001",
        "currentArrival":{"plannedArrival":planned,"maxGustKn":15,"minVisibilityM":5000}})
    assert result.status_code == 200,result.text
    company = result.json(); evidence = company["evidence"]["currentEnvironment"]
    assert evidence["forecastGateWaitHours"] == 2 and evidence["noWeatherGateWaitHours"] == 0
    window = next(o for o in company["options"] if not o["isBaseline"])
    assert window["status"] == "FEASIBLE",window
    assert window["evaluation"]["objectives"]["port_wait"]["value"] == 0
    cp = base+"/decisions/problems/"+company["decisionId"]
    for target in ("REVIEWED","APPROVED"):
        r=client.post(cp+"/transition",headers=header,json={"target":target,"optionId":window["optionId"]})
        assert r.status_code == 200,r.text
    proposal = store.read(credential)["terminalProposal"]
    assert proposal["environmentEvidenceId"] == evidence["evidenceId"] and proposal["etaShiftHours"] == 3
    assert client.post(cp+"/outcome",headers=header,json={"observed":{"eta":1},"actualAction":"DELAY_ARRIVAL"}).status_code == 409
    from backend.app.services.demo_terminal import company_for
    assert company_for(store.read(credential)).vessels[0].eta == (epoch+timedelta(hours=180)).isoformat()
    store.switch(credential,"PORT_AUTHORITY")
    assert client.get(base+"/decisions/current-proposals",headers=header).json()["proposals"][0]["evidence"] == evidence
    review = client.post(base+"/decisions/current-proposals/review",headers=header,json={"decisionId":company["decisionId"]})
    assert review.status_code == 200,review.text
    port = review.json(); pp=base+"/decisions/problems/"+port["decisionId"]
    assert port["evidence"]["currentEnvironment"] == evidence
    for target in ("REVIEWED","APPROVED"):
        r=client.post(pp+"/transition",headers=header,json={"target":target,"optionId":window["optionId"]})
        assert r.status_code == 200,r.text
    assert store.read(credential)["terminalProposal"]["decisionId"] == company["decisionId"]
    handoff = client.post(pp+"/handoff",headers=header,json={})
    assert handoff.status_code == 200,handoff.text
    advisory=handoff.json()["advisories"][0]; ap=base+"/advisories/"+advisory["advisoryId"]
    assert advisory["evidence"]["currentEnvironment"] == evidence
    assert advisory["recommendation"]["recommendedArrival"] == window["evaluation"]["derived"]["arrivalAt"]
    assert client.post(pp+"/demo-outcome",headers=header,json={}).status_code == 409
    for target in ("under_review","issued"):
        r=client.post(ap+"/transition",headers=header,json={"target":target}); assert r.status_code==200,r.text
    store.switch(credential,"VESSEL_OPERATOR")
    vessel = client.get(base+"/advisories",headers=header).json()["advisories"][0]
    assert vessel["evidence"]["currentEnvironment"] == evidence
    for target in ("acknowledged","accepted"):
        r=client.post(ap+"/transition",headers=header,json={"target":target}); assert r.status_code==200,r.text
    assert client.post(pp+"/demo-outcome",headers=header,json={}).status_code == 403
    store.switch(credential,"PORT_AUTHORITY")
    r=client.post(pp+"/demo-outcome",headers=header,json={}); assert r.status_code == 200,r.text
    outcome=r.json()["outcome"]
    assert outcome["kind"] == "SIMULATED_DEMO_OUTCOME" and outcome["baselineAssumedWaitHours"] == 2
    assert outcome["selectedAssumedWaitHours"] == 0 and r.json()["advisories"][0]["state"] == "completed"
    assert company_for(store.read(credential)).vessels[0].eta == outcome["requestedArrival"]
    assert client.get(pp,headers=header).json()["evidence"]["currentEnvironment"] == evidence
    other=store.create("PORT_AUTHORITY")
    assert client.get(base+"/decisions/current-proposals",headers={"Authorization":"Bearer "+other["accessToken"]}).json()["proposals"] == []
    assert client.post(base+"/decisions/current-proposals/review",headers={"Authorization":"Bearer "+other["accessToken"]},
                       json={"decisionId":company["decisionId"]}).status_code == 404
    client.close()


def test_current_forecast_refuses_old_source_impossible_arrival_and_replay(tmp_path,monkeypatch):
    store,client=setup(tmp_path,monkeypatch); session=store.create("SHIPPING_COMPANY")
    header={"Authorization":"Bearer "+session["accessToken"]};base="/api/demo/terminal"
    epoch=datetime.fromisoformat(store.read(session["accessToken"])["epoch"])
    data=forecast(epoch)
    monkeypatch.setattr("src.portwatch_os.decision.current_arrival.bundle", lambda port: data)
    body={"domain":"vessel","vesselId":"PWD-001","currentArrival":{"plannedArrival":(epoch+timedelta(hours=12)).isoformat()}}
    assert client.post(base+"/decisions/problems",headers=header,json=body).status_code == 400
    body["currentArrival"]["plannedArrival"]=(epoch+timedelta(hours=181)).isoformat()
    data["sources"]["surface"]["status"]="STALE"
    assert client.post(base+"/decisions/problems",headers=header,json=body).status_code == 400
    body["at"]=epoch.isoformat()
    assert client.post(base+"/decisions/problems",headers=header,json=body).status_code == 409
    client.close()


def test_current_refresh_failure_preserves_original_receipt(tmp_path,monkeypatch):
    monkeypatch.setattr(environment,"ROOT",tmp_path)
    port=environment.port_registry.resolve("INNSA"); received=datetime.now(timezone.utc)-timedelta(hours=2)
    import json
    (tmp_path/"surface-INNSA.json").write_text(json.dumps({"kind":"surface","availableAt":received.isoformat(),"rows":[],"source":"public"}))
    monkeypatch.setattr(environment.requests,"get",Mock(side_effect=requests.RequestException("offline")))
    result=environment.refresh("surface",port)
    assert result["status"]=="STALE" and result["availableAt"]==received.isoformat()
