"""Read-only operational context from existing public collectors and retained originals.

Public report rows and aggregate daily estimates never become a visitor vessel's
actual movement history. The original public pilot owns PDF collection and ETA
reconciliation; this adapter only projects its bounded, hash-checked evidence.
"""
from __future__ import annotations

import copy
import json
import re
import threading
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from src.portwatch_os.clock import LIVE, get_clock, wall_now
from src.portwatch_os.intelligence.public_collection import get_service
from src.portwatch_os.intelligence.public_ports import IST, PORTS, TIMEZONE_NOTE, digest, parse_pdf, stamp
from src.portwatch_os.learning.weather_feedback import instant

VERSION = "operational-port-context-v1"
IMF_PORTS = {"INNSA": "port776"}
IMF_ENDPOINT = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/Daily_Ports_Data/FeatureServer/0/query"
NAMES = {"INMAA": "Chennai", "INPRT": "Paradip", "INNSA": "Jawaharlal Nehru"}
LOCATIONS = {"INMAA": (13.100, 80.294), "INPRT": (20.280, 86.649), "INNSA": (18.917, 72.940)}
PDF_LIMITATIONS = [
    "Source: Chennai Port Authority or Paradip Port Authority as named by the selected original. Public-report research inspection; no blanket open-content licence or authority endorsement is claimed.",
    "Publisher-reported expected arrival, arrival or position only; event boundaries and all-fast are unconfirmed.",
    "Public names and dimensions do not establish a link to this visitor's demo vessel; explicit context selection is required.",
    TIMEZONE_NOTE,
    "Printed report date is known; precise publication time and vessel identifiers such as IMO/MMSI are unavailable.",
    "No supported voyage delay, cost, fuel, safety benefit or actual execution is calculated from this context.",
]
IMF_LIMITATIONS = [
    "Source: International Monetary Fund, IMF PortWatch. Fields are selected and dates normalized for inspection; no IMF endorsement is implied. Source terms remain applicable.",
    "Aggregate daily AIS-derived port activity estimates; not individual AIS, an official vessel call or all-fast.",
    "A recent receipt does not make a lagging observation current. Publication time is unavailable; revisions remain separate receipts.",
    "Port-call counts have unit calls/day. Raw trade fields are retained without asserting an unverified unit or shipping effect.",
]


def _key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Exact retained evidence identity is required")
    return value


def _date(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value / 1000, timezone.utc).date().isoformat()
    return date.fromisoformat(value).isoformat()


def _fresh(report_date, now):
    age_days = (now.astimezone(IST).date() - date.fromisoformat(report_date)).days
    if age_days < 0:
        return "FUTURE_REPORT", age_days
    return ("CURRENT" if age_days <= 1 else "STALE"), age_days


def _pdf_record(snapshot, row):
    semantic = ("PUBLISHED_EXPECTED_ARRIVAL" if row["kind"] == "expected" else
                "REPORTED_PORT_ARRIVAL" if row.get("arrivalAt") else "REPORTED_PORT_POSITION")
    return {"selector": {"product": "PUBLIC_PORT_PDF", "portCode": snapshot["portCode"],
            "snapshotId": snapshot["snapshotId"], "recordId": row["recordId"]},
        "title": row["vesselName"], "semanticClass": semantic, "record": copy.deepcopy(row)}


