"""Independent six-hour collector; public source records in the existing ledger.

No visitor worlds are enumerated. Quotes are observations. Only an explicitly
frozen future persistence claim is scored when the matching release arrives.
"""
import csv
import io
import json
import logging
import os
from pathlib import Path
import threading

import requests

from src.portwatch_os.clock import wall_now
from src.portwatch_os.ledger.store import SqliteLedgerStore, DEFAULT_LEDGER_PATH
from src.portwatch_os.intelligence.current_environment import ROOT
from src.portwatch_os.learning import shared_feedback as feedback

DB = DEFAULT_LEDGER_PATH
STOP = threading.Event()
LOCK = threading.Lock()
THREAD = None
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def open_public():
    # Explicit path bypasses visitor resource lookup without changing its scope.
    return SqliteLedgerStore(DB)


def retain_response(store, raw, source, received, root=ROOT):
    digest = feedback.hashlib.sha256(raw).hexdigest()
    archive = Path(root)/"shared_feedback"
    archive.mkdir(parents=True, exist_ok=True)
    path = archive/(digest + ".response")
    if path.exists() and feedback.hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("Source archive hash mismatch")
    if not path.exists():
        path.write_bytes(raw)
    store.append_feedback("receipt", {"id": feedback.identifier([digest, received]), "responseSha256": digest,
        "source": source, "receivedAt": received, "providerPublishedAt": None})
    return digest


def collect_fx(store, raw, received, root=ROOT):
    digest = retain_response(store, raw, URL, received, root)
    rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if rows.fieldnames not in (["observation_date", "DEXINUS"], ["DATE", "DEXINUS"]):
        raise ValueError("Unexpected DEXINUS CSV schema")
    date_key = rows.fieldnames[0]
    observations = []
    for row in rows:
        day = row[date_key]
        measured = day + "T00:00:00+00:00"
        if feedback.instant(measured).date() > feedback.instant(received).date():
            continue
        if row["DEXINUS"] in (".", "", "NA"):
            store.append_feedback("missing-date", {"id": "DEXINUS:" + day, "date": day,
                "source": URL, "responseSha256": digest, "firstAvailableAt": received}) if not store.feedback("missing-date", "DEXINUS:" + day) else None
            continue
        value = float(row["DEXINUS"])
        if not feedback.finite(value) or value <= 0:
            raise ValueError("Invalid DEXINUS observation")
        # The first receipt of this date/value retains its original vintage.
        vintages = [e for e in store.feedback("evidence") if e["eventKey"] == "DEXINUS:" + day
                    and e["recordKind"] == "ECONOMIC_OBSERVATION"
                    and e["source"] == "Federal Reserve H.10 via FRED DEXINUS"
                    and e["unit"] == feedback.FX_UNIT and e["aggregation"] == feedback.FX_AGGREGATION]
        latest = max(vintages, key=lambda e: e["firstAvailableAt"]) if vintages else None
        if latest and latest["value"] == value:
            observations.append(latest); continue
        outcome = feedback.evidence(store, {"eventKey": "DEXINUS:" + day,
            "target": {"kind": "ECONOMIC_OBSERVATION", "series": "DEXINUS", "date": day,
                       "at": day+"T16:00:00+00:00", "timePrecision": "OBSERVATION_DATE_ONLY; UTC timestamp is an eligibility label"},
            "entity": "USD/INR", "geography": "India / New York reference rate", "source": "Federal Reserve H.10 via FRED DEXINUS",
            "sourceVersion": digest, "independenceKey": "Federal Reserve H.10", "firstAvailableAt": received,
            "observedAt": measured, "measurementTimePrecision": "DATE_ONLY; New York noon buying rate, not closing price",
            "providerPublishedAt": None, "availabilityBasis": "First PortWatch receipt; historical publication vintage unavailable",
            "unit": feedback.FX_UNIT, "aggregation": feedback.FX_AGGREGATION, "value": value,
            "recordKind": "ECONOMIC_OBSERVATION", "responseSha256": digest,
            "revises": [e["id"] for e in vintages]})
        observations.append(outcome)
    if observations:
        quote = max(observations, key=lambda e: (e["target"]["date"], e["firstAvailableAt"]))
        if (feedback.instant(received)-feedback.instant(quote["observedAt"])).days <= 14:
            feedback.freeze_fx(store, quote, received)
    return observations


