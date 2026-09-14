"""The marine environment: sea state, swell, surface temperature and current.

The weather layer this product has carried so far is atmospheric and coarse
-- a forecast the pipeline exported for the ports. What a route runs through
is the sea: significant wave height that decides whether a hull slows, swell
that decides whether cargo shifts, a current that adds or removes a knot from
the day's run. None of that was in the model. This module puts it in, from a
real forecast service, at the granularity a route can be sampled at.

The service is Open-Meteo's Marine API. Its free tier is CC-BY data over a
service licensed for **non-commercial use only**, and its subscription tier
is the same data licensed for commercial use with a key. The adapter chooses
the product by whether ``OPEN_METEO_API_KEY`` is present and lets the
catalogue's policy for that product decide whether the deployment's mode may
use it. It never calls the free host from a COMMERCIAL deployment.

Three honesty rules shape what comes back:

*   A forecast cell says **when it is for** (``valid_at``) and **when we
    fetched it** (``fetched_at``). The service publishes no model-run time, so
    freshness is the fetch's age and the provenance says so.
*   Units are converted once, here, and named on the cell: metres, seconds,
    degrees true, Celsius, knots. The service's km/h currents become knots.
*   A cell never invents a value. A variable the service returned as null is
    ``None`` on the cell, and a sampler downstream reports it as unknown.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.fabric.adapters import Availability, BaseAdapter
from src.portwatch_os.fabric.model import AVAILABLE, CONFIGURABLE, MARINE, UNAVAILABLE
from src.portwatch_os.clock import wall_now

log = logging.getLogger(__name__)

FREE_HOST = "https://marine-api.open-meteo.com/v1/marine"
CUSTOMER_HOST = "https://customer-marine-api.open-meteo.com/v1/marine"
ENV_KEY = "OPEN_METEO_API_KEY"

#: The hourly variables asked for, in the service's names.
VARIABLES: Tuple[str, ...] = (
    "wave_height", "wave_direction", "wave_period",
    "swell_wave_height", "swell_wave_direction", "swell_wave_period",
    "wind_wave_height",
    "sea_surface_temperature",
    "ocean_current_velocity", "ocean_current_direction",
)
FORECAST_DAYS = 5
KMH_TO_KN = 0.539957

#: A fetched grid is reused for this long before the service is asked again.
DEFAULT_TTL = timedelta(hours=1)
#: A cell older than this is stale for the trust surface.
STALE_AFTER = 3 * 3600.0
#: Where the last good grid is written, so a restart shows the last known
#: sea state with its age rather than nothing.
CACHE_PATH = Path("data/cache/marine_forecast.json")


# --------------------------------------------------------------------------
# the cell
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MarineForecastCell:
    """One place, one hour, the sea as forecast."""

    lat: float
    lon: float
    valid_at: datetime
    fetched_at: datetime
    wave_height_m: Optional[float] = None
    wave_direction_deg: Optional[float] = None
    wave_period_s: Optional[float] = None
    swell_height_m: Optional[float] = None
    swell_direction_deg: Optional[float] = None
    swell_period_s: Optional[float] = None
    wind_wave_height_m: Optional[float] = None
    sst_c: Optional[float] = None
    current_speed_kn: Optional[float] = None
    current_direction_deg: Optional[float] = None
    provider_id: str = "open-meteo"
    product_id: str = "open-meteo-free"
    #: Where the grid point was requested; the service snaps to its grid.
    requested: Tuple[float, float] = (0.0, 0.0)
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lat": self.lat,
            "lon": self.lon,
            "validAt": self.valid_at.isoformat(),
            "fetchedAt": self.fetched_at.isoformat(),
            "waveHeightM": self.wave_height_m,
            "waveDirectionDeg": self.wave_direction_deg,
            "wavePeriodS": self.wave_period_s,
            "swellHeightM": self.swell_height_m,
            "swellDirectionDeg": self.swell_direction_deg,
            "swellPeriodS": self.swell_period_s,
            "windWaveHeightM": self.wind_wave_height_m,
            "sstC": self.sst_c,
            "currentSpeedKn": self.current_speed_kn,
            "currentDirectionDeg": self.current_direction_deg,
            "providerId": self.provider_id,
            "productId": self.product_id,
            "label": self.label,
        }


#: The points the grid is fetched for. Chokepoints, port approaches and the
#: open-water legs between them -- enough to sample any modelled route,
#: few enough for one request an hour on the free tier.
SAMPLE_POINTS: Tuple[Tuple[str, float, float], ...] = (
    # chokepoints
    ("HORMUZ", 26.6, 56.3), ("BAB_EL_MANDEB", 12.6, 43.3), ("SUEZ_SOUTH", 29.5, 32.6),
    ("MALACCA", 2.5, 101.0), ("MALACCA_NORTH", 6.0, 97.5),
    # Red Sea and Gulf of Aden
    ("RED_SEA_N", 24.0, 36.5), ("RED_SEA_S", 16.5, 40.5), ("ADEN", 12.5, 47.0),
    ("SOCOTRA", 12.0, 55.0),
    # Arabian Sea crossing
    ("ARABIAN_W", 15.0, 60.0), ("ARABIAN_C", 17.0, 65.0), ("ARABIAN_E", 18.0, 69.5),
    ("OMAN", 22.5, 61.0), ("GULF_OF_OMAN", 24.5, 58.5), ("PERSIAN_GULF", 26.5, 52.5),
    # west coast approaches
    ("INIXY", 22.6, 69.8), ("INMUN", 22.5, 69.4), ("INNSA", 18.8, 72.6), ("INBOM", 18.9, 72.7),
    ("INMRM", 15.3, 73.5), ("INNML", 12.9, 74.5), ("INCOK", 9.9, 76.0),
    # around the cape
    ("LAKSHADWEEP", 10.0, 73.0), ("COMORIN", 7.5, 77.5), ("MANNAR", 8.5, 79.0),
    # east coast approaches
    ("INTUT", 8.7, 78.4), ("INMAA", 13.1, 80.5), ("INENR", 13.3, 80.5),
    ("INVTZ", 17.6, 83.5), ("INPRT", 20.2, 87.0), ("INCCU", 21.3, 88.2),
    # Bay of Bengal and the approach from Malacca
    ("BENGAL_C", 15.0, 85.0), ("BENGAL_S", 10.0, 88.0), ("ANDAMAN", 10.0, 93.0),
    ("NICOBAR", 6.5, 94.0),
    # east Africa lane
    ("EAF_N", 5.0, 52.0), ("EAF_S", -2.0, 48.0), ("SEYCHELLES", -4.0, 58.0),
)


# --------------------------------------------------------------------------
# the grid
# --------------------------------------------------------------------------


class MarineGrid:
    """Cells by point and hour, with nearest-point / nearest-hour sampling."""

    def __init__(self, cells: Iterable[MarineForecastCell] = ()) -> None:
        self._by_point: Dict[Tuple[float, float], List[MarineForecastCell]] = {}
        self.fetched_at: Optional[datetime] = None
        self.product_id: Optional[str] = None
        for cell in cells:
            self.add(cell)

    def add(self, cell: MarineForecastCell) -> None:
        bucket = self._by_point.setdefault(cell.requested, [])
        bucket.append(cell)
        bucket.sort(key=lambda c: c.valid_at)
        if self.fetched_at is None or cell.fetched_at > self.fetched_at:
            self.fetched_at = cell.fetched_at
        self.product_id = cell.product_id

    def __len__(self) -> int:
        return sum(len(b) for b in self._by_point.values())

    @property
    def points(self) -> List[Tuple[float, float]]:
        return list(self._by_point)

    @property
    def horizon(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        stamps = [c.valid_at for b in self._by_point.values() for c in b]
        return (min(stamps), max(stamps)) if stamps else (None, None)

    def cells(self) -> List[MarineForecastCell]:
        return [c for b in self._by_point.values() for c in b]

    def at(self, moment: datetime) -> List[MarineForecastCell]:
        """One cell per point: the hour nearest `moment`."""
        out: List[MarineForecastCell] = []
        for bucket in self._by_point.values():
            nearest = min(bucket, key=lambda c: abs((c.valid_at - moment).total_seconds()))
            out.append(nearest)
        return out

    def sample(self, lat: float, lon: float, moment: datetime) -> Optional["MarineSample"]:
        """The nearest point's nearest hour, with how far off both are."""
        if not self._by_point:
            return None
        from src.portwatch_os.world.observed import haversine_nm

        point = min(self._by_point, key=lambda p: haversine_nm(lat, lon, p[0], p[1]))
        bucket = self._by_point[point]
        nearest = min(bucket, key=lambda c: abs((c.valid_at - moment).total_seconds()))
        return MarineSample(
            cell=nearest,
            distance_nm=round(haversine_nm(lat, lon, point[0], point[1]), 1),
            hours_off=round((moment - nearest.valid_at).total_seconds() / 3600.0, 2),
        )

    # -- persistence -----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "fetchedAt": None if self.fetched_at is None else self.fetched_at.isoformat(),
            "productId": self.product_id,
            "cells": [c.to_dict() | {"requested": list(c.requested)} for c in self.cells()],
        }

    @classmethod
    def from_dict(cls, body: Dict[str, Any]) -> "MarineGrid":
        grid = cls()
        for row in body.get("cells", []):
            grid.add(MarineForecastCell(
                lat=row["lat"], lon=row["lon"],
                valid_at=datetime.fromisoformat(row["validAt"]),
                fetched_at=datetime.fromisoformat(row["fetchedAt"]),
                wave_height_m=row.get("waveHeightM"), wave_direction_deg=row.get("waveDirectionDeg"),
                wave_period_s=row.get("wavePeriodS"), swell_height_m=row.get("swellHeightM"),
                swell_direction_deg=row.get("swellDirectionDeg"), swell_period_s=row.get("swellPeriodS"),
                wind_wave_height_m=row.get("windWaveHeightM"), sst_c=row.get("sstC"),
                current_speed_kn=row.get("currentSpeedKn"), current_direction_deg=row.get("currentDirectionDeg"),
                provider_id=row.get("providerId", "open-meteo"), product_id=row.get("productId", "open-meteo-free"),
                requested=tuple(row.get("requested", (row["lat"], row["lon"]))),
                label=row.get("label", ""),
            ))
        return grid