def _pdf_product(store, snapshot, now, collection):
    status, age_days = _fresh(snapshot["reportDate"], now) if snapshot["reportDate"] else ("UNAVAILABLE", None)
    verified = False
    try:
        store.evidence(snapshot["portCode"], snapshot["snapshotId"], now)
        verified = True
    except (ValueError, OSError):
        status = "UNAVAILABLE"
    records = [_pdf_record(snapshot, row) for row in snapshot["records"]
               if row["kind"] in ("expected", "reported")]
    if not records:
        status = "UNAVAILABLE"
    return {"id": snapshot["snapshotId"], "product": "PUBLIC_PORT_PDF", "portCode": snapshot["portCode"],
        "name": NAMES[snapshot["portCode"]] + " published " + snapshot["kind"] + " report",
        "status": status, "semanticClass": "PUBLISHED_EXPECTED_ARRIVAL" if snapshot["kind"] == "expected" else "REPORTED_PORT_POSITION",
        "sourceUrl": snapshot["sourceUrl"], "sha256": snapshot["sha256"], "originalHashVerified": verified,
        "clocks": {"reportDate": snapshot["reportDate"], "observedAt": None, "publishedAt": None,
            "firstAvailableAt": snapshot["firstSeenAt"], "parsedAt": snapshot["parsedAt"],
            "checkedAt": collection["lastCheckAt"], "observationAgeHours": None, "reportAgeDays": age_days,
            "ageBasis": "Printed report date in assumed Asia/Kolkata; not an invented publication instant"},
        "parserVersion": snapshot["parserVersion"], "parseHistory": snapshot["parseHistory"],
        "location": {"lat": LOCATIONS[snapshot["portCode"]][0], "lon": LOCATIONS[snapshot["portCode"]][1],
            "basis": "Existing IMF PortWatch physical-port catalogue point; not vessel coordinates"},
        "records": records, "limitations": PDF_LIMITATIONS, "collection": collection,
        "counts": {"records": len(records), "parserIssues": len(snapshot["issues"])}, "issues": snapshot["issues"]}


