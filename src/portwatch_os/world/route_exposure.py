"""Route × environment: what sea a passage will actually run through.

A route is a line on a chart. A passage is that line at the hours a hull will
be on each part of it, and the sea is different at each of those hours. This
module walks a route at a vessel's speed, samples the marine grid at the
place *and the time* the vessel would be there, and reports what it found as
a profile: where the seas are heaviest, how much of the run is in head seas,
what the current gives or takes, and how many hours the sea state adds.

Every number is graded. A sample says how far its grid point was and how far
off its forecast hour was; the profile's coverage is the share of samples
with a usable cell; and the added-hours figure is a documented heuristic with
the confidence a heuristic deserves, not a routing engine's promise.

The speed-loss heuristic: involuntary speed loss in head seas is of the
order of one knot per metre of significant wave height for a laden
merchant hull, roughly half that in beam seas and a fifth in following
seas, and it saturates -- no hull loses more than about forty percent of
its service speed to weather before the master slows down deliberately,
which is a different decision. Those coefficients are order-of-magnitude
figures from the seakeeping literature, not this hull's curve, and the
profile says so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.fabric.marine import MarineGrid, MarineSample
from src.portwatch_os.world.observed import bearing_deg, haversine_nm

#: Spacing of samples along the route.
DEFAULT_STEP_NM = 60.0
#: A cell further than this from the sample, or further than this many
#: hours from the sample's ETA, does not count as covering it.
MAX_CELL_DISTANCE_NM = 200.0
MAX_HOURS_OFF = 1.5

#: Sea-state thresholds, significant wave height in metres.
ROUGH_M = 2.5
HEAVY_M = 4.0
VERY_HEAVY_M = 6.0

#: Speed-loss coefficients, knots per metre of significant wave height.
LOSS_HEAD_KN_PER_M = 0.9
LOSS_BEAM_KN_PER_M = 0.45
LOSS_FOLLOWING_KN_PER_M = 0.2
MAX_LOSS_FRACTION = 0.4
HEURISTIC_CONFIDENCE = 0.5


def _relative_angle(heading: float, wave_from: float) -> float:
    """Angle between the hull's heading and where the waves come from, 0..180.

    0 is head seas (waves coming from dead ahead), 180 is following seas.
    """
    return abs((wave_from - heading + 180.0) % 360.0 - 180.0)


def _sea_aspect(relative: float) -> str:
    if relative <= 45.0:
        return "HEAD"
    if relative >= 135.0:
        return "FOLLOWING"
    return "BEAM"


def _speed_loss_kn(wave_m: Optional[float], aspect: Optional[str], speed_kn: float) -> Optional[float]:
    if wave_m is None or aspect is None:
        return None
    rate = {"HEAD": LOSS_HEAD_KN_PER_M, "BEAM": LOSS_BEAM_KN_PER_M, "FOLLOWING": LOSS_FOLLOWING_KN_PER_M}[aspect]
    return round(min(wave_m * rate, speed_kn * MAX_LOSS_FRACTION), 2)


@dataclass(frozen=True)
class RouteSample:
    """One point on the passage, at the hour the hull reaches it."""

    index: int
    lat: float
    lon: float
    distance_nm: float
    eta: datetime
    heading_deg: float
    sample: Optional[MarineSample]
    covered: bool
    aspect: Optional[str]
    relative_wave_deg: Optional[float]
    current_along_kn: Optional[float]
    current_across_kn: Optional[float]
    speed_loss_kn: Optional[float]

    @property
    def wave_m(self) -> Optional[float]:
        return None if self.sample is None else self.sample.cell.wave_height_m

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "lat": round(self.lat, 4),
            "lon": round(self.lon, 4),
            "distanceNm": round(self.distance_nm, 1),
            "eta": self.eta.isoformat(),
            "headingDeg": round(self.heading_deg, 1),
            "covered": self.covered,
            "cell": None if self.sample is None else self.sample.cell.to_dict(),
            "cellDistanceNm": None if self.sample is None else self.sample.distance_nm,
            "hoursOff": None if self.sample is None else self.sample.hours_off,
            "aspect": self.aspect,
            "relativeWaveDeg": self.relative_wave_deg,
            "currentAlongKn": self.current_along_kn,
            "currentAcrossKn": self.current_across_kn,
            "speedLossKn": self.speed_loss_kn,
        }


@dataclass
class RouteExposureProfile:
    """The passage, summarised, with the samples it was summarised from."""

    waypoints: List[Tuple[float, float]]
    departs_at: datetime
    speed_kn: float
    total_nm: float
    nominal_hours: float
    samples: List[RouteSample] = field(default_factory=list)

    # -- coverage ---------------------------------------------------------
    @property
    def coverage(self) -> float:
        return 0.0 if not self.samples else sum(1 for s in self.samples if s.covered) / len(self.samples)

    @property
    def covered(self) -> List[RouteSample]:
        return [s for s in self.samples if s.covered]

    # -- sea state ----------------------------------------------------------
    @property
    def max_wave(self) -> Optional[RouteSample]:
        rows = [s for s in self.covered if s.wave_m is not None]
        return max(rows, key=lambda s: s.wave_m) if rows else None

    @property
    def mean_wave_m(self) -> Optional[float]:
        rows = [s.wave_m for s in self.covered if s.wave_m is not None]
        return round(sum(rows) / len(rows), 2) if rows else None

    @property
    def max_swell_m(self) -> Optional[float]:
        rows = [s.sample.cell.swell_height_m for s in self.covered
                if s.sample and s.sample.cell.swell_height_m is not None]
        return max(rows) if rows else None

    def hours_above(self, threshold_m: float) -> float:
        step = self._hours_per_sample()
        return round(sum(step for s in self.covered if s.wave_m is not None and s.wave_m >= threshold_m), 1)

    def hours_in(self, aspect: str, *, above_m: float = 0.0) -> float:
        step = self._hours_per_sample()
        return round(sum(step for s in self.covered
                         if s.aspect == aspect and s.wave_m is not None and s.wave_m >= above_m), 1)

    def _hours_per_sample(self) -> float:
        return 0.0 if len(self.samples) < 2 else self.nominal_hours / (len(self.samples) - 1)

    # -- current and time -----------------------------------------------------
    @property
    def mean_current_along_kn(self) -> Optional[float]:
        rows = [s.current_along_kn for s in self.covered if s.current_along_kn is not None]
        return round(sum(rows) / len(rows), 2) if rows else None

    @property
    def added_hours(self) -> Optional[float]:
        """Hours the sea state adds to the nominal passage, by the heuristic.

        Integrates the speed loss and the along-track current over the
        covered samples; uncovered samples contribute nothing, which is why
        the coverage travels with the figure.
        """
        rows = [s for s in self.covered if s.speed_loss_kn is not None]
        if not rows:
            return None
        step = self._hours_per_sample()
        added = 0.0
        for s in rows:
            effective = self.speed_kn - s.speed_loss_kn + (s.current_along_kn or 0.0)
            effective = max(effective, self.speed_kn * (1.0 - MAX_LOSS_FRACTION))
            leg_nm = self.speed_kn * step
            added += leg_nm / effective - step
        return round(added, 2)

    @property
    def flags(self) -> List[str]:
        flags: List[str] = []
        worst = self.max_wave
        if worst is not None and worst.wave_m is not None:
            if worst.wave_m >= VERY_HEAVY_M:
                flags.append("VERY_HEAVY_SEAS")
            elif worst.wave_m >= HEAVY_M:
                flags.append("HEAVY_SEAS")
            elif worst.wave_m >= ROUGH_M:
                flags.append("ROUGH_SEAS")
        if self.hours_in("HEAD", above_m=ROUGH_M) >= 6.0:
            flags.append("SUSTAINED_HEAD_SEAS")
        current = self.mean_current_along_kn
        if current is not None and current <= -0.75:
            flags.append("ADVERSE_CURRENT")
        elif current is not None and current >= 0.75:
            flags.append("FAVOURABLE_CURRENT")
        if self.coverage < 0.5:
            flags.append("LOW_COVERAGE")
        beyond = [s for s in self.samples if not s.covered and s.sample is not None and s.sample.hours_off > MAX_HOURS_OFF]
        if beyond:
            flags.append("BEYOND_FORECAST_HORIZON")
        return flags

    @property
    def confidence(self) -> float:
        """Coverage times the heuristic's own confidence. Never above 0.5."""
        return round(self.coverage * HEURISTIC_CONFIDENCE, 3)

    def to_dict(self, *, include_samples: bool = True) -> Dict[str, Any]:
        worst = self.max_wave
        return {
            "waypoints": [[round(a, 4), round(b, 4)] for a, b in self.waypoints],
            "departsAt": self.departs_at.isoformat(),
            "speedKn": self.speed_kn,
            "totalNm": round(self.total_nm, 1),
            "nominalHours": round(self.nominal_hours, 1),
            "coverage": round(self.coverage, 3),
            "confidence": self.confidence,
            "maxWaveM": None if worst is None else worst.wave_m,
            "maxWaveAt": None if worst is None else {
                "lat": round(worst.lat, 4), "lon": round(worst.lon, 4),
                "eta": worst.eta.isoformat(), "distanceNm": round(worst.distance_nm, 1),
                "aspect": worst.aspect,
            },
            "meanWaveM": self.mean_wave_m,
            "maxSwellM": self.max_swell_m,
            "hoursRough": self.hours_above(ROUGH_M),
            "hoursHeavy": self.hours_above(HEAVY_M),
            "hoursHeadSeasRough": self.hours_in("HEAD", above_m=ROUGH_M),
            "meanCurrentAlongKn": self.mean_current_along_kn,
            "addedHours": self.added_hours,
            "flags": self.flags,
            "method": (
                f"sampled every {DEFAULT_STEP_NM:.0f} nm at the hour of arrival; speed loss "
                f"{LOSS_HEAD_KN_PER_M} kn/m head, {LOSS_BEAM_KN_PER_M} beam, "
                f"{LOSS_FOLLOWING_KN_PER_M} following, capped at {MAX_LOSS_FRACTION:.0%}; "
                "order-of-magnitude seakeeping figures, not this hull's curve"
            ),
            "samples": [s.to_dict() for s in self.samples] if include_samples else None,
            "sampleCount": len(self.samples),
        }


