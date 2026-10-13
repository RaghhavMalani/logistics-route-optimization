"""Read-only host acceptance checks; never requests collection or evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def verify(root: Path):
    sys.path[:0] = [str(root), str(root / ".portwatch/backend-runtime"), str(root / ".venv/Lib/site-packages")]
    from src.portwatch_os.intelligence.public_collection import get_service

    store = get_service()
    folder = store.root.parent / "backend_service"
    baseline = json.loads((folder / "acceptance-baseline.json").read_text(encoding="utf-8"))
    host = json.loads((folder / "host-status.json").read_text(encoding="utf-8"))
    before_path = root / "work/public-backend-task-before-restart.json"
    before = json.loads(before_path.read_text(encoding="utf-8")) if before_path.exists() else None
    now = datetime.now(timezone.utc)  # wall-clock: actual host verification time.
    ports = {}
    for port, original in baseline["ports"].items():
        w = store.workspace(port, now)
        current = {
            "snapshots": {s["snapshotId"]: [s["sha256"], s["firstSeenAt"]] for s in w["snapshots"]},
            "cases": {c["caseId"]: [c["etaAt"], c["frozenAt"]] for c in w["cases"]},
            "cohorts": {c["cohortId"]: [c["enrollmentStartAt"], c["enrollmentEndAt"], c["initialCaseIds"]] for c in w["cohorts"]},
        }
        preserved = {key: all(current[key].get(k) == v for k, v in original[key].items()) for key in current}
        hashes = all(hashlib.sha256((store.root / "evidence" / (s["sha256"] + ".pdf")).read_bytes()).hexdigest() == s["sha256"] for s in w["snapshots"])
        latest = store.collection_status(port, now)
        old_job = ((before or {}).get("jobs", {}).get(port, {}).get("job", {}).get("lastResult") or {})
        startup = bool(old_job.get("ok") and old_job.get("reason") == "scheduled")
        startup_at = (before or {}).get("collections", {}).get(port, {}).get("lastSuccessfulCollectionAt")
        job = host.get("jobs", {}).get(port, {}).get("job", {}).get("lastResult") or {}
        cadence = bool(startup_at and job.get("ok") and job.get("reason") == "scheduled"
            and instant(job["startedAt"]) >= instant(startup_at) + timedelta(hours=3) - timedelta(seconds=1))
        ports[port] = {"counts": w["counts"], "preserved": preserved, "archivedHashesVerified": hashes,
            "automaticStartupCollectionVerified": startup, "startupSuccessfulCollectionAt": startup_at,
            "nextExpectedCollectionAt": (instant(startup_at) + timedelta(hours=3)).isoformat() if startup_at else None,
            "unattendedThreeHourRefreshVerified": cadence, "lastSuccessfulCollectionAt": latest["lastSuccessfulCollectionAt"],
            "lastErrors": (latest["lastRun"] or {}).get("errors", []),
            "restartRetainedSuccessfulReceipt": bool(before and host["runId"] != before["runId"]
                and host.get("collections", {}).get(port, {}).get("lastSuccessfulCollectionAt") == startup_at),
            "candidateAuditDirectories": [str(store.root / "case_audits" / port / c["caseId"])
                for c in w["cases"] if c["outcome"] and c["outcome"]["waitingHours"] is not None]}
    result = {"verifiedAt": now.isoformat(), "stateDir": str(store.root.parent.resolve()),
        "host": {k: host[k] for k in ("runId", "pid", "startedAt", "updatedAt", "serverReady", "schedulerRunning", "worldMode", "vesselFinderEnabled")},
        "hostStatusFresh": (now - instant(host["updatedAt"])) < timedelta(minutes=2),
        "restartChangedProcess": bool(before and host["pid"] != before["pid"] and host["runId"] != before["runId"]),
        "ports": ports, "collectionRequestedByThisCheck": False, "holdoutInspected": False,
        "rebootAndLogoffRecoveryTested": False}
    return result


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(root / "work/public-backend-host-validation.json"))
    args = parser.parse_args()
    result = verify(root)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not all(all(p["preserved"].values()) and p["archivedHashesVerified"] for p in result["ports"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