class AggregateArchive:
    """Immutable ArcGIS receipts beside the existing public pilot's originals."""
    def __init__(self, root):
        self.root = Path(root) / "aggregate_activity"
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "checks").mkdir(exist_ok=True)
        self.lock = threading.RLock()

    def retain(self, payload, *, port, url, received_at, status=200, headers=None, params=None):
        if port not in IMF_PORTS or received_at.tzinfo is None:
            raise ValueError("An approved aggregate port and aware receipt clock are required")
        parsed_url = urlparse(url)
        if parsed_url._replace(query="", fragment="").geturl() != IMF_ENDPOINT or parsed_url.fragment:
            raise ValueError("Aggregate response did not come from the approved exact provider endpoint")
        sha = digest(payload)
        received = stamp(received_at)
        key = digest(json.dumps([sha, received, port, params], sort_keys=True))
        body = {"receiptId": key, "portCode": port, "sourceUrl": url, "receivedAt": received,
            "sha256": sha, "httpStatus": status, "httpDate": (headers or {}).get("Date"),
            "lastModified": (headers or {}).get("Last-Modified"), "query": params or {}, "records": [], "errors": []}
        try:
            if status != 200:
                raise ValueError("Provider HTTP status " + str(status))
            decoded = json.loads(payload)
            if not isinstance(decoded, dict) or decoded.get("error") or not isinstance(decoded.get("features"), list):
                raise ValueError("Provider error or missing features array")
            if decoded.get("exceededTransferLimit"):
                raise ValueError("Truncated aggregate response was retained but is not usable")
            for feature in decoded["features"]:
                if not isinstance(feature, dict):
                    raise ValueError("Aggregate feature must be an object")
                attrs = feature.get("attributes")
                if not isinstance(attrs, dict) or attrs.get("portid") != IMF_PORTS[port]:
                    raise ValueError("Aggregate record has a different or missing physical port")
                day = _date(attrs.get("date"))
                if date.fromisoformat(day) > received_at.date():
                    raise ValueError("Future aggregate observation is not accepted")
                calls = attrs.get("portcalls")
                if isinstance(calls, bool) or not isinstance(calls, (int, float)) or calls < 0 or int(calls) != calls:
                    raise ValueError("Port-call count must be a nonnegative integer")
                body["records"].append({"recordId": digest(json.dumps(attrs, sort_keys=True)), "date": day,
                    "portcalls": calls, "unit": "calls/day", "sourceAttributes": attrs})
            if not body["records"]:
                raise ValueError("No aggregate observations returned")
        except (ValueError, TypeError, OverflowError) as exc:
            body["records"] = []
            body["errors"] = [str(exc)]
        with self.lock:
            previous = self.receipts(received_at, port)
            same_response = [r for r in previous if r["sha256"] == sha]
            body["firstAvailableAt"] = same_response[0].get("firstAvailableAt", same_response[0]["receivedAt"]) if same_response else received
            known = {}
            for prior in previous:
                for row in prior["records"]:
                    known.setdefault(row["recordId"], row.get("firstAvailableAt", prior["receivedAt"]))
            for row in body["records"]:
                row["firstAvailableAt"] = known.get(row["recordId"], received)
            raw_path = self.root / (sha + ".response")
            if raw_path.exists():
                if digest(raw_path.read_bytes()) != sha:
                    raise ValueError("Aggregate original source hash mismatch")
            else:
                with raw_path.open("xb") as stream:
                    stream.write(payload)
            metadata = self.root / (key + ".json")
            if not metadata.exists():
                pending = self.root / (key + ".pending")
                with pending.open("w", encoding="utf-8") as stream:
                    json.dump(body, stream, sort_keys=True)
                pending.replace(metadata)
        return body

    def check(self, port, at, error=None):
        body = {"portCode": port, "checkedAt": stamp(at), "errors": [error] if error else []}
        path = self.root / "checks" / (digest(json.dumps(body, sort_keys=True)) + ".json")
        with self.lock:
            if not path.exists():
                pending = path.with_suffix(".pending")
                with pending.open("w", encoding="utf-8") as stream:
                    json.dump(body, stream)
                pending.replace(path)

    def last_check(self, port, now):
        rows = [json.loads(p.read_text(encoding="utf-8")) for p in (self.root / "checks").glob("*.json")]
        return max((r for r in rows if r["portCode"] == port and instant(r["checkedAt"]) <= now),
            key=lambda r: r["checkedAt"], default=None)

    def receipts(self, now, port=None):
        result = []
        for path in self.root.glob("*.json"):
            body = json.loads(path.read_text(encoding="utf-8"))
            if instant(body["receivedAt"]) <= now and (not port or body["portCode"] == port):
                result.append(body)
        return sorted(result, key=lambda row: (row["receivedAt"], row["receiptId"]))

    def evidence(self, receipt, now):
        if instant(receipt["receivedAt"]) > now:
            raise ValueError("Aggregate receipt was unavailable at this clock")
        path = self.root / (_key(receipt["sha256"]) + ".response")
        if digest(path.read_bytes()) != receipt["sha256"]:
            raise ValueError("Aggregate original source hash mismatch")
        parsed_url = urlparse(receipt["sourceUrl"])
        if parsed_url._replace(query="", fragment="").geturl() != IMF_ENDPOINT or parsed_url.fragment or receipt["portCode"] not in IMF_PORTS:
            raise ValueError("Aggregate source identity is not approved")
        if receipt["records"]:
            original = json.loads(path.read_bytes())
            if (not isinstance(original, dict) or not isinstance(original.get("features"), list)
                    or any(not isinstance(f, dict) for f in original["features"])):
                raise ValueError("Aggregate parsed metadata does not match the original")
            attrs = [f.get("attributes") for f in original["features"]]
            if original.get("error") or original.get("exceededTransferLimit") or len(attrs) != len(receipt["records"]):
                raise ValueError("Aggregate parsed metadata does not match the original")
            for row, raw in zip(receipt["records"], attrs):
                if (not isinstance(raw, dict) or raw.get("portid") != IMF_PORTS[receipt["portCode"]]
                        or row["sourceAttributes"] != raw or row["recordId"] != digest(json.dumps(raw, sort_keys=True))
                        or row["date"] != _date(raw.get("date")) or row["portcalls"] != raw.get("portcalls")
                        or row["unit"] != "calls/day"):
                    raise ValueError("Aggregate parsed row does not match the original response")
        return path


@lru_cache(maxsize=1)
def get_aggregate():
    return AggregateArchive(get_service().root)