@dataclass(frozen=True)
class MarineSample:
    cell: MarineForecastCell
    #: How far the sampled point is from the grid point that answered.
    distance_nm: float
    #: How far the asked instant is from the cell's hour. Positive = later.
    hours_off: float

    def to_dict(self) -> Dict[str, Any]:
        return {"cell": self.cell.to_dict(), "distanceNm": self.distance_nm, "hoursOff": self.hours_off}


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_response(
    payload: Any,
    *,
    requested: Sequence[Tuple[str, float, float]],
    fetched_at: datetime,
    product_id: str,
) -> List[MarineForecastCell]:
    """The service's hourly arrays into cells. Nulls stay None."""
    rows = payload if isinstance(payload, list) else [payload]
    cells: List[MarineForecastCell] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or "hourly" not in row:
            continue
        # Multi-location responses carry location_id; a single one does not.
        position = int(row.get("location_id", index))
        label, req_lat, req_lon = requested[position] if position < len(requested) else ("", 0.0, 0.0)
        hourly = row["hourly"]
        times = hourly.get("time") or []
        for i, stamp in enumerate(times):
            try:
                valid = datetime.fromisoformat(str(stamp))
            except ValueError:
                continue
            if valid.tzinfo is None:
                valid = valid.replace(tzinfo=timezone.utc)

            def pick(name: str) -> Optional[float]:
                series = hourly.get(name) or []
                return _num(series[i]) if i < len(series) else None

            current_kmh = pick("ocean_current_velocity")
            cells.append(MarineForecastCell(
                lat=float(row.get("latitude", req_lat)),
                lon=float(row.get("longitude", req_lon)),
                valid_at=valid,
                fetched_at=fetched_at,
                wave_height_m=pick("wave_height"),
                wave_direction_deg=pick("wave_direction"),
                wave_period_s=pick("wave_period"),
                swell_height_m=pick("swell_wave_height"),
                swell_direction_deg=pick("swell_wave_direction"),
                swell_period_s=pick("swell_wave_period"),
                wind_wave_height_m=pick("wind_wave_height"),
                sst_c=pick("sea_surface_temperature"),
                current_speed_kn=None if current_kmh is None else round(current_kmh * KMH_TO_KN, 2),
                current_direction_deg=pick("ocean_current_direction"),
                product_id=product_id,
                requested=(req_lat, req_lon),
                label=label,
            ))
    return cells


