"""Independent check and issue clocks for retained Open-Meteo forecasts."""
from datetime import datetime, timedelta, timezone
from math import isfinite

CHECK_SECONDS = 90 * 60
MODEL_UPDATE_SECONDS = 6 * 3600
ISSUE_MARGIN_SECONDS = 2 * 3600


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def covers_hour(row, now, fields):
    if not isinstance(row, dict):
        return False
    try:
        valid = instant(row.get("validAt"))
    except (ValueError, TypeError, AttributeError, OverflowError):
        return False
    return valid <= now < valid + timedelta(hours=1) and all(
        type(row.get(key)) in (int, float) and isfinite(row[key]) for key in fields)


def describe(snapshot, now):
    checked = snapshot.get("lastSuccessfulCheckAt") or snapshot.get("fetchedAt") or snapshot.get("availableAt")
    # Best Match combines models. A static per-model metadata response cannot
    # establish the generation time of these particular mixed forecast bytes.
    issue = snapshot.get("forecastIssuedAt") or snapshot.get("valuesChangedAt") or snapshot.get("availableAt")
    checked_age = (now - instant(checked)).total_seconds() if checked else None
    issue_age = (now - instant(issue)).total_seconds() if issue else None
    fields = ("wave_height",) if snapshot["kind"] == "marine" else (
        "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m", "precipitation", "visibility")
    covered = any(covers_hour(row, now, fields) for row in snapshot.get("rows", []))
    current = (checked_age is not None and 0 <= checked_age <= CHECK_SECONDS
               and issue_age is not None and 0 <= issue_age <= MODEL_UPDATE_SECONDS + ISSUE_MARGIN_SECONDS
               and covered)
    return {
        "status": "CURRENT" if current else "STALE",
        "checkedAt": checked, "forecastIssuedAt": issue,
        "forecastIssueBasis": snapshot.get("forecastIssueBasis", "VALUES_LAST_CHANGED"),
        "checkAgeSeconds": checked_age, "forecastAgeSeconds": issue_age,
        "checkPolicySeconds": CHECK_SECONDS,
        "modelUpdateSeconds": MODEL_UPDATE_SECONDS, "issueMarginSeconds": ISSUE_MARGIN_SECONDS,
        "latestAvailable": checked_age is not None and 0 <= checked_age <= CHECK_SECONDS,
    }
