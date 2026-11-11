"""Publication scope and freshness budgets for reviewed source trials."""

from datetime import datetime, timedelta, timezone
from math import isfinite

from src.portwatch_os.fabric.licence import ALLOWED
from src.portwatch_os.fabric.model import deployment_mode
from src.portwatch_os.freshness.source_snapshots import Snapshot, configured_store
from src.utils.settings import get_settings

ECB_RATES = "frankfurter-ecb-fx"
PUBLISHED_MAX_AGE = {
    "open-meteo-marine-extended": timedelta(hours=9),
    "open-meteo-ensemble": timedelta(hours=9),
    ECB_RATES: timedelta(days=4),
}
REVIEWED_TRIAL = "trial-live-20261106180034"
REVIEW_DECISIONS = {
    "open-meteo-marine-extended": "adopted for covered ports",
    "open-meteo-ensemble": "adopted for weather context",
    ECB_RATES: "adopted for FX reference context",
}


def permits_publication(product) -> bool:
    enabled = (get_settings().PORTWATCH_PUBLISH_REVIEWED_SOURCES or "").split(",")
    return (
        product.product_id in PUBLISHED_MAX_AGE
        and product.product_id in enabled
        and product.policy.redistribution == ALLOWED
        and product.policy.permits(deployment_mode())[0]
    )


def _valid_time(value: str) -> datetime:
    # The collector requests GMT. Open-Meteo returns UTC local-formatted times.
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def forecast_readings(sample: Snapshot, product: str, now: datetime) -> tuple[dict, list[dict]]:
    available = datetime.fromisoformat(sample.payload["availableAt"])
    age = now - available
    metrics = {"availableAt": available, "portsTotal": len(sample.payload["ports"]), "portsCurrent": 0}
    if not timedelta(0) <= age <= PUBLISHED_MAX_AGE[product]:
        return metrics, []

    current_hour = now.replace(minute=0, second=0, microsecond=0)
    readings = []
    horizons = []
    for locode, row in sample.payload["ports"].items():
        if row.get("error"):
            continue
        hourly = row["hourly"]
        times = [_valid_time(value) for value in hourly["time"]]
        if current_hour not in times or now > times[-1]:
            continue
        index = times.index(current_hour)
        if product == "open-meteo-ensemble":
            wind = [series[index] for key, series in hourly.items() if key.startswith("wind_speed_10m")]
            finite = [value for value in wind if type(value) in (float, int) and isfinite(value)]
            if len(finite) < 2:
                continue
            values = [{"label": "Wind member range", "value": f"{min(finite):g}–{max(finite):g}",
                       "unit": "kn", "detail": f"{len(finite)} of {len(wind)} series"}]
        else:
            labels = {"wave_height": "Waves", "swell_wave_height": "Swell",
                      "ocean_current_velocity": "Current speed", "ocean_current_direction": "Current direction"}
            values = []
            for key, label in labels.items():
                value = hourly[key][index]
                values.append({"label": label, "value": f"{value:g}" if type(value) in (float, int) and isfinite(value) else None,
                               "unit": row["units"].get(key, "")})
            if not any(value["value"] is not None for value in values):
                continue
        horizons.append(times[-1])
        readings.append({"label": locode, "validAt": current_hour, "values": values})
    metrics["portsCurrent"] = len(readings)
    if readings:
        metrics.update(status="live", validThrough=min(horizons))
    return metrics, readings


def ecb_readings(sample: Snapshot, now: datetime) -> list[dict]:
    observed = sample.observed_at
    if observed is None or not timedelta(0) <= now - observed <= PUBLISHED_MAX_AGE[ECB_RATES]:
        return []
    return [{"label": f"EUR/{row['quote']}", "validAt": _valid_time(row['date']), "values": [
        {"label": "ECB reference rate", "value": str(row['rate']), "unit": f"{row['quote']}/EUR"},
    ]} for row in sample.payload.get("rates", [])]


def ecb_context(now: datetime) -> dict:
    """Display-only INR per USD cross from same-date retained ECB legs."""
    from sqlalchemy.exc import SQLAlchemyError

    try:
        store = configured_store()
        sample = store.latest("published", ECB_RATES) if store else None
    except (SQLAlchemyError, ValueError):
        return {}
    if not sample or sample.observed_at is None or sample.observed_at > now:
        return {}
    rates = {row["quote"]: row for row in sample.payload.get("rates", [])}
    if rates.keys() != {"INR", "USD"} or rates["INR"]["date"] != rates["USD"]["date"]:
        return {}
    age = now - sample.observed_at
    return {
        "value": rates["INR"]["rate"] / rates["USD"]["rate"],
        "observedAt": sample.observed_at.date().isoformat(),
        "ageHours": round(age.total_seconds() / 3600, 1),
        "status": "CURRENT" if age <= PUBLISHED_MAX_AGE[ECB_RATES] else "STALE",
    }
