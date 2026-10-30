"""Independent six-hour collector; public source records in the existing ledger.

No visitor worlds are enumerated. Quotes are observations. Only an explicitly
frozen future persistence claim is scored when the matching release arrives.
"""
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
from src.portwatch_os.learning import economic_feedback as economic

DB = Path(os.getenv('PORTWATCH_PUBLIC_FEEDBACK_DB') or DEFAULT_LEDGER_PATH)
STOP = threading.Event()
LOCK = threading.Lock()
THREAD = None
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def open_public():
    # Explicit path bypasses visitor resource lookup without changing its scope.
    return SqliteLedgerStore(DB)


def retain_response(store, raw, source, received, root=ROOT, *, product=None, request_metadata=None):
    digest = feedback.hashlib.sha256(raw).hexdigest()
    archive = Path(root)/"shared_feedback"
    archive.mkdir(parents=True, exist_ok=True)
    path = archive/(digest + ".response")
    if path.exists() and feedback.hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("Source archive hash mismatch")
    if not path.exists():
        path.write_bytes(raw)
    previous = [row for row in store.feedback("receipt") if row.get("responseSha256") == digest and row.get("source") == source]
    if not previous:
        store.append_feedback("receipt", {"id": feedback.identifier(["public-source-receipt-v2", source, digest, product]),
            "responseSha256": digest, "source": source, "receivedAt": received, "firstAvailableAt": received,
            "providerPublishedAt": None, "productId": product, "requestMetadata": request_metadata,
            "archivePath": str(path.resolve()), "originalBytesRetained": True})
    check = {"source": source, "productId": product, "responseSha256": digest, "checkedAt": received,
             "status": "HASH_VERIFIED", "requestMetadata": request_metadata}
    store.append_feedback("receipt-check", {**check, "id": feedback.identifier(check)})
    return digest


def collect_fx(store, raw, received, root=ROOT, *, request_metadata=None):
    digest = retain_response(store, raw, URL, received, root, product=economic.PRODUCT,
        request_metadata={"url": URL, "series": "DEXINUS", "format": "CSV", "derivationVersion": "fred-dexinus-date-only-v2",
                          "requestParameters": None, "requestScopeMeaning": "Caller supplied response; exact network parameters unavailable",
                          **(request_metadata or {})})
    try:
        rows = economic.parse_fx_csv(raw)
    except ValueError:
        record_fx_check(store, received, "MALFORMED_RESPONSE", digest=digest,
                        reason="Retained response failed the reviewed DEXINUS CSV schema/date/value checks")
        raise
    observations = []
    for day, value in sorted(rows.items()):
        if economic._date(day) > feedback.instant(received).date():
            continue
        if value is None:
            store.append_feedback("missing-date", {"id": "DEXINUS:" + day, "date": day,
                "source": URL, "responseSha256": digest, "firstAvailableAt": received}) if not store.feedback("missing-date", "DEXINUS:" + day) else None
            missing = {"date": day, "series": "DEXINUS", "source": URL, "responseSha256": digest,
                       "firstAvailableAt": received, "reason": "Publisher supplies no observation; holiday cause is not inferred"}
            missing_id = feedback.identifier(["DEXINUS-missing-v2", day, digest])
            if not store.feedback("economic-missing-observation", missing_id):
                store.append_feedback("economic-missing-observation", {**missing, "id": missing_id})
            continue
        # The first receipt of this date/value retains its original vintage.
        vintages = [e for e in store.feedback("evidence") if e["eventKey"] == "DEXINUS:" + day
                    and e["recordKind"] == "ECONOMIC_OBSERVATION"
                    and e["source"] == "Federal Reserve H.10 via FRED DEXINUS"
                    and e["unit"] == feedback.FX_UNIT and e["aggregation"] == feedback.FX_AGGREGATION]
        latest = max(vintages, key=lambda e: (feedback.instant(e["firstAvailableAt"]), e["id"])) if vintages else None
        if latest and latest["value"] == value:
            observations.append(latest); continue
        outcome = feedback.evidence(store, {"eventKey": "DEXINUS:" + day,
            "target": {"kind": "ECONOMIC_OBSERVATION", "series": "DEXINUS", "date": day,
                       "timePrecision": "DATE_ONLY"},
            "entity": "USD/INR", "geography": "India / New York reference rate", "source": "Federal Reserve H.10 via FRED DEXINUS",
            "sourceVersion": digest, "independenceKey": "Federal Reserve H.10", "firstAvailableAt": received,
            "observedAt": None, "observationDate": day, "measurementTimePrecision": "DATE_ONLY",
            "productId": economic.PRODUCT, "baseCurrency": "USD", "quoteCurrency": "INR", "statistic": feedback.FX_AGGREGATION,
            "providerPublishedAt": None, "availabilityBasis": "First PortWatch receipt; historical publication vintage unavailable",
            "unit": feedback.FX_UNIT, "aggregation": feedback.FX_AGGREGATION, "value": value,
            "recordKind": "ECONOMIC_OBSERVATION", "responseSha256": digest,
            "revises": [e["id"] for e in vintages]})
        observations.append(outcome)
    if observations:
        quote = max(observations, key=lambda e: (e["target"]["date"], e["firstAvailableAt"]))
        if (feedback.instant(received).date()-economic._date(economic.observation_date(quote))).days <= 14:
            feedback.freeze_fx(store, quote, received)
    record_fx_check(store, received, "CURRENT", digest=digest, observations=len(observations),
                    latest_observation=max((economic.observation_date(row) for row in observations), default=None))
    return observations


