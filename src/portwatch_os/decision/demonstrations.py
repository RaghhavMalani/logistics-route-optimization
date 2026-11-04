"""Explicit visitor-only teaching inputs. Never public evidence or scoring.

The ordinary engines calculate results; these inputs do not prescribe a winning
option, change equations, reserve capacity or manufacture measured outcomes.
"""
from datetime import timedelta
import copy,json,hashlib
from .episodes import new_episode
from src.portwatch_os.intelligence.public_ports import stamp

VERSION='shipping-demonstrations-v1'
TITLES=[
'Routine current port context; keep the plan','Explicit operator review threshold','Relevant report update and explicit successor','Unrelated information','Stale, unavailable or contradictory source',
'Computed rerouting before a valid branch','Too late to take the alternative','An alternative route exists but is worse','Alternative destination requires a different approval basis',
'Slow steaming to the same approach window','Speeding up for a hard deadline','Delay departure instead of anchorage waiting','Departure hold unavailable at sea','Weather approach gate','Insufficient forecast coverage',
'Required cargo connection fits','Required cargo connection fails','Later sailing proposal','Optional cargo and missing compatibility','Port action and capacity limits','News, economics and FX context',
'Approval, query, rejection and withdrawal','Accepted plan, restart and retry','Close a journey and begin a distinct call','No plan, feasible option or sufficient evidence','Observation, camera, twin and learning limits']
BLOCKED={'S09':'A destination change needs separately declared cargo, terminal, onward and authority suitability; this preset supplies none.',
         'S20':'Independent per-voyage ranking is not joint berth/slot reservation. Existing scoped Port and schematic twin views remain inspectable.',
         'S21':'The existing feedback views retain news/FX vintages. No declared FX exposure/settlement product is implemented here.',
         'S26':'Authorized camera footage and independently validated corrections/models are not available from a teaching preset. Existing learning and schematic twin views remain inspectable.'}


def catalogue():
    return [{'id':f'S{i:02}','title':title,'status':'BLOCKED_INPUT' if f'S{i:02}' in BLOCKED else 'REAL_SOURCE_CONTEXT' if i==1 else 'RUNNABLE_SIMULATED',
             'basis':'Current retained official metadata + explicitly fictional owned call' if i==1 else 'Illustrative voyage/source assumptions; not an actual event',
             'missingInputs':BLOCKED.get(f'S{i:02}'),'safeToRepeat':'Explicit selection begins a distinct owned call; earlier records remain inspectable. Stable requestId retries return the original result.',
             'uiRoute':'/company/global-eye#intelligence-review','authority':'Company creates a comparison; Port and Vessel actions remain separate.'} for i,title in enumerate(TITLES,1)]


