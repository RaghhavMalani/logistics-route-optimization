"""The learning surface: outcomes, reliability, attribution and policies.

Everything the admin learning dashboard renders. All of it is read out of the
ledger; nothing here computes an intelligence figure of its own.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from src.portwatch_os.global_eye.calibration import fit_calibrator
from src.portwatch_os.ledger.schema import (
    APPROVED,
    CANDIDATE,
    EVALUATING,
    RESOLVED,
    utc_now,
)
from src.portwatch_os.ledger.store import LedgerError, get_ledger
from src.portwatch_os.learning.attribution import attribute, rank_misses, verify_decomposition
from src.portwatch_os.learning.outcome_agent import OutcomeAgent
from src.portwatch_os.twin.promotion import active_policy

router = APIRouter()


@router.get("/learning/summary")
def learning_summary() -> Dict[str, Any]:
    """The dashboard header: what the ledger holds and how it is scoring."""
    ledger = get_ledger()
    agent = OutcomeAgent(ledger)
    counts = ledger.counts()
    scored = agent.score_history()
    active = active_policy(ledger)

    return {
        "counts": counts,
        "overall": scored["overall"].to_dict(),
        "events": agent.score_events(),
        "decisions": agent.score_decisions(),
        "activePolicyId": active.policy_id if active else None,
        "reliabilityRows": len(ledger.reliability()),
        "ranAt": utc_now(),
        "note": (
            "Every figure here is computed from resolved ledger rows. Where nothing "
            "has resolved, the corresponding section reports unavailable rather than "
            "a default."
        ),
    }


@router.get("/learning/outcomes")
def learning_outcomes(
    domain: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
) -> Dict[str, Any]:
    """Scored history, sliced the way the dashboard shows it."""
    ledger = get_ledger()
    agent = OutcomeAgent(ledger)
    rows = ledger.predictions(status=RESOLVED, domain=domain, model=model, limit=limit)
    scored = agent.score_history(rows)
    return {
        "overall": scored["overall"].to_dict(),
        "byDomain": [s.to_dict() for s in scored["byDomain"]],
        "byModel": [s.to_dict() for s in scored["byModel"]],
        "byHorizon": [s.to_dict() for s in scored["byHorizon"]],
        "byPort": [s.to_dict() for s in scored["byPort"]],
        "resolved": len(rows),
        "open": len(ledger.predictions(status="open", limit=1000)),
    }


@router.get("/learning/reliability")
def learning_reliability(contributor: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Learned reliability weights, and what moved them."""
    ledger = get_ledger()
    rows = ledger.reliability(contributor=contributor)
    changed = [
        r for r in rows
        if r.previous_weight is not None and abs(r.weight - r.previous_weight) > 1e-4
    ]
    return {
        "weights": [
            {
                "contributor": r.contributor,
                "context": r.context_key,
                "dimensions": r.dimensions,
                "weight": r.weight,
                "previousWeight": r.previous_weight,
                "delta": (
                    None if r.previous_weight is None
                    else round(r.weight - r.previous_weight, 4)
                ),
                "samples": r.sample_count,
                "meanAbsoluteError": r.mean_absolute_error,
                "bias": r.bias,
                "calibrationError": r.calibration_error,
                "updatedAt": r.updated_at,
                "fittedFrom": r.fitted_from,
                "fittedTo": r.fitted_to,
                "notes": r.notes,
            }
            for r in rows
        ],
        "changedCount": len(changed),
        "contributors": sorted({r.contributor for r in rows}),
        "method": (
            "Fitted from resolved rows only, behind an explicit leakage barrier, and "
            "shrunk toward 1.0 in proportion to how little evidence a context has. "
            "Weights move at most 0.12 per update and are clamped to 0.35-1.60."
        ),
    }


@router.get("/learning/misses")
def learning_misses(limit: int = Query(10, ge=1, le=50)) -> Dict[str, Any]:
    """"Why was PortWatch wrong?" -- the largest misses, decomposed.

    Attribution is only reported where it was actually computed. A prediction
    recorded without per-contributor signals returns ``available: false`` and the
    reason, rather than a plausible bar chart.
    """
    ledger = get_ledger()
    resolved = ledger.predictions(status=RESOLVED, limit=1000)
    reliability = ledger.reliability()
    by_contributor: Dict[str, List[Dict[str, Any]]] = {}
    for row in reliability:
        if row.previous_weight is None or abs(row.weight - row.previous_weight) < 1e-4:
            continue
        by_contributor.setdefault(row.contributor, []).append({
            "contributor": row.contributor,
            "context": row.context_key,
            "from": round(row.previous_weight, 4),
            "to": round(row.weight, 4),
            "delta": round(row.weight - row.previous_weight, 4),
            "samples": row.sample_count,
        })

    misses = rank_misses(resolved, limit=limit, reliability_changes=by_contributor)
    return {
        "misses": [m.to_dict() for m in misses],
        "resolvedCount": len(resolved),
        "attributionAvailable": sum(1 for m in misses if m.attribution.available),
        "method": (
            "The error of a weighted blend decomposes exactly: the observation minus "
            "the prediction equals the sum over contributors of weight times that "
            "contributor's own residual. Shares are that identity, not an estimate. "
            "Where a prediction carried no per-contributor signals, no attribution is "
            "produced."
        ),
    }


