"""Retained public MSI parser replay and synthetic workflows, not accuracy data."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import copy
import hashlib
import json
import pytest
from tests.test_demo_terminal import setup, resources
from tests.test_current_recovery import step, BASE
from src.portwatch_os.intelligence import navigation_restrictions as n
from src.portwatch_os.learning import intelligence_reconciliation as collector
from src.portwatch_os.learning import shared_feedback as f
from src.portwatch_os.ledger.store import SqliteLedgerStore

RAW=Path(__file__).parent/'fixtures/navigation_restrictions/navcen-msi-20261014.geojson'
NOW=datetime(2026,10,14,10,tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def scripted_clock(monkeypatch):
    from src.portwatch_os import clock
    from backend.app.services import demo_store
    original=clock.WorldClock.__init__
    def initialize(self,*,wall=None): original(self,wall=wall or (lambda:NOW))
    monkeypatch.setattr(clock.WorldClock,'__init__',initialize)
    monkeypatch.setattr(clock,'_CLOCK',clock.WorldClock())
    monkeypatch.setattr(demo_store,'utc_now',lambda:NOW)
    resources.cache_clear();yield;resources.cache_clear()


def retained(tmp_path,monkeypatch):
    raw=RAW.read_bytes(); facts=n.parse(raw); digest=hashlib.sha256(raw).hexdigest()
    root=tmp_path/'sources';folder=root/'operational_notices';folder.mkdir(parents=True,exist_ok=True)
    (folder/(digest+'.response')).write_bytes(raw)
    source={**facts,'source':n.SOURCE,'revisionId':f.identifier(facts),'responseSha256':digest,
        'availableAt':NOW.isoformat(),'checkedAt':NOW.isoformat(),'sourceStatus':'CURRENT'}
    monkeypatch.setattr(n,'ROOT',root);monkeypatch.setattr(n,'refresh',lambda *a,**k:copy.deepcopy(source))
    return source


def plan():
    return {'vesselId':'PWD-001','areaId':n.AREA_ID,'route':[n.AREA_ID,'INNSA'],
        'passageAt':'2026-10-17T12:00:00Z','postPassageHours':180,
        'openingRequired':True,'emergencyTransit':False,'timezoneAssumption':'America/New_York',
        'passageConfirmed':True,'characteristics':{'loaM':70,'beamM':12,'draughtM':3,'airDraughtM':9}}


def test_reviewed_original_clock_precision_exemption_and_consequence():
    notice={**n.parse(RAW.read_bytes()),'sourceStatus':'CURRENT'}
    assert notice['windows'][0]['start']=='2026-10-17T08:30:00+00:00'
    assert notice['windows'][0]['end']=='2026-10-17T14:15:00+00:00'
    assert notice['publishedAt'] is None and 'ASSUMPTION' in notice['windows'][0]['timeZoneBasis']
    result=n.planned_consequence(notice,plan())
    assert result['calculatedWaitHours']==2.25 and result['actualEarliestPermittedAccess'] is None
    for delta in ({'areaId':'INNSA'},{'route':['INNSA']},{'openingRequired':False},
        {'emergencyTransit':True},{'timezoneAssumption':'UTC'}, {'passageAt':'2026-10-17T14:15:00Z'}):
        with pytest.raises(ValueError): n.planned_consequence(notice,{**plan(),**delta})
    changed=json.loads(RAW.read_bytes())
    feature=next(x for x in changed['features'] if x['properties']['MSI_UID']==n.FEATURE_ID)
    feature['properties']['DESCRIPTION']='General construction with no explicit operating restriction'
    with pytest.raises(ValueError,match='semantics'):n.parse(json.dumps(changed).encode())
    feature['properties']['STATUS']='Cancelled'
    assert n.parse(json.dumps(changed).encode())['status']=='CANCELLED'
    changed['features'].remove(feature)
    with pytest.raises(ValueError,match='absence is not cancellation'):n.parse(json.dumps(changed).encode())


def test_collector_receipts_revisions_cancellation_and_independent_confirmation(tmp_path,monkeypatch):
    source=retained(tmp_path,monkeypatch); store=SqliteLedgerStore(tmp_path/'ledger.db')
    claims=collector.collect_navigation(store,source);collector.collect_navigation(store,source)
    assert len(store.feedback('claim'))==2
    assert all(f.current_assessment(store,c)['verdict']=='UNRESOLVED' for c in claims)
    announcement=next(c for c in claims if c['target']['kind']=='ANNOUNCEMENT')
    actual=next(c for c in claims if c['target']['kind']=='ACTUAL_EVENT')
    authority={'eventKey':announcement['eventKey'],'entity':announcement['entity'],'geography':announcement['geography'],
        'target':announcement['target'],'source':'Synthetic independent operator authority fixture','sourceVersion':'fixture-v1',
        'independenceKey':'Independent operator','firstAvailableAt':(NOW+timedelta(minutes=1)).isoformat(),
        'observedAt':NOW.isoformat(),'unit':'boolean','aggregation':'EXPLICIT_NOTICE_WINDOW','value':True,
        'recordKind':'OPERATOR_RECORD','responseSha256':'b'*64}
    f.evidence(store,authority)
    assert f.verify_news(store,announcement,(NOW+timedelta(minutes=2)).isoformat())['verdict']=='CORROBORATED'
    assert f.verify_news(store,actual,(NOW+timedelta(minutes=2)).isoformat())['verdict']=='UNRESOLVED'
    # A syndicated/derived copy cannot confirm the authority's own report.
    f.evidence(store,{**authority,'independenceKey':'USCG NAVCEN','derivedFrom':'USCG NAVCEN','value':False})
    assert f.verify_news(store,announcement,(NOW+timedelta(minutes=2)).isoformat())['verdict']=='CORROBORATED'
    revision={**source,'revisionId':'new-reviewed-version','previousRevisionId':source['revisionId'],
        'availableAt':(NOW+timedelta(minutes=3)).isoformat()}
    newer=collector.collect_navigation(store,revision)
    assert {c['supersedesClaimId'] for c in newer}=={c['id'] for c in claims}
    cancelled={**source,'status':'CANCELLED','revisionId':'cancellation-v1','availableAt':(NOW+timedelta(minutes=4)).isoformat()}
    collector.collect_navigation(store,cancelled)
    assessment=f.current_assessment(store,announcement)
    assert assessment['verdict']=='CORROBORATED' and assessment['applicability']=='SUPERSEDED'
    assert f.current_assessment(store,actual)['verdict']=='UNRESOLVED'
    assert len(store.feedback('claim'))==4
    store.close()


def test_originals_source_freshness_and_revision_blocking(tmp_path,monkeypatch):
    source=retained(tmp_path,monkeypatch);basis={'reportedFact':source,'restriction':{'revisionId':source['revisionId']}}
    n.require_revision(basis)
    for delta in ({'sourceStatus':'UNAVAILABLE'},{'status':'CANCELLED'},{'revisionId':'changed'},
        {'checkedAt':(NOW-timedelta(hours=7)).isoformat()},{'productThrough':(NOW-timedelta(seconds=1)).isoformat()}):
        monkeypatch.setattr(n,'refresh',lambda d=delta:{**source,**d})
        with pytest.raises(ValueError):n.require_revision(basis)
    monkeypatch.setattr(n,'refresh',lambda:source)
    (n.ROOT/'operational_notices'/(source['responseSha256']+'.response')).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='corrupt'):n.require_revision(basis)


def test_live_collector_retains_first_receipt_revisions_reversion_and_provider_failure(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from src.portwatch_os import clock
    # Use the actual environment key rather than allowing an implicit mode.
    from src.portwatch_os.fabric.model import MODE_ENV
    monkeypatch.setenv(MODE_ENV,'DEMO');monkeypatch.setattr(n,'ROOT',tmp_path/'sources')
    content=[RAW.read_bytes()]
    monkeypatch.setattr(n.requests,'get',lambda *a,**k:SimpleNamespace(content=content[0],raise_for_status=lambda:None))
    first=n.refresh(force=True)
    assert first['sourceStatus']=='CURRENT'
    initial=first['availableAt']; revision=first['revisionId']
    monkeypatch.setattr(clock,'_CLOCK',clock.WorldClock(wall=lambda:NOW+timedelta(hours=1)))
    same=n.refresh(force=True)
    assert same['revisionId']==revision and same['availableAt']==initial and same['checkedAt']!=initial
    changed=json.loads(content[0]);feature=next(x for x in changed['features'] if x['properties']['MSI_UID']==n.FEATURE_ID)
    feature['properties']['DESCRIPTION']=feature['properties']['DESCRIPTION'].replace('10:15 a.m.','11:15 a.m.')
    content[0]=json.dumps(changed).encode(); second=n.refresh(force=True)
    assert second['revisionId']!=revision and second['previousRevisionId']==revision
    monkeypatch.setattr(clock,'_CLOCK',clock.WorldClock(wall=lambda:NOW+timedelta(hours=2)))
    content[0]=RAW.read_bytes();reversion=n.refresh(force=True)
    assert reversion['revisionId'] not in (revision,second['revisionId'])
    assert reversion['previousRevisionId']==second['revisionId'] and reversion['availableAt']!=initial
    def unavailable(*a,**k): raise n.requests.Timeout('Synthetic provider timeout')
    monkeypatch.setattr(n.requests,'get',unavailable)
    failed=n.refresh(force=True)
    assert failed['sourceStatus']=='UNAVAILABLE' and failed['revisionId']==reversion['revisionId']
    assert len(list((n.ROOT/'operational_notices').glob('*.response')))==2
    assert len((n.ROOT/'operational_notices/navcen-receipts.jsonl').read_text().splitlines())==5


def test_original_four_role_bridge_journey_frozen_recovery_isolation(tmp_path,monkeypatch):
    store,client=setup(tmp_path,monkeypatch);source=retained(tmp_path,monkeypatch)
    session=store.create('SHIPPING_COMPANY');token=session['accessToken'];h={'Authorization':'Bearer '+token}
    payload={'vesselId':'PWD-001','revisionId':source['revisionId']}
    assert client.post(BASE+'/intelligence/navigation-comparison',headers=h,json=payload).status_code==409
    r=client.post(BASE+'/intelligence/navigation-passage-plan',headers=h,json=plan());assert r.status_code==200,r.text
    episode=r.json()['plan']['operationalEpisode'];assert store.read(token)['fleet'][0]['operationalEpisode']==episode
    r=client.post(BASE+'/intelligence/navigation-comparison',headers=h,json=payload);assert r.status_code==200,r.text
    p=r.json();opts=p['options'];basis=p['evidence']['intelligenceBasis']
    assert [o['evaluation']['objectives']['eta']['value'] for o in opts]==[2.25,2.25]
    assert [o['evaluation']['objectives']['port_wait']['value'] for o in opts]==[2.25,0]
    assert all(o['evaluation']['objectives']['cost']['value'] is None for o in opts)
    assert p['evidence']['restrictionAsset']['lat']==pytest.approx(34.21828)
    assert all(all(isinstance(m['hours'],float) for m in o['timeline']) for o in opts)
    assert 'without faster delivery' in p['recommendation']['statement']
    cp=BASE+'/decisions/problems/'+p['decisionId'];choice=opts[1]['optionId']
    step(client,cp,h,'REVIEWED');step(client,cp,h,'APPROVED',choice);resources.cache_clear()
    assert client.get(cp,headers=h).json()['evidence']['intelligenceBasis']==basis
    store.switch(token,'PORT_AUTHORITY')
    r=client.post(BASE+'/decisions/current-proposals/review',headers=h,json={'decisionId':p['decisionId']});assert r.status_code==200,r.text
    port=r.json();pp=BASE+'/decisions/problems/'+port['decisionId']
    assert port['evidence']['intelligenceBasis']['operationalEpisode']==episode
    step(client,pp,h,'REVIEWED');step(client,pp,h,'APPROVED',choice);resources.cache_clear()
    r=client.post(pp+'/handoff',headers=h,json={});assert r.status_code==200,r.text
    rows=r.json()['advisories'];assert client.post(pp+'/handoff',headers=h,json={}).json()['advisories']==rows
    ap=BASE+'/advisories/'+rows[0]['advisoryId'];step(client,ap,h,'under_review');step(client,ap,h,'issued');resources.cache_clear()
    store.switch(token,'VESSEL_OPERATOR');step(client,ap,h,'acknowledged');step(client,ap,h,'accepted');resources.cache_clear()
    store.switch(token,'PORT_AUTHORITY');r=client.post(pp+'/demo-outcome',headers=h,json={});assert r.status_code==200,r.text
    assert r.json()['outcome']['recordKind']=='SIMULATED_DEMO_OUTCOME'
    assert r.json()['outcome']['totalScheduleShiftHours']==2.25
    assert client.post(pp+'/demo-outcome',headers=h,json={}).json()==r.json()
    impacts=client.get(BASE+'/intelligence/feedback/impacts',headers=h).json()
    assert impacts['claims'] and not impacts['reliability']['sampleIds']
    store.switch(token,'NATIONAL_ADMIN');assert client.get(BASE+'/intelligence/navigation-restrictions',headers=h).status_code==200
    other=store.create('SHIPPING_COMPANY');oh={'Authorization':'Bearer '+other['accessToken']}
    assert client.get(cp,headers=oh).status_code==404
    assert not client.get(BASE+'/intelligence/feedback/impacts',headers=oh).json()['claims']
    client.close()