# --------------------------------------------------------------------------
# walking the route
# --------------------------------------------------------------------------


def _interpolate(a: Tuple[float, float], b: Tuple[float, float], fraction: float) -> Tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction)


def walk(waypoints: Sequence[Tuple[float, float]], *, step_nm: float) -> List[Tuple[float, float, float, float]]:
    """Points along the route: (lat, lon, distance_from_start_nm, heading_deg)."""
    if len(waypoints) < 2:
        return [(waypoints[0][0], waypoints[0][1], 0.0, 0.0)] if waypoints else []
    out: List[Tuple[float, float, float, float]] = []
    travelled = 0.0
    for a, b in zip(waypoints, waypoints[1:]):
        leg = haversine_nm(a[0], a[1], b[0], b[1])
        heading = bearing_deg(a[0], a[1], b[0], b[1])
        steps = max(1, int(math.ceil(leg / step_nm)))
        for i in range(steps):
            fraction = i / steps
            lat, lon = _interpolate(a, b, fraction)
            out.append((lat, lon, travelled + leg * fraction, heading))
        travelled += leg
    last = waypoints[-1]
    out.append((last[0], last[1], travelled, out[-1][3] if out else 0.0))
    return out


def sample_route(
    waypoints: Sequence[Tuple[float, float]],
    *,
    grid: Optional[MarineGrid],
    departs_at: datetime,
    speed_kn: float,
    step_nm: float = DEFAULT_STEP_NM,
) -> RouteExposureProfile:
    """The passage along `waypoints` from `departs_at` at `speed_kn`, sampled."""
    points = walk(list(waypoints), step_nm=step_nm)
    total = points[-1][2] if points else 0.0
    speed = max(speed_kn, 0.1)
    profile = RouteExposureProfile(
        waypoints=list(waypoints), departs_at=departs_at, speed_kn=speed_kn,
        total_nm=total, nominal_hours=total / speed,
    )
    for index, (lat, lon, distance, heading) in enumerate(points):
        eta = departs_at + timedelta(hours=distance / speed)
        found = grid.sample(lat, lon, eta) if grid is not None else None
        covered = (
            found is not None
            and found.distance_nm <= MAX_CELL_DISTANCE_NM
            and abs(found.hours_off) <= MAX_HOURS_OFF
        )
        aspect = relative = along = across = loss = None
        if covered and found is not None:
            cell = found.cell
            if cell.wave_direction_deg is not None:
                relative = round(_relative_angle(heading, cell.wave_direction_deg), 1)
                aspect = _sea_aspect(relative)
            if cell.current_speed_kn is not None and cell.current_direction_deg is not None:
                # Current direction is where it flows *to*; along-track is
                # positive when it helps.
                delta = math.radians(cell.current_direction_deg - heading)
                along = round(cell.current_speed_kn * math.cos(delta), 2)
                across = round(cell.current_speed_kn * math.sin(delta), 2)
            loss = _speed_loss_kn(cell.wave_height_m, aspect, speed)
        profile.samples.append(RouteSample(
            index=index, lat=lat, lon=lon, distance_nm=distance, eta=eta, heading_deg=heading,
            sample=found, covered=bool(covered), aspect=aspect, relative_wave_deg=relative,
            current_along_kn=along, current_across_kn=across, speed_loss_kn=loss,
        ))
    return profile


__all__ = [
    "DEFAULT_STEP_NM",
    "HEAVY_M",
    "HEURISTIC_CONFIDENCE",
    "MAX_CELL_DISTANCE_NM",
    "MAX_HOURS_OFF",
    "ROUGH_M",
    "RouteExposureProfile",
    "RouteSample",
    "VERY_HEAVY_M",
    "sample_route",
    "walk",
]
