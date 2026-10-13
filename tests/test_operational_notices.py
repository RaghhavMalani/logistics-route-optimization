"""Real notice parsing and software workflow fixtures; no measured outcome claim."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import copy
import hashlib
import json
import pytest
from tests.test_demo_terminal import setup, resources
from tests.test_current_recovery import step, BASE
from src.portwatch_os.intelligence import operational_notices as notices

FIXTURE=Path(__file__).parent/'fixtures/operational_notices/eastham-2026-18.pdf'
FIXTURE_NOW=datetime(2026,10,12,15,tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def scripted_fixture_clock(monkeypatch):
    """Keep this dated authority example valid without weakening live expiry."""
    from src.portwatch_os import clock
    from backend.app.services import demo_store
    original_init=clock.WorldClock.__init__
    def initialize(self, *, wall=None):
        original_init(self,wall=wall or (lambda:FIXTURE_NOW))
    monkeypatch.setattr(clock.WorldClock,'__init__',initialize)
    monkeypatch.setattr(clock,'_CLOCK',clock.WorldClock())
    monkeypatch.setattr(demo_store,'utc_now',lambda:FIXTURE_NOW)
    resources.cache_clear()
    yield
    resources.cache_clear()


def retained(tmp_path,monkeypatch):
    raw=FIXTURE.read_bytes(); root=tmp_path/'sources'; folder=root/'operational_notices';folder.mkdir(parents=True)
    sha=hashlib.sha256(raw).hexdigest();(folder/(sha+'.response')).write_bytes(raw)
    parsed=notices.parse_eastham(raw)
    now=FIXTURE_NOW
    revision=hashlib.sha256(json.dumps(parsed,sort_keys=True).encode()).hexdigest()
    source={**parsed,'revisionId':revision,'id':revision,'availableAt':now.isoformat(),'checkedAt':now.isoformat(),
        'sourceStatus':'CURRENT','responseSha256':sha,'pdfSha256':sha,'source':notices.SOURCE,'pdfSource':notices.PDF}
    monkeypatch.setattr(notices,'ROOT',root);monkeypatch.setattr(notices,'refresh',lambda *a,**k:copy.deepcopy(source))
    return source


def plan_payload():
    return {'vesselId':'PWD-001','areaId':'EASTHAM_80_LOCK','direction':'OUTBOUND','passageAt':'2026-10-15T11:00:00Z',
        'postPassageHours':180,'characteristics':{'loaM':140,'beamM':19,'draughtM':6,'airDraughtM':25},
        'alternativeAccess':'NOT_VERIFIED','declarationConfirmed':True}


def test_original_parse_timezones_and_contradiction():
    n=notices.parse_eastham(FIXTURE.read_bytes());assert n['publishedDate']=='2026-07-15'
    assert n['windows'][1]['firstOperationalTide']=='2026-10-16T01:42:00+00:00'
    assert not n['windows'][2]['calculationSupported']
    assert 'unaffected' in n['unaffectedAlternative']
    p={**plan_payload(),'alternativeAccess':'NOT_VERIFIED'}
    c=notices.planned_consequence({**n,'sourceStatus':'CURRENT'},p)
    assert c['calculatedWaitHours']==pytest.approx(14.7)
    assert c['actualEarliestPermittedAccess'] is None
    for delta in ({'areaId':'OTHER_LOCK'},{'direction':'OTHER'},{'passageAt':'2026-10-16T01:42:00Z'},
        {'alternativeAccess':'VERIFIED'},{'passageAt':'2026-11-18T12:00:00Z'}):
        with pytest.raises(ValueError): notices.planned_consequence({**n,'sourceStatus':'CURRENT'},{**p,**delta})


def test_construction_is_not_a_closure_and_explicit_cancellation(monkeypatch):
    from types import SimpleNamespace
    def reader(text): return lambda raw: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:text)])
    monkeypatch.setattr(notices,'PdfReader',reader('NOTICE TO MARINERS №18 – 2026 HARBOUR AND PORT OF MANCHESTER EASTHAM construction works only'))
    with pytest.raises(ValueError,match='Explicit restriction'): notices.parse_eastham(b'fixture')
    monkeypatch.setattr(notices,'PdfReader',reader('NOTICE TO MARINERS №18 – 2026 HARBOUR AND PORT OF MANCHESTER EASTHAM This notice has been cancelled'))
    assert notices.parse_eastham(b'fixture')['status']=='CANCELLED'


def test_restriction_originals_and_revisions_guarded(tmp_path,monkeypatch):
    source=retained(tmp_path,monkeypatch);basis={'reportedFact':source,'restriction':{'revisionId':source['revisionId']}}
    notices.require_revision(basis)
    for delta in ({'status':'CANCELLED'},{'sourceStatus':'UNAVAILABLE'},{'revisionId':'revised'}):
        monkeypatch.setattr(notices,'refresh',lambda d=delta:{**source,**d})
        with pytest.raises(ValueError): notices.require_revision(basis)
    monkeypatch.setattr(notices,'refresh',lambda:source)
    expired={**source,'checkedAt':(FIXTURE_NOW-timedelta(hours=7)).isoformat()}
    monkeypatch.setattr(notices,'refresh',lambda:expired)
    with pytest.raises(ValueError,match='expired'): notices.require_revision(basis)
    monkeypatch.setattr(notices,'refresh',lambda:source)
    (notices.ROOT/'operational_notices'/(source['pdfSha256']+'.response')).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='corrupt'): notices.require_revision(basis)


def test_connected_restriction_recovery_roles_isolation_and_retries(tmp_path,monkeypatch):
    store,client=setup(tmp_path,monkeypatch);source=retained(tmp_path,monkeypatch)
    session=store.create('SHIPPING_COMPANY');token=session['accessToken'];h={'Authorization':'Bearer '+token}
    body={'vesselId':'PWD-001','revisionId':source['revisionId']}
    assert client.post(BASE+'/intelligence/notice-comparison',headers=h,json=body).status_code==409
    for delta in ({'declarationConfirmed':False},{'characteristics':{'loaM':True}},{'vesselId':'private'}):
        assert client.post(BASE+'/intelligence/notice-passage-plan',headers=h,json={**plan_payload(),**delta}).status_code in (404,422)
    response=client.post(BASE+'/intelligence/notice-passage-plan',headers=h,json=plan_payload());assert response.status_code==200,response.text
    response=client.post(BASE+'/intelligence/notice-comparison',headers=h,json=body);assert response.status_code==200,response.text
    company=response.json();basis=company['evidence']['intelligenceBasis'];options=company['options']
    assert basis['kind']=='NOTICE_RESTRICTION' and basis['reportedFact']['pdfSha256']==source['pdfSha256']
    assert [o['evaluation']['objectives']['eta']['value'] for o in options]==[14.7,14.7]
    assert [o['evaluation']['objectives']['port_wait']['value'] for o in options]==[14.7,0]
    assert all(o['evaluation']['objectives']['cost']['value'] is None for o in options)
    assert all(o['evaluation']['derived']['actualEarliestPermittedAccess'] is None for o in options)
    assert all(o['evaluation']['derived']['earliestScheduledAccess']=='2026-10-16T01:42:00+00:00' for o in options)
    cp=BASE+'/decisions/problems/'+company['decisionId'];choice=options[1]['optionId']
    step(client,cp,h,'REVIEWED');step(client,cp,h,'APPROVED',choice);resources.cache_clear()
    assert client.get(cp,headers=h).json()['options']==options
    store.switch(token,'PORT_AUTHORITY')
    assert client.post(BASE+'/intelligence/notice-passage-plan',headers=h,json=plan_payload()).status_code==403
    response=client.post(BASE+'/decisions/current-proposals/review',headers=h,json={'decisionId':company['decisionId']});assert response.status_code==200,response.text
    port=response.json();pp=BASE+'/decisions/problems/'+port['decisionId'];step(client,pp,h,'REVIEWED');step(client,pp,h,'APPROVED',choice);resources.cache_clear()
    handoff=client.post(pp+'/handoff',headers=h,json={});assert handoff.status_code==200,handoff.text
    rows=handoff.json()['advisories'];assert client.post(pp+'/handoff',headers=h,json={}).json()['advisories']==rows
    ap=BASE+'/advisories/'+rows[0]['advisoryId'];step(client,ap,h,'under_review');step(client,ap,h,'issued')
    store.switch(token,'VESSEL_OPERATOR');step(client,ap,h,'acknowledged');step(client,ap,h,'accepted');resources.cache_clear()
    store.switch(token,'PORT_AUTHORITY');done=client.post(pp+'/demo-outcome',headers=h,json={});assert done.status_code==200,done.text
    outcome=done.json()['outcome'];assert outcome['evidenceKind']=='restriction' and outcome['selectedAssumedWaitHours']==0
    assert outcome['totalScheduleShiftHours']==14.7 and outcome['calculation']==basis['restriction']
    assert client.post(pp+'/demo-outcome',headers=h,json={}).json()==done.json()
    other=store.create('PORT_AUTHORITY');assert client.get(pp,headers={'Authorization':'Bearer '+other['accessToken']}).status_code==404
    client.close()
