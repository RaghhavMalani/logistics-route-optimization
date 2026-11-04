"""Explainable declared-voyage exposure, separate from source truth and impact.

Destination membership, broad lanes and schematic vessel positions never prove
passage. Route proximity is a confirmation lead, not navigational clearance.
"""
import math
from datetime import timedelta

from src.portwatch_os.intelligence.timestamps import instant

CONFIRMED = "CONFIRMED_DECLARED_EXPOSURE"
POSSIBLE = "POSSIBLE_EXPOSURE"
NONE = "NO_DEMONSTRATED_EXPOSURE"
INSUFFICIENT = "INSUFFICIENT_DATA"


def declared_passages(vessel):
    rows = vessel.get("declaredPassages") or {}
    rows = list(rows.values()) if isinstance(rows, dict) else list(rows)
    latest = vessel.get("declaredPassage")
    if latest and not any(p.get("id") == latest.get("id") for p in rows):
        rows.append(latest)
    return rows


def passage_for(vessel, asset_id):
    direct = (vessel.get("declaredPassages") or {}).get(asset_id) if isinstance(vessel.get("declaredPassages"), dict) else None
    return direct or next((p for p in reversed(declared_passages(vessel)) if p.get("areaId") == asset_id), None)


def source_validity(event, now):
    state = event.get("sourceStatus") or event.get("status") or "UNKNOWN"
    status = event.get("status")
    if status in ("CANCELLED", "EXPIRED", "UNREVIEWED", "SUPERSEDED"):
        return status
    try:
        if event.get("availableAt") and instant(event["availableAt"]) > now:
            return "NOT_YET_AVAILABLE"
        if event.get("productThrough") and instant(event["productThrough"]) <= now:
            return "EXPIRED"
        windows = event.get("windows") or []
        if windows and all(instant(w["end"]) <= now for w in windows):
            return "EXPIRED"
        if state in ("UNAVAILABLE", "MISSING", "STALE", "FUTURE_DATED", "UNKNOWN"):
            return state
        if event.get("checkedAt") and instant(event["checkedAt"]) + timedelta(hours=6) < now:
            return "STALE"
    except (ValueError, TypeError, KeyError, AttributeError):
        return "UNKNOWN"
    return "CURRENT" if state in ("CURRENT", "CACHED", "SCHEDULED", "SUPPORTED") else state


def _route_near_asset(vessel, event):
    """Declared route segment within 2km of point: possible exposure only."""
    geometry = vessel.get("routeGeometry") or {}
    coords = geometry.get("coordinates")
    asset = event.get("coordinates") or {}
    if geometry.get("type") != "LineString" or geometry.get("basis") not in ("OPERATOR_DECLARED_ROUTE", "REVIEWED_ROUTE_GEOMETRY"):
        return False
    if not isinstance(coords, list) or len(coords) < 2:
        return False
    try:
        lon, lat = float(asset["lon"]), float(asset["lat"])
        sx, sy = 111.32 * math.cos(math.radians(lat)), 110.57
        for first, second in zip(coords, coords[1:]):
            ax, ay = (float(first[0])-lon)*sx, (float(first[1])-lat)*sy
            bx, by = (float(second[0])-lon)*sx, (float(second[1])-lat)*sy
            values = (ax, ay, bx, by)
            if not all(math.isfinite(x) for x in values):
                return False
            dx, dy = bx-ax, by-ay
            t = max(0, min(1, -(ax*dx+ay*dy)/(dx*dx+dy*dy))) if dx*dx+dy*dy else 0
            if math.hypot(ax+t*dx, ay+t*dy) <= 2:
                return True
    except (ValueError, TypeError, KeyError, IndexError):
        return False
    return False


