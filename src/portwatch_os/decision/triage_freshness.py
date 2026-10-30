"""Read-only freshness for retained fleet decisions, separate from continuation.

No provider clients, world builders, episode constructors or writable ledger
stores are imported here. The caller supplies one owned world and one as-of
instant. File/SQLite readers below only inspect server-selected public roots.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

POLICY = "fleet-triage-consumed-freshness-v1"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _instant(value):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("Aware timestamp required")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Aware timestamp required")
    return result.astimezone(timezone.utc)


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _rows(value):
    return value if isinstance(value, list) else []


def _basis(problem):
    evidence = _mapping(problem.get("evidence"))
    return _mapping(evidence.get("currentEnvironment") or evidence.get("intelligenceBasis"))


def restriction_key(basis):
    restriction = _mapping(basis.get("restriction"))
    fact = _mapping(basis.get("reportedFact"))
    family = restriction.get("sourceFamily") or fact.get("sourceFamily") or "PEEL_PORTS"
    if family == "NAVCEN_MSI":
        notice = fact.get("noticeId") or fact.get("providerNoticeId")
        return "NAVCEN_MSI:" + str(notice).split(":")[-1] if notice is not None else None
    return "PEEL_PORTS:" + str(fact.get("noticeRef") or "MNTM 2026-18")


def _response_digests(basis):
    values = []
    if basis.get("kind") == "NOTICE_RESTRICTION":
        fact = _mapping(basis.get("reportedFact"))
        keys = ("responseSha256",) if _mapping(basis.get("restriction")).get("sourceFamily") == "NAVCEN_MSI" else ("responseSha256", "pdfSha256")
        values.extend(fact.get(key) for key in keys)
    elif basis.get("source") or basis.get("snapshotId"):
        values.append(basis.get("responseSha256"))
    elif basis.get("reportedFact") and not _rows(_mapping(basis.get("feedbackConsumption")).get("inputs")):
        values.append(_mapping(basis.get("reportedFact")).get("responseSha256"))
    for entry in _rows(_mapping(basis.get("feedbackConsumption")).get("inputs")):
        if not isinstance(entry, dict):
            values.append(None)
            continue
        claim = _mapping(entry.get("claim"))
        originals = [claim, *[row for row in _rows(claim.get("inputs")) if isinstance(row, dict)]]
        found = [row.get("responseSha256") for row in originals if row.get("responseSha256")]
        values.extend(found or [None])
    return values


def _current_eta(world, vessel):
    if vessel.get("currentEta"):
        return _instant(vessel["currentEta"])
    # Same declared visitor ETA boundary as company_for; no fleet construction.
    epoch = _instant(world["epoch"])
    hours = vessel["etaHours"]
    if isinstance(hours, bool) or not isinstance(hours, (int, float)):
        raise ValueError("Declared ETA is unavailable")
    shift = 0
    proposal = _mapping(world.get("terminalProposal") or world.get("proposal"))
    outcome = _mapping(world.get("currentArrivalOutcome"))
    if proposal.get("vesselId") == vessel.get("id") and (
            not proposal.get("environmentEvidenceId") or outcome.get("environmentEvidenceId") == proposal.get("environmentEvidenceId")):
        shift = proposal.get("etaShiftHours") or 0
    return epoch + timedelta(hours=hours + shift)


def _passage_for(vessel, area):
    declared = vessel.get("declaredPassages") or {}
    if isinstance(declared, dict) and isinstance(declared.get(area), dict):
        return declared[area]
    rows = list(declared.values()) if isinstance(declared, dict) else declared if isinstance(declared, list) else []
    latest = vessel.get("declaredPassage")
    if isinstance(latest, dict) and not any(_mapping(row).get("id") == latest.get("id") for row in rows):
        rows.append(latest)
    return next((row for row in reversed(rows) if _mapping(row).get("areaId") == area), {})


def evaluate_freshness(problem, world, *, as_of, clock_mode="LIVE", retained=None):
    """Describe stale or unavailable *consumed* inputs without moving a record.

    A completed journey is excluded by the caller's workflow projection. This
    evaluator intentionally makes no statement about an actual missed shipment.
    """
    now = _instant(as_of)
    retained = _mapping(retained)
    basis = _basis(problem)
    reasons = []

    def add(code, text, ref, state="REASSESSMENT"):
        if code not in {r["code"] for r in reasons}:
            reasons.append({"code": code, "text": text, "basis": ref, "status": state,
                "decisionId": problem.get("decisionId"), "evidenceId": basis.get("evidenceId")})

    if not basis:
        add("UNSUPPORTED_LEGACY_EVIDENCE", "This retained comparison has no supported consumed-evidence basis.", "evidence", "UNKNOWN")
    if clock_mode != "LIVE":
        add("OPERATIONAL_CLOCK_NOT_LIVE", "Return the operational decision clock to live before reassessment or continuation; traffic replay is separate.", "operationalClock.mode")
    vessel_id = _mapping(problem.get("subject")).get("id") or basis.get("voyageId")
    fleet = world.get("fleet") if isinstance(world.get("fleet"), list) else []
    vessel = next((row for row in fleet if isinstance(row, dict) and row.get("id") == vessel_id), None)
    if vessel is None:
        add("VOYAGE_NOT_IN_OWNED_FLEET", "The retained voyage is not a member of this visitor's current fleet.", "world.fleet", "UNKNOWN")
    else:
        episode = _mapping(basis.get("operationalEpisode"))
        current = _mapping(vessel.get("operationalEpisode"))
        if not episode.get("id") or not episode.get("voyageLegId") or not current.get("id") or not current.get("voyageLegId"):
            add("CURRENT_CALL_BASIS_UNAVAILABLE", "A supported current call and voyage-leg identity is missing; no call was created by this read.", "operationalEpisode", "UNKNOWN")
        elif any(episode.get(k) != current.get(k) for k in ("id", "voyageLegId")):
            add("CURRENT_CALL_CHANGED", "This frozen comparison belongs to another operational call or voyage leg.", "operationalEpisode")
        if not isinstance(basis.get("portCode"), str) or not isinstance(vessel.get("portCode"), str):
            add("VOYAGE_DESTINATION_UNAVAILABLE", "The consumed or current declared destination cannot be verified.", "portCode", "UNKNOWN")
        elif basis.get("portCode") != vessel.get("portCode"):
            add("VOYAGE_DESTINATION_CHANGED", "The consumed destination differs from the declared current voyage destination.", "portCode")
        try:
            if _instant(basis.get("earliestVoyageArrival")) != _current_eta(world, vessel):
                add("VOYAGE_ETA_CHANGED", "The consumed declared voyage ETA changed within this call; an ETA edit is not a new call.", "earliestVoyageArrival")
        except (KeyError, ValueError, TypeError, OverflowError):
            add("VOYAGE_TIMING_UNAVAILABLE", "The consumed or current declared ETA cannot be verified.", "earliestVoyageArrival", "UNKNOWN")
        cargo = _mapping(basis.get("cargoCommitment"))
        if cargo:
            from .passage_cargo_integration import declaration_identity
            try:
                record = _mapping(_mapping(world.get("cargoCommitments")).get(_mapping(cargo.get("shipment")).get("shipmentId")))
                if not record:
                    add("CARGO_COMMITMENT_UNAVAILABLE", "The current version of the consumed shipment declaration is unavailable.", "cargoCommitment", "UNKNOWN")
                elif record.get("inputVersion") != declaration_identity(cargo):
                    add("CARGO_COMMITMENT_CHANGED", "The consumed shipment or connection declaration changed; the saved result remains frozen.", "cargoCommitment")
            except (TypeError, ValueError):
                add("CARGO_COMMITMENT_MALFORMED", "The retained shipment declaration cannot be checked.", "cargoCommitment", "UNKNOWN")
    if basis:
        try:
            available = _instant(basis.get("availableAt"))
            if available > now:
                add("SOURCE_RECEIPT_NOT_YET_AVAILABLE", "The consumed receipt is future-dated at this projection time.", "availableAt", "UNKNOWN")
            elif now - available > timedelta(hours=1):
                add("CONSUMED_RECEIPT_EXPIRED", "The frozen input receipt is older than the existing one-hour continuation window.", "availableAt")
        except (ValueError, TypeError):
            add("SOURCE_RECEIPT_UNAVAILABLE", "The consumed receipt has no valid aware availability time.", "availableAt", "UNKNOWN")
        try:
            if _instant(basis.get("plannedArrival")) <= now:
                add("REQUESTED_ARRIVAL_ELAPSED", "The scheduled requested arrival has elapsed; actual arrival or execution is not established.", "plannedArrival")
        except (ValueError, TypeError):
            add("REQUESTED_ARRIVAL_UNAVAILABLE", "The retained requested arrival cannot be checked.", "plannedArrival", "UNKNOWN")
    digests = _response_digests(basis)
    for digest in sorted(set(d for d in digests if isinstance(d, str) and _DIGEST.fullmatch(d))):
        status = _mapping(retained.get("originalStatuses")).get(digest)
        if status == "MISSING":
            add("MISSING_REQUIRED_ORIGINAL", "An original consumed source response is missing; prior evidence remains inspectable.", "sourceOriginal:" + digest, "UNKNOWN")
        elif status == "CORRUPT":
            add("CORRUPT_REQUIRED_ORIGINAL", "An original consumed source response fails its retained content hash.", "sourceOriginal:" + digest, "UNKNOWN")
        elif status != "AVAILABLE":
            add("REQUIRED_ORIGINAL_UNCHECKED", "An original consumed source response could not be qualified from retained records.", "sourceOriginal:" + digest, "UNKNOWN")
    if any(not isinstance(d, str) or not _DIGEST.fullmatch(d) for d in digests):
        add("LEGACY_ORIGINAL_IDENTITY_UNAVAILABLE", "A consumed input has no supported original response identity.", "sourceOriginal", "UNKNOWN")
    if basis.get("kind") == "NOTICE_RESTRICTION":
        try:
            restriction = _mapping(basis.get("restriction"))
            plan = _mapping(restriction.get("plan"))
            declared = _passage_for(vessel or {}, plan.get("areaId"))
            if not plan.get("id") or not declared:
                add("RESTRICTION_DECLARATION_UNAVAILABLE", "The consumed route/passage declaration is unavailable for this call.", "restriction.plan", "UNKNOWN")
            elif declared.get("id") != plan.get("id"):
                add("RESTRICTION_DECLARATION_CHANGED", "The consumed route, vessel characteristics or passage declaration changed.", "restriction.plan")
            elif any(declared.get(key) != plan.get(key) for key in ("areaId", "route", "direction", "characteristics",
                    "postPassageHours", "alternativeAccess", "openingRequired", "emergencyTransit", "timezoneAssumption", "sourceFamily")) or _instant(declared.get("passageAt")) != _instant(plan.get("passageAt")):
                add("RESTRICTION_DECLARATION_CHANGED", "The consumed route, vessel characteristics or passage declaration changed.", "restriction.plan")
            if not plan.get("areaId") or plan["areaId"] not in _rows(plan.get("route")):
                add("RESTRICTION_APPLICABILITY_UNAVAILABLE", "An explicit declared route through the consumed restricted area is missing.", "restriction.plan.route", "UNKNOWN")
            if _instant(plan.get("passageAt")) <= now:
                add("DECLARED_PASSAGE_ELAPSED", "The declared scheduled passage is no longer future; actual passage is not established.", "restriction.plan.passageAt")
            notice = _mapping(_mapping(retained.get("restrictions")).get(restriction_key(basis)))
            if not notice or notice.get("_unavailable"):
                add("RESTRICTION_CATALOGUE_UNAVAILABLE", "The retained authority catalogue cannot establish this restriction's current version.", "restriction.revisionId", "UNKNOWN")
            else:
                if notice.get("sourceStatus") != "CURRENT" or notice.get("status") != "SCHEDULED":
                    add("RESTRICTION_SOURCE_UNAVAILABLE_OR_WITHDRAWN", "The retained authority restriction is unavailable, cancelled or withdrawn; no new restriction consequence is inferred.", "restriction.revisionId")
                if notice.get("revisionId") != restriction.get("revisionId"):
                    add("RESTRICTION_REVISION_CHANGED", "The authority restriction has a different retained revision; refresh a linked successor.", "restriction.revisionId")
                if notice.get("areaId") != plan.get("areaId"):
                    add("RESTRICTION_APPLICABILITY_CHANGED", "The retained restriction applies to a different area than the consumed passage declaration.", "restriction.plan.areaId")
                checked = _instant(notice.get("checkedAt"))
                if checked > now or now > checked + timedelta(hours=6):
                    add("RESTRICTION_RECEIPT_EXPIRED", "The retained authority receipt is outside its six-hour validity window.", "restriction.checkedAt")
                windows = _rows(notice.get("windows"))
                if ((notice.get("withdrawsAt") and now >= _instant(notice["withdrawsAt"]))
                        or (notice.get("productThrough") and now >= _instant(notice["productThrough"]))
                        or (windows and all(_instant(w["end"]) <= now for w in windows))):
                    add("RESTRICTION_EFFECTIVE_PERIOD_ELAPSED", "The retained restriction's effective period has elapsed; actual occurrence remains unknown.", "restriction.windows")
                if not any(_instant(w["start"]) <= _instant(plan["passageAt"]) < _instant(w["end"]) for w in windows):
                    add("RESTRICTION_APPLICABILITY_CHANGED", "The declared passage does not overlap a retained supported restriction interval.", "restriction.plan.passageAt")
                else:
                    window = next(w for w in windows if _instant(w["start"]) <= _instant(plan["passageAt"]) < _instant(w["end"]))
                    if window.get("calculationSupported") is False or notice.get("calculationSupported") is False:
                        add("RESTRICTION_CALCULATION_UNSUPPORTED", "The retained restriction interval is not qualified for this conditional calculation.", "restriction.window", "UNKNOWN")
                    if restriction.get("sourceFamily") == "NAVCEN_MSI":
                        if plan.get("openingRequired") is not True or plan.get("emergencyTransit") is not False or plan.get("timezoneAssumption") != window.get("timeZone"):
                            add("RESTRICTION_APPLICABILITY_CHANGED", "The declared opening, exemption or confirmed time-zone basis no longer supports this ordinary passage calculation.", "restriction.plan")
                    elif plan.get("direction") not in _rows(_mapping(notice.get("applicability")).get("directions")):
                        add("RESTRICTION_APPLICABILITY_CHANGED", "The declared passage direction is not supported by this retained restriction.", "restriction.plan.direction")
        except (KeyError, TypeError, ValueError, AttributeError):
            add("RESTRICTION_BASIS_MALFORMED", "The retained restriction or declared applicability cannot be verified.", "restriction", "UNKNOWN")
    consumed = _mapping(basis.get("feedbackConsumption"))
    if consumed:
        cid = consumed.get("id")
        check = _mapping(_mapping(retained.get("feedbackStatus")).get(cid)) if isinstance(cid, str) else {}
        if check.get("status") == "CHANGED":
            add("CONSUMED_FEEDBACK_CHANGED", "A consumed claim verification, relevant vintage or actually applied policy changed; unrelated counts are excluded.", "feedbackConsumption")
        elif check.get("status") != "CURRENT":
            add("CONSUMED_FEEDBACK_UNAVAILABLE", "Consumer-bound feedback could not be checked from retained source/evidence records.", "feedbackConsumption", "UNKNOWN")
    status = "REASSESSMENT" if any(r["status"] == "REASSESSMENT" for r in reasons) else "UNKNOWN" if reasons else "CURRENT"
    return {"policyVersion": POLICY, "status": status, "reasons": reasons, "checkedAt": now.isoformat()}


class _ReadOnlyFeedback:
    """Frozen public feedback rows for existing pure continuation predicates."""
    def __init__(self, rows, original_status):
        self._rows, self._original_status = rows, original_status

    def feedback(self, kind, identifier=None):
        return deepcopy([body for row_kind, row_id, body in self._rows if row_kind == kind and (identifier is None or row_id == identifier)])

    def retained_original_status(self, record):
        state = self._original_status(record.get("responseSha256"))
        return None if state == "AVAILABLE" else "CORRUPT_ORIGINAL" if state == "CORRUPT" else "MISSING_ORIGINAL"


def collect_retained_dependencies(problems, *, environment_root, public_feedback_db, as_of):
    """Read only canonical public files and a consistent SQLite read snapshot.

    No supplied record can choose a path. Invalid or unavailable dependencies
    are represented as unknown; provider absence is never a cancellation.
    """
    now = _instant(as_of)
    root, db_path = Path(environment_root), Path(public_feedback_db)
    result = {"originalStatuses": {}, "restrictions": {}, "feedbackStatus": {}, "asOf": now.isoformat()}

    def original_status(digest):
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            return "MISSING"
        if digest in result["originalStatuses"]:
            return result["originalStatuses"][digest]
        found = False
        # Legacy shared public data may sit next to its configured ledger.
        paths = [base / folder / (digest + ".response") for base in (root, db_path.parent)
                 for folder in ("archive", "operational_notices", "shared_feedback")]
        for path in dict.fromkeys(paths):
            try:
                if path.is_file():
                    found = True
                    if hashlib.sha256(path.read_bytes()).hexdigest() == digest:
                        result["originalStatuses"][digest] = "AVAILABLE"
                        return "AVAILABLE"
            except OSError:
                continue
        result["originalStatuses"][digest] = "CORRUPT" if found else "MISSING"
        return result["originalStatuses"][digest]

    def read_json(name):
        try:
            value = json.loads((root / "operational_notices" / name).read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {"_unavailable": True}
        except (OSError, ValueError, TypeError):
            return {"_unavailable": True}

    bases = [_basis(problem) for problem in problems if isinstance(problem, dict)]
    if any(b.get("kind") == "NOTICE_RESTRICTION" for b in bases):
        nav = read_json("navcen-catalogue-latest.json")
        notices = nav.get("notices") if isinstance(nav.get("notices"), list) else []
        if not notices:
            legacy = read_json("navcen-53842-latest.json")
            if not legacy.get("_unavailable"):
                notices = [legacy]
        for row in notices:
            if not isinstance(row, dict):
                continue
            uid = row.get("providerNoticeId") or str(row.get("noticeId", "")).split(":")[-1]
            if uid:
                result["restrictions"]["NAVCEN_MSI:" + str(uid)] = deepcopy(row)
        result["restrictions"]["PEEL_PORTS:MNTM 2026-18"] = read_json("eastham-2026-18-latest.json")
    for basis in bases:
        for digest in _response_digests(basis):
            original_status(digest)
    consumed_rows = [_mapping(basis.get("feedbackConsumption")) for basis in bases if basis.get("feedbackConsumption")]
    if consumed_rows:
        try:
            # mode=ro refuses absent databases; BEGIN reads a coherent WAL view.
            connection = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
            try:
                connection.execute("PRAGMA query_only=ON")
                connection.execute("BEGIN")
                rows = [(kind, row_id, json.loads(body)) for kind, row_id, body in connection.execute("SELECT kind, id, body FROM shared_feedback")]
            finally:
                connection.close()
            store = _ReadOnlyFeedback(rows, original_status)
            from src.portwatch_os.learning.shared_feedback import require_consumption
            for consumed in consumed_rows:
                cid = consumed.get("id")
                if not isinstance(cid, str):
                    continue
                try:
                    require_consumption(store, consumed, now.isoformat())
                    result["feedbackStatus"][cid] = {"status": "CURRENT"}
                except ValueError as exc:
                    known_change = str(exc).startswith(("Consumed verification changed", "Consumed news target vintage/conflict changed",
                        "Consumed claim revised", "Consumed applied reliability/correction changed", "Applicable applied policy has conflicting versions"))
                    result["feedbackStatus"][cid] = {"status": "CHANGED" if known_change else "UNAVAILABLE"}
                except (KeyError, TypeError, AttributeError, IndexError):
                    result["feedbackStatus"][cid] = {"status": "UNAVAILABLE"}
        except (OSError, sqlite3.Error, ValueError, TypeError):
            for consumed in consumed_rows:
                if isinstance(consumed.get("id"), str):
                    result["feedbackStatus"][consumed["id"]] = {"status": "UNAVAILABLE"}
    return result
