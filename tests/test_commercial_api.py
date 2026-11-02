"""Actual API/ledger boundaries with explicitly fictional scenario inputs."""
import copy
from tests.test_demo_terminal import setup,resources

BASE='/api/demo/terminal'


def test_all_explicit_examples_have_valid_typed_declarations(tmp_path,monkeypatch):
    from src.portwatch_os.decision.commercial import CommercialContext
    from src.portwatch_os.decision.commercial_uncertainty import Simulation
    store,client=setup(tmp_path,monkeypatch)
    session=store.create('SHIPPING_COMPANY');h={'Authorization':'Bearer '+session['accessToken']}
    r=client.post(BASE+'/demonstrations/select',headers=h,json={'scenarioId':'S16','requestId':'typed-examples','acknowledged':True})
    assert r.status_code==200,r.text
    decision_id=r.json()['problem']['decisionId']
    for name in ('CURRENT_SOURCE','PERISHABLE','BULK','MANUFACTURING','ELECTRONICS','CHOKEPOINT','INSURANCE','MARKET','MEAN_TAIL','MULTI','INCOMPLETE','REVISION','RESOURCE'):
        r=client.get(BASE+'/commercial/templates/'+decision_id,params={'example':name},headers=h)
        assert r.status_code==200,(name,r.text)
        model=CommercialContext(**r.json()['context'])
        configuration=r.json()['simulation']
        assert configuration['acknowledgedAssumptions'] is False
        configuration['acknowledgedAssumptions']=True
        Simulation(**configuration)
        assert model.decisionId==decision_id and model.basis.kind=='SIMULATION'


def study(tmp_path,monkeypatch):
    store,client=setup(tmp_path,monkeypatch)
    session=store.create('SHIPPING_COMPANY');token=session['accessToken'];headers={'Authorization':'Bearer '+token}
    response=client.post(BASE+'/demonstrations/select',headers=headers,json={'scenarioId':'S16','requestId':'commercial-api-case','acknowledged':True})
    assert response.status_code==200,response.text
    problem=response.json()['problem']
    template=client.get(BASE+'/commercial/templates/'+problem['decisionId'],headers=headers)
    assert template.status_code==200,template.text
    payload={k:template.json()[k] for k in ('context','simulation')};payload['simulation']['acknowledgedAssumptions']=True
    result=client.post(BASE+'/commercial/evaluate',headers=headers,json=payload)
    assert result.status_code==200,result.text
    return store,client,token,headers,problem,payload,result.json()


def test_retained_get_retry_resource_eviction_and_private_roles(tmp_path,monkeypatch):
    store,client,token,h,p,payload,result=study(tmp_path,monkeypatch)
    resources.cache_clear()
    monkeypatch.setattr('backend.app.routes.commercial.simulate',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Retained reads/retries must not rerun simulation')))
    assert client.get(BASE+'/commercial/records/'+result['recordId'],headers=h).json()==result
    job_id=result['computeJob']['id']
    assert client.get(BASE+'/commercial/jobs/'+job_id,headers=h).json()['status']=='COMPLETED'
    retry=client.post(BASE+'/commercial/evaluate',headers=h,json=payload)
    assert retry.status_code==200 and retry.json()==result
    other=store.create('SHIPPING_COMPANY')
    assert client.get(BASE+'/commercial/records/'+result['recordId'],headers={'Authorization':'Bearer '+other['accessToken']}).status_code==404
    assert client.get(BASE+'/commercial/jobs/'+job_id,headers={'Authorization':'Bearer '+other['accessToken']}).status_code==404
    assert client.post(BASE+'/commercial/jobs/'+job_id+'/cancel',headers={'Authorization':'Bearer '+other['accessToken']},json={}).status_code==404
    for role in ('PORT_AUTHORITY','VESSEL_OPERATOR','NATIONAL_ADMIN'):
        store.switch(token,role)
        assert client.get(BASE+'/commercial/records/'+result['recordId'],headers=h).status_code==403


def test_successor_is_fresh_review_minimal_shared_binding_and_revision(tmp_path,monkeypatch):
    store,client,token,h,p,payload,result=study(tmp_path,monkeypatch)
    path=BASE+'/commercial/records/'+result['recordId']+'/successor'
    r=client.post(path,headers=h,json={})
    assert r.status_code==200,r.text
    successor=r.json()
    assert successor['decisionId']!=p['decisionId'] and successor['workflow']=='COMPUTED'
    binding=successor['evidence']['commercialReview']
    assert binding['contextHash']==result['contextHash'] and binding['worldSampleHash']==result['uncertainty']['worldSampleHash']
    assert not {'context','policies','parties','consignments','simulationConfiguration'} & set(binding)
    assert client.post(path,headers=h,json={}).json()['decisionId']==successor['decisionId']
    assert client.get(BASE+'/decisions/problems/'+p['decisionId'],headers=h).json()['evidence'].get('commercialReview') is None
    revised=copy.deepcopy(payload);revised['context']['accountingScope']+='; revised declared basis'
    new=client.post(BASE+'/commercial/evaluate',headers=h,json=revised)
    assert new.status_code==200,new.text
    assert new.json()['previousCommercialId']==result['recordId']
    assert client.get(BASE+'/commercial/records/'+result['recordId'],headers=h).json()==result
    option=next(o for o in successor['options'] if o['status']=='FEASIBLE')['optionId']
    assert client.post(BASE+'/decisions/problems/'+successor['decisionId']+'/transition',headers=h,json={'target':'REVIEWED','optionId':option}).status_code==200
    refused=client.post(BASE+'/decisions/problems/'+successor['decisionId']+'/transition',headers=h,json={'target':'APPROVED','optionId':option})
    assert refused.status_code==409,refused.text


def test_private_commercial_terms_do_not_cross_the_advisory_boundary(tmp_path,monkeypatch):
    store,client,token,h,p,payload,result=study(tmp_path,monkeypatch)
    r=client.post(BASE+'/commercial/records/'+result['recordId']+'/successor',headers=h,json={});assert r.status_code==200,r.text
    successor=r.json();option=next(o for o in successor['options'] if o['status']=='FEASIBLE' and not o['isBaseline'])['optionId']
    company=BASE+'/decisions/problems/'+successor['decisionId']
    for target in ('REVIEWED','APPROVED'):
        r=client.post(company+'/transition',headers=h,json={'target':target,'optionId':option});assert r.status_code==200,r.text
    store.switch(token,'PORT_AUTHORITY')
    r=client.post(BASE+'/decisions/current-proposals/review',headers=h,json={'decisionId':successor['decisionId']});assert r.status_code==200,r.text
    port=r.json();assert port['evidence']['commercialReview']==successor['evidence']['commercialReview']
    target=BASE+'/decisions/problems/'+port['decisionId']
    for state in ('REVIEWED','APPROVED'):
        r=client.post(target+'/transition',headers=h,json={'target':state,'optionId':option});assert r.status_code==200,r.text
    r=client.post(target+'/handoff',headers=h,json={});assert r.status_code==200,r.text
    body=r.json()
    assert 'Fictional demo carrier' not in str(body)
    assert 'additional downstream handling delay; these weights' not in str(body)
    assert result['contextHash'] in str(body)