def collect_aggregate(port="INNSA", archive=None):
    """Use the existing IMF query adapter, retaining every response before parsing."""
    from app.data.portwatch import _query
    if get_clock().state.mode != LIVE or port not in IMF_PORTS:
        raise ValueError("Aggregate collection requires LIVE and an approved port")
    archive = archive or get_aggregate()
    receipts = []
    def retain(response, params):
        # wall-clock: availability begins when the backend receives the actual provider response.
        receipts.append(archive.retain(response.content, port=port, url=response.url,
            received_at=wall_now(), status=response.status_code, headers=response.headers, params=params))
    # wall-clock: bounded provider query is relative to the real current date, never replay.
    since = (wall_now().date() - timedelta(days=40)).isoformat()
    try:
        _query("Daily_Ports_Data", "portid='" + IMF_PORTS[port] + "' AND date>=DATE '" + since + "'",
            order="date DESC", page=1000, max_records=1000, receipt_sink=retain)
        if not receipts or any(r["errors"] for r in receipts):
            raise ValueError("Aggregate provider response was retained but did not pass validation")
    except Exception as exc:
        # wall-clock: persist real failure time independently of the last successful response.
        archive.check(port, wall_now(), str(exc)[:250])
        raise
    # wall-clock: preserve successful collection cadence without retiming observations.
    archive.check(port, wall_now())
    return receipts[-1]


def aggregate_product(archive, port, now):
    receipts = archive.receipts(now, port)
    last = receipts[-1] if receipts else None
    usable = next((r for r in reversed(receipts) if r["records"] and not r["errors"]), None)
    checked = archive.last_check(port, now)
    base = {"id": "IMF_PORTWATCH_DAILY-" + port, "product": "IMF_PORTWATCH_DAILY", "portCode": port,
        "name": "IMF PortWatch " + NAMES[port] + " daily aggregate", "semanticClass": "AGGREGATE_PORT_ACTIVITY",
        "status": "UNAVAILABLE", "sourceUrl": "https://portwatch.imf.org/pages/data-and-methodology",
        "sha256": None, "originalHashVerified": False, "records": [], "limitations": IMF_LIMITATIONS,
        "clocks": {"reportDate": None, "observedAt": None, "publishedAt": None, "firstAvailableAt": None,
            "checkedAt": last["receivedAt"] if last else None, "observationAgeHours": None, "reportAgeDays": None},
        "collection": {"lastCheckAt": last["receivedAt"] if last else None,
            "lastSuccessfulCollectionAt": usable["receivedAt"] if usable else None, "errors": last["errors"] if last else []},
        "counts": {"records": 0, "retainedReceipts": len(receipts)}}
    if checked and (not last or checked["checkedAt"] >= last["receivedAt"]):
        base["clocks"]["checkedAt"] = checked["checkedAt"]
        base["collection"]["lastCheckAt"] = checked["checkedAt"]
        base["collection"]["errors"] = checked["errors"]
    if not usable:
        return base
    try:
        archive.evidence(usable, now)
    except (OSError, ValueError) as exc:
        base["collection"]["errors"] = [str(exc)]
        return base
    latest_day = max(r["date"] for r in usable["records"])
    records = [{"selector": {"product": "IMF_PORTWATCH_DAILY", "portCode": port, "receiptId": usable["receiptId"], "recordId": row["recordId"]},
        "title": row["date"] + ": " + str(row["portcalls"]) + " aggregate calls", "semanticClass": "AGGREGATE_PORT_ACTIVITY", "record": row}
        for row in sorted(usable["records"], key=lambda row: row["date"], reverse=True)]
    status, age_days = _fresh(latest_day, now)
    return {**base, "id": usable["receiptId"], "status": status, "sourceUrl": usable["sourceUrl"],
        "sha256": usable["sha256"], "originalHashVerified": True, "records": records,
        "location": {"lat": LOCATIONS[port][0], "lon": LOCATIONS[port][1], "basis": "Existing IMF PortWatch physical-port catalogue point; not vessel coordinates"},
        "clocks": {**base["clocks"], "reportDate": latest_day, "firstAvailableAt": usable.get("firstAvailableAt", usable["receivedAt"]),
            "reportAgeDays": age_days, "ageBasis": "Daily source date; exact observation/publication instant unavailable"},
        "counts": {**base["counts"], "records": len(records)}}


