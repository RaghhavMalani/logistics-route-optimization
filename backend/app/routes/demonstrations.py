"""Explicit visitor-only presets, evaluated by the ordinary engines."""
import copy,json,re
from fastapi import APIRouter,Body,HTTPException
from backend.app.identity import current_identity
from backend.app.routes.shipping_intelligence import scoped_world
from backend.app.routes.operational_notices import company
from src.portwatch_os.clock import world_now,get_clock,LIVE
from src.portwatch_os.decision import demonstrations as examples
from src.portwatch_os.panel_runtime import pinned_panel_at
from src.portwatch_os.sandbox import current_sandbox

router=APIRouter()


@router.get('/demonstrations/scenarios')
def catalogue():
    panel = pinned_panel_at() is not None
    if not panel:
        scoped_world()
    rows = examples.catalogue()
    if panel:
        rows = [row for row in rows if row['id'] == 'S10']
    return {'version':examples.VERSION,'scenarios':rows,'meaning':'Explicit fictional inputs, existing calculations. Excluded from real archives/scoring.'}


@router.get('/demonstrations/selection')
def selection():
    scoped = current_sandbox.get() if pinned_panel_at() is not None else scoped_world()
    return {'selection':scoped.world.get('demoScenario')}


@router.post('/demonstrations/select')
def select(payload:dict=Body(...)):
    panel = pinned_panel_at() is not None
    if panel:
        scoped, who = current_sandbox.get(), current_identity.get()
        if who.role != 'SHIPPING_COMPANY':
            raise HTTPException(403, 'Company declares and compares its own voyage')
        if payload.get('scenarioId') != 'S10':
            raise HTTPException(409, 'The offline panel only runs the fictional S10 passage')
    else:
        scoped,who=company()
    if set(payload)-{'scenarioId','requestId','acknowledged'} or payload.get('acknowledged') is not True or not re.fullmatch(r'[a-zA-Z0-9-]{8,80}',str(payload.get('requestId',''))):
        raise HTTPException(422,'Explicit acknowledgement, bounded scenarioId and stable requestId required')
    scenario=payload.get('scenarioId');request_id=payload['requestId']
    if scenario not in {r['id'] for r in examples.catalogue()}:raise HTTPException(422,'Unknown scenario')
    old=scoped.world.get('scenarioRequests',{}).get(request_id)
    if old:
        if old['scenarioId']!=scenario:raise HTTPException(409,'Request identity already belongs to another scenario')
        result=copy.deepcopy(old['result'])
        if result.get('decisionId'):
            from src.portwatch_os.decision.engine import get_engine
            problem=get_engine().get(result.pop('decisionId'))
            if problem is None:raise HTTPException(409,'Retained comparison unavailable; inspect recovery status rather than recomputing the selection')
            result['problem']=problem.to_dict()
        return result
    if not panel and get_clock().state.mode!=LIVE:raise HTTPException(409,'Return to Live before selecting a new illustrative call')
    at=world_now();prepared=examples.prepare(scoped,scenario,at,panel_replay=panel)
    result={'scenarioId':scenario,'status':'BLOCKED_INPUT','missingInputs':prepared.get('blocked'),'selectedAt':at.isoformat()}
    if not prepared.get('blocked'):
        fixture=scoped.world['illustrativeInputs']['forecast']
        original=json.dumps(fixture['fixtureOriginal'],sort_keys=True).encode()
        folder=scoped.root/'scenario_evidence';folder.mkdir(parents=True,exist_ok=True)
        path=folder/(fixture['sources']['surface']['responseSha256']+'.response')
        if not path.exists():path.write_bytes(original)
        body={'domain':'vessel','vesselId':'PWD-001','mode':'DEMO'}
        if prepared.get('routing'):body['eventId']=scoped.world['event']['id']
        else:body['currentArrival']=prepared['arrival']
        from backend.app.routes.decisions import _create_problem
        try:
            problem=_create_problem(body,who.actor,who.role,who.port_code,who.organisation,','.join(who.vessel_ids),panel_fixture=panel)
            result.update(status='RUNNABLE_SIMULATED',problem=problem,inputs=body,episode=prepared['episode'])
        except HTTPException as exc:
            if exc.status_code not in (400,422):raise
            result.update(missingInputs=exc.detail,inputs=body,episode=prepared['episode'])
    def save(world):
        retained=copy.deepcopy(result);problem=retained.pop('problem',None)
        if problem:retained['decisionId']=problem['decisionId']
        world.setdefault('scenarioRequests',{})[request_id]={'scenarioId':scenario,'result':retained}
        if not prepared.get('blocked'):world['demoScenario'].update(decisionId=(result.get('problem') or {}).get('decisionId'),status=result['status'])
    scoped.save_world(save)
    return result


@router.post('/demonstrations/advance-source')
def advance_source(payload:dict=Body(...)):
    scoped,who=company()
    if payload!={'acknowledged':True} or (scoped.world.get('demoScenario') or {}).get('id')!='S03':raise HTTPException(422,'Only explicitly selected S03 can advance')
    def update(world):
        current=world['illustrativeInputs']['portContext']
        if current['metrics'][0]['value']==7:return current
        successor=examples.context_fixture(world_now(),7);successor['previousRevisionId']=current['revisionId']
        world.setdefault('illustrativeSourceHistory',[]).append(copy.deepcopy(current))
        world['illustrativeInputs']['portContext']=successor
        return successor
    return {'context':scoped.save_world(update),'meaning':'Software fixture only; not an authority revision'}