def match(event, vessel, now):
    asset = event.get("areaId") or event.get("assetId")
    event_id = event.get("noticeId") or event.get("id") or event.get("noticeRef")
    validity = source_validity(event, now)
    plan = passage_for(vessel, asset) if asset else None
    missing, windows = [], event.get("windows") or []
    overlap, passage_at = None, None
    status, reason = NONE, "No explicit passage through this asset is demonstrated; destination, broad lane and schematic position are not proof."
    if not asset:
        status, reason = INSUFFICIENT, "The source has no reviewed stable asset mapping."
        missing.append("reviewedAssetId")
    elif plan:
        episode = vessel.get("operationalEpisode")
        if episode and (plan.get("operationalEpisode") or {}).get("id") != episode["id"]:
            status, reason = INSUFFICIENT, "The declaration belongs to another operational call."
            missing.append("currentCallPassageDeclaration")
        elif asset not in (plan.get("route") or []):
            status, reason = INSUFFICIENT, "The declared asset is absent from the declared route."
            missing.append("explicitRouteMembership")
        else:
            try:
                passage_at = instant(plan["passageAt"])
                if not windows:
                    status, reason = INSUFFICIENT, "Declared asset membership is known, but no usable restriction interval is available."
                    missing.append("reviewedRestrictionWindow")
                else:
                    overlap = next((w for w in windows if instant(w["start"]) <= passage_at < instant(w["end"])), None)
                    if overlap:
                        status, reason = CONFIRMED, "Explicit declared passage through the stable asset overlaps the published restriction interval. This confirms declared exposure, not actual passage or event occurrence."
                    else:
                        status, reason = NONE, "The declared passage time does not overlap a published restriction interval."
            except (ValueError, TypeError, KeyError, AttributeError):
                status, reason = INSUFFICIENT, "Declared asset membership needs a valid passage time and restriction interval."
                missing.append("passageTimeOrWindow")
    elif asset in (vessel.get("possibleAssetIds") or []) or _route_near_asset(vessel, event):
        status, reason = POSSIBLE, "A declared candidate asset or reviewed route segment suggests proximity; explicit passage membership, applicability and time need confirmation."
        missing.extend(("explicitPassageConfirmation", "passageAt", "vesselApplicability"))
    elif not any(vessel.get(k) for k in ("portCode", "laneCode", "declaredPassage", "declaredPassages", "routeGeometry")):
        status, reason = INSUFFICIENT, "No route or passage declaration is available."
        missing.append("routeOrPassageDeclaration")
    applicability = "UNCONFIRMED"
    if plan:
        applicability = "DECLARED_APPLICABLE" if plan.get("openingRequired") is True and plan.get("emergencyTransit") is False else "EXEMPT_OR_UNCONFIRMED"
        if plan.get("openingRequired") is not True:
            missing.append("openingRequired")
        if plan.get("emergencyTransit") is not False:
            missing.append("ordinaryNonEmergencyTransit")
        zone=(overlap or {}).get('timeZone')
        if zone and plan.get('timezoneAssumption') != zone:
            missing.append('confirmedTimeZoneAssumption')
        chars=plan.get('characteristics') or {}
        if any(not isinstance(chars.get(k),(int,float)) or isinstance(chars.get(k),bool)
               or not math.isfinite(chars[k]) or chars[k]<=0 for k in ('loaM','beamM','draughtM','airDraughtM')):
            missing.append('vesselCharacteristics')
    extraction = event.get("extractionStatus", "SUPPORTED" if event.get("windows") else "UNSUPPORTED")
    supported = event.get("calculationSupported", bool(event.get("windows")))
    calculable = bool(status == CONFIRMED and validity == "CURRENT" and extraction == "SUPPORTED" and supported
                      and applicability == "DECLARED_APPLICABLE" and passage_at and passage_at > now and not missing)
    if calculable:
        calculation_reason = "Supported conditional interval calculation; actual access, route suitability, berth and monetary effects remain unknown."
    else:
        calculation_reason = f"No numerical comparison: exposure={status}, source={validity}, extraction={extraction}, vessel applicability={applicability}."
    return {"eventId": event_id, "noticeId": event_id, "providerNoticeId": event.get("providerNoticeId"),
        "title": event.get("title", "Unidentified source event"), "vesselId": vessel["id"], "vesselName": vessel.get("name", vessel["id"]),
        "assetId": asset, "assetName": event.get("assetName") or event.get("title"), "coordinates": event.get("coordinates"),
        "sourceFamily": event.get("sourceFamily", event.get("category", "UNKNOWN")), "sourceStatus": event.get("sourceStatus", "UNKNOWN"),
        "sourceValidity": validity, "sourceRevisionId": event.get("revisionId"), "sourceAvailableAt": event.get("availableAt"),
        "status": status, "reason": reason, "missingInputs": sorted(set(missing)), "windows": windows,
        "from": min((w.get("start") for w in windows), default=None), "through": max((w.get("end") for w in windows), default=None),
        "passageAt": passage_at.isoformat() if passage_at else None, "timingOverlap": overlap,
        "vesselApplicability": applicability, "operationalEpisode": vessel.get("operationalEpisode"),
        "calculable": calculable, "calculationReason": calculation_reason,
        "declaredExposureIsObserved": False}


def queue(events, vessels, now, *, event_id=None, vessel_id=None):
    rows = [match(event, vessel, now) for event in events for vessel in vessels
            if (not event_id or event_id in (event.get("noticeId"), event.get("id"), event.get("providerNoticeId")))
            and (not vessel_id or vessel["id"] == vessel_id)]
    for row in rows:
        hours = (instant(row["passageAt"])-now).total_seconds()/3600 if row["passageAt"] else None
        score = {CONFIRMED: 40, POSSIBLE: 20, INSUFFICIENT: 5, NONE: 0}[row["status"]]
        if row["sourceValidity"] in ("CANCELLED", "EXPIRED", "SUPERSEDED"):
            score = 0
        elif hours is not None and 0 <= hours <= 72:
            score += 15 if hours <= 24 else 10
        row["priority"] = {"score": score, "rank": None, "label": "Heuristic review priority; not disruption probability",
            "reason": "Declared exposure (40), possible route lead (20), insufficient data (5), otherwise 0; passage within 24h adds 15 or within 72h adds 10. Cancelled/expired/superseded sources score 0.",
            "hoursToDeclaredPassage": hours}
    rows.sort(key=lambda r: (-r["priority"]["score"], str(r["eventId"]), r["vesselId"]))
    for rank, row in enumerate(rows, 1):
        row["priority"]["rank"] = rank
    return rows
