"""Contextual shipping evidence and durable nonnumerical verification tasks."""
import hashlib
import json
from fastapi import APIRouter, Body, HTTPException
from backend.app.identity import current_identity
from src.portwatch_os.sandbox import current_sandbox
from src.portwatch_os.clock import wall_now, get_clock, LIVE
from src.portwatch_os.intelligence.shipping_signals import signals_for, ROOT
from src.portwatch_os.intelligence.current_environment import instant

router=APIRouter()

def scoped_world():
    scoped=current_sandbox.get()
    if not scoped: raise HTTPException(403,"This comparison uses a visitor-owned demonstration fleet")
    if get_clock().state.mode!=LIVE: raise HTTPException(409,"Current intelligence is unavailable in replay")
    return scoped

@router.get("/intelligence/shipping-signals")
def signals():
    world=scoped_world().world
    who=current_identity.get()
    if who.role=='VESSEL_OPERATOR':
        world={**world,'fleet':[v for v in world['fleet'] if v['id'] in who.vessel_ids]}
    return signals_for(world)


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

def _owned_vessel(scoped, vessel_id):
    row = next((v for v in scoped.world["fleet"] if v["id"] == vessel_id), None)
    if not row:
        raise HTTPException(404, "Vessel not owned by this visitor")
    return row


def _retained_signal(signal_id):
    if not isinstance(signal_id, str) or len(signal_id) != 64 or any(c not in "0123456789abcdef" for c in signal_id):
        raise HTTPException(422, "Select an archived signal")
    path = ROOT / "shipping_intelligence" / (signal_id + ".json")
    if not path.is_file():
        raise HTTPException(404, "Signal evidence unavailable")
    return json.loads(path.read_text())


@router.post("/intelligence/shipping-comparison")
def comparison(payload: dict = Body(...)):
    scoped = scoped_world()
    if current_identity.get().role != "SHIPPING_COMPANY":
        raise HTTPException(403, "Company reviews its own voyage evidence")
    signal = _retained_signal(payload.get("signalId"))
    _owned_vessel(scoped, payload.get("vesselId"))
    if signal.get("category") == "economic":
        raise HTTPException(422, "FX context alone cannot create a vessel hold; declared currency exposure and settlement dates are required for valuation")
    raise HTTPException(422, {"reason": "This contextual report has no supported numerical shipping consequence. Create a source and voyage verification task; no generic review hold is calculated.",
        "reviewTaskEndpoint": "/intelligence/review-tasks", "signalId": signal["id"]})


def _operational_evidence(selector):
    from src.portwatch_os.intelligence.operational_feed import resolve_evidence
    try:
        # wall-clock: retained live evidence must exist before this request's audit time.
        return resolve_evidence(selector, wall_now())
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from exc


