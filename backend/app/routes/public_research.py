"""Anonymous, read-only projections of public evidence and published research.

Explicit DTOs exclude private camera URLs, vessel/operator identities, decisions,
advisories, permissions and tenant records. No collection or fitting on requests.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.app.services import cache_service as cache
from src.portwatch_os.clock import LIVE, get_clock, wall_now
from src.portwatch_os.global_eye.exposure import build_impact
from src.portwatch_os.global_eye.ingest import from_news_bundle
from src.utils import port_registry

router = APIRouter(prefix="/public")
ROOT = Path(__file__).resolve().parents[3]


@router.get("/port-calls")
def port_calls():
    from backend.app.services.public_cases import public_calls
    try:
        return public_calls()
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503, "Public case publication failed integrity verification") from None
    except (sqlite3.DatabaseError, OSError):
        return {"available": False, "asOf": get_clock().now().isoformat(), "ports": [], "cases": [],
            "meaning": "Public port-call evidence is unavailable; historical research remains independently available."}


@router.get("/port-calls/evidence/{sha}.pdf")
def public_evidence(sha: str):
    from backend.app.services.public_cases import document, publication, packaged_document
    from src.portwatch_os.intelligence.public_collection import get_service
    now = get_clock().now()
    try:
        folder, data = publication(now)
        path = packaged_document(folder, data, sha, now)
        if not path:
            store = get_service()
            snapshots = [s for port in ("INPRT", "INMAA") for s in store.snapshots(port, now)]
            path = document(store, snapshots, sha)
    except (ValueError, KeyError, TypeError, OSError, sqlite3.DatabaseError):
        raise HTTPException(503, "Public evidence storage or integrity check is unavailable") from None
    if not path:
        raise HTTPException(404, "Public evidence is unavailable or failed hash verification")
    return FileResponse(path, media_type="application/pdf", headers={
        "Cache-Control": "no-store", "ETag": f'"{sha}"', "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'inline; filename="public-port-{sha}.pdf"'})


@router.get("/port-calls/{case_id}/audit")
def public_case_audit(case_id: str):
    from fastapi.responses import JSONResponse
    case = next((c for c in port_calls()["cases"] if c["caseId"] == case_id), None)
    if not case:
        raise HTTPException(404, "A visually reviewed public case is not available")
    return JSONResponse(case, headers={"Cache-Control": "no-store",
        "Content-Disposition": f'attachment; filename="{case["portCode"]}-public-case.json"'})


def release_root():
    return Path(os.getenv("PORTWATCH_PUBLIC_RESEARCH_DIR") or ROOT / "data/research_release")


def release():
    try:
        pointer = json.loads((release_root() / "current.json").read_text(encoding="utf-8"))
        version = pointer["releaseId"]
        if not re.fullmatch(r"research-[a-f0-9]{16}", version):
            raise ValueError("Invalid release identity")
        folder = release_root() / version
        body = (folder / "report.json").read_bytes()
        if hashlib.sha256(body).hexdigest() != pointer["reportSha256"]:
            raise ValueError("Research manifest hash mismatch")
        return folder, json.loads(body)
    except FileNotFoundError:
        return None, {"available": False, "reason": "Published historical results have not been built.", "downloads": []}
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503, "The published research manifest failed integrity validation") from None


def safe_url(value):
    try:
        p = urlparse(str(value))
        return str(value) if p.scheme in ("http", "https") and p.hostname and not p.username and not p.password else None
    except ValueError:
        return None


def optional(loader, fallback):
    try:
        return loader()
    except cache.CacheNotReadyError:
        return fallback


def is_stale(value, now, hours):
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return moment.tzinfo is None or moment > now or (now-moment).total_seconds() > hours*3600
    except (ValueError, TypeError):
        return True


def pilot_counts():
    from src.portwatch_os.intelligence.public_collection import get_service
    store, now = get_service(), wall_now()  # wall-clock: actual public collection availability.
    result = []
    for port in ("INPRT", "INMAA"):
        w = store.workspace(port, now)
        c = store.collection_status(port, now)
        result.append({"portCode": port, "frozen": w["counts"]["frozen"],
            "matchedArrivals": w["counts"]["matched"], "complete": w["counts"]["waitingOutcomes"],
            "ambiguous": w["counts"]["ambiguous"], "pending": w["counts"]["pending"],
            "lastSuccessfulCollectionAt": c["lastSuccessfulCollectionAt"],
            "collectionFailed": bool((c["lastRun"] or {}).get("errors"))})
    return result


@router.get("/explore")
def explore():
    now = wall_now()  # wall-clock: public cached feed freshness, no visitor replay state.
    live = get_clock().state.mode == LIVE
    provenance = optional(cache.get_provenance, {}).get("sources", {})
    news_source = provenance.get("Maritime events (GDELT + GDACS)", {})
    port_source = provenance.get("Port activity (IMF PortWatch)", {})
    real_news = news_source.get("isReal") is True
    real_ports = port_source.get("isReal") is True
    bundle = optional(cache.get_news_bundle, {}) if live and real_news else {}
    events, _ = from_news_bundle(bundle)
    states = optional(cache.get_port_state, {}) if live and real_ports else {}
    forecasts = optional(cache.get_forecast_by_port, {}) if live and real_ports else {}
    ports = []
    for p in port_registry.all_ports():
        s = states.get(p.locode, {})
        rows = []
        for f in forecasts.get(p.locode, []):
            origin = f.get("originDate")
            stale = is_stale(origin, now, 48)
            rows.append({k: f.get(k) for k in ("day", "targetDate", "originDate", "q10", "q50", "q90", "delayHoursP50", "source")} | {"status": "STALE" if stale else "CACHED"})
        ports.append({"code": p.locode, "name": p.name,
            "observedAt": s.get("observedAt"), "congestionIndex": s.get("congestionIndex"),
            "forecasts": rows, "forecastTarget": "congestion-index proxy, 0–100",
            "delayMeaning": "Modelled delay proxy; not confirmed anchorage waiting or all-fast."})
    public_events = []
    for e in events[:60]:
        raw = e.to_dict()
        impact = build_impact(e).to_dict()  # No private fleet voyages are supplied.
        sources = [{"url": safe_url(s.get("url")), "outlet": s.get("outlet"),
                    "publishedAt": s.get("publishedAt")} for s in raw["sources"]]
        public_events.append({k: raw.get(k) for k in ("eventId", "title", "categoryLabel", "region", "firstSeen", "lastSeen", "severity", "confidence")} | {
            "sources": sources,
            "lanes": [{k: l.get(k) for k in ("laneCode", "laneName", "detourNm", "alternative", "indiaPorts")} for l in impact["lanes"]],
            "ports": [{k: p.get(k) for k in ("portCode", "portName", "exposure")} for p in impact["ports"]],
            "confidenceMeaning": "Reporting corroboration heuristic; not a calibrated disruption probability.",
            "status": "STALE" if is_stale(e.last_seen, now, 72) else "CACHED"})
    return {"asOf": now.isoformat(), "readOnly": True, "events": public_events, "ports": ports,
        "eventStatus": "CACHED" if public_events else "UNAVAILABLE",
        "eventReason": "Live evidence is withheld while the backend is in replay." if not live else ("Real-source provenance is unavailable; simulated events are withheld." if not real_news else None),
        "simulation": {"meaning": "Route catalogue scenario: extra nautical miles / assumed speed. Cost uses visitor-entered USD/day. No observed savings or event-caused port delay is inferred.",
            "defaultSpeedKn": 16, "defaultDailyCostUsd": 30000, "speedRangeKn": [10, 22]},
        "sources": [{"name": name, "url": url, "status": source.get("status", "UNAVAILABLE"),
            "collectedAt": source.get("fetched_at"), "observedAt": source.get("observed_at")}
            for name, url, source in (("IMF PortWatch", "https://portwatch.imf.org/", port_source),
                ("Maritime reports (GDELT / GDACS)", "https://www.gdeltproject.org/", news_source),
                ("Open-Meteo", "https://open-meteo.com/", provenance.get("Marine weather (Open-Meteo)", {})))],
        "limits": "Event exposure, port forecasts and route scenarios are separate evidence. Forecasts do not attribute a causal delay to a selected event."}


@router.get("/research")
def research():
    from src.portwatch_os.learning.weather_feedback import WeatherFeedback, MODEL_VERSION
    from src.portwatch_os.ledger.store import get_ledger, LedgerError, SqliteLedgerStore
    _, report = release()
    now = wall_now()  # wall-clock: public paired scores use actual observation availability.
    try:
        feedback_path = os.getenv("PORTWATCH_WEATHER_FEEDBACK_DB")
        if feedback_path:
            if not Path(feedback_path).is_file():
                raise OSError("Public forecast archive is unavailable")
            public_ledger = SqliteLedgerStore(feedback_path)
            try:
                weather = WeatherFeedback(public_ledger).report(limit=0, now=now, public_only=True)
            finally:
                public_ledger.close()
        else:
            weather = WeatherFeedback(get_ledger()).report(limit=0, now=now, public_only=True)
        weather_view = {"available": True, "version": MODEL_VERSION, "total": weather["total"],
        "resolved": weather["resolved"], "pending": weather["pending"], "scores": weather["scores"],
        "method": "Independent chronological fitting, validation and calibration with availability purging; immutable forecast originals.",
        "note": weather["note"] + " Public scores include only Open-Meteo forecasts paired with public ERA5 outcomes. Station/operator outcomes stay private; pending means no publishable observation."}
    except (LedgerError, sqlite3.DatabaseError, OSError):
        weather_view = {"available": False, "version": MODEL_VERSION, "total": None, "resolved": None,
            "pending": None, "scores": [], "method": "Public weather feedback unavailable.",
            "note": "The feedback store is unavailable. Published historical results remain independently available."}
    operational = {"meaning": "Prospective public-report collection. Reported berth is not confirmed all-fast. Counts do not establish operational accuracy or savings."}
    try:
        operational.update(available=True, ports=pilot_counts())
    except (sqlite3.DatabaseError, OSError):
        operational.update(available=False, ports=[], reason="Collection status is unavailable; no zero counts are inferred.")
    return {**report, "weather": weather_view, "operational": operational,
        "simulationMeaning": "Visitor route/cost scenarios use explicit assumptions and are not measured operational results."}


@router.get("/research/download/{artifact}")
def download(artifact: str, releaseId: str | None = None):
    folder, report = release()
    if releaseId and releaseId != report.get("releaseId"):
        raise HTTPException(409, "The research release changed. Reload the research page before downloading.")
    item = next((d for d in report["downloads"] if d["name"] == artifact), None)
    if not folder or not item or not re.fullmatch(r"[a-z_]+\.(csv|json|zip|txt)", artifact):
        raise HTTPException(404, "Published result not found")
    path = folder / artifact
    if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
        raise HTTPException(503, "Published result failed integrity verification")
    return FileResponse(path, filename=artifact, headers={"Cache-Control": "no-store"})
