"""Live marine + surface weather per Indian port (Open-Meteo).

IMF PortWatch carries no meteorology, so before this connector existed the
weather expert scored 0.0 on every port and the "Weather Intelligence" screen
had nothing real behind it. Open-Meteo is a free, keyless API that serves both
recent observations (ERA5-backed reanalysis and station blends) and a 10-day
forecast, which is exactly the shape the pipeline needs: measured history for
training and a genuine known-future covariate for the horizon.

Two endpoints are used, both batched across all ports in a single request:

    api.open-meteo.com/v1/forecast   wind, gusts, precipitation, visibility
    marine-api.open-meteo.com/v1/marine  significant wave height

Failure is handled honestly. A live fetch records LIVE; a replay from the local
cache records CACHED_LIVE (downgraded to STALE by the provenance layer once the
newest observation ages out); a total failure records SYNTHETIC and returns
nothing, so the weather expert falls back to GDACS storm flags alone rather than
inventing wind speeds.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.utils import port_registry, provenance
from src.utils.config import DATA_DIR, DATE, PORT_ID
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

CACHE_DIR: Path = DATA_DIR / "cache"
FORECAST_CACHE = CACHE_DIR / "openmeteo_forecast.json"
MARINE_CACHE = CACHE_DIR / "openmeteo_marine.json"
ARCHIVE_CACHE = CACHE_DIR / "openmeteo_archive.json"

#: The reanalysis archive lags real time by about five days.
ARCHIVE_LAG_DAYS = 6
ARCHIVE_TTL_SECONDS = 7 * 24 * 3600

#: Re-fetch at most this often; the underlying model updates hourly.
DEFAULT_TTL_SECONDS = 3 * 3600

KMH_TO_KNOTS = 0.539957


def _requests():
    try:
        import requests
        return requests
    except Exception:  # pragma: no cover - requests is a hard dependency
        return None


def _fresh(path: Path, ttl: int) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < ttl


def _fetch(url: str, params: dict, cache: Path, ttl: int,
           timeout: int = 30) -> tuple[Optional[list], str]:
    """Return (payload, mode) where mode is 'live', 'cache' or 'unavailable'."""
    if _fresh(cache, ttl):
        try:
            return json.loads(cache.read_text(encoding="utf-8")), "cache"
        except (OSError, json.JSONDecodeError):
            pass

    requests = _requests()
    if requests is not None:
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            # A single-location query returns an object; batched returns a list.
            payload = payload if isinstance(payload, list) else [payload]
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(payload), encoding="utf-8")
            return payload, "live"
        except Exception as exc:
            log.warning("Open-Meteo fetch failed for %s (%s).", cache.stem, exc)

    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8")), "cache"
        except (OSError, json.JSONDecodeError):
            pass
    return None, "unavailable"


def _daily_frame(payload: list, ports, field_map: dict) -> pd.DataFrame:
    """Flatten Open-Meteo's per-location daily blocks into a tidy frame."""
    rows = []
    for port, block in zip(ports, payload or []):
        daily = (block or {}).get("daily") or {}
        dates = daily.get("time") or []
        for index, day in enumerate(dates):
            row = {PORT_ID: port.model_id, DATE: pd.to_datetime(day)}
            for source, target in field_map.items():
                series = daily.get(source) or []
                row[target] = series[index] if index < len(series) else np.nan
            rows.append(row)
    if not rows:
        return pd.DataFrame(columns=[PORT_ID, DATE])
    return pd.DataFrame(rows)