def _task_source(payload, *, destination_port=None):
    if sum(bool(payload.get(k)) for k in ("signalId", "claimId", "operationalEvidence")) != 1:
        raise HTTPException(422, "Choose exactly one retained signalId, claimId or operationalEvidence selector")
    if payload.get("operationalEvidence"):
        from src.portwatch_os.intelligence.evidence_dispositions import task_source
        try:
            # wall-clock: a context task records the real receipt and operator review time.
            at = wall_now()
            return task_source(_operational_evidence(payload["operationalEvidence"]),
                context_confirmed=payload.get("portContextConfirmed"), destination_port=destination_port,
                now=at)
        except (ValueError, TypeError) as exc:
            raise HTTPException(409, str(exc)) from exc
    if payload.get("signalId"):
        signal = _retained_signal(payload["signalId"])
        digest = signal.get("responseSha256", "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise HTTPException(409, "Original signal response unavailable")
        paths = (ROOT / "shipping_intelligence" / (digest + ".response"), ROOT / "archive" / (digest + ".response"))
        if not any(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest for path in paths):
            raise HTTPException(409, "Original signal response unavailable or corrupt")
        return signal
    from src.portwatch_os.learning import intelligence_reconciliation as collector
    from src.portwatch_os.learning import shared_feedback as feedback
    from backend.app.routes.shared_feedback import require_originals
    public = collector.open_public()
    try:
        found = public.feedback("claim", payload["claimId"])
        if not found:
            raise HTTPException(404, "Retained feedback claim unavailable")
        item = found[0]
        if item.get("target", {}).get("series") == "DEXINUS":
            raise HTTPException(422, "FX observations and forecasts remain economic context; declared amounts, currency and settlement date are required for valuation")
        if not public.feedback("news-source-quality", item["id"]):
            raise HTTPException(422, "Reviewed authority notices use the explicit passage/exposure workflow")
        try:
            require_originals({"inputs": [{"claim": item}]})
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        # wall-clock: source assessment is bounded by real information availability.
        assessed_at = wall_now().isoformat()
        from src.portwatch_os.ledger.store import get_ledger
        frozen=feedback.freeze_consumption(public,get_ledger(),[item['id']],assessed_at)
        return {"id": item["id"], "claimId": item["id"], "category": "news", "title": item["wording"],
            "fact": item["wording"], "source": item["source"], "responseSha256": item["responseSha256"],
            "availableAt": item["firstAvailableAt"], "status": "UNRESOLVED", "claim": item,
            "verification": frozen['inputs'][0]['assessment'],
            "feedbackConsumption":frozen,
            "relationship": "Reported evidence requiring source and voyage confirmation; no quantified operational delay"}
    finally:
        public.close()


@router.get("/intelligence/review-tasks")
def review_tasks():
    scoped = scoped_world()
    who = current_identity.get()
    rows = list((scoped.world.get("intelligenceReviewTasks") or {}).values())
    if who.role == "VESSEL_OPERATOR":
        rows = [row for row in rows if row["vesselId"] in who.vessel_ids]
    if who.role == "PORT_AUTHORITY":
        rows = [row for row in rows if row["portCode"] == who.port_code]
    from src.portwatch_os.ledger.store import get_ledger
    from src.portwatch_os.intelligence.evidence_dispositions import project_task
    dispositions = get_ledger().feedback("review-task-disposition")
    rows = [project_task(row, [d for d in dispositions if d["taskId"] == row["id"]]) for row in rows]
    # Only the visitor's consumed claims are checked. Public counts/descriptive
    # weights are not dependencies, and this projection never rewrites tasks.
    if any((row.get('source') or {}).get('claim') for row in rows):
        from src.portwatch_os.learning import intelligence_reconciliation as collector
        from src.portwatch_os.learning import shared_feedback as feedback
        from src.portwatch_os.clock import world_now
        public=collector.open_public();at=world_now().isoformat()
        try:
            for row in rows:
                source=row.get('source') or {};item=source.get('claim')
                if not item:continue
                current=feedback.news_assessment(public,item,at)
                reason='Consumed source assessment and applicability are unchanged; no numerical action is inferred'
                changed=[]
                frozen=source.get('feedbackConsumption') or {'inputs':[{'claim':item,'assessment':source.get('verification')} ]}
                try:
                    feedback.require_consumption(public,frozen,now=at)
                    if feedback.retained_original_status(public,item):
                        raise ValueError('Consumed original is unavailable or corrupt; review remains required')
                    initial=source.get('verification')
                    if initial and feedback.assessment_dependency(current)!=feedback.assessment_dependency(initial):
                        raise ValueError('Consumed verification or applicability changed; inspect current source evidence and request fresh review')
                except ValueError as exc:
                    changed=['consumedVerificationOrApplicability'];reason=str(exc)
                row['sourceReview']={'status':'REVIEW_REQUIRED' if changed else 'UNCHANGED','asOf':at,
                    'reason':reason,'requiresFreshReview':bool(changed),'currentAssessment':current,
                    'changedFields':changed,'realOperationalTargetsAdded':0}
        finally:public.close()
    return {"tasks": sorted(rows, key=lambda row: (row["createdAt"], row["id"]), reverse=True),
        "meaning": "Durable requests to verify evidence and exposure, not voyage approvals, measured effects or executed actions"}


@router.post("/intelligence/review-tasks")
def create_review_task(payload: dict = Body(...)):
    scoped = scoped_world()
    who = current_identity.get()
    if who.role != "SHIPPING_COMPANY":
        raise HTTPException(403, "Company requests verification for its own voyage")
    vessel = _owned_vessel(scoped, payload.get("vesselId"))
    request_id = payload.get("requestId")
    if not isinstance(request_id, str) or not 8 <= len(request_id) <= 100:
        raise HTTPException(422, "A stable requestId is required for safe verification-task retries")
    signature = {k: payload.get(k) for k in ("signalId", "claimId", "vesselId")}
    if payload.get("operationalEvidence"):
        signature.update({k: payload.get(k) for k in ("operationalEvidence", "portContextConfirmed")})
    old = (scoped.world.get("intelligenceReviewTaskIntents") or {}).get(request_id)
    if old:
        if old["input"] != signature:
            raise HTTPException(409, "Review-task requestId already used with different inputs")
        from src.portwatch_os.ledger.store import get_ledger
        original = get_ledger().feedback("review-task", old["taskId"])
        saved = original[0] if original else {k: v for k, v in scoped.world["intelligenceReviewTasks"][old["taskId"]].items()
            if k != "dispositionIds"}
        get_ledger().append_feedback("review-task", saved)
        return saved
    source = _task_source(payload, destination_port=vessel["portCode"])
    if source.get("category") == "economic":
        raise HTTPException(422, "FX context alone cannot create a vessel hold or operational-delay task; declare currency exposure for a separate valuation")
    # wall-clock: task creation is an operator audit event on the live receipt stream.
    at = wall_now()
    if not source.get("availableAt") or instant(source["availableAt"]) > at:
        raise HTTPException(409, "The retained source was unavailable at this review request")
    from src.portwatch_os.decision.episodes import ensure_episode
    from src.portwatch_os.intelligence.voyage_exposure import match
    from src.portwatch_os.learning.shared_feedback import identifier
    episode = ensure_episode(scoped, vessel)
    task = {"id": "review-" + identifier([str(scoped.root), request_id]), "kind": "SOURCE_EXPOSURE_VERIFICATION_TASK",
        "status": "PENDING_VERIFICATION", "createdAt": at.isoformat(), "actor": who.actor,
        "vesselId": vessel["id"], "vesselName": vessel["name"], "portCode": vessel["portCode"],
        "operationalEpisode": episode, "source": source, "evidence": source,
        "exposure": match(source, vessel, at), "requestedAction": "VERIFY_SOURCE_APPLICABILITY_AND_PASSAGE",
        "reason": "Review the attributed source, identify a precise restriction or event target and confirm the declared voyage exposure before calculating an operational effect.",
        "missingOperationalInputs": ["reviewed effective restriction", "confirmed asset/route membership", "applicable target period", "supporting consequence inputs"],
        "calculatedDelayHours": None, "calculatedCost": None, "createsOperationalTarget": False,
        "actualExecutionStatus": "NOT_OBSERVED", "meaning": "Task creation does not confirm the report, approve a voyage change or demonstrate actual execution."}
    if source.get("operationalEvidence"):
        from src.portwatch_os.intelligence.evidence_dispositions import TASK_QUESTION
        task.update(taskQuestion=TASK_QUESTION, requestedAction="INSPECT_AVAILABLE_PORT_CONTEXT",
            reason="Inspect the exact publisher record and its relationship to the selected voyage. Context review does not establish vessel identity, an actual arrival or a restriction.",
            missingOperationalInputs=["confirmed real-vessel association", "comparable individual event definition", "supported operational consequence inputs"],
            sourceClaimStatus="UNRESOLVED")
    def save(world):
        world.setdefault("intelligenceReviewTasks", {})[task["id"]] = task
        world.setdefault("intelligenceReviewTaskIntents", {})[request_id] = {"input": signature, "taskId": task["id"]}
        return task
    task = scoped.save_world(save)
    from src.portwatch_os.ledger.store import get_ledger
    get_ledger().append_feedback("review-task", task)
    return task


@router.post("/intelligence/review-tasks/{task_id}/dispositions")
def review_task_disposition(task_id: str, payload: dict = Body(...)):
    """Add an attributed context inspection; never ingest caller-supplied outcomes."""
    scoped, who = scoped_world(), current_identity.get()
    task = (scoped.world.get("intelligenceReviewTasks") or {}).get(task_id)
    if not task:
        raise HTTPException(404, "Review task unavailable in this visitor's workspace")
    _owned_vessel(scoped, task["vesselId"])
    if who.role not in ("SHIPPING_COMPANY", "PORT_AUTHORITY") or (
            who.role == "PORT_AUTHORITY" and task["portCode"] != who.port_code):
        raise HTTPException(403, "Company or the task's port authority reviews its own evidence context")
    permitted = {"requestId", "operationalEvidence", "dispositionType", "contextConfirmed", "note"}
    if set(payload) - permitted:
        raise HTTPException(422, "Only retained evidence selectors and an attributed context review are accepted")
    request_id = payload.get("requestId")
    if not isinstance(request_id, str) or not 8 <= len(request_id) <= 100:
        raise HTTPException(422, "A stable requestId is required for safe disposition retries")
    if payload.get("dispositionType") != "CONTEXT_REVIEWED" or payload.get("contextConfirmed") is not True:
        raise HTTPException(422, "Explicit CONTEXT_REVIEWED confirmation is required; this is not source or outcome verification")
    note = payload.get("note", "")
    if not isinstance(note, str) or len(note) > 1000:
        raise HTTPException(422, "The optional review note must be text of at most 1000 characters")
    from src.portwatch_os.ledger.store import get_ledger
    from src.portwatch_os.learning.shared_feedback import identifier
    from src.portwatch_os.intelligence.evidence_dispositions import build_disposition
    ledger = get_ledger()
    disposition_id = "review-disposition-" + identifier([str(scoped.root), task_id, request_id])
    signature = {k: payload.get(k) for k in sorted(permitted) if k != "requestId"}
    old = ledger.feedback("review-task-disposition", disposition_id)
    if old:
        if old[0]["request"] != signature:
            raise HTTPException(409, "Disposition requestId already identifies a different review")
        return old[0]
    original = ledger.feedback("review-task", task_id)
    if not original:
        raise HTTPException(409, "The frozen original task is unavailable")
    try:
        # wall-clock: an attributed context inspection records when the operator reviewed it.
        reviewed_at = wall_now()
        disposition = build_disposition(original[0], _operational_evidence(payload.get("operationalEvidence")),
            namespace=str(scoped.root), request_id=request_id, who=who, now=reviewed_at, note=note)
    except (ValueError, TypeError) as exc:
        raise HTTPException(409, str(exc)) from exc
    disposition["request"] = signature
    ledger.append_feedback("review-task-disposition", disposition)
    def save(world):
        stored = world["intelligenceReviewTasks"][task_id]
        pointers = stored.setdefault("dispositionIds", [])
        if disposition["id"] not in pointers:
            pointers.append(disposition["id"])
        return disposition
    return scoped.save_world(save)
