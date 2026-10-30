"""Controlled synthetic NHO + weather workflow, separate from real-source acceptance."""
import copy
from datetime import datetime, timedelta
import json

from tests.test_demo_terminal import setup, resources
from tests.test_current_input_journey import forecast
from tests.test_current_recovery import step
from tests.test_indian_notices import ID, URL, pages
from src.portwatch_os.intelligence import indian_notices as n, current_environment as environment

BASE='/api/demo/terminal'


def journey(tmp_path, monkeypatch):
    store,client=setup(tmp_path,monkeypatch)
    public=tmp_path/'public';monkeypatch.setenv('PORTWATCH_CURRENT_ENVIRONMENT_DIR',str(public));monkeypatch.setattr(environment,'ROOT',public)
    session=store.create('SHIPPING_COMPANY');token=session['accessToken'];h={'Authorization':'Bearer '+token}
    epoch=datetime.fromisoformat(store.read(token)['epoch'])
    text=pages(day=epoch.strftime('%d %b %Y').upper())
    monkeypatch.setattr(n,'parse',lambda _:n.parse_pages(text))
    state=n.retain(b'SYNTHETIC NHO WORKFLOW ORIGINAL',document_url=URL,received_at=epoch.isoformat(),root=public/'indian_notices')
    source=state['notices'][0]
    declaration={'vesselId':'PWD-001','noticeId':ID,'portCode':'INPRT','direction':'INBOUND','passageAt':(epoch+timedelta(hours=180)).isoformat(),'postPassageHours':0,'declarationConfirmed':True}
    response=client.post(BASE+'/intelligence/indian-passage-plan',headers=h,json=declaration)
    assert response.status_code==200,response.text
    data=forecast(epoch);data['portCode']='INPRT'
    monkeypatch.setattr('src.portwatch_os.decision.current_arrival.bundle',lambda _:data)
    body={'domain':'vessel','vesselId':'PWD-001','currentArrival':{'plannedArrival':(epoch+timedelta(hours=181)).isoformat(),'maxGustKn':15,'minVisibilityM':5000,'sourceReviews':[{'noticeId':ID,'revisionId':source['revisionId'],'acknowledged':True}]}}
    response=client.post(BASE+'/decisions/problems',headers=h,json=body)
    assert response.status_code==200,response.text
    return store,client,token,h,response.json(),body,state,epoch,declaration


def test_context_frozen_through_all_roles_recovery_retries_and_isolation(tmp_path,monkeypatch):
    store,c,token,h,company,body,state,epoch,declaration=journey(tmp_path,monkeypatch)
    env=company['evidence']['currentEnvironment'];bindings=copy.deepcopy(env['sourceReviewBindings'])
    assert env['forecastGateWaitHours']==2 and bindings[0]['numericalEffect'] is None
    choice=next(o['optionId'] for o in company['options'] if not o['isBaseline'])
    cp=BASE+'/decisions/problems/'+company['decisionId']
    step(c,cp,h,'REVIEWED');step(c,cp,h,'APPROVED',choice)
    store.switch(token,'PORT_AUTHORITY');assert store.session(token)['user']['portCode']=='INPRT'
    r=c.post(BASE+'/decisions/current-proposals/review',headers=h,json={'decisionId':company['decisionId']});assert r.status_code==200,r.text
    pp=BASE+'/decisions/problems/'+r.json()['decisionId']
    step(c,pp,h,'REVIEWED');step(c,pp,h,'APPROVED',choice)
    r=c.post(pp+'/handoff',headers=h,json={});assert r.status_code==200,r.text
    advisory=r.json()['advisories'][0];resources.cache_clear()
    assert c.post(pp+'/handoff',headers=h,json={}).json()['advisories']==[advisory]
    assert advisory['evidence']['currentEnvironment']['sourceReviewBindings']==bindings
    ap=BASE+'/advisories/'+advisory['advisoryId'];step(c,ap,h,'under_review');step(c,ap,h,'issued')
    store.switch(token,'VESSEL_OPERATOR');step(c,ap,h,'acknowledged');step(c,ap,h,'accepted')
    store.switch(token,'PORT_AUTHORITY');done=c.post(pp+'/demo-outcome',headers=h,json={});assert done.status_code==200,done.text
    assert done.json()['outcome']['kind']=='SIMULATED_DEMO_OUTCOME'
    resources.cache_clear();assert c.post(pp+'/demo-outcome',headers=h,json={}).json()==done.json()
    store.switch(token,'SHIPPING_COMPANY')
    assert c.get(cp,headers=h).json()['evidence']['currentEnvironment']['sourceReviewBindings']==bindings
    other=store.create('SHIPPING_COMPANY');oh={'Authorization':'Bearer '+other['accessToken']}
    assert c.get(cp,headers=oh).status_code==404 and c.get(ap,headers=oh).status_code==404
    assert c.get(BASE+'/intelligence/navigation-restrictions',headers=oh).json()['voyages'][0].get('declaredPassages') is None
    store.switch(token,'SHIPPING_COMPANY')
    assert c.post(BASE+'/intelligence/indian-passage-plan',headers=h,json=declaration).status_code==409
    c.close()


