"""Port-to-vessel advisories.

The one place in this API where a human's identity actually matters. Every
mutating route builds a :class:`~src.portwatch_os.advisories.store.Principal`
from the request's declared identity headers, and the store refuses anything
that principal is not entitled to do.

**On the identity source.** In this deployment the principal comes from headers
the terminal sets from its authenticated session. That is honest about what it
is: the demo auth adapter verifies nothing, and this API says so in
``/advisories/policy`` rather than implying a security boundary it does not have.
The seam is the important part -- a production deployment replaces
:func:`principal_from_request` with one that reads a verified token, and no other
line changes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query

from src.portwatch_os.advisories.model import (
    ACCEPTED,
    ACKNOWLEDGED,
    ADVISORY_KINDS,
    ADVISORY_STATES,
    DECLINED,
    ISSUED,
    ISSUER,
    QUERIED,
    RECIPIENT,
    TRANSITIONS,
    UNDER_REVIEW,
    Advisory,
    AdvisoryError,
    allowed_transitions,
)
from src.portwatch_os.advisories.store import (
    AuthorisationError,
    Principal,
    get_advisory_store,
)
from src.portwatch_os.ledger.schema import ACTION_PENDING, DecisionRecord, utc_now
from src.portwatch_os.ledger.store import get_ledger
from src.utils import port_registry

router = APIRouter()


def principal_from_request(
    actor: Optional[str],
    role: Optional[str],
    port_code: Optional[str],
    organisation: Optional[str],
    vessel_ids: Optional[str],
    is_admin: bool = False,
) -> Principal:
    """Build the acting principal. The seam a real token verifier replaces."""
    if not actor:
        raise HTTPException(
            status_code=401,
            detail=(
                "Every advisory action must name its actor. Send X-PortWatch-Actor "
                "with the signed-in operator's name."
            ),
        )
    normalised = (role or "").lower()
    if normalised in ("issuer", "port_authority", "port_operator"):
        resolved = ISSUER
    elif normalised in ("recipient", "shipping_company", "vessel_operator"):
        resolved = RECIPIENT
    else:
        raise HTTPException(
            status_code=403,
            detail=(
                f"'{role}' is not a role that may act on advisories. A port authority "
                "acts as the issuer; a company or vessel operator as the recipient."
            ),
        )
    try:
        return Principal(
            actor=actor, role=resolved, port_code=port_code,
            organisation=organisation,
            vessel_ids=[v.strip() for v in (vessel_ids or "").split(",") if v.strip()],
            is_admin=is_admin,
        )
    except AuthorisationError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/advisories/policy")
def advisory_policy() -> Dict[str, Any]:
    """What the workflow permits, and what this deployment actually verifies."""
    return {
        "states": list(ADVISORY_STATES),
        "kinds": [
            {"key": k.key, "label": k.label, "requiredField": k.required_field,
             "unit": k.unit, "description": k.description}
            for k in ADVISORY_KINDS.values()
        ],
        "transitions": [
            {"from": t.source, "to": t.target, "actorRole": t.actor_role,
             "label": t.label, "requiresReason": t.requires_reason}
            for t in TRANSITIONS
        ],
        "rules": [
            "A draft is not visible to the recipient until a named controller issues it.",
            "Only the issuing port authority may issue, withdraw or close an advisory.",
            "Only the recipient may accept, query or decline it.",
            "Expiry is the only system-driven transition and takes no caller identity.",
            "Declining is a normal terminal state. PortWatch does not control vessel "
            "navigation and an advisory is never an instruction.",
        ],
        "identity": {
            "source": "request headers set by the terminal from its session",
            "verified": False,
            "note": (
                "This deployment's identity is asserted by the client, not verified by "
                "a token. Replace principal_from_request with a verifier before this "
                "is used for anything real."
            ),
        },
    }


@router.get("/advisories")
def list_advisories(
    state: Optional[str] = Query(None),
    port_code: Optional[str] = Query(None),
    vessel_id: Optional[str] = Query(None),
    actor: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
    admin: Optional[str] = Header(None, alias="X-PortWatch-Admin"),
) -> Dict[str, Any]:
    acting = principal_from_request(
        actor, role, header_port, organisation, vessel_ids,
        is_admin=(admin or "").lower() in ("1", "true", "yes"),
    )
    store = get_advisory_store()
    store.expire_due()
    rows = store.visible_to(
        acting, state=state, port_code=port_code, vessel_id=vessel_id
    )
    return {
        "advisories": [
            a.to_dict(for_recipient=acting.role == RECIPIENT) for a in rows
        ],
        "counts": store.counts(),
        "principal": acting.to_dict(),
    }


@router.get("/advisories/{advisory_id}")
def get_advisory(
    advisory_id: str,
    actor: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
    admin: Optional[str] = Header(None, alias="X-PortWatch-Admin"),
) -> Dict[str, Any]:
    acting = principal_from_request(
        actor, role, header_port, organisation, vessel_ids,
        is_admin=(admin or "").lower() in ("1", "true", "yes"),
    )
    store = get_advisory_store()
    try:
        advisory = store.require(advisory_id)
    except AdvisoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not acting.may_see(advisory):
        # 404 rather than 403: an unauthorised reader should not learn that an
        # advisory exists, only that they cannot address it.
        raise HTTPException(status_code=404, detail=f"no advisory {advisory_id}")
    return advisory.to_dict(for_recipient=acting.role == RECIPIENT)


@router.post("/advisories")
def create_advisory(
    payload: Dict[str, Any] = Body(...),
    actor: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    admin: Optional[str] = Header(None, alias="X-PortWatch-Admin"),
) -> Dict[str, Any]:
    """Raise a draft advisory. Always lands in DRAFT, never visible to the vessel."""
    acting = principal_from_request(
        actor, role, header_port, organisation, None,
        is_admin=(admin or "").lower() in ("1", "true", "yes"),
    )
    if acting.role != ISSUER:
        raise HTTPException(
            status_code=403,
            detail="Only a port authority may raise an advisory.",
        )

    port_code = str(payload.get("portCode") or header_port or "")
    record = port_registry.resolve(port_code)
    created = utc_now()
    vessel_id = str(payload.get("recipientVesselId") or "")

    advisory = Advisory(
        advisory_id=Advisory.make_id(port_code, vessel_id, str(payload.get("kind")), created),
        kind=str(payload.get("kind") or ""),
        port_code=(record.locode if record else port_code),
        issuer=acting.actor,
        issuer_organisation=str(
            payload.get("issuerOrganisation")
            or (record.authority if record else port_code)
        ),
        recipient_vessel_id=vessel_id,
        recipient_vessel_name=str(payload.get("recipientVesselName") or vessel_id),
        recipient_organisation=str(payload.get("recipientOrganisation") or "Unknown operator"),
        created_at=created,
        recommendation=dict(payload.get("recommendation") or {}),
        reason=str(payload.get("reason") or ""),
        model_confidence=payload.get("modelConfidence"),
        prediction_ids=list(payload.get("predictionIds") or []),
        evidence=dict(payload.get("evidence") or {}),
        critic_verdict=payload.get("criticVerdict"),
        critic_reasons=list(payload.get("criticReasons") or []),
        valid_until=payload.get("validUntil") or _default_validity(),
    )

    try:
        get_advisory_store().create(advisory, principal=acting)
    except (AdvisoryError, AuthorisationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Record the recommendation in the decision ledger so the outcome agent can
    # later score whether it was taken and what it was worth.
    decision = DecisionRecord(
        decision_id=DecisionRecord.make_id(
            "arrival_advisory", advisory.advisory_id, created, acting.actor
        ),
        kind=f"advisory:{advisory.kind}",
        subject=advisory.recipient_vessel_id,
        issued_at=created,
        issuer=acting.actor,
        recommendation=advisory.recommendation,
        reason=advisory.reason,
        prediction_ids=advisory.prediction_ids,
        confidence=advisory.model_confidence,
        expected_impact={
            k: float(v) for k, v in advisory.evidence.items()
            if isinstance(v, (int, float))
        },
        critic_verdict=advisory.critic_verdict,
        critic_reasons=advisory.critic_reasons,
        approval_state="draft",
        action_state=ACTION_PENDING,
    )
    get_ledger().record_decision(decision)
    advisory.decision_id = decision.decision_id
    get_advisory_store()._write(advisory)  # noqa: SLF001 - same module family

    return advisory.to_dict()


@router.post("/advisories/generate")
def generate_advisories(
    payload: Dict[str, Any] = Body(default={}),
    actor: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    admin: Optional[str] = Header(None, alias="X-PortWatch-Admin"),
) -> Dict[str, Any]:
    """Draft advisories from the decision engine, for a controller to review.

    This is the *left* end of the human-in-the-loop workflow: the twin is run
    forward, the vessels that would wait longest are identified, the Critic
    reviews each recommendation, and a draft is raised. Nothing here is visible
    to a vessel, and nothing here can issue.

    The arithmetic comes from the simulator. A recommendation whose recommended
    arrival shift the Critic rejects is not drafted at all -- it is returned in
    ``refused`` with the reason, because a controller should be able to see what
    the engine considered and discarded.
    """
    acting = principal_from_request(
        actor, role, header_port, None, None,
        is_admin=(admin or "").lower() in ("1", "true", "yes"),
    )
    if acting.role != ISSUER:
        raise HTTPException(
            status_code=403, detail="Only a port authority may raise advisories."
        )

    port_code = str(payload.get("portCode") or header_port or "")
    if not port_code:
        raise HTTPException(status_code=400, detail="A port is required.")

    from backend.app.routes.company import resolve_company
    from backend.app.routes.port_twin import build_state_for
    from src.portwatch_os.agents.critic import Critic, Recommendation
    from src.portwatch_os.twin.policies import GreedyPolicy
    from src.portwatch_os.twin.simulation import SimulationConfig, simulate

    state = build_state_for(port_code)
    result = simulate(
        state, GreedyPolicy(),
        SimulationConfig(horizon_hours=24.0, record_trace=False),
        snapshot_hours=(),
    )
    final = result.final_state
    record = port_registry.resolve(port_code)
    profile = resolve_company(None)
    fleet = profile.vessels if profile else []

    # The calls that actually waited. Anything under an hour is not worth an
    # advisory: the schedule buffer absorbs it and a controller's attention is
    # the scarce resource here.
    waited = sorted(
        (c for c in final.calls if c.wait_hours >= 1.0),
        key=lambda c: -c.wait_hours,
    )[: int(payload.get("limit") or 4)]

    critic = Critic()
    created: List[Dict[str, Any]] = []
    refused: List[Dict[str, Any]] = []
    store = get_advisory_store()

    for index, call in enumerate(waited):
        # Half the observed wait, capped at the advisory envelope. Arriving
        # later than the berth frees buys nothing, so the recommendation never
        # exceeds the wait it is removing.
        shift = round(min(call.wait_hours * 0.5, 12.0), 1)
        vessel = fleet[index % len(fleet)] if fleet else None

        recommendation = Recommendation(
            kind="arrival_advisory",
            subject=vessel.vessel_id if vessel else call.vessel_id,
            action="restagger_arrival",
            values={
                "arrivalShiftHours": shift,
                "simulatedWaitHours": round(call.wait_hours, 1),
            },
            expected_impact={"waitHoursSaved": shift},
            confidence=0.72,
            evidence_tools=["portwatch.port_twin.simulate"],
            evidence={
                "violations": result.violations,
                "rejectedActions": result.rejected_actions,
            },
            reason=(
                f"The twin simulates {call.wait_hours:.1f} h at anchor for this call "
                f"under the greedy berth policy."
            ),
        )
        verdict = critic.review(recommendation)
        if verdict.verdict == "REJECTED":
            refused.append({
                "vesselId": recommendation.subject,
                "reasons": verdict.reasons,
                "checks": verdict.to_dict()["failedChecks"],
            })
            continue

        created_at = utc_now()
        advisory = Advisory(
            advisory_id=Advisory.make_id(
                port_code,
                vessel.vessel_id if vessel else call.vessel_id,
                "arrival_window",
                created_at,
            ),
            kind="arrival_window",
            port_code=(record.locode if record else port_code),
            issuer="PortWatch decision engine",
            issuer_organisation=(record.authority if record else port_code),
            recipient_vessel_id=vessel.vessel_id if vessel else call.vessel_id,
            recipient_vessel_name=vessel.name if vessel else call.name,
            recipient_organisation=(profile.name if profile else "Unknown operator"),
            created_at=created_at,
            recommendation={
                # The advisory kind requires an instant, not a simulation hour:
                # a master reads a time, and the twin's hour axis is internal.
                "recommendedArrival": _instant(final.epoch, call.eta_hour + shift),
                "currentEta": _instant(final.epoch, call.eta_hour),
                "recommendedArrivalShiftHours": shift,
                "berth": call.berth_id or "to be assigned",
            },
            reason=(
                f"{call.name} is simulated to wait {call.wait_hours:.1f} h at anchor "
                f"under the current berth plan. Arriving {shift:.1f} h later removes "
                f"about {shift:.1f} h of that wait without moving the berth window."
            ),
            model_confidence=verdict.adjusted_confidence,
            evidence={
                "simulatedWaitHours": round(call.wait_hours, 1),
                "expectedWaitReductionHours": shift,
                "berthUtilisation": result.metrics.get("berthUtilisation"),
                "queueLength": result.metrics.get("queueLength"),
            },
            critic_verdict=verdict.verdict,
            critic_reasons=verdict.reasons + verdict.qualifications,
            valid_until=_default_validity(),
        )
        try:
            store.create(advisory, principal=acting)
        except (AdvisoryError, AuthorisationError) as exc:
            refused.append({"vesselId": advisory.recipient_vessel_id, "reasons": [str(exc)]})
            continue
        created.append(advisory.to_dict())

    return {
        "portCode": port_code,
        "created": created,
        "refused": refused,
        "callsConsidered": len(final.calls),
        "callsThatWaited": len([c for c in final.calls if c.wait_hours >= 1.0]),
        "note": (
            "Drafts only. Every one is invisible to its recipient until a named "
            "controller reviews and issues it. The arrival shifts come from the "
            "twin simulation; the Critic reviewed each before it was drafted."
        ),
    }


@router.post("/advisories/{advisory_id}/transition")
def transition_advisory(
    advisory_id: str,
    payload: Dict[str, Any] = Body(...),
    actor: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    organisation: Optional[str] = Header(None, alias="X-PortWatch-Org"),
    vessel_ids: Optional[str] = Header(None, alias="X-PortWatch-Vessels"),
    admin: Optional[str] = Header(None, alias="X-PortWatch-Admin"),
) -> Dict[str, Any]:
    """Approve, issue, reject, accept, query, decline or withdraw."""
    acting = principal_from_request(
        actor, role, header_port, organisation, vessel_ids,
        is_admin=(admin or "").lower() in ("1", "true", "yes"),
    )
    target = str(payload.get("target") or "")
    reason = payload.get("reason")

    store = get_advisory_store()
    try:
        advisory = store.act(
            advisory_id, target, principal=acting, reason=reason,
            changes=payload.get("changes"),
        )
    except AuthorisationError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except AdvisoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    _sync_decision(advisory)
    return advisory.to_dict(for_recipient=acting.role == RECIPIENT)


@router.post("/advisories/{advisory_id}/modify")
def modify_advisory(
    advisory_id: str,
    payload: Dict[str, Any] = Body(...),
    actor: Optional[str] = Header(None, alias="X-PortWatch-Actor"),
    role: Optional[str] = Header(None, alias="X-PortWatch-Role"),
    header_port: Optional[str] = Header(None, alias="X-PortWatch-Port"),
    admin: Optional[str] = Header(None, alias="X-PortWatch-Admin"),
) -> Dict[str, Any]:
    """A controller edits the recommendation before issuing it."""
    acting = principal_from_request(
        actor, role, header_port, None, None,
        is_admin=(admin or "").lower() in ("1", "true", "yes"),
    )
    try:
        advisory = get_advisory_store().modify(
            advisory_id, dict(payload.get("changes") or {}),
            principal=acting, reason=str(payload.get("reason") or ""),
        )
    except AuthorisationError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except AdvisoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return advisory.to_dict()


@router.get("/advisories/{advisory_id}/audit")
def advisory_audit(advisory_id: str) -> Dict[str, Any]:
    try:
        return {
            "advisoryId": advisory_id,
            "audit": get_advisory_store().audit_trail(advisory_id),
        }
    except AdvisoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _instant(epoch: Optional[str], hour: float) -> str:
    """Turn a simulation hour into a UTC instant a master can read.

    The twin counts hours from the observed snapshot. Every advisory that names
    a time has to name a real one, so the epoch is carried through rather than
    the hour being shown raw.
    """
    base = None
    if epoch:
        try:
            base = datetime.fromisoformat(str(epoch).replace("Z", "+00:00"))
        except ValueError:
            base = None
    if base is None:
        base = datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return (base + timedelta(hours=float(hour))).isoformat(timespec="seconds")


def _default_validity() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(timespec="seconds")


def _sync_decision(advisory: Advisory) -> None:
    """Mirror the advisory's outcome into the decision ledger.

    A recommendation that was declined is as informative as one that was taken:
    the take-up rate is how the product finds out whether operators trust it.
    """
    if not advisory.decision_id:
        return
    ledger = get_ledger()
    mapping = {
        ACCEPTED: "taken",
        DECLINED: "not_taken",
        QUERIED: "pending",
        ACKNOWLEDGED: "pending",
    }
    action_state = mapping.get(advisory.state)
    if action_state is None or action_state == "pending":
        return
    ledger.resolve_decision(
        advisory.decision_id,
        action_state,
        observed_outcome={"advisoryState": advisory.state},
        observed_at=advisory.responded_at or utc_now(),
    )
