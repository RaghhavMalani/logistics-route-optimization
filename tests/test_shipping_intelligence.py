"""Reported-source scenario through the durable original Company/Port/Vessel flow."""
import json
from tests.test_demo_terminal import setup,resources
from tests.test_current_recovery import step,BASE

def test_connected_intelligence_recovery_isolation_and_idempotence(tmp_path,monkeypatch):
    store,client=setup(tmp_path,monkeypatch);session=store.create("SHIPPING_COMPANY");token=session["accessToken"];h={"Authorization":"Bearer "+token}
    root=tmp_path/"sources";(root/"shipping_intelligence").mkdir(parents=True)
    identifier="a"*64
    signal={"id":identifier,"category":"economic","title":"Fixture Brent quote","fact":"Fixture quote: 80 USD/bbl","source":"https://fred.stlouisfed.org/series/DCOILBRENTEU","status":"CACHED","availableAt":store.read(token)["epoch"],"mechanism":"Crude cost exposure; bunker quote unavailable","relationship":"Inferred contract exposure","responseSha256":"b"*64}
    (root/"shipping_intelligence"/(identifier+".json")).write_text(json.dumps(signal))
    monkeypatch.setattr("backend.app.routes.shipping_intelligence.ROOT",root)
    response=client.post(BASE+"/intelligence/shipping-comparison",headers=h,json={"signalId":identifier,"vesselId":"PWD-001","assumedHoldHours":6})
    assert response.status_code==200,response.text
    company=response.json();choice=next(o["optionId"] for o in company["options"] if not o["isBaseline"])
    for payload,status in (({"signalId":"../other","vesselId":"PWD-001","assumedHoldHours":6},422),
                           ({"signalId":identifier,"vesselId":"private-vessel","assumedHoldHours":6},404),
                           ({"signalId":identifier,"vesselId":"PWD-001","assumedHoldHours":True},422)):
        assert client.post(BASE+"/intelligence/shipping-comparison",headers=h,json=payload).status_code==status
    assert "currentEnvironment" not in company["evidence"] and company["evidence"]["intelligenceBasis"]["reportedFact"]==signal
    assert all(o["evaluation"]["objectives"]["cost"]["value"] is None for o in company["options"])
    cp=BASE+"/decisions/problems/"+company["decisionId"]
    step(client,cp,h,"REVIEWED");step(client,cp,h,"APPROVED",choice)
    assert client.get(cp,headers=h).json()["options"]==company["options"]
    store.switch(token,"PORT_AUTHORITY")
    assert client.post(BASE+"/intelligence/shipping-comparison",headers=h,json={"signalId":identifier,"vesselId":"PWD-001","assumedHoldHours":6}).status_code==403
    proposal=client.get(BASE+"/decisions/current-proposals",headers=h).json()["proposals"][0]
    assert proposal["evidenceKind"]=="intelligence"
    response=client.post(BASE+"/decisions/current-proposals/review",headers=h,json={"decisionId":company["decisionId"]});assert response.status_code==200,response.text
    port=response.json();pp=BASE+"/decisions/problems/"+port["decisionId"]
    step(client,pp,h,"REVIEWED");step(client,pp,h,"APPROVED",choice)
    response=client.post(pp+"/handoff",headers=h,json={});assert response.status_code==200,response.text
    rows=response.json()["advisories"];resources.cache_clear()
    assert client.post(pp+"/handoff",headers=h,json={}).json()["advisories"]==rows
    ap=BASE+"/advisories/"+rows[0]["advisoryId"]
    step(client,ap,h,"under_review");step(client,ap,h,"issued");store.switch(token,"VESSEL_OPERATOR")
    step(client,ap,h,"acknowledged");step(client,ap,h,"accepted");store.switch(token,"PORT_AUTHORITY")
    done=client.post(pp+"/demo-outcome",headers=h,json={});assert done.status_code==200,done.text
    assert done.json()["outcome"]["evidenceKind"]=="intelligence" and done.json()["outcome"]["selectedAssumedWaitHours"]==6
    resources.cache_clear();assert client.post(pp+"/demo-outcome",headers=h,json={}).json()==done.json()
    other=store.create("PORT_AUTHORITY");oh={"Authorization":"Bearer "+other["accessToken"]}
    assert client.get(pp,headers=oh).status_code==404
    assert client.post(pp+"/handoff",headers=oh,json={}).status_code==404
    client.close()

def test_current_hazard_receipt_does_not_redate_expired_event(tmp_path,monkeypatch):
    from datetime import datetime,timedelta,timezone
    from src.portwatch_os.intelligence import shipping_signals as signals
    from backend.app.services import cache_service
    now=datetime(2026,10,12,tzinfo=timezone.utc)
    monkeypatch.setattr(signals,"ROOT",tmp_path)
    monkeypatch.setattr(signals,"wall_now",lambda:now)
    monkeypatch.setattr(signals,"refresh",lambda *args:{"status":"CURRENT","rows":[{
        "lat":18.95,"lon":72.95,"kind":"DR","title":"Expired fixture drought",
        "alertLevel":"Green","source":"https://www.gdacs.org/",
        "publishedAt":(now-timedelta(days=10)).isoformat(),
        "validFrom":(now-timedelta(days=10)).isoformat(),"validThrough":(now-timedelta(days=1)).isoformat()}]})
    monkeypatch.setattr(signals,"economic_signal",lambda *args:{"category":"economic","title":"Unavailable fixture quote","status":"UNAVAILABLE"})
    monkeypatch.setattr(cache_service,"get_news_bundle",lambda:{})
    result=signals.signals_for({"fleet":[{"id":"PWD-001","name":"Fixture ship","portCode":"INNSA","laneCode":"EUR_IND","cargo":"Fixture manifest"}]})
    hazard=next(s for s in result["signals"] if s["category"]=="hazard")
    assert hazard["status"]=="STALE" and hazard["sourceReceiptStatus"]=="CURRENT"
    assert hazard["active"] is False and hazard["validThrough"]==(now-timedelta(days=1)).isoformat()
