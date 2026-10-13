"""Source-supported scheduled access, in the existing visitor advisory workflow."""
from datetime import timedelta
import hashlib
import json
import math
import re
from fastapi import APIRouter, Body, HTTPException
from backend.app.identity import current_identity
from backend.app.routes.shipping_intelligence import scoped_world
from src.portwatch_os.clock import wall_now
from src.portwatch_os.intelligence import operational_notices as notices
from src.portwatch_os.intelligence.current_environment import instant
from src.portwatch_os.decision.model import (DecisionProblem,DecisionOption,DecisionActor,DecisionEvaluation,
    DecisionObjective,ConstraintResult,VESSEL_ROUTING,FEASIBLE,known,unknown)
from src.portwatch_os.decision.actions import KEEP_PLAN,DELAY_ARRIVAL,CATALOGUE

router=APIRouter()


def company():
    scoped=scoped_world();who=current_identity.get()
    if who.role!='SHIPPING_COMPANY': raise HTTPException(403,'Company declares and compares its own voyage')
    return scoped,who


@router.get('/intelligence/operational-notices')
def listing():
    scoped=scoped_world();notice=notices.refresh()
    rows=[{'id':v['id'],'name':v['name'],'laneCode':v['laneCode'],'portCode':v['portCode'],
        'cargo':v['cargo'],'declaredPassage':v.get('declaredPassage')} for v in scoped.world['fleet']]
    return {'notices':[notice],'voyages':rows,
        'meaning':'Authority facts and operator-declared future voyage plans are separate. No broad lane match establishes lock exposure.'}


@router.get('/intelligence/notice-evidence/{digest}')
def original(digest:str):
    scoped_world()
    if not re.fullmatch('[a-f0-9]{64}',digest): raise HTTPException(404,'Original unavailable')
    path=notices.ROOT/'operational_notices'/(digest+'.response')
    if not path.exists(): raise HTTPException(404,'Original unavailable')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest: raise HTTPException(503,'Original hash mismatch')
    if raw.startswith(b'%PDF-'):
        import base64
        return {'sha256':digest,'mediaType':'application/pdf','byteLength':len(raw),'base64':base64.b64encode(raw).decode()}
    return {'sha256':digest,'mediaType':'text/html','byteLength':len(raw),'response':raw.decode('utf-8')}


@router.post('/intelligence/notice-passage-plan')
def declare(payload:dict=Body(...)):
    scoped,who=company()
    row=next((v for v in scoped.world['fleet'] if v['id']==payload.get('vesselId')),None)
    if not row: raise HTTPException(404,'Voyage not owned by this visitor')
    if row['laneCode']!='EUR_IND': raise HTTPException(409,'This declaration needs the Europe–India voyage; Gulf membership does not establish Eastham exposure')
    try:
        passage=instant(payload['passageAt'])
        if passage<=wall_now() or passage>wall_now()+timedelta(days=365): raise ValueError('Declare a future passage within one year')
        hours=payload['postPassageHours']
        if isinstance(hours,bool) or not isinstance(hours,(int,float)) or not math.isfinite(hours) or not 24<=hours<=720: raise ValueError('Post-passage travel assumption must be 24–720 h')
        chars=payload['characteristics']
        for key,upper in (('loaM',450),('beamM',80),('draughtM',25),('airDraughtM',80)):
            value=chars[key]
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<value<=upper: raise ValueError('Positive declared vessel characteristics required')
        if payload.get('direction')!='OUTBOUND' or payload.get('areaId')!='EASTHAM_80_LOCK': raise ValueError('Supported declaration is outbound through Eastham 80-foot Lock to India')
        if payload.get('alternativeAccess')!='NOT_VERIFIED': raise ValueError('Alternate lock suitability/booking need separate evidence; no alternative access inferred')
        if payload.get('declarationConfirmed') is not True: raise ValueError('Confirm these are operator-declared fictional voyage inputs')
    except (KeyError,TypeError,ValueError) as exc: raise HTTPException(422,str(exc))
    plan={'areaId':'EASTHAM_80_LOCK','direction':'OUTBOUND','origin':'Manchester Ship Canal upstream of Eastham 80-foot Lock',
        'route':['EASTHAM_80_LOCK','SUEZ',row['portCode']],'passageAt':passage.isoformat(),
        'postPassageHours':hours,'characteristics':{k:chars[k] for k in ('loaM','beamM','draughtM','airDraughtM')},
        'alternativeAccess':'NOT_VERIFIED','source':'OPERATOR_DECLARED_FICTIONAL_VOYAGE',
        'declaredAt':wall_now().isoformat(),'actor':who.actor}
    plan['id']=hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
    arrival=passage+timedelta(hours=hours)
    def save(world):
        vessel=next(v for v in world['fleet'] if v['id']==row['id'])
        vessel['declaredPassage']=plan
        vessel['etaHours']=(arrival-instant(world['epoch'])).total_seconds()/3600
        # Prior comparisons/approvals remain in the durable journey ledger.
        # Their completed schedule delta cannot silently amend this new plan.
        if (world.get('terminalProposal') or {}).get('vesselId')==row['id']:
            world.pop('terminalProposal',None);world.pop('currentArrivalOutcome',None);world.pop('currentArrivalReview',None)
        world.setdefault('passagePlanHistory',[]).append({'vesselId':row['id'],'plan':plan})
        return {'vesselId':row['id'],'plan':plan,'requestedDestinationArrival':arrival.isoformat()}
    return scoped.save_world(save)