def record_fx_check(store, checked_at, status, *, digest=None, reason=None, observations=None, latest_observation=None):
    """Append public source-check diagnostics to the existing ledger."""
    body = {"source": "DEXINUS", "productId": economic.PRODUCT, "checkedAt": checked_at, "status": status,
            "responseSha256": digest, "reason": reason, "observationsInResponse": observations,
            "latestObservationDate": latest_observation, "providerPublishedAt": None,
            "meaning": "Fetch/check time is distinct from original first receipt, observation date and actual provider publication"}
    return store.append_feedback("economic-source-check", {**body, "id": feedback.identifier(body)})


def collect_notice(store, notice):
    # wall-clock: extraction assessments become available when this collector interprets retained source bytes.
    assessed_at = wall_now().isoformat()
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
                feedback.verify_news(store, item, assessed_at)
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
            feedback.verify_news(store, item, assessed_at); made.append(item)
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
    """Retain source state; only reviewed intervals create precise claim targets.

    Each provider notice/asset has its own lineage. Disappearance is not a
    cancellation, and an authority revision is not independent confirmation.
    """
    if not notice.get('revisionId') or not notice.get('responseSha256'):
        return []
    from src.portwatch_os.intelligence import navigation_restrictions
    uid=str(notice.get('providerNoticeId') or str(notice.get('noticeId') or notice.get('noticeRef','')).split(':')[-1].replace('USCG MSI #',''))
    if not uid:
        raise ValueError('Stable provider notice identity required')
    path=navigation_restrictions.ROOT/'operational_notices'/(notice['responseSha256']+'.response')
    if not path.is_file() or feedback.hashlib.sha256(path.read_bytes()).hexdigest()!=notice['responseSha256']:
        raise ValueError('NAVCEN original unavailable or corrupt')
    received=notice.get('checkedAt') or notice['availableAt']
    state={'providerNoticeId':uid,'noticeId':'NAVCEN_MSI:'+uid,'areaId':notice.get('areaId'),
        'revisionId':notice['revisionId'],'sourcePreviousRevisionId':notice.get('previousRevisionId'),
        'sourceStatus':notice.get('sourceStatus'),'status':notice.get('status'),
        'extractionStatus':notice.get('extractionStatus'),'calculationSupported':notice.get('calculationSupported'),
        'firstAvailableAt':notice['availableAt'],'checkedAt':received,'responseSha256':notice['responseSha256'],
        'source':notice['source'],'meaning':'Source/extraction state only; neither event occurrence nor shipping impact evidence'}
    store.append_feedback('navigation-source-version',{**state,'id':feedback.identifier(state)})
    if notice.get('sourceStatus') in ('MISSING','UNAVAILABLE','STALE'):
        return []
    prior=[c for c in store.feedback('claim') if c.get('providerNoticeId')==uid
        or (uid=='53842' and c.get('reviewedSourceFamily')=='NAVCEN_MSI_53842')]
    if notice.get('status')=='CANCELLED':
        for item in prior:
            if feedback.instant(item['firstAvailableAt'])>feedback.instant(notice['availableAt']):
                continue
            feedback.evidence(store, {'eventKey':item['eventKey'],'eventReference':item.get('eventReference') or 'NAVCEN_MSI:'+uid+':'+item['entity'],
                'entity':item['entity'],'geography':item['geography'],'target':item['target'],
                'source':notice['source'],'sourceVersion':notice['revisionId'], 'sourceLineageId':'USCG NAVCEN',
                'sourceReportId':'NAVCEN_MSI:'+uid,'sourceRevisionId':notice['revisionId'],
                'independenceKey':'USCG NAVCEN','firstAvailableAt':notice['availableAt'],'observedAt':notice['availableAt'],
                'unit':'boolean','aggregation':'EXPLICIT_NOTICE_WINDOW','value':None,'recordKind':'CANCELLATION',
                'cancellationTarget':{'kind':'CANCELLATION','noticeId':'NAVCEN_MSI:'+uid,'effectiveAt':None,
                    'meaning':'Explicit cancellation received; effective instant is not inferred from receipt'},
                'responseSha256':notice['responseSha256'],'cancelsSourceVersion':item['sourceVersion']})
            feedback.verify_news(store,item,notice['availableAt'])
        return []
    if notice.get('extractionStatus','SUPPORTED')!='SUPPORTED' or not notice.get('areaId'):
        return []
    def same_period(item,window):
        try:
            target=item['target']
            return feedback.instant(target['from'])==feedback.instant(window['start']) and feedback.instant(target['through'])==feedback.instant(window['end'])
        except (ValueError,KeyError,TypeError):
            return False
    made=[]
    for window in notice.get('windows',[]):
        event_key='NAVCEN_MSI:'+uid+':'+notice['areaId']
        for kind in ('ANNOUNCEMENT','ACTUAL_EVENT'):
            existing=[c for c in prior if c['sourceVersion']==notice['revisionId'] and c['target']['kind']==kind and same_period(c,window)]
            if existing:
                for item in sorted(existing,key=lambda c:c['id']):
                    feedback.verify_news(store,item,notice['availableAt']);made.append(item)
                continue
            predecessors=[c for c in prior if c['sourceVersion']==notice.get('previousRevisionId') and c['target']['kind']==kind and same_period(c,window)]
            body={'kind':'REPORTED_FACT' if kind=='ANNOUNCEMENT' else 'INFERRED_EXPOSURE',
                'wording':notice['originalWording'] if kind=='ANNOUNCEMENT' else 'Scheduled bridge opening restriction may occur; actual operation requires independent records',
                'value':True,'entity':notice['areaId'],'geography':notice['area'],
                'originAt':notice['availableAt'],'firstAvailableAt':notice['availableAt'],
                'target':{'kind':kind,'from':window['start'],'through':window['end'],'precision':'MINUTE',
                    'timeZoneBasis':window['timeZoneBasis']},
                'source':notice['source'],'sourceVersion':notice['revisionId'],'responseSha256':notice['responseSha256'],
                'eventKey':event_key,'eventReference':event_key,'independenceKey':'USCG NAVCEN','sourceLineageId':'USCG NAVCEN',
                'sourceReportId':'NAVCEN_MSI:'+uid,'sourceRevisionId':notice['revisionId'],
                'sourcePreviousRevisionId':notice.get('previousRevisionId'),'providerNoticeId':uid,'inputs':[],
                'unit':'boolean','aggregation':'EXPLICIT_NOTICE_WINDOW','reviewedSourceFamily':'NAVCEN_MSI_REVIEWED_BRIDGE_INTERVALS',
                'providerCreatedAt':notice.get('providerCreatedAt'),'providerModifiedAt':notice.get('providerModifiedAt'),
                'publicationPrecision':notice.get('publicationPrecision'),'coordinates':notice.get('coordinates'),
                'extractionVersion':notice.get('extractionVersion'),
                'recordTiming':('PROSPECTIVE_SOURCE_RECEIPT' if feedback.instant(notice['availableAt'])<feedback.instant(window['start']) else
                    'HISTORICAL_AUTHORITY_REPORT_REPLAY' if feedback.instant(notice['availableAt'])>=feedback.instant(window['end']) else 'RECEIVED_DURING_TARGET_INTERVAL'),
                'extractionState':'REVIEWED_ADAPTER; parser tests are not independent accuracy evidence'}
            if len(predecessors)==1: body['supersedesClaimId']=predecessors[0]['id']
            elif predecessors: body['supersedesClaimIds']=sorted(c['id'] for c in predecessors)
            item=feedback.claim(store,body)
            feedback.verify_news(store,item,notice['availableAt']);made.append(item)
    return made