def _hash(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def forecast(at,scenario):
    start=at.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
    gate=26 if scenario in {'S01','S02','S03','S04','S10','S12','S14','S16','S18','S22','S23','S24'} else 0
    count=23 if scenario=='S15' else 73
    rows=[{'validAt':stamp(start+timedelta(hours=h)),'wind_gusts_10m':22. if h<gate else 8.,'visibility':10000.,'wave_height':None} for h in range(count)]
    original={'scenario':scenario,'referenceAt':stamp(at),'hourly':rows,'meaning':'Explicit software forecast fixture; not provider observations, reanalysis or weather verification'}
    sha=_hash(original)
    return {'portCode':'INPRT','sources':{'surface':{'status':'SIMULATED','source':'ILLUSTRATIVE_SCENARIO_HOURLY','snapshotId':'fixture-hourly-'+sha[:20],
            'responseSha256':sha,'availableAt':stamp(at),'issuedAt':None,'evidenceKind':'SOFTWARE_LIFECYCLE_FIXTURE'},'hazards':{'status':'UNAVAILABLE','snapshotId':None}},
            'hourly':rows,'daily':[],'regionalHazards':[],'fixtureOriginal':original}


def context_fixture(at,value,status='CURRENT_ELIGIBLE'):
    from src.portwatch_os.intelligence import public_port_context as source
    identity=_hash(['LABELLED_FIXTURE',stamp(at),value,status])
    return {'sourceFamily':source.FAMILY,'portCode':'INPRT','policyVersion':source.POLICY,'status':status,'reason':'SOFTWARE LIFECYCLE FIXTURE; no authority report or actual port event is asserted.',
            'reportDate':at.date().isoformat(),'availableAt':stamp(at),'firstReceivedAt':stamp(at),'lastSuccessfulCheckAt':stamp(at),'publicationAt':None,
            'revisionId':'fixture-context-'+identity,'snapshotId':'fixture-snapshot-'+identity,'originalStatus':'SOFTWARE_FIXTURE_NOT_AUTHORITY_ORIGINAL',
            'evidenceKind':'SOFTWARE_LIFECYCLE_FIXTURE','sourceUse':{'attribution':'Explicit software fixture, not Paradip-issued data','scope':'Illustrative aggregate only; excluded from real operational scoring','policy':'Not an authority publication','fullDocumentDownload':False},
            'metrics':[{'id':'ANCHORAGE_READY_ROWS','value':value,'unit':'illustrative listed rows','section':'Illustrative ready-anchorage table','precision':'ILLUSTRATIVE_INSTANT','asOf':stamp(at),'pages':[],
                        'eligibility':status,'meaning':'Threshold fixture only; no individual waiting hours, actual readiness or port closure.'}]}


def prepare(scoped,scenario,at,*,panel_replay=False):
    if scenario not in {r['id'] for r in catalogue()}:raise ValueError('Unknown bounded scenario identity')
    if scenario in BLOCKED:return {'blocked':BLOCKED[scenario]}
    old=next(v for v in scoped.world['fleet'] if v['id']=='PWD-001')
    episode=new_episode(scoped,{**old,'portCode':'INPRT'})
    is_route=scenario in {'S06','S07','S08'}
    hours=500 if scenario in {'S06','S08'} else -8 if scenario=='S07' else 24
    weather=forecast(at,scenario)
    illustrative={'forecast':weather}
    if scenario in {'S02','S03','S05'}:illustrative['portContext']=context_fixture(at,4,'LATEST_AVAILABLE' if scenario=='S05' else 'CURRENT_ELIGIBLE')
    if scenario=='S04':illustrative['unrelatedReport']={'portCode':'INMAA','value':999,'meaning':'Unconsumed illustrative report, not a Paradip dependency'}
    marker={'contractVersion':VERSION,'id':scenario,'title':TITLES[int(scenario[1:])-1],'selectedAt':stamp(at),
            'basis':'Illustrative voyage and source assumptions; real official port context is separately labelled.',
            'scope':'Visitor-owned DEMO only; no real operational target, booking or measured benefit'}
    if panel_replay:
        marker.update(panelReplay=True, scope='Offline replay rehearsal with fictional S10 inputs only')
    def update(world):
        vessel=next(v for v in world['fleet'] if v['id']=='PWD-001')
        vessel.update(portCode='INPRT',operationalEpisode=episode,hoursToRisk=hours,laneCode='EUR_IND',serviceSpeedKn=12.,etaHours=(at-scoped_epoch(world)).total_seconds()/3600+20)
        vessel.pop('declaredPassage',None);vessel.pop('declaredPassages',None)
        if is_route:
            from .routing import routes_for
            routes=routes_for('EUR_IND','INPRT',{'SUEZ':hours},12.)
            if routes:vessel.update(lat=routes.position[0],lon=routes.position[1],etaHours=(at-scoped_epoch(world)).total_seconds()/3600+routes.remaining_primary_nm/12.)
        world['portCode']='INPRT';world['demoScenario']=marker;world['illustrativeInputs']=illustrative
        world.setdefault('operationalEpisodes',{})[episode['id']]=episode
        world.setdefault('scenarioHistory',[]).append(marker)
        world['event']={**world['event'],'closureHours':720 if scenario=='S06' else 12 if scenario=='S08' else 72}
        for key in ('terminalProposal','currentArrivalReview','currentArrivalOutcome'):world.pop(key,None)
        return copy.deepcopy(world)
    latest=scoped.save_world(update);scoped.world.clear();scoped.world.update(latest)
    if is_route:return {'routing':True,'episode':episode,'marker':marker}
    reference=at+timedelta(minutes=5) if scenario=='S12' else at
    if scenario=='S12':
        def future_eta(world):
            next(v for v in world['fleet'] if v['id']=='PWD-001')['etaHours']=(reference-scoped_epoch(world)).total_seconds()/3600+20
        scoped.save_world(future_eta)
        next(v for v in scoped.world['fleet'] if v['id']=='PWD-001')['etaHours']=(reference-scoped_epoch(scoped.world)).total_seconds()/3600+20
    plan={'schemaVersion':1,'referenceKind':'NOT_DEPARTED' if scenario=='S12' else 'AT_SEA','referenceAt':stamp(reference),'referenceLabel':'Explicit illustrative remaining-passage reference',
          'declaredAt':stamp(at),'remainingDistanceNm':240.,'distanceBasis':'Illustrative scalar distance; not measured AIS, routing geometry or safe navigation',
          'baselineSpeedKn':12.,'baselineArrivalAt':stamp(reference+timedelta(hours=20)),'minSpeedKn':8.,'maxSpeedKn':18.,'alternativeSpeedKn':16. if scenario=='S11' else 10.,
          'finance':{'consumption':{'referenceSpeedKn':12.,'referencePropulsionTonnesPerDay':24.,'auxiliaryTonnesPerDay':2.,'anchorageTonnesPerDay':2.,'departureHoldTonnesPerDay':2.,
              'minSpeedKn':8.,'maxSpeedKn':18.,'loadCondition':'Unchanged illustrative load','source':'Explicit simplified teaching assumption, not measured vessel performance','declaredAt':stamp(at)}}}
    if scenario=='S11':plan['deadlineAt']=stamp(at+timedelta(hours=18))
    if scenario=='S12':plan.update(departureHoldPermitted=True,departureHoldLocation='Explicit fictional origin holding location',departureDelayHours=6.)
    if scenario=='S13':plan.update(departureHoldPermitted=True,departureHoldLocation='Invalid at-sea departure hold',departureDelayHours=6.)
    arrival={'plannedArrival':stamp(reference+timedelta(hours=15 if scenario=='S11' else 20)),'maxGustKn':15.,'minVisibilityM':5000.,'passagePlan':plan}
    if scenario in {'S16','S17','S18','S19','S22','S23','S24'}:
        cutoff=27 if scenario=='S17' else 30 if scenario=='S18' else 33
        cargo_epoch=at.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
        connection={'vesselId':'FICTIONAL-FEEDER','name':'Illustrative unreserved onward sailing','departureAt':stamp(cargo_epoch+timedelta(hours=cutoff+2)),
                    'loadingCutoffAt':stamp(cargo_epoch+timedelta(hours=cutoff)),'onwardPorts':['SGSIN'],'availableTeu':100.,'availableDeadweightT':1000.,'availableReeferPlugs':None if scenario=='S19' else 30,
                    'acceptsHazardous':True,'acceptsOog':True,'basis':'Explicit fictional schedule and unreserved capacity'}
        later={**connection,'vesselId':'FICTIONAL-LATER-FEEDER','name':'Illustrative later sailing, not booked','departureAt':stamp(cargo_epoch+timedelta(hours=cutoff+26)), 'loadingCutoffAt':stamp(cargo_epoch+timedelta(hours=cutoff+24))}
        arrival['cargoCommitment']={'schemaVersion':1,'fictionalShipment':True,'voyageId':'PWD-001','portCode':'INPRT','declaredAt':stamp(at),'basis':'Explicit teaching shipment, not an actual booking','mustMeet':scenario!='S19',
            'shipment':{'shipmentId':'ILLUSTRATIVE-CARGO-'+scenario,'teu':24.,'cargoClass':'reefer' if scenario=='S19' else 'dry','destinationPort':'SGSIN','weightT':240.},
            'transfer':{'approachToStartHours':2.,'basis':'Explicit assumption before inbound handling starts','acceptedSchematicHandling':True,'gangs':1,'mode':'DIRECT'},
            'bookedConnection':connection,'laterConnections':[later] if scenario=='S18' else []}
    if scenario=='S25':arrival['plannedArrival']=stamp(at+timedelta(hours=200))
    return {'arrival':arrival,'episode':episode,'marker':marker}


def scoped_epoch(world):
    from src.portwatch_os.learning.weather_feedback import instant
    return instant(world['epoch'])