# --------------------------------------------------------------------------
# the service
# --------------------------------------------------------------------------


Fetcher = Callable[[str], Any]


def _http_fetch(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "portwatch-x/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


class MarineService:
    """Fetches, caches and serves the marine grid for the sample points.

    One instance per process. `grid()` returns the cached grid when it is
    younger than the TTL, refreshes it when it is not, and falls back to the
    last good grid -- age and all -- when the refresh fails. A grid is never
    fabricated: with no successful fetch ever, there is no grid.
    """

    def __init__(
        self,
        *,
        points: Sequence[Tuple[str, float, float]] = SAMPLE_POINTS,
        fetcher: Optional[Fetcher] = None,
        ttl: timedelta = DEFAULT_TTL,
        cache_path: Optional[Path] = CACHE_PATH,
        api_key: Optional[str] = None,
    ) -> None:
        self.points = list(points)
        self._fetcher = fetcher or _http_fetch
        self.ttl = ttl
        self.cache_path = cache_path
        self._api_key = api_key if api_key is not None else os.getenv(ENV_KEY)
        self._grid: Optional[MarineGrid] = None
        self._lock = threading.Lock()
        self.last_error: Optional[str] = None
        self.last_attempt_at: Optional[datetime] = None
        self.fetches = 0
        self.failures = 0

    @property
    def product_id(self) -> str:
        return "open-meteo-customer" if self._api_key else "open-meteo-free"

    def url(self) -> str:
        host = CUSTOMER_HOST if self._api_key else FREE_HOST
        params = {
            "latitude": ",".join(f"{lat:.3f}" for _, lat, _ in self.points),
            "longitude": ",".join(f"{lon:.3f}" for _, _, lon in self.points),
            "hourly": ",".join(VARIABLES),
            "forecast_days": str(FORECAST_DAYS),
            "timezone": "UTC",
        }
        if self._api_key:
            params["apikey"] = self._api_key
        return f"{host}?{urllib.parse.urlencode(params)}"

    def _load_cache(self) -> None:
        if self._grid is not None or self.cache_path is None or not self.cache_path.exists():
            return
        try:
            body = json.loads(self.cache_path.read_text(encoding="utf-8"))
            grid = MarineGrid.from_dict(body)
            if len(grid):
                self._grid = grid
        except Exception as exc:  # noqa: BLE001 - an unreadable cache is no cache
            log.info("marine cache unreadable: %s", exc)

    def _save_cache(self, grid: MarineGrid) -> None:
        if self.cache_path is None:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(grid.to_dict()), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - failing to cache is not failing to serve
            log.info("marine cache not written: %s", exc)

    def refresh(self, *, now: Optional[datetime] = None) -> Optional[MarineGrid]:
        """Ask the service. Returns the new grid, or None and records why not."""
        moment = now or wall_now()  # wall-clock: a fetch happens in the real present
        self.last_attempt_at = moment
        self.fetches += 1
        try:
            payload = self._fetcher(self.url())
            cells = parse_response(payload, requested=self.points, fetched_at=moment,
                                   product_id=self.product_id)
            if not cells:
                raise ValueError("the response carried no hourly cells")
            grid = MarineGrid(cells)
            self._grid = grid
            self.last_error = None
            self._save_cache(grid)
            return grid
        except Exception as exc:  # noqa: BLE001 - every failure is a status
            self.failures += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            log.warning("marine forecast fetch failed: %s", self.last_error)
            return None

    def grid(self, *, now: Optional[datetime] = None, allow_fetch: bool = True) -> Optional[MarineGrid]:
        moment = now or wall_now()  # wall-clock: the TTL is a fetch cadence, not a world age
        with self._lock:
            self._load_cache()
            fresh = (
                self._grid is not None
                and self._grid.fetched_at is not None
                and moment - self._grid.fetched_at <= self.ttl
            )
            if fresh or not allow_fetch:
                return self._grid
            refreshed = self.refresh(now=moment)
            return refreshed if refreshed is not None else self._grid

    def status(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        moment = now or wall_now()  # wall-clock: the feed's fetch age is measured against the wall
        grid = self._grid
        lo, hi = grid.horizon if grid else (None, None)
        return {
            "productId": self.product_id,
            "points": len(self.points),
            "cells": 0 if grid is None else len(grid),
            "fetchedAt": None if grid is None or grid.fetched_at is None else grid.fetched_at.isoformat(),
            "ageSeconds": (
                None if grid is None or grid.fetched_at is None
                else round((moment - grid.fetched_at).total_seconds(), 1)
            ),
            "horizon": [None if lo is None else lo.isoformat(), None if hi is None else hi.isoformat()],
            "lastError": self.last_error,
            "lastAttemptAt": None if self.last_attempt_at is None else self.last_attempt_at.isoformat(),
            "fetches": self.fetches,
            "failures": self.failures,
        }


_SERVICE: Optional[MarineService] = None
_SERVICE_LOCK = threading.Lock()


def get_service() -> MarineService:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = MarineService()
        return _SERVICE


def set_service(service: Optional[MarineService]) -> None:
    """Install a scripted service. For tests."""
    global _SERVICE
    with _SERVICE_LOCK:
        _SERVICE = service


_REFRESHER: Optional[threading.Thread] = None
_REFRESH_STOP = threading.Event()


def start_refresher(*, interval: Optional[timedelta] = None) -> None:
    """Keep the process's grid within its TTL from a background thread.

    Runs under the deployment's own licence mode: a COMMERCIAL deployment
    without a key never calls the free host, because that would be using the
    non-commercial service commercially whether or not anyone read the result.
    """
    global _REFRESHER
    from src.portwatch_os.fabric.model import deployment_mode

    service = get_service()
    adapter = OpenMeteoMarineAdapter(licence_mode=deployment_mode(), service=service)
    if adapter.licence_gate() is not None:
        log.info("marine refresher not started: %s", adapter.licence_gate().reason)
        return
    if _REFRESHER is not None and _REFRESHER.is_alive():
        return
    every = (interval or service.ttl).total_seconds()
    _REFRESH_STOP.clear()

    def run() -> None:
        while not _REFRESH_STOP.is_set():
            service.grid()
            _REFRESH_STOP.wait(every)

    _REFRESHER = threading.Thread(target=run, name="marine-refresh", daemon=True)
    _REFRESHER.start()


def stop_refresher() -> None:
    _REFRESH_STOP.set()


# --------------------------------------------------------------------------
# the adapter
# --------------------------------------------------------------------------


class OpenMeteoMarineAdapter(BaseAdapter):
    """Sea state from Open-Meteo Marine, under the product the deployment may use.

    The licence gate chooses first: the free product is barred from a
    COMMERCIAL or GOVERNMENT deployment by the catalogue's verified policy,
    and the adapter yields nothing there rather than calling the free host
    anyway. With a key the customer product applies and the same data comes
    from the paid host.
    """

    provider_id = "open-meteo"
    capability = MARINE
    coverage = "Indian Ocean sample grid: chokepoints, approaches, open-water legs"
    stale_after_seconds = STALE_AFTER

    def __init__(self, *, licence_mode: str = "RESEARCH", service: Optional[MarineService] = None) -> None:
        super().__init__(licence_mode=licence_mode)
        self._service = service

    @property
    def service(self) -> MarineService:
        return self._service or get_service()

    @property
    def product_id(self) -> str:
        return self.service.product_id

    def licence_gate(self) -> Optional[Availability]:
        from src.portwatch_os.fabric.registry import get_fabric

        product = get_fabric(self.licence_mode).product(self.product_id)
        if product is None:
            return None
        permitted, reason = product.policy.permits(self.licence_mode)
        if permitted:
            return None
        return Availability(
            UNAVAILABLE,
            reason=f"{product.name}: {reason}",
            needs=(f"{ENV_KEY} for the Open-Meteo API subscription",),
        )

    def availability(self) -> Availability:
        barred = self.licence_gate()
        if barred is not None:
            return barred
        grid = self.service.grid(allow_fetch=False)
        if grid is None:
            status = self.service.status()
            if status["lastError"]:
                return Availability(
                    UNAVAILABLE,
                    reason=f"no marine grid has been fetched: {status['lastError']}",
                )
            return Availability(
                CONFIGURABLE,
                reason="no marine grid has been fetched yet in this process",
                needs=("the first successful Open-Meteo Marine fetch",),
            )
        return Availability(AVAILABLE, reason=f"{len(grid)} forecast cells over {len(grid.points)} points")

    def _read(self, *, now: datetime):
        grid = self.service.grid(now=now, allow_fetch=False)
        if grid is None or grid.fetched_at is None:
            return []
        lo, hi = grid.horizon
        # One observation for the grid as a whole, dated when it was fetched:
        # the service publishes no model-run time, and a cell-by-cell
        # observation list would put thousands of rows on the trust surface.
        return [(
            {"cells": len(grid), "points": len(grid.points),
             "horizon": [lo.isoformat() if lo else None, hi.isoformat() if hi else None],
             "productId": grid.product_id},
            grid.fetched_at,
            {"basis": "fetch time; the service publishes no model-run time",
             "model_run_time_known": False},
        )]


__all__ = [
    "CACHE_PATH",
    "CUSTOMER_HOST",
    "DEFAULT_TTL",
    "ENV_KEY",
    "FREE_HOST",
    "MarineForecastCell",
    "MarineGrid",
    "MarineSample",
    "MarineService",
    "OpenMeteoMarineAdapter",
    "SAMPLE_POINTS",
    "VARIABLES",
    "get_service",
    "parse_response",
    "set_service",
    "start_refresher",
    "stop_refresher",
]