def collect_notice(store, notice):
    if not notice.get("revisionId") or not notice.get("pdfSha256"):
        return []
    from src.portwatch_os.intelligence import operational_notices
    from pypdf import PdfReader
    path = operational_notices.ROOT/"operational_notices"/(notice["pdfSha256"]+".response")
    raw = path.read_bytes()
    if feedback.hashlib.sha256(raw).hexdigest() != notice["pdfSha256"]:
        raise ValueError("Authority original hash mismatch")
    text = " ".join(" ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(raw)).pages).split())
    # Keep literal extracted wording, separately from the reviewed interpretation.
    import re
    excerpt = re.search(r"[^.]{0,160}closed to vessel movements[^.]{0,160}\.", text, re.I)
    if not excerpt and notice.get("status") != "CANCELLED":
        raise ValueError("Exact closure wording unavailable")
    if notice.get("status") == "CANCELLED":
        for item in store.feedback("claim"):
            if item["eventKey"].startswith(notice["noticeRef"] + ":"):
                feedback.evidence(store, {"eventKey": item["eventKey"], "entity": item["entity"], "geography": item["geography"],
                    "target": item["target"], "source": notice["source"], "sourceVersion": notice["revisionId"],
                    "independenceKey": "Peel Ports", "firstAvailableAt": notice["availableAt"], "observedAt": notice["availableAt"],
                    "unit": "boolean", "aggregation": "EXPLICIT_NOTICE_WINDOW", "value": None,
                    "recordKind": "CANCELLATION", "responseSha256": notice["pdfSha256"], "cancelsSourceVersion": item["sourceVersion"]})
                feedback.verify_news(store, item, wall_now().isoformat())
        return []
    # This source's own notice is not an independent confirmation of itself.
    made = []
    for window in notice.get("windows", []):
        event_key = notice["noticeRef"] + ":" + window["closureStartDate"]
        for target_kind in ("ANNOUNCEMENT", "ACTUAL_EVENT"):
            body = {"kind": "REPORTED_FACT" if target_kind == "ANNOUNCEMENT" else "INFERRED_EXPOSURE",
                "wording": excerpt[0] if target_kind == "ANNOUNCEMENT" else "Scheduled closure may affect actual access; occurrence requires independent operational records",
                "wordingBasis": "Exact PDF excerpt" if target_kind == "ANNOUNCEMENT" else "Contingent inference from the scheduled notice, not an actual closure report",
                "value": True, "entity": notice["areaId"], "geography": notice["area"],
                "originAt": notice["availableAt"], "firstAvailableAt": notice["availableAt"],
                "target": {"kind": target_kind, "from": window["start"], "through": window["end"]},
                "publishedDate": notice["publishedDate"], "publicationPrecision": "DATE_ONLY",
                "source": notice["source"], "sourceVersion": notice["revisionId"], "responseSha256": notice["pdfSha256"],
                "eventKey": event_key, "independenceKey": "Peel Ports", "inputs": [],
                "unit": "boolean", "aggregation": "EXPLICIT_NOTICE_WINDOW"}
            item = feedback.claim(store, body)
            feedback.verify_news(store, item, wall_now().isoformat()); made.append(item)
    return made


def collect_news_product(store, bundle, received, root=ROOT):
    """Bounded reviewed headline family; broad tags do not become closures.

    Original GDELT-derived source product is retained. Publisher article bodies,
    publication vintage and exact reporting period are not inferred from it.
    """
    import re
    from urllib.parse import urlparse
    raw = json.dumps(bundle, sort_keys=True).encode()
    digest = retain_response(store, raw, "PortWatch GDELT-derived news source product", received, root)
    for event in bundle.get("events", []):
        headline = event.get("title", "")
        matched = re.fullmatch(r"Centcom says (\d+) vessels redirected in Hormuz as it enforces Iran blockade", headline, re.I)
        if not matched or not event.get("url"):
            continue
        value = int(matched[1]); source = event["url"]
        target = {"kind": "ANNOUNCEMENT", "predicate": "CENTCOM_REPORTED_CUMULATIVE_REDIRECTIONS",
                  "reportedPeriod": "UNKNOWN; independent evidence must establish the same announcement and period"}
        prior = [c for c in store.feedback("claim") if c["source"] == source and c["wording"] == headline and c["target"] == target]
        if prior:
            item = prior[0]
        else:
            item = feedback.news_report(store, wording=headline, source=source, source_version=digest,
                independence_key=event.get("syndicationOrigin") or urlparse(source).hostname,
                event_key="CENTCOM:HORMUZ:reported-redirections:" + str(value), entity="Strait of Hormuz",
                geography="Hormuz / Iranian-port blockade; not a blanket strait closure", target=target,
                first_available_at=received, published_at=None, response_sha256=digest, value=value, unit="vessels")
            store.append_feedback("news-source-quality", {"id": item["id"], "sourceProductTimestamp": event.get("timestamp"),
                "timestampMeaning": "Source-product timestamp; publisher publication time unverified",
                "articleBodyRetained": False, "sourceProductRetained": True,
                "inferredPortCodes": event.get("affectedPorts", []),
                "closureInference": "Legacy CHOKEPOINT_CLOSURE tag is not consumed as evidence of a closure",
                "deduplication": "Reviewed issuer/predicate/cumulative-count identity; source lineage retained, independence unverified"})
        feedback.verify_news(store, item, received)


def collect_navigation(store, notice):
    """Reviewed authority announcement and contingent occurrence stay separate."""
    if not notice.get('revisionId') or not notice.get('responseSha256'):
        return []
    from src.portwatch_os.intelligence import navigation_restrictions
    path=navigation_restrictions.ROOT/'operational_notices'/(notice['responseSha256']+'.response')
    if not path.is_file() or feedback.hashlib.sha256(path.read_bytes()).hexdigest()!=notice['responseSha256']:
        raise ValueError('NAVCEN original unavailable or corrupt')
    prior=[c for c in store.feedback('claim') if c.get('reviewedSourceFamily')=='NAVCEN_MSI_53842']
    if notice.get('status')=='CANCELLED':
        for item in prior:
            feedback.evidence(store, {'eventKey':item['eventKey'],'entity':item['entity'],'geography':item['geography'],
                'target':item['target'],'source':notice['source'],'sourceVersion':notice['revisionId'],
                'independenceKey':'USCG NAVCEN','firstAvailableAt':notice['availableAt'],'observedAt':notice['availableAt'],
                'unit':'boolean','aggregation':'EXPLICIT_NOTICE_WINDOW','value':None,'recordKind':'CANCELLATION',
                'responseSha256':notice['responseSha256'],'cancelsSourceVersion':item['sourceVersion']})
            feedback.verify_news(store,item,notice['availableAt'])
        return []
    made=[]
    for window in notice.get('windows',[]):
        event_key=notice['noticeRef']+':'+window['localDate']+':'+notice['areaId']
        for kind in ('ANNOUNCEMENT','ACTUAL_EVENT'):
            predecessor=next((c for c in prior if c['sourceVersion']==notice.get('previousRevisionId') and c['target']['kind']==kind),None)
            body={'kind':'REPORTED_FACT' if kind=='ANNOUNCEMENT' else 'INFERRED_EXPOSURE',
                'wording':notice['originalWording'] if kind=='ANNOUNCEMENT' else 'Scheduled bridge opening restriction may occur; actual operation requires independent records',
                'value':True,'entity':notice['areaId'],'geography':notice['area'],
                'originAt':notice['availableAt'],'firstAvailableAt':notice['availableAt'],
                'target':{'kind':kind,'from':window['start'],'through':window['end'],
                    'timeZoneBasis':window['timeZoneBasis']},
                'source':notice['source'],'sourceVersion':notice['revisionId'],'responseSha256':notice['responseSha256'],
                'eventKey':event_key,'independenceKey':'USCG NAVCEN','inputs':[],
                'unit':'boolean','aggregation':'EXPLICIT_NOTICE_WINDOW','reviewedSourceFamily':'NAVCEN_MSI_53842',
                'providerCreatedAt':notice['providerCreatedAt'],'providerModifiedAt':notice['providerModifiedAt'],
                'publicationPrecision':notice['publicationPrecision'],'coordinates':notice['coordinates'],
                'extractionState':'REVIEWED_ADAPTER; parser tests are not independent accuracy evidence',
                **({'supersedesClaimId':predecessor['id']} if predecessor else {})}
            # Repeated receipts of the same revision must retain exactly its
            # original claim, regardless of which newer revisions are present.
            existing=next((c for c in prior if c['sourceVersion']==notice['revisionId'] and c['target']['kind']==kind),None)
            item=existing or feedback.claim(store,body)
            feedback.verify_news(store,item,wall_now().isoformat()); made.append(item)
    return made


def run_once():
    if not LOCK.acquire(blocking=False):
        return {"status": "RUNNING"}
    store = open_public()
    status = {"status": "COLLECTING", "ranAt": wall_now().isoformat(), "failures": []}
    try:
        try:
            response = requests.get(URL, params={"id": "DEXINUS", "cosd": (wall_now()-feedback.timedelta(days=45)).date().isoformat(),
                                                "coed": wall_now().date().isoformat()}, timeout=(4, 20))
            response.raise_for_status()
            status["observations"] = len(collect_fx(store, response.content, wall_now().isoformat()))
        except (requests.RequestException, ValueError) as exc:
            status["failures"].append({"source": "DEXINUS", "reason": str(exc)[:180]})
        try:
            from src.portwatch_os.intelligence.operational_notices import refresh
            notice = refresh()
            collect_notice(store, notice)
        except (ValueError, KeyError, OSError) as exc:
            status["failures"].append({"source": "Peel Ports", "reason": str(exc)[:180]})
        try:
            from src.portwatch_os.intelligence.navigation_restrictions import refresh as navigation_refresh
            collect_navigation(store,navigation_refresh())
        except (ValueError,KeyError,OSError) as exc:
            status['failures'].append({'source':'USCG NAVCEN','reason':str(exc)[:180]})
        try:
            from backend.app.services.cache_service import get_news_bundle
            collect_news_product(store, get_news_bundle(), wall_now().isoformat())
        except (ValueError, OSError, RuntimeError) as exc:
            status["failures"].append({"source": "News source product", "reason": str(exc)[:180]})
        status["resolved"], status["pending"] = feedback.reconcile(store, wall_now().isoformat())
        status["reliabilityVersion"] = feedback.reliability_version(store, wall_now().isoformat())["id"]
        store.append_feedback("run", {**status, "id": feedback.identifier(status)})
        return status
    finally:
        store.close(); LOCK.release()


def start():
    global THREAD
    if os.getenv("PORTWATCH_INTELLIGENCE_RECONCILIATION", "1").lower() in ("0", "false", "off"):
        return
    if THREAD and THREAD.is_alive():
        return
    STOP.clear()
    def work():
        while not STOP.is_set():
            try: run_once()
            except Exception: logging.getLogger(__name__).exception("Intelligence reconciliation failed; originals retained")
            STOP.wait(6*3600)
    THREAD = threading.Thread(target=work, name="intelligence-reconciliation", daemon=True); THREAD.start()


def stop():
    STOP.set()
