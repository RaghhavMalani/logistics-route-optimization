"""Synthetic semantic/availability tests; not measured source accuracy."""
import copy
import pytest

from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.portwatch_os.learning import shared_feedback as feedback
from src.portwatch_os.learning import news_vintages as vintages


from tests.feedback_originals import NEWS_ORIGINAL, AUTHORITY_ORIGINAL, retain_test_originals

@pytest.fixture(autouse=True)
def _retained_news_originals(tmp_path):
    retain_test_originals(tmp_path)

T0 = '2026-10-10T10:00:00+00:00'
T1 = '2026-10-11T10:00:00+00:00'
T2 = '2026-10-12T10:00:00+00:00'
T3 = '2026-10-13T10:00:00+00:00'
T4 = '2026-10-14T10:00:00+00:00'


def body(value=10, *, version='v1', at=T0, document='wire:report-17', lineage='Wire A',
         period=None, kind='ANNOUNCEMENT', parent=None, parents=None):
    target = {'kind': kind, 'predicate': 'OPERATOR_REPORTED_VESSELS',
              'reportedPeriod': period if period is not None else
                  {'from': '2026-10-01', 'through': '2026-10-07', 'precision': 'DATE_ONLY'}}
    return {'kind': 'REPORTED_FACT', 'wording': f'Operator reports {value} vessels during the stated period',
        'value': value, 'entity': 'Canal A', 'geography': 'Canal A reporting area',
        'originAt': at, 'firstAvailableAt': at, 'publishedAt': None, 'target': target,
        'source': 'https://source.example/'+document, 'sourceVersion': version,
        'sourceLineageId': lineage, 'sourceReportId': document, 'sourceRevisionId': version,
        'eventKey': 'OPERATOR:VESSELS', 'eventReference': 'OPERATOR:VESSELS',
        'independenceKey': lineage, 'inputs': [], 'responseSha256': NEWS_ORIGINAL,
        'unit': 'vessels', 'aggregation': 'EXPLICIT_NEWS_TARGET',
        **({'supersedesClaimId': parent} if parent else {}),
        **({'supersedesClaimIds': parents} if parents is not None else {})}


def record(store, data):
    return feedback.claim(store, copy.deepcopy(data))


def authority(store, item, value=10, *, at=T3, **changes):
    return feedback.evidence(store, {'eventKey': item['eventKey'], 'eventReference':item.get('eventReference'),
        'entity': item['entity'], 'geography': item['geography'], 'target': item['target'],
        'source': 'https://authority.example/log', 'sourceVersion': 'authority:v1',
        'independenceKey': 'Independent operator', 'sourceLineageId': 'Independent operator',
        'firstAvailableAt': at, 'observedAt': at, 'unit': item['unit'], 'aggregation': item['aggregation'],
        'value': value, 'recordKind': 'AUTHORITY_RECORD', 'responseSha256': AUTHORITY_ORIGINAL, **changes})


def view(store, at=T4):
    return feedback.inspect(store, at)['newsAggregation']


