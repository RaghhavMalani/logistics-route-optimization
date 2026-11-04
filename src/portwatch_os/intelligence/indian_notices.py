"""Bounded NHO NAVAREA VIII metadata/context adapter; never a closure calculator.

Originals are retained locally for research audit and referenced at the issuer.
This application does not republish the full bulletin or infer hazard clearance.
"""
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import io
import json
import os
import re
import threading
from urllib.parse import urljoin, urlparse

import requests
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from src.portwatch_os.clock import wall_now, world_now
from src.portwatch_os.intelligence.timestamps import instant

FAMILY = "NHO_NAVAREA_VIII"
PARSER = "nho-navarea-metadata-v1"
CATALOGUE = "https://www.hydrobharat.gov.in/hi/web/guest/navarea-warnings"
HOSTS = {"www.hydrobharat.gov.in", "hydrobharat.gov.in"}
TTL = timedelta(hours=6)
LOCK = threading.RLock()
AREA = "NHO_PARADIP_DGPS"
SOURCE_USE = {"status": "REFERENCE_METADATA_ONLY", "basis": "No product-specific public republication licence established in the inspected catalogue. Full bulletin is not served by PortWatch; use issuer links and page references.", "attribution": "Indian Naval Hydrographic Department / NAVAREA VIII coordinator"}