def fetch_archive_weather(start: pd.Timestamp,
                          end: pd.Timestamp | None = None,
                          ttl_seconds: int = ARCHIVE_TTL_SECONDS) -> pd.DataFrame:
    """ERA5 reanalysis history per port, for the span the forecast API cannot reach.

    The forecast endpoint only backfills roughly two months. Training the model
    on two months of weather while the port panel covers a year would leave most
    of the history weatherless, so the archive endpoint supplies the rest.
    """
    ports = port_registry.all_ports()
    end = end or (pd.Timestamp.utcnow().normalize().tz_localize(None)
                  - pd.Timedelta(days=ARCHIVE_LAG_DAYS))
    start = pd.Timestamp(start).normalize()
    if start >= end:
        return pd.DataFrame(columns=[PORT_ID, DATE])

    payload, mode = _fetch(
        ARCHIVE_URL,
        {
            "latitude": ",".join(f"{p.lat}" for p in ports),
            "longitude": ",".join(f"{p.lon}" for p in ports),
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "daily": "wind_speed_10m_max,wind_gusts_10m_max,precipitation_sum",
            "timezone": "UTC",
        },
        ARCHIVE_CACHE, ttl_seconds, timeout=60)

    if payload is None:
        return pd.DataFrame(columns=[PORT_ID, DATE])

    frame = _daily_frame(payload, ports, {
        "wind_speed_10m_max": "wind_speed_kmh",
        "wind_gusts_10m_max": "wind_gust_kmh",
        "precipitation_sum": "rainfall",
    })
    if frame.empty:
        return frame

    frame["wind_speed"] = pd.to_numeric(frame["wind_speed_kmh"],
                                        errors="coerce") * KMH_TO_KNOTS
    frame["wind_gust"] = pd.to_numeric(frame["wind_gust_kmh"],
                                       errors="coerce") * KMH_TO_KNOTS
    frame = frame.drop(columns=["wind_speed_kmh", "wind_gust_kmh"])
    frame["visibility"] = np.nan
    frame["wave_height"] = np.nan
    frame["is_forecast"] = 0
    frame["storm_flag"] = 0.0

    # This feed is a *history* segment by design: it ends where the forecast
    # endpoint's own backfill begins. Its freshness budget spans a year so the
    # provenance layer does not mislabel a complete archive as stale telemetry.
    provenance.record(
        "Weather history (Open-Meteo ERA5 archive)",
        provenance.LIVE if mode == "live" else provenance.CACHED_LIVE,
        f"ERA5 daily reanalysis {start.date()}..{end.date()} for "
        f"{frame[PORT_ID].nunique()} ports. Training history only -- the live "
        "forecast feed covers everything after this window.",
        provider="Open-Meteo ERA5 archive",
        observed_at=frame[DATE].max(), rows=len(frame),
        freshness_hours=24 * 365,
        fallback=None if mode == "live" else "local response cache")
    return frame


