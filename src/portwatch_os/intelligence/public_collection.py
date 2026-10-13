"""Shared backend/CLI public collector, evidence verification and case audits."""
import json
from pathlib import Path
from functools import lru_cache

from src.portwatch_os.clock import LIVE, get_clock, wall_now
from src.portwatch_os.intelligence.public_ports import PORTS, PublicPilot, compatible, digest, parse_pdf, stamp
from src.utils.config import STATE_DIR


def verify_chain(store, workspace, case):
    """Re-extract event fields from hash-checked originals, not exported outcomes."""
    outcome = case["outcome"]
    if case["status"] != "MATCHED" or not outcome or outcome["waitingHours"] is None:
        raise ValueError("Complete reported arrival and berth are required")
    snapshots = {s["snapshotId"]: s for s in workspace["snapshots"]}
    evidence = []
    from src.portwatch_os.learning.weather_feedback import instant
    for label, snapshot_id, field, value, available in [
        ("frozenEta", case["snapshotId"], "etaAt", case["etaAt"], case["frozenAt"]),
        ("reportedArrival", outcome["arrivalSnapshotId"], "arrivalAt", outcome["arrivalAt"], outcome["arrivalAvailableAt"]),
        ("reportedBerth", outcome["berthSnapshotId"], "berthAt", outcome["berthAt"], outcome["berthAvailableAt"]),
    ]:
        snapshot = snapshots[snapshot_id]
        path = store.evidence(workspace["portCode"], snapshot_id, instant(workspace["asOf"]))
        parsed = parse_pdf(path.read_bytes(), workspace["portCode"], snapshot["kind"])
        rows = [r for r in parsed["records"] if compatible(case, r) and r.get(field) == value
                and (label != "reportedBerth" or r["berthRef"] == outcome["berthRef"])]
        if not rows:
            raise ValueError(f"Original {label} fields do not support the matched chain")
        evidence.append({"event": label, "snapshotId": snapshot_id, "sha256": snapshot["sha256"],
            "sourceUrl": snapshot["sourceUrl"], "firstSeenAt": snapshot["firstSeenAt"], "path": str(path.resolve()),
            "availableAt": available, "value": value, "page": rows[0]["page"], "rawTimestamps": rows[0]["rawTimestamps"], "berthRef": rows[0]["berthRef"],
            "reportedVesselName": rows[0]["vesselName"], "loaMetres": rows[0]["loa"], "beamMetres": rows[0]["beam"]})
    return {"caseId": case["caseId"], "portCode": workspace["portCode"], "vesselName": case["vesselName"], "status": "ORIGINAL_FIELDS_VERIFIED",
        "identity": {"normalizedName": case["nameKey"], "loaMetres": case["loa"], "beamMetres": case["beam"], "mmsi": None,
            "basis": "Physical port, normalized vessel name, LOA within 0.5 m and beam within 0.5 m when supplied"},
        "frozenEtaAt": case["etaAt"], "frozenAt": case["frozenAt"], "freezeActor": case["freezeActor"],
        "reportedArrivalAt": outcome["arrivalAt"], "reportedBerthAt": outcome["berthAt"], "berthRef": outcome["berthRef"],
        "arrivalErrorHours": outcome["arrivalErrorHours"], "waitingHours": outcome["waitingHours"],
        "cohort": next(({k: c[k] for k in ("cohortId", "enrollmentEndAt", "protocol")} for c in workspace["cohorts"] if case["caseId"] in c["caseIds"]), None),
        "timezoneNote": workspace["timezoneNote"], "evidence": evidence,
        "statement": "Public report chain only; event definitions and all-fast remain unconfirmed"}