@router.get("/learning/predictions/{prediction_id}")
def learning_prediction(prediction_id: str) -> Dict[str, Any]:
    ledger = get_ledger()
    record = ledger.get_prediction(prediction_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no prediction {prediction_id}")
    decomposition = attribute(record)
    return {
        "prediction": {
            "predictionId": record.prediction_id,
            "domain": record.domain,
            "kind": record.kind,
            "target": record.target,
            "subject": record.subject,
            "model": record.model,
            "modelVersion": record.model_version,
            "issuedAt": record.issued_at,
            "validAt": record.valid_at,
            "context": record.context.to_dict(),
            "predicted": record.predicted_value,
            "low": record.predicted_low,
            "high": record.predicted_high,
            "confidence": record.confidence,
            "observed": record.observed_value,
            "observedAt": record.observed_at,
            "status": record.status,
            "error": record.error,
            "withinInterval": record.within_interval,
        },
        "attribution": decomposition.to_dict(),
        "decompositionCloses": verify_decomposition(decomposition),
    }


@router.get("/learning/policies")
def learning_policies() -> Dict[str, Any]:
    """Learned policies and their promotion state."""
    ledger = get_ledger()
    active = active_policy(ledger)
    return {
        "policies": [
            {
                "policyId": p.policy_id, "name": p.name, "family": p.family,
                "version": p.version, "state": p.state, "environment": p.environment,
                "training": p.training, "evaluation": p.evaluation,
                "safetyChecks": p.safety_checks, "approvedBy": p.approved_by,
                "approvedAt": p.approved_at, "rejectionReason": p.rejection_reason,
                "createdAt": p.created_at, "updatedAt": p.updated_at,
                "notes": p.notes,
            }
            for p in ledger.policies()
        ],
        "activePolicyId": active.policy_id if active else None,
        "states": {
            "candidate": len(ledger.policies(state=CANDIDATE)),
            "evaluating": len(ledger.policies(state=EVALUATING)),
            "approved": len(ledger.policies(state=APPROVED)),
        },
        "note": (
            "No learned policy is approved, so operational recommendations use the "
            "hand-written optimiser. A candidate must beat both the incumbent rule and "
            "the best hand-written optimiser, take no infeasible action, and be "
            "approved by a named person."
            if active is None else
            f"{active.name} is approved for use in recommendations, approved by "
            f"{active.approved_by} on {active.approved_at}."
        ),
    }


@router.post("/learning/policies/{policy_id}/approve")
def approve_policy(
    policy_id: str,
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """Promote an evaluated policy. Refused unless every gate passed.

    The approver is required and is recorded. There is no automated path to this
    endpoint's effect: the ledger refuses an APPROVED transition whose safety
    checks carry a false, and refuses one with no named approver.
    """
    approver = str(payload.get("approver") or "").strip()
    if not approver:
        raise HTTPException(
            status_code=400,
            detail="A named human approver is required to promote a policy.",
        )
    ledger = get_ledger()
    record = ledger.get_policy(policy_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no policy {policy_id}")
    try:
        updated = ledger.transition_policy(
            policy_id, APPROVED, actor=approver,
            reason=payload.get("reason"),
        )
    except LedgerError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"policyId": updated.policy_id, "state": updated.state,
            "approvedBy": updated.approved_by, "approvedAt": updated.approved_at}


@router.get("/learning/calibration")
def learning_calibration() -> Dict[str, Any]:
    """Event-probability calibration, and how it was fitted."""
    ledger = get_ledger()
    calibrator = fit_calibrator(
        ledger.event_outcomes(),
        fitted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return {
        "calibrator": calibrator.to_dict(),
        "scores": OutcomeAgent(ledger).score_events(),
    }


@router.post("/learning/backfill")
def backfill(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """Load the pipeline's walk-forward history into the ledger.

    The pipeline does this at the end of a run. Exposed here so a deployment
    whose ledger is empty can be filled without a full pipeline pass, and so the
    demo can show the loop closing on screen.
    """
    from src.portwatch_os.learning.backfill import backfill_forecasts

    ledger = get_ledger()
    report = backfill_forecasts(ledger, limit=int(payload.get("limit") or 4000))
    outcome = None
    if report.resolved:
        outcome = OutcomeAgent(ledger).run()
    return {
        "backfill": report.to_dict(),
        "outcome": outcome.to_dict() if outcome else None,
    }


@router.post("/learning/run")
def run_outcome_pass(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """Run the outcome agent: resolve, score, attribute, recalibrate.

    Exposed so the demo can close the loop on screen. In a deployment this runs
    on the pipeline's schedule; the two paths call the same agent.
    """
    ledger = get_ledger()
    agent = OutcomeAgent(ledger)
    run = agent.run(
        now=payload.get("now"),
        miss_limit=int(payload.get("missLimit") or 10),
    )
    return run.to_dict()
