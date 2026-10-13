"""Read-only publication of visually reviewed official public port-call evidence."""
import json
import os
import re
import sqlite3
from datetime import timedelta
from pathlib import Path

from src.portwatch_os.clock import world_now
from src.portwatch_os.intelligence.public_collection import get_service
from src.portwatch_os.intelligence.public_ports import approved, digest
from src.portwatch_os.learning.weather_feedback import instant

EVENTS = ("frozenEta", "reportedArrival", "reportedBerth")


def publication(now):
    """A public-only immutable bundle keeps paper evidence available on new hosts."""
    root = Path(os.getenv("PORTWATCH_PUBLIC_CASE_DIR") or Path(__file__).resolve().parents[3] / "data/public_port_cases")
    if not (root / "current.json").is_file():
        return None, {"cases": [], "documents": []}
    pointer = json.loads((root / "current.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"case-publication-[a-f0-9]{16}", pointer["publicationId"]):
        raise ValueError("Public case publication failed integrity verification")
    folder = root / pointer["publicationId"]
    body = (folder / "publication.json").read_bytes()
    if digest(body) != pointer["sha256"]:
        raise ValueError("Public case publication failed integrity verification")
    data = json.loads(body)
    cases = []
    if instant(data["publishedAt"]) <= now:
        for case in data["cases"]:
            if case["review"]["status"] != "PASSED" or instant(case["review"]["reviewedAt"]) > now:
                continue
            if any(instant(e["availableAt"]) > now or not packaged_document(folder, data, e["sha256"], now) for e in case["events"]):
                continue
            cases.append({**case, "archivedPublication": True, "publishedAt": data["publishedAt"]})
    return folder, {**data, "cases": cases}


def packaged_document(folder, data, sha, now):
    if not folder or not re.fullmatch(r"[a-f0-9]{64}", sha):
        return None
    doc = next((d for d in data["documents"] if d["sha256"] == sha and approved(d["sourceUrl"]) and instant(d["firstSeenAt"]) <= now), None)
    path = folder / "evidence" / (sha + ".pdf")
    if not doc or not path.is_file() or path.is_symlink():
        return None
    return path if digest(path.read_bytes()) == sha else None


def document(store, snapshots, sha):
    """A hash alone never authorizes publication of an arbitrary local file."""
    if not re.fullmatch(r"[a-f0-9]{64}", sha):
        return None
    snapshot = next((s for s in snapshots if s["sha256"] == sha and approved(s["sourceUrl"])), None)
    path = store.root / "evidence" / (sha + ".pdf")
    if not snapshot or not path.is_file() or path.is_symlink():
        return None
    return path if digest(path.read_bytes()) == sha else None


def evidence_url(sha, page):
    return f"/api/public/port-calls/evidence/{sha}.pdf#page={page}"


def reviewed_case(store, workspace, case, now):
    outcome = case.get("outcome")
    if case["status"] != "MATCHED" or not outcome or outcome["waitingHours"] is None:
        return None
    if not re.fullmatch(r"[a-f0-9]{64}", case["caseId"]):
        return None
    folder = store.root / "case_audits" / workspace["portCode"] / case["caseId"]
    if folder.is_symlink():
        return None
    snapshots = {s["snapshotId"]: s for s in workspace["snapshots"]}
    for path in sorted(folder.glob("*.json"), reverse=True):
        if path.is_symlink():
            continue
        try:
            audit = json.loads(path.read_text(encoding="utf-8"))
            review = audit["visualReview"]
            if audit["caseId"] != case["caseId"] or audit["portCode"] != workspace["portCode"]:
                continue
            if review["status"] != "PASSED" or instant(review["reviewedAt"]) > now or instant(audit["preparedAt"]) > now:
                continue
            checks = {c["event"]: c for c in review["pageChecks"]}
            values = {"frozenEta": case["etaAt"], "reportedArrival": outcome["arrivalAt"], "reportedBerth": outcome["berthAt"]}
            audit_values = dict(zip(EVENTS, (audit["frozenEtaAt"], audit["reportedArrivalAt"], audit["reportedBerthAt"])))
            if any(instant(values[k]) != instant(audit_values[k]) for k in EVENTS) or audit["berthRef"] != outcome["berthRef"]:
                continue
            events = []
            for event in EVENTS:
                e = next(e for e in audit["evidence"] if e["event"] == event)
                s, check = snapshots[e["snapshotId"]], checks[event]
                expected_snapshot = case["snapshotId"] if event == "frozenEta" else outcome["arrivalSnapshotId" if event == "reportedArrival" else "berthSnapshotId"]
                expected_available = case["frozenAt"] if event == "frozenEta" else outcome["arrivalAvailableAt" if event == "reportedArrival" else "berthAvailableAt"]
                if (e["snapshotId"] != expected_snapshot or e["sha256"] != s["sha256"]
                    or instant(e["firstSeenAt"]) != instant(s["firstSeenAt"])
                    or instant(e["availableAt"]) != instant(expected_available)
                    or instant(e["availableAt"]) > now or check["status"] != "PASSED"
                    or not check["sourceHashVerified"] or not check["checks"] or not all(check["checks"].values())
                    or check["sourceSha256"] != e["sha256"] or check["originalPage"] != e["page"]
                    or instant(check["reviewedAt"]) > now or not document(store, [s], e["sha256"])):
                    raise ValueError("Evidence or review no longer agrees")
                field = {"frozenEta": "etaAt", "reportedArrival": "arrivalAt", "reportedBerth": "berthAt"}[event]
                observed = check["observedFields"]
                if (observed["rawPublisherClock"] != e["rawTimestamps"][field] or observed["vesselName"] != e["reportedVesselName"]
                    or observed["loaMetres"] != case["loa"] or observed["beamMetres"] != case["beam"]
                    or observed["berthRef"] != e["berthRef"] or not observed["printedDateHeadings"]):
                    raise ValueError("Visual fields no longer agree")
                events.append({"event": event, "at": values[event], "rawClock": e["rawTimestamps"][field],
                    "availableAt": e["availableAt"], "firstSeenAt": s["firstSeenAt"], "reportDate": s["reportDate"],
                    "page": e["page"], "sha256": e["sha256"], "url": evidence_url(e["sha256"], e["page"]),
                    "sourceUrl": s["sourceUrl"], "parserVersion": s["parserVersion"], "parsedAt": s["parsedAt"]})
            return {"caseId": case["caseId"], "portCode": workspace["portCode"], "vesselName": case["vesselName"],
                "identity": {"loaMetres": case["loa"], "beamMetres": case["beam"], "mmsi": None,
                    "basis": "Public vessel name and dimensions; no verified MMSI."},
                "berthRef": outcome["berthRef"], "publishedEtaBaselineErrorMinutes": outcome["arrivalErrorHours"] * 60,
                "reportedWaitingHours": outcome["waitingHours"], "events": events,
                "review": {"status": "PASSED", "reviewedAt": review["reviewedAt"], "preparedAt": audit["preparedAt"]},
                "timezoneNote": workspace["timezoneNote"],
                "uncertainty": "The publisher supplies no ETA confidence interval. Timestamp meanings and timezone remain unconfirmed; reported berth is not confirmed all-fast.",
                "meaning": "Published ETA baseline error = reported arrival minus the prospectively frozen published ETA. This ETA was not produced by the ML model.",
                "auditUrl": f"/api/public/port-calls/{case['caseId']}/audit"}
        except (OSError, ValueError, KeyError, TypeError, StopIteration):
            continue
    return None


def public_calls():
    now = world_now()
    _, bundle = publication(now)
    try:
        store = get_service()
    except (OSError, sqlite3.DatabaseError):
        return {"available": bool(bundle["cases"]), "asOf": now.isoformat(), "ports": [], "cases": bundle["cases"],
            "meaning": "Published public case studies remain available; current collection status is unavailable."}
    ports, cases = [], []
    current_case_ids = set()
    for port in ("INPRT", "INMAA"):
        with store.lock:
            w = store.workspace(port, now)
            status = store.collection_status(port, now)
            rows = store.db.execute("SELECT at,body FROM collections WHERE port=? AND at<=? ORDER BY at DESC", (port, now.isoformat(timespec="microseconds").replace("+00:00", "Z"))).fetchall()
            successes = [(r["at"], json.loads(r["body"])) for r in rows if not json.loads(r["body"])["errors"]]
        latest = status["lastRun"]
        previous = (successes[1] if len(successes) > 1 else None) if latest and not latest["errors"] else (successes[0] if successes else None)
        due = instant(previous[0]) + timedelta(hours=3) if previous else None
        delay = max(0, (instant(latest["startedAt"]) - due).total_seconds()/60) if due and latest else None
        errors = []
        for s in w["snapshots"]:
            for issue in s["issues"]:
                errors.append({"code": issue["code"], "page": issue.get("page"), "candidates": issue.get("candidates", []),
                    "reportDate": s["reportDate"], "url": evidence_url(s["sha256"], issue.get("page", 1))})
        success_at = status["lastSuccessfulCollectionAt"]
        ports.append({"portCode": port, **{k: w["counts"][k] for k in ("frozen", "matched", "waitingOutcomes", "pending", "ambiguous", "excludedRecords")},
            "lastSuccessfulCollectionAt": success_at, "lastRunStartedAt": latest["startedAt"] if latest else None,
            "collectionDelayMinutes": delay, "expectedCollectionAt": due.isoformat() if due else None,
            "freshness": "UNAVAILABLE" if not success_at else "OVERDUE" if now >= instant(success_at) + timedelta(hours=3) else "CURRENT",
            "collectionFailed": bool(latest and latest["errors"]), "parserIssues": errors})
        for case in w["cases"]:
            current_case_ids.add(case["caseId"])
            published = reviewed_case(store, w, case, now)
            if published:
                cases.append(published)
    cases += [c for c in bundle["cases"] if c["caseId"] not in current_case_ids]
    return {"available": True, "asOf": now.isoformat(), "ports": ports, "cases": cases,
        "meaning": "Prospective public reports with hash-checked originals and visual review. Individual cases do not establish ML accuracy or operational savings."}