def fetch_port_weather(past_days: int = 92,
                       forecast_days: int = 10,
                       history_start: pd.Timestamp | None = None,
                       ttl_seconds: int = DEFAULT_TTL_SECONDS) -> pd.DataFrame:
    """Daily weather per port: measured history plus the forward forecast.

    Returns the column set the weather expert consumes -- ``wind_speed`` in
    knots, ``rainfall`` in mm/day, ``wave_height`` in metres, ``visibility`` in
    km -- plus ``is_forecast`` so downstream code can tell observation from
    prediction. An empty frame means no weather data was obtainable.
    """
    ports = port_registry.all_ports()
    latitudes = ",".join(f"{p.lat}" for p in ports)
    longitudes = ",".join(f"{p.lon}" for p in ports)
    past_days = int(max(1, min(past_days, 92)))
    forecast_days = int(max(1, min(forecast_days, 16)))

    surface, surface_mode = _fetch(
        FORECAST_URL,
        {
            "latitude": latitudes,
            "longitude": longitudes,
            "daily": ("wind_speed_10m_max,wind_gusts_10m_max,"
                      "precipitation_sum,visibility_mean"),
            "timezone": "UTC",
            "past_days": past_days,
            "forecast_days": forecast_days,
        },
        FORECAST_CACHE, ttl_seconds)

    marine, marine_mode = _fetch(
        MARINE_URL,
        {
            "latitude": latitudes,
            "longitude": longitudes,
            "daily": "wave_height_max",
            "timezone": "UTC",
            "past_days": past_days,
            "forecast_days": min(forecast_days, 10),
        },
        MARINE_CACHE, ttl_seconds)

    if surface is None:
        provenance.record(
            "Marine weather (Open-Meteo)", provenance.UNAVAILABLE,
            "Open-Meteo unreachable and no cached response exists; the weather "
            "expert falls back to GDACS storm flags only.",
            provider="Open-Meteo", fallback="GDACS storm flags")
        return pd.DataFrame(columns=[PORT_ID, DATE])

    frame = _daily_frame(surface, ports, {
        "wind_speed_10m_max": "wind_speed_kmh",
        "wind_gusts_10m_max": "wind_gust_kmh",
        "precipitation_sum": "rainfall",
        "visibility_mean": "visibility_m",
    })
    if frame.empty:
        provenance.record(
            "Marine weather (Open-Meteo)", provenance.UNAVAILABLE,
            "Open-Meteo returned no daily records.", provider="Open-Meteo")
        return frame

    frame["wind_speed"] = pd.to_numeric(frame["wind_speed_kmh"],
                                        errors="coerce") * KMH_TO_KNOTS
    frame["wind_gust"] = pd.to_numeric(frame["wind_gust_kmh"],
                                       errors="coerce") * KMH_TO_KNOTS
    frame["visibility"] = pd.to_numeric(frame["visibility_m"],
                                        errors="coerce") / 1000.0
    frame = frame.drop(columns=["wind_speed_kmh", "wind_gust_kmh", "visibility_m"])

    if marine is not None:
        waves = _daily_frame(marine, ports, {"wave_height_max": "wave_height"})
        if not waves.empty:
            frame = frame.merge(waves, on=[PORT_ID, DATE], how="left")
    if "wave_height" not in frame.columns:
        frame["wave_height"] = np.nan

    today = pd.Timestamp.utcnow().normalize().tz_localize(None)
    frame["is_forecast"] = (frame[DATE] > today).astype(int)
    frame["storm_flag"] = 0.0

    # Extend backwards with the reanalysis archive when the caller needs more
    # history than the forecast endpoint retains (roughly two months).
    if history_start is not None:
        earliest = frame[DATE].min()
        archive = fetch_archive_weather(history_start,
                                        earliest - pd.Timedelta(days=1))
        if not archive.empty:
            frame = pd.concat([archive, frame], ignore_index=True)
            frame = frame.drop_duplicates(subset=[PORT_ID, DATE], keep="last")

    observed = frame.loc[frame["is_forecast"] == 0, DATE].max()
    mode = provenance.LIVE if surface_mode == "live" else provenance.CACHED_LIVE
    detail = ("Daily wind, gusts, precipitation, visibility and significant wave "
              f"height for {frame[PORT_ID].nunique()} ports "
              f"({past_days}d history + {forecast_days}d forecast).")
    if marine is None:
        detail += " Marine wave endpoint unavailable; wave risk falls back to a wind proxy."
    provenance.record(
        "Marine weather (Open-Meteo)", mode, detail,
        provider="Open-Meteo (ERA5 blend + ICON/GFS forecast)",
        observed_at=observed, rows=len(frame), freshness_hours=24.0,
        fallback=None if surface_mode == "live" else "local response cache")

    return frame.sort_values([PORT_ID, DATE]).reset_index(drop=True)


def merge_storm_flags(weather: pd.DataFrame,
                      storm_source: pd.DataFrame | None) -> pd.DataFrame:
    """Overlay GDACS storm severity onto the Open-Meteo frame."""
    if weather.empty or storm_source is None or storm_source.empty:
        return weather
    if "storm_flag" not in storm_source.columns:
        return weather
    flags = storm_source[[PORT_ID, DATE, "storm_flag"]].copy()
    flags[DATE] = pd.to_datetime(flags[DATE], errors="coerce")
    merged = weather.merge(flags.drop_duplicates([PORT_ID, DATE]),
                           on=[PORT_ID, DATE], how="left",
                           suffixes=("", "_gdacs"))
    merged["storm_flag"] = merged[["storm_flag", "storm_flag_gdacs"]].max(axis=1)
    return merged.drop(columns=["storm_flag_gdacs"], errors="ignore")
