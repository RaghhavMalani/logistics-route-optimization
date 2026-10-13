"""Shipping exposure and explicitly assumed scheduling through original workflows."""
from datetime import timedelta
import hashlib
import json
from fastapi import APIRouter, Body, HTTPException
from backend.app.identity import current_identity
from src.portwatch_os.sandbox import current_sandbox
from src.portwatch_os.clock import wall_now, get_clock, LIVE
from src.portwatch_os.intelligence.shipping_signals import signals_for, ROOT
from src.portwatch_os.intelligence.current_environment import instant
from src.portwatch_os.decision.model import (DecisionProblem,DecisionOption,DecisionActor,DecisionEvaluation,DecisionObjective,
    ConstraintResult,VESSEL_ROUTING,FEASIBLE,known,unknown)
from src.portwatch_os.decision.actions import KEEP_PLAN,DELAY_ARRIVAL,CATALOGUE

router=APIRouter()

def scoped_world():
    scoped=current_sandbox.get()
    if not scoped: raise HTTPException(403,"This comparison uses a visitor-owned demonstration fleet")
    if get_clock().state.mode!=LIVE: raise HTTPException(409,"Current intelligence is unavailable in replay")
    return scoped

@router.get("/intelligence/shipping-signals")
def signals():
    return signals_for(scoped_world().world)


@router.get("/intelligence/shipping-evidence/{digest}")
def source_evidence(digest:str):
    if len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest): raise HTTPException(404,"Source evidence unavailable")
    for directory in ("shipping_intelligence","archive"):
        path=ROOT/directory/(digest+".response")
        if path.is_file():
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=digest: raise HTTPException(503,"Source evidence hash mismatch")
            try: response=json.loads(raw)
            except ValueError: response=raw.decode("utf-8",errors="replace")
            return {"sha256":digest,"response":response}
    raise HTTPException(404,"Original source response unavailable")

