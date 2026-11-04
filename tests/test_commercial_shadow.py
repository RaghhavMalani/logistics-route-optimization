"""Illustrative arithmetic and counterexamples, not operational outcomes."""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
import pytest
from src.portwatch_os.decision.commercial import CommercialContext,evaluate
from src.portwatch_os.decision.commercial_uncertainty import Simulation,simulate,summarize

AT=datetime(2026,11,2,tzinfo=timezone.utc)


def example():
    basis=dict(kind='SIMULATION',source='Deliberately selected software fixture',actor='demo-company',firstAvailableAt=AT.isoformat(),applicableFrom=AT.isoformat(),applicableThrough='2026-12-02T00:00:00Z')
    context=dict(decisionId='p1',voyageId='v1',parties=[dict(id='carrier',name='Fictional carrier',roles=['CARRIER']),dict(id='owner',name='Fictional owner',roles=['CARGO_OWNER'])],objectiveParty='carrier',objective='SUPPORTED_COMPONENT_COST',currency='USD',accountingScope='Future declared time only',materialComponents=['time'],basis=basis,
        charges=[dict(id='time',payer='carrier',beneficiary='owner',kind='ELAPSED_FUTURE_TIME',rate=dict(amount='10',currency='USD'),contractBasis='Fictional USD 10 per future hour',basis=basis)],
        consignments=[dict(id='s1',goodsClass='Fictional goods',destinationPort='INPRT',event='DECLARED_FINAL_DELIVERY',deadline='2026-11-02T15:00:00Z',required=True,deliveryOffsetHours='2',offsetBasis='Assumed handling and onward 2 h counted once',basis=basis)])
    options=[dict(optionId='keep',label='Keep',status='FEASIBLE',approachClearAt='2026-11-02T08:00:00Z',sailingHours=8,anchorageWaitHours=0,departureHoldHours=0),
        dict(optionId='slow',label='Slower',status='FEASIBLE',approachClearAt='2026-11-02T12:00:00Z',sailingHours=12,anchorageWaitHours=0,departureHoldHours=0)]
    problem=dict(decisionId='p1',subject={'id':'v1'},baselineOptionId='keep',recommendation={'optionId':'keep'},options=[dict(optionId=o['optionId'],status='FEASIBLE') for o in options],evidence={'currentEnvironment':dict(voyageId='v1',portCode='INPRT',passageComparison={'options':options})})
    return context,problem


def test_party_scope_and_ship_cost_once_for_two_shipments():
    c,p=example();c['consignments'].append({**deepcopy(c['consignments'][0]),'id':'s2'})
    result=evaluate(CommercialContext(**c),p,AT)
    assert result['options'][0]['comparableTotal']=='80'
    assert len(result['options'][0]['consignments'])==2
    c['objectiveParty']='owner'
    assert evaluate(CommercialContext(**c),p,AT)['options'][0]['supportedComponentTotal']=='-80'


def test_perishable_hard_gate_beats_a_financial_advantage():
    c,p=example();s=c['consignments'][0];s.update(remainingShelfLifeHours='11',shelfLifeReferenceAt=AT.isoformat())
    c['charges'][0]['optionAmounts']={'keep':{'amount':'10','currency':'USD'},'slow':{'amount':'1','currency':'USD'}}
    r=evaluate(CommercialContext(**c),p,AT)
    assert r['options'][1]['status']=='REQUIRES_REVIEW'
    assert r['commercialPick']=='keep'


def test_nonurgent_bulk_lower_supported_component_can_win():
    c,p=example();c['charges'][0].update(kind='FIXED_COMPONENT',optionAmounts={'keep':{'amount':'100','currency':'USD'},'slow':{'amount':'80','currency':'USD'}})
    r=evaluate(CommercialContext(**c),p,AT)
    assert r['commercialPick']=='slow' and r['profit'] is None


def test_low_invoice_does_not_override_a_critical_commitment():
    c,p=example();c['consignments'][0].update(invoiceValue={'amount':'1','currency':'USD'},deadline='2026-11-02T11:00:00Z',stockoutConsequence='Declared manufacturing line interruption')
    assert evaluate(CommercialContext(**c),p,AT)['options'][1]['consignments'][0]['status']=='FAILS'


def test_invoice_and_insured_values_are_separate_not_automatic_losses():
    c,p=example();c['consignments'][0].update(invoiceValue={'amount':'1000000','currency':'USD'},insuredValue={'amount':'800000','currency':'USD'})
    r=evaluate(CommercialContext(**c),p,AT)
    assert r['options'][0]['comparableTotal']=='80' and r['expectedRecovery'] is None
    assert r['insurance']['policies'][0]['status']=='NO_POLICY_EVIDENCE'


def test_unknown_costs_currency_and_margin_abstain():
    c,p=example();c['materialComponents'].append('port_tariff')
    assert evaluate(CommercialContext(**c),p,AT)['commercialPick'] is None
    c,p=example();c['charges'][0]['rate']['currency']='INR'
    assert evaluate(CommercialContext(**c),p,AT)['commercialPick'] is None
    c,p=example();c['objective']='DECLARED_MARGIN'
    assert evaluate(CommercialContext(**c),p,AT)['commercialPick'] is None


