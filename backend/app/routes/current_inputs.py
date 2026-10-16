"""Current public inputs and visitor-owned proposal review in original workflows."""
import copy
from datetime import timedelta
from fastapi import APIRouter, Body, HTTPException, Query
from backend.app.identity import current_identity
from src.utils import port_registry
from src.portwatch_os.clock import get_clock, LIVE, wall_now
from src.portwatch_os.sandbox import current_sandbox
from src.portwatch_os.decision.continuation import connected_basis
from src.portwatch_os.intelligence.current_environment import bundle, map_signals, instant, ensure_current, retain_feedback

router = APIRouter()


def public_mode():
    if current_sandbox.get() is not None: return
    from src.portwatch_os.deployment import resolve_mode
    if resolve_mode(None)[0] == "COMMERCIAL":
        raise HTTPException(403,"This current input adapter uses the non-commercial public API product")


@router.get("/intelligence/current")
def current(portCode: str = Query("INNSA")):
    public_mode()
    port = port_registry.resolve(portCode)
    if port is None: raise HTTPException(404,"Port is not registered")
    if get_clock().state.mode != LIVE:
        return {"status":"HISTORICAL_UNAVAILABLE","portCode":port.locode,"sources":{},"hourly":[],"daily":[],"regionalHazards":[]}
    result = bundle(port)
    retain_feedback(port)
    return result


@router.get("/weather/current-map")
def weather_map():
    public_mode()
    if get_clock().state.mode != LIVE: return []
    ensure_current()
    return map_signals()


def demo_issuer():
    scoped, who = current_sandbox.get(), current_identity.get()
    if scoped is None or who is None:
        raise HTTPException(403,"Visitor-owned demonstration only")
    if who.role not in ("PORT_AUTHORITY","NATIONAL_ADMIN"):
        raise HTTPException(403,"The port desk reviews Company proposals")
    return scoped, who


@router.get("/decisions/current-proposals")
def proposals():
    scoped, who = demo_issuer()
    from src.portwatch_os.decision.engine import get_engine
    journeys = dict(scoped.world.get("weatherJourneys") or {})
    latest = scoped.world.get("terminalProposal") or {}
    if latest.get("environmentEvidenceId"):
        journeys.setdefault(latest["decisionId"], {"proposal":latest,"reviewDecisionId":scoped.world.get("currentArrivalReview")})
    rows = []
    for key, journey in reversed(list(journeys.items())):
        proposal = journey.get("proposal")
        source = get_engine().get(key)
        if not proposal or source is None: continue
        env = connected_basis(source)
        if who.role == "PORT_AUTHORITY" and env["portCode"] != who.port_code: continue
        rows.append({**proposal,"subject":source.subject_label,"evidence":env,
                     "evidenceKind":"restriction" if env.get('kind')=='NOTICE_RESTRICTION' else "intelligence" if source.evidence.get("intelligenceBasis") else "weather",
                     "reviewDecisionId":journey.get("reviewDecisionId") or (scoped.world.get("currentArrivalReview") if key == latest.get("decisionId") else None)})
    return {"proposals":rows}


@router.post("/decisions/current-proposals/review")
def review_proposal(payload: dict = Body(...)):
    scoped, who = demo_issuer()
    journey = (scoped.world.get("weatherJourneys") or {}).get(payload.get("decisionId"), {})
    proposal = journey.get("proposal") or scoped.world.get("terminalProposal") or {}
    if not proposal.get("environmentEvidenceId") or proposal.get("decisionId") != payload.get("decisionId"):
        raise HTTPException(404,"No submitted current-input proposal in this visitor's world")
    from src.portwatch_os.decision.engine import get_engine
    from src.portwatch_os.decision.model import DecisionActor, COMPUTED, APPROVED
    engine = get_engine(); source = engine.get(proposal["decisionId"])
    if source is None or source.workflow != APPROVED:
        raise HTTPException(409,"The Company proposal must have a computed, approved decision")
    env = connected_basis(source)
    existing = journey.get("reviewDecisionId") or (scoped.world.get("currentArrivalReview") if (scoped.world.get("terminalProposal") or {}).get("decisionId")==source.decision_id else None)
    if existing and engine.get(existing): return engine.get(existing).to_dict()
    if who.role == "PORT_AUTHORITY" and env["portCode"] != who.port_code:
        raise HTTPException(403,"This proposal belongs to another port")
    from src.portwatch_os.decision.continuation import require_current
    require_current(source)
    problem = copy.deepcopy(source)
    problem.decision_id = source.decision_id+"-port"
    problem.actor = DecisionActor(role=who.role,organisation=who.organisation,port_code=env["portCode"])
    problem.workflow, problem.workflow_history, problem.human_choice = COMPUTED, [], None
    problem.created_at = wall_now().isoformat()
    problem.evidence["companyProposal"] = {"decisionId":source.decision_id,"optionId":proposal["optionId"],
        "environmentEvidenceId":env["evidenceId"],"meaning":"Port review of the identical frozen Company input/assumptions"}
    if env.get("operationalEpisode"):
        problem.evidence["companyProposal"].update(operationalEpisode=env["operationalEpisode"],
            approvedAction=proposal.get("approvedAction"))
    for option in problem.options: option.actor = who.role
    problem = engine.finish(problem)
    def save(world):
        world["currentArrivalReview"] = problem.decision_id
        world.setdefault("weatherJourneys", {}).setdefault(source.decision_id, {"proposal":proposal})["reviewDecisionId"] = problem.decision_id
    scoped.save_world(save)
    return problem.to_dict()


