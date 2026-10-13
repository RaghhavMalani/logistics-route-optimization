"""Read-only reconciliation of one JNPA export against operator-supplied records.

This verifies consistency and retained source files, not a person's authority or
the authenticity of their acknowledgment. The project must verify those first.
It never registers a call, writes the ledger or changes the qualifying count.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

IMMUTABLE = ("operationId", "operationRef", "mmsi", "vesselName", "recipientOrganisation", "plannedArrivalAt",
    "issuedAt", "cohortId", "baselineWaitHours", "baselineSource", "baselineRef", "baselineEstimatedAt",
    "baselineAvailableAt", "routeRevision", "evidence", "features", "prediction", "predictionId", "decisionId",
    "missingEvidence", "recommendation")
AGREEMENT_FIELDS = ("organisation", "terminal", "operatorName", "operatorRole", "operatorContact", "confirmationRef",
    "researchUsePermissionRef", "sourceTimezone", "callIdentityDefinition", "mmsiVerificationSourceRef",
    "anchorageArrivalDefinition", "allFastDefinition", "schedulerWaitDefinition", "availabilityDefinition")


def file_hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(512*1024), b""):
            result.update(chunk)
    return result.hexdigest()


def reconcile(dataset: dict, manifest: dict, root: Path, *, phase="complete", frozen: dict | None = None) -> dict:
    blockers, documents = [], {}
    def check(ok, message):
        if not ok:
            blockers.append(message)
        return bool(ok)
    def moment(value, label):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError()
            return parsed.astimezone(timezone.utc)
        except (ValueError, AttributeError, TypeError):
            blockers.append(f"{label}: timestamp with an explicit timezone required")
            return None
    def number(value, label):
        try:
            if isinstance(value, bool):
                raise ValueError()
            result = float(value)
            if not math.isfinite(result):
                raise ValueError()
            return result
        except (ValueError, TypeError):
            blockers.append(f"{label}: finite numeric value required")
            return None
    def same_time(left, right, label):
        a, b = moment(left, label+" source"), moment(right, label+" export")
        if a and b:
            check(a == b, label+": source and export differ")
    def source_document(role):
        entry = manifest.get("evidenceDocuments", {}).get(role, {})
        try:
            relative = Path(entry.get("path") or "")
            path = (root/relative).resolve()
            if relative.is_absolute() or not path.is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError("retained file must be inside the handoff directory")
            expected = entry.get("sha256", "")
            if not re.fullmatch(r"[0-9a-f]{64}", expected):
                raise ValueError("record the retained file's SHA-256")
            actual = file_hash(path)
            if actual != expected:
                raise ValueError("retained file hash differs")
            if not str(entry.get("sourceRef", "")).strip():
                raise ValueError("source reference is missing")
            documents[role] = {"path": str(relative), "sha256": actual, "sourceRef": entry["sourceRef"]}
            return path
        except (ValueError, OSError, TypeError) as exc:
            blockers.append(f"{role} document: {exc}")
            return None
    def source_row(path, role, operation):
        if path is None:
            return None
        try:
            if path.stat().st_size > 250_000:
                raise ValueError("CSV exceeds 250 KB")
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream, strict=True)
                if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                    raise ValueError("unique named columns required")
                rows = list(reader)
            if any(None in r or any(v is None for v in r.values()) for r in rows):
                raise ValueError("row has the wrong number of cells")
            rows = [r for r in rows if r.get("operationRef") == operation["operationRef"]]
            if len(rows) != 1 or rows[0].get("mmsi") != operation["mmsi"]:
                raise ValueError("exactly one matching call reference/MMSI required")
            return rows[0]
        except (ValueError, csv.Error, OSError, UnicodeError) as exc:
            blockers.append(f"{role} CSV: {exc}")
            return None

    report = {"phase": phase, "portCode": "INNSA", "operationRef": manifest.get("call", {}).get("operationRef"),
        "status": "HANDOFF_REQUIRED", "blockers": blockers, "documents": documents,
        "note": "Consistency checks require an independently verified operator acknowledgment; no model accuracy or savings is established"}
    check(manifest.get("schemaVersion") == "jnpa-first-call-handoff-v1", "Handoff schema version is missing or unsupported")
    check(manifest.get("portCode") == dataset.get("portCode") == "INNSA", "JNPA port identity differs or is missing")
    agreement = manifest.get("sourceAgreement", {})
    for name in AGREEMENT_FIELDS:
        check(bool(str(agreement.get(name) or "").strip()), f"Source agreement: {name} is missing")
    agreed_at = moment(agreement.get("confirmedAt"), "Source agreement confirmedAt")
    identity = manifest.get("call", {})
    check(bool(re.fullmatch(r"[1-9][0-9]{8}", str(identity.get("mmsi") or ""))), "Verified nine-digit MMSI is missing")
    for name in ("operationRef", "vesselName"):
        check(bool(str(identity.get(name) or "").strip()), f"Call {name} is missing")
    selected = [c for c in dataset.get("operations", []) if c.get("operationRef") == identity.get("operationRef")]
    if not check(len(selected) == 1, "Export must contain exactly one operation with the agreed call reference"):
        return report
    case = selected[0]
    report["operationId"] = case["operationId"]
    check(case.get("mmsi") == identity.get("mmsi") and case.get("vesselName") == identity.get("vesselName"), "Exported vessel identity differs from the confirmed handoff")
    cohort = dataset.get("collection", {}).get("cohort") or {}
    check(bool(case.get("cohortId")) and case.get("cohortId") == cohort.get("cohortId"), "Call is not enrolled in the exported prospective cohort")
    issued = moment(case.get("issuedAt"), "Frozen claim issuedAt")
    started = moment(cohort.get("startedAt"), "Cohort startedAt")
    planned = moment(case.get("plannedArrivalAt"), "Planned arrival")
    as_of = moment(dataset.get("asOf"), "Export asOf")
    if issued and started:
        check(started <= issued, "Cohort must begin before the frozen claim")
    if issued and agreed_at:
        check(agreed_at <= issued, "Source agreement was confirmed after the frozen claim")
    if issued and planned:
        check(issued < planned <= issued+timedelta(days=7), "Planned arrival was not future at registration")
    if issued and as_of:
        check(issued <= as_of, "Claim was recorded after the export clock")
    check(not case.get("disposition"), "Call is cancelled or marked as a duplicate")
    created = [e for e in case.get("events", []) if e.get("kind") == "created"]
    if check(len(created) == 1 and bool(created[0].get("actor")), "Named registration audit is missing"):
        same_time(created[0].get("recordedAt"), case.get("issuedAt"), "Registration audit")
        for field in IMMUTABLE:
            if field != "operationId":
                check(created[0].get("body", {}).get(field) == case.get(field), f"Frozen registration audit differs: {field}")

    source_document("agreement")
    source_document("identity")
    scheduler_file = source_document("scheduler")
    for role, reference in (("agreement", agreement.get("confirmationRef")), ("identity", agreement.get("mmsiVerificationSourceRef")),
                            ("scheduler", case.get("baselineRef"))):
        if role in documents:
            check(documents[role]["sourceRef"] == reference, f"{role} document reference differs from the agreed/frozen reference")
    schedule = source_row(scheduler_file, "scheduler", case)
    if schedule:
        for name in ("vesselName", "recipientOrganisation", "baselineSource", "baselineRef"):
            check(schedule.get(name) == case.get(name), f"Scheduler source differs: {name}")
        for name in ("plannedArrivalAt", "baselineEstimatedAt", "baselineAvailableAt"):
            same_time(schedule.get(name), case.get(name), name)
        source_wait = number(schedule.get("baselineWaitHours"), "Source scheduler estimate")
        frozen_wait = number(case.get("baselineWaitHours"), "Frozen scheduler estimate")
        if source_wait is not None and frozen_wait is not None:
            check(0 <= source_wait <= 720 and math.isclose(source_wait, frozen_wait, abs_tol=1e-9), "Individual scheduler estimate differs or is outside accepted bounds")
    estimated = moment(case.get("baselineEstimatedAt"), "Scheduler issue time")
    baseline_available = moment(case.get("baselineAvailableAt"), "Scheduler availability")
    if estimated and baseline_available and issued:
        check(estimated <= baseline_available <= issued, "Scheduler estimate was not known before the claim")

    features, evidence = case.get("features", {}), case.get("evidence", {})
    tracks = evidence.get("tracks", [])
    check(len(tracks) >= 2 and len({t.get("id") for t in tracks}) == len(tracks), "At least two distinct archived AIS reports are required")
    check(features.get("trackCount") == len(tracks), "Frozen AIS report count differs from archived evidence")
    observed_times = []
    for track in tracks:
        check(track.get("mmsi") == case.get("mmsi") and bool(track.get("source")) and bool(track.get("rawRef")), "AIS identity/source reference is missing or differs")
        observed, available, recorded = [moment(track.get(k), "AIS "+k) for k in ("observedAt", "availableAt", "recordedAt")]
        if observed and available and recorded and issued:
            check(issued-timedelta(days=1) <= observed <= available <= recorded <= issued, "AIS observation/availability/recording was outside the frozen window")
            observed_times.append(observed)
    if observed_times and issued:
        age = (issued-max(observed_times)).total_seconds()/3600
        stored_age = number(features.get("trackAgeHours"), "Frozen AIS age")
        check(0 <= age <= 1, "Latest AIS was stale at issue")
        if stored_age is not None:
            check(math.isclose(age, stored_age, abs_tol=1e-6), "Frozen AIS age differs from source times")
    winds = [w for w in evidence.get("weather", []) if w.get("variable") == "wind_speed"]
    if check(len(winds) == 1, "One issue-time maximum-wind forecast is required"):
        wind = winds[0]
        check(wind.get("unit") == "kn" and bool(wind.get("id")) and bool(wind.get("source")), "Wind forecast units/identity/source are missing")
        for name in ("issuedAt", "recordedAt", "availableAt"):
            known = moment(wind.get(name), "Wind "+name)
            if known and issued:
                check(known <= issued, "Wind forecast became known after freezing")
        end = moment(wind.get("validAt"), "Wind validity")
        if end and planned:
            check(end-timedelta(days=1) <= planned < end, "Daily wind forecast does not cover planned arrival")
        original = number(wind.get("original"), "Original wind forecast")
        consumed = number(wind.get("consumed"), "Consumed wind forecast")
        feature = number(features.get("wind_speed"), "Frozen wind feature")
        if consumed is not None and feature is not None:
            check(math.isclose(consumed, feature, abs_tol=1e-9), "Consumed wind forecast differs from the model input")

    if phase == "frozen":
        check(case.get("outcome") is None, "Frozen-phase export already contains an outcome")
        if planned and as_of:
            check(as_of < planned, "Frozen-phase export was not captured before planned arrival")
        report["status"] = "FROZEN_INPUTS_RECONCILED" if not blockers else "RECONCILIATION_BLOCKED"
        return report

    if check(frozen is not None, "A separate pre-arrival frozen export is required"):
        before = [c for c in frozen.get("operations", []) if c.get("operationId") == case["operationId"]]
        if check(len(before) == 1 and before[0].get("outcome") is None, "Pre-arrival export does not contain this unresolved call"):
            for name in IMMUTABLE:
                check(before[0].get(name) == case.get(name), f"Frozen original changed: {name}")
            frozen_as_of = moment(frozen.get("asOf"), "Pre-arrival export asOf")
            arrival = moment((case.get("outcome") or {}).get("arrivedAt"), "Confirmed arrival")
            if frozen_as_of and arrival and issued:
                check(issued <= frozen_as_of < arrival, "First export was not captured before actual arrival")
    outcome = case.get("outcome") or {}
    source_outcome = source_row(source_document("outcome"), "outcome", case)
    if "outcome" in documents:
        check(documents["outcome"]["sourceRef"] == outcome.get("sourceRef"), "Outcome document reference differs from the ledger")
    if source_outcome:
        for name in ("source", "sourceRef", "kind", "berthRef"):
            check(source_outcome.get(name) == outcome.get(name), f"Confirmed outcome source differs: {name}")
        for name in ("arrivedAt", "berthedAt", "arrivalAvailableAt", "allFastAvailableAt", "availableAt"):
            same_time(source_outcome.get(name), outcome.get(name), name)
    arrival, all_fast, arrival_available, all_fast_available, available, recorded = [moment(outcome.get(k), "Outcome "+k)
        for k in ("arrivedAt", "berthedAt", "arrivalAvailableAt", "allFastAvailableAt", "availableAt", "recordedAt")]
    if all((issued, arrival, all_fast, arrival_available, all_fast_available, available, recorded, as_of)):
        check(issued < arrival <= all_fast <= all_fast_available <= available <= recorded <= as_of, "Confirmed outcome timeline is not prospective/available at the export clock")
        check(arrival <= arrival_available <= available, "Anchorage-record availability is inconsistent")
        measured = (all_fast-arrival).total_seconds()/3600
        wait = number(outcome.get("waitHours"), "Exported waiting hours")
        if wait is not None:
            check(math.isclose(wait, measured, abs_tol=1e-9), "Waiting hours differ from confirmed timestamps")
        report["observedWaitHours"] = measured
    outcomes = [e for e in case.get("events", []) if e.get("kind") == "outcome"]
    if check(len(outcomes) == 1 and bool(outcomes[0].get("actor")), "Named outcome-recording audit is missing"):
        check(outcomes[0].get("body") == outcome, "Outcome audit differs from the exported measurement")
        same_time(outcomes[0].get("recordedAt"), outcome.get("recordedAt"), "Outcome recording audit")
    q = [c for c in dataset.get("collection", {}).get("calls", []) if c.get("operationId") == case["operationId"]]
    check(len(q) == 1 and q[0].get("qualifying") is True and not q[0].get("flags"), "Exported call is not qualifying or has unresolved quality flags")
    confirmation = manifest.get("reconciliation", {})
    check(bool(confirmation.get("confirmedBy")) and bool(confirmation.get("confirmationRef")), "Operator export reconciliation acknowledgment is missing")
    confirmed = moment(confirmation.get("confirmedAt"), "Reconciliation confirmedAt")
    if confirmed and as_of:
        check(as_of <= confirmed, "Operator reconciliation predates the final export")
    report["status"] = "QUALIFICATION_RECONCILED" if not blockers else "RECONCILIATION_BLOCKED"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="Export cohort JSON from the verified workspace")
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--frozen-export", type=Path)
    parser.add_argument("--phase", choices=("frozen", "complete"), default="complete")
    parser.add_argument("--output", type=Path, help="Save the reconciliation report; inputs must remain unchanged")
    args = parser.parse_args()
    protected = [args.export.resolve(), args.handoff.resolve()]
    if args.frozen_export:
        protected.append(args.frozen_export.resolve())
    try:
        if args.output and args.output.resolve() in protected:
            raise ValueError("Report output cannot overwrite an input")
        data = json.loads(args.export.read_text(encoding="utf-8-sig"))
        manifest = json.loads(args.handoff.read_text(encoding="utf-8-sig"))
        frozen = json.loads(args.frozen_export.read_text(encoding="utf-8-sig")) if args.frozen_export else None
        if not isinstance(data, dict) or not isinstance(manifest, dict) or (frozen is not None and not isinstance(frozen, dict)):
            raise ValueError("Export and handoff must be JSON objects")
        report = reconcile(data, manifest, args.handoff.parent, phase=args.phase, frozen=frozen)
        report["inputHashes"] = {"export": file_hash(args.export), "handoff": file_hash(args.handoff),
                                 "frozenExport": file_hash(args.frozen_export) if args.frozen_export else None}
        output = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
        if args.output:
            with args.output.open("x", encoding="utf-8") as target:
                target.write(output+"\n")
        print(output)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        parser.exit(2, f"Invalid handoff/export: {exc}\n")
    raise SystemExit(0 if not report["blockers"] else 1)


if __name__ == "__main__":
    main()
