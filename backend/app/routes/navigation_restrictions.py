"""One reviewed bridge consequence carried through the original role workflow."""
from datetime import timedelta
import hashlib
import json
import math
from fastapi import APIRouter, Body, HTTPException, Query
from backend.app.routes.operational_notices import company
from backend.app.routes.shipping_intelligence import scoped_world
from src.portwatch_os.clock import wall_now, world_now, get_clock
from src.portwatch_os.intelligence import navigation_restrictions as notices
from src.portwatch_os.intelligence.current_environment import instant
from src.portwatch_os.decision.episodes import ensure_episode
from src.portwatch_os.decision.model import (DecisionProblem, DecisionOption, DecisionActor,
    DecisionEvaluation, DecisionObjective, ConstraintResult, VESSEL_ROUTING, FEASIBLE, known, unknown)
from src.portwatch_os.decision.actions import KEEP_PLAN, DELAY_ARRIVAL, CATALOGUE
from src.portwatch_os.intelligence.voyage_exposure import match, passage_for, queue

router=APIRouter()


@router.get('/intelligence/navigation-restrictions')
def listing():
    query_at = world_now()
    scoped=scoped_world()
    catalogue=notices.refresh_all()
    from backend.app.identity import current_identity
    who=current_identity.get()
    vessels=[v for v in scoped.world['fleet'] if who.role!='VESSEL_OPERATOR' or v['id'] in who.vessel_ids]
    return {**catalogue, 'voyages':[
        {k:v.get(k) for k in ('id','name','laneCode','portCode','cargo','declaredPassage','declaredPassages','possibleAssetIds','operationalEpisode')}
        for v in vessels], 'asOf':query_at.isoformat(), 'exposureQueue':queue(catalogue.get('notices',[]),vessels,query_at),
        'meaning':'The original map point identifies the restricted asset. Exposure requires an explicit declared passage; no destination or lane automatically crosses this bridge.'}


@router.get('/intelligence/voyage-exposure')
def exposure(noticeId: str = Query(None), vesselId: str = Query(None)):
    data=listing()
    if vesselId and not any(v['id']==vesselId for v in data['voyages']):
        raise HTTPException(404,'Voyage not owned by this role and visitor')
    rows=[r for r in data['exposureQueue'] if (not noticeId or noticeId in (r['noticeId'],r.get('providerNoticeId')))
          and (not vesselId or r['vesselId']==vesselId)]
    return {'asOf':data['asOf'],'relations':rows,'exposureQueue':rows,
        'counts':{state:sum(r['status']==state for r in rows) for state in (
            'CONFIRMED_DECLARED_EXPOSURE','POSSIBLE_EXPOSURE','NO_DEMONSTRATED_EXPOSURE','INSUFFICIENT_DATA')},
        'sourceRegistry':data.get('sourceRegistry',[]),
        'meaning':'Declared exposure is separate from event verification, route suitability and actual operational impact.'}


def selected_notice(payload):
    kwargs={'notice_id':payload['noticeId']} if payload.get('noticeId') else {}
    return notices.refresh(force=payload.get('refreshSource') is True, **kwargs)


@router.post('/intelligence/exposure-lead')
def exposure_lead(payload:dict=Body(...)):
    scoped,_=company()
    row=next((v for v in scoped.world['fleet'] if v['id']==payload.get('vesselId')),None)
    if not row: raise HTTPException(404,'Voyage not owned by this visitor')
    if payload.get('possible') is not True:
        raise HTTPException(422,'Explicitly mark a possible passage needing confirmation')
    notice=selected_notice(payload);asset=notice.get('areaId')
    if not asset or (payload.get('areaId') and payload['areaId']!=asset):
        raise HTTPException(422,'Select a retained notice with a reviewed stable asset mapping')
    def save(world):
        vessel=next(v for v in world['fleet'] if v['id']==row['id'])
        vessel['possibleAssetIds']=sorted(set(vessel.get('possibleAssetIds') or [])|{asset})
        return {'vesselId':row['id'],'assetId':asset,'noticeId':notice.get('noticeId'),
            'exposure':match(notice,vessel,world_now()),'createsOperationalTarget':False,
            'meaning':'Operator-marked review lead only; route membership, passage timing and vessel applicability need confirmation. No arrival, approval or measured impact changes.'}
    return scoped.save_world(save)


