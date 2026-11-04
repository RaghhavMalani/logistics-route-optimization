"""Scoped daily context; reads never instantiate writable PublicPilot."""
from fastapi import APIRouter,Body,HTTPException,Query
from backend.app.identity import current_identity
from backend.app.services.demo_terminal import demo_hulls
from backend.app.services import public_collection_queue
from backend.app.routes.shipping_intelligence import scoped_world
from backend.app.routes.operational_notices import company
from src.portwatch_os.clock import world_now,wall_now
from src.portwatch_os.learning.weather_feedback import instant
from src.portwatch_os.intelligence import port_context_review as review,public_port_context as source
from src.portwatch_os.intelligence.public_ports import digest
from src.portwatch_os.decision.episodes import ensure_episode
import json

router=APIRouter()


@router.get('/intelligence/port-context')
def listing(vesselId:str=Query(None)):
    scoped=scoped_world()
    vessels=demo_hulls(scoped.world)
    if vesselId and not any(v['id']==vesselId for v in vessels):raise HTTPException(404,'Owned voyage unavailable')
    at=world_now();data=review.view(scoped.world,at)
    return {'context':data, 'refreshPending': 'INPRT_CONTEXT' in public_collection_queue.active(), 'voyages':[{'id':v['id'],'name':v['name'],'portCode':v['portCode'],'episodeId':(v.get('operationalEpisode') or {}).get('id'),'rule':review.rule_for(scoped.world,v['id'])} for v in vessels],
            'meaning':'Public destination context is shared; declarations and review criteria belong to this visitor only.'}


@router.get('/intelligence/port-context/audit')
def audit(vesselId:str=Query(None),asOf:str=Query(None)):
    data=listing(vesselId)
    if asOf:
        from backend.app.routes.shared_feedback import inspection_time
        at=instant(inspection_time(asOf));data['context']=review.view(scoped_world().world,at)
        for vessel in data['voyages']:
            if vessel['rule'] and instant(vessel['rule']['declaredAt'])>at:vessel['rule']=None
    return {**data,'contractVersion':'port-context-audit-v1','realOperationalTargetsResolved':0,'fullDocumentDownload':False}


@router.post('/intelligence/port-context/refresh', status_code=202)
def refresh(payload:dict=Body(...)):
    scoped_world();who=current_identity.get()
    if who.role not in ('SHIPPING_COMPANY','PORT_AUTHORITY','NATIONAL_ADMIN'):raise HTTPException(403,'Company/Port/Admin explicit source review required')
    if payload!={'portCode':'INPRT'}:raise HTTPException(422,'Only the fixed approved Paradip family is supported; no caller URLs or paths')
    from src.portwatch_os.intelligence.public_collection import get_service
    def collect():
        get_service().refresh('INPRT', who.actor, report_limit=1)
    public_collection_queue.enqueue('INPRT_CONTEXT', collect)
    return listing()


@router.post('/intelligence/port-context/rule')
def declare(payload:dict=Body(...)):
    scoped,who=company();vessel=next((v for v in scoped.world['fleet'] if v['id']==payload.get('vesselId')),None)
    if not vessel:raise HTTPException(404,'Owned voyage unavailable')
    if set(payload)-{'vesselId','metricId','threshold','acknowledged','declareDestination'}:raise HTTPException(422,'Unsupported rule fields')
    threshold=payload.get('threshold')
    if payload.get('acknowledged') is not True or payload.get('declareDestination') is not True or payload.get('metricId') not in source.METRICS or isinstance(threshold,bool) or not isinstance(threshold,int) or not 1<=threshold<=1000:
        raise HTTPException(422,'Explicit fictional INPRT destination, supported metric and integer operator threshold are required')
    if vessel['portCode']!='INPRT':
        from src.portwatch_os.decision.episodes import new_episode
        episode=new_episode(scoped,{**vessel,'portCode':'INPRT'})
        vessel['operationalEpisode']=episode
    else:episode=ensure_episode(scoped,vessel)
    # wall-clock: an operator rule's actual audit receipt is separate from report and passage time.
    at=wall_now()
    rule={'contractVersion':review.VERSION,'vesselId':vessel['id'],'portCode':'INPRT','episodeId':episode['id'],'metricId':payload['metricId'],
          'threshold':threshold,'operator':'>=','basis':'Explicit operator review criterion; not authority forecast, congestion or waiting-hours equation'}
    rule['id']=digest(json.dumps(rule,sort_keys=True));rule['declaredAt']=at.isoformat();rule['actor']=who.actor
    def save(world):
        old=review.rule_for(world,vessel['id'])
        if old and old['id']==rule['id']:return old
        row=next(v for v in world['fleet'] if v['id']==vessel['id']);row['portCode']='INPRT';world['portCode']='INPRT'
        row['operationalEpisode']=episode;world.setdefault('operationalEpisodes',{})[episode['id']]=episode
        world.setdefault('portContextRules',{})[vessel['id']]=rule
        world.setdefault('portContextRuleHistory',[]).append(rule)
        return rule
    return scoped.save_world(save)