@router.post('/intelligence/notice-comparison')
def comparison(payload:dict=Body(...)):
    scoped,who=company();row=next((v for v in scoped.world['fleet'] if v['id']==payload.get('vesselId')),None)
    if not row: raise HTTPException(404,'Voyage not owned by this visitor')
    plan=row.get('declaredPassage')
    if not plan: raise HTTPException(409,'Declare the route, characteristics and future passage first')
    notice=notices.refresh(force=payload.get('refreshSource') is True)
    if notice.get('revisionId')!=payload.get('revisionId'): raise HTTPException(409,'Notice revision changed; inspect the current original before comparing')
    try:
        result=notices.planned_consequence(notice,plan)
        if instant(plan['passageAt'])<=wall_now(): raise ValueError('Declared passage is no longer future')
    except (ValueError,KeyError) as exc: raise HTTPException(409,str(exc))
    from backend.app.services.demo_terminal import company_for
    vessel=company_for(scoped.world).vessel(row['id']);eta=instant(vessel.eta)
    expected=instant(plan['passageAt'])+timedelta(hours=plan['postPassageHours'])
    if eta!=expected: raise HTTPException(409,'Declared arrival has changed; save a fresh passage plan before comparison')
    at=wall_now();wait=result['calculatedWaitHours'];earliest=eta+timedelta(hours=wait)
    frozen={'kind':'NOTICE_RESTRICTION','portCode':row['portCode'],'voyageId':row['id'],
        'availableAt':at.isoformat(),'earliestVoyageArrival':eta.isoformat(),'plannedArrival':eta.isoformat(),
        'firstClearApproach':earliest.isoformat(),'forecastGateWaitHours':wait,
        'reportedFact':{**notice,'title':'Peel Ports MNTM 2026-18 · Eastham lock restriction',
            'fact':'Eastham 80-foot Lock closed '+result['window']['closureStartDate']+' through '+result['window']['closureEndDate']+'; first operational tide '+result['window']['localDate']+' '+result['window']['localEnd']+' '+result['window']['timeZone']+'. Queen Elizabeth II Lock is unaffected.'},
        'inferredExposure':{'route':' → '.join(plan['route']),'port':row['portCode'],'vessel':row['name'],'cargo':row['cargo'],
            'basis':'Explicit visitor-declared outbound passage in the affected control zone overlaps the published window; not inferred from AIS or broad lane proximity.'},
        'assumptions':{'kind':'OPERATOR_DECLARED_PASSAGE','postPassageHours':plan['postPassageHours'],
            'purpose':'Fixed travel duration after lock passage, with no additional queue or berth calculation',
            'doesNotAssert':'No confirmed reopening, clearance, fuel, cost, safety or berth benefit'},
        'restriction':{**result,'revisionId':notice['revisionId'],'plan':plan},
        'meaning':'Conditional schedule calculation from the authority’s first published operational tide and declared lock route. Both options have the same scheduled access and destination shift; revising the request relocates planned waiting. Alternative lock, actual slot and reopening are unavailable. Simulated, not measured.'}
    try: notices.require_revision(frozen)
    except ValueError as exc: raise HTTPException(409,str(exc))
    frozen['evidenceId']=hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest()
    did='dec-notice-'+frozen['evidenceId'][:20];options=[]
    for baseline,action,label in ((True,KEEP_PLAN,'Keep requested passage; wait for first operational tide'),(False,DELAY_ARRIVAL,'Request passage at first published operational tide')):
        arrival=eta if baseline else earliest;passage=instant(plan['passageAt']) if baseline else instant(result['earliestScheduledAccess'])
        options.append(DecisionOption(option_id=did+('-continue' if baseline else '-window'),action=action,label=label,actor=who.role,is_baseline=baseline,status=FEASIBLE,
            params={'arrivalAt':arrival.isoformat(),'holdHours':0 if baseline else wait},
            constraints=[ConstraintResult('scheduled_access','Published lock restriction is respected',True,True,
                'No movement during the published closure; first stated operational tide needs operator slot/clearance confirmation',basis='evidence.intelligenceBasis.restriction')],
            assumptions=[frozen['assumptions']],provenance={'source':'AUTHORITY_SCHEDULE_WITH_DECLARED_VOYAGE','evidenceId':frozen['evidenceId']},
            evaluation=DecisionEvaluation(objectives={'eta':known(wait,'hours',basis='First published operational tide minus requested passage; fixed onward travel assumption; same total destination shift for both options',confidence=None),
                'port_wait':known(wait if baseline else 0,'hours',basis='Planned lock waiting under published schedule; revised request moves waiting before arrival',confidence=None),
                **{k:unknown(unit,'No supporting operational inputs or measured benefit') for k,unit in (('fuel','index'),('cost','money'),('risk','risk'),('weather','m'))}},
                derived={'destinationPort':row['portCode'],'arrivalAt':arrival.isoformat(),'arrivalShiftHours':(arrival-eta).total_seconds()/3600,
                    'holdHours':0 if baseline else wait,'requestedPassageAt':passage.isoformat(),'earliestScheduledAccess':result['earliestScheduledAccess'],
                    'actualEarliestPermittedAccess':None,
                    'approachClearAt':earliest.isoformat(),'earliestDestinationArrival':earliest.isoformat(),'totalScheduleShiftHours':wait},
                computed_at=at.isoformat()),timeline=[{'at':passage.isoformat(),'kind':'passage_request','label':'Requested lock passage'},
                    {'at':result['earliestScheduledAccess'],'kind':'scheduled_access','label':'First published operational tide; operator confirmation required'},
                    {'at':earliest.isoformat(),'kind':'arrival','label':'Conditional destination arrival'}]))
    problem=DecisionProblem(decision_id=did,created_at=at.isoformat(),domain=VESSEL_ROUTING,world_revision={'mode':'LIVE'},world_state_id=scoped.world['epoch']+frozen['evidenceId'],
        subject_type='vessel',subject_id=row['id'],subject_label=row['name'],actor=DecisionActor(role=who.role,organisation=who.organisation),at=at.isoformat(),
        objectives=[DecisionObjective('eta','Total schedule shift','hours','min','Published window and fixed onward travel assumption'),
                    DecisionObjective('port_wait','Scheduled lock waiting','hours','min','Requested passage versus scheduled access')],
        available_actions=[{**CATALOGUE[a].to_dict(),'availability':{'status':'AVAILABLE','reason':'Conditional scheduled access comparison'}} for a in (KEEP_PLAN,DELAY_ARRIVAL)],
        options=options,baseline_option_id=options[0].option_id,evidence={'intelligenceBasis':frozen,'frontierObjectives':['eta','port_wait'],'subject':{'source':'FICTIONAL_DEMO'}},
        headline=row['name']+': published Eastham lock restriction → passage window',do_nothing_statement='Keep requested passage; no movement is assumed during the published closure.',notes=[frozen['meaning']])
    from src.portwatch_os.decision.engine import get_engine
    return get_engine().finish(problem).to_dict()