@router.post("/decisions/problems/{decision_id}/demo-outcome")
def demo_outcome(decision_id: str):
    scoped, who = demo_issuer()
    from src.portwatch_os.decision.engine import get_engine
    from src.portwatch_os.advisories.store import get_advisory_store
    from backend.app.routes.advisories import principal_from_request
    engine = get_engine(); problem = engine.get(decision_id)
    reviews = {j.get("reviewDecisionId") for j in scoped.world.get("weatherJourneys", {}).values()}
    reviews.add(scoped.world.get("currentArrivalReview"))
    if problem is None or decision_id not in reviews:
        raise HTTPException(404,"No weather proposal review in this visitor's world")
    env = connected_basis(problem)
    ids = problem.evidence.get("advisories") or []
    store = get_advisory_store(); rows = [store.get(i) for i in ids]
    if env and who.role == "PORT_AUTHORITY" and env["portCode"] != who.port_code:
        raise HTTPException(403,"This review belongs to another port")
    saved = problem.evidence.get("demoOutcome")
    if saved and rows and all(r and r.state == "completed" for r in rows):
        # A crash may have closed the advisories before updating the workflow
        # and world mirror. Redrive only those durable bookkeeping steps.
        if problem.workflow == "PROPOSED": engine.transition(decision_id,"ISSUED",actor=who.actor,note="Recovered completed advisory audit")
        if problem.workflow == "ISSUED": engine.transition(decision_id,"ACCEPTED",actor=who.actor,note="Recovered Vessel acceptance")
        problem.evidence["demoOutcome"] = saved
        engine._record(problem)
        def recover(world):
            if (world.get("terminalProposal") or {}).get("environmentEvidenceId") == saved["environmentEvidenceId"]:
                world["currentArrivalOutcome"] = saved
            if saved.get("simulatedAction"):
                action = saved["simulatedAction"]
                world.setdefault("operationalActions", {})[action["id"]] = action
        scoped.save_world(recover)
        return {"outcome":saved,"advisories":[r.to_dict() for r in rows]}
    if not env or not rows or any(r is None or r.state not in ("accepted", "completed") for r in rows):
        raise HTTPException(409,"Every linked advisory must be issued, acknowledged and accepted before a demo outcome")
    from src.portwatch_os.decision.continuation import require_current
    require_current(problem)
    if any((connected_basis(r) or {}).get("evidenceId") != env["evidenceId"] for r in rows):
        raise HTTPException(409,"Frozen input evidence no longer matches the advisory")
    choice = problem.option(problem.human_choice)
    outcome = {"kind":"SIMULATED_DEMO_OUTCOME","recordKind":"SIMULATED_DEMO_OUTCOME","environmentEvidenceId":env["evidenceId"],
        "requestedArrival":choice.evaluation.derived["arrivalAt"],"clearApproachAt":env.get("firstClearApproach"),
        "baselineAssumedWaitHours":env.get("forecastGateWaitHours",0),
        "selectedAssumedWaitHours":choice.evaluation.objectives["eta"].value if problem.evidence.get("intelligenceBasis") else choice.evaluation.objectives["port_wait"].value,
        "evidenceKind":"intelligence" if problem.evidence.get("intelligenceBasis") else "weather",
        "note":env["meaning"] if problem.evidence.get("intelligenceBasis") else "Reproduced from the frozen forecast/approach assumptions; not an independent observed outcome, forecast verification, berth guarantee or measured saving."}
    from backend.app.routes.decisions import _approved_operational_action
    approved = _approved_operational_action(problem, choice)
    if approved:
        from src.portwatch_os.learning.shared_feedback import identifier
        action = {**approved, "kind": "SIMULATED_DEMO_ACTION", "recordKind": "SIMULATED_OPERATIONAL_RECORD",
            "id": "sim-action-" + identifier([decision_id, approved["operationalActionId"]]),
            "recordedAt": wall_now().isoformat(), "simulatedTargetAt": choice.evaluation.derived.get("requestedPassageAt") or choice.evaluation.derived["arrivalAt"],
            "actualExecutionStatus": "NOT_OBSERVED", "actualExecutionAt": None,
            "eligibleForRealTarget": False,
            "meaning": "Reproduces the accepted conditional plan in this fictional visitor world; no real vessel action or actual operational record is asserted."}
        outcome.update(operationalEpisode=env["operationalEpisode"],
            operationalActionId=approved["operationalActionId"], simulatedAction=action,
            realOutcomeStatus="PENDING_ACTUAL_RECORDS", eligibleForRealTarget=False)
    if env.get('kind')=='NOTICE_RESTRICTION':
        outcome.update(evidenceKind='restriction',selectedAssumedWaitHours=choice.evaluation.objectives['port_wait'].value,
            requestedPassage=choice.evaluation.derived['requestedPassageAt'],earliestScheduledAccess=env['restriction']['earliestScheduledAccess'],
            totalScheduleShiftHours=env['restriction']['totalScheduleShiftHours'],noticeRevisionId=env['restriction']['revisionId'],
            calculation=env['restriction'])
    principal = principal_from_request(who.actor,who.role,who.port_code,who.organisation,None)
    for row in rows:
        row.evidence["demoOutcome"] = outcome
        store._write(row)
        if row.state != "completed": store.act(row.advisory_id,"completed",principal=principal,reason=outcome["note"])
    if problem.workflow == "PROPOSED":
        engine.transition(decision_id,"ISSUED",actor=who.actor,note="Original advisory was issued and answered by the vessel")
    if problem.workflow == "ISSUED":
        engine.transition(decision_id,"ACCEPTED",actor=who.actor,note="Vessel acceptance is retained in the advisory audit")
    # The demo result is deliberately NOT resolved into the observation/accuracy ledger.
    problem.evidence["demoOutcome"] = outcome
    engine._record(problem)
    def save_outcome(world):
        if outcome.get("simulatedAction"):
            action = outcome["simulatedAction"]
            world.setdefault("operationalActions", {})[action["id"]] = action
        source = (problem.evidence.get("companyProposal") or {}).get("decisionId")
        if source: world.setdefault("weatherJourneys", {}).setdefault(source, {})["outcome"] = outcome
        if (world.get("terminalProposal") or {}).get("environmentEvidenceId") == env["evidenceId"]:
            world["currentArrivalOutcome"] = outcome
    scoped.save_world(save_outcome)
    return {"outcome":outcome,"advisories":[store.get(i).to_dict() for i in ids]}


