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


def _task_source(payload):
    if bool(payload.get("signalId")) == bool(payload.get("claimId")):
        raise HTTPException(422, "Choose exactly one retained signalId or claimId")
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
        return {"id": item["id"], "claimId": item["id"], "category": "news", "title": item["wording"],
            "fact": item["wording"], "source": item["source"], "responseSha256": item["responseSha256"],
            "availableAt": item["firstAvailableAt"], "status": "UNRESOLVED", "claim": item,
            "verification": feedback.current_assessment(public, item, as_of=wall_now().isoformat()),
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
    old = (scoped.world.get("intelligenceReviewTaskIntents") or {}).get(request_id)
    if old:
        if old["input"] != signature:
            raise HTTPException(409, "Review-task requestId already used with different inputs")
        saved = scoped.world["intelligenceReviewTasks"][old["taskId"]]
        from src.portwatch_os.ledger.store import get_ledger
        get_ledger().append_feedback("review-task", saved)
        return saved
    source = _task_source(payload)
    if source.get("category") == "economic":
        raise HTTPException(422, "FX context alone cannot create a vessel hold or operational-delay task; declare currency exposure for a separate valuation")
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
    def save(world):
        world.setdefault("intelligenceReviewTasks", {})[task["id"]] = task
        world.setdefault("intelligenceReviewTaskIntents", {})[request_id] = {"input": signature, "taskId": task["id"]}
        return task
    task = scoped.save_world(save)
    from src.portwatch_os.ledger.store import get_ledger
    get_ledger().append_feedback("review-task", task)
    return task
