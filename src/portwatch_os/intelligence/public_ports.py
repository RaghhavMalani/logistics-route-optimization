"""Public reports, immutable first-seen evidence and prospective ETA cases.

These are publisher-reported events under an explicit IST assumption, never
operator-confirmed all-fast records. JNPA's ledger and protocol are independent.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from html.parser import HTMLParser

from src.portwatch_os.learning.weather_feedback import instant

VERSION = "public-port-report-v1.2"
COHORT_PROTOCOL = "public-port-cohort-v2"
PORTS = ("INPRT", "INMAA")
PARADIP_INDEX = "https://paradipport.gov.in/traffic/"
CHENNAI_POSITION = "https://www.chennaiport.gov.in/api/static/default/vessel_report/pos.pdf"
CHENNAI_ETA = "https://www.chennaiport.gov.in/api/static/default/vessel_report/eta.pdf"
IST = timezone(timedelta(hours=5, minutes=30))
TIMEZONE_NOTE = "Assumed Asia/Kolkata (UTC+05:30); publisher event/timezone definitions are unconfirmed"
MAX_BYTES = 5_000_000


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def approved(url: str, *, index: bool = False) -> bool:
    p = urlparse(url)
    if p.scheme != "https" or p.username or p.password or p.port not in (None, 443) or p.query or p.fragment:
        return False
    if url in (CHENNAI_POSITION, CHENNAI_ETA):
        return True
    if p.hostname not in ("paradipport.gov.in", "www.paradipport.gov.in"):
        return False
    return (index and p.path == "/traffic/") or bool(re.fullmatch(
        r"/(?:uploads/\d{4}/\d{2}|Writereaddata/Daily_Traffic)/dtr\d{4}(?:_\d+)?\.pdf", p.path))


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not approved(newurl, index=True):
            raise ValueError("Official source redirected outside the approved URLs")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str) -> bytes:
    if not approved(url, index=True):
        raise ValueError("Source URL is not approved")
    with build_opener(SafeRedirect()).open(Request(url, headers={"User-Agent": "PortWatch-public-research/1"}), timeout=25) as response:
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError("Official document exceeds the collection limit")
    return payload


class ReportLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            url = urljoin(PARADIP_INDEX, dict(attrs).get("href", ""))
            if approved(url) and url not in self.urls:
                self.urls.append(url)


def normalize_name(value: str) -> str:
    value = re.sub(r"^(?:M[VT]\.?|RV\.?)\s+", "", value.strip(), flags=re.I)
    value = re.sub(r"\s*\(\d+\s*HMC\)\s*", "", value, flags=re.I)
    return re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()


def number(value: str) -> float | None:
    if not re.fullmatch(r"\d+(?:\.\d+)?", value.strip()):
        return None
    n = float(value)
    return n if 0 < n <= 500 else None


def timestamp(raw: str, report: date, *, future: bool = False) -> tuple[str | None, list[str]]:
    """Missing clocks stay missing; short years are bounded by the report date."""
    raw = raw.strip()
    dm = re.search(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})(?:[-/](\d{4}|\d{2}))?(?!\d)", raw)
    tm = re.search(r"(?<!\d)([0-2]\d):([0-5]\d)(?!\d)", raw)
    if not tm:
        # Paradip's unpunctuated HHMM is accepted only as its own token.
        clocks = [t for t in raw.split() if re.fullmatch(r"[0-2]\d[0-5]\d", t) and not (dm and t == dm.group(3))]
        if len(clocks) == 1:
            tm_values = (int(clocks[0][:2]), int(clocks[0][2:]))
        else:
            return None, ["MISSING_CLOCK" if not clocks else "AMBIGUOUS_CLOCK"]
    else:
        tm_values = (int(tm[1]), int(tm[2]))
    if not dm:
        return None, ["MALFORMED_DATE"]
    flags = []
    try:
        if dm[3]:
            year = int(dm[3]) + (2000 if len(dm[3]) == 2 else 0)
            day = date(year, int(dm[2]), int(dm[1]))
        else:
            flags.append("YEAR_FROM_REPORT")
            candidates = []
            for year in (report.year - 1, report.year, report.year + 1):
                try:
                    d = date(year, int(dm[2]), int(dm[1]))
                    if (abs((d-report).days) <= 90 if future else d <= report and (report-d).days <= 366):
                        candidates.append(d)
                except ValueError:
                    continue
            if not candidates:
                return None, ["MALFORMED_DATE"]
            day = min(candidates, key=lambda d: abs((d-report).days))
        value = datetime.combine(day, datetime.min.time(), IST).replace(hour=tm_values[0], minute=tm_values[1])
        if not future and day > report:
            return None, ["EVENT_AFTER_REPORT_DATE"]
        return stamp(value), flags
    except ValueError:
        return None, ["MALFORMED_DATE_OR_CLOCK"]


def text_at(page, x0, x1, y0, y1) -> str:
    return (page.crop((x0, max(0, y0), x1, min(page.height, y1))).extract_text(x_tolerance=2, y_tolerance=2) or "").strip()


def lines(page, x0, x1):
    return page.crop((x0, 0, x1, page.height)).extract_text_lines(x_tolerance=2, y_tolerance=2)


def date_heading(line):
    """Separate actual PDF baselines; conflicting printed dates stay unresolved."""
    baselines = {}
    for char in line.get("chars", []):
        baselines.setdefault(round(char["top"], 1), []).append(char)
    candidates = []
    for chars in baselines.values():
        text = "".join(c["text"] for c in sorted(chars, key=lambda c: c["x0"])).strip()
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", text):
            try:
                datetime.strptime(text, "%d/%m/%Y")
                candidates.append(text)
            except ValueError:
                pass
    distinct = sorted(set(candidates))
    # Require every glyph to belong to complete dates; never repair arbitrary noise.
    complete = candidates and sum(len(c) for c in candidates) == len(line.get("chars", []))
    return (distinct[0] if complete and len(distinct) == 1 else None), distinct if complete else []


def record(kind, name, loa, beam, draft, berth, raw, report, page):
    row = {"kind": kind, "vesselName": name.strip(), "nameKey": normalize_name(name), "loa": number(loa),
           "beam": number(beam), "draft": number(draft), "berthRef": berth.strip() or None,
           "rawTimestamps": raw, "page": page + 1, "flags": [], "etaAt": None, "arrivalAt": None, "berthAt": None}
    if row["loa"] is None:
        row["flags"].append("MISSING_DIMENSIONS")
    for key, val in raw.items():
        parsed, flags = timestamp(val, report, future=key in ("etaAt", "movementAt"))
        row[key] = parsed
        row["flags"].extend(f"{key}:{f}" for f in flags)
    if row["arrivalAt"] and row["berthAt"] and instant(row["berthAt"]) < instant(row["arrivalAt"]):
        row["flags"].append("BERTH_BEFORE_ARRIVAL")
        row["berthAt"] = None
    return row


def parse_pdf(payload: bytes, port: str, kind: str) -> dict:
    import pdfplumber
    records, issues = [], []
    if not payload.startswith(b"%PDF-"):
        raise ValueError("Official response is not a PDF")
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        if not 1 <= len(pdf.pages) <= 12:
            raise ValueError("LAYOUT_CHANGED: unexpected page count")
        title = pdf.pages[0].extract_text() or ""
        if port == "INPRT":
            found = re.search(r"HELD ON DT:\s*(\d{2}-\d{2}-\d{4})", title)
            if "PARADIP PORT AUTHORITY" not in title or not found:
                raise ValueError("LAYOUT_CHANGED: Paradip report date/header missing")
            report = datetime.strptime(found[1], "%d-%m-%Y").date()
        else:
            found = re.search(r"(?:VESSEL POSITION ON|VESSELS\s+DATE\s*:)\s*(\d{2}/\d{2}/\d{4})", title)
            if "CHENNAI PORT AUTHORITY" not in title or not found:
                raise ValueError("LAYOUT_CHANGED: Chennai report date/header missing")
            report = datetime.strptime(found[1], "%d/%m/%Y").date()
        for n, p in enumerate(pdf.pages):
            page_text = p.extract_text() or ""
            width = 841 if port == "INPRT" else 792
            if abs(p.width-width) > 2 or abs(p.height-(595 if port == "INPRT" else 612)) > 2:
                raise ValueError("LAYOUT_CHANGED: page geometry")
            if port == "INPRT":
                if "C. EXPECTED VESSSEL" in page_text:
                    if not all(h in page_text for h in ("ETA", "LOA", "DRAFT")):
                        raise ValueError("LAYOUT_CHANGED: expected columns")
                    for w in lines(p, 30, 155):
                        if re.match(r"^(?:MV|MT|RV)\. ", w["text"]):
                            y = w["top"]
                            records.append(record("expected", text_at(p, 30, 155, y-1, y+9),
                                text_at(p, 155, 182, y-2, y+9), text_at(p, 182, 210, y-2, y+9),
                                text_at(p, 210, 240, y-2, y+9), text_at(p, 590, 610, y-2, y+9),
                                {"etaAt": text_at(p, 750, 795, y-2, y+9)}, report, n))
                elif "D. BERTHING MOVEMENTS" in page_text:
                    for w in lines(p, 59, 188):
                        if re.match(r"^(?:MV|MT|RV)\. ", w["text"]):
                            y = w["top"]
                            row = record("planned_movement", text_at(p, 59, 188, y-1, y+9),
                                text_at(p, 188, 218, y-2, y+9), text_at(p, 218, 244, y-2, y+9),
                                text_at(p, 244, 270, y-2, y+9), text_at(p, 450, 512, y-2, y+9),
                                {"movementAt": text_at(p, 14, 59, y-2, y+9)+" "+text_at(p, 515, 555, y-2, y+9)}, report, n)
                            row["purpose"] = text_at(p, 399, 448, y-2, y+9)
                            records.append(row)
                elif "B. VESSELS WAITING AT ANCHORAGE" in page_text:
                    for w in lines(p, 85, 196):
                        if re.match(r"^(?:MV|MT|RV)\. ", w["text"]):
                            y = w["top"]
                            records.append(record("reported", text_at(p, 85, 196, y-1, y+9),
                                text_at(p, 227, 253, y-2, y+9), text_at(p, 253, 280, y-2, y+9),
                                text_at(p, 282, 308, y-2, y+9), "",
                                {"arrivalAt": text_at(p, 508, 548, y-2, y+9)}, report, n))
                elif n <= 2:
                    if n == 0 and "ARVLREADYBERTH" not in re.sub(r"\s+", "", text_at(p, 270, 351, 80, 120)):
                        raise ValueError("LAYOUT_CHANGED: arrival/readiness/berth columns")
                    for w in lines(p, 47, 184):
                        if re.match(r"^(?:MV|MT|RV)\. ", w["text"]):
                            y = w["top"]
                            records.append(record("reported", text_at(p, 47, 184, y-1, y+9),
                                text_at(p, 185, 212, y+7, y+20), text_at(p, 212, 240, y+7, y+20),
                                text_at(p, 240, 270, y+7, y+20), text_at(p, 16, 47, y-3, y+9),
                                {"arrivalAt": text_at(p, 273, 297, y-2, y+20),
                                 "berthAt": text_at(p, 323, 351, y-2, y+20)}, report, n))
            elif kind == "expected":
                if not all(h in page_text for h in ("Vessel Name", "Time", "LOA", "Draft", "Beam")):
                    raise ValueError("LAYOUT_CHANGED: Chennai expected columns")
                current_date, heading_evidence = None, None
                for line in lines(p, 26, 121):
                    name = line["text"].strip()
                    y = line["top"]
                    if name.startswith("Print"):
                        continue
                    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", name):
                        current_date = name
                        heading_evidence = None
                        continue
                    if "/" in name and y > 85 and not name.startswith("Print"):
                        recovered, candidates = date_heading(line)
                        code = "RECOVERED_IDENTICAL_DATE_HEADINGS" if recovered else "CONFLICTING_DATE_HEADINGS" if len(candidates) > 1 else "MALFORMED_DATE_HEADING"
                        heading_evidence = {"raw": name, "candidates": candidates, "code": code}
                        issues.append({"page": n+1, **heading_evidence})
                        current_date = recovered
                        continue
                    if y < 90 or name in ("Vessel Name", "CHENNAI PORT"):
                        continue
                    clock = text_at(p, 122, 148, y-1, y+9)
                    if not clock:
                        continue
                    row = record("expected", name, text_at(p, 566, 596, y-1, y+10),
                        text_at(p, 627, 653, y-1, y+10), text_at(p, 597, 625, y-1, y+10),
                        text_at(p, 403, 465, y-1, y+10), {"etaAt": (current_date or "INVALID")+" "+clock}, report, n)
                    if heading_evidence:
                        row["dateHeadingEvidence"] = heading_evidence
                        if not current_date:
                            row["flags"].append("etaAt:" + heading_evidence["code"])
                    records.append(row)
            else:
                if "Arrived" not in page_text or "Berthed" not in page_text:
                    raise ValueError("LAYOUT_CHANGED: Chennai position columns")
                for line in lines(p, 73, 208):
                    m = re.fullmatch(r"(.+?)\s*/\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", line["text"])
                    if not m:
                        continue
                    y = line["top"]
                    records.append(record("reported", m[1], m[2], "", m[3],
                        text_at(p, 32, 71, y-1, y+9), {"arrivalAt": text_at(p, 300, 330, y-6, y+14),
                        "berthAt": text_at(p, 334, 359, y-6, y+14)}, report, n))
                # Outer-anchorage table has a different schema; derive cells from its headers.
                for table in p.extract_tables():
                    header = next((r for r in table if "Anchored on" in r), None)
                    if not header:
                        continue
                    fields = {v: i for i, v in enumerate(header) if v}
                    for row in table[table.index(header)+1:]:
                        name = row[fields["Vessel Name - Preferred Berth"]]
                        if not name:
                            continue
                        parts = name.split(" - ", 1)
                        records.append(record("reported", parts[0], row[fields["LOA(M)"]] or "", "",
                            row[fields["Draft(M)"]] or "", parts[1] if len(parts)>1 else "",
                            {"arrivalAt": row[fields["Anchored on"]] or ""}, report, n))
        if not records:
            raise ValueError("LAYOUT_CHANGED: no identifiable vessel rows")
        for i, row in enumerate(records):
            row["recordId"] = digest(json.dumps([port, kind, i, row], sort_keys=True))
        return {"reportDate": report.isoformat(), "records": records, "issues": issues}


def compatible(a, b) -> bool:
    if a["nameKey"] != b["nameKey"] or a["loa"] is None or b["loa"] is None or abs(a["loa"]-b["loa"]) > 0.5:
        return False
    return a["beam"] is None or b["beam"] is None or abs(a["beam"]-b["beam"]) <= 0.5


class PublicPilot:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root/"evidence").mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root/"public_ports.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY,port TEXT,kind TEXT,sha TEXT,url TEXT,
            first_seen TEXT,report_date TEXT,parser TEXT,body TEXT,UNIQUE(port,kind,sha));
          CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY,port TEXT,issued TEXT,body TEXT);
          CREATE TABLE IF NOT EXISTS checks(id INTEGER PRIMARY KEY,port TEXT,at TEXT,actor TEXT,body TEXT);
          CREATE TABLE IF NOT EXISTS benchmarks(id TEXT PRIMARY KEY,port TEXT,at TEXT,body TEXT);
          CREATE TABLE IF NOT EXISTS parses(snapshot TEXT,parser TEXT,at TEXT,body TEXT,PRIMARY KEY(snapshot,parser));
          CREATE TABLE IF NOT EXISTS cohorts(id TEXT PRIMARY KEY,port TEXT,created TEXT,body TEXT);
          CREATE TABLE IF NOT EXISTS cohort_cases(cohort TEXT,case_id TEXT PRIMARY KEY,at TEXT);
          CREATE TABLE IF NOT EXISTS collections(id TEXT PRIMARY KEY,port TEXT,at TEXT,body TEXT);
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def collection_status(self, port, as_of):
        """Durable workflow failures and last success survive backend restarts."""
        with self.lock:
            rows = self.db.execute("SELECT at,body FROM collections WHERE port=? AND at<=? ORDER BY at DESC", (port, stamp(as_of))).fetchall()
            runs = [(r["at"], json.loads(r["body"])) for r in rows]
            if runs:
                success = next((at for at, r in runs if not r["errors"]), None)
                if success is None:
                    cutoff = min(r["startedAt"] for _, r in runs)
                    checks = self.db.execute("SELECT at,body FROM checks WHERE port=? AND at<? ORDER BY id DESC", (port, cutoff)).fetchall()
                    success = next((r["at"] for r in checks if not json.loads(r["body"])["errors"] and json.loads(r["body"])["results"]), None)
                return {"lastRun": runs[0][1], "lastSuccessfulCollectionAt": success}
            # Earlier operator collections remain valid cadence evidence.
            checks = self.db.execute("SELECT at,body FROM checks WHERE port=? AND at<=? ORDER BY id DESC", (port, stamp(as_of))).fetchall()
            success = next((r["at"] for r in checks if not json.loads(r["body"])["errors"] and json.loads(r["body"])["results"]), None)
            return {"lastRun": None, "lastSuccessfulCollectionAt": success}

    def cohorts(self, port, as_of):
        result = []
        for row in self.db.execute("SELECT body FROM cohorts WHERE port=? AND created<=? ORDER BY created,id", (port, stamp(as_of))):
            cohort = json.loads(row[0])
            cohort["caseIds"] = [r[0] for r in self.db.execute(
                "SELECT case_id FROM cohort_cases WHERE cohort=? AND at<=? ORDER BY at,case_id",
                (cohort["cohortId"], stamp(as_of)))]
            cohort["status"] = "CLOSED" if as_of >= instant(cohort["enrollmentEndAt"]) else "ENROLLING"
            result.append(cohort)
        return result

    def start_cohort(self, port, now, actor, *, enrollment_days=30):
        """Fix an enrollment cutoff before evaluation; include every unassigned case.

        Existing frozen cases are included without selecting on outcomes. Membership
        is exclusive and availability-stamped; no backdated cutoff or reopening.
        """
        if port not in PORTS or now.tzinfo is None or not 1 <= enrollment_days <= 90:
            raise ValueError("Cohort requires a supported port, aware clock and 1–90 enrollment days")
        with self.lock, self.db:
            if any(c["status"] == "ENROLLING" for c in self.cohorts(port, now)):
                raise ValueError("This port already has an enrolling cohort")
            rows = self.db.execute("SELECT id,issued FROM cases WHERE port=? AND issued<=? AND id NOT IN (SELECT case_id FROM cohort_cases) ORDER BY issued,id", (port, stamp(now))).fetchall()
            cohort = {"cohortId": digest(port+stamp(now)+COHORT_PROTOCOL), "portCode": port,
                "createdAt": stamp(now), "createdBy": actor, "enrollmentStartAt": rows[0]["issued"] if rows else stamp(now),
                "enrollmentEndAt": stamp(now+timedelta(days=enrollment_days)), "protocol": COHORT_PROTOCOL,
                "initialCaseIds": [r["id"] for r in rows], "minimumUsablePerTarget": 60,
                "minimumPartitions": [24, 10, 10], "matchWindowHours": 72,
                "partitionPolicy": "60/20/20 of all enrolled cases by frozen time; equal instants stay together; availability purge"}
            self.db.execute("INSERT INTO cohorts VALUES(?,?,?,?)", (cohort["cohortId"], port, stamp(now), json.dumps(cohort)))
            self.db.executemany("INSERT INTO cohort_cases VALUES(?,?,?)", [(cohort["cohortId"], r["id"], stamp(now)) for r in rows])
            return self.cohorts(port, now)[-1]

    def snapshots(self, port, as_of):
        rows = self.db.execute("SELECT * FROM snapshots WHERE port=? AND first_seen<=? ORDER BY first_seen,id", (port, stamp(as_of))).fetchall()
        result = []
        for r in rows:
            versions = self.db.execute("SELECT * FROM parses WHERE snapshot=? AND at<=? ORDER BY at,parser", (r["id"], stamp(as_of))).fetchall()
            latest = versions[-1] if versions else None
            body = json.loads(latest["body"] if latest else r["body"])
            known_times = {}
            for at, parsed_body in [(r["first_seen"], json.loads(r["body"]))]+[(v["at"], json.loads(v["body"])) for v in versions]:
                for row in parsed_body["records"]:
                    fact = digest(json.dumps({k: v for k, v in row.items() if k != "recordId"}, sort_keys=True))
                    known_times.setdefault(fact, at)
            for row in body["records"]:
                fact = digest(json.dumps({k: v for k, v in row.items() if k != "recordId"}, sort_keys=True))
                row["recordAvailableAt"] = known_times[fact]
            result.append({"snapshotId": r["id"], "portCode": r["port"], "kind": r["kind"], "sha256": r["sha"],
                "sourceUrl": r["url"], "firstSeenAt": r["first_seen"], "reportDate": r["report_date"],
                "originalParserVersion": r["parser"], "parserVersion": latest["parser"] if latest else r["parser"],
                "parsedAt": latest["at"] if latest else r["first_seen"],
                "parseHistory": [{"parserVersion": r["parser"], "at": r["first_seen"]}]+[{"parserVersion": v["parser"], "at": v["at"]} for v in versions],
                **body})
        return result

    def import_pdf(self, port, kind, url, payload, *, collected: datetime, actor: str):
        if port not in PORTS or not approved(url) or (port == "INMAA" and (kind not in ("position", "expected") or url != (CHENNAI_ETA if kind == "expected" else CHENNAI_POSITION))) or (port == "INPRT" and (kind != "traffic" or "paradipport.gov.in" not in url)):
            raise ValueError("Port/source combination is not approved")
        if len(payload) > MAX_BYTES or not payload.startswith(b"%PDF-"):
            raise ValueError("Source must be a PDF within the collection limit")
        if collected.tzinfo is None:
            raise ValueError("Collection clock requires a timezone")
        sha = digest(payload)
        key = digest(port+kind+sha)
        # Original bytes are retained before parser execution, including changed layouts.
        path = self.root/"evidence"/(sha+".pdf")
        with self.lock:
            if path.exists():
                if digest(path.read_bytes()) != sha:
                    raise ValueError("Archived PDF hash mismatch")
            else:
                with path.open("xb") as stream:
                    stream.write(payload)
            old = self.db.execute("SELECT * FROM snapshots WHERE id=?", (key,)).fetchone()
            if old and (old["parser"] == VERSION or self.db.execute("SELECT 1 FROM parses WHERE snapshot=? AND parser=?", (key, VERSION)).fetchone()):
                return {"snapshotId": key, "new": False}
            try:
                parsed = parse_pdf(payload, port, kind)
            except Exception as exc:
                parsed = {"reportDate": None, "records": [], "issues": [{"code": "PARSER_UNAVAILABLE", "raw": str(exc)[:300]}]}
            body = {"records": parsed["records"], "issues": parsed["issues"], "collectedBy": actor}
            if old:
                # A new parser view is available only now. Original bytes/metadata,
                # first-seen time and all frozen cases remain immutable.
                with self.db:
                    self.db.execute("INSERT INTO parses VALUES(?,?,?,?)", (key, VERSION, stamp(collected), json.dumps(body)))
                return {"snapshotId": key, "new": False, "reparsed": True}
            with self.db:
                self.db.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?,?,?,?)", (key, port, kind, sha, url,
                    stamp(collected), parsed["reportDate"], VERSION, json.dumps(body)))
                existing = self.workspace(port, collected)["cases"]
                historical = [r for s in self.snapshots(port, collected) for r in s["records"] if r["kind"] == "reported" and r["arrivalAt"]]
                fresh = parsed["reportDate"] and 0 <= (collected.astimezone(IST).date()-date.fromisoformat(parsed["reportDate"])).days <= 3
                for row in parsed["records"]:
                    if row["kind"] != "expected" or not row["etaAt"] or not row["loa"] or not fresh:
                        continue
                    eta = instant(row["etaAt"])
                    if not collected < eta <= collected+timedelta(days=21):
                        continue
                    # A later publication cannot retime a frozen case or enroll a known arrived call.
                    if any(compatible(row, c) and abs((eta-instant(c["etaAt"])).total_seconds()) <= 3*86400 and c["status"] in ("PENDING", "AMBIGUOUS") for c in existing):
                        continue
                    if any(compatible(row, h) and abs((eta-instant(h["arrivalAt"])).total_seconds()) <= 3*86400 for h in historical):
                        continue
                    case_id = digest(key+row["recordId"])
                    case = {**row, "caseId": case_id, "snapshotId": key, "portCode": port,
                            "frozenAt": stamp(collected), "freezeActor": actor, "timezoneNote": TIMEZONE_NOTE, "parserVersion": VERSION}
                    self.db.execute("INSERT INTO cases VALUES(?,?,?,?)", (case_id, port, stamp(collected), json.dumps(case)))
                    active = next((c for c in self.cohorts(port, collected) if c["status"] == "ENROLLING"), None)
                    if active:
                        self.db.execute("INSERT INTO cohort_cases VALUES(?,?,?)", (active["cohortId"], case_id, stamp(collected)))
                    existing.append({**case, "status": "PENDING"})
            return {"snapshotId": key, "new": True, "records": len(parsed["records"]), "issues": len(parsed["issues"])}

    def refresh(self, port, actor, *, report_limit=3):
        if port not in PORTS or not 1 <= report_limit <= 7:
            raise ValueError("Public pilot supports INPRT/INMAA and at most seven reports per refresh")
        from src.portwatch_os.clock import LIVE, get_clock, wall_now
        if get_clock().state.mode != LIVE:
            raise ValueError("Official collection requires the live clock")
        results, errors = [], []
        if port == "INPRT":
            parser = ReportLinks()
            try:
                parser.feed(fetch(PARADIP_INDEX).decode("utf-8", errors="replace"))
                sources = [("traffic", url) for url in parser.urls[:report_limit]]
                if not sources:
                    raise ValueError("Paradip index has no approved daily reports")
            except Exception as exc:
                sources = []
                errors.append(str(exc)[:300])
        else:
            sources = [("position", CHENNAI_POSITION), ("expected", CHENNAI_ETA)]
        for kind, url in sources:
            try:
                payload = fetch(url)
                if get_clock().state.mode != LIVE:
                    raise ValueError("Clock changed during collection; document was not imported")
                # wall-clock: collection receipt is the real present, never the replay anchor.
                results.append(self.import_pdf(port, kind, url, payload, collected=wall_now(), actor=actor))
            except Exception as exc:
                errors.append(f"{url}: {str(exc)[:250]}")
        with self.lock, self.db:
            # wall-clock: this audit records when an actual collection attempt finished.
            self.db.execute("INSERT INTO checks(port,at,actor,body) VALUES(?,?,?,?)", (port, stamp(wall_now()), actor,
                json.dumps({"results": results, "errors": errors})))
        return {"results": results, "errors": errors}

    def workspace(self, port, as_of):
        with self.lock:
            snapshots = self.snapshots(port, as_of)
            observations = []
            for s in snapshots:
                for row in s["records"]:
                    if row["kind"] == "reported":
                        known = {**row, "snapshotId": s["snapshotId"], "availableAt": row["recordAvailableAt"]}
                        for field in ("arrivalAt", "berthAt"):
                            if known[field] and instant(known[field]) > as_of:
                                known[field] = None
                        observations.append(known)
            # Repeated facts collapse; contradictory berth references/times stay distinct.
            unique = {}
            for row in observations:
                k = (row["nameKey"], row["loa"], row["beam"], row["arrivalAt"], row["berthAt"], row["berthRef"])
                if k not in unique or row["availableAt"] < unique[k]["availableAt"]:
                    unique[k] = row
            observations = list(unique.values())
            cases = [json.loads(r[0]) for r in self.db.execute("SELECT body FROM cases WHERE port=? AND issued<=? ORDER BY issued,id", (port, stamp(as_of)))]
            candidates = {}
            for c in cases:
                candidate = [o for o in observations if o["arrivalAt"] and compatible(c, o)
                    and instant(o["availableAt"]) >= instant(c["frozenAt"])
                    and instant(o["arrivalAt"]) > instant(c["frozenAt"])
                    and abs((instant(o["arrivalAt"])-instant(c["etaAt"])).total_seconds()) <= 3*86400]
                # An arrival-only report and its later berth report are the same call.
                grouped = {}
                for o in candidate:
                    grouped.setdefault(o["arrivalAt"], []).append(o)
                candidates[c["caseId"]] = grouped
            for c in cases:
                groups = candidates[c["caseId"]]
                c.update(status="PENDING", outcome=None, exclusions=[])
                arrivals = list(groups)
                shared = len(arrivals) == 1 and any(other != c["caseId"] and arrivals[0] in g and compatible(c, next(x for x in cases if x["caseId"] == other)) for other, g in candidates.items())
                if len(arrivals) > 1 or shared:
                    c.update(status="AMBIGUOUS", exclusions=["AMBIGUOUS_CALL_MATCH"])
                elif len(arrivals) == 1:
                    matches = groups[arrivals[0]]
                    berth_matches = [o for o in matches if o["berthAt"]]
                    times = {o["berthAt"] for o in berth_matches}
                    refs = {o["berthRef"] for o in berth_matches if o["berthRef"]}
                    arrival = min(matches, key=lambda o: o["availableAt"])
                    berth = min(berth_matches, key=lambda o: o["availableAt"]) if len(times) == 1 and len(refs) <= 1 else None
                    c["status"] = "MATCHED"
                    c["outcome"] = {"arrivalAt": arrival["arrivalAt"], "arrivalAvailableAt": arrival["availableAt"],
                        "arrivalSnapshotId": arrival["snapshotId"], "arrivalErrorHours": (instant(arrival["arrivalAt"])-instant(c["etaAt"])).total_seconds()/3600,
                        "berthAt": berth["berthAt"] if berth else None, "berthAvailableAt": berth["availableAt"] if berth else None,
                        "berthSnapshotId": berth["snapshotId"] if berth else None, "berthRef": berth["berthRef"] if berth else None,
                        "waitingHours": (instant(berth["berthAt"])-instant(arrival["arrivalAt"])).total_seconds()/3600 if berth else None}
                    c["berthEvidence"] = [{k: o[k] for k in ("snapshotId", "recordId", "berthAt", "berthRef", "availableAt", "rawTimestamps", "page")} for o in berth_matches]
                    if len(times)>1:
                        c["exclusions"].append("CONFLICTING_REPORTED_BERTH_TIMES")
                    if len(refs)>1:
                        c["exclusions"].append("CONFLICTING_REPORTED_BERTH_REFERENCES")
                    if not berth:
                        c["exclusions"].append("WAITING_OUTCOME_UNAVAILABLE")
                elif as_of > instant(c["etaAt"])+timedelta(days=3):
                    c.update(status="UNRESOLVED", exclusions=["NO_REPORT_MATCH_WITHIN_WINDOW"])
            check = self.db.execute("SELECT at,body FROM checks WHERE port=? AND at<=? ORDER BY id DESC LIMIT 1", (port, stamp(as_of))).fetchone()
            reports = [json.loads(r[0]) for r in self.db.execute("SELECT body FROM benchmarks WHERE port=? AND at<=? ORDER BY at", (port, stamp(as_of)))]
            bad = [dict(snapshotId=s["snapshotId"], **issue) for s in snapshots for issue in s["issues"]]
            excluded = [dict(snapshotId=s["snapshotId"], recordId=r["recordId"], vesselName=r["vesselName"], flags=r["flags"])
                        for s in snapshots for r in s["records"] if r["flags"] and any("YEAR_FROM_REPORT" not in f for f in r["flags"])]
            cohorts = self.cohorts(port, as_of)
            assigned = {key for cohort in cohorts for key in cohort["caseIds"]}
            return {"portCode": port, "asOf": stamp(as_of), "parserVersion": VERSION, "timezoneNote": TIMEZONE_NOTE,
                "targets": ["Frozen published ETA vs reported arrival", "Reported arrival-to-berth hours; not confirmed all-fast"],
                "snapshots": snapshots, "cases": cases, "cohorts": cohorts, "unassignedCases": sum(c["caseId"] not in assigned for c in cases),
                "historicalObservations": observations, "issues": bad, "excludedRecords": excluded,
                "counts": {"snapshots": len(snapshots), "records": sum(len(s["records"]) for s in snapshots), "frozen": len(cases),
                    "pending": sum(c["status"] == "PENDING" for c in cases), "matched": sum(c["status"] == "MATCHED" for c in cases),
                    "ambiguous": sum(c["status"] == "AMBIGUOUS" for c in cases), "unresolved": sum(c["status"] == "UNRESOLVED" for c in cases),
                    "waitingOutcomes": sum(bool(c["outcome"] and c["outcome"]["waitingHours"] is not None) for c in cases), "excludedRecords": len(excluded)},
                "freshness": {"lastCollectionAt": max((s["firstSeenAt"] for s in snapshots), default=None),
                    "latestReportDate": max((s["reportDate"] for s in snapshots if s["reportDate"]), default=None),
                    "lastCheckAt": check["at"] if check else None, "lastCheck": json.loads(check["body"]) if check else None},
                "benchmarks": reports, "evaluationReason": "Need 60 resolved prospective calls per target, with 24 fitting / 10 calibration / 10 untouched holdout after availability purging"}

    def evidence(self, port, key, as_of):
        snapshot = next((s for s in self.snapshots(port, as_of) if s["snapshotId"] == key), None)
        if not snapshot:
            raise ValueError("Archived evidence is unavailable at this clock")
        path = self.root/"evidence"/(snapshot["sha256"]+".pdf")
        if digest(path.read_bytes()) != snapshot["sha256"]:
            raise ValueError("Archived PDF hash mismatch")
        return path

    def evaluate(self, port, now, actor, *, cohort_id=None):
        """Seal chronological baseline comparisons; no trained operational prediction."""
        import statistics
        workspace = self.workspace(port, now)
        cohorts = workspace["cohorts"]
        cohort = next((c for c in cohorts if c["cohortId"] == cohort_id), None) if cohort_id else next((c for c in reversed(cohorts) if c["status"] == "CLOSED"), cohorts[-1] if cohorts else None)
        if cohort_id and cohort is None:
            raise ValueError("Cohort is unavailable for this port and clock")
        prior = [r for r in workspace["benchmarks"] if cohort and r.get("cohortId") == cohort["cohortId"]]
        if prior:
            return prior[-1]  # Sealed cohort never reuses holdout labels.
        cases = sorted([c for c in workspace["cases"] if cohort and c["caseId"] in cohort["caseIds"]], key=lambda c: (c["frozenAt"], c["caseId"]))
        targets = {}
        for target in ("arrival", "waiting"):
            usable = [c for c in cases if c["outcome"] and (target == "arrival" or c["outcome"]["waitingHours"] is not None)]
            if not cohort or cohort["status"] != "CLOSED":
                targets[target] = {"status": "UNAVAILABLE", "reason": "Define a cohort and wait for its fixed enrollment cutoff", "usable": len(usable)}
                continue
            if len(usable) < 60 or any(c not in usable and now <= instant(c.get("etaAt", c["frozenAt"]))+timedelta(days=3) for c in cases):
                targets[target] = {"status": "UNAVAILABLE", "reason": workspace["evaluationReason"], "usable": len(usable)}
                continue
            # Boundaries depend on ALL enrollment, never on which labels succeeded.
            # Equal issue instants stay together; labels precede the next period.
            cut1, cut2 = cases[int(len(cases)*.6)]["frozenAt"], cases[int(len(cases)*.8)]["frozenAt"]
            available = lambda c: c["outcome"]["arrivalAvailableAt" if target == "arrival" else "berthAvailableAt"]
            fit = [c for c in usable if c["frozenAt"] < cut1 and available(c) < cut1]
            cal = [c for c in usable if cut1 <= c["frozenAt"] < cut2 and available(c) < cut2]
            hold = [c for c in usable if c["frozenAt"] >= cut2]
            if len(fit)<24 or len(cal)<10 or len(hold)<10:
                targets[target] = {"status": "UNAVAILABLE", "reason": "Insufficient chronological partitions after purging", "partitionCounts": [len(fit), len(cal), len(hold)]}
                continue
            value = lambda c: c["outcome"]["arrivalErrorHours" if target == "arrival" else "waitingHours"]
            median = statistics.median(value(c) for c in fit)
            estimators = {"publishedEta": 0, "fittingMedianEtaCorrection": median} if target == "arrival" else {"fittingHistoricalMedianWait": median}
            metrics = {}
            for name, prediction in estimators.items():
                residuals = sorted(abs(value(c)-prediction) for c in cal)
                radius = residuals[min(len(residuals)-1, math.ceil((len(residuals)+1)*.8)-1)]
                errors = [value(c)-prediction for c in hold]
                metrics[name] = {"MAE": statistics.mean(abs(e) for e in errors), "signedBias": statistics.mean(errors),
                    "intervalCoverage": statistics.mean(abs(e)<=radius for e in errors), "intervalRadiusHours": radius,
                    "holdoutPredictions": [{"caseId": c["caseId"], "observed": value(c), "prediction": prediction} for c in hold]}
            targets[target] = {"status": "AVAILABLE", "fitIds": [c["caseId"] for c in fit], "calibrationIds": [c["caseId"] for c in cal],
                "holdoutIds": [c["caseId"] for c in hold], "metrics": metrics, "nominalCoverage": .8}
        # Do not expose one target's holdout while the joint protocol is still
        # unsealed: repeatedly recomputing a partial preview would reuse it.
        if not all(t["status"] == "AVAILABLE" for t in targets.values()):
            for target, result in list(targets.items()):
                if result["status"] == "AVAILABLE":
                    targets[target] = {"status": "UNAVAILABLE", "reason": "Both targets must pass collection and purging gates before holdout is exposed"}
        result = {"benchmarkId": digest(json.dumps(cases, sort_keys=True)+str(cohort)+COHORT_PROTOCOL), "at": stamp(now), "actor": actor, "portCode": port,
                  "cohortId": cohort["cohortId"] if cohort else None, "cohort": cohort,
                  "protocol": COHORT_PROTOCOL, "datasetHash": digest(json.dumps(cases, sort_keys=True)), "targets": targets,
                  "codeHash": digest(Path(__file__).read_bytes()),
                  "datasetCases": cases,
                  "excludedCaseIds": [c["caseId"] for c in cases if not c["outcome"] or c["outcome"]["waitingHours"] is None],
                  "statement": "Descriptive/predictive baseline error only; no operational accuracy or savings established"}
        if all(t["status"] == "AVAILABLE" for t in targets.values()):
            with self.lock, self.db:
                self.db.execute("INSERT OR IGNORE INTO benchmarks VALUES(?,?,?,?)", (result["benchmarkId"], port, stamp(now), json.dumps(result)))
        return result
