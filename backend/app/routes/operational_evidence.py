"""Shared public evidence, visitor-owned context selection; no collection writes."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.app.identity import current_identity
from backend.app.routes.shipping_intelligence import scoped_world
from src.portwatch_os.clock import wall_now
from src.portwatch_os.intelligence import operational_feed as feed

router = APIRouter()


@router.get("/intelligence/operational-evidence")
def operational_evidence():
    # wall-clock: live-source availability and age use actual collection time, never visitor scenario time.
    scoped, now = scoped_world(), wall_now()
    who = current_identity.get()
    fleet = scoped.world["fleet"]
    if who.role == "VESSEL_OPERATOR":
        fleet = [v for v in fleet if v["id"] in who.vessel_ids]
    if who.role == "PORT_AUTHORITY":
        fleet = [v for v in fleet if v["portCode"] == who.port_code]
    from src.portwatch_os.intelligence.oceans_x import qualification_status
    return {"contractVersion": feed.VERSION, "asOf": feed.stamp(now), "products": feed.latest_products(now),
        "voyages": [{"id": v["id"], "name": v.get("name") or v["id"], "portCode": v["portCode"]} for v in fleet],
        "oceansQualification": qualification_status(), "realResolvedTargetsAdded": 0,
        "meaning": "Public evidence can support an explicit context review. It does not establish actual execution by a visitor vessel or a numerical shipping consequence."}


@router.get("/intelligence/operational-evidence/original")
def original(product: str, port_code: str = Query(..., alias="portCode"),
             snapshot_id: str | None = Query(None, alias="snapshotId"),
             receipt_id: str | None = Query(None, alias="receiptId")):
    scoped_world()
    # wall-clock: originals are readable only after actual backend receipt.
    now = wall_now()
    try:
        if product == "PUBLIC_PORT_PDF" and port_code in feed.PORTS:
            path = feed.get_service().evidence(port_code, feed._key(snapshot_id), now)
            media = "application/pdf"
        elif product == "IMF_PORTWATCH_DAILY" and port_code in feed.IMF_PORTS:
            archive = feed.get_aggregate()
            receipt = next((r for r in archive.receipts(now, port_code) if r["receiptId"] == feed._key(receipt_id)), None)
            if not receipt:
                raise ValueError("Receipt unavailable")
            path = archive.evidence(receipt, now)
            media = "application/json"
        else:
            raise ValueError("Product/port unavailable")
    except (OSError, ValueError) as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, media_type=media, filename=path.name,
        headers={"Cache-Control": "private, no-store"})