def root_path():
    base = os.getenv("PORTWATCH_CURRENT_ENVIRONMENT_DIR")
    return (Path(base) if base else Path(__file__).resolve().parents[3] / "data/cache/current_environment") / "indian_notices"


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _read(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def trusted(url, document=False):
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and parsed.hostname in HOSTS and parsed.port in (None, 443) and not parsed.username and not parsed.password and (not document or parsed.path.startswith("/documents/"))
    except (ValueError, TypeError):
        return False


def aware(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Explicit timezone required for Indian-source receipt/query instant")
    return parsed.astimezone(timezone.utc)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.href = None; self.words = []; self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a": self.href = dict(attrs).get("href"); self.words = []
    def handle_data(self, value):
        if self.href is not None: self.words.append(value)
    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.links.append((self.href, " ".join(self.words))); self.href = None


def discover_links(raw):
    parser = _Links(); parser.feed(raw.decode("utf-8"))
    links = []
    for href, label in parser.links:
        url = urljoin(CATALOGUE, href)
        identity = re.sub(r"[^a-z0-9]", "", label.lower() + " " + urlparse(url).path.lower())
        if "inforce" in identity and "navarea" in identity and trusted(url, document=True): links.append(url)
    result = sorted(set(links))
    if not result or len(result) > 4: raise ValueError("In-force product links absent or ambiguous; catalogue review required")
    return result


def parse_pages(pages):
    """Preserve issuer identities/DTGs/pages; only one named aid has a reviewed mapping."""
    full = "\n".join(pages)
    product = re.search(r"WARNINGS\s+IN\s+FORCE\s+AS\s+ON\s+(\d{1,2}\s+[A-Z]{3}\s+\d{4})", full, re.I)
    if not product: raise ValueError("Explicit NAVAREA in-force product as-of date unavailable")
    product_date = datetime.strptime(product[1].upper(), "%d %b %Y").date().isoformat()
    entries = []
    offsets=[]; offset=0
    for page_text in pages:
        offsets.append(offset); offset+=len(page_text)+1
    headings=list(re.finditer(r"^[ \t]*NAVAREA[ \t]+VIII[ \t]*[-–][ \t]*(\d{1,4})[ \t]*/[ \t]*(\d{2})\b",full,re.I|re.M))
    for index, heading in enumerate(headings):
        end=headings[index+1].start() if index+1<len(headings) else len(full)
        first_page=max(i+1 for i,start in enumerate(offsets) if start<=heading.start())
        last_page=max(i+1 for i,start in enumerate(offsets) if start<end)
        before = full[max(0, heading.start()-100):heading.start()]
        body = full[heading.end():end]
        # Stop before the next issuer DTG/header; separators are layout, not prose.
        body = re.split(r"\b\d{6}Z/[A-Z]{3}\s*\d{2}\b", body)[0]
        wording = " ".join(re.sub(r"-{5,}", " ", body).split())
        uid = f"{int(heading[1])}/{heading[2]}"
        dates = re.findall(r"(\d{2})(\d{2})(\d{2})Z/([A-Z]{3})\s*(\d{2})", before)
        issued, raw_dtg = None, None
        if dates:
            day, hour, minute, month, year = dates[-1]; raw_dtg = f"{day}{hour}{minute}Z/{month} {year}"
            try:
                issued = datetime.strptime(raw_dtg, "%d%H%MZ/%b %y").replace(tzinfo=timezone.utc).isoformat()
            except ValueError: pass
        mapped = bool(re.search(r"INDIA\s+EAST\s+COAST\s*[-–]\s*PARADIP", wording, re.I) and "DGPS" in wording.upper() and "OFF AIR" in wording.upper())
        coordinate = re.search(r"\((\d{2})-(\d{2}\.\d+)N\s+(\d{3})-(\d{2}\.\d+)E\)", wording)
        point = None
        if mapped and coordinate:
            a,b,c,d = map(float, coordinate.groups())
            if b < 60 and d < 60 and a+b/60 <= 90 and c+d/60 <= 180:
                point = {"lat": a+b/60, "lon": c+d/60, "basis": "Issuer's Paradip lighthouse DGPS station point; not a port boundary, route or closure polygon"}
        # Additional qualifiers/cancellation/OCR/geometry ambiguity never enables calculation.
        cancelled = bool(re.search(r"\bTHIS (?:WARNING|NOTICE) (?:IS |HAS BEEN )?CANCELLED\b", wording, re.I))
        cancellation_refs = [FAMILY+":"+str(int(number))+"/"+year for number,year in re.findall(r"CANCEL\s+NAVAREA\s+VIII\s*[-–]?\s*(\d{1,4})/(\d{2})", wording, re.I)]
        semantic = {"providerNoticeId": uid, "issuerDtgRaw": raw_dtg, "wording": wording, "mapped": mapped, "cancelled": cancelled, "point": point}
        entries.append({"sourceFamily": FAMILY, "providerNoticeId": uid, "noticeId": FAMILY+":"+uid,
            "noticeRef": "NAVAREA VIII "+uid, "title": "Paradip DGPS transmission warning" if mapped else "NAVAREA VIII warning "+uid,
            "issuer": SOURCE_USE["attribution"], "areaId": AREA if mapped else None, "assetId": AREA if mapped else None,
            "portCodes": ["INPRT"] if mapped else [], "area": "Paradip lighthouse DGPS station" if mapped else "NAVAREA VIII; precise operational mapping unreviewed",
            "assetMappingStatus": "REVIEWED_NAMED_AID" if mapped else "UNMAPPED", "coordinates": point,
            "providerIssueAt": issued, "issuerDtgRaw": raw_dtg, "publishedAt": None, "publicationPrecision": "ISSUER_DTG_MINUTE_UTC; publication instant unavailable" if issued else "UNKNOWN",
            "productAsOfDate": product_date, "productPrecision": "DATE_ONLY", "documentPages": list(range(first_page, last_page+1)),
            "status": "SOURCE_NOTICE_CANCELLED" if cancelled else "REVIEW_CONTEXT", "windows": [], "calculationSupported": False,
            "extractionStatus": "CONTEXT_METADATA" if mapped and issued and point else "UNSUPPORTED", "extractionVersion": PARSER,
            "semanticId": digest(semantic), "sourceText": wording, "cancellationRefs": cancellation_refs,
            "restriction": "Issuer reported a navigation-aid transmission outage. No port closure, waiting time or clearance is established." if mapped else "Unreviewed warning; inspect the authority document. No closure or numerical consequence inferred.",
            "applicability": {"vesselScope": "EXPLICIT_OPERATOR_DECLARATION_REQUIRED"}, "sourceUse": SOURCE_USE,
            "originalWording": "Full wording is not republished; inspect the attributed authority document/page.",
            "meaning": "Notice status is source evidence, not actual aid restoration, hazard clearance or vessel execution."})
    if not entries: raise ValueError("No supported provider notice identities extracted")
    by_id = {}
    for row in entries: by_id.setdefault(row["noticeId"], []).append(row)
    result = []
    for same in by_id.values():
        row = dict(same[0]); row["documentPages"] = sorted({p for item in same for p in item["documentPages"]})
        if len({item["semanticId"] for item in same}) > 1:
            row.update(status="AMBIGUOUS", extractionStatus="UNSUPPORTED", restriction="Conflicting duplicate provider identities require source review.")
            row["semanticId"] = digest(sorted(item["semanticId"] for item in same))
        result.append(row)
    return {"productAsOfDate": product_date, "productPrecision": "DATE_ONLY", "notices": result,
        "coverage": "All extracted provider headings in received pages; unmapped/unsupported entries remain inspectable. Omission is not cancellation."}


def parse(raw):
    if not raw.startswith(b"%PDF-") or len(raw) > 8_000_000: raise ValueError("Bounded original PDF required")
    reader = PdfReader(io.BytesIO(raw))
    if not 1 <= len(reader.pages) <= 40: raise ValueError("Product page count outside reviewed bounds")
    return parse_pages([page.extract_text() or "" for page in reader.pages])


def _original(root, raw, at):
    sha = digest(raw); target = root/(sha+".response")
    if not target.exists():
        try:
            with target.open("xb") as stream: stream.write(raw)
        except FileExistsError: pass
    if digest(target.read_bytes()) != sha:
        raise ValueError("Retained original failed its content hash; preserve it for audit and stop collection")
    record = root/(sha+".receipt.json")
    if not record.exists(): _write(record, {"responseSha256": sha, "firstReceivedAt": at})
    return sha, _read(record)["firstReceivedAt"]


def retain(raw, *, document_url, received_at, catalogue_hash=None, root=None, parser_version=PARSER):
    if not trusted(document_url, document=True): raise ValueError("Reviewed authority document URL required")
    at = aware(received_at).isoformat(); parsed = parse(raw)
    root = Path(root) if root is not None else root_path(); root.mkdir(parents=True, exist_ok=True)
    sha, first = _original(root, raw, at)
    old = _read(root/"catalogue-latest.json", {}) or {}; previous = {n["noticeId"]:n for n in old.get("notices", [])}
    notices = []
    explicit = {target: facts for facts in parsed['notices'] for target in facts.get('cancellationRefs', [])}
    for facts in parsed["notices"]:
        if facts['noticeId'] in explicit:
            issuer = explicit[facts['noticeId']]
            facts = {**facts, 'status': 'SOURCE_NOTICE_CANCELLED', 'cancellationNoticeId': issuer['noticeId'],
                'semanticId': digest([facts['semanticId'], 'CANCELLED_BY', issuer['semanticId']]),
                'reason': 'Explicit authority notice cancellation reference; actual aid restoration/hazard clearance is not established.'}
        before = previous.get(facts["noticeId"])
        stable = digest([facts["semanticId"], parser_version])
        unchanged = before and before.get("semanticRevisionId") == stable and before.get("status") == facts.get("status")
        if unchanged:
            row = dict(before)
        else:
            revision = digest([stable, before.get("revisionId") if before else None, at])
            row = {**facts, "revisionId": revision, "semanticRevisionId": stable, "previousRevisionId": before.get("revisionId") if before else None,
                "availableAt": at, "extractedAt": at, "sourceFirstReceivedAt": first, "responseSha256": sha,
                "sourceDocumentRevision": sha, "source": document_url, "catalogueSource": CATALOGUE, "extractionVersion": parser_version}
            _write(root/(revision+".json"), row)
        row.update(checkedAt=at, lastSuccessfulReceiptAt=at, latestResponseSha256=sha, latestProductFirstReceivedAt=first,
            latestDocumentSource=document_url, latestDocumentPages=facts["documentPages"], catalogueResponseSha256=catalogue_hash, productAsOfDate=parsed["productAsOfDate"])
        notices.append(row)
    present = {row["noticeId"] for row in notices}
    for identity, before in previous.items():
        if identity not in present:
            if before.get("status") == "NOT_LISTED" and old.get("responseSha256") == sha:
                notices.append({**before, "checkedAt": at}); continue
            row = {**before, "status": "NOT_LISTED", "calculationSupported": False, "checkedAt": at,
                "reason": "Absent from this received product; no explicit cancellation or actual clearance inferred."}
            row["previousRevisionId"] = before.get("revisionId"); row["revisionId"] = digest([before.get("revisionId"), "NOT_LISTED", sha, at]); row["availableAt"] = at
            _write(root/(row["revisionId"]+".json"), row); notices.append(row)
    cancellations = {target: n for n in notices for target in n.get("cancellationRefs", [])}
    for index, row in enumerate(notices):
        if row["noticeId"] in cancellations and row.get("status") != "SOURCE_NOTICE_CANCELLED":
            cancelled_by = cancellations[row["noticeId"]]
            updated = {**row, "status": "SOURCE_NOTICE_CANCELLED", "previousRevisionId": row["revisionId"], "availableAt": at,
                "cancellationNoticeId": cancelled_by["noticeId"], "cancellationResponseSha256": sha,
                "productAsOfDate":parsed["productAsOfDate"],"latestResponseSha256":sha,"checkedAt":at,"lastSuccessfulReceiptAt":at,
                "reason": "Explicit authority notice cancellation reference; actual aid restoration/hazard clearance is not established."}
            updated["revisionId"] = digest([row["revisionId"], "CANCELLED_BY", cancelled_by["revisionId"]])
            _write(root/(updated["revisionId"]+".json"), updated); notices[index] = updated
    state = {**parsed, "notices": notices, "sourceFamily": FAMILY, "sourceStatus": "RETAINED", "checkedAt": at, "lastSuccessfulReceiptAt": at,
        "responseSha256": sha, "sourceFirstReceivedAt": first, "catalogueResponseSha256": catalogue_hash, "source": document_url, "sourceUse": SOURCE_USE}
    _write(root/"catalogue-latest.json", state)
    _write(root/("catalogue-snapshot-"+digest([sha, parser_version, at])+".json"), state)
    return state


def _fetch(url, *, document=False, fetch=None):
    fetch = fetch or requests.get
    for _ in range(3):
        if not trusted(url, document): raise ValueError("Unreviewed authority URL/redirect")
        for attempt in range(2):
            try:
                response = fetch(url, timeout=(4, 15), allow_redirects=False, headers={"User-Agent": "PortWatch-Research/1.0"})
                break
            except (requests.Timeout, requests.ConnectionError):
                if attempt: raise
                threading.Event().wait(.2)
        if response.status_code in (301,302,303,307,308):
            url = urljoin(url, response.headers.get("Location", "")); continue
        response.raise_for_status()
        if len(response.content) > 8_000_000: raise ValueError("Authority response exceeds bounded size")
        return response.content, url
    raise ValueError("Authority redirect limit reached")


def refresh(*, root=None, fetch=None, force=False):
    root = Path(root) if root is not None else root_path()
    with LOCK:
        root.mkdir(parents=True, exist_ok=True)
        old = _read(root/"catalogue-latest.json", {}) or {}
        # wall-clock: explicit/backend-owned collection cadence and check receipts are real provider attempts.
        checked = wall_now()
        if old.get("checkedAt") and not force and checked < instant(old["checkedAt"])+TTL: return old
        try:
            catalogue, _ = _fetch(CATALOGUE, fetch=fetch)
            catalogue_sha, _ = _original(root, catalogue, checked.isoformat())
            links = discover_links(catalogue)
            products = []
            for url in links[:2]:
                raw, final = _fetch(url, document=True, fetch=fetch)
                products.append((digest(raw), raw, final))
            if len({item[0] for item in products}) != 1: raise ValueError("Conflicting in-force products; authority review required")
            # wall-clock: extraction availability begins after the downloaded product returns, not at its date-only as-of label.
            received = wall_now().isoformat()
            state = retain(products[0][1], document_url=products[0][2], received_at=received, catalogue_hash=catalogue_sha, root=root)
        except (requests.RequestException, ValueError, OSError, KeyError, PdfReadError) as exc:
            state = {**old, "sourceFamily": FAMILY, "sourceStatus": "UNAVAILABLE", "checkedAt": checked.isoformat(),
                "reason": "Authority collection failed: "+type(exc).__name__+"; last good evidence retained", "notices": old.get("notices", [])}
            _write(root/"catalogue-latest.json", state)
            _write(root/("catalogue-snapshot-"+digest(["failure", checked.isoformat()])+".json"), state)
        with (root/"checks.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({k:state.get(k) for k in ("sourceStatus","checkedAt","lastSuccessfulReceiptAt","responseSha256","reason")})+"\n")
        return state


def public_notice(row, *, as_of, source_state=None):
    now = aware(as_of); body = {k:v for k,v in row.items() if k != "sourceText"}
    day = row.get("productAsOfDate")
    status = "CURRENT_PRODUCT_DATE" if day == now.date().isoformat() else "FUTURE_PRODUCT" if day and day > now.date().isoformat() else "HISTORICAL_PRODUCT"
    age = (now.date()-datetime.fromisoformat(day).date()).days if day else None
    if source_state == "UNAVAILABLE": status = "UNAVAILABLE"
    if row.get("checkedAt") and now > instant(row["checkedAt"])+TTL and status == "CURRENT_PRODUCT_DATE": status = "STALE"
    body.update(sourceStatus=status, productAgeDays=age, calculationSupported=False,
        calculationReason="This reviewed family supplies navigation-warning context only; no closure, access window, delay, fuel or cost model is qualified.",
        originalAvailability="RETAINED_REFERENCE_ONLY", originalDownloadAvailable=False)
    return body


def retained(*, root=None, as_of=None):
    """Pure file reads. No mkdir, collector, ledger, task or visitor writes."""
    root = Path(root) if root is not None else root_path(); now = world_now() if as_of is None else aware(as_of)
    pointer = _read(root/"catalogue-latest.json", {}) or {}
    if not isinstance(pointer, dict):
        return {"sourceFamily": FAMILY, "notices": [], "sourceStatus": "MALFORMED", "checkedAt": None, "lastSuccessfulReceiptAt": None,
            "reason": "Retained source metadata cannot be qualified; no current-condition conclusion", "sourceUse": SOURCE_USE}
    if not pointer.get("checkedAt") or instant(pointer["checkedAt"]) > now:
        candidates = [_read(path, {}) or {} for path in root.glob("catalogue-snapshot-*.json")]
        candidates = [state for state in candidates if state.get("checkedAt") and instant(state["checkedAt"]) <= now]
        pointer = max(candidates, key=lambda state: instant(state["checkedAt"]), default={})
    rows = [r for r in pointer.get("notices", []) if isinstance(r, dict) and r.get("availableAt") and instant(r["availableAt"]) <= now]
    # Historical views select the last available revision for each identity, never the later-known pointer.
    if not rows or (pointer.get("checkedAt") and instant(pointer["checkedAt"]) > now) or any(instant(r.get("availableAt", now.isoformat())) > now for r in pointer.get("notices", []) if isinstance(r, dict)):
        revisions = {}
        for path in root.glob("*.json"):
            record = _read(path, {}) or {}
            if record.get("noticeId") and record.get("availableAt") and instant(record["availableAt"]) <= now:
                previous = revisions.get(record["noticeId"])
                if previous is None or instant(record["availableAt"]) > instant(previous["availableAt"]): revisions[record["noticeId"]] = record
        rows = list(revisions.values())
    failure = pointer.get("sourceStatus") == "UNAVAILABLE" and pointer.get("checkedAt") and instant(pointer["checkedAt"]) <= now
    original_statuses = {}
    public_rows = []
    for row in sorted(rows, key=lambda r:r["noticeId"]):
        public = public_notice(row, as_of=now, source_state="UNAVAILABLE" if failure else None)
        sha = row.get("latestResponseSha256") or row.get("responseSha256")
        if sha not in original_statuses:
            status = "MISSING"
            if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha):
                path = root/(sha+".response")
                try:
                    if path.is_file(): status = "AVAILABLE_LOCAL_REFERENCE" if digest(path.read_bytes()) == sha else "CORRUPT"
                except OSError: pass
            original_statuses[sha] = status
        public["originalAvailability"] = original_statuses[sha]
        if original_statuses[sha] != "AVAILABLE_LOCAL_REFERENCE": public["sourceStatus"] = "UNAVAILABLE_ORIGINAL"
        public_rows.append(public)
    return {"sourceFamily": FAMILY, "notices": public_rows,
        "sourceStatus": "UNAVAILABLE" if failure else "RETAINED" if rows else "MISSING", "checkedAt": pointer.get("checkedAt") if pointer.get("checkedAt") and instant(pointer["checkedAt"]) <= now else None,
        "lastSuccessfulReceiptAt": pointer.get("lastSuccessfulReceiptAt") if pointer.get("lastSuccessfulReceiptAt") and instant(pointer["lastSuccessfulReceiptAt"]) <= now else None,
        "reason": pointer.get("reason") if failure else None, "sourceUse": SOURCE_USE}