def latest_products(now=None, store=None, aggregate=None):
    # wall-clock: source availability and freshness reflect actual receipts, not a replay anchor.
    now, store = now or wall_now(), store or get_service()
    products = []
    for port in PORTS:
        workspace = store.workspace(port, now)
        durable = store.collection_status(port, now)
        check = workspace["freshness"]
        collection = {"lastSuccessfulCollectionAt": durable["lastSuccessfulCollectionAt"],
            "lastCheckAt": check["lastCheckAt"], "errors": (check["lastCheck"] or {}).get("errors", [])}
        for kind in (("position", "expected") if port == "INMAA" else ("traffic",)):
            snapshots = [s for s in workspace["snapshots"] if s["kind"] == kind]
            if snapshots:
                product = _pdf_product(store, snapshots[-1], now, collection)
                product["counts"].update({**workspace["counts"], "portRecords": workspace["counts"]["records"], "records": len(product["records"])})
                products.append(product)
            else:
                products.append({"id": "PUBLIC_PORT_PDF-" + port + "-" + kind, "product": "PUBLIC_PORT_PDF", "portCode": port,
                    "name": NAMES[port] + " published " + kind + " report", "status": "UNAVAILABLE",
                    "semanticClass": "PUBLISHED_EXPECTED_ARRIVAL" if kind == "expected" else "REPORTED_PORT_POSITION",
                    "sourceUrl": "https://www.chennaiport.gov.in/" if port == "INMAA" else "https://paradipport.gov.in/traffic/",
                    "sha256": None, "originalHashVerified": False, "clocks": {"reportDate": None, "observedAt": None,
                        "publishedAt": None, "firstAvailableAt": None, "checkedAt": collection["lastCheckAt"], "observationAgeHours": None},
                    "records": [], "limitations": PDF_LIMITATIONS, "collection": collection, "counts": workspace["counts"]})
    for port in IMF_PORTS:
        products.append(aggregate_product(aggregate or get_aggregate(), port, now))
    return products