@router.post("/intelligence/shipping-comparison")
def comparison(payload:dict=Body(...)):
    scoped=scoped_world();who=current_identity.get()
    if who.role!="SHIPPING_COMPANY": raise HTTPException(403,"Company proposes its own scheduling comparison")
    identifier=payload.get("signalId")
    if not isinstance(identifier,str) or len(identifier)!=64 or any(c not in "0123456789abcdef" for c in identifier): raise HTTPException(422,"Select an archived signal")
    path=ROOT/"shipping_intelligence"/(identifier+".json")
    if not path.is_file(): raise HTTPException(404,"Signal evidence unavailable")
    signal=json.loads(path.read_text())
    # Exposure is recomputed from this visitor's declared fleet, not accepted from the caller.
    from backend.app.services.demo_terminal import company_for
    vessel=company_for(scoped.world).vessel(payload.get("vesselId"))
    if not vessel: raise HTTPException(404,"Vessel not owned by this visitor")
    codes=signal.get("portCodes") or ([v["portCode"] for v in scoped.world["fleet"]] if signal["category"]=="economic" else [])
    if vessel.destination_port not in codes or (signal.get("laneCodes") and vessel.lane_code not in signal["laneCodes"]): raise HTTPException(409,"Selected signal has no declared exposure to this voyage")
    hold=payload.get("assumedHoldHours")
    if isinstance(hold,bool) or not isinstance(hold,(int,float)) or not 1<=hold<=24: raise HTTPException(422,"Explicit review-hold assumption must be 1–24 hours")
    at=wall_now();eta=instant(vessel.eta)
    if eta<=at: raise HTTPException(409,"Voyage arrival must remain future")
    basis={"kind":"INTELLIGENCE_SCENARIO","portCode":vessel.destination_port,"voyageId":vessel.vessel_id,
        "availableAt":at.isoformat(),"availabilityBasis":"Scenario freeze time; source first receipt and validity remain in reportedFact",
        "plannedArrival":eta.isoformat(),"earliestVoyageArrival":eta.isoformat(),
        "reportedFact":signal,"inferredExposure":{"route":vessel.lane_code,"port":vessel.destination_port,"vessel":vessel.name,
            "cargo":next(v["cargo"] for v in scoped.world["fleet"] if v["id"]==vessel.vessel_id),
            "basis":"Destination/lane membership in the fictional visitor world; geographic and causal exposure needs confirmation"},
        "assumptions":{"kind":"OPERATOR_REVIEW_HOLD","assumedHoldHours":hold,"purpose":"Allow additional source/port verification before arrival",
            "source":"OPERATOR_DEMO_ASSUMPTION","doesNotAssert":"No current port closure, hazard-caused delay, safer passage or measured saving"},
        "meaning":"Reported evidence → inferred shipping exposure → explicit scheduling scenario. Delay/cost caused by the event are unavailable."}
    basis["evidenceId"]=hashlib.sha256(json.dumps(basis,sort_keys=True).encode()).hexdigest()
    did="dec-intelligence-"+basis["evidenceId"][:20]; options=[]
    for action,hours,baseline,label in ((KEEP_PLAN,0,True,"Continue current arrival plan"),(DELAY_ARRIVAL,hold,False,"Propose an assumed review hold before arrival")):
        arrival=(eta+timedelta(hours=hours)).isoformat()
        options.append(DecisionOption(option_id=did+("-continue" if baseline else "-review"),action=action,label=label,actor=who.role,is_baseline=baseline,status=FEASIBLE,
            params={"arrivalAt":arrival,"holdHours":hours},constraints=[ConstraintResult("future_arrival","Future declared arrival",True,True,"Arrival computed from declared ETA plus explicit hold assumption",basis="evidence.intelligenceBasis.earliestVoyageArrival")],
            assumptions=[basis["assumptions"]],provenance={"source":"INTELLIGENCE_SCENARIO","evidenceId":basis["evidenceId"]},
            evaluation=DecisionEvaluation(objectives={"eta":known(hours,"hours",basis="Operator-assumed hold added to declared arrival; not event-caused delay",confidence=None),
                **{k:unknown(unit,"No supporting event-to-operational-effect inputs") for k,unit in (("port_wait","hours"),("risk","risk"),("fuel","index"),("cost","money"),("weather","m"))}},
                derived={"destinationPort":vessel.destination_port,"arrivalAt":arrival,"arrivalShiftHours":hours,"holdHours":hours},computed_at=at.isoformat()),
            timeline=[{"at":arrival,"kind":"arrival","label":"Declared arrival plus explicit review-hold assumption"}]))
    problem=DecisionProblem(decision_id=did,created_at=at.isoformat(),domain=VESSEL_ROUTING,world_revision={"mode":"LIVE"},world_state_id=scoped.world["epoch"]+basis["evidenceId"],
        subject_type="vessel",subject_id=vessel.vessel_id,subject_label=vessel.name,actor=DecisionActor(role=who.role,organisation=who.organisation),at=at.isoformat(),
        objectives=[DecisionObjective("eta","Assumed schedule shift","hours","min","Explicit operator review hold")],
        available_actions=[{**CATALOGUE[a].to_dict(),"availability":{"status":"AVAILABLE","reason":"Explicit bounded scheduling assumption"}} for a in (KEEP_PLAN,DELAY_ARRIVAL)],
        options=options,baseline_option_id=options[0].option_id,evidence={"intelligenceBasis":basis,"frontierObjectives":["eta"],"subject":{"source":"FICTIONAL_DEMO"}},
        headline=f"{vessel.name}: {signal['category']} evidence and review-hold comparison",do_nothing_statement="Continue the declared arrival. This source does not establish event-caused delay or a port closure.",notes=[basis["meaning"]])
    from src.portwatch_os.decision.engine import get_engine
    return get_engine().finish(problem).to_dict()
