"""Shipping company: fleet, routes, risk and cargo.

The company account is a seam, not a hardcoded fleet. :func:`resolve_company`
looks up a configured provider first and falls back to the demo carrier, so a
real carrier integration is a provider registration rather than a change to any
route here.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.portwatch_os.fleet.company import (
    COMPANY_DISCLAIMER,
    DEMO_COMPANY_ID,
    CompanyProfile,
    attach_etas,
    capacities_for,
    demo_company,
    from_provider,
)
from src.portwatch_os.global_eye.calibration import apply_calibration, fit_calibrator
from src.portwatch_os.global_eye.exposure import (
    TRADE_LANES,
    aggregate_port_risk,
    build_impact,
)
from src.portwatch_os.global_eye.ingest import from_news_bundle
from src.portwatch_os.ledger.store import get_ledger

router = APIRouter()

#: Anchor for the demo fleet's ETAs. Read from the pipeline's forecast origin so
#: the fleet screen agrees with the port state beside it and a screenshot is
#: reproducible.
_FALLBACK_EPOCH_MS = 1_787_896_800_000  # 2026-08-28T06:00:00Z


def resolve_company(company_id: Optional[str] = None) -> Optional[CompanyProfile]:
    """The company account for this deployment.

    ``PORTWATCH_FLEET_PROVIDER`` names a JSON file a real carrier integration
    writes. Absent, the demo carrier is used and every payload carries the
    disclaimer saying so. There is no path where a fictional fleet is presented
    as a real one.

    The result is cached on everything it actually reads, not on the company id
    alone. Both of the other inputs move underneath a long-running process --
    the provider rewrites its file, and the pipeline advances its forecast
    origin -- and keying on the id alone pinned the first snapshot for the life
    of the process, so the fleet clock drifted away from the port state shown
    beside it.
    """
    provider_path = os.getenv("PORTWATCH_FLEET_PROVIDER")
    if provider_path and os.path.exists(provider_path):
        try:
            stamp = os.path.getmtime(provider_path)
        except OSError:
            stamp = None
        return _from_provider_file(company_id, provider_path, stamp)

    if company_id and company_id != DEMO_COMPANY_ID:
        return None
    return _demo_at(_epoch_ms())


@lru_cache(maxsize=4)
def _from_provider_file(
    company_id: Optional[str], provider_path: str, stamp: Optional[float]
) -> Optional[CompanyProfile]:
    import json

    with open(provider_path, "r", encoding="utf-8") as handle:
        profile = from_provider(json.load(handle))
    if company_id and company_id != profile.company_id:
        return None
    return profile


@lru_cache(maxsize=4)
def _demo_at(epoch_ms: int) -> CompanyProfile:
    return attach_etas(demo_company(), epoch_ms)


def _epoch_ms() -> int:
    from backend.app.services import cache_service as cache

    try:
        status = cache.get_live_status()
        origin = status.get("forecastOrigin") if isinstance(status, dict) else None
        if origin:
            parsed = datetime.fromisoformat(str(origin).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1000)
    except Exception:  # noqa: BLE001 - a missing artefact is not fatal here
        pass
    return _FALLBACK_EPOCH_MS


def _require(company_id: Optional[str]) -> CompanyProfile:
    profile = resolve_company(company_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No company account '{company_id}' is configured. Set "
                "PORTWATCH_FLEET_PROVIDER to a provider payload, or omit the id to "
                "use the demo carrier."
            ),
        )
    return profile


def _events():
    from backend.app.services import cache_service as cache

    try:
        bundle = cache.get_news_bundle()
    except cache.CacheNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    events, _ = from_news_bundle(bundle)
    calibrator = fit_calibrator(
        get_ledger().event_outcomes(),
        fitted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    apply_calibration(events, calibrator)
    return events


@router.get("/company")
def company_profile(company_id: Optional[str] = None) -> Dict[str, Any]:
    profile = _require(company_id)
    return profile.to_dict()


@router.get("/company/fleet")
def company_fleet(company_id: Optional[str] = None) -> Dict[str, Any]:
    profile = _require(company_id)
    return {
        "companyId": profile.company_id,
        "companyName": profile.name,
        "verified": profile.verified,
        "positionSource": profile.position_source,
        "disclaimer": profile.disclaimer,
        "vessels": [v.to_dict() for v in profile.vessels],
        "lanes": [
            {"code": lane.code, "name": lane.name,
             "chokepoints": list(lane.chokepoints),
             "alternative": lane.alternative, "detourNm": lane.detour_nm}
            for lane in TRADE_LANES.values()
        ],
    }


@router.get("/company/risk")
def company_risk(
    company_id: Optional[str] = None,
    horizon_hours: float = Query(72.0, ge=1.0, le=336.0),
) -> Dict[str, Any]:
    """Which vessels require intervention over the horizon, and by when.

    The answer to the company workspace's primary question. Every row carries
    whether the vessel can still act -- a vessel already inside the risk area is
    reported, but never with a diversion recommendation attached.
    """
    profile = _require(company_id)
    events = _events()
    voyages = profile.voyages()

    rows: List[Dict[str, Any]] = []
    impacts = []
    for event in events:
        impact = build_impact(event, voyages)
        if not impact.vessels:
            continue
        impacts.append(impact)
        for vessel in impact.vessels:
            hours = vessel.hours_to_risk_area
            if hours is not None and hours > horizon_hours:
                continue
            rows.append({
                **vessel.to_dict(),
                "eventId": event.event_id,
                "eventTitle": event.title,
                "eventCategory": event.category,
                "eventCategoryLabel": (
                    event.category_spec.label if event.category_spec else event.category
                ),
                "eventSeverity": round(event.severity, 3),
                "eventConfidence": round(event.confidence, 3),
                "eventProbability": event.probability,
                "eventSourceCount": event.source_count,
            })

    rows.sort(key=lambda r: (-r["exposure"], r.get("hoursToRiskArea") or 1e9))

    by_vessel: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        current = by_vessel.get(row["vesselId"])
        if current is None or row["exposure"] > current["exposure"]:
            by_vessel[row["vesselId"]] = row

    actionable = [r for r in by_vessel.values() if not r["alreadyEntered"]]
    committed = [r for r in by_vessel.values() if r["alreadyEntered"]]

    return {
        "companyId": profile.company_id,
        "companyName": profile.name,
        "horizonHours": horizon_hours,
        "fleetSize": len(profile.vessels),
        "vesselsExposed": len(by_vessel),
        "actionRequired": sorted(actionable, key=lambda r: -r["exposure"]),
        "monitorOnly": sorted(committed, key=lambda r: -r["exposure"]),
        "rows": rows,
        "portRisk": aggregate_port_risk(impacts),
        "disclaimer": profile.disclaimer,
        "note": (
            "A vessel that has already entered the exposed water carries no diversion "
            "recommendation: the option is gone, and offering one would be unactionable."
        ),
    }


@router.get("/company/vessels/{vessel_id}")
def company_vessel(vessel_id: str, company_id: Optional[str] = None) -> Dict[str, Any]:
    profile = _require(company_id)
    vessel = profile.vessel(vessel_id)
    if vessel is None:
        raise HTTPException(
            status_code=404, detail=f"{vessel_id} is not in the {profile.name} fleet"
        )

    events = _events()
    exposures: List[Dict[str, Any]] = []
    for event in events:
        impact = build_impact(event, [vessel.to_voyage()])
        for row in impact.vessels:
            if row.vessel_id != vessel_id:
                continue
            exposures.append({
                **row.to_dict(),
                "eventId": event.event_id,
                "eventTitle": event.title,
                "eventCategory": event.category,
                "eventProbability": event.probability,
                "eventConfidence": round(event.confidence, 3),
            })
    exposures.sort(key=lambda r: -r["exposure"])

    lane = TRADE_LANES.get(vessel.lane_code or "")
    return {
        "vessel": vessel.to_dict(),
        "companyId": profile.company_id,
        "companyName": profile.name,
        "lane": (
            {
                "code": lane.code, "name": lane.name,
                "chokepoints": list(lane.chokepoints),
                "primaryNm": lane.primary_nm, "alternative": lane.alternative,
                "detourNm": lane.detour_nm, "description": lane.description,
            }
            if lane else None
        ),
        "exposures": exposures,
        "disclaimer": profile.disclaimer,
    }


@router.get("/company/routes")
def company_routes(company_id: Optional[str] = None) -> Dict[str, Any]:
    """Lane-level exposure across the fleet."""
    profile = _require(company_id)
    events = _events()
    voyages = profile.voyages()

    per_lane: Dict[str, Dict[str, Any]] = {}
    for lane in TRADE_LANES.values():
        vessels = [v for v in profile.vessels if v.lane_code == lane.code]
        if not vessels:
            continue
        per_lane[lane.code] = {
            "laneCode": lane.code,
            "laneName": lane.name,
            "chokepoints": list(lane.chokepoints),
            "primaryNm": lane.primary_nm,
            "alternative": lane.alternative,
            "detourNm": lane.detour_nm,
            "description": lane.description,
            "vessels": [{"vesselId": v.vessel_id, "name": v.name,
                         "destination": v.destination_port, "eta": v.eta}
                        for v in vessels],
            "exposure": 0.0,
            "events": [],
        }

    for event in events:
        impact = build_impact(event, voyages)
        for lane_exposure in impact.lanes:
            entry = per_lane.get(lane_exposure.lane_code)
            if entry is None:
                continue
            if lane_exposure.exposure > entry["exposure"]:
                entry["exposure"] = lane_exposure.exposure
            entry["events"].append({
                "eventId": event.event_id, "title": event.title,
                "category": event.category, "exposure": lane_exposure.exposure,
            })

    lanes = sorted(per_lane.values(), key=lambda r: -r["exposure"])
    for entry in lanes:
        entry["events"].sort(key=lambda e: -e["exposure"])
        entry["events"] = entry["events"][:5]
        entry["exposure"] = round(entry["exposure"], 3)

    return {
        "companyId": profile.company_id,
        "lanes": lanes,
        "disclaimer": profile.disclaimer,
    }


@router.get("/company/cargo")
def company_cargo(
    port_code: str = Query(..., description="Port to look for connections at."),
    company_id: Optional[str] = None,
    limit: int = Query(25, ge=1, le=100),
) -> Dict[str, Any]:
    """Transshipment opportunities for this fleet at a port."""
    from backend.app.routes.port_twin import build_state_for
    from src.portwatch_os.cargo.model import CARGO_DISCLAIMER, demo_manifest, zones_from_state
    from src.portwatch_os.cargo.optimizer import opportunities

    profile = _require(company_id)
    state = build_state_for(port_code)
    manifest = [s for s in demo_manifest(port_code) if s.inbound_vessel_id]
    rows = opportunities(
        manifest, capacities_for(profile), zones_from_state(state), limit=limit
    )
    return {
        "portCode": port_code,
        "companyId": profile.company_id,
        "opportunities": rows,
        "shipmentsConsidered": len(manifest),
        "vesselsInScope": len(profile.vessels),
        "disclaimer": CARGO_DISCLAIMER,
    }
