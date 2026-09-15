"""The financial twin over HTTP: the cost basis, its coverage, the public
tariffs it holds with their citations, scenario assumptions and FX.

There is no route that returns a cost without its basis. ``/finance/basis``
says, primitive by primitive, whether a rate exists, where it came from and
whether it is an assumption; ``/finance/tariffs`` serves the public schedules
with the document, page, section and verbatim text each rate was read from,
and the reuse finding for the site it came from. An operator's assumption is
added with their name on it and labelled ASSUMPTION on every figure it
touches. FX is an explicit observation or it is absent -- and absent means
cross-currency totals are refused, not approximated.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query

from backend.app.routes.world import _at
from src.portwatch_os.decision.engine import get_engine
from src.portwatch_os.finance.basis import PRIMITIVES, assumption as cost_assumption, observation as cost_observation
from src.portwatch_os.finance.money import FxObservation
from src.portwatch_os.finance.tariffs import investigation, load_public_tariffs

router = APIRouter()


@router.get("/finance/basis")
def finance_basis(
    at: Optional[str] = Query(None),
    scope: Optional[str] = Query(None, description="A port locode, vessel class or company id."),
) -> Dict[str, Any]:
    """Every primitive and whether it can be priced right now."""
    engine = get_engine()
    moment = _at(at)
    body = engine.basis.to_dict(at=moment)
    body["coverage"] = engine.basis.coverage(at=moment, scope=scope)
    body["scope"] = scope
    body["currency"] = engine.currency
    body["fx"] = engine.fx.to_dict()
    body["investigated"] = investigation()
    return body


@router.get("/finance/tariffs")
def finance_tariffs() -> Dict[str, Any]:
    """The public schedules, transcribed and cited. Lapsed ones say so."""
    schedules = [s.to_dict() for s in load_public_tariffs()]
    return {
        "schedules": schedules,
        "investigated": investigation(),
        "label": "PUBLIC_TARIFF",
        "note": (
            "What each port publishes, not what any carrier pays under contract. A schedule outside "
            "its validity is held for the record and never used to price."
        ),
    }


@router.post("/finance/assumptions")
def add_assumption(
    payload: Dict[str, Any] = Body(...),
    actor: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
) -> Dict[str, Any]:
    """An operator's scenario rate. Named, dated, labelled ASSUMPTION."""
    if not actor:
        raise HTTPException(status_code=401, detail="an assumption must be entered by a named actor (X-PortWatch-Actor)")
    primitive = str(payload.get("primitive") or "")
    if primitive not in PRIMITIVES:
        raise HTTPException(status_code=400, detail=f"unknown primitive {primitive}; known: {', '.join(PRIMITIVES)}")
    try:
        rate = cost_assumption(
            primitive, float(payload.get("value")), str(payload.get("currency") or "USD"),
            entered_by=actor, purpose=str(payload.get("purpose") or "scenario"),
            scope=str(payload.get("scope") or "*"), note=str(payload.get("note") or ""),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    engine = get_engine()
    engine.basis.add(rate)
    # Journalled before it is answered: an assumption that priced a decision
    # must still exist after a restart, with who entered it.
    journal = getattr(engine, "assumption_journal", None)
    if journal is not None:
        try:
            journal.append(rate)
        except OSError as exc:
            raise HTTPException(status_code=503, detail=f"the assumption could not be journalled: {exc}")
    return {"added": rate.to_dict(), "label": "ASSUMPTION", "journalled": journal is not None,
            "assumptions": [r.to_dict() for r in engine.basis.rates if r.is_assumption]}


@router.post("/finance/observations")
def add_observation(
    payload: Dict[str, Any] = Body(...),
    actor: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
) -> Dict[str, Any]:
    """A market observation -- a bunker price, say -- with its source and instant."""
    primitive = str(payload.get("primitive") or "")
    if primitive not in PRIMITIVES:
        raise HTTPException(status_code=400, detail=f"unknown primitive {primitive}")
    source = str(payload.get("source") or "").strip()
    observed_at = str(payload.get("observedAt") or "").strip()
    if not source or not observed_at:
        raise HTTPException(status_code=400, detail="a market observation needs a source and an observedAt instant")
    try:
        rate = cost_observation(
            primitive, float(payload.get("value")), str(payload.get("currency") or "USD"),
            source=source, observed_at=observed_at, scope=str(payload.get("scope") or "*"),
            provenance={"enteredBy": actor, **(payload.get("provenance") or {})},
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    get_engine().basis.add(rate)
    return {"added": rate.to_dict(), "label": "MARKET_DATA"}


@router.post("/finance/assumptions/clear")
def clear_assumptions(actor: Optional[str] = Header(None, alias="X-PortWatch-Actor")) -> Dict[str, Any]:
    if not actor:
        raise HTTPException(status_code=401, detail="name the actor clearing the assumptions")
    engine = get_engine()
    kept = [r for r in engine.basis.rates if not r.is_assumption]
    engine.basis._rates = kept  # noqa: SLF001 - the basis is the engine's own
    journal = getattr(engine, "assumption_journal", None)
    if journal is not None:
        try:
            journal.clear(actor)
        except OSError as exc:
            raise HTTPException(status_code=503, detail=f"the clear could not be journalled: {exc}")
    return {"remaining": len(kept), "clearedBy": actor, "journalled": journal is not None}


@router.post("/finance/fx")
def add_fx(
    payload: Dict[str, Any] = Body(...),
    actor: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
) -> Dict[str, Any]:
    """An explicit exchange observation. The only way a cross-currency total exists."""
    try:
        observation = FxObservation(
            base=str(payload.get("base") or ""), quote=str(payload.get("quote") or ""),
            rate=float(payload.get("rate")), observed_at=str(payload.get("observedAt") or ""),
            source=str(payload.get("source") or ""),
            source_type=str(payload.get("sourceType") or "MARKET_DATA"),
            provenance={"enteredBy": actor, **(payload.get("provenance") or {})},
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    engine = get_engine()
    engine.fx.add(observation)
    return {"added": observation.to_dict(), "fx": engine.fx.to_dict()}


__all__ = ["router"]