@router.post('/intelligence/navigation-passage-plan')
def declare(payload:dict=Body(...)):
    query_at = world_now()
    scoped,who=company()
    row=next((v for v in scoped.world['fleet'] if v['id']==payload.get('vesselId')),None)
    if not row: raise HTTPException(404,'Voyage not owned by this visitor')
    notice=selected_notice(payload)
    area=notice.get('areaId')
    zones={w.get('timeZone') for w in notice.get('windows',[]) if w.get('timeZone')}
    try:
        passage=instant(payload['passageAt']); hours=payload['postPassageHours']
        if not query_at < passage <= query_at+timedelta(days=365): raise ValueError('Declare a future passage within one year')
        if isinstance(hours,bool) or not isinstance(hours,(int,float)) or not math.isfinite(hours) or not 24<=hours<=720:
            raise ValueError('Declared onward travel must be 24–720 hours')
        if not area or payload.get('areaId') != area or payload.get('passageConfirmed') is not True:
            raise ValueError('Confirm explicit fictional passage through this bridge; destination membership is insufficient')
        if not isinstance(payload.get('openingRequired'),bool) or not isinstance(payload.get('emergencyTransit'),bool):
            raise ValueError('Explicit opening requirement and emergency-transit declaration required; exemptions do not become calculated ordinary restrictions')
        if len(zones)!=1 or payload.get('timezoneAssumption') not in zones:
            raise ValueError('Confirm the geographic local-zone assumption, which is not stated in the MSI body')
        chars=payload['characteristics']
        for key,upper in (('loaM',450),('beamM',80),('draughtM',25),('airDraughtM',80)):
            value=chars[key]
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<value<=upper:
                raise ValueError('Positive finite vessel characteristics required')
    except (KeyError,ValueError,TypeError) as exc: raise HTTPException(422,str(exc))
    episode=ensure_episode(scoped,row)
    # wall-clock: the operator declaration's receipt is actual audit time; passageAt is a distinct domain instant.
    declared_at = wall_now().isoformat()
    plan={'sourceFamily':'NAVCEN_MSI','areaId':area,'route':[area,row['portCode']],
        'noticeId':notice.get('noticeId') or payload.get('noticeId') or notice.get('noticeRef'),
        'origin':'Visitor-declared upstream passage at '+notice.get('title','reviewed asset')+'; route suitability unverified',
        'direction':'DECLARED','passageAt':passage.isoformat(),'postPassageHours':hours,
        'characteristics':{k:chars[k] for k in ('loaM','beamM','draughtM','airDraughtM')},
        'openingRequired':payload['openingRequired'],'emergencyTransit':payload['emergencyTransit'],'timezoneAssumption':payload['timezoneAssumption'],
        'alternativeAccess':'NOT_VERIFIED','operationalEpisode':episode,
        'source':'OPERATOR_DECLARED_FICTIONAL_VOYAGE','declaredAt':declared_at,'actor':who.actor}
    signature={k:v for k,v in plan.items() if k not in ('declaredAt','actor','noticeId')}
    plan['id']=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    arrival=passage+timedelta(hours=hours)
    def save(world):
        vessel=next(v for v in world['fleet'] if v['id']==row['id'])
        previous=passage_for(vessel,area)
        if previous and previous['id']==plan['id']:
            return {'vesselId':row['id'],'plan':previous,'requestedDestinationArrival':arrival.isoformat()}
        eta=(arrival-instant(world['epoch'])).total_seconds()/3600
        eta_changed=vessel['etaHours']!=eta
        latest=vessel.get('declaredPassage')
        if latest:
            vessel.setdefault('declaredPassages',{}).setdefault(latest['areaId'],latest)
        vessel.setdefault('declaredPassages',{})[area]=plan
        vessel['declaredPassage']=plan; vessel['etaHours']=eta
        proposal=world.get('terminalProposal') or {}
        consumed_asset=(((proposal.get('approvedAction') or {}).get('actionBasis') or {}).get('declaredPassage') or {}).get('areaId')
        if proposal.get('vesselId')==row['id'] and (eta_changed or consumed_asset==area):
            for key in ('terminalProposal','currentArrivalOutcome','currentArrivalReview'): world.pop(key,None)
        world.setdefault('passagePlanHistory',[]).append({'vesselId':row['id'],'plan':plan})
        return {'vesselId':row['id'],'plan':plan,'requestedDestinationArrival':arrival.isoformat()}
    return scoped.save_world(save)


