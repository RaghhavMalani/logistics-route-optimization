"""Isolated archived-report software tests; no current-source accuracy claim."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import copy,json,hashlib
from unittest.mock import Mock
import pytest
from src.portwatch_os.intelligence import public_ports as p,public_port_context as c,port_context_review as review

RAW=(Path(__file__).parent/'fixtures/public_ports/paradip-2026-10-06.pdf').read_bytes()
URL='https://www.paradipport.gov.in/uploads/2026/10/dtr0610.pdf'
NOW=datetime(2026,10,6,12,tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path,monkeypatch):
    monkeypatch.setattr('src.portwatch_os.clock.wall_now',lambda:NOW)
    monkeypatch.setattr(p,'fetch',lambda url:b'<a href="'+URL.encode()+b'">Daily</a>' if url==p.PARADIP_INDEX else RAW)
    pilot=p.PublicPilot(tmp_path);pilot.refresh('INPRT','Labelled software fixture',report_limit=1)
    yield pilot
    pilot.close()


def test_reviewed_sections_keep_clock_and_metric_meanings():
    data=c.extract(RAW);metrics={m['id']:m for m in data['metrics']}
    assert data['reportDate']=='2026-10-06' and data['priorDayTrafficDate']=='2026-10-05'
    assert metrics['WORKING_LISTED_ROWS']['value']==21 and metrics['WORKING_LISTED_ROWS']['asOf']=='2026-10-06T00:30:00.000000Z'
    # This older layout contains a separate no-cargo heading without an
    # explicitly reviewed readiness category. The stricter parser withholds it.
    assert metrics['ANCHORAGE_READY_ROWS']['value'] is None and data['issues']
    legacy=c.extract(RAW,strict=False)
    assert legacy['metrics'][2]['value']==7 and legacy['metrics'][3]['value']==10
    assert 'asOf' not in metrics['ANCHORAGE_LISTED_ROWS'] and metrics['ANCHORAGE_LISTED_ROWS']['precision']=='DATE_ONLY'
    assert data['publicationAt'] is None


def test_original_first_receipt_and_prospective_cases_unchanged_on_supplemental_parse(store,monkeypatch):
    before=store.workspace('INPRT',NOW)
    a=c.retained(root=store.root,as_of=NOW)
    assert a['status']=='CURRENT_ELIGIBLE' and a['firstReceivedAt']==p.stamp(NOW)
    monkeypatch.setattr('src.portwatch_os.clock.wall_now',lambda:NOW+timedelta(minutes=5))
    store.refresh('INPRT','Repeat identical fixture',report_limit=1)
    b=c.retained(root=store.root,as_of=NOW+timedelta(minutes=5))
    assert b['revisionId']==a['revisionId'] and b['availableAt']==a['availableAt']
    after=store.workspace('INPRT',NOW+timedelta(minutes=5))
    assert before['cases']==after['cases'] and before['snapshots']==after['snapshots']


def test_fresh_old_download_cannot_qualify_and_sections_age_independently(store,monkeypatch):
    later=NOW+timedelta(hours=20)
    monkeypatch.setattr('src.portwatch_os.clock.wall_now',lambda:later)
    store.refresh('INPRT','Later current check',report_limit=1)
    result=c.retained(root=store.root,as_of=later)
    metrics={m['id']:m for m in result['metrics']}
    assert result['status']=='CURRENT_ELIGIBLE'
    assert metrics['WORKING_LISTED_ROWS']['eligibility']=='CURRENT_ELIGIBLE'
    assert metrics['ANCHORAGE_READY_ROWS']['eligibility']=='LATEST_AVAILABLE'
    old=NOW+timedelta(days=8)
    monkeypatch.setattr('src.portwatch_os.clock.wall_now',lambda:old)
    store.refresh('INPRT','New receipt of old data',report_limit=1)
    assert c.retained(root=store.root,as_of=old)['status']=='LATEST_AVAILABLE'


def test_failure_retains_last_good_and_future_parse_is_unavailable(store,monkeypatch):
    original=c.retained(root=store.root,as_of=NOW)
    assert c.retained(root=store.root,as_of=NOW-timedelta(seconds=1))['metrics']==[]
    monkeypatch.setattr('src.portwatch_os.clock.wall_now',lambda:NOW+timedelta(minutes=1))
    monkeypatch.setattr(p,'fetch',Mock(side_effect=TimeoutError('Synthetic unavailable source')))
    store.refresh('INPRT','Failure fixture',report_limit=1)
    later=c.retained(root=store.root,as_of=NOW+timedelta(minutes=2))
    assert later['status']=='RETAINED_AFTER_FAILURE' and later['snapshotId']==original['snapshotId']
    assert later['firstReceivedAt']==original['firstReceivedAt']


def test_read_uses_existing_committed_wal_and_has_no_constructor_or_network_side_effect(store,monkeypatch):
    store.db.execute('PRAGMA journal_mode=WAL')
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in store.root.rglob('*') if p.is_file() and not str(p).endswith(('-wal','-shm'))}
    monkeypatch.setattr(p.PublicPilot,'__init__',Mock(side_effect=AssertionError('GET must not construct')))
    monkeypatch.setattr(p,'fetch',Mock(side_effect=AssertionError('GET must not fetch')))
    assert c.retained(root=store.root,as_of=NOW)['status']=='CURRENT_ELIGIBLE'
    after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in store.root.rglob('*') if p.is_file() and not str(p).endswith(('-wal','-shm'))}
    assert before==after


def test_corrupt_original_or_derived_metric_withholds_actions(store):
    current=c.retained(root=store.root,as_of=NOW);path=store.root/'evidence'/(current['originalSha256']+'.pdf')
    path.write_bytes(b'corrupt')
    result=c.retained(root=store.root,as_of=NOW)
    assert result['originalStatus']=='UNAVAILABLE' and all(m['eligibility']!='CURRENT_ELIGIBLE' for m in result['metrics'])


def test_material_metric_rule_changes_separate_from_unrelated_context(store):
    data=c.retained(root=store.root,as_of=NOW)
    rule={'id':'rule','vesselId':'PWD-001','portCode':'INPRT','episodeId':'call','metricId':'WORKING_LISTED_ROWS','threshold':20}
    world={'fleet':[{'id':'PWD-001','portCode':'INPRT','operationalEpisode':{'id':'call'}}],'portContextRules':{'PWD-001':rule}}
    binding={'id':'binding','revisionId':data['revisionId'],'availableAt':data['availableAt'],'metric':data['metrics'][0],'rule':rule,'policyVersion':data['policyVersion']}
    assert review.assess([binding],world,data,at=NOW)==[]
    unused=copy.deepcopy(data);unused['metrics'][1]['value']=999
    assert review.assess([binding],world,unused,at=NOW)==[]
    changed=copy.deepcopy(data);changed['metrics'][0]['value']+=1
    findings=review.assess([binding],world,changed,at=NOW)
    assert findings[0]['changes'][0]['field']=='metricValue' and binding['metric']['value']==21


def test_byte_revision_reversion_has_new_availability_without_rewriting_original(store,monkeypatch):
    first=c.retained(root=store.root,as_of=NOW)
    for minute,raw in [(1,RAW+b'\n% explicitly labelled software revision\n'),(2,RAW)]:
        monkeypatch.setattr('src.portwatch_os.clock.wall_now',lambda m=minute:NOW+timedelta(minutes=m))
        monkeypatch.setattr(p,'fetch',lambda url,payload=raw:b'<a href="'+URL.encode()+b'">Daily</a>' if url==p.PARADIP_INDEX else payload)
        store.refresh('INPRT','Software revision/reversion test',report_limit=1)
        current=c.retained(root=store.root,as_of=NOW+timedelta(minutes=minute))
        assert current['revisionId']!=first['revisionId']
        if minute==1:second=current
    assert current['previousRevisionId']==second['revisionId'] and current['originalSha256']==first['originalSha256']
    assert current['firstReceivedAt']==first['firstReceivedAt'] and current['availableAt']!=first['availableAt']
    assert c.retained(root=store.root,as_of=NOW+timedelta(minutes=1))['revisionId']==second['revisionId']


def test_malformed_database_is_unknown_and_does_not_repair_or_write(tmp_path):
    path=tmp_path/'public_ports.db';path.write_bytes(b'broken test database')
    assert c.retained(root=tmp_path,as_of=NOW)['status']=='UNAVAILABLE'
    assert path.read_bytes()==b'broken test database'


def test_new_unsupported_context_parse_cannot_refresh_prior_eligibility(store,monkeypatch):
    old=c.retained(root=store.root,as_of=NOW)
    monkeypatch.setattr('src.portwatch_os.clock.wall_now',lambda:NOW+timedelta(minutes=5))
    monkeypatch.setattr(c,'extract',Mock(side_effect=ValueError('Explicit unsupported software layout')))
    store.refresh('INPRT','Unsupported section software test',report_limit=1)
    result=c.retained(root=store.root,as_of=NOW+timedelta(minutes=5))
    assert result['status']=='RETAINED_AFTER_UNSUPPORTED_PARSE'
    assert result['lastSuccessfulCheckAt']==old['lastSuccessfulCheckAt']
    assert result['snapshotId']==old['snapshotId'] and all(m['eligibility']!='CURRENT_ELIGIBLE' for m in result['metrics'])
