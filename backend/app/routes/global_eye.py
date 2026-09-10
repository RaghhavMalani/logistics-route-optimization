"""Global Eye: events, exposure and the calibration behind the probabilities.

The route layer stays thin, as the rest of this API does. It reads the exported
news bundle, hands it to :mod:`src.portwatch_os.global_eye`, and serialises the
result. No intelligence is computed here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.portwatch_os.global_eye.calibration import (
    apply_calibration,
    claims_for,
    fit_calibrator,
)
from src.portwatch_os.global_eye.exposure import (
    TRADE_LANES,
    aggregate_port_risk,
    build_impact,
)
from src.portwatch_os.global_eye.ingest import from_news_bundle
from src.portwatch_os.global_eye.model import CATEGORIES
from src.portwatch_os.ledger.store import get_ledger

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_events():
    """Ingest, calibrate and return the current event register.

    Calibration runs on every request rather than being cached because it is
    cheap (a few hundred resolved rows at most) and because a stale calibration
    is exactly the kind of quiet wrongness this product is built to avoid.
    """
    from backend.app.services import cache_service as cache

    try:
        bundle = cache.get_news_bundle()
    except cache.CacheNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    events, report = from_news_bundle(bundle)
    calibrator = fit_calibrator(get_ledger().event_outcomes(), fitted_at=_now())
    stamped = apply_calibration(events, calibrator)
    return events, report, calibrator, stamped


@router.get("/global-eye/events")
def global_eye_events(
    category: Optional[str] = Query(None, description="Filter to one category."),
    group: Optional[str] = Query(None, description="Filter to one category group."),
    min_severity: float = Query(0.0, ge=0.0, le=1.0),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(60, ge=1, le=200),
) -> Dict[str, Any]:
    events, report, calibrator, stamped = _load_events()

    filtered = [
        event for event in events
        if (category is None or event.category == category)
        and (
            group is None
            or (event.category_spec and event.category_spec.group == group)
        )
        and event.severity >= min_severity
        and event.confidence >= min_confidence
    ]

    return {
        "events": [event.to_dict() for event in filtered[:limit]],
        "total": len(events),
        "returned": min(len(filtered), limit),
        "ingest": report.to_dict(),
        "calibration": {
            "available": calibrator.available,
            "stampedEvents": stamped,
            "resolvedClaims": calibrator.global_count,
            "globalBaseRate": calibrator.global_base_rate,
            "note": (
                "Probabilities are calibrated against resolved outcomes. Where too few "
                "have resolved, no probability is shown and severity with confidence is "
                "reported instead."
            ),
        },
        "categories": [
            {
                "key": spec.key, "label": spec.label, "group": spec.group,
                "actsOn": spec.acts_on, "description": spec.description,
                "count": sum(1 for e in events if e.category == spec.key),
            }
            for spec in CATEGORIES.values()
        ],
    }


@router.get("/global-eye/events/{event_id}")
def global_eye_event(event_id: str, company_id: Optional[str] = None) -> Dict[str, Any]:
    events, _, _, _ = _load_events()
    event = next((e for e in events if e.event_id == event_id), None)
    if event is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Event {event_id} is not in the current register. Events age out of "
                "the feed; its recorded outcome remains in the ledger."
            ),
        )
    voyages = _company_voyages(company_id)
    return build_impact(event, voyages).to_dict()


@router.get("/global-eye/exposure")
def global_eye_exposure(
    company_id: Optional[str] = None,
    port_code: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """The whole exposure picture: every live event traced through the graph."""
    events, report, calibrator, _ = _load_events()
    voyages = _company_voyages(company_id)

    impacts = [build_impact(event, voyages) for event in events[:limit]]
    impacts = [i for i in impacts if i.lanes or i.ports]
    port_risk = aggregate_port_risk(impacts)

    if port_code:
        code = port_code.upper()
        impacts = [
            i for i in impacts if any(p.port_code == code for p in i.ports)
        ]
        port_risk = {k: v for k, v in port_risk.items() if k == code}

    return {
        "impacts": [i.to_dict() for i in impacts],
        "portRisk": port_risk,
        "lanes": [
            {
                "code": lane.code, "name": lane.name,
                "chokepoints": list(lane.chokepoints),
                "indiaPorts": list(lane.india_ports),
                "primaryNm": lane.primary_nm,
                "alternative": lane.alternative,
                "alternativeNm": lane.alternative_nm,
                "detourNm": lane.detour_nm,
                "description": lane.description,
            }
            for lane in TRADE_LANES.values()
        ],
        "ingest": report.to_dict(),
        "calibrationAvailable": calibrator.available,
    }


@router.get("/global-eye/calibration")
def global_eye_calibration() -> Dict[str, Any]:
    """How Global Eye's probabilities were fitted, and how they have scored."""
    from src.portwatch_os.learning.outcome_agent import OutcomeAgent

    ledger = get_ledger()
    calibrator = fit_calibrator(ledger.event_outcomes(), fitted_at=_now())
    agent = OutcomeAgent(ledger)
    return {
        "calibrator": calibrator.to_dict(),
        "scores": agent.score_events(),
        "openClaims": len(ledger.event_outcomes(status="open")),
        "resolvedClaims": len(ledger.event_outcomes(status="resolved")),
    }


@router.post("/global-eye/claims")
def record_claims(horizon_hours: Optional[float] = None) -> Dict[str, Any]:
    """Commit a falsifiable outcome claim for every current event.

    This is what makes Global Eye scorable at all: the claim and its horizon go
    into the ledger *before* the world answers. Called by the pipeline; exposed
    here so a demo can show the loop closing without a full pipeline run.
    """
    events, _, _, _ = _load_events()
    ledger = get_ledger()
    issued_at = _now()
    written = 0
    for record in claims_for(events, issued_at=issued_at, resolve_by_hours=horizon_hours):
        try:
            ledger.record_event_outcome(record)
            written += 1
        except Exception:  # noqa: BLE001 - a resolved claim is not rewritten
            continue
    return {
        "issuedAt": issued_at,
        "eventsConsidered": len(events),
        "claimsWritten": written,
        "note": (
            "Each claim carries a horizon. The outcome agent scores it once that "
            "horizon elapses, whether or not anything was observed -- an unconfirmed "
            "claim past its horizon is a measured non-event, not a missing row."
        ),
    }


def _company_voyages(company_id: Optional[str]):
    from backend.app.routes.company import resolve_company

    profile = resolve_company(company_id)
    return profile.voyages() if profile else []