def test_reported_value_does_not_change_event_but_distinct_period_does(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    a=record(store,body(10)); changed=record(store,body(11,version='v2',at=T1))
    next_period=record(store,body(10,period={'from':'2026-10-08','through':'2026-10-14','precision':'DATE_ONLY'}))
    ai, bi, ci=map(vintages.identity,(a,changed,next_period))
    assert ai['eventId']==bi['eventId'] and ai['targetId']==bi['targetId']
    assert ai['claimId']!=bi['claimId'] and ai['revisionId']!=bi['revisionId']
    assert ai['reportId']==bi['reportId']
    assert ci['eventId']!=ai['eventId'] and ci['targetId']!=ai['targetId']
    result=view(store)
    assert result['summary']['eventCount']==2
    assert result['summary']['independentTargets']==2
    assert result['summary']['excludedTargetCount']==1
    store.close()


def test_reversed_insertion_correction_reversion_and_restart_are_deterministic(tmp_path):
    first=body(10)
    second=body(11,version='v2',at=T1,parent=feedback.identifier(first))
    reverted=body(10,version='v3',at=T2,parent=feedback.identifier(second))
    results=[]
    for name, sequence in [('forward',[first,second,reverted]),('reverse',[reverted,second,first])]:
        path=tmp_path/(name+'.db'); store=SqliteLedgerStore(path)
        records=[record(store,item) for item in sequence]
        authority(store,records[0],10)
        before=view(store,T0)
        corrected=view(store,T1)
        final=view(store,T4)
        assert before['targets'][0]['activeClaimIds']==[feedback.identifier(first)]
        assert corrected['targets'][0]['activeClaimIds']==[feedback.identifier(second)]
        assert final['targets'][0]['activeClaimIds']==[feedback.identifier(reverted)]
        assert final['targets'][0]['verdict']=='CORROBORATED'
        assert final['summary']['independentTargets']==1
        assert final['summary']['reportCount']==1
        assert final['summary']['revisionCount']==3
        assert final['summary']['additionalRevisionCount']==2
        assert len(store.feedback('claim'))==3
        store.close(); store=SqliteLedgerStore(path)
        assert view(store,T4)==final
        results.append((before,corrected,final,feedback.reliability_version(store,T4)['newsSlices']))
        store.close()
    assert results[0]==results[1]


def test_syndicated_copies_count_reports_not_independent_targets(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    a=record(store,body())
    record(store,body(document='paper:wire-copy',at=T1))
    record(store,body(document='independent:report',lineage='Independent publisher',at=T1))
    authority(store,a)
    result=view(store)
    assert result['summary']['independentTargets']==1
    assert result['summary']['resolvedIndependentTargets']==1
    assert result['summary']['reportCount']==3
    assert result['summary']['revisionCount']==3
    assert len(result['targets'])==2  # Two declared reporting lineages, one event target.
    slices=feedback.reliability_version(store,T4)['newsSlices']
    wire=next(row for row in slices if row['context'][0]=='Wire A')
    assert wire['independentTargets']==1 and wire['reportCount']==2
    # A republisher's record derived from the original lineage cannot verify it.
    second_store=SqliteLedgerStore(tmp_path/'self.db'); report=record(second_store,body())
    authority(second_store,report,sourceLineageId='Wire A',independenceKey='Republisher')
    assert feedback.verify_news(second_store,report,T4)['verdict']=='UNRESOLVED'
    store.close(); second_store.close()


@pytest.mark.parametrize('same_revision',[False,True])
def test_conflicting_heads_excluded_until_explicit_correction(tmp_path,same_revision):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    a=record(store,body())
    b=record(store,body(11,version='v1' if same_revision else 'v2',at=T1))
    authority(store,a)
    result=view(store)
    assert result['summary']['independentTargets']==1
    assert result['summary']['resolvedIndependentTargets']==0
    assert result['targets'][0]['status']=='EXCLUDED'
    assert 'UNRESOLVED_SAME_TARGET_VALUE_CONFLICT' in result['targets'][0]['exclusionReasons']
    if same_revision: assert 'SAME_SOURCE_REVISION_CONFLICT' in result['targets'][0]['exclusionReasons']
    corrected=record(store,body(10,version='correction-v3',at=T2,parents=[a['id'],b['id']]))
    after=view(store)
    assert after['targets'][0]['status']=='ELIGIBLE'
    assert after['targets'][0]['activeClaimIds']==[corrected['id']]
    assert after['summary']['resolvedIndependentTargets']==1
    store.close()


@pytest.mark.parametrize('unknown',[{'from':'2026-10-01'}, {'from':'2026-10-01','through':'2026-10-07','precision':'UNKNOWN'},
    'UNKNOWN; article body unavailable'])
def test_unknown_period_never_becomes_a_verified_event(tmp_path,unknown):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    a=record(store,body(period=unknown));record(store,body(11,period=unknown,version='v2',at=T1))
    authority(store,a)
    assert feedback.verify_news(store,a,T4)['verdict']=='UNRESOLVED'
    result=view(store)
    assert result['summary']['eventCount']==0 and result['summary']['independentTargets']==0
    assert result['summary']['ambiguousClaimCount']==2
    assert all(row['targetId'] is None for row in result['claims'])
    assert 'AMBIGUOUS_PERIOD' in result['targets'][0]['exclusionReasons']
    store.close()


def test_equivalent_explicit_time_bounds_normalize_without_guessing_precision(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    a=record(store,body(period={'from':'2026-10-01T00:00:00Z','through':'2026-10-02T00:00:00Z'}))
    b=record(store,body(document='wire:copy',period={'from':'2026-10-01T05:30:00+05:30',
        'through':'2026-10-02T05:30:00+05:30','precision':'INSTANT'}))
    assert vintages.identity(a)['targetId']==vintages.identity(b)['targetId']
    authority(store,a)
    assert feedback.verify_news(store,b,T4)['verdict']=='CORROBORATED'
    date_only=record(store,body(document='date-only',period={'from':'2026-10-01','through':'2026-10-02'}))
    assert vintages.identity(a)['targetId']!=vintages.identity(date_only)['targetId']
    store.close()


def test_announcement_actual_and_cancellation_keep_distinct_truth_targets(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    announcement=record(store,body())
    actual=record(store,body(kind='ACTUAL_EVENT'))
    cancellation=record(store,body(kind='CANCELLATION',version='cancel-v2',at=T1))
    authority(store,announcement)
    authority(store,announcement,value=None,recordKind='CANCELLATION',cancelsSourceVersion=announcement['sourceVersion'])
    assert feedback.verify_news(store,announcement,T4)['verdict']=='CORROBORATED'
    assert feedback.verify_news(store,announcement,T4)['applicability']=='SUPERSEDED'
    assert feedback.verify_news(store,actual,T4)['verdict']=='UNRESOLVED'
    assert feedback.verify_news(store,cancellation,T4)['verdict']=='UNRESOLVED'
    result=view(store)
    assert result['summary']['eventCount']==1 and result['summary']['independentTargets']==3
    assert result['summary']['resolvedIndependentTargets']==1
    store.close()


@pytest.mark.parametrize('mutation,reason', [('period','CROSS_TARGET_SUPERSESSION'),('lineage','CROSS_LINEAGE_SUPERSESSION')])
def test_cross_target_or_lineage_supersession_cannot_erase_earlier_report(tmp_path,mutation,reason):
    public=SqliteLedgerStore(tmp_path/'public.db'); private=SqliteLedgerStore(tmp_path/'private.db')
    a=record(public,body());feedback.verify_news(public,a,T0)
    frozen=feedback.freeze_consumption(public,private,[a['id']],T0)
    changed=body(11,version='v2',at=T1,parent=a['id'])
    if mutation=='period': changed['target']['reportedPeriod']={'from':'2026-10-08','through':'2026-10-14'}
    else: changed['sourceLineageId']=changed['independenceKey']='Another wire'
    b=record(public,changed)
    result=view(public)
    original=next(row for row in result['targets'] if a['id'] in row['activeClaimIds'])
    rejected=next(row for row in result['targets'] if b['id'] in row['activeClaimIds'])
    assert original['status']=='ELIGIBLE' and reason in rejected['exclusionReasons']
    feedback.require_consumption(public,frozen,now=T2)
    assert private.feedback('consumption')[0]==frozen
    public.close();private.close()


def test_cycle_missing_parent_and_reverse_availability_are_inspectable_exclusions(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    for name,parent,version in [('A','B','a'),('B','A','b')]:
        raw=body(version=version,parent=parent);raw['id']=name
        store.append_feedback('claim',raw)  # Deliberate corrupt imported graph fixture.
    result=view(store)
    assert 'SUPERSESSION_CYCLE' in result['targets'][0]['exclusionReasons']
    assert result['summary']['resolvedIndependentTargets']==0
    store.close()
    store=SqliteLedgerStore(tmp_path/'missing.db')
    record(store,body(parent='not-retained'))
    assert 'SUPERSEDED_CLAIM_UNAVAILABLE_AS_OF' in view(store)['targets'][0]['exclusionReasons']
    store.close()
    store=SqliteLedgerStore(tmp_path/'availability.db')
    late=record(store,body(at=T2))
    record(store,body(11,at=T1,version='v2',parent=late['id']))
    assert 'SUPERSEDED_CLAIM_UNAVAILABLE_AS_OF' in view(store,T1)['targets'][0]['exclusionReasons']
    assert 'SUPERSESSION_PRECEDES_ORIGINAL_AVAILABILITY' in view(store,T4)['targets'][0]['exclusionReasons']
    store.close()


def test_future_correction_and_outcome_cannot_leak_into_prior_as_of(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    a=record(store,body()); before=view(store,T0)
    record(store,body(11,version='v2',at=T2,parent=a['id']))
    authority(store,a,at=T3)
    assert view(store,T0)==before
    assert len(feedback.inspect(store,T0)['claims'])==1
    assert view(store,T1)['summary']['resolvedIndependentTargets']==0
    assert view(store,T4)['targets'][0]['verdict']=='CONTRADICTED'
    store.close()


def test_frozen_consumption_ignores_copies_but_relevant_conflict_requires_successor(tmp_path):
    public=SqliteLedgerStore(tmp_path/'public.db'); private=SqliteLedgerStore(tmp_path/'private.db')
    a=record(public,body());feedback.verify_news(public,a,T0)
    frozen=feedback.freeze_consumption(public,private,[a['id']],T0)
    record(public,body(at=T1,document='syndicated-copy'))
    unrelated=body(at=T1,document='unrelated');unrelated['eventKey']=unrelated['eventReference']='OTHER:EVENT'
    record(public,unrelated)
    feedback.require_consumption(public,frozen,now=T1)
    b=record(public,body(11,version='v2',at=T2))
    with pytest.raises(ValueError,match='vintage/conflict changed'):
        feedback.require_consumption(public,frozen,now=T2)
    record(public,body(10,version='correction-v3',at=T3,parents=[a['id'],b['id']]))
    with pytest.raises(ValueError,match='claim revised'):
        feedback.require_consumption(public,frozen,now=T4)
    assert private.feedback('consumption')[0]==frozen
    public.close();private.close()


def test_legacy_headline_count_keys_remain_one_ambiguous_family_not_known_events(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    for count,at in [(133,T0),(135,T1)]:
        feedback.news_report(store,wording=f'CENTCOM reports {count} cumulative redirections',
            source='https://wire.example/rolling-report',source_version='snapshot-'+str(count),
            independence_key='Wire A',event_key='CENTCOM:HORMUZ:reported-redirections:'+str(count),
            entity='Strait of Hormuz',geography='Hormuz / Iranian-port blockade',
            target={'kind':'ANNOUNCEMENT','predicate':'CENTCOM_REPORTED_CUMULATIVE_REDIRECTIONS',
                    'reportedPeriod':'UNKNOWN; article reporting period unavailable'},
            first_available_at=at,published_at=None,response_sha256=NEWS_ORIGINAL,value=count,unit='vessels')
    result=view(store)
    assert len({row['eventFamilyId'] for row in result['claims']})==1
    assert result['summary']['independentTargets']==0 and result['summary']['eventCount']==0
    assert result['summary']['reportCount']==1 and result['summary']['revisionCount']==2
    assert feedback.inspect(store,T4)['newsIndependentEvents']==0
    store.close()


def test_reviewed_legacy_navcen_identity_adapts_without_rewriting_original(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    legacy={'kind':'REPORTED_FACT','wording':'Bridge held closed from 04:30 to 10:15 local',
        'value':True,'entity':'WRIGHTSVILLE_SR74','geography':'Atlantic Intracoastal Waterway at Wrightsville Beach, North Carolina',
        'originAt':T0,'firstAvailableAt':T0,'source':'https://www.navcen.uscg.gov/sites/default/files/msi/bridge_1.geojson',
        'sourceVersion':'retained-legacy-revision','responseSha256':NEWS_ORIGINAL,
        'target':{'kind':'ANNOUNCEMENT','from':'2026-10-17T08:30:00+00:00','through':'2026-10-17T14:15:00+00:00',
                  'timeZoneBasis':'OPERATOR_CONFIRMED_GEOGRAPHIC_ASSUMPTION'},
        'eventKey':'USCG MSI #53842:2026-10-17:WRIGHTSVILLE_SR74','independenceKey':'USCG NAVCEN',
        'inputs':[],'unit':'boolean','aggregation':'EXPLICIT_NOTICE_WINDOW','reviewedSourceFamily':'NAVCEN_MSI_53842'}
    a=record(store,legacy)
    upgraded=copy.deepcopy(legacy)
    upgraded.update(eventReference='NAVCEN_MSI:53842:WRIGHTSVILLE_SR74',eventKey='NAVCEN_MSI:53842:WRIGHTSVILLE_SR74',
        sourceLineageId='USCG NAVCEN',sourceReportId='NAVCEN_MSI:53842',sourceRevisionId='new-extraction-revision',
        sourceVersion='new-extraction-revision',reviewedSourceFamily='NAVCEN_MSI_REVIEWED_FAMILY',
        supersedesClaimId=a['id'],originAt=T1,firstAvailableAt=T1)
    upgraded['target']['precision']='MINUTE'
    b=record(store,upgraded)
    assert vintages.identity(a)['targetId']==vintages.identity(b)['targetId']
    authority(store,a,value=True)
    assessment=feedback.verify_news(store,b,T4)
    assert assessment['verdict']=='UNRESOLVED'
    assert 'UNQUALIFIED_LEGACY_PREDICATE' in assessment['exclusionReasons']
    result=view(store)
    assert result['summary']['independentTargets']==1 and result['summary']['reportCount']==1
    assert result['summary']['revisionCount']==2
    assert result['targets'][0]['status']=='EXCLUDED'
    assert result['targets'][0]['activeClaimIds']==[b['id']]
    assert store.feedback('claim',a['id'])[0]==a
    assert 'eventReference' not in store.feedback('claim',a['id'])[0]
    store.close()


def test_explicit_source_revision_lineage_is_order_independent_and_period_scoped(tmp_path):
    old=body(10,version='provider-v1')
    changed=body(11,version='provider-v2',at=T1)
    changed['sourcePreviousRevisionId']='provider-v1'
    reverted=body(10,version='provider-v3',at=T2)
    reverted['sourcePreviousRevisionId']='provider-v2'
    snapshots=[]
    for name,sequence in [('forward',[old,changed,reverted]),('reverse',[reverted,changed,old])]:
        store=SqliteLedgerStore(tmp_path/(name+'.db'))
        made=[record(store,item) for item in sequence]
        authority(store,made[0])
        result=view(store,T4)
        assert result['targets'][0]['status']=='ELIGIBLE'
        assert result['targets'][0]['activeClaimIds']==[feedback.identifier(reverted)]
        snapshots.append(result)
        store.close()
    assert snapshots[0]==snapshots[1]
    store=SqliteLedgerStore(tmp_path/'other-period.db')
    a=record(store,old)
    next_period=copy.deepcopy(changed)
    next_period['target']['reportedPeriod']={'from':'2026-10-08','through':'2026-10-14','precision':'DATE_ONLY'}
    b=record(store,next_period)
    result=view(store)
    assert result['summary']['independentTargets']==2
    assert {row['status'] for row in result['targets']}=={'ELIGIBLE'}
    assert sorted(cid for row in result['targets'] for cid in row['activeClaimIds'])==sorted([a['id'],b['id']])
    store.close()


def test_future_parent_cannot_change_an_earlier_revision_view(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    future_parent=body(10,at=T2)
    record(store,body(11,at=T1,version='v2',parent=feedback.identifier(future_parent)))
    before=view(store,T1)
    record(store,future_parent)
    assert view(store,T1)==before
    store.close()


def test_inspection_hides_future_outcomes_matches_and_scores_without_deleting_them(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    report=record(store,body())
    authority(store,report,at=T3)
    from src.portwatch_os.learning import intelligence_reconciliation as collector
    quote=collector.collect_fx(store,b'observation_date,DEXINUS\n2026-10-09,96.31\n',T0,tmp_path)[0]
    forecast=feedback.freeze_fx(store,quote,T0,target_date='2026-10-12')
    collector.collect_fx(store,b'observation_date,DEXINUS\n2026-10-09,96.31\n2026-10-12,97.31\n',T4,tmp_path)
    outcome=next(e for e in store.feedback('evidence') if e['eventKey']==forecast['eventKey'])
    assert feedback.reconcile(store,T4)[0]==1
    earlier=feedback.inspect(store,T1)
    shown={c['id']:c for c in earlier['claims']}
    assert shown[report['id']]['outcomes']==[]
    hidden=shown[forecast['id']]
    assert hidden['outcomes']==[] and hidden['match'] is None
    assert hidden['score']=={'status':'open','observed':None,'error':None,'absoluteError':None,'availableAt':None}
    assert {row['kind'] for row in hidden['inspectionExclusions']}=={'OUTCOME','SCORE'}
    later={c['id']:c for c in feedback.inspect(store,T4)['claims']}[forecast['id']]
    assert later['outcomes'][0]['id']==outcome['id']
    assert later['match']['evidenceId']==outcome['id']
    assert later['score']['observed']==97.31 and later['score']['status']=='resolved'
    assert store.get_prediction(forecast['id']).status=='resolved'
    assert store.feedback('evidence',outcome['id'])[0]==outcome
    store.close()