@router.post('/intelligence/navigation-comparison')
def comparison(payload:dict=Body(...)):
    at = world_now()
    scoped,who=company(); row=next((v for v in scoped.world['fleet'] if v['id']==payload.get('vesselId')),None)
    if not row: raise HTTPException(404,'Voyage not owned by this visitor')
    notice=selected_notice(payload)
    plan=passage_for(row,notice.get('areaId'))
    if not plan or plan.get('sourceFamily') != 'NAVCEN_MSI': raise HTTPException(409,'Declare this specific bridge passage first')
    if notice.get('revisionId') != payload.get('revisionId'): raise HTTPException(409,'Authority revision changed; inspect current evidence')
    try:
        result=notices.planned_consequence(notice,plan)
        if instant(plan['passageAt'])<=at: raise ValueError('Declared passage is no longer future')
    except (ValueError,KeyError) as exc: raise HTTPException(409,str(exc))
    from backend.app.services.demo_terminal import company_for
    eta=instant(company_for(scoped.world).vessel(row['id']).eta)
    if eta != instant(plan['passageAt'])+timedelta(hours=plan['postPassageHours']):
        raise HTTPException(409,'Declared ETA changed; save a fresh passage plan for the same call')
    wait=result['calculatedWaitHours']; shifted=eta+timedelta(hours=wait)
    relation=match(notice,row,at)
    if not relation['calculable']:
        raise HTTPException(409,relation['calculationReason'])
    # wall-clock: comparison creation is actual application knowledge; at/computedAt remain domain query times.
    created_at = wall_now().isoformat()
    basis={'kind':'NOTICE_RESTRICTION','operationalEpisode':ensure_episode(scoped,row),
        'portCode':row['portCode'],'voyageId':row['id'],'availableAt':created_at,'evaluatedAt':at.isoformat(),
        'earliestVoyageArrival':eta.isoformat(),'plannedArrival':eta.isoformat(),'firstClearApproach':shifted.isoformat(),
        'forecastGateWaitHours':wait,'reportedFact':{**notice,'fact':notice['restriction']},
        'inferredExposure':{'route':' → '.join(plan['route']),'port':row['portCode'],'vessel':row['name'],'cargo':row['cargo'],
            'relation':relation,
            'basis':'Explicit declared bridge passage requiring an opening at the restricted time; schematic vessel location and destination do not establish exposure.'},
        'assumptions':{'kind':'OPERATOR_DECLARED_PASSAGE','postPassageHours':plan['postPassageHours'],
            'purpose':'Fixed onward travel, ordinary opening-requiring transit and geographic local-zone interpretation',
            'doesNotAssert':'Route suitability, actual opening/clearance, anchorage location, berth, fuel, cost, safety and capacity benefits are unavailable'},
        'restriction':{**result,'revisionId':notice['revisionId'],'plan':plan},
        'meaning':'Both options have identical conditional access and destination timing. Revising requested passage relocates waiting; no faster delivery or measured saving is claimed.'}
    try: notices.require_revision(basis)
    except ValueError as exc: raise HTTPException(409,str(exc))
    from src.portwatch_os.learning import intelligence_reconciliation as collector
    from backend.app.routes.shared_feedback import consumption
    public=collector.open_public()
    try: ids=[c['id'] for c in collector.collect_navigation(public,notice)]
    finally: public.close()
    basis['feedbackConsumption']=consumption(ids)
    basis['evidenceId']=hashlib.sha256(json.dumps(basis,sort_keys=True).encode()).hexdigest()
    did='dec-navigation-'+basis['evidenceId'][:20]; options=[]
    for baseline,action,label in ((True,KEEP_PLAN,'Keep passage request; wait until published opening restriction ends'),
        (False,DELAY_ARRIVAL,'Request passage after the published bridge restriction')):
        arrival=eta if baseline else shifted; passage=instant(plan['passageAt']) if baseline else instant(result['earliestScheduledAccess'])
        marks=[(instant(result['window']['start']),'restriction_start','Bridge closed-position period starts'),
            (passage,'passage_request','Declared bridge passage request'),
            (instant(result['earliestScheduledAccess']),'restriction_end','Published restriction ends; opening unconfirmed'),
            (shifted,'arrival','Conditional destination arrival with assumed onward travel')]
        options.append(DecisionOption(option_id=did+('-continue' if baseline else '-window'), action=action,label=label,
            actor=who.role,is_baseline=baseline,status=FEASIBLE,params={'arrivalAt':arrival.isoformat(),'holdHours':0 if baseline else wait},
            constraints=[ConstraintResult('scheduled_access','Ordinary bridge-opening requirement respects published closed-position interval',True,True,
                'Opening, clearance, water level and route suitability require confirmation; no emergency opening assumed',basis='evidence.intelligenceBasis.restriction')],
            assumptions=[basis['assumptions']],provenance={'source':'NAVCEN_MSI_WITH_DECLARED_PASSAGE','evidenceId':basis['evidenceId']},
            evaluation=DecisionEvaluation(objectives={'eta':known(wait,'hours',basis='Published interval end minus requested passage; same conditional destination shift for both options',confidence=None),
                'port_wait':known(wait if baseline else 0,'hours',basis='Planned wait at bridge before opening; not anchorage or arrival-to-berth wait',confidence=None),
                **{k:unknown(unit,'No supporting operational inputs or measured benefit') for k,unit in (('fuel','index'),('cost','money'),('risk','risk'),('weather','m'))}},
                derived={'destinationPort':row['portCode'],'arrivalAt':arrival.isoformat(),'arrivalShiftHours':0 if baseline else wait,
                    'holdHours':0 if baseline else wait,'requestedPassageAt':passage.isoformat(),
                    'earliestScheduledAccess':result['earliestScheduledAccess'],'actualEarliestPermittedAccess':None,
                    'earliestDestinationArrival':shifted.isoformat(),'approachClearAt':shifted.isoformat()},computed_at=at.isoformat()),
            timeline=[{'at':when.isoformat(),'hours':(when-at).total_seconds()/3600,'kind':kind,'subject':text,'label':text} for when,kind,text in marks]))
    problem=DecisionProblem(decision_id=did,created_at=created_at,domain=VESSEL_ROUTING,world_revision={'mode':get_clock().state.mode},
        world_state_id=scoped.world['epoch']+basis['evidenceId'],subject_type='vessel',subject_id=row['id'],subject_label=row['name'],
        actor=DecisionActor(role=who.role,organisation=who.organisation),at=at.isoformat(),
        objectives=[DecisionObjective('eta','Conditional destination schedule shift','hours','min','Authority interval plus declared travel'),
            DecisionObjective('port_wait','Planned bridge waiting','hours','min','Opening-requiring passage at the bridge')],
        available_actions=[{**CATALOGUE[a].to_dict(),'availability':{'status':'AVAILABLE','reason':'Conditional scheduled passage comparison'}} for a in (KEEP_PLAN,DELAY_ARRIVAL)],
        options=options,baseline_option_id=options[0].option_id,evidence={'intelligenceBasis':basis,'frontierObjectives':['eta','port_wait'],
            'restrictionAsset':{'id':notice['areaId'],'name':notice['title'],**notice['coordinates']},'subject':{'source':'FICTIONAL_DEMO'}},
        headline=row['name']+': published bridge restriction → passage window',do_nothing_statement='Keep requested passage; wait for the scheduled closed-position period to end.',notes=[basis['meaning']])
    from src.portwatch_os.decision.engine import get_engine
    return get_engine().finish(problem).to_dict()
