"""Read-only fleet worklist over retained comparisons and their explicit links.

This module neither loads stores nor recomputes decisions. The caller supplies
one visitor-owned snapshot and side-effect-free continuation assessments.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

POLICY_VERSION = "fleet-decision-triage-v1"
PLAN_SELECTION_VERSION = "current-call-plan-selection-v1"
CATEGORY_ORDER = ("CURRENT_CONDITIONAL_FAILURE", "REASSESSMENT", "COMPANY_ACTION",
                  "WAITING_OTHER_ROLE", "INCOMPLETE_ASSESSMENT", "MONITORED")
APPROVED_STATES = {"APPROVED", "PROPOSED", "ISSUED", "ACCEPTED", "OBSERVED", "SCORED"}


def _object(value):
    return value if isinstance(value, dict) else {}


def _rows(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, (list, tuple)) else []


def _dedupe(records, key):
    """Exact retry representations collapse; conflicting bodies remain ambiguous."""
    seen, result = {}, []
    for record in records:
        identity = _text(record.get(key))
        prior = seen.setdefault(identity, []) if identity else []
        if any(record == old for old in prior):
            continue
        prior.append(record)
        result.append(record)
    return result


def _text(value):
    return value if isinstance(value, str) and value else None


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _basis(problem):
    evidence = _object(problem.get("evidence"))
    return _object(evidence.get("currentEnvironment")) or _object(evidence.get("intelligenceBasis"))


def _id(problem):
    return _text(problem.get("decisionId"))


def _option(problem, identity):
    if not _text(identity):
        return None
    matches = [o for o in _rows(problem.get("options")) if o.get("optionId") == identity]
    return matches[0] if len(matches) == 1 else None


def _reason(code, text, *, decision=None, option=None, basis="retained visitor records"):
    result = {"code": code, "text": text, "basis": basis}
    if decision:
        result["decisionId"] = _id(decision)
        evidence_id = _text(_basis(decision).get("evidenceId"))
        if evidence_id:
            result["evidenceId"] = evidence_id
    if option:
        result["optionId"] = option.get("optionId")
    return result


def _same_call(problem, vessel):
    current = _object(vessel.get("operationalEpisode"))
    frozen = _object(_basis(problem).get("operationalEpisode"))
    return bool(_text(current.get("id")) and _text(current.get("voyageLegId")) and frozen.get("id") == current["id"]
                and frozen.get("voyageLegId") == current["voyageLegId"]
                and frozen.get("vesselId") == vessel.get("id")
                and (not current.get("namespace") or frozen.get("namespace") == current["namespace"]))


def _approved(problem):
    return problem.get("workflow") in APPROVED_STATES and _option(problem, problem.get("humanChoice")) is not None


def _unique_leaf(problems):
    """One complete acyclic retained chain can select its leaf; date/order cannot."""
    by_id = {_id(p): p for p in problems}
    if None in by_id or len(by_id) != len(problems):
        return None
    parents, predecessor_by_child = set(), {}
    for problem in problems:
        predecessor = _text(_object(problem.get("evidence")).get("predecessorDecisionId"))
        parent = by_id.get(predecessor)
        if parent is None:
            continue
        evidence = _object(parent.get("evidence"))
        children = evidence.get("successorDecisionIds")
        linked = isinstance(children, list) and _id(problem) in children
        if linked or evidence.get("successorDecisionId") == _id(problem):
            parents.add(predecessor)
            predecessor_by_child[_id(problem)] = predecessor
    leaves = [p for p in problems if _id(p) not in parents]
    if len(leaves) != 1:
        return None
    # A disconnected cycle has no leaf of its own and must not disappear merely
    # because another comparison is a unique leaf. Every candidate must belong
    # to this verified chain, and no retained ancestor may repeat.
    visited, cursor = set(), _id(leaves[0])
    while cursor is not None:
        if cursor in visited:
            return None
        visited.add(cursor)
        cursor = predecessor_by_child.get(cursor)
    return leaves[0] if len(visited) == len(problems) else None


def _journey(world, problem):
    identity = _id(problem)
    journey = dict(_object(_object(world.get("weatherJourneys")).get(identity)))
    active = _object(world.get("terminalProposal"))
    if active.get("decisionId") == identity:
        journey.setdefault("proposal", active)
        if world.get("currentArrivalReview"):
            journey.setdefault("reviewDecisionId", world["currentArrivalReview"])
        if world.get("currentArrivalOutcome"):
            journey.setdefault("outcome", world["currentArrivalOutcome"])
    return journey


def _valid_proposal(world, problem):
    proposal = _object(_journey(world, problem).get("proposal"))
    return _proposal_matches(proposal, problem)


def _proposal_matches(proposal, problem):
    return bool(proposal.get("decisionId") == _id(problem)
                and proposal.get("optionId") == problem.get("humanChoice")
                and proposal.get("vesselId") == _object(problem.get("subject")).get("id")
                and proposal.get("environmentEvidenceId") == _basis(problem).get("evidenceId"))


def _select_plan(world, current, vessel):
    active = _object(world.get("terminalProposal"))
    active_episode = _object(active.get("operationalEpisode")) or _object(_object(active.get("approvedAction")).get("operationalEpisode"))
    current_episode = _object(vessel.get("operationalEpisode"))
    active_record = next((p for p in current if _id(p) == active.get("decisionId")), None)
    active_bound_here = (active.get("vesselId") == vessel.get("id") or active_episode.get("vesselId") == vessel.get("id"))
    active_other_call = bool(_text(active_episode.get("id")) and _text(current_episode.get("id"))
        and (active_episode["id"] != current_episode["id"] or
             (_text(active_episode.get("voyageLegId")) and active_episode["voyageLegId"] != current_episode.get("voyageLegId"))))
    if active_bound_here and active_other_call:
        if active_record:
            return None, "AMBIGUOUS", _reason("ACTIVE_PROPOSAL_BASIS_INCONSISTENT",
                "The active proposal and its retained comparison identify different calls. No current plan was inferred from the conflicting relationship.")
        # An explicitly identified previous call is historical, even if the
        # same vessel has a uniquely applicable current baseline today.
        active = {}
    elif active_bound_here and _text(active.get("decisionId")) and active_record is None:
        return None, "AMBIGUOUS", _reason("ACTIVE_APPROVED_COMPARISON_UNAVAILABLE" if _text(active_episode.get("id")) else "ACTIVE_PROPOSAL_CURRENT_CALL_UNAVAILABLE",
            "The active Company proposal's exact durable comparison is unavailable. A different saved baseline was not substituted; inspect the missing relationship before reassessment.")
    if active_record and (not _approved(active_record) or not _proposal_matches(active, active_record)):
        return None, "AMBIGUOUS", _reason("ACTIVE_PROPOSAL_BASIS_INCONSISTENT",
            "The active proposal does not match its durable approved human choice and frozen evidence. Refresh the linked state before selecting a plan.")
    approved = [p for p in current if _approved(p)]
    if approved:
        linked = [p for p in approved if _valid_proposal(world, p)]
        explicit = [p for p in linked if _id(p) == active.get("decisionId")]
        if len(explicit) == 1:
            return explicit[0], "APPROVED", None
        if len(linked) == len(approved):
            selected = _unique_leaf(linked)
            if selected:
                return selected, "APPROVED", None
        return None, "AMBIGUOUS", _reason("AMBIGUOUS_APPROVED_PLAN",
            "Approved records lack one consistent active proposal relationship. Review their exact choices; no candidate was adopted.")
    if any(p.get("workflow") in APPROVED_STATES for p in current):
        return None, "AMBIGUOUS", _reason("APPROVAL_CHOICE_UNAVAILABLE",
            "An approval has no unique retained humanChoice option; its active plan cannot be established.")
    candidates = [p for p in current if p.get("workflow") in {"COMPUTED", "REVIEWED"}]
    selected = _unique_leaf(candidates)
    if selected and _option(selected, selected.get("baselineOptionId")):
        return selected, "BASELINE_NOT_APPROVED", None
    if candidates:
        return None, "AMBIGUOUS", _reason("AMBIGUOUS_CURRENT_COMPARISON",
            "Several separate current comparisons exist without one declared current-plan basis. Open a specific candidate for review.")
    return None, "MISSING", _reason("NEEDS_ASSESSMENT", "No applicable retained comparison establishes this call's current plan.")


def _workflow(world, source, option, decisions, advisories):
    """Follow actual linked records rather than treating source APPROVED as final."""
    source_id = _id(source)
    journey = _journey(world, source)
    port_id = _text(journey.get("reviewDecisionId"))
    port_copies = [p for p in decisions if _object(_object(p.get("evidence")).get("companyProposal")).get("decisionId") == source_id]
    ports = [p for p in port_copies if _id(p) == port_id] if port_id else port_copies
    port = ports[0] if len(ports) == 1 else None
    result = {"stage": "NEEDS_ASSESSMENT", "nextRole": "SHIPPING_COMPANY",
              "companyDecisionId": source_id, "portDecisionId": _id(port) if port else port_id,
              "advisoryIds": [], "completed": False}
    port_relation = _object(_object((port or {}).get("evidence")).get("companyProposal"))
    port_valid = not port or (port_relation.get("optionId") == source.get("humanChoice")
        and port_relation.get("environmentEvidenceId") == _basis(source).get("evidenceId")
        and _basis(port).get("evidenceId") == _basis(source).get("evidenceId"))
    if port_id and port is None or not port_id and len(port_copies) > 1 or not port_valid:
        result.update(stage="UPDATING_LINKED_STATE", nextRole=None)
        return result
    declared_ids = _object((port or {}).get("evidence")).get("advisories")
    expected = set(v for v in declared_ids if isinstance(v, str)) if isinstance(declared_ids, list) else set()
    linked = [a for a in advisories if _object(a.get("evidence")).get("decisionId") in {source_id, _id(port) if port else source_id}
              or a.get("advisoryId") in expected]
    linked = sorted(linked, key=lambda a: a.get("advisoryId") or "")
    result["advisoryIds"] = [a["advisoryId"] for a in linked if isinstance(a.get("advisoryId"), str)]
    linked_valid = all(a.get("recipientVesselId") == _object(source.get("subject")).get("id")
        and (_object(_object(a.get("evidence")).get("currentEnvironment")) or
             _object(_object(a.get("evidence")).get("intelligenceBasis"))).get("evidenceId") == _basis(source).get("evidenceId") for a in linked)
    if expected - set(result["advisoryIds"]) or not linked_valid or len(result["advisoryIds"]) != len(set(result["advisoryIds"])):
        result.update(stage="UPDATING_LINKED_STATE", nextRole=None)
        return result
    outcome = _object(journey.get("outcome")) or _object(_object(source.get("evidence")).get("demoOutcome"))
    if port:
        outcome = outcome or _object(_object(port.get("evidence")).get("demoOutcome"))
    outcome = outcome or next((_object(_object(a.get("evidence")).get("demoOutcome")) for a in linked
                               if _object(_object(a.get("evidence")).get("demoOutcome"))), {})
    states = {_text(a.get("state")) or "UNKNOWN" for a in linked}
    deadlines = [_time(a.get("validUntil")) for a in linked if a.get("state") in {"issued", "acknowledged", "draft", "under_review", "queried"}]
    known_deadlines = [v for v in deadlines if v is not None]
    if known_deadlines:
        result["_advisoryDeadlineAt"] = min(known_deadlines).isoformat()
    if linked and states == {"completed"}:
        result.update(stage="SIMULATED_OUTCOME_COMPLETED" if outcome.get("kind") == "SIMULATED_DEMO_OUTCOME" else "ADVISORY_COMPLETED",
                      nextRole=None, completed=True)
    elif outcome:
        result.update(stage="UPDATING_LINKED_STATE", nextRole=None)
    elif states & {"declined", "rejected", "withdrawn"}:
        result.update(stage="PROPOSAL_RETURNED", nextRole="SHIPPING_COMPANY")
    elif states & {"expired"}:
        result.update(stage="ADVISORY_EXPIRED", nextRole="SHIPPING_COMPANY")
    elif states & {"queried"}:
        result.update(stage="PORT_RESPONSE_PENDING", nextRole="PORT_AUTHORITY")
    elif states & {"draft", "under_review"}:
        result.update(stage="PORT_ISSUE_PENDING", nextRole="PORT_AUTHORITY")
    elif states & {"issued", "acknowledged"}:
        result.update(stage="VESSEL_RESPONSE_PENDING", nextRole="VESSEL_OPERATOR")
    elif linked and states <= {"accepted", "completed"}:
        result.update(stage="VESSEL_ACCEPTED_DEMO_OUTCOME_PENDING", nextRole="PORT_AUTHORITY")
    elif linked:
        result.update(stage="UPDATING_LINKED_STATE", nextRole=None)
    elif source.get("workflow") == "COMPUTED":
        result.update(stage="COMPANY_REVIEW_PENDING", nextRole="SHIPPING_COMPANY")
    elif source.get("workflow") == "REVIEWED":
        result.update(stage="COMPANY_APPROVAL_PENDING", nextRole="SHIPPING_COMPANY")
    elif port is None and _approved(source):
        result.update(stage="PORT_REVIEW_PENDING", nextRole="PORT_AUTHORITY")
    elif port and port.get("workflow") in {"COMPUTED", "REVIEWED"}:
        result.update(stage="PORT_REVIEW_PENDING" if port["workflow"] == "COMPUTED" else "PORT_APPROVAL_PENDING", nextRole="PORT_AUTHORITY")
    elif port and port.get("workflow") == "APPROVED":
        result.update(stage="CURRENT_PLAN_RETAINED" if option.get("isBaseline") else "PORT_ISSUE_PENDING",
                      nextRole=None if option.get("isBaseline") else "PORT_AUTHORITY")
    elif port:
        result.update(stage="UPDATING_LINKED_STATE", nextRole=None)
    return result


def _candidate(problem):
    return {"decisionId": _id(problem), "baselineOptionId": _text(problem.get("baselineOptionId")),
            "optionId": _text(problem.get("humanChoice")) or _text(problem.get("baselineOptionId")),
            "recommendationOptionId": _text(_object(problem.get("recommendation")).get("optionId")),
            "workflow": _text(problem.get("workflow")),
            "predecessorDecisionId": _text(_object(problem.get("evidence")).get("predecessorDecisionId")),
            "evidenceId": _text(_basis(problem).get("evidenceId"))}


def _deadline(problem, cargo, as_of, workflow):
    if workflow.get("completed"):
        return None
    at, kind, basis = _time(workflow.get("_advisoryDeadlineAt")), "ADVISORY_VALID_UNTIL", "Retained validity of the linked advisory awaiting a response or Port action"
    if at is None and workflow.get("stage") in {"COMPANY_REVIEW_PENDING", "COMPANY_APPROVAL_PENDING", "PORT_REVIEW_PENDING", "PORT_APPROVAL_PENDING"}:
        at, kind, basis = _time(problem.get("decisionDeadline")), "COMPARISON_ACTION_DEADLINE", "Retained comparison decisionDeadline; not the vessel ETA or cargo cutoff"
    if at is None and cargo and cargo.get("mustMeet"):
        at, kind, basis = _time(cargo.get("cutoffAt")), "CARGO_LOADING_CUTOFF", "Declared required loading cutoff; not an approval deadline or vessel ETA"
    if at is None:
        return None
    return {"at": at.isoformat(), "kind": kind, "hoursRemaining": (at-as_of).total_seconds()/3600, "basis": basis}


def _row(world, vessel, current, all_decisions, advisories, freshness, as_of, consistent):
    episode = _object(vessel.get("operationalEpisode"))
    selected, basis, selection_reason = _select_plan(world, current, vessel) if _text(episode.get("id")) and _text(episode.get("voyageLegId")) else (
        None, "MISSING", _reason("CURRENT_CALL_UNAVAILABLE", "No retained current call/leg identity is available. Start the existing explicit assessment or new-call action."))
    option_id = selected.get("humanChoice") if basis == "APPROVED" else (selected or {}).get("baselineOptionId")
    option = _option(selected, option_id) if selected else None
    reasons, missing = [], []
    if selection_reason:
        reasons.append(selection_reason)
        missing.append(selection_reason["code"])
    workflow = _workflow(world, selected, option, all_decisions, advisories) if selected and option else {
        "stage": "AMBIGUOUS_PLAN" if basis == "AMBIGUOUS" else "NEEDS_ASSESSMENT", "nextRole": "SHIPPING_COMPANY",
        "companyDecisionId": None, "portDecisionId": None, "advisoryIds": [], "completed": False}
    raw_fresh = _object(freshness.get(_id(selected))) if selected else {}
    safe_reasons = [{key: value for key, value in reason.items() if key in {"code", "text", "basis", "evidenceId", "decisionId", "optionId"} and isinstance(value, str)} for reason in _rows(raw_fresh.get("reasons"))]
    fresh = {"status": raw_fresh.get("status") if raw_fresh.get("status") in {"CURRENT", "REASSESSMENT", "UNKNOWN"} else "UNKNOWN",
             "reasons": safe_reasons,
             "sourceChanges": [{k:v for k,v in change.items() if k in {"code","text","basis","noticeId","consumedRevisionId","currentRevisionId","consumedAvailableAt","currentAvailableAt","changes","unknown","nextAction"}} for change in _rows(raw_fresh.get("sourceChanges"))]}
    if workflow["completed"]:
        fresh = {"status": "NOT_REQUIRED_COMPLETED", "reasons": []}
    elif selected:
        reasons.extend({"code": _text(r.get("code")) or "FRESHNESS_UNAVAILABLE", "text": _text(r.get("text")) or "Consumed evidence could not be checked.",
                        "basis": _text(r.get("basis")) or "Retained consumed evidence", "decisionId": _id(selected),
                        **({"evidenceId": _text(r.get("evidenceId"))} if _text(r.get("evidenceId")) else {})} for r in fresh["reasons"])
        if fresh["status"] == "UNKNOWN" and not fresh["reasons"]:
            reasons.append(_reason("FRESHNESS_UNAVAILABLE", "The consumed basis could not be verified from retained records.", decision=selected))
    if not consistent:
        reasons.insert(0, _reason("SNAPSHOT_UPDATING", "Linked visitor records changed during the bounded snapshot read. Refresh before acting."))
        fresh = {"status": "UNKNOWN", "reasons": [reasons[0]]}
    cargo = None
    required_failure = incomplete_required = elapsed_cutoff = False
    if selected and option:
        declaration = _object(_basis(selected).get("cargoCommitment"))
        assessment = _object(_object(_object(option.get("evaluation")).get("derived")).get("cargoAssessment"))
        if declaration:
            cargo = {"mustMeet": declaration.get("mustMeet") is True, "status": _text(assessment.get("status")) or "UNKNOWN",
                     "timingStatus": _text(assessment.get("timingStatus")) or "UNKNOWN", "slackHours": _number(assessment.get("slackHours")),
                     "cutoffAt": _text(assessment.get("cutoffAt")), "unit": "hours",
                     "basis": "Frozen applicable option under declared fictional handling, schedule and capacity assumptions"}
            if cargo["status"] == "COMPATIBLE_UNDER_ASSUMPTIONS" and (cargo["slackHours"] is None or _time(cargo["cutoffAt"]) is None or cargo["timingStatus"] != "FITS"):
                cargo["status"] = "UNKNOWN"
                missing.append("retained cargo timing result")
            retained_reasons = assessment.get("reasons")
            if cargo["status"] == "BLOCKED" and not (isinstance(retained_reasons, list) and any(isinstance(r, str) and r for r in retained_reasons)):
                cargo["status"] = "UNKNOWN"
                missing.append("retained cargo decisive rule")
            if cargo["mustMeet"] and not workflow["completed"]:
                cutoff = _time(cargo["cutoffAt"])
                elapsed_cutoff = cutoff is not None and cutoff <= as_of
                if elapsed_cutoff:
                    reasons.append(_reason("SCHEDULED_CUTOFF_ELAPSED", "The declared scheduled cutoff has passed without suitable cargo execution evidence. This does not prove an actual missed shipment.", decision=selected, option=option))
                elif cargo["status"] == "BLOCKED" and fresh["status"] == "CURRENT":
                    required_failure = True
                    raw_reasons = assessment.get("reasons")
                    decisive = next((r for r in raw_reasons if isinstance(r, str) and r), "The retained required connection rule fails.") if isinstance(raw_reasons, list) else "The retained required connection rule fails."
                    reasons.insert(0, _reason("REQUIRED_CARGO_CONNECTION_BLOCKED", "Conditional required connection failure under declared assumptions: " + decisive,
                                             decision=selected, option=option, basis="Applicable plan's retained cargo assessment; other alternatives are not current plans"))
                elif cargo["status"] not in {"BLOCKED", "COMPATIBLE_UNDER_ASSUMPTIONS"}:
                    incomplete_required = True
                    reasons.append(_reason("REQUIRED_CARGO_ASSESSMENT_INCOMPLETE", "Timing or compatibility basis for the required connection is incomplete; no missed shipment is established.", decision=selected, option=option))
                    raw_missing = assessment.get("missing")
                    if isinstance(raw_missing, list):
                        missing.extend(v for v in raw_missing if isinstance(v, str))
                elif cargo["status"] == "BLOCKED":
                    reasons.append(_reason("FROZEN_CARGO_CONCLUSION_NOT_CURRENT", "The frozen selected-plan cargo failure remains inspectable, but its basis needs reassessment before it can be treated as current.", decision=selected, option=option))
            elif not cargo["mustMeet"] and cargo["status"] != "COMPATIBLE_UNDER_ASSUMPTIONS" and not workflow["completed"]:
                reasons.append(_reason("OPTIONAL_CARGO_CONTEXT", "Optional cargo context is blocked or incomplete; it does not create a required passage block.", decision=selected, option=option))
        if workflow["completed"]:
            reasons.append(_reason("SIMULATION_JOURNEY_COMPLETED" if workflow["stage"] == "SIMULATED_OUTCOME_COMPLETED" else "ADVISORY_JOURNEY_COMPLETED",
                "The linked journey is completed. Simulation and advisory completion do not establish real cargo booking, execution or measured benefit.", decision=selected, option=option))
        elif workflow["stage"] == "UPDATING_LINKED_STATE":
            reasons.append(_reason("LINKED_WORKFLOW_UNAVAILABLE", "Linked proposal, review or advisory records are inconsistent or unavailable. The next responsible role cannot yet be established.", decision=selected))
            missing.append("linked workflow")
        elif workflow["stage"] == "PROPOSAL_RETURNED":
            reasons.append(_reason("PROPOSAL_RETURNED", "A linked advisory was declined, rejected or withdrawn. Company review is required; no action is treated as executed.", decision=selected))
        elif workflow["stage"] == "ADVISORY_EXPIRED":
            reasons.append(_reason("ADVISORY_EXPIRED", "A linked advisory expired. Company must reassess before another proposal.", decision=selected))
        elif workflow["nextRole"]:
            reasons.append(_reason(workflow["stage"], {
                "SHIPPING_COMPANY": "Company review or approval is pending for the retained comparison.",
                "PORT_AUTHORITY": "The linked journey awaits the scoped Port desk's next step.",
                "VESSEL_OPERATOR": "The issued advisory awaits Vessel acknowledgement or response; Company approval is already retained."
            }[workflow["nextRole"]], decision=selected))
        else:
            reasons.append(_reason("NO_IDENTIFIED_BLOCK_WITHIN_ASSESSED_SCOPE", "No identified blocking condition within the retained assessment's evaluated scope. This is not route safety or operational-readiness verification.", decision=selected, option=option))
    advisory_deadline = _time(workflow.get("_advisoryDeadlineAt"))
    advisory_elapsed = bool(not workflow["completed"] and advisory_deadline is not None and advisory_deadline <= as_of)
    if advisory_elapsed:
        reasons.append(_reason("ADVISORY_RESPONSE_WINDOW_ELAPSED", "The linked advisory's retained validity window has elapsed. Its recorded state is preserved, but a fresh review is required before further action.", decision=selected))
        workflow["nextRole"] = "SHIPPING_COMPANY"
    if workflow["completed"] and consistent:
        category = "MONITORED"
    elif required_failure and consistent:
        category = "CURRENT_CONDITIONAL_FAILURE"
    elif fresh["status"] == "REASSESSMENT" or elapsed_cutoff or advisory_elapsed or workflow["stage"] == "ADVISORY_EXPIRED":
        category = "REASSESSMENT"
    elif not selected or fresh["status"] == "UNKNOWN" or incomplete_required or workflow["stage"] == "UPDATING_LINKED_STATE" or not consistent:
        category = "INCOMPLETE_ASSESSMENT"
    elif workflow["nextRole"] == "SHIPPING_COMPANY":
        category = "COMPANY_ACTION"
    elif workflow["nextRole"]:
        category = "WAITING_OTHER_ROLE"
    else:
        category = "MONITORED"
    if fresh["status"] == "REASSESSMENT" or elapsed_cutoff:
        workflow["nextRole"] = "SHIPPING_COMPANY"
    candidates = [_candidate(p) for p in current if p is not selected and p.get("workflow") in {"COMPUTED", "REVIEWED"}]
    reassessment_codes = {reason.get("code") for reason in _rows(raw_fresh.get("reasons")) if reason.get("status") == "REASSESSMENT" and isinstance(reason.get("code"), str)}
    if not reassessment_codes and fresh["status"] == "REASSESSMENT":
        reassessment_codes = {reason.get("code") for reason in safe_reasons}
    primary_codes = {
        "CURRENT_CONDITIONAL_FAILURE": {"REQUIRED_CARGO_CONNECTION_BLOCKED"},
        "REASSESSMENT": reassessment_codes | {"SCHEDULED_CUTOFF_ELAPSED", "ADVISORY_RESPONSE_WINDOW_ELAPSED", "ADVISORY_EXPIRED"},
        "COMPANY_ACTION": {"PROPOSAL_RETURNED", "COMPANY_REVIEW_PENDING", "COMPANY_APPROVAL_PENDING"},
        "WAITING_OTHER_ROLE": {workflow["stage"]},
        "INCOMPLETE_ASSESSMENT": {"AMBIGUOUS_APPROVED_PLAN", "APPROVAL_CHOICE_UNAVAILABLE", "AMBIGUOUS_CURRENT_COMPARISON",
            "ACTIVE_PROPOSAL_BASIS_INCONSISTENT", "ACTIVE_APPROVED_COMPARISON_UNAVAILABLE", "ACTIVE_PROPOSAL_CURRENT_CALL_UNAVAILABLE",
            "CURRENT_CALL_UNAVAILABLE", "NEEDS_ASSESSMENT", "SNAPSHOT_UPDATING", "LINKED_WORKFLOW_UNAVAILABLE", "REQUIRED_CARGO_ASSESSMENT_INCOMPLETE"}
            | ({reason.get("code") for reason in safe_reasons} if fresh["status"] == "UNKNOWN" else set()),
        "MONITORED": {"SIMULATION_JOURNEY_COMPLETED", "ADVISORY_JOURNEY_COMPLETED", "NO_IDENTIFIED_BLOCK_WITHIN_ASSESSED_SCOPE"},
    }[category]
    reasons.sort(key=lambda reason: reason["code"] not in primary_codes)
    return {"id": "fleet-call:" + vessel["id"] + ":" + (_text(episode.get("id")) or "unavailable"),
            "policyVersion": POLICY_VERSION, "vessel": {"id": vessel["id"], "name": _text(vessel.get("name")) or vessel["id"]},
            "destinationPort": _text(vessel.get("portCode")),
            "episode": {"id": episode["id"], "voyageLegId": _text(episode.get("voyageLegId"))} if _text(episode.get("id")) else None,
            "currentPlan": {"basis": basis, "decisionId": _id(selected) if selected else None, "optionId": option_id,
                            "approvalStatus": "APPROVED" if basis == "APPROVED" else "NOT_APPROVED", "label": _text((option or {}).get("label"))},
            "recommendation": {"decisionId": _id(selected), "optionId": _text(_object(selected.get("recommendation")).get("optionId"))} if selected else None,
            "workflow": {k: v for k, v in workflow.items() if k != "completed" and not k.startswith("_")}, "primaryCategory": category,
            "reasons": reasons, "primaryReason": reasons[0] if reasons else None,
            "freshness": fresh, "deadline": _deadline(selected or {}, cargo, as_of, workflow), "cargo": cargo,
            "navigation": {"kind": "SAVED_COMPARISON" if selected else "CURRENT_INPUTS", "vesselId": vessel["id"],
                           "episodeId": _text(episode.get("id")), "decisionId": _id(selected) if selected else None, "optionId": option_id},
            "candidateComparisons": sorted(candidates, key=lambda p: p["decisionId"]),
            "missingCoverage": sorted(set(missing)), "asOf": as_of.isoformat()}


def project_fleet_triage(world: dict, decisions: list[dict], advisories: list[dict], *, as_of: datetime,
                        freshness: dict[str, dict] | None = None, snapshot_consistent: bool = True) -> dict[str, Any]:
    """Project every owned vessel once; no storage, clock, provider or engine IO."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("Fleet triage as_of must be aware")
    as_of = as_of.astimezone(timezone.utc)
    fleet = _rows(world.get("fleet"))
    by_vessel = {v["id"]: v for v in fleet if _text(v.get("id"))}
    all_decisions = _dedupe(_rows(decisions), "decisionId")
    all_advisories = _dedupe(_rows(advisories), "advisoryId")
    company = [p for p in all_decisions if _object(p.get("actor")).get("role") == "SHIPPING_COMPANY"
               and _object(p.get("actor")).get("organisation") == world.get("organisation")
               and _object(p.get("subject")).get("id") in by_vessel and _id(p)]
    rows = []
    legacy = 0
    for vessel_id, vessel in sorted(by_vessel.items()):
        owned = [p for p in company if _object(p.get("subject")).get("id") == vessel_id]
        current = [p for p in owned if _same_call(p, vessel)]
        legacy_owned = sum(not _object(_basis(p).get("operationalEpisode")).get("id") for p in owned)
        legacy += legacy_owned
        row = _row(world, vessel, current, all_decisions, all_advisories, freshness or {}, as_of, snapshot_consistent)
        if legacy_owned:
            row["reasons"].append(_reason("LEGACY_CALL_IDENTITY_UNAVAILABLE", "Older comparisons lack a complete retained call relationship and are excluded from current-plan selection."))
            row["missingCoverage"].append("legacy comparison call identity")
        rows.append(row)
    def order(row):
        deadline = row["deadline"]
        return (CATEGORY_ORDER.index(row["primaryCategory"]), deadline is None,
                deadline["at"] if deadline else "", row["vessel"]["id"], row["episode"]["id"] if row["episode"] else "")
    rows.sort(key=order)
    counts = {category: sum(r["primaryCategory"] == category for r in rows) for category in CATEGORY_ORDER}
    reason_counts = {}
    for row in rows:
        for code in {reason["code"] for reason in row["reasons"]}:
            reason_counts[code] = reason_counts.get(code, 0) + 1
    return {"policyVersion": POLICY_VERSION, "planSelectionVersion": PLAN_SELECTION_VERSION,
            "asOf": as_of.isoformat(), "categoryOrder": list(CATEGORY_ORDER), "counts": counts,
            "reasonCounts": dict(sorted(reason_counts.items())), "reasonCountsOverlap": True,
            "coverage": {"ownedVoyages": len(by_vessel), "currentCalls": sum(bool(_object(v.get("operationalEpisode")).get("id")) for v in by_vessel.values()),
                         "assessedCurrentPlans": sum(r["currentPlan"]["decisionId"] is not None for r in rows),
                         "retainedComparisons": len(company), "legacyComparisons": legacy, "snapshotConsistent": snapshot_consistent},
            "orderBasis": "Category, known applicable time before unknown time, then stable vessel/call identities. Signed overdue times are retained; this is triage, not a risk or optimizer score.",
            "scope": "All authenticated visitor-owned fleet voyages; one derived row per retained current call or missing-call vessel. No route safety, terminal readiness or real outcome is established.",
            "rows": rows}


__all__ = ["POLICY_VERSION", "PLAN_SELECTION_VERSION", "CATEGORY_ORDER", "project_fleet_triage"]
