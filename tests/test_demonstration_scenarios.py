"""Teaching presets must exercise real engines without provider/scoring writes."""
import copy,json
from tests.test_demo_terminal import setup

BASE='/api/demo/terminal'


def choose(client,headers,id):
    r=client.post(BASE+'/demonstrations/select',headers=headers,json={'scenarioId':id,'requestId':'test-request-'+id,'acknowledged':True})
    assert r.status_code==200,r.text
    return r.json()


def test_all_scenarios_are_bounded_reproducible_engine_results(tmp_path,monkeypatch):
    store,client=setup(tmp_path,monkeypatch);s=store.create('SHIPPING_COMPANY');h={'Authorization':'Bearer '+s['accessToken']}
    monkeypatch.setattr('src.portwatch_os.decision.current_arrival.bundle',lambda p:(_ for _ in ()).throw(AssertionError('Preset fetched real forecast')))
    results={}
    for i in range(1,27):
        id=f'S{i:02}';result=choose(client,h,id);results[id]=result
        if i in (6,7,8):
            from src.portwatch_os.decision.routing import routes_for
            from src.portwatch_os.learning.weather_feedback import instant
            world=store.read(s['accessToken']);v=world['fleet'][0]
            routes=routes_for(v['laneCode'],v['portCode'],{'SUEZ':v['hoursToRisk']},12.)
            declared=(instant(world['epoch'])-instant(result['selectedAt'])).total_seconds()/3600+v['etaHours']
            assert abs(declared-routes.remaining_primary_nm/12.)<1/3600
        before=copy.deepcopy(store.read(s['accessToken']))
        assert choose(client,h,id)==result
        assert store.read(s['accessToken'])==before
        if result.get('problem'):
            assert result['problem']['options']
            if i not in (6,7,8):assert result['problem']['evidence']['currentEnvironment']['evidenceKind']=='SOFTWARE_LIFECYCLE_FIXTURE'
    (tmp_path/'results.json').write_text(json.dumps(results,indent=2))
    assert results['S10'].get('problem'),results['S10']
    assert results['S16'].get('problem'),results['S16']
    assert all(o['status']=='FEASIBLE' for o in results['S10']['problem']['options'])
    assert any(o['action']=='DELAY_DEPARTURE' for o in results['S12']['problem']['options'])
    assert any(o['action']=='SPEED_UP' and o['status']=='FEASIBLE' for o in results['S11']['problem']['options'])
    assert next(a for a in results['S13']['problem']['availableActions'] if a['kind']=='DELAY_DEPARTURE')['availability']['status']=='UNAVAILABLE'
    assert results['S25']['status']=='BLOCKED_INPUT'
    other=store.create('SHIPPING_COMPANY');oh={'Authorization':'Bearer '+other['accessToken']}
    assert client.get(BASE+'/demonstrations/selection',headers=oh).json()=={'selection':None}
    pid=results['S10']['problem']['decisionId']
    assert client.get(BASE+'/decisions/problems/'+pid,headers=oh).status_code==404
    store.switch(s['accessToken'],'VESSEL_OPERATOR')
    assert client.post(BASE+'/demonstrations/select',headers=h,json={'scenarioId':'S10','requestId':'forbidden-1','acknowledged':True}).status_code==403
    assert client.get('/api/demonstrations/scenarios',headers=h).status_code in (401,404)
    client.close()


def test_daily_rule_begins_exact_declared_destination_call_and_gets_are_pure(tmp_path,monkeypatch):
    store,client=setup(tmp_path,monkeypatch);s=store.create('SHIPPING_COMPANY');token=s['accessToken'];h={'Authorization':'Bearer '+token}
    from src.portwatch_os.intelligence import public_port_context as source,public_ports
    from unittest.mock import Mock
    monkeypatch.setattr(source,'root_path',lambda:tmp_path/'absent-public-archive')
    monkeypatch.setattr(public_ports.PublicPilot,'__init__',Mock(side_effect=AssertionError('GET must not initialize a source store')))
    monkeypatch.setattr(public_ports,'fetch',Mock(side_effect=AssertionError('GET must not fetch')))
    before=store.read(token)
    a=client.get(BASE+'/intelligence/port-context',headers=h);assert a.status_code==200
    assert client.get(BASE+'/intelligence/port-context/audit',headers=h).status_code==200
    assert store.read(token)==before and not (tmp_path/'absent-public-archive').exists()
    body={'vesselId':'PWD-001','metricId':'WORKING_LISTED_ROWS','threshold':15,'acknowledged':True,'declareDestination':True}
    r=client.post(BASE+'/intelligence/port-context/rule',headers=h,json=body);assert r.status_code==200,r.text
    world=store.read(token);v=world['fleet'][0]
    assert v['portCode']==v['operationalEpisode']['portCode']=='INPRT'
    assert r.json()['episodeId']==v['operationalEpisode']['id']
    assert client.post(BASE+'/intelligence/port-context/rule',headers=h,json=body).json()['id']==r.json()['id']
    assert client.get(BASE+'/intelligence/port-context?vesselId=unknown',headers=h).status_code==404
    assert client.get(BASE+'/intelligence/operational-evidence/original?product=PUBLIC_PORT_PDF&portCode=INPRT&snapshotId=x',headers=h).status_code==403
    store.switch(token,'VESSEL_OPERATOR')
    assert client.post(BASE+'/intelligence/port-context/rule',headers=h,json=body).status_code==403
    client.close()


