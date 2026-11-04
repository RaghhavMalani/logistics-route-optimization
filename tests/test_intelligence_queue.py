"""Synthetic visitor/API regressions; no provider or deployed-state writes."""
import copy
from datetime import timedelta

from tests.test_current_recovery import BASE, step
from tests.test_demo_terminal import setup, resources
from tests.test_navigation_restrictions import NOW, plan, retained, scripted_clock as queue_clock
from src.portwatch_os.intelligence import navigation_restrictions as n


def catalogue(tmp_path,monkeypatch):
    first=retained(tmp_path,monkeypatch)
    first.update(noticeId='NAVCEN_MSI:53842',providerNoticeId='53842',extractionStatus='SUPPORTED',calculationSupported=True)
    second={**copy.deepcopy(first),'noticeId':'NAVCEN_MSI:synthetic-second','providerNoticeId':'synthetic-second',
        'areaId':'SYNTHETIC_SECOND_ASSET','title':'Synthetic unrelated second asset','revisionId':'synthetic-second-revision'}
    expired={**copy.deepcopy(first),'noticeId':'NAVCEN_MSI:synthetic-expired','providerNoticeId':'synthetic-expired',
        'areaId':'SYNTHETIC_EXPIRED_ASSET','title':'Synthetic expired notice','status':'EXPIRED','calculationSupported':False}
    items=[first,second,expired]
    monkeypatch.setattr(n,'refresh',lambda force=False,notice_id=None:copy.deepcopy(next(x for x in items if x['noticeId']==(notice_id if str(notice_id).startswith('NAVCEN_MSI:') else 'NAVCEN_MSI:'+str(notice_id or '53842')))))
    monkeypatch.setattr(n,'refresh_all',lambda force=False:{'notices':copy.deepcopy(items),'sourceStatus':'CURRENT',
        'sourceRegistry':[{'provider':'USCG NAVCEN','family':'reviewed bridge intervals','meaning':'Synthetic route contract fixture'}]})
    return items


def declared_comparison(tmp_path,monkeypatch):
    store,client=setup(tmp_path,monkeypatch);items=catalogue(tmp_path,monkeypatch)
    session=store.create('SHIPPING_COMPANY');token=session['accessToken'];h={'Authorization':'Bearer '+token}
    declared=client.post(BASE+'/intelligence/navigation-passage-plan',headers=h,json={**plan(),'noticeId':items[0]['noticeId']})
    assert declared.status_code==200,declared.text
    result=client.post(BASE+'/intelligence/navigation-comparison',headers=h,
        json={'vesselId':'PWD-001','noticeId':items[0]['noticeId'],'revisionId':items[0]['revisionId']})
    assert result.status_code==200,result.text
    return store,client,token,h,items,declared.json(),result.json()


def test_rolling_list_bidirectional_exposure_roles_and_isolation(tmp_path,monkeypatch,queue_clock):
    store,client,token,h,items,declared,p=declared_comparison(tmp_path,monkeypatch)
    listing=client.get(BASE+'/intelligence/navigation-restrictions',headers=h)
    assert listing.status_code==200,listing.text
    data=listing.json()
    assert len(data['notices'])==3 and len(data['exposureQueue'])==9
    confirmed=next(r for r in data['exposureQueue'] if r['noticeId']==items[0]['noticeId'] and r['vesselId']=='PWD-001')
    assert confirmed['status']=='CONFIRMED_DECLARED_EXPOSURE' and confirmed['calculable']
    assert confirmed['priority']['rank']==1 and 'not disruption probability' in confirmed['priority']['label']
    assert any(r['sourceValidity']=='EXPIRED' and not r['calculable'] for r in data['exposureQueue'])
    event=client.get(BASE+'/intelligence/voyage-exposure?noticeId=NAVCEN_MSI:53842',headers=h).json()
    voyage=client.get(BASE+'/intelligence/voyage-exposure?vesselId=PWD-001',headers=h).json()
    assert len(event['relations'])==3 and len(voyage['relations'])==3
    assert event['counts']['CONFIRMED_DECLARED_EXPOSURE']==1
    assert all(r['status']=='NO_DEMONSTRATED_EXPOSURE' for r in event['relations'] if r['vesselId']!='PWD-001')
    store.switch(token,'VESSEL_OPERATOR')
    assert len(client.get(BASE+'/intelligence/navigation-restrictions',headers=h).json()['voyages'])==1
    assert client.get(BASE+'/intelligence/voyage-exposure?vesselId=PWD-002',headers=h).status_code==404
    other=store.create('SHIPPING_COMPANY');oh={'Authorization':'Bearer '+other['accessToken']}
    foreign=client.get(BASE+'/intelligence/voyage-exposure',headers=oh).json()['relations']
    assert all(r['status']=='NO_DEMONSTRATED_EXPOSURE' and not r['calculable'] for r in foreign)
    assert client.get(BASE+'/decisions/problems/'+p['decisionId'],headers=oh).status_code==404
    client.close();resources.cache_clear()