def test_revision_requires_explicit_successor_and_preserves_approval(tmp_path,monkeypatch):
    store,c,token,h,company,body,state,epoch,_=journey(tmp_path,monkeypatch)
    cp=BASE+'/decisions/problems/'+company['decisionId'];choice=company['baselineOptionId']
    step(c,cp,h,'REVIEWED');step(c,cp,h,'APPROVED',choice);approved=c.get(cp,headers=h).json()
    text=pages('REVISED SYNTHETIC WORDING',day=epoch.strftime('%d %b %Y').upper())
    monkeypatch.setattr(n,'parse',lambda _:n.parse_pages(text))
    new=n.retain(b'SYNTHETIC REVISED ORIGINAL',document_url=URL,received_at=epoch.isoformat(),root=tmp_path/'public'/'indian_notices')['notices'][0]
    store.switch(token,'PORT_AUTHORITY')
    assert c.post(BASE+'/decisions/current-proposals/review',headers=h,json={'decisionId':company['decisionId']}).status_code==409
    store.switch(token,'SHIPPING_COMPANY')
    projection=c.get(BASE+'/company/decision-triage',headers=h).json();row=next(r for r in projection['rows'] if r['vessel']['id']=='PWD-001')
    assert row['primaryCategory']=='REASSESSMENT' and row['freshness']['sourceChanges'][0]['changes']
    assert c.post(cp+'/refresh',headers=h,json={}).status_code==409
    missing=copy.deepcopy(body);missing['predecessorDecisionId']=company['decisionId'];missing['currentArrival'].pop('sourceReviews')
    assert c.post(BASE+'/decisions/problems',headers=h,json=missing).status_code==409
    body['predecessorDecisionId']=company['decisionId'];body['currentArrival']['sourceReviews'][0]['revisionId']=new['revisionId']
    r=c.post(BASE+'/decisions/problems',headers=h,json=body);assert r.status_code==200,r.text
    assert r.json()['decisionId']!=company['decisionId'] and r.json()['workflow']=='COMPUTED'
    original=c.get(cp,headers=h).json()
    assert original['evidence']['currentEnvironment']==approved['evidence']['currentEnvironment']
    assert original['evidence']['approvalBasis']==approved['evidence']['approvalBasis']
    assert original['humanChoice']==approved['humanChoice'] and original['workflowHistory']==approved['workflowHistory']
    c.close()


def test_source_get_audit_read_only_and_permissions(tmp_path,monkeypatch):
    store,c,token,h,company,body,state,epoch,declaration=journey(tmp_path,monkeypatch)
    before={str(p.relative_to(tmp_path)):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file() and not str(p).endswith(('-wal','-shm'))}
    monkeypatch.setattr(n.requests,'get',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('GET must not collect')))
    listing=c.get(BASE+'/intelligence/navigation-restrictions',headers=h);assert listing.status_code==200,listing.text
    row=next(r for r in listing.json()['notices'] if r['noticeId']==ID)
    audit=c.get(BASE+'/intelligence/indian-source-audit',headers=h,params={'noticeId':ID,'asOf':listing.json()['asOf']})
    assert audit.status_code==200 and audit.json()['notice']==row
    assert 'sourceText' not in row and not row['originalDownloadAvailable']
    assert c.get(BASE+'/intelligence/indian-source-audit',headers=h,params={'noticeId':ID,'asOf':(epoch-timedelta(seconds=1)).isoformat()}).status_code==404
    after={str(p.relative_to(tmp_path)):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file() and not str(p).endswith(('-wal','-shm'))}
    assert before==after
    assert c.post(BASE+'/intelligence/navigation-restrictions/refresh',headers=h,json={'sourceFamily':n.FAMILY,'url':'https://other.invalid'}).status_code==422
    store.switch(token,'VESSEL_OPERATOR')
    assert c.post(BASE+'/intelligence/navigation-restrictions/refresh',headers=h,json={'sourceFamily':n.FAMILY}).status_code==403
    assert c.post(BASE+'/intelligence/indian-passage-plan',headers=h,json=declaration).status_code==403
    c.close()