def test_selected_port_fixture_does_not_relabel_another_owned_port(tmp_path,monkeypatch):
    # An explicit INPRT teaching selection must not poison other owned calls.
    from datetime import timedelta
    from src.portwatch_os.learning.weather_feedback import instant
    store,client=setup(tmp_path,monkeypatch);s=store.create('SHIPPING_COMPANY');h={'Authorization':'Bearer '+s['accessToken']}
    choose(client,h,'S10');world=store.read(s['accessToken']);v=world['fleet'][1];arrival=instant(world['epoch'])+timedelta(hours=v['etaHours'])
    data={'portCode':v['portCode'],'sources':{'surface':{'status':'CURRENT','source':'TEST_ONLY_OTHER_PORT_BUNDLE','snapshotId':'test-only-other-port','responseSha256':'a'*64,'issuedAt':None,'availableAt':world['epoch']},'hazards':{'snapshotId':None}},
          'hourly':[{'validAt':(arrival+timedelta(hours=n)).isoformat(),'wind_gusts_10m':8.,'visibility':10000.,'wave_height':None} for n in range(4)]}
    monkeypatch.setattr('src.portwatch_os.decision.current_arrival.bundle',lambda port:data)
    r=client.post(BASE+'/decisions/problems',headers=h,json={'domain':'vessel','vesselId':v['id'],'currentArrival':{'plannedArrival':arrival.isoformat()}})
    assert r.status_code==200,r.text
    env=r.json()['evidence']['currentEnvironment'];assert 'evidenceKind' not in env and 'scenario' not in env
    assert env['source']=='TEST_ONLY_OTHER_PORT_BUNDLE'
    client.close()


def test_consumed_daily_context_reassesses_and_keeps_approvals(tmp_path,monkeypatch):
    store,client=setup(tmp_path,monkeypatch);session=store.create('SHIPPING_COMPANY');token=session['accessToken'];h={'Authorization':'Bearer '+token}
    selected=choose(client,h,'S03')
    r=client.post(BASE+'/intelligence/port-context/rule',headers=h,json={'vesselId':'PWD-001','metricId':'ANCHORAGE_READY_ROWS','threshold':6,'acknowledged':True,'declareDestination':True})
    assert r.status_code==200,r.text
    rule=r.json();context=client.get(BASE+'/intelligence/port-context',headers=h).json()['context']
    body=copy.deepcopy(selected['inputs']);body['currentArrival']['portContextReviews']=[{'ruleId':rule['id'],'revisionId':context['revisionId'],'acknowledged':True}]
    r=client.post(BASE+'/decisions/problems',headers=h,json=body);assert r.status_code==200,r.text
    problem=r.json();id=problem['decisionId'];option=next(o for o in problem['options'] if o['status']=='FEASIBLE' and not o['isBaseline'])['optionId'];path=BASE+'/decisions/problems/'+id
    frozen=copy.deepcopy(problem['evidence']['currentEnvironment'])
    assert frozen['portContextBindings'][0]['metric']['value']==4
    for target in ['REVIEWED','APPROVED']:
        r=client.post(path+'/transition',headers=h,json={'target':target,'optionId':option});assert r.status_code==200,r.text
    from backend.app.services.demo_terminal import resources
    resources.cache_clear()
    store.switch(token,'PORT_AUTHORITY')
    r=client.post(BASE+'/decisions/current-proposals/review',headers=h,json={'decisionId':id});assert r.status_code==200,r.text
    review_id=r.json()['decisionId']
    store.switch(token,'SHIPPING_COMPANY')
    r=client.post(BASE+'/demonstrations/advance-source',headers=h,json={'acknowledged':True});assert r.status_code==200,r.text
    changed=r.json()['context'];assert changed['metrics'][0]['value']==7
    store.switch(token,'PORT_AUTHORITY')
    r=client.post(BASE+'/decisions/problems/'+review_id+'/transition',headers=h,json={'target':'REVIEWED','optionId':option});assert r.status_code==200,r.text
    r=client.post(BASE+'/decisions/problems/'+review_id+'/transition',headers=h,json={'target':'APPROVED','optionId':option});assert r.status_code==409,r.text
    store.switch(token,'SHIPPING_COMPANY')
    assert client.get(path,headers=h).json()['workflow']=='APPROVED'
    assert client.get(path,headers=h).json()['evidence']['currentEnvironment']==frozen
    body['predecessorDecisionId']=id
    assert client.post(BASE+'/decisions/problems',headers=h,json=body).status_code==400
    body['currentArrival']['portContextReviews'][0]['revisionId']=changed['revisionId']
    r=client.post(BASE+'/decisions/problems',headers=h,json=body);assert r.status_code==200,r.text
    assert r.json()['workflow']=='COMPUTED' and r.json()['evidence']['predecessorDecisionId']==id
    assert client.post(BASE+'/decisions/problems',headers=h,json=body).json()['decisionId']==r.json()['decisionId']
    client.close()
