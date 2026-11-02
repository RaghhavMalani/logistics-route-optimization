"""Visitor-owned, Company-private commercial planning. No external execution."""
from __future__ import annotations
import copy
from datetime import timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from backend.app.identity import current_identity
from src.portwatch_os.clock import LIVE, get_clock, wall_now
from src.portwatch_os.sandbox import current_sandbox
from src.portwatch_os.decision.commercial import CommercialContext, evaluate, digest
from src.portwatch_os.decision.commercial_uncertainty import Simulation, simulate
from src.portwatch_os.decision import commercial_jobs as jobs

router=APIRouter()
KIND='commercial_shadow'


def owned(decision_id=None):
    scoped,who=current_sandbox.get(),current_identity.get()
    if scoped is None or who is None or who.role!='SHIPPING_COMPANY': raise HTTPException(403,'Commercial records are Company-private in this visitor world')
    from src.portwatch_os.decision.engine import get_engine
    from backend.app.routes.decisions import _visible_or_403
    engine=get_engine();problem=engine.get(decision_id) if decision_id else None
    if decision_id:
        if problem is None or problem.actor.role!='SHIPPING_COMPANY': raise HTTPException(404,'No owned Company comparison')
        _visible_or_403(problem,who)
    return scoped,who,engine,problem


class Request(BaseModel):
    model_config=ConfigDict(extra='forbid')
    context: CommercialContext
    simulation: Simulation | None = None
    jobId: str | None = Field(default=None,pattern=r'^[a-f0-9-]{36}$')


def _owner(scoped): return digest(str(scoped.root.resolve()))


def _shadow(scoped,engine,problem,context,config,at,job_id):
    from src.portwatch_os.ledger.schema import DecisionRecord
    control=None
    if job_id and engine.ledger.get_decision('commercial-job-'+job_id):
        raise HTTPException(409,'This job identifier is already retained; inspect it or retry unfinished inputs with a new job identifier')
    try:
        with jobs.study(_owner(scoped),job_id) as control:
            engine.ledger.record_decision(DecisionRecord(decision_id='commercial-job-'+control.id,
                kind='commercial_job',subject=problem.decision_id,issued_at=at.isoformat(),issuer=context.basis.actor,
                recommendation={'jobId':control.id,'status':'STARTED','sourceDecisionId':problem.decision_id,
                    'contextHash':digest(context.model_dump(mode='json')),'budgetSeconds':jobs.MAX_SECONDS},
                reason='Bounded Company-private shadow study',model='commercial-mc-shadow-v1'))
            output=simulate(context,problem.to_dict(),at,config,checkpoint=control.checkpoint)
        return output,control.public()
    finally:
        if control is not None:
            # Wall-clock: actual compute completion, separate from frozen forecast targets.
            engine.ledger.append_feedback('commercial-job-event',{'jobId':control.id,
                'at':wall_now().isoformat(),**control.public()})


@router.get('/commercial/jobs/{job_id}')
def job_detail(job_id:str):
    scoped,who,engine,_=owned()
    record=engine.ledger.get_decision('commercial-job-'+job_id)
    if record is None or record.kind!='commercial_job': raise HTTPException(404,'No owned study job')
    try: return jobs.inspect(_owner(scoped),job_id)
    except jobs.UnknownJob:
        events=[r for r in engine.ledger.feedback('commercial-job-event') if r.get('jobId')==job_id]
        return events[-1] if events else {**record.recommendation,'status':'INTERRUPTED','reason':'Process no longer owns this unfinished job; retained inputs may be retried'}


@router.post('/commercial/jobs/{job_id}/cancel')
def cancel_job(job_id:str):
    scoped,who,engine,_=owned()
    if engine.ledger.get_decision('commercial-job-'+job_id) is None: raise HTTPException(404,'No owned study job')
    try: return jobs.cancel(_owner(scoped),job_id)
    except jobs.UnknownJob: raise HTTPException(409,'This process does not own an active job; inspect its retained status') from None


@router.get('/commercial/comparisons/{decision_id}')
def retained(decision_id:str):
    scoped,who,engine,problem=owned(decision_id)
    rows=engine.ledger.decisions(kind=KIND,subject=decision_id)
    return {'records':[r.recommendation for r in rows], 'scope':'Company-private shadow studies, not operational outcomes'}


