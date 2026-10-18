"""Bounded human evidence review on the existing intelligence task ledger.

Reviewing port context answers an inspection question. It does not turn a
publisher's report into an individual vessel outcome or verify a news event.
"""
import copy

from src.portwatch_os.learning.shared_feedback import identifier, instant

CONTEXT_CLASSES = {
    "AGGREGATE_PORT_ACTIVITY",
    "PUBLISHED_EXPECTED_ARRIVAL",
    "REPORTED_PORT_ARRIVAL",
    "REPORTED_PORT_POSITION",
}
TASK_QUESTION = "INSPECT_PUBLISHED_PORT_CONTEXT_FOR_DECLARED_VOYAGE"


def checked_evidence(evidence, now):
    """Only server-resolved, retained originals can support this review."""
    if not isinstance(evidence, dict) or evidence.get("semanticClass") not in CONTEXT_CLASSES:
        raise ValueError("This evidence product has no reviewed port-context semantics")
    if evidence.get("originalHashVerified") is not True:
        raise ValueError("A hash-checked original source response is required")
    digest = evidence.get("sha256", "")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Original source identity is missing")
    if (not evidence.get("portCode") or not isinstance(evidence.get("selector"), dict)
            or not evidence["selector"] or not evidence.get("sourceUrl")):
        raise ValueError("Source, physical port and exact retained evidence selector are required")
    if not evidence.get("firstAvailableAt") or instant(evidence["firstAvailableAt"]) > now:
        raise ValueError("Evidence was unavailable at the review time")
    available_at = instant(evidence["firstAvailableAt"])
    for field in ("observedAt", "publishedAt"):
        # These are source/report clocks, not an expected-arrival target. A
        # future target inside the retained expected-arrival row stays valid.
        if evidence.get(field) and instant(evidence[field]) > available_at:
            raise ValueError("Source/report time cannot follow its first application availability")
    if evidence.get("checkedAt") and instant(evidence["checkedAt"]) > now:
        raise ValueError("A later source check cannot support an earlier review")
    record = evidence.get("record")
    if not isinstance(record, dict):
        raise ValueError("A retained publisher record is required")
    for item in (evidence, record):
        if (item.get("isSimulated") is True or item.get("eligibleForRealTarget") is True
                or item.get("recordKind") in ("SIMULATED", "DEMO", "DEMO_OUTCOME", "SIMULATED_OUTCOME")
                or item.get("sourceFamily") in ("DEMO_SCENARIO", "SIMULATED")):
            raise ValueError("Demo or asserted actual records cannot be reviewed as live port evidence")
    return copy.deepcopy(evidence)


def task_source(evidence, *, context_confirmed, destination_port, now):
    evidence = checked_evidence(evidence, now)
    if evidence["portCode"] != destination_port and context_confirmed is not True:
        raise ValueError("Confirm the other port as candidate context; it is not this voyage's declared destination")
    title = evidence.get("title") or "Published port evidence at " + evidence["portCode"]
    return {
        "id": identifier(evidence["selector"]), "category": "operational_context",
        "title": title, "fact": evidence.get("meaning") or title,
        "source": evidence["sourceUrl"], "responseSha256": evidence["sha256"],
        "availableAt": evidence["firstAvailableAt"], "status": evidence.get("status", "RETAINED"),
        "portCodes": [evidence["portCode"]], "operationalEvidence": evidence,
        "relationship": "Operator-selected published port context; no real-vessel association, route membership or actual execution is inferred.",
        "contextDeclaration": {"portCode": evidence["portCode"], "destinationPortCode": destination_port,
            "confirmed": context_confirmed is True, "meaning": "Context selection only; not identity or passage confirmation"},
    }


def build_disposition(task, evidence, *, namespace, request_id, who, now, note=""):
    evidence = checked_evidence(evidence, now)
    original = copy.deepcopy(task)
    original.pop("dispositionIds", None)
    context_task = original.get("taskQuestion") == TASK_QUESTION
    source_evidence = (original.get("source") or {}).get("operationalEvidence") or {}
    if context_task and source_evidence.get("portCode") != evidence["portCode"]:
        raise ValueError("This review answers the frozen task's selected physical-port context only")
    result = {
        "id": "review-disposition-" + identifier([namespace, task["id"], request_id]),
        "contractVersion": "intelligence-evidence-disposition-v1", "taskId": task["id"],
        "type": "CONTEXT_REVIEWED", "reviewedAt": now.isoformat(), "actor": who.actor,
        "role": who.role, "vesselId": task["vesselId"], "portCode": task["portCode"],
        "evidencePortCode": evidence["portCode"],
        "operationalEpisode": copy.deepcopy(task["operationalEpisode"]),
        "originalTask": original, "originalTaskSha256": identifier(original),
        "evidence": evidence, "operatorNote": note,
        "answersContextQuestion": context_task,
        "taskStatus": "CONTEXT_REVIEWED" if context_task else "PENDING_VERIFICATION",
        "sourceClaimStatus": "UNRESOLVED", "actualExecutionStatus": "NOT_OBSERVED",
        "newsVerificationChanged": False, "createsOperationalTarget": False,
        "eligibleForRealTarget": False, "realResolvedTargetsAdded": 0,
        "calculatedDelayHours": None, "calculatedCost": None,
        "meaning": "Published port context was inspected. Aggregate activity is not individual AIS; expected and reported port records are not all-fast or proof that this fictional vessel executed an action. Source accuracy and operational prediction error remain separate and unresolved.",
    }
    return result


def project_task(task, dispositions):
    """Project additive reviews without rewriting the original task context."""
    rows = sorted(dispositions, key=lambda row: (row["reviewedAt"], row["id"]))
    if not rows:
        return task
    result = copy.deepcopy(task)
    result["dispositions"] = rows
    result["latestDispositionId"] = rows[-1]["id"]
    result["status"] = rows[-1]["taskStatus"]
    result["sourceClaimStatus"] = "UNRESOLVED"
    result["actualExecutionStatus"] = "NOT_OBSERVED"
    return result
