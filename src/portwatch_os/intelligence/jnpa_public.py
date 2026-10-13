"""Stage public JNPA berth facts without manufacturing all-fast or scheduler labels."""
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

URL = "https://www.jnport.gov.in/page/berthing-report/M2VlS0pwUXZ3akhSV0E0RDFUVlhxQT09"


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None
        self.spans = {}
        self.column = 0
        self.rowspan = 1

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row, self.column = [], 0
        if tag in ("td", "th") and self.row is not None:
            while self.column in self.spans:
                value, remaining = self.spans[self.column]
                self.row.append(value)
                if remaining <= 1:
                    del self.spans[self.column]
                else:
                    self.spans[self.column] = (value, remaining-1)
                self.column += 1
            self.cell = []
            self.rowspan = int(dict(attrs).get("rowspan", "1"))

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            value = " ".join("".join(self.cell).split())
            self.row.append(value)
            if self.rowspan > 1:
                self.spans[self.column] = (value, self.rowspan-1)
            self.column += 1
            self.cell = None
        if tag == "tr" and self.row is not None:
            while self.column in self.spans:
                value, remaining = self.spans[self.column]
                self.row.append(value)
                if remaining <= 1:
                    del self.spans[self.column]
                else:
                    self.spans[self.column] = (value, remaining-1)
                self.column += 1
            self.rows.append(self.row)
            self.row = None


def parse_report(html: str, retrieved_at: str) -> dict:
    parser = Tables()
    parser.feed(html)
    match = re.search(r"Daily\s+Berthing\s+Report\s+as\s+on\s+(\d{2}-\d{2}-\d{4})", html, re.I)
    if not match:
        raise ValueError("JNPA report date missing; source layout needs review")
    headers = next((r for r in parser.rows if "VIA No" in r and "Berthed on" in r), None)
    required = {"Terminal", "Berth No.", "VIA No", "Vessel Name", "Berthed on", "Expected Completion"}
    if not headers or not required.issubset(headers):
        raise ValueError("JNPA berth columns changed; refuse a guessed mapping")
    records = []
    for row in parser.rows:
        if row == headers or len(row) != len(headers):
            continue
        cells = dict(zip(headers, row))
        if not cells.get("VIA No") or not cells.get("Vessel Name"):
            continue
        records.append({"portCode": "INNSA", "operationRef": cells["VIA No"],
            "vesselName": cells["Vessel Name"], "terminal": cells["Terminal"], "berthRef": cells["Berth No."],
            "reportedBerthedOn": cells["Berthed on"], "reportedExpectedCompletion": cells["Expected Completion"],
            "firstSeenAt": retrieved_at, "source": URL, "reportDate": match.group(1),
            "status": "NEEDS_VERIFICATION", "qualifying": False,
            "missing": ["MMSI and verified call match", "Confirmed anchorage arrival", "All-fast definition and timestamp",
                        "Timestamp timezone", "Individual pre-arrival scheduler estimate and reference", "Original publication availability"]})
    if not records:
        raise ValueError("No named berth records found; source layout needs review")
    snapshot_id = hashlib.sha256(json.dumps([{k: v for k, v in r.items() if k != "firstSeenAt"} for r in records], sort_keys=True).encode()).hexdigest()
    return {"source": URL, "retrievedAt": retrieved_at, "reportDate": match.group(1), "snapshotId": snapshot_id,
            "sourceContentHash": hashlib.sha256(html.encode()).hexdigest(), "records": records,
            "note": "Reported berth times retain source text. First seen now is an availability bound, not historical publication time. No prospective labels or baselines are created."}


def save_report(report: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (report["snapshotId"] + ".json")
    # First observation of unchanged content is immutable across repeat imports.
    try:
        with path.open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2, ensure_ascii=False)
    except FileExistsError:
        pass
    return path


def latest_report(*, before=None):
    from src.portwatch_os.learning.weather_feedback import instant
    directory = Path(__file__).resolve().parents[3] / "data/jnpa/public_reports"
    reports = []
    for path in directory.glob("*.json"):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("snapshotId") and report.get("source") == URL and all(r["operationRef"] != "VIA No" for r in report["records"]):
                if before is None or instant(report["retrievedAt"]) <= instant(before):
                    reports.append(report)
        except (ValueError, OSError):
            continue
    return max(reports, key=lambda r: r["retrievedAt"]) if reports else None