def test_multiasset_declarations_preserve_unrelated_approval_but_guard_same_asset(tmp_path,monkeypatch,queue_clock):
    store,client,token,h,items,declared,p=declared_comparison(tmp_path,monkeypatch)
    cp=BASE+'/decisions/problems/'+p['decisionId'];choice=next(o['optionId'] for o in p['options'] if not o['isBaseline'])
    step(client,cp,h,'REVIEWED');step(client,cp,h,'APPROVED',choice)
    original_plan=declared['plan'];original_episode=original_plan['operationalEpisode']
    # Second asset, same destination-arrival reference: no consumed dependency changed.
    second={**plan(),'noticeId':items[1]['noticeId'],'areaId':items[1]['areaId'],
        'passageAt':'2026-10-17T13:00:00Z','postPassageHours':179}
    r=client.post(BASE+'/intelligence/navigation-passage-plan',headers=h,json=second);assert r.status_code==200,r.text
    assert r.json()['plan']['operationalEpisode']==original_episode
    world=store.read(token)
    assert world['fleet'][0]['declaredPassages'][original_plan['areaId']]==original_plan
    assert world['terminalProposal']['decisionId']==p['decisionId']
    resources.cache_clear();store.switch(token,'PORT_AUTHORITY')
    review=client.post(BASE+'/decisions/current-proposals/review',headers=h,json={'decisionId':p['decisionId']})
    assert review.status_code==200,review.text
    pp=BASE+'/decisions/problems/'+review.json()['decisionId'];step(client,pp,h,'REVIEWED')
    # Same asset and same overall ETA, but changed passage request invalidates approval.
    store.switch(token,'SHIPPING_COMPANY')
    changed={**plan(),'noticeId':items[0]['noticeId'],'passageAt':'2026-10-17T12:30:00Z','postPassageHours':179.5}
    r=client.post(BASE+'/intelligence/navigation-passage-plan',headers=h,json=changed);assert r.status_code==200,r.text
    assert r.json()['plan']['id']!=original_plan['id']
    store.switch(token,'PORT_AUTHORITY')
    blocked=client.post(pp+'/transition',headers=h,json={'target':'APPROVED','optionId':choice})
    assert blocked.status_code==409 and 'passage declaration has changed' in blocked.text
    store.switch(token,'SHIPPING_COMPANY')
    assert client.get(cp,headers=h).json()['evidence']['intelligenceBasis']['restriction']['plan']==original_plan
    client.close();resources.cache_clear()


def test_identical_declaration_retries_and_new_call_clear_all_current_passages(tmp_path,monkeypatch,queue_clock):
    store,client,token,h,items,declared,p=declared_comparison(tmp_path,monkeypatch)
    body={**plan(),'noticeId':items[0]['noticeId']}
    retried=client.post(BASE+'/intelligence/navigation-passage-plan',headers=h,json=body)
    assert retried.status_code==200 and retried.json()==declared
    assert len(store.read(token)['passagePlanHistory'])==1
    created=client.post(BASE+'/intelligence/operational-calls',headers=h,json={'vesselId':'PWD-001',
        'requestedArrival':(NOW+timedelta(days=9)).isoformat(),'requestId':'new-rolling-call','newCallConfirmed':True})
    assert created.status_code==200,created.text
    world=store.read(token);assert not world['fleet'][0].get('declaredPassages') and not world['fleet'][0].get('declaredPassage')
    assert len(world['passagePlanHistory'])==1
    assert client.get(BASE+'/decisions/problems/'+p['decisionId'],headers=h).json()['evidence']['intelligenceBasis']['operationalEpisode']!=created.json()['episode']
    client.close();resources.cache_clear()


def test_possible_passage_lead_is_owned_idempotent_and_does_not_change_approved_plan(tmp_path,monkeypatch,queue_clock):
    store,client,token,h,items,declared,p=declared_comparison(tmp_path,monkeypatch)
    cp=BASE+'/decisions/problems/'+p['decisionId'];choice=next(o['optionId'] for o in p['options'] if not o['isBaseline'])
    step(client,cp,h,'REVIEWED');step(client,cp,h,'APPROVED',choice)
    before=store.read(token)
    payload={'vesselId':'PWD-001','noticeId':items[1]['noticeId'],'possible':True}
    result=client.post(BASE+'/intelligence/exposure-lead',headers=h,json=payload)
    assert result.status_code==200,result.text
    assert result.json()['exposure']['status']=='POSSIBLE_EXPOSURE' and not result.json()['createsOperationalTarget']
    assert client.post(BASE+'/intelligence/exposure-lead',headers=h,json=payload).json()==result.json()
    after=store.read(token)
    for key in ('etaHours','declaredPassage','declaredPassages','operationalEpisode'):
        assert before['fleet'][0].get(key)==after['fleet'][0].get(key)
    assert before['terminalProposal']==after['terminalProposal']
    assert client.post(BASE+'/intelligence/exposure-lead',headers=h,json={**payload,'vesselId':'PRIVATE'}).status_code==404
    assert client.post(BASE+'/intelligence/exposure-lead',headers=h,json={**payload,'possible':False}).status_code==422
    store.switch(token,'PORT_AUTHORITY')
    assert client.post(BASE+'/intelligence/exposure-lead',headers=h,json=payload).status_code==403
    review=client.post(BASE+'/decisions/current-proposals/review',headers=h,json={'decisionId':p['decisionId']})
    assert review.status_code==200,review.text
    other=store.create('SHIPPING_COMPANY');oh={'Authorization':'Bearer '+other['accessToken']}
    own=client.get(BASE+'/intelligence/voyage-exposure?vesselId=PWD-001&noticeId='+items[1]['noticeId'],headers=h).json()
    foreign=client.get(BASE+'/intelligence/voyage-exposure?vesselId=PWD-001&noticeId='+items[1]['noticeId'],headers=oh).json()
    assert own['relations'][0]['status']=='POSSIBLE_EXPOSURE' and foreign['relations'][0]['status']=='NO_DEMONSTRATED_EXPOSURE'
    client.close();resources.cache_clear()