def test_penalty_grace_cap_and_timezone_event():
    c,p=example();s=c['consignments'][0];s.update(deadline='2026-11-02T14:30:00+05:30',required=False,penalty=dict(payer='carrier',beneficiary='owner',ratePerHour={'amount':'20','currency':'USD'},graceHours='1',cap={'amount':'30','currency':'USD'},contractBasis='Illustrative capped penalty'))
    c['materialComponents'].append('penalty:s1')
    r=evaluate(CommercialContext(**c),p,AT)
    assert r['options'][0]['consignments'][0]['slackHours']==-1
    assert r['options'][0]['comparableTotal']=='80'
    assert r['options'][1]['comparableTotal']=='150'


def test_overlap_units_future_information_and_duplicate_ids_refused():
    c,p=example();c['charges'].append({**deepcopy(c['charges'][0]),'id':'wait','kind':'WAIT_TIME'})
    with pytest.raises(ValueError): CommercialContext(**c)

    c,p=example();c['fuelPayer']='undeclared-party'
    with pytest.raises(ValueError): CommercialContext(**c)
    c,p=example();future=deepcopy(c['basis']);future['firstAvailableAt']='2026-11-03T00:00:00Z'
    c['resources']=[dict(resourceId='future-slot',unit='TEU',quantity='1',capacity='2',beginsAt=AT.isoformat(),endsAt='2026-11-04T00:00:00Z',basis=future)]
    with pytest.raises(ValueError): evaluate(CommercialContext(**c),p,AT)
    c,p=example();c['consignments'][0]['quantity']='1'
    with pytest.raises(ValueError): CommercialContext(**c)
    c,p=example();c['basis']['firstAvailableAt']='2026-11-03T00:00:00Z'
    with pytest.raises(ValueError): evaluate(CommercialContext(**c),p,AT)
    c,p=example();c['consignments'].append(deepcopy(c['consignments'][0]))
    with pytest.raises(ValueError): CommercialContext(**c)


def test_common_elapsed_time_is_not_charged_again():
    c,p=example();o=p['evidence']['currentEnvironment']['passageComparison']['options'][0]
    o.update(commonElapsedSailingHours=3,futureSailingHours=5)
    r=evaluate(CommercialContext(**c),p,AT)
    assert r['options'][0]['comparableTotal']=='50'


def test_required_insurance_review_blocks_clearance_without_calling_uninsured():
    c,p=example();c['insuranceReviewRequired']=True
    r=evaluate(CommercialContext(**c),p,AT)
    assert r['commercialPick'] is None
    assert 'not a finding' in r['insurance']['policies'][0]['issues'][0]


def test_finite_tail_ties_against_enumerated_loss_mass():
    # Worst 25% of [0,10,10,30] is exactly 30, not the mean of all values ≥ p75.
    assert summarize([0,10,10,30],.75)['cvar']==30
    # Worst 40% is 30*0.25 + 10*0.15, divided by 0.40 = 22.5.
    assert summarize([0,10,10,30],.60)['cvar']==22.5


def simulation(values=(0,4),weights=(.5,.5)):
    return Simulation(mode='ASSUMPTION_SENSITIVITY',seed=3,draws=64,alpha=.75,tailPreference=.5,acknowledgedAssumptions=True,
        distribution=dict(kind='DISCRETE',values=list(values),weights=list(weights),declaration='Explicit software assumed shared additional delay'))


def test_deterministic_equivalence_common_samples_and_reproducibility():
    c,p=example();model=CommercialContext(**c);config=simulation((0,), (1,))
    a=simulate(model,p,AT,config);b=simulate(model,p,AT,config)
    assert a==b
    assert a['options'][0]['supportedCost']['mean']==float(evaluate(model,p,AT)['options'][0]['supportedComponentTotal'])
    config=simulation();a=simulate(model,p,AT,config)
    p['options'].reverse();p['evidence']['currentEnvironment']['passageComparison']['options'].reverse()
    b=simulate(model,p,AT,config)
    assert a==b
    assert a['options'][0]['pairedDeltaVsCurrent']['mean']==0
    assert a['options'][1]['pairedDeltaVsCurrent']['mean']==40
    assert a['independentOperationalTargets']==0


def test_missing_empirical_distribution_stays_collecting_and_does_not_sample():
    c,p=example();r=simulate(CommercialContext(**c),p,AT,Simulation(mode='EMPIRICAL_SHADOW',seed=3))
    assert r['status']=='COLLECTING' and 'worldSampleHash' not in r


def test_invalid_weights_or_unacknowledged_distribution_are_refused():
    with pytest.raises(ValueError): simulation((0,1),(.2,.2))
    with pytest.raises(ValueError): Simulation(mode='ASSUMPTION_SENSITIVITY',seed=1)


def test_missing_material_components_block_mc_pick_but_keep_timing_study():
    c,p=example();c['materialComponents'].append('unknown_canal_cost')
    r=simulate(CommercialContext(**c),p,AT,simulation())
    assert r['conditionalShadowPick'] is None
    assert all(row['supportedCost'] is None for row in r['options'])
