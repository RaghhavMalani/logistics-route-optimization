"""Synthetic identity/availability regressions; no real-world accuracy claim."""
from types import SimpleNamespace as NS
import pytest

from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.portwatch_os.learning import shared_feedback as f

ORIGIN='2026-10-13T10:00:00+00:00'
LATER='2026-10-20T10:00:00+00:00'


def problem(call, decision, *, origin=ORIGIN, value=0, port=False, arrival='2026-10-18T12:00:00+00:00', approved_at=None):
    episode={'id':call,'namespace':'private-visitor-A','voyageLegId':'leg-'+call,'vesselId':'vessel-A','portCode':'port-A'}
    option=NS(option_id=decision+'-keep', action='KEEP_PLAN', params={'arrivalAt':arrival},
              evaluation=NS(derived={'arrivalAt':arrival}, objectives={'eta':NS(value=value),'port_wait':NS(value=None)}))
    return NS(decision_id=decision, created_at=origin, subject_id='vessel-A', options=[option],
              workflow='APPROVED', workflow_history=[{'state':'APPROVED','at':approved_at or origin}], human_choice=option.option_id,
              evidence={'intelligenceBasis':{
                  'operationalEpisode':episode,'portCode':'port-A','plannedArrival':arrival,'availableAt':origin,
                  'evidenceId':'vintage-'+origin,'assumptions':{}}, **({'companyProposal':{'decisionId':'company'}} if port else {})})


def prediction(store, p):
    f.record_operational_targets(store,p)
    f.select_operational_targets(store,p)
    return next(c for c in store.feedback('claim') if c['target']['decisionId']==p.decision_id)


def actual(store,item,value, **changes):
    return f.evidence(store, {'eventKey':'actual-'+item['operationalEpisode']['id'],
        'target':{'kind':'SCHEDULE_SHIFT'}, 'entity':item['entity'],'geography':item['geography'],
        'source':'Synthetic independent operator log','sourceVersion':'fixture-v1','independenceKey':'Operator',
        'episodeId':item['operationalEpisode']['id'],'independentTargetKey':item['independentTargetKey'],
        'executedActionId':item['operationalActionId'],'forecastCutoffAt':'2026-10-16T12:00:00+00:00',
        'actionBasisSha256':item['actionBasisSha256'],'metricBasisSha256':item['metricBasisSha256'],
        'executedAt':'2026-10-17T12:00:00+00:00','observedAt':'2026-10-18T23:00:00+00:00',
        'firstAvailableAt':LATER,'unit':'hours','aggregation':'SELECTED_VOYAGE_OPTION','value':value,
        'recordKind':'ACTUAL_OPERATIONAL_RECORD','responseSha256':'b'*64, **changes})