def resolve_evidence(selector, now=None):
    # wall-clock: an evidence review cannot consume a response before its real availability.
    now = now or wall_now()
    if not isinstance(selector, dict) or set(selector) - {"product", "portCode", "snapshotId", "receiptId", "recordId"}:
        raise ValueError("Select exact retained operational evidence")
    product = selector.get("product")
    record_id = _key(selector.get("recordId"))
    if product == "PUBLIC_PORT_PDF":
        key, store = _key(selector.get("snapshotId")), get_service()
        snapshot = next((s for port in PORTS for s in store.snapshots(port, now) if s["snapshotId"] == key), None)
        if not snapshot:
            raise ValueError("Public report is unavailable at this clock")
        record = next((r for r in snapshot["records"] if r["recordId"] == record_id), None)
        if not record or record["kind"] not in ("expected", "reported"):
            raise ValueError("Exact retained public report row unavailable")
        if selector.get("portCode", snapshot["portCode"]) != snapshot["portCode"]:
            raise ValueError("Selected physical port differs from the retained original")
        original_path = store.evidence(snapshot["portCode"], key, now)
        original_parse = parse_pdf(original_path.read_bytes(), snapshot["portCode"], snapshot["kind"])
        raw_row = next((r for r in original_parse["records"] if r["recordId"] == record_id), None)
        if raw_row != {k: v for k, v in record.items() if k != "recordAvailableAt"}:
            raise ValueError("Public report fields do not match the original PDF under the current reviewed parser")
        status, age = _fresh(snapshot["reportDate"], now)
        if status == "FUTURE_REPORT" or instant(record["recordAvailableAt"]) > now:
            raise ValueError("Public report fields were unavailable at this clock")
        for field in ("arrivalAt", "berthAt"):
            if record.get(field) and instant(record[field]) > now:
                raise ValueError("Future reported actual event is not accepted")
        selected = _pdf_record(snapshot, record)
        return {**selected, "product": product, "portCode": snapshot["portCode"], "sha256": snapshot["sha256"],
            "originalHashVerified": True, "sourceUrl": snapshot["sourceUrl"], "firstAvailableAt": record["recordAvailableAt"],
            "originalReceivedAt": snapshot["firstSeenAt"], "reportDate": snapshot["reportDate"], "publishedAt": None,
            "observedAt": record.get("arrivalAt"), "status": status, "reportAgeDays": age,
            "parserVersion": snapshot["parserVersion"], "limitations": PDF_LIMITATIONS, "eligibleForRealTarget": False,
            "meaning": "A retained publisher port-report row reviewed as context; no individual demo-vessel association or all-fast is inferred."}
    if product == "IMF_PORTWATCH_DAILY":
        key, archive = _key(selector.get("receiptId")), get_aggregate()
        receipt = next((r for r in archive.receipts(now) if r["receiptId"] == key), None)
        if not receipt or receipt["errors"]:
            raise ValueError("Usable aggregate receipt unavailable at this clock")
        archive.evidence(receipt, now)
        row = next((r for r in receipt["records"] if r["recordId"] == record_id), None)
        if not row or selector.get("portCode", receipt["portCode"]) != receipt["portCode"]:
            raise ValueError("Exact aggregate observation/physical port unavailable")
        status, age = _fresh(row["date"], now)
        return {"selector": {"product": product, "portCode": receipt["portCode"], "receiptId": key, "recordId": record_id},
            "product": product, "semanticClass": "AGGREGATE_PORT_ACTIVITY", "title": NAMES[receipt["portCode"]] + " " + row["date"],
            "portCode": receipt["portCode"], "record": row, "sha256": receipt["sha256"], "originalHashVerified": True,
            "sourceUrl": receipt["sourceUrl"], "firstAvailableAt": row.get("firstAvailableAt", receipt["receivedAt"]), "publishedAt": None,
            "observedAt": None, "reportDate": row["date"], "status": status, "reportAgeDays": age,
            "limitations": IMF_LIMITATIONS, "eligibleForRealTarget": False,
            "meaning": "Daily aggregate published port activity; not an individual vessel movement or proof of actual execution."}
    raise ValueError("Operational product is not approved")


def operational_feed_jobs():
    """The same backend freshness coordinator retries this provider independently."""
    from src.portwatch_os.freshness.job import JobOutcome, RefreshJob
    from src.portwatch_os.freshness.policy import ArtifactProbe, FreshnessPolicy
    def probe():
        # wall-clock: job cadence reflects actual successful receipts, distinct from daily source dates.
        rows = [r for r in get_aggregate().receipts(wall_now(), "INNSA") if r["records"] and not r["errors"]]
        return ArtifactProbe(observed_at=instant(rows[-1]["receivedAt"]) if rows else None,
            detail={"meaning": "Collection cadence only; observation age remains separate"})
    def run(context):
        receipt = collect_aggregate()
        return JobOutcome(changed=True, observed_at=instant(receipt["receivedAt"]),
            detail={"receiptId": receipt["receiptId"], "latestObservationDate": max(r["date"] for r in receipt["records"])})
    return [RefreshJob(policy=FreshnessPolicy(artifact="operational_aggregate_INNSA", label="JNPA aggregate port context",
        provider="IMF PortWatch", fresh_for=timedelta(hours=12), stale_after=timedelta(hours=24), max_attempts=3,
        backoff_base=timedelta(minutes=1), backoff_cap=timedelta(hours=3),
        rationale="Retain raw aggregate daily responses independently of PDFs and weather; receipt freshness never substitutes for observation freshness."),
        probe=probe, run=run, eligibility=lambda: None if get_clock().state.mode == LIVE else "Aggregate collection pauses during replay")]
