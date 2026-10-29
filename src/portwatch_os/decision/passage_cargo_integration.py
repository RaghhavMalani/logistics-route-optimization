"""Attach one declared shipment to the existing frozen passage workflow.

The visitor world stores only the current declaration identity. Assessments,
approvals and successors remain in the existing decision ledger.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json

from .model import ConstraintResult, REJECTED


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def extend_with_cargo(problem, raw, *, at):
    from .passage_cargo import validate_commitment, evaluate_commitment
    env = problem.evidence["currentEnvironment"]
    if not env.get("passageComparison"):
        raise ValueError("A supported declared passage is required for a cargo commitment; arrival-only fallback cannot establish cargo timing")
    commitment = validate_commitment(raw, voyage_id=problem.subject_id, port_code=env["portCode"], at=at)
    results = []
    summaries = {row["optionId"]: row for row in env["passageComparison"]["options"]}
    reference = datetime.fromisoformat(env["passageComparison"]["referenceAt"])
    for option in problem.options:
        result = evaluate_commitment(commitment,
            clear_approach_at=option.evaluation.derived.get("approachClearAt"),
            option_id=option.option_id,
            source_passage_id=env["passageComparison"]["inputVersion"])
        option.evaluation.derived["cargoAssessment"] = deepcopy(result)
        option.assumptions.append({"kind": "DECLARED_FICTIONAL_CARGO_COMMITMENT", "declaration": deepcopy(commitment)})
        required = commitment["mustMeet"]
        if required:
            passed = result["status"] == "COMPATIBLE_UNDER_ASSUMPTIONS"
            detail = "; ".join(result.get("reasons") or result.get("missing") or [result["status"]])
            option.constraints.append(ConstraintResult("cargo_commitment", "Declared must-meet cargo connection",
                passed, True, detail, "currentEnvironment.cargoCommitment"))
            if not passed:
                option.status = REJECTED
                summary = summaries[option.option_id]
                summary["status"] = REJECTED
                summary["reason"] = "; ".join(filter(None, [summary.get("reason"), "Required cargo connection: " + detail]))
        for field, kind, label in (("startAt", "cargo_start", "Declared conditional cargo transfer start"),
                                    ("readinessAt", "cargo_ready", "Modeled handling complete"),
                                    ("cutoffAt", "cargo_cutoff", "Declared booked loading cutoff"),
                                    ("departureAt", "cargo_departure", "Declared onward sailing; no reservation")):
            if result.get(field):
                when = datetime.fromisoformat(result[field].replace("Z", "+00:00"))
                option.timeline.append({"at": when.isoformat(), "hours": (when-reference).total_seconds()/3600,
                    "subject": commitment["shipment"]["shipmentId"], "kind": kind, "label": label})
        results.append(result)
    comparison = {"version": "passage-cargo-comparison-v1", "referenceAt": commitment["conversionReferenceAt"],
        "inputVersion": "passage-cargo-" + _hash({"declaration": commitment,
            "passageInputVersion": env["passageComparison"]["inputVersion"]}), "options": results,
        "meaning": "Conditional cargo connection under declared demonstration inputs. No berth access, booking, customs release, final delivery or actual execution is established."}
    env.update(evidenceVersion="current-weather-passage-cargo-v4", cargoCommitment=commitment, cargoComparison=comparison)
    env.pop("evidenceId", None)
    env["evidenceId"] = _hash(env)
    problem.decision_id = "dec-arrival-" + _hash({"evidence": env["evidenceId"], "actor": problem.actor.to_dict(), "at": at.isoformat()})[:20]
    problem.world_state_id = problem.world_state_id.split(":")[0] + ":" + env["evidenceId"]
    for option in problem.options:
        option.provenance["evidenceId"] = env["evidenceId"]
    # No cargo objective or scoring weight is added. Only an explicitly hard
    # commitment changes feasibility before the existing engine ranks options.
    problem.notes.append(comparison["meaning"])
    return problem


def declaration_identity(commitment):
    # Conversion is per comparison; it cannot make an unchanged shipment look
    # edited merely because weather was refreshed at a later wall-clock time.
    return _hash({k: v for k, v in commitment.items() if k not in ("conversionReferenceAt", "inputVersion")})


def bind_declaration(problem, *, predecessor_id=None, persist=True):
    """Validate and persist a fictional shipment inside its existing visitor."""
    from fastapi import HTTPException
    from src.portwatch_os.sandbox import current_sandbox
    scoped = current_sandbox.get()
    env = problem.evidence.get("currentEnvironment") or {}
    declaration = env.get("cargoCommitment")
    if declaration is None:
        return
    if scoped is None or problem.actor.role != "SHIPPING_COMPANY":
        raise HTTPException(403, "Company declares fictional cargo in its own visitor world")
    shipment_id = declaration["shipment"]["shipmentId"]
    episode_id = (env.get("operationalEpisode") or {}).get("id")
    record = {"voyageId": problem.subject_id, "portCode": env["portCode"], "episodeId": episode_id,
        "inputVersion": declaration_identity(declaration), "declaration": deepcopy(declaration),
        "comparisonId": problem.decision_id}
    def update(world):
        records = world.setdefault("cargoCommitments", {})
        previous = records.get(shipment_id)
        if previous:
            if any(previous.get(k) != record[k] for k in ("voyageId", "portCode", "episodeId")):
                raise HTTPException(409, "This fictional shipment belongs to another voyage or call; explicitly create a different shipment")
            if previous["inputVersion"] != record["inputVersion"] and predecessor_id != previous["comparisonId"]:
                raise HTTPException(409, "Changed shipment or connection inputs require a linked successor of the current cargo comparison")
        if persist:
            records[shipment_id] = record
    if not persist:
        update(deepcopy(scoped.world))
        return
    # The store applies updates under its existing visitor lock and atomic save.
    scoped.save_world(update)
    scoped.world.setdefault("cargoCommitments", {})[shipment_id] = record


def require_cargo_current(env, scoped):
    declaration = env.get("cargoCommitment")
    if not declaration:
        return None
    record = scoped.world.get("cargoCommitments", {}).get(declaration["shipment"]["shipmentId"])
    if not record or record.get("inputVersion") != declaration_identity(declaration):
        return "The consumed shipment or connection declaration has changed."
    return None