def collection_quality(workspace):
    """Separate pending/expired unmatched calls from matched-but-incomplete calls."""
    groups = {key: [] for key in ("unmatched", "ambiguous", "incomplete", "complete")}
    for case in workspace["cases"]:
        if case["status"] == "AMBIGUOUS":
            group = "ambiguous"
        elif not case["outcome"]:
            group = "unmatched"
        elif case["outcome"]["waitingHours"] is None:
            group = "incomplete"
        else:
            group = "complete"
        groups[group].append({"caseId": case["caseId"], "vesselName": case["vesselName"],
            "status": case["status"], "etaAt": case["etaAt"], "exclusions": case["exclusions"]})
    return {key: {"count": len(rows), "cases": rows} for key, rows in groups.items()}


def prepare_audit(root, chain, as_of):
    """Write one candidate per evidence version; never overwrite visual review."""
    audit_id = digest(json.dumps(chain, sort_keys=True))
    folder = Path(root)/"case_audits"/chain["portCode"]/chain["caseId"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/(audit_id+".json")
    if not path.exists():
        audit = {**chain, "auditId": audit_id, "preparedAt": as_of,
            "visualReview": {"status": "PENDING", "reviewedAt": None, "reviewer": None, "pageChecks": []}}
        with path.open("x", encoding="utf-8") as stream:
            json.dump(audit, stream, indent=2)
        def cell(value):
            return str(value).replace("\n", " ").replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
        lines = [f"# Public port-call audit — {cell(chain['vesselName'])}", "",
            "**Visual review: PENDING.** Extracted fields have been rechecked against hash-checked originals; PDF pages still require visual comparison.", "",
            f"Port: {chain['portCode']} · Case: {chain['caseId']} · Prepared: {as_of}", "",
            f"Identity: {cell(chain['identity']['normalizedName'])} · LOA {chain['identity']['loaMetres']} m · beam {chain['identity']['beamMetres'] if chain['identity']['beamMetres'] is not None else 'unavailable'}. MMSI is unavailable; this is a public name/dimensions match.", "",
            f"Frozen ETA: {chain['frozenEtaAt']} · Frozen at: {chain['frozenAt']} · Collector: {cell(chain['freezeActor'])}",
            f"Reported arrival: {chain['reportedArrivalAt']} · Reported berth: {chain['reportedBerthAt']} · Berth: {cell(chain['berthRef'])}",
            f"Arrival error (arrival − frozen ETA): {chain['arrivalErrorHours']:.6f} h · Reported arrival-to-berth wait: {chain['waitingHours']:.6f} h", "",
            f"Cohort: {cell(chain['cohort']) if chain['cohort'] else 'Unassigned'}", "",
            chain["timezoneNote"], "All normalized instants are UTC. Raw publisher clocks remain below. Public berth is distinct from confirmed all-fast.", "",
            "| Event | Reported instant (UTC) | Original collected at | Field available at | Raw publisher clocks | Evidence |",
            "|---|---|---|---|---|---|"]
        for e in chain["evidence"]:
            link = Path(e["path"]).as_posix()
            raw = "; ".join(f"{k}: {v}" for k, v in e["rawTimestamps"].items())
            lines.append(f"| {e['event']} | {e['value']} | {e['firstSeenAt']} | {e['availableAt']} | {cell(raw)} | [Archived PDF, page {e['page']}](<{link}>) |")
        lines += [""]+[f"{e['event']}: SHA-256 `{e['sha256']}` · Reported vessel {cell(e['reportedVesselName'])} · LOA {e['loaMetres']} m · beam {e['beamMetres']} m · [Publisher URL (may change)]({e['sourceUrl']})" for e in chain["evidence"]]
        lines += ["", "For visual review, render each cited original page, compare vessel name/dimensions, date heading, raw clocks and berth reference, and record pass/fail, reviewer, actual review time and rendered page links in the JSON's `visualReview.pageChecks`. Do not mark PASSED until all three events have been inspected.", "",
            chain["statement"], "One case does not establish baseline accuracy. Closing enrollment does not guarantee evaluation readiness; later outcomes, minimum counts and chronological partition checks are still required per port and target.", ""]
        path.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    saved = json.loads(path.read_text(encoding="utf-8"))
    return {"auditId": audit_id, "json": str(path.resolve()), "markdown": str(path.with_suffix(".md").resolve()),
            "visualReviewStatus": saved["visualReview"]["status"]}



@lru_cache(maxsize=1)
def get_service():
    return PublicPilot(Path(STATE_DIR)/"public_port_pilot")


def collect_port(store, port, actor):
    """One port per job, using the same ledger and workflow as the operator CLI."""
    if port not in PORTS or get_clock().state.mode != LIVE:
        raise ValueError("Public port collection requires a supported port and LIVE")
    # wall-clock: capture the actual pre-collection state, never a replay anchor.
    now = wall_now()
    with store.lock:
        before = store.workspace(port, now)
        if not any(c["status"] == "ENROLLING" for c in before["cohorts"]):
            store.start_cohort(port, now, actor)
    refreshed = store.refresh(port, actor)
    # wall-clock: reconciliation may use only evidence available after receipt.
    workspace = store.workspace(port, wall_now())
    verified, verification_errors = [], []
    for case in workspace["cases"]:
        if case["outcome"] and case["outcome"]["waitingHours"] is not None:
            try:
                chain = verify_chain(store, workspace, case)
                chain["audit"] = prepare_audit(store.root, chain, workspace["asOf"])
                verified.append(chain)
            except Exception as exc:
                verification_errors.append({"caseId": case["caseId"], "error": str(exc)})
    originals = {s["snapshotId"]: s for s in workspace["snapshots"]}
    frozen = {c["caseId"]: c for c in workspace["cases"]}
    preserved = all(originals[s["snapshotId"]]["firstSeenAt"] == s["firstSeenAt"] and originals[s["snapshotId"]]["sha256"] == s["sha256"] for s in before["snapshots"])
    preserved = preserved and all(frozen[c["caseId"]]["etaAt"] == c["etaAt"] and frozen[c["caseId"]]["frozenAt"] == c["frozenAt"] for c in before["cases"])
    fatal = [dict(snapshotId=s["snapshotId"], **issue) for s in workspace["snapshots"]
             if s["snapshotId"] in {r["snapshotId"] for r in refreshed["results"]}
             for issue in s["issues"] if issue["code"] == "PARSER_UNAVAILABLE"]
    errors = list(refreshed["errors"])+[f"{e['caseId']}: {e['error']}" for e in verification_errors]
    errors += [f"Report parser unavailable: {e['raw']}" for e in fatal]
    if not preserved:
        errors.append("Previously archived originals or frozen cases changed")
    export = store.root/f"export-{port}-{workspace['asOf'][:10]}.json"
    export.write_text(json.dumps(workspace, indent=2), encoding="utf-8")
    # wall-clock: the durable job outcome is recorded when processing finishes.
    finished = stamp(wall_now())
    result = {"portCode": port, "startedAt": stamp(now), "finishedAt": finished, "actor": actor,
        "refresh": refreshed, "errors": errors, "counts": workspace["counts"], "freshness": workspace["freshness"],
        "collectionQuality": collection_quality(workspace), "cohorts": workspace["cohorts"],
        "originalsAndFrozenCasesPreserved": preserved, "verifiedChains": verified,
        "verificationErrors": verification_errors, "export": str(export.resolve()), "parserIssues": workspace["issues"]}
    key = digest(port+finished)
    with store.lock, store.db:
        store.db.execute("INSERT INTO collections VALUES(?,?,?,?)", (key, port, finished, json.dumps(result)))
    folder = store.root/"collection_runs"
    folder.mkdir(exist_ok=True)
    receipt = folder/(finished.replace(":", "-")+"-"+port+".json")
    receipt.write_text(json.dumps({"ports": {port: result}}, indent=2), encoding="utf-8")
    return {**result, "receipt": str(receipt.resolve())}