def run_once():
    if not LOCK.acquire(blocking=False):
        return {"status": "RUNNING"}
    store = open_public()
    # wall-clock: run audit and bounded provider query dates describe an actual collection attempt.
    started_at = wall_now()
    status = {"status": "COLLECTING", "ranAt": started_at.isoformat(), "failures": []}
    try:
        try:
            request_params = {"id": "DEXINUS", "cosd": (started_at-feedback.timedelta(days=45)).date().isoformat(),
                              "coed": started_at.date().isoformat()}
            response = requests.get(URL, params=request_params, timeout=(4, 20))
            response.raise_for_status()
            # wall-clock: observation availability starts after the actual provider response returns.
            status["observations"] = len(collect_fx(store, response.content, wall_now().isoformat(),
                request_metadata={"requestParameters": request_params, "requestScopeMeaning": "Exact parameters sent by the existing six-hour worker"}))
        except requests.RequestException:
            reason = "DEXINUS provider request failed; the last retained observation is not reused as a new outcome"
            # wall-clock: persist this failed attempt's receipt; no new observation is created.
            record_fx_check(store, wall_now().isoformat(), "PROVIDER_UNAVAILABLE", reason=reason)
            status["failures"].append({"source": "DEXINUS", "reason": reason})
        except (ValueError, OSError):
            reason = "DEXINUS source response or original-evidence validation failed; retained records remain inspectable"
            latest = sorted(store.feedback("economic-source-check"), key=lambda row: (row["checkedAt"], row["id"]))
            if not latest or latest[-1]["status"] != "MALFORMED_RESPONSE":
                # wall-clock: validation failure is an actual audit check, not an observation date.
                record_fx_check(store, wall_now().isoformat(), "ORIGINAL_VALIDATION_FAILED", reason=reason)
            status["failures"].append({"source": "DEXINUS", "reason": reason})
        notice = {}
        try:
            from src.portwatch_os.intelligence.operational_notices import refresh
            notice = refresh()
            collect_notice(store, notice)
        except (ValueError, KeyError, OSError) as exc:
            status["failures"].append({"source": "Peel Ports", "reason": str(exc)[:180]})
        # A primary-notice fetch/parser failure must not suppress this separate
        # report's check or original retention on the existing worker.
        try:
            from src.portwatch_os.learning.reviewed_news import refresh_gac_eastham
            status["reviewedNews"] = refresh_gac_eastham(store, notice)
            if status['reviewedNews'].get('status') != 'RETAINED':
                status['failures'].append({'source':'GAC Eastham announcement',
                    'reason':status['reviewedNews'].get('reason') or 'Reviewed source evidence is not currently qualified'})
        except (requests.RequestException, ValueError, OSError):
            status["reviewedNews"] = {"status": "UNAVAILABLE", "reason": "Reviewed GAC announcement evidence unavailable or unsupported; no resolution inferred"}
            status["failures"].append({"source": "GAC Eastham announcement", "reason": status["reviewedNews"]["reason"]})
        try:
            from src.portwatch_os.intelligence.navigation_restrictions import refresh_all
            catalogue=refresh_all()
            status['navigation']={'sourceStatus':catalogue.get('sourceStatus','UNKNOWN'),
                'checkedAt':catalogue.get('checkedAt'),'discovered':len(catalogue.get('notices',[])),
                'claimsCollected':0,'missing':0,'unavailable':0,'unsupported':0}
            if catalogue.get('sourceStatus')!='CURRENT':
                status['failures'].append({'source':'USCG NAVCEN','reason':catalogue.get('reason') or 'Source product unavailable'})
            for notice in catalogue.get('notices',[]):
                for label,condition in (('missing',notice.get('sourceStatus')=='MISSING'),
                    ('unavailable',notice.get('sourceStatus')=='UNAVAILABLE'),('unsupported',notice.get('extractionStatus')!='SUPPORTED')):
                    status['navigation'][label]+=int(condition)
                try:
                    status['navigation']['claimsCollected']+=len(collect_navigation(store,notice))
                except (ValueError,KeyError,OSError) as exc:
                    status['failures'].append({'source':'USCG NAVCEN','noticeId':notice.get('noticeId'),'reason':str(exc)[:180]})
        except (ValueError,KeyError,OSError) as exc:
            status['navigation']={'sourceStatus':'UNAVAILABLE','reason':str(exc)[:180]}
            status['failures'].append({'source':'USCG NAVCEN','reason':str(exc)[:180]})
        try:
            from backend.app.services.cache_service import get_news_bundle
            # wall-clock: public news cache becomes available to this collector at actual ingest.
            collect_news_product(store, get_news_bundle(), wall_now().isoformat())
        except (ValueError, OSError, RuntimeError) as exc:
            status["failures"].append({"source": "News source product", "reason": str(exc)[:180]})
        # Optional bounded family on the existing worker; no extra scheduler.
        # Context metadata is never collected as an actual closure/outcome claim.
        if os.getenv("PORTWATCH_NHO_ENABLED", "0") == "1":
            from src.portwatch_os.intelligence import indian_notices
            indian = indian_notices.refresh()
            status["indianNavigation"] = {key: indian.get(key) for key in ("sourceStatus", "checkedAt", "lastSuccessfulReceiptAt", "productAsOfDate", "reason")}
        # wall-clock: evaluate a live collection cohort at one post-ingest instant, not a visitor's replay.
        evaluation_at = wall_now().isoformat()
        status["resolved"], status["pending"] = feedback.reconcile(store, evaluation_at)
        status["reliabilityVersion"] = feedback.reliability_version(store, evaluation_at)["id"]
        # wall-clock: completed result availability follows calculation completion, not run start.
        status['completedAt']=wall_now().isoformat()
        status['firstAvailableAt']=status['completedAt']
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
