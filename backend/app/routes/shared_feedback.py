"""Public source feedback and visitor-owned consumption; no demo evidence writes."""
import json
from fastapi import APIRouter, Body, HTTPException, Query
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


def inspection_time(value=None):
    try:
        now=wall_now()
        at=feedback.instant(value) if value else now
        if at>now:raise ValueError('An as-of view cannot inspect future application knowledge')
        return at.isoformat()
    except (TypeError,ValueError) as exc:
        raise HTTPException(422,'Use an aware as-of instant no later than now') from exc


def collector_projection(store,as_of):
    def availability(row):
        # A run's start is not the availability of its completed result. Legacy
        # rows lack a completion clock, so conservatively include later known
        # nested check/receipt/assessment clocks in their visibility boundary.
        clocks=[]
        fields={'ranAt','completedAt','firstAvailableAt','receivedAt','checkedAt','assessedAt','availableAt'}
        def collect(value):
            if isinstance(value,dict):
                for key,nested in value.items():
                    if key in fields and nested is not None:
                        clocks.append(feedback.instant(nested))
                    elif isinstance(nested,(dict,list)):
                        collect(nested)
            elif isinstance(value,list):
                for nested in value:collect(nested)
        collect(row)
        return max(clocks) if clocks else None
    runs=[]
    for row in store.feedback('run'):
        try:
            available=availability(row)
        except (TypeError,ValueError):
            continue  # An unqualified result clock cannot support an as-of view.
        if available is not None and available<=feedback.instant(as_of):
            runs.append((available,row))
    return max(runs,key=lambda pair:(pair[0],pair[1]['id']))[1] if runs else {'status':'COLLECTING','failures':[]}


@router.get("/intelligence/feedback")
def inspection(asOf: str | None = None, kind: str = 'ALL', offset: int = Query(0,ge=0), limit: int = Query(100,ge=1,le=100), claimId: str | None = None):
    store = collector.open_public()
    try:
        at=inspection_time(asOf)
        result = feedback.inspect(store,at,kind=kind,offset=offset,limit=limit,claim_id=claimId)
        result['collector']=collector_projection(store,at)
        return result
    except ValueError as exc:
        raise HTTPException(422,'Unsupported feedback selection') from exc
    finally:
        store.close()


@router.get('/intelligence/feedback/audit')
def audit(asOf: str | None = None,kind: str = 'ALL',claimId: str | None = None):
    """Full declared public selection, never a page or a visitor ledger."""
    from fastapi.responses import Response
    store=collector.open_public()
    try:
        at=inspection_time(asOf)
        result=feedback.inspect(store,at,kind=kind,limit=max(1,len(store.feedback('claim'))),claim_id=claimId)
        result['dataset'].update(complete=True,exportScope='SELECTED_CLAIM_AS_OF' if claimId else 'ALL_FILTERED_RETAINED_PUBLIC_CLAIMS_AS_OF')
        claims=result['claims'];digests={r.get('responseSha256') for c in claims for r in [c,*c.get('inputs',[])] if r.get('responseSha256')}
        evidence_ids={e['id'] for c in claims for e in c.get('outcomes',[])}
        for c in claims:
            detail=c.get('economicInspection') or {}
            evidence_ids.update(e['evidenceId'] for e in detail.get('outcomeVintages',[]))
            evidence_ids.update((c.get('newsInspection',{}).get('currentAssessment') or {}).get('evidenceIds',[]))
        evidence=[e for e in store.feedback('evidence') if e['id'] in evidence_ids and feedback.instant(e['firstAvailableAt'])<=feedback.instant(at)]
        digests.update(e['responseSha256'] for e in evidence)
        receipts=[{k:v for k,v in r.items() if k!='archivePath'} for r in store.feedback('receipt') if r.get('responseSha256') in digests and feedback.instant(r.get('firstAvailableAt') or r['receivedAt'])<=feedback.instant(at)]
        result.update(auditVersion='shared-feedback-audit-v2',evidence=evidence,receipts=receipts,collector=collector_projection(store,at))
        encoded=json.dumps(result,sort_keys=True,allow_nan=False).encode()
        return Response(encoded,media_type='application/json',headers={'Content-Disposition':'attachment; filename=portwatch-feedback-audit.json','X-Audit-SHA256':feedback.hashlib.sha256(encoded).hexdigest()})
    except ValueError as exc:
        raise HTTPException(422,'Unsupported feedback audit selection') from exc
    finally:store.close()


@router.get("/intelligence/feedback/impacts")
def impacts():
    scoped_world()
    return feedback.inspect(get_ledger(), wall_now().isoformat())


@router.get("/intelligence/feedback/evidence/{digest}")
def original(digest: str):
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise HTTPException(404, "Original unavailable")
    from pathlib import Path
    from src.portwatch_os.intelligence import operational_notices, navigation_restrictions
    store=collector.open_public()
    try:
        local_only=[q for q in store.feedback('news-source-quality') if q.get('originalAccess')=='LOCAL_RESEARCH_ARCHIVE']
        claims={c['id']:c for c in store.feedback('claim')}
        receipts=[r for r in store.feedback('receipt') if r.get('responseSha256')==digest]
        records=[*claims.values(),*store.feedback('evidence')]
        records.extend(i for c in claims.values() for i in c.get('inputs',[]))
        if not receipts and not any(r.get('responseSha256')==digest for r in records):
            raise HTTPException(404,'Public retained original unavailable')
        if (any(claims.get(q['id'],{}).get('responseSha256')==digest for q in local_only)
                or any(r.get('productId')=='GAC_EASTHAM_NOTICE_ANNOUNCEMENT_V1' for r in receipts)):
            raise HTTPException(403,'Original retained for local research; full-response redistribution is unqualified. Inspect the attributed source URL and retained hash.')
        roots=[collector.ROOT,operational_notices.ROOT,navigation_restrictions.ROOT]
        if getattr(store,'path',None) and str(store.path)!=':memory:':
            roots.append(Path(store.path).parent)
        paths=[Path(root)/folder/(digest+'.response') for root in roots for folder in ('shared_feedback','operational_notices')]
        for receipt in receipts:
            if receipt.get('archivePath'):
                path=Path(receipt['archivePath'])
                # Internal collector metadata only; the caller supplies a hash,
                # never a filesystem selector. Match the archive naming contract.
                if path.name==digest+'.response' and path.parent.name in ('shared_feedback','operational_notices'):
                    paths.append(path)
    finally:store.close()
    corrupt=False
    for path in dict.fromkeys(paths):
        if path.is_file():
            raw = path.read_bytes()
            if feedback.hashlib.sha256(raw).hexdigest() != digest:
                corrupt=True
                continue
            # PDF bytes remain a downloadable original, not an invented summary.
            if raw.startswith(b"%PDF"):
                from fastapi.responses import Response
                return Response(raw, media_type="application/pdf", headers={"Content-Disposition": "inline; filename=authority-original.pdf"})
            from fastapi.responses import Response
            return Response(raw, media_type="application/octet-stream",
                headers={"Content-Disposition": f"attachment; filename={digest}.response", "X-Source-SHA256": digest})
    if corrupt:
        raise HTTPException(503, "Original hash mismatch")
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
