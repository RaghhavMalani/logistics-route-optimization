"""Optional VesselFinder JSON evidence. Disabled until explicitly configured.

Vendor AIS ETAs and port-call events enrich vessel identity; they do not
rewrite the public PDF cohort or establish anchorage/all-fast/berth labels.
"""
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from src.portwatch_os.clock import LIVE, get_clock, wall_now
from src.portwatch_os.freshness.job import JobOutcome, RefreshJob
from src.portwatch_os.freshness.policy import ArtifactProbe, FreshnessPolicy, NOT_APPLICABLE
from src.portwatch_os.intelligence.public_ports import MAX_BYTES, PORTS, digest, stamp
from src.portwatch_os.learning.weather_feedback import instant
from src.utils.config import STATE_DIR

BASE = "https://api.vesselfinder.com/"
VERSION = "vesselfinder-json-v1"


def configured():
    return (os.getenv("PORTWATCH_VESSELFINDER_ENABLED") or "0").lower() in ("1", "true", "yes", "on")


def eligibility():
    if not configured():
        return "Optional VesselFinder adapter is disabled"
    if not os.getenv("VESSELFINDER_API_KEY"):
        return "Optional VesselFinder adapter requires a server API key and credits"
    if get_clock().state.mode != LIVE:
        return "Structured vessel collection requires LIVE"
    return None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("VesselFinder redirect refused")


def fetch_json(port, kind):
    if port not in PORTS or kind not in ("portcalls", "expectedarrivals"):
        raise ValueError("Unsupported vessel source")
    if eligibility():
        raise ValueError(eligibility())
    key = os.environ["VESSELFINDER_API_KEY"]
    params = {"locode": port, "interval": 1440, "limit": 50, "format": "json"}
    if kind == "portcalls":
        params["extradata"] = "ais"
        params["anchorage"] = 1
    request = Request(BASE+kind+"?"+urlencode({**params, "userkey": key}), headers={"User-Agent": "PortWatch-vessel-evidence/1"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=25) as response:
            payload = response.read(MAX_BYTES+1)
    except HTTPError as exc:
        raise ValueError(f"VesselFinder HTTP {exc.code}; check server credentials, credits and coverage") from None
    except Exception:
        # urllib exceptions can include the credential-bearing request URL.
        raise ValueError("VesselFinder request failed; check connectivity and provider configuration") from None
    if len(payload) > MAX_BYTES or key.encode() in payload:
        raise ValueError("VesselFinder response exceeds limits or contains credentials")
    return payload, params


def utc(raw):
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return stamp(datetime.strptime(raw.removesuffix(" UTC"), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc))
    except ValueError:
        return None


def identifier(value, length):
    text = str(value)
    return text if text.isdigit() and len(text) == length and int(text) > 0 else None


def parse_json(payload, port, kind):
    rows = json.loads(payload)
    if not isinstance(rows, list) or len(rows) > 50:
        raise ValueError("VesselFinder response is not a bounded vessel array")
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("AIS" if kind == "expectedarrivals" else "PORTCALL"), dict):
            raise ValueError("VesselFinder response layout changed")
        ais, event = row.get("AIS") or {}, row.get("PORTCALL") or {}
        if not isinstance(ais, dict):
            raise ValueError("VesselFinder AIS layout changed")
        timestamp = utc(ais.get("TIMESTAMP") if kind == "expectedarrivals" else event.get("TIMESTAMP"))
        flags = [] if timestamp else ["MISSING_OR_MALFORMED_EVENT_CLOCK"]
        raw_locode = event.get("LOCODE", port)
        if raw_locode != port:
            flags.append("PORT_LOCODE_MISMATCH")
        mmsi = identifier(event.get("MMSI", ais.get("MMSI")), 9)
        imo = identifier(event.get("IMO", ais.get("IMO")), 7)
        if not mmsi:
            flags.append("MISSING_OR_MALFORMED_MMSI")
        eta = utc(ais.get("ETA"))
        if kind == "expectedarrivals" and eta is None:
            flags.append("MISSING_OR_MALFORMED_AIS_ETA")
        event_type = str(event.get("EVENT") or "EXPECTED").upper()
        if kind == "portcalls" and event_type not in ("ARRIVAL", "DEPARTURE"):
            flags.append("UNKNOWN_PORTCALL_EVENT")
        result.append({"recordId": digest(json.dumps(row, sort_keys=True)), "portCode": port,
            "reportedLocode": raw_locode, "kind": kind, "mmsi": mmsi, "imo": imo,
            "vesselName": ais.get("NAME"), "event": event_type, "eventAt": timestamp, "aisEtaAt": eta,
            "rawEventTime": ais.get("TIMESTAMP") if kind == "expectedarrivals" else event.get("TIMESTAMP"),
            "rawAisEta": ais.get("ETA"), "flags": flags, "raw": row,
            "etaTimezoneNote": "AIS ETA interpreted as UTC; the API adds its year, so this is distinct from a frozen published port ETA",
            "berthAt": None, "allFastAt": None})
    return result


class VesselStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root/"evidence").mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root/"vessels.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY,port TEXT,kind TEXT,at TEXT,sha TEXT,body TEXT); CREATE TABLE IF NOT EXISTS checks(id INTEGER PRIMARY KEY,port TEXT,at TEXT,body TEXT);")
        self.db.commit()

    def close(self):
        self.db.close()

    def import_json(self, port, kind, payload, at, params):
        if port not in PORTS or kind not in ("portcalls", "expectedarrivals") or at.tzinfo is None or len(payload) > MAX_BYTES:
            raise ValueError("Invalid structured evidence input")
        rows = parse_json(payload, port, kind)
        sha = digest(payload)
        key = digest(port+kind+sha)
        body = {"snapshotId": key, "portCode": port, "kind": kind, "sha256": sha, "firstSeenAt": stamp(at),
                "sourceUrl": BASE+kind, "request": params, "parserVersion": VERSION, "records": rows}
        # Only credential-free request metadata may be retained.
        if set(params)-{"locode", "interval", "limit", "format", "extradata", "anchorage"}:
            raise ValueError("Credential-bearing or unsupported request metadata refused")
        with self.lock, self.db:
            path = self.root/"evidence"/(sha+".json")
            if path.exists():
                if digest(path.read_bytes()) != sha:
                    raise ValueError("Structured evidence hash mismatch")
            else:
                path.write_bytes(payload)
            self.db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?,?)", (key, port, kind, stamp(at), sha, json.dumps(body)))
        return key

    def refresh(self, port):
        if eligibility():
            raise ValueError(eligibility())
        results, errors = [], []
        for kind in ("portcalls", "expectedarrivals"):
            try:
                payload, params = fetch_json(port, kind)
                if get_clock().state.mode != LIVE:
                    raise ValueError("Clock changed during structured collection")
                # wall-clock: vendor evidence is available only at actual receipt.
                results.append(self.import_json(port, kind, payload, wall_now(), params))
            except Exception:
                errors.append(f"{kind}: collection failed; check provider status, response schema, credentials and credits")
        # wall-clock: retained status records the actual completion of this attempt.
        at = stamp(wall_now())
        with self.lock, self.db:
            self.db.execute("INSERT INTO checks(port,at,body) VALUES(?,?,?)", (port, at, json.dumps({"results": results, "errors": errors})))
        return {"at": at, "results": results, "errors": errors}

    def workspace(self, port, as_of):
        with self.lock:
            snapshots = [json.loads(r[0]) for r in self.db.execute("SELECT body FROM snapshots WHERE port=? AND at<=? ORDER BY at,id", (port, stamp(as_of)))]
            checks = [(r["at"], json.loads(r["body"])) for r in self.db.execute("SELECT at,body FROM checks WHERE port=? AND at<=? ORDER BY id DESC", (port, stamp(as_of)))]
        latest = {}
        for snapshot in snapshots:
            latest[snapshot["kind"]] = snapshot
        records = [r for s in latest.values() for r in s["records"] if not r["eventAt"] or instant(r["eventAt"]) <= as_of]
        return {"enabled": configured(), "configurationReason": eligibility(), "source": "VesselFinder", "coverage": "Unverified; empty results do not establish coverage",
            "lastCheckAt": checks[0][0] if checks else None, "lastErrors": checks[0][1]["errors"] if checks else [],
            "lastSuccessfulCollectionAt": next((at for at, r in checks if not r["errors"]), None),
            "snapshots": snapshots, "records": records, "statement": "Vendor AIS ETAs and arrival/departure events are separate from public PDF cohort outcomes and confirmed all-fast"}

    def evidence(self, port, key, as_of):
        snapshot = next((s for s in self.workspace(port, as_of)["snapshots"] if s["snapshotId"] == key), None)
        if not snapshot:
            raise ValueError("Structured evidence unavailable at this port and clock")
        path = self.root/"evidence"/(snapshot["sha256"]+".json")
        if digest(path.read_bytes()) != snapshot["sha256"]:
            raise ValueError("Structured evidence hash mismatch")
        return path


@lru_cache(maxsize=1)
def get_vessel_store():
    return VesselStore(Path(STATE_DIR)/"public_port_pilot"/"vesselfinder")


def vessel_jobs(store_getter=get_vessel_store):
    jobs = []
    for port in PORTS:
        def probe(port=port):
            if not configured():
                return ArtifactProbe(None, override_state=NOT_APPLICABLE, reason="Optional VesselFinder adapter disabled")
            # wall-clock: scheduler cadence uses real successful provider receipts.
            state = store_getter().workspace(port, wall_now())
            return ArtifactProbe(instant(state["lastSuccessfulCollectionAt"]) if state["lastSuccessfulCollectionAt"] else None)
        def run(context, port=port):
            result = store_getter().refresh(port)
            if result["errors"]:
                raise RuntimeError("; ".join(result["errors"]))
            return JobOutcome(observed_at=instant(result["at"]), detail={"portCode": port, "snapshots": len(result["results"])})
        jobs.append(RefreshJob(FreshnessPolicy("vesselfinder_"+port, "VesselFinder", timedelta(hours=3), timedelta(hours=36),
            max_attempts=2, backoff_base=timedelta(minutes=5), backoff_cap=timedelta(hours=3),
            rationale="Optional paid JSON collection, bounded to 50 records per endpoint and disabled until explicitly enabled with a server key; coverage requires validation"),
            probe=probe, run=run, eligibility=eligibility))
    return jobs
