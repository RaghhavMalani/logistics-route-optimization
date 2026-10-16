"""Public source feedback and visitor-owned consumption; no demo evidence writes."""
import json
from fastapi import APIRouter, Body, HTTPException
from src.portwatch_os.clock import wall_now
from src.portwatch_os.learning import shared_feedback as feedback
from src.portwatch_os.learning import intelligence_reconciliation as collector
from src.portwatch_os.ledger.store import get_ledger
from backend.app.routes.shipping_intelligence import scoped_world
from backend.app.identity import current_identity

router = APIRouter()


@router.post('/intelligence/operational-calls')
def begin_operational_call(payload: dict = Body(...)):
    scoped = scoped_world()
    if current_identity.get().role != 'SHIPPING_COMPANY':
        raise HTTPException(403, 'Company declares its own next call')
    vessel = next((v for v in scoped.world['fleet'] if v['id'] == payload.get('vesselId')), None)
    if not vessel:
        raise HTTPException(404, 'Vessel not owned by this visitor')
    if payload.get('newCallConfirmed') is not True:
        raise HTTPException(422, 'Confirm a distinct new call; an ETA edit is not a new call')
    from src.portwatch_os.decision.episodes import begin_call
    try:
        return begin_call(scoped, vessel, payload['requestedArrival'], payload.get('requestId'))
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc))


@router.get("/intelligence/feedback")
def inspection():
    store = collector.open_public()
    try:
        result = feedback.inspect(store, wall_now().isoformat())
        runs = store.feedback("run")
        result["collector"] = max(runs, key=lambda r: r["ranAt"]) if runs else {"status": "COLLECTING", "failures": []}
        return result
    finally:
        store.close()


@router.get("/intelligence/feedback/impacts")
def impacts():
    scoped_world()
    return feedback.inspect(get_ledger(), wall_now().isoformat())


@router.get("/intelligence/feedback/evidence/{digest}")
def original(digest: str):
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise HTTPException(404, "Original unavailable")
    for folder in ("shared_feedback", "operational_notices"):
        path = collector.ROOT/folder/(digest+".response")
        if path.is_file():
            raw = path.read_bytes()
            if feedback.hashlib.sha256(raw).hexdigest() != digest:
                raise HTTPException(503, "Original hash mismatch")
            # PDF bytes remain a downloadable original, not an invented summary.
            if raw.startswith(b"%PDF"):
                from fastapi.responses import Response
                return Response(raw, media_type="application/pdf", headers={"Content-Disposition": "inline; filename=authority-original.pdf"})
            from fastapi.responses import Response
            return Response(raw, media_type="application/octet-stream",
                headers={"Content-Disposition": f"attachment; filename={digest}.response", "X-Source-SHA256": digest})
    raise HTTPException(404, "Retained original unavailable")


@router.post("/intelligence/feedback/comparison")
def comparison(payload: dict = Body(...)):
    scoped = scoped_world()
    if current_identity.get().role != "SHIPPING_COMPANY":
        raise HTTPException(403, "Company proposes its own comparison")
    store = collector.open_public()
    try:
        found = store.feedback("claim", payload.get("claimId", ""))
        if not found:
            raise HTTPException(422, "Select a retained claim")
        item = found[0]
        economic = item["target"].get("series") == "DEXINUS"
        if economic:
            raise HTTPException(422, 'A reference-rate forecast does not justify a vessel hold. Declare currency amounts and settlement dates before a separate valuation comparison; none are currently supplied.')
        quality = store.feedback("news-source-quality", item["id"])
        if not quality:
            raise HTTPException(422, "Authority notice exposure uses the declared-route comparison")
        raise HTTPException(422, {"reason": "This report requires source and voyage verification; no numerical consequence or generic vessel hold is supported.",
            "reviewTaskEndpoint": "/intelligence/review-tasks", "claimId": item["id"]})
    finally:
        store.close()


def consumption(ids):
    store = collector.open_public()
    try:
        frozen = feedback.freeze_consumption(store, get_ledger(), ids, wall_now().isoformat())
        require_originals(frozen)
        return frozen
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    finally:
        store.close()


def require_originals(frozen):
    from src.portwatch_os.intelligence import operational_notices
    from src.portwatch_os.intelligence import navigation_restrictions
    for entry in frozen["inputs"]:
        item = entry["claim"]
        digests = {row["responseSha256"] for row in [item, *item.get("inputs", [])] if row.get("responseSha256")}
        if not digests:
            raise ValueError("Consumed claim has no retained original response")
        for digest in digests:
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Invalid source response identifier")
            paths = [collector.ROOT/"shared_feedback"/(digest+".response"),
                     operational_notices.ROOT/"operational_notices"/(digest+".response"),
                     navigation_restrictions.ROOT/"operational_notices"/(digest+".response")]
            if not any(path.is_file() and feedback.hashlib.sha256(path.read_bytes()).hexdigest() == digest for path in paths):
                raise ValueError("Consumed original source response unavailable or corrupt; prior evidence remains saved")