@router.post('/commercial/evaluate')
def calculate(payload:Request):
    scoped,who,engine,problem=owned(payload.context.decisionId)
    if get_clock().state.mode!=LIVE: raise HTTPException(409,'New commercial declarations require the live clock; retained inspection does not rerun them')
    # wall-clock: this is the actual commercial declaration/evaluation receipt.
    at=wall_now()
    context=payload.context
    if context.basis.actor!=who.actor: raise HTTPException(400,'The declaring actor must be the current Company actor')
    frozen=problem.to_dict()
    binding={'decisionId':problem.decision_id,'evidenceHash':digest(frozen['evidence']),
        'context':context.model_dump(mode='json'),'simulation':payload.simulation.model_dump(mode='json') if payload.simulation else None}
    key='commercial-'+digest(binding)[:32]
    previous=engine.ledger.get_decision(key)
    if previous: return previous.recommendation
    try:
        from src.portwatch_os.intelligence.free_sources import catalogue
        products=catalogue()['products']
        public_refs={p['sha256']:p for p in products if p['sha256']}
        for evidence_id in context.marketEvidenceIds:
            if evidence_id not in public_refs or public_refs[evidence_id]['productId']!='trade': raise ValueError('Market evidence must name a retained public trade product')
        for evidence_id in context.listedAreaEvidenceIds:
            if evidence_id not in public_refs or public_refs[evidence_id]['productId']!='jwc': raise ValueError('Listed-area evidence must name a retained dated JWC product')
        evaluation=evaluate(context,frozen,at)
        uncertainty,compute_job=_shadow(scoped,engine,problem,context,payload.simulation,at,payload.jobId) if payload.simulation else (None,None)
    except jobs.Busy as exc: raise HTTPException(429,str(exc),headers={'Retry-After':'5'}) from exc
    except jobs.Cancelled as exc: raise HTTPException(409,str(exc)) from exc
    except jobs.BudgetExceeded as exc: raise HTTPException(408,str(exc)) from exc
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    # Versions of the same study do not count as additional voyages or capacity.
    latest=scoped.world.get('commercialLatest',{})
    others=[]
    for other_id in set(latest.values()):
        record=engine.ledger.get_decision(other_id)
        if not record: continue
        other=record.recommendation.get('context',{})
        if other.get('voyageId')==context.voyageId: continue
        other_problem=engine.get(record.recommendation.get('sourceDecisionId',''))
        vessel=next((v for v in scoped.world['fleet'] if v['id']==other.get('voyageId')),None)
        other_episode=((other_problem.evidence.get('currentEnvironment') or {}).get('operationalEpisode') or {}).get('id') if other_problem else None
        if not vessel or other_episode!=(vessel.get('operationalEpisode') or {}).get('id'): continue
        others.append(other)
    from src.portwatch_os.decision.commercial import resource_conflicts
    conflicts=resource_conflicts(context,others)
    if any(c['status']!='UNRESERVED_WITHIN_DECLARED_CAPACITY' for c in conflicts):
        evaluation.update(commercialPick=None,decision='REQUIRES_REVIEW')
        if uncertainty: uncertainty['conditionalShadowPick']=None
    env=frozen['evidence']['currentEnvironment']
    episode=(env.get('operationalEpisode') or {}).get('id')
    call_key=context.voyageId+':'+str(episode)
    result={'recordId':key,'createdAt':at.isoformat(),'sourceDecisionId':problem.decision_id,'contextHash':digest(context.model_dump(mode='json')),
        'consumedEvidenceHash':binding['evidenceHash'],'context':context.model_dump(mode='json'),'evaluation':evaluation,'uncertainty':uncertainty,
        'simulationConfiguration':binding['simulation'],'computeJob':compute_job,'publicContext':[public_refs[i] for i in [*context.marketEvidenceIds,*context.listedAreaEvidenceIds]],
        'resourceConflicts':conflicts,'previousCommercialId':latest.get(call_key),'execution':'SHADOW','privacy':'COMPANY_PRIVATE',
        'meaning':'New commercial study; no incumbent policy adoption or human approval is implied.'}
    from src.portwatch_os.ledger.schema import DecisionRecord
    engine.ledger.record_decision(DecisionRecord(decision_id=key,kind=KIND,subject=problem.decision_id,issued_at=at.isoformat(),issuer=who.actor,
        recommendation=result,reason='Explicit Company commercial shadow study',model=evaluation['version'],model_version=evaluation['policyVersion']))
    def save(world): world.setdefault('commercialLatest',{})[call_key]=key
    scoped.save_world(save)
    return result


