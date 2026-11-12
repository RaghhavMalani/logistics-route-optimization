"""As-of cargo simulation inputs from existing published snapshot products."""

from datetime import datetime, timedelta, timezone
from math import isfinite

from .cargo_sampling import FXHistory, PortQuantiles, WeatherMembers
from .commercial import digest, instant
from src.portwatch_os.freshness.reviewed_sources import ECB_RATES, PUBLISHED_MAX_AGE

ENSEMBLE = "open-meteo-ensemble"


def retained_weather(store, at: datetime, port: str, target: datetime) -> WeatherMembers | None:
    if store is None:
        return None
    at = instant(at)
    target = instant(target).replace(minute=0, second=0, microsecond=0)
    for snapshot in store.snapshots("published", ENSEMBLE, since=at - PUBLISHED_MAX_AGE[ENSEMBLE], until=at, limit=8):
        payload = snapshot.payload
        available = instant(payload["availableAt"])
        if not at - PUBLISHED_MAX_AGE[ENSEMBLE] <= available <= at:
            continue
        row = payload.get("ports", {}).get(port, {})
        if row.get("error") or row.get("units", {}).get("wind_speed_10m") not in ("kn", "knots"):
            continue
        hourly = row.get("hourly") or {}
        hours = [datetime.fromisoformat(hour) for hour in hourly.get("time", [])]
        hours = [hour.replace(tzinfo=timezone.utc) if hour.tzinfo is None else hour.astimezone(timezone.utc) for hour in hours]
        if target not in hours:
            continue
        index = hours.index(target)
        members = [series[index] for key, series in sorted(hourly.items())
                   if key.startswith("wind_speed_10m_member") and index < len(series)
                   and type(series[index]) in (int, float) and isfinite(series[index]) and 0 <= series[index] <= 300]
        if len(members) >= 2:
            return WeatherMembers(windKn=members, source=(
                f"Open-Meteo ensemble · {port} · valid {target.isoformat()} · retained {available.isoformat()}"
                f" · receipt {digest(payload)[:16]}"
            ))
    return None


def retained_fx(store, at: datetime) -> FXHistory | None:
    if store is None:
        return None
    at = instant(at)
    days: dict[str, dict[str, float]] = {}
    rows = store.snapshots("published", ECB_RATES, since=at - timedelta(days=365), until=at, limit=1200)
    for snapshot in rows:
        if snapshot.observed_at is None or snapshot.observed_at > at:
            continue
        rates = {row["quote"]: row for row in snapshot.payload.get("rates", [])}
        if rates.keys() != {"USD", "INR"} or rates["USD"]["date"] != rates["INR"]["date"]:
            continue
        day = rates["USD"]["date"]
        if day > at.date().isoformat() or day in days:
            continue
        quotes = {name: float(row["rate"]) for name, row in rates.items()}
        if all(isfinite(rate) and rate > 0 for rate in quotes.values()):
            days[day] = {"EUR": 1, **quotes}
    if not days:
        return None
    date_keys = sorted(days)
    movement = "single observation, fixed rate" if len(days) == 1 else "empirical paired date resampling"
    return FXHistory(
        datedQuotes=[days[day] for day in date_keys],
        source=(f"ECB via Frankfurter · {len(days)} published dates · {date_keys[0]} through {date_keys[-1]}"
                f" · {movement} · input {digest(days)[:16]}"),
    )


def retained_port_quantiles(rows: list[dict], at: datetime, target: datetime) -> PortQuantiles | None:
    """Select the target-day quantiles issued by the as-of instant."""
    day = instant(target).date().isoformat()
    at = instant(at)
    for row in rows:
        origin = row.get("originDate")
        if (row.get("targetDate") or "")[:10] != day or not origin or row.get("dataStatus") in {"SYNTHETIC", "UNAVAILABLE"}:
            continue
        issued = datetime.fromisoformat(origin.replace("Z", "+00:00"))
        if issued.tzinfo is None:
            issued = issued.replace(tzinfo=timezone.utc)
        if issued > at or instant(target) < at:
            continue
        values = [row.get(key) for key in ("q10", "q50", "q90", "delayHoursP50")]
        if all(type(value) in (int, float) and isfinite(value) for value in values):
            low, median, high, wait = values
            if 0 <= low <= median <= high <= 100 and wait >= 0:
                return PortQuantiles(
                    congestion=(low, median, high), medianWaitHours=wait,
                    waitHoursPerIndexPoint=wait / max(median, 1),
                    source=f"Retained port forecast {origin} → {day} · modelled proportional wait mapping",
                )
    return None
