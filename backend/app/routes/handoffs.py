from hashlib import sha256
from urllib.parse import urlencode

from fastapi import APIRouter

from backend.app.identity import current_identity, may_see_decision
from backend.app.routes.advisories import principal_from_request
from backend.app.routes.company import resolve_company
from backend.app.services.demo_terminal import demo_hulls
from src.portwatch_os.advisories.store import get_advisory_store
from src.portwatch_os.decision.engine import get_engine
from src.portwatch_os.sandbox import current_sandbox

router = APIRouter()

ADVISORY_STAGES = {
    "draft": ("PORT_REVIEWING", "PORT_AUTHORITY"),
    "under_review": ("PORT_REVIEWING", "PORT_AUTHORITY"),
    "issued": ("ISSUED_TO_VESSEL", "VESSEL_OPERATOR"),
    "acknowledged": ("ACKNOWLEDGED", "VESSEL_OPERATOR"),
    "accepted": ("ACCEPTED", "PORT_AUTHORITY"),
    "queried": ("QUERIED", "PORT_AUTHORITY"),
    "declined": ("DECLINED", None),
    "rejected": ("REJECTED", None),
    "withdrawn": ("WITHDRAWN", None),
    "expired": ("EXPIRED", None),
    "completed": ("COMPLETED", None),
}


def link(workspace, **selection):
    return f"/{workspace}/advisories?{urlencode(selection)}"


@router.get("/handoffs")
def handoffs():
    who = current_identity.get()
    sandbox = current_sandbox.get()
    if who is None or (sandbox is None and not who.verified):
        return {"items": []}

    if sandbox:
        allowed = {row["id"] for row in demo_hulls(sandbox.world)}
    elif who.is_admin:
        allowed = None
    else:
        profile = resolve_company()
        allowed = set(profile.vessel_ids()) if profile else set()

    if allowed is not None and not allowed:
        return {"items": []}
    principal = principal_from_request(None, None, None, None, None)
    register = get_advisory_store()
    advisory_rows = {row.advisory_id: row for row in register.visible_to(principal)
                     if allowed is None or row.recipient_vessel_id in allowed}
    items = []
    consumed = set()
    if sandbox:
        world = sandbox.world
        engine = get_engine()
        journeys = dict(world.get("weatherJourneys") or {})
        latest = world.get("terminalProposal") or {}
        if latest.get("environmentEvidenceId"):
            journeys.setdefault(latest["decisionId"], {
                "proposal": latest, "reviewDecisionId": world.get("currentArrivalReview"),
            })

        for key, journey in journeys.items():
            proposal = journey.get("proposal") or {}
            vessel_id = proposal.get("vesselId")
            if vessel_id not in allowed or (who.role == "PORT_AUTHORITY" and who.port_code != proposal.get("portCode")):
                continue
            source = engine.get(key)
            if source is None or source.actor.role != "SHIPPING_COMPANY":
                continue
            if who.role == "SHIPPING_COMPANY" and not may_see_decision(
                who, source.actor.to_dict(),
                {"type": source.subject_type, "id": source.subject_id}, source.domain,
            ):
                continue
            review = engine.get(journey["reviewDecisionId"]) if journey.get("reviewDecisionId") else None
            advisory = next((advisory_rows[i] for i in (review.evidence.get("advisories") or [])
                             if i in advisory_rows), None) if review else None
            if who.role == "VESSEL_OPERATOR" and advisory is None:
                continue

            state, next_actor = ("PORT_REVIEWING" if review else "COMPANY_PROPOSED"), "PORT_AUTHORITY"
            change = (review.workflow_history[-1]["at"] if review.workflow_history else review.created_at) if review else (
                source.workflow_history[-1]["at"] if source.workflow_history else source.created_at)
            summary = "Company approved an arrival comparison for Port review."
            choice = source.option(proposal.get("optionId"))
            if choice and who.role != "VESSEL_OPERATOR":
                summary = choice.label
                baseline = source.option(source.baseline_option_id)
                if baseline and baseline.evaluation and choice.evaluation:
                    before = baseline.evaluation.derived.get("anchorageWaitHours")
                    after = choice.evaluation.derived.get("anchorageWaitHours")
                    if before is not None and after is not None:
                        summary += f" · assumed anchorage wait {before:.2f} h → {after:.2f} h"
                    if choice.evaluation.derived.get("scheduleShiftHours") == 0:
                        summary += " · same modeled schedule"
            target = link("port", proposal=key) if who.role in ("PORT_AUTHORITY", "NATIONAL_ADMIN") else None
            if who.role == "SHIPPING_COMPANY":
                selection = {"vesselId": vessel_id, "decisionId": key}
                if proposal.get("optionId"):
                    selection["optionId"] = proposal["optionId"]
                target = f"/company/global-eye#fleet-review?{urlencode(selection)}"
            from_role, from_org = "SHIPPING_COMPANY", source.actor.organisation
            if advisory:
                consumed.add(advisory.advisory_id)
                state, next_actor = ADVISORY_STAGES[advisory.state]
                change = advisory.audit[-1].at if advisory.audit else advisory.created_at
                from_role, from_org = "PORT_AUTHORITY", advisory.issuer_organisation
                if state == "COMPLETED" and review.evidence.get("demoOutcome"):
                    state = "OUTCOME_RECORDED"
                if who.role == "VESSEL_OPERATOR":
                    target = link("vessel", advisory=advisory.advisory_id)
                    summary = "Port issued an advisory for this vessel."
                if who.role == "SHIPPING_COMPANY":
                    target = link("company", advisory=advisory.advisory_id)
            item = {
                "id": "handoff-" + sha256(key.encode()).hexdigest()[:24],
                "vesselId": vessel_id, "vesselName": source.subject_label,
                "fromRole": from_role, "fromOrg": from_org, "toRole": next_actor,
                "portCode": proposal.get("portCode"), "summary": summary,
                "state": state, "stateChangedAt": change, "nextActor": next_actor,
                "deepLink": target, "labels": ["DEMO", "SIMULATED", "ASSUMPTION"],
            }
            if who.role == "PORT_AUTHORITY" and advisory:
                item["advisoryId"] = advisory.advisory_id
            items.append(item)

    for advisory_id, row in advisory_rows.items():
        if advisory_id in consumed:
            continue
        state, next_actor = ADVISORY_STAGES[row.state]
        if not sandbox and state == "ACCEPTED":
            next_actor = None
        workspace = {"VESSEL_OPERATOR": "vessel", "SHIPPING_COMPANY": "company"}.get(who.role, "port")
        items.append({
            "id": advisory_id, "vesselId": row.recipient_vessel_id, "vesselName": row.recipient_vessel_name,
            "fromRole": "PORT_AUTHORITY", "fromOrg": row.issuer_organisation, "toRole": next_actor,
            "portCode": row.port_code, "summary": "Port advisory for this vessel.",
            "state": state, "stateChangedAt": row.audit[-1].at if row.audit else row.created_at,
            "nextActor": next_actor, "deepLink": link(workspace, advisory=advisory_id),
            "labels": ["DEMO", "SIMULATED"] if sandbox else [],
        })
    return {"items": sorted(items, key=lambda item: item["stateChangedAt"], reverse=True)}