@router.get('/commercial/records/{record_id}')
def record_detail(record_id:str):
    scoped,who,engine,_=owned()
    record=engine.ledger.get_decision(record_id)
    if record is None or record.kind!=KIND: raise HTTPException(404,'No owned commercial study')
    owned(record.recommendation['sourceDecisionId'])
    return record.recommendation


@router.post('/commercial/records/{record_id}/successor')
def successor(record_id:str):
    scoped,who,engine,_=owned()
    record=engine.ledger.get_decision(record_id)
    if not record or record.kind!=KIND: raise HTTPException(404,'No owned commercial study')
    data=record.recommendation
    _,_,_,source=owned(data['sourceDecisionId'])
    if get_clock().state.mode!=LIVE: raise HTTPException(409,'Fresh review requires the live clock')
    from src.portwatch_os.decision.continuation import require_current
    physical=copy.deepcopy(source)
    physical.evidence.pop('commercialReview',None)
    require_current(physical)
    clone_id='dec-commercial-'+record_id.split('commercial-',1)[1]
    existing=engine.get(clone_id)
    if existing: return existing.to_dict()
    problem=copy.deepcopy(source)
    from src.portwatch_os.decision.model import COMPUTED,REJECTED,ConstraintResult
    problem.decision_id=clone_id
    # wall-clock: this explicit successor begins a new human review now.
    at=wall_now()
    try:
        now_evaluation=evaluate(CommercialContext(**data['context']),source.to_dict(),at)
    except ValueError as exc: raise HTTPException(409,'Declaration applicability changed; retain a new linked study before fresh review') from exc
    if now_evaluation['insurance']!=data['evaluation']['insurance']:
        raise HTTPException(409,'Insurance or quote review status changed; evaluate and retain a new linked study')
    problem.created_at=at.isoformat();problem.workflow=COMPUTED;problem.workflow_history=[];problem.human_choice=None
    problem.evidence['predecessorDecisionId']=source.decision_id
    # This is the only commercial payload copied into Port/Vessel evidence.
    # Invoice values, margins, policy wording, counterparties and samples stay private.
    problem.evidence['commercialReview']={'recordId':record_id,'contextHash':data['contextHash'],'sourceComparisonId':source.decision_id,
        'evaluationVersion':data['evaluation']['version'],'policyVersion':data['evaluation']['policyVersion'],
        'simulationVersion':(data.get('uncertainty') or {}).get('version'),'worldSampleHash':(data.get('uncertainty') or {}).get('worldSampleHash'),
        'execution':'DEMONSTRATION_WORKFLOW','scope':'Declared Company commitments; private commercial terms are withheld',
        'incumbentPick':data['evaluation']['incumbentPick'],'commercialPick':data['evaluation']['commercialPick']}
    rows={r['optionId']:r for r in data['evaluation']['options']}
    for option in problem.options:
        prior=[c for c in option.constraints if c.key=='commercial_required_commitment']
        option.constraints=[c for c in option.constraints if c.key!='commercial_required_commitment']
        if prior and not any(c.hard and not c.passed for c in option.constraints):
            from src.portwatch_os.decision.model import FEASIBLE
            physical_row=next((r for r in problem.evidence['currentEnvironment']['passageComparison']['options'] if r['optionId']==option.option_id),{})
            if physical_row.get('status')==FEASIBLE: option.status=FEASIBLE
        row=rows.get(option.option_id)
        if row and row['reasons']:
            option.status=REJECTED
            option.constraints.append(ConstraintResult('commercial_required_commitment','Declared Company commitment',False,True,
                'Company-declared required commitment or review gate fails; private terms withheld',basis=record_id))
    problem=engine.finish(problem,now=at)
    return problem.to_dict()