@router.post("/decisions/problems/{decision_id}/refresh")
def refresh_comparison(decision_id: str):
    scoped, who = current_sandbox.get(), current_identity.get()
    if scoped is None or who is None or who.role != "SHIPPING_COMPANY":
        raise HTTPException(403,"Company refreshes its own frozen comparison")
    from src.portwatch_os.decision.engine import get_engine
    from backend.app.routes.decisions import create_problem, _visible_or_403
    engine = get_engine(); source = engine.get(decision_id)
    if source is None or not connected_basis(source) or source.actor.role != who.role:
        raise HTTPException(404,"No Company connected comparison in this visitor's records")
    _visible_or_403(source, who)
    previous = source.evidence.get("successorDecisionId")
    if previous and engine.get(previous):
        return engine.get(previous).to_dict()
    env = connected_basis(source)
    if env.get('kind')=='NOTICE_RESTRICTION':
        if env['restriction'].get('sourceFamily') == 'NAVCEN_MSI':
            from backend.app.routes.navigation_restrictions import comparison
            from src.portwatch_os.intelligence.navigation_restrictions import refresh
            notice_id=env['reportedFact'].get('noticeId') or env['reportedFact'].get('providerNoticeId')
            latest=refresh(force=True,**({'notice_id':notice_id} if notice_id else {}))
        else:
            from backend.app.routes.operational_notices import comparison
            from src.portwatch_os.intelligence.operational_notices import refresh
            latest=refresh(force=True)
        result=comparison({'vesselId':source.subject_id,'revisionId':latest.get('revisionId'),
            **({'noticeId':latest.get('noticeId')} if latest.get('noticeId') else {})})
    elif source.evidence.get("intelligenceBasis"):
        from backend.app.routes.shipping_intelligence import comparison
        result=comparison({"signalId":env["reportedFact"]["id"],"vesselId":source.subject_id,
                           "assumedHoldHours":env["assumptions"]["assumedHoldHours"],
                           "feedbackClaimIds":[i["claim"]["id"] for i in env.get("feedbackConsumption",{}).get("inputs",[])]})
    else:
        result = create_problem({"domain":"vessel", "vesselId":source.subject_id,
            "currentArrival":{"plannedArrival":env["plannedArrival"], **{k:env["assumptions"][k] for k in ("maxGustKn","minVisibilityM")}}},
            actor_name=who.actor, role=who.role, header_port=who.port_code, organisation=who.organisation,
            vessel_ids=",".join(who.vessel_ids))
    successor = engine.get(result["decisionId"])
    successor.evidence["predecessorDecisionId"] = source.decision_id
    source.evidence["successorDecisionId"] = successor.decision_id
    engine._record(successor); engine._record(source)
    return successor.to_dict()
