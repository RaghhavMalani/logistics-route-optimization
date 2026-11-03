"""Fleet board -- served straight from the route optimizer output.

Each row is a vessel the optimizer scored against the live forecast: its
intended port, the recommended port, the ETA and risk difference between them,
and the buffer it should carry. Nothing is invented here.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.services import cache_service as cache

router = APIRouter()


@router.get("/fleet")
def fleet() -> list[dict]:
    from src.portwatch_os.sandbox import current_sandbox
    scoped = current_sandbox.get()
    if scoped is not None:
        from backend.app.identity import current_identity
        who = current_identity.get()
        vessels = [v for v in scoped.world["fleet"] if who.role != "VESSEL_OPERATOR" or v["id"] in who.vessel_ids]
        proposal = scoped.world.get("terminalProposal") or scoped.world.get("proposal") or {}
        def arrival(v):
            return (v["etaHours"] + (proposal.get("etaShiftHours") or 0 if proposal.get("vesselId") == v["id"] else 0)) / 24
        return [{"id": v["id"], "name": v["name"], "intendedPortCode": v["portCode"],
                 "originPortCode": "SUEZ" if v["laneCode"] == "EUR_IND" else "AEJEA",
                 "oneWay": True,
                 "recommendedPortCode": v["portCode"], "reroute": False,
                 "intendedArrivalDay": arrival(v), "bestArrivalDay": arrival(v),
                 "etaDeltaHours": None, "riskDelta": None, "portWaitDeltaHours": None,
                 "bufferHours": None, "diversionKm": None,
                 "recommendation": "Fictional itinerary; compare options before proposing a change.",
                 "originDate": scoped.world["epoch"], "source": "SIMULATED_TRAFFIC"}
                for v in vessels]
    from backend.app.routes.company import configured_fleet, resolve_company
    if not configured_fleet():
        return cache.get_fleet()
    profile = resolve_company()
    if profile is None:
        return []
    allowed = set(profile.vessel_ids())
    fields = {"id", "name", "intendedPortCode", "originPortCode", "recommendedPortCode",
              "oneWay", "reroute", "intendedArrivalDay", "bestArrivalDay", "etaDeltaHours",
              "riskDelta", "portWaitDeltaHours", "bufferHours", "diversionKm", "originDate", "source"}
    return [{key: value for key, value in row.items()
             if key in fields and (value is None or isinstance(value, (str, int, float, bool)))}
            for row in cache.get_fleet() if row.get("id") in allowed]