def test_generated_identity_counts_distinct_calls_same_vessel_same_port(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    a=prediction(store,problem('call-A','decision-A'))
    b=prediction(store,problem('call-B','decision-B'))
    assert a['independentTargetKey'] != b['independentTargetKey']
    actual(store,a,1);actual(store,b,5)
    assert f.reconcile(store,LATER)==(2,0)
    view=f.reliability_version(store,'2026-10-21T00:00:00+00:00')
    assert view['slices'][0]['independentTargets']==2
    assert view['slices'][0]['meanAbsoluteError']==3
    store.close()


def test_copies_eta_edits_and_successors_share_episode_explicit_cutoff(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    a=prediction(store,problem('call-A','company',value=1))
    port=prediction(store,problem('call-A','port',value=1,port=True))
    successor=prediction(store,problem('call-A','successor',origin='2026-10-14T10:00:00+00:00',value=4))
    revised=prediction(store,problem('call-A','eta-edit',arrival='2026-10-19T12:00:00+00:00'))
    assert len({c['independentTargetKey'] for c in (a,port,successor,revised)})==1
    actual(store,a,5)
    # Same action identity is required. An ETA edit changes the action, not the call.
    assert revised['operationalActionId'] != a['operationalActionId']
    assert f.reconcile(store,LATER)[0]==3
    view=f.reliability_version(store,'2026-10-21T00:00:00+00:00')
    assert view['slices'][0]['independentTargets']==1
    assert view['slices'][0]['meanAbsoluteError']==1
    assert view['sampleIds']==[successor['id']]
    assert len(store.feedback('claim'))==4
    store.close()


@pytest.mark.parametrize('change',[{'executedActionId':'other-action'},{'episodeId':'other-call'},
    {'observedAt':'2026-10-18T12:00:00+00:00'},
    {'executedAt':None},{'forecastCutoffAt':'2026-10-12T00:00:00+00:00'},
    {'recordKind':'SIMULATED_DEMO_OUTCOME'}, {'actionBasisSha256':'c'*64},
    {'metricBasisSha256':'c'*64}, {'entity':'another-vessel'}, {'geography':'another-port'},
    {'target':{'kind':'WAITING'}}, {'unit':'minutes'}, {'aggregation':'ANCHORAGE_WAIT'}])
def test_approval_is_not_execution_and_simulation_cannot_settle(tmp_path,change):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    item=prediction(store,problem('call-A','company'))
    actual(store,item,5,**change)
    assert f.reconcile(store,LATER)[0]==0
    store.close()


def test_unselected_option_and_missing_approval_time_cannot_resolve(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    unselected=problem('call-A','unselected')
    unselected.human_choice=None
    f.record_operational_targets(store,unselected)
    f.select_operational_targets(store,unselected)
    no_approval=problem('call-B','missing-approval')
    no_approval.workflow_history=[]
    f.record_operational_targets(store,no_approval)
    f.select_operational_targets(store,no_approval)
    for item in store.feedback('claim'):
        actual(store,item,5)
    assert store.feedback('selected-impact')==[]
    assert f.reconcile(store,LATER)==(0,2)
    store.close()


def test_latest_forecast_before_explicit_cutoff_excludes_late_vintages_and_approvals(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    first=prediction(store,problem('call-A','first',value=1))
    eligible=prediction(store,problem('call-A','eligible',origin='2026-10-14T10:00:00+00:00',value=4))
    prediction(store,problem('call-A','late-origin',origin='2026-10-15T10:00:00+00:00',value=5))
    prediction(store,problem('call-A','late-approval',origin='2026-10-14T11:00:00+00:00',value=5,
                            approved_at='2026-10-15T10:00:00+00:00'))
    actual(store,first,5,forecastCutoffAt='2026-10-14T12:00:00+00:00')
    assert f.reconcile(store,LATER)==(2,2)
    view=f.reliability_version(store,'2026-10-21T00:00:00+00:00')
    assert view['slices'][0]['independentTargets']==1
    assert view['slices'][0]['meanAbsoluteError']==1
    assert view['sampleIds']==[eligible['id']]
    assert len(store.feedback('claim'))==4
    store.close()


def test_late_first_availability_is_not_backdated_to_forecast_origin(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    item=prediction(store,problem('call-A','original'))
    body={key:value for key,value in item.items() if key not in ('id','contractVersion')}
    body.update(firstAvailableAt='2026-10-17T00:00:00+00:00',value=9,
                target={**item['target'],'decisionId':'late-availability'})
    late=f.claim(store,body)
    f.register_prediction(store,late,'operational_consequence')
    store.append_feedback('selected-impact',{'id':late['id'],'selectedAt':'2026-10-17T00:00:00+00:00',
                                           'operationalActionId':late['operationalActionId']})
    actual(store,item,5)
    assert f.reconcile(store,LATER)==(1,1)
    assert f.reliability_version(store,'2026-10-21T00:00:00+00:00')['sampleIds']==[item['id']]
    store.close()


def test_action_identity_includes_route_characteristics_and_schedule_reference(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    first_problem=problem('call-A','original')
    basis=first_problem.evidence['intelligenceBasis']
    basis['restriction']={'plan':{'areaId':'LOCK-A','route':['LOCK-A','port-A'],
                                  'characteristics':{'draughtM':5},'direction':'OUTBOUND'}}
    first=prediction(store,first_problem)
    changed_problem=problem('call-A','changed')
    changed_basis=changed_problem.evidence['intelligenceBasis']
    changed_basis['restriction']={'plan':{'areaId':'LOCK-B','route':['LOCK-B','port-A'],
                                       'characteristics':{'draughtM':6},'direction':'OUTBOUND'}}
    changed_basis['earliestVoyageArrival']='2026-10-18T10:00:00+00:00'
    changed=prediction(store,changed_problem)
    assert first['independentTargetKey']==changed['independentTargetKey']
    assert first['operationalActionId']!=changed['operationalActionId']
    assert first['metricBasisSha256']!=changed['metricBasisSha256']
    actual(store,first,5)
    assert f.reconcile(store,LATER)==(1,1)
    store.close()


@pytest.mark.parametrize('field,value', [('openingRequired',True), ('emergencyTransit',False),
    ('timezoneAssumption','America/New_York'), ('sourceFamily','USCG_NAVCEN_BNM')])
def test_action_identity_carries_restriction_applicability_assumptions(field,value):
    p=problem('call-A','original')
    basis=p.evidence['intelligenceBasis']
    basis['restriction']={'plan':{'areaId':'BRIDGE-A'}}
    original=f.operational_action_id(basis,p.options[0])
    basis['restriction']['plan'][field]=value
    assert f.operational_action_id(basis,p.options[0])!=original


def test_impossible_wait_or_future_access_measurement_remains_pending(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    waiting=problem('call-A','waiting')
    waiting.options[0].evaluation.objectives={'eta':NS(value=None),'port_wait':NS(value=1)}
    wait=prediction(store,waiting)
    actual(store,wait,-1,target={'kind':'WAITING'})
    access=problem('call-B','access')
    access.options[0].evaluation.objectives={'eta':NS(value=None),'port_wait':NS(value=None)}
    access.options[0].evaluation.derived['earliestScheduledAccess']='2026-10-18T12:00:00+00:00'
    at=prediction(store,access)
    actual(store,at,f.instant('2026-10-19T12:00:00+00:00').timestamp(),
           target={'kind':'ACCESS_TIME'},unit='UTC epoch seconds')
    assert f.reconcile(store,LATER)==(0,2)
    store.close()


def test_semantically_equivalent_cutoff_times_do_not_create_conflicts(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    item=prediction(store,problem('call-A','original'))
    actual(store,item,5)
    actual(store,item,5,forecastCutoffAt='2026-10-16T17:30:00+05:30')
    assert f.reconcile(store,LATER)==(1,0)
    view=f.reliability_version(store,'2026-10-21T00:00:00+00:00')
    assert view['slices'][0]['independentTargets']==1
    store.close()


def test_conflicting_actual_cutoffs_are_not_silently_selected(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    item=prediction(store,problem('call-A','original'))
    actual(store,item,5)
    assert f.reconcile(store,LATER)==(1,0)
    actual(store,item,5,forecastCutoffAt='2026-10-16T13:00:00+00:00')
    view=f.reliability_version(store,'2026-10-21T00:00:00+00:00')
    assert view['slices']==[]
    assert any('cutoffs' in row['reason'] for row in view['excludedTargets'])
    # Before initial resolution a conflicting pair stays pending as well.
    other=prediction(store,problem('call-B','other'))
    actual(store,other,5)
    actual(store,other,5,forecastCutoffAt='2026-10-16T13:00:00+00:00')
    assert f.reconcile(store,LATER)==(0,1)
    store.close()


def test_actual_revisions_exclude_fit_but_wrong_entity_or_measurement_do_not(tmp_path):
    store=SqliteLedgerStore(tmp_path/'ledger.db')
    item=prediction(store,problem('call-A','original'))
    actual(store,item,5)
    assert f.reconcile(store,LATER)==(1,0)
    actual(store,item,10,entity='another-vessel')
    actual(store,item,11,target={'kind':'WAITING'})
    actual(store,item,12,metricBasisSha256='c'*64)
    now='2026-10-21T00:00:00+00:00'
    assert f.reliability_version(store,now)['slices'][0]['independentTargets']==1
    revised=actual(store,item,6,firstAvailableAt='2026-10-20T12:00:00+00:00')
    view=f.reliability_version(store,now)
    assert view['slices']==[]
    assert store.get_prediction(item['id']).observed_value==5
    assert revised['id'] in {row['id'] for row in store.feedback('evidence')}
    store.close()


def report(store,entity,at=ORIGIN):
    item=f.news_report(store,wording='Specific announcement '+entity,source='Authority '+entity,
        source_version='v1',independence_key='Authority '+entity,event_key=entity+':window',entity=entity,
        geography='Geography '+entity,target={'kind':'ANNOUNCEMENT','from':'2026-10-15','through':'2026-10-15'},
        first_available_at=at,published_at=at,response_sha256='a'*64)
    f.verify_news(store,item,at)
    return item


def test_unrelated_pending_counts_do_not_invalidate_but_applied_policy_does(tmp_path):
    public=SqliteLedgerStore(tmp_path/'public.db');private=SqliteLedgerStore(tmp_path/'private.db')
    item=report(public,'A')
    consumers={item['id']:'synthetic-reference-calculation-v1'}
    frozen=f.freeze_consumption(public,private,[item['id']],ORIGIN,calculation_consumers=consumers)
    report(public,'B','2026-10-13T10:05:00+00:00')
    assert f.reliability_version(public,LATER)['id'] != frozen['reliabilityVersion']['id']
    f.require_consumption(public,frozen,now=LATER)
    dependency=f.neutral_dependency(item)
    public.append_feedback('applied-policy',{'id':'validated-weight-v2','contextKey':dependency['contextKey'],
        'firstAvailableAt':'2026-10-13T11:00:00+00:00','status':'VALIDATED_APPLIED','weight':0.8,
        'calculationConsumer':consumers[item['id']],
        'correction':None,'policyParameters':{'rule':'Synthetic policy regression'}})
    with pytest.raises(ValueError,match='applied reliability/correction changed'):
        f.require_consumption(public,frozen,now=LATER)
    newer=f.freeze_consumption(public,private,[item['id']],LATER,calculation_consumers=consumers)
    public.append_feedback('applied-policy',{'id':'validated-correction-v3','contextKey':dependency['contextKey'],
        'firstAvailableAt':'2026-10-21T11:00:00+00:00','status':'VALIDATED_APPLIED','weight':0.8,
        'calculationConsumer':consumers[item['id']],
        'correction':{'kind':'Synthetic test only','offset':1}})
    f.require_consumption(public,newer,now=LATER)
    with pytest.raises(ValueError,match='applied reliability/correction changed'):
        f.require_consumption(public,newer,now='2026-10-22T00:00:00+00:00')
    public.close();private.close()


@pytest.mark.parametrize('record_kind,value', [('OPERATOR_RECORD', False), ('CANCELLATION', True)])
def test_relevant_contradiction_or_cancellation_requires_successor(tmp_path, record_kind, value):
    public=SqliteLedgerStore(tmp_path/'public.db');private=SqliteLedgerStore(tmp_path/'private.db')
    item=report(public,'A')
    frozen=f.freeze_consumption(public,private,[item['id']],ORIGIN)
    at='2026-10-13T11:00:00+00:00'
    f.evidence(public,{'eventKey':item['eventKey'],'target':item['target'],
        'entity':item['entity'],'geography':item['geography'],'source':'Independent operator',
        'sourceVersion':'operator-v1','independenceKey':'Independent operator',
        'firstAvailableAt':at,'observedAt':at,'unit':item['unit'],'aggregation':item['aggregation'],
        'value':value,'recordKind':record_kind,'responseSha256':'b'*64,
        **({'cancelsSourceVersion':item['sourceVersion']} if record_kind=='CANCELLATION' else {})})
    result=f.verify_news(public,item,at)
    if record_kind=='CANCELLATION':
        assert result['applicability']=='SUPERSEDED'
        assert result['verdict']=='UNRESOLVED'  # Cancellation does not falsify the announcement.
    else:
        assert result['verdict']=='CONTRADICTED'
    with pytest.raises(ValueError,match='verification changed'):
        f.require_consumption(public,frozen,now=LATER)
    assert private.feedback('consumption')[0]['inputs'][0]['assessment']==frozen['inputs'][0]['assessment']
    public.close();private.close()


def test_unrelated_applied_context_does_not_invalidate_and_conflicting_applicable_policies_block(tmp_path):
    public=SqliteLedgerStore(tmp_path/'public.db');private=SqliteLedgerStore(tmp_path/'private.db')
    a=report(public,'A');b=report(public,'B')
    consumer='synthetic-reference-calculation-v1'
    frozen=f.freeze_consumption(public,private,[a['id']],ORIGIN,calculation_consumers={a['id']:consumer})
    at='2026-10-13T11:00:00+00:00'
    public.append_feedback('applied-policy',{'id':'unrelated-weight-v2',
        'contextKey':f.neutral_dependency(b)['contextKey'],'firstAvailableAt':at,
        'calculationConsumer':consumer,
        'status':'VALIDATED_APPLIED','weight':0.8,'correction':None})
    f.require_consumption(public,frozen,now=LATER)
    for policy_id in ('conflicting-weight-v2','conflicting-weight-v3'):
        public.append_feedback('applied-policy',{'id':policy_id,
            'contextKey':f.neutral_dependency(a)['contextKey'],'firstAvailableAt':at,
            'calculationConsumer':consumer,
            'status':'VALIDATED_APPLIED','weight':0.8,'correction':None})
    with pytest.raises(ValueError,match='conflicting versions'):
        f.require_consumption(public,frozen,now=LATER)
    public.close();private.close()


def test_discovered_policy_is_not_applied_to_review_only_comparison(tmp_path):
    public=SqliteLedgerStore(tmp_path/'public.db');private=SqliteLedgerStore(tmp_path/'private.db')
    item=report(public,'A')
    frozen=f.freeze_consumption(public,private,[item['id']],ORIGIN)
    public.append_feedback('applied-policy',{'id':'discovered-weight-v2',
        'contextKey':f.neutral_dependency(item)['contextKey'],
        'firstAvailableAt':'2026-10-13T11:00:00+00:00','status':'VALIDATED_APPLIED',
        'calculationConsumer':'other-calculation-v1','weight':0.8,'correction':None})
    f.require_consumption(public,frozen,now=LATER)
    later=f.freeze_consumption(public,private,[item['id']],LATER)
    assert later['appliedDependencies']==[f.neutral_dependency(item)]
    assert 'Review context only' in later['effect']
    public.close();private.close()
