"""Reported-source scenario through the durable original Company/Port/Vessel flow."""
import json
from tests.test_demo_terminal import setup,resources
from tests.test_current_recovery import step,BASE

def test_contextual_news_creates_verification_task_without_assumed_hold(tmp_path,monkeypatch):
    import hashlib
    store,client=setup(tmp_path,monkeypatch);session=store.create("SHIPPING_COMPANY");token=session["accessToken"];h={"Authorization":"Bearer "+token}
    root=tmp_path/"sources";folder=root/"shipping_intelligence";folder.mkdir(parents=True)
    identifier="a"*64;raw=b'{"synthetic":"attributed news source fixture"}';digest=hashlib.sha256(raw).hexdigest()
    signal={"id":identifier,"category":"news","title":"Synthetic operator announcement","fact":"Synthetic news fixture; event outcome unavailable","source":"https://fixture.example/announcement","status":"CACHED","portCodes":["INNSA"],"availableAt":store.read(token)["epoch"],"mechanism":"Source and passage require verification; event-caused delay unavailable","relationship":"Contextual destination association, not passage proof","responseSha256":digest}
    (folder/(identifier+".json")).write_text(json.dumps(signal));(folder/(digest+".response")).write_bytes(raw)
    monkeypatch.setattr("backend.app.routes.shipping_intelligence.ROOT",root)
    rejected=client.post(BASE+"/intelligence/shipping-comparison",headers=h,json={"signalId":identifier,"vesselId":"PWD-001","assumedHoldHours":6})
    assert rejected.status_code==422 and 'review-tasks' in rejected.text
    payload={"signalId":identifier,"vesselId":"PWD-001","requestId":"news-verification-fixture"}
    response=client.post(BASE+"/intelligence/review-tasks",headers=h,json=payload)
    assert response.status_code==200,response.text
    task=response.json()
    assert task['kind']=='SOURCE_EXPOSURE_VERIFICATION_TASK' and task['status']=='PENDING_VERIFICATION'
    assert task['source']==signal and task['calculatedDelayHours'] is None and task['createsOperationalTarget'] is False
    assert task['exposure']['status']=='INSUFFICIENT_DATA' and task['actualExecutionStatus']=='NOT_OBSERVED'
    resources.cache_clear()
    assert client.post(BASE+"/intelligence/review-tasks",headers=h,json=payload).json()==task
    assert client.get(BASE+"/intelligence/review-tasks",headers=h).json()['tasks']==[task]
    assert client.get(BASE+"/decisions/problems",headers=h).json()['total']==0
    assert not client.get(BASE+"/intelligence/feedback/impacts",headers=h).json()['claims']
    assert client.post(BASE+"/intelligence/review-tasks",headers=h,json={**payload,'vesselId':'PWD-002'}).status_code==409
    store.switch(token,'PORT_AUTHORITY')
    assert client.get(BASE+"/intelligence/review-tasks",headers=h).json()['tasks']==[task]
    assert client.post(BASE+"/intelligence/review-tasks",headers=h,json=payload).status_code==403
    store.switch(token,'VESSEL_OPERATOR')
    assert client.get(BASE+"/intelligence/review-tasks",headers=h).json()['tasks']==[task]
    other=store.create('SHIPPING_COMPANY');oh={'Authorization':'Bearer '+other['accessToken']}
    assert client.get(BASE+"/intelligence/review-tasks",headers=oh).json()['tasks']==[]
    client.close()


def test_reference_quotes_cannot_create_an_operational_hold(tmp_path,monkeypatch):
    store,client=setup(tmp_path,monkeypatch);session=store.create('SHIPPING_COMPANY')
    root=tmp_path/'sources';folder=root/'shipping_intelligence';folder.mkdir(parents=True)
    identifier='a'*64
    (folder/(identifier+'.json')).write_text(json.dumps({'id':identifier,'category':'economic','title':'Synthetic reference quote'}))
    monkeypatch.setattr('backend.app.routes.shipping_intelligence.ROOT',root)
    r=client.post(BASE+'/intelligence/shipping-comparison',headers={'Authorization':'Bearer '+session['accessToken']},
        json={'signalId':identifier,'vesselId':'PWD-001','assumedHoldHours':6})
    assert r.status_code==422 and 'cannot create a vessel hold' in r.text
    client.close()


def test_review_task_original_hash_future_availability_and_vessel_scope(tmp_path,monkeypatch):
    import hashlib
    from datetime import datetime,timedelta
    store,client=setup(tmp_path,monkeypatch);session=store.create('SHIPPING_COMPANY');token=session['accessToken']
    h={'Authorization':'Bearer '+token};folder=tmp_path/'sources'/'shipping_intelligence';folder.mkdir(parents=True)
    monkeypatch.setattr('backend.app.routes.shipping_intelligence.ROOT',folder.parent)
    identifier='c'*64;raw=b'{"synthetic":"review source product"}';digest=hashlib.sha256(raw).hexdigest()
    signal={'id':identifier,'category':'news','title':'Synthetic unverified report','source':'https://fixture.example/report',
        'fact':'Synthetic source record, not independent outcome evidence','responseSha256':digest,'status':'CACHED',
        'availableAt':store.read(token)['epoch']}
    original=folder/(digest+'.response');original.write_bytes(b'corrupt')
    path=folder/(identifier+'.json');path.write_text(json.dumps(signal))
    payload={'signalId':identifier,'vesselId':'PWD-002','requestId':'review-original-hash'}
    endpoint=BASE+'/intelligence/review-tasks'
    assert client.post(endpoint,headers=h,json=payload).status_code==409
    assert not client.get(endpoint,headers=h).json()['tasks']
    original.write_bytes(raw)
    future={**signal,'availableAt':(datetime.fromisoformat(signal['availableAt'])+timedelta(days=1)).isoformat()}
    path.write_text(json.dumps(future))
    assert client.post(endpoint,headers=h,json=payload).status_code==409
    path.write_text(json.dumps(signal))
    created=client.post(endpoint,headers=h,json=payload);assert created.status_code==200,created.text
    original.write_bytes(b'corrupt after task frozen')
    resources.cache_clear()
    # Retrying a completed write recovers its exact record; no renewed source claim/action is made.
    assert client.post(endpoint,headers=h,json=payload).json()==created.json()
    assert client.post(endpoint,headers=h,json={**payload,'requestId':'different-new-intent'}).status_code==409
    store.switch(token,'VESSEL_OPERATOR')
    assert client.get(endpoint,headers=h).json()['tasks']==[]
    store.switch(token,'PORT_AUTHORITY')
    assert client.get(endpoint,headers=h).json()['tasks']==[created.json()]
    client.close();resources.cache_clear()

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