@router.get('/commercial/templates/{decision_id}')
def templates(decision_id:str,example:str='CURRENT_SOURCE'):
    scoped,who,engine,problem=owned(decision_id)
    # wall-clock: these are proposed declarations at the time of inspection, not retained evidence or private commercial facts.
    now=wall_now();env=problem.evidence.get('currentEnvironment',{});comparison=env.get('passageComparison')
    if not comparison: raise HTTPException(409,'Open a declared-passage comparison first')
    from src.portwatch_os.decision.commercial import instant
    if not any(o.get('status')=='FEASIBLE' and o.get('approachClearAt') for o in comparison['options']): raise HTTPException(409,'No physically feasible retained approach is available for this template')
    clear=max(instant(o['approachClearAt']) for o in comparison['options'] if o.get('approachClearAt'))
    basis=dict(kind='SIMULATION',source='Explicit fictional commercial template; edit before use',actor=who.actor,
        firstAvailableAt=now.isoformat(),applicableFrom=now.isoformat(),applicableThrough=(now+timedelta(days=30)).isoformat(),access='COMPANY_PRIVATE')
    context=dict(schemaVersion='commercial-context-v1',decisionId=decision_id,voyageId=problem.subject_id,
        parties=[dict(id='carrier',name='Fictional demo carrier',roles=['CARRIER']),dict(id='cargo-owner',name='Fictional cargo owner',roles=['CARGO_OWNER'])],
        objectiveParty='carrier',objective='SUPPORTED_COMPONENT_COST',currency='USD',accountingScope='Declared future time and contract penalties only; fuel and other terms excluded from this component scope',
        materialComponents=['time'],includePassageFuel=False,basis=basis,
        charges=[dict(id='time',payer='carrier',beneficiary='cargo-owner',kind='ELAPSED_FUTURE_TIME',rate=dict(amount='100',currency='USD'),
            contractBasis='Fictional illustrative future-time charge; no real charter rate',basis=basis)],
        consignments=[dict(id='demo-consignment-1',goodsClass='Declared dry bulk',quantity='100',quantityUnit='tonne',destinationPort=env['portCode'],
            event='DECLARED_FINAL_DELIVERY',deliveryOffsetHours='12',offsetBasis='Fictional 12 h downstream interval; includes all assumed handling and onward delivery once',
            deadline=(clear+timedelta(hours=24)).isoformat(),required=True,ownerParty='cargo-owner',delayCostParty='carrier',basis=basis)],
        policies=[],insuranceReviewRequired=False)
    descriptions={
        'CURRENT_SOURCE':'Uses the already frozen weather basis. Choose current provider data in the passage editor for a genuine forecast; this template does not replace weather.',
        'PERISHABLE':'Required declared shelf-life event; lower fuel cannot compensate for failure. Deterioration money remains unknown.',
        'BULK':'Nonurgent bulk; declared component prices may favor a slower feasible plan. This is illustrative pricing, not an actual quote.',
        'MANUFACTURING':'Low invoice value with a required stockout-related commitment. Invoice sorting is not the objective.',
        'ELECTRONICS':'Invoice and insured amounts differ; war/theft probabilities and payable recovery stay unknown.',
        'CHOKEPOINT':'Strategic detour prerequisites are incomplete in this bounded approach study. Use existing S06 route geometry/stress comparison; Port issue cannot authorize a whole-route diversion.',
        'INSURANCE':'Timely arrival still requires private policy/notification review. Missing evidence does not establish absence of insurance.',
        'MARKET':'Dated HS 1006 India/world import context is not a confirmed buyer, port demand, invoice or diversion permission.',
        'MEAN_TAIL':'Declared component-price versus delay-penalty sensitivity. A mean/tail trade-off requires different retained approach times; equal clocks are not changed to force one.',
        'MULTI':'Two distinct consignments share one voyage-level component bill. No duplicated fuel charge or automatic insurance recovery.',
        'INCOMPLETE':'Unknown material charges withhold a total-cost pick while retaining the passage comparison.',
        'REVISION':'Edit an assumption, retain a linked study and explicitly create a fresh-review successor. Prior approvals and sample identity stay inspectable.',
        'RESOURCE':'One unreserved declared connection resource. Declare the same interval from another voyage to expose shared-capacity conflict; this is not joint optimization.'}
    if example not in descriptions: raise HTTPException(422,'Unknown commercial example')
    shipment=context['consignments'][0]
    times=[instant(o['approachClearAt']) for o in comparison['options'] if o.get('status')=='FEASIBLE' and o.get('approachClearAt')]
    if example=='PERISHABLE':
        middle=min(times)+(max(times)-min(times))/2+timedelta(hours=12)
        shipment.update(goodsClass='Fictional perishable reefer',remainingShelfLifeHours=str(max(0,(middle-now).total_seconds()/3600)),shelfLifeReferenceAt=now.isoformat(),temperatureRequirement='Declared cold-chain review required')
    if example in ('BULK','MEAN_TAIL'):
        context['charges'][0].update(kind='FIXED_COMPONENT',optionAmounts={o['optionId']:{'amount':'1000' if o['optionId']==problem.baseline_option_id else '800','currency':'USD'} for o in comparison['options']},contractBasis='Explicit illustrative component prices, not a charter or bunker quote')
    if example=='MANUFACTURING':
        shipment.update(goodsClass='Fictional critical manufacturing input',invoiceValue={'amount':'1','currency':'USD'},stockoutConsequence='Declared production interruption; financial loss unpriced',deadline=(min(times)+timedelta(hours=12)).isoformat())
    if example=='ELECTRONICS':
        shipment.update(goodsClass='Fictional electronics',hsCode='8517',hsVersion='HS2022',invoiceValue={'amount':'1000000','currency':'USD'},insuredValue={'amount':'800000','currency':'USD'})
    if example in ('ELECTRONICS','INSURANCE'): context['insuranceReviewRequired']=True
    if example=='CHOKEPOINT': context['materialComponents'].append('strategic_diversion_prerequisites')
    if example=='MARKET':
        from src.portwatch_os.intelligence.free_sources import public_product
        trade=public_product('trade')
        shipment.update(goodsClass='Fictional rice cargo',hsCode='1006',hsVersion='HS2022')
        context['marketEvidenceIds']=[trade['sha256']] if trade.get('sha256') else []
    if example=='MEAN_TAIL':
        shipment.update(required=False,deliveryOffsetHours='0',offsetBasis='Illustrative event at conditional approach, no additional handling duplicated',deadline=(max(times)+timedelta(hours=8)).isoformat(),
            penalty={'payer':'carrier','beneficiary':'cargo-owner','ratePerHour':{'amount':'100','currency':'USD'},'cap':{'amount':'2000','currency':'USD'},'graceHours':'0','contractBasis':'Illustrative capped delay penalty, not a real contract'})
        context['materialComponents'].append('penalty:'+shipment['id'])
    if example=='MULTI':
        second=copy.deepcopy(shipment);second.update(id='demo-consignment-2',goodsClass='Second distinct fictional consignment',required=False)
        context['consignments'].append(second)
    if example=='INCOMPLETE': context['materialComponents'].append('unavailable_common_voyage_cost')
    if example=='RESOURCE':
        context['resources']=[dict(resourceId='illustrative-shared-connection-slot',unit='TEU',quantity='1',capacity='1',beginsAt=clear.isoformat(),endsAt=(clear+timedelta(hours=48)).isoformat(),basis=basis)]
    context['basis']['source']+=' · '+example
    from src.portwatch_os.intelligence.free_sources import public_product
    listed=public_product('jwc')
    context['listedAreaEvidenceIds']=[listed['sha256']] if listed.get('sha256') else []
    return {'context':context,'simulation':{'mode':'ASSUMPTION_SENSITIVITY','seed':2404,'draws':256,'alpha':.95,'tailPreference':.5,'acknowledgedAssumptions':False,
        'distribution':{'kind':'DISCRETE','values':[0,4,24],'weights':[.6,.3,.1],'declaration':'Fictional additional downstream handling delay; these weights are assumptions, not empirical frequencies'}},
        'meaning':'Illustrative editable template; not private records, a policy quote or a calibrated distribution',
        'example':example,'description':descriptions[example],'examples':descriptions}
