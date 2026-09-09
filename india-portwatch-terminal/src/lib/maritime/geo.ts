/**
 * Spherical geometry for the traffic layer.
 *
 * Everything here works in degrees in, degrees out, kilometres for distance and
 * degrees true for bearings, because that is what the rest of the maritime code
 * and every readout on screen speaks. Knots and nautical miles are converted at
 * the edge, never carried through the maths.
 */

export const EARTH_KM = 6371;
export const DEG = Math.PI / 180;
export const KM_PER_NM = 1.852;

export interface LonLat {
  lon: number;
  lat: number;
}

export type Position = [number, number];

export function haversineKm(a: Position, b: Position): number {
  const dLat = (b[1] - a[1]) * DEG;
  const dLon = (b[0] - a[0]) * DEG;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a[1] * DEG) * Math.cos(b[1] * DEG) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.sqrt(h));
}

export function kmBetween(a: LonLat, b: LonLat): number {
  return haversineKm([a.lon, a.lat], [b.lon, b.lat]);
}

export function nmBetween(a: LonLat, b: LonLat): number {
  return kmBetween(a, b) / KM_PER_NM;
}

/** Initial great-circle bearing from `a` to `b`, degrees true. */
export function bearingDeg(a: Position, b: Position): number {
  const φ1 = a[1] * DEG;
  const φ2 = b[1] * DEG;
  const Δλ = (b[0] - a[0]) * DEG;
  const y = Math.sin(Δλ) * Math.cos(φ2);
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
  return (Math.atan2(y, x) / DEG + 360) % 360;
}

export function destination(from: Position, bearing: number, km: number): Position {
  const δ = km / EARTH_KM;
  const θ = bearing * DEG;
  const φ1 = from[1] * DEG;
  const λ1 = from[0] * DEG;
  const φ2 = Math.asin(
    Math.sin(φ1) * Math.cos(δ) + Math.cos(φ1) * Math.sin(δ) * Math.cos(θ),
  );
  const λ2 =
    λ1 +
    Math.atan2(
      Math.sin(θ) * Math.sin(δ) * Math.cos(φ1),
      Math.cos(δ) - Math.sin(φ1) * Math.sin(φ2),
    );
  return [((λ2 / DEG + 540) % 360) - 180, φ2 / DEG];
}

/** Shortest signed difference between two bearings, in (-180, 180]. */
export function bearingDelta(from: number, to: number): number {
  return ((((to - from) % 360) + 540) % 360) - 180;
}

export function compassPoint(bearing: number): string {
  const points = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
  ];
  return points[Math.round((((bearing % 360) + 360) % 360) / 22.5) % 16];
}

/* --------------------------------------------------------------- routes -- */

/** A polyline with its cumulative along-track distance precomputed. */
export interface MeasuredPath {
  coords: Position[];
  /** `cumulative[i]` is the distance in km from the start to `coords[i]`. */
  cumulative: number[];
  km: number;
}

export function measurePath(coords: Position[]): MeasuredPath {
  const cumulative = new Array<number>(coords.length);
  cumulative[0] = 0;
  for (let i = 1; i < coords.length; i += 1) {
    cumulative[i] = cumulative[i - 1] + haversineKm(coords[i - 1], coords[i]);
  }
  return { coords, cumulative, km: cumulative[coords.length - 1] ?? 0 };
}

export interface PathFix {
  position: Position;
  /** Course over ground along the path at this point, degrees true. */
  course: number;
  /** Index of the segment the fix sits on. */
  segment: number;
}

/** Position and course at `km` along a measured path, clamped at both ends. */
export function fixAt(path: MeasuredPath, km: number): PathFix {
  const { coords, cumulative } = path;
  if (coords.length < 2) {
    return { position: coords[0] ?? [0, 0], course: 0, segment: 0 };
  }
  const target = Math.min(Math.max(km, 0), path.km);

  // Binary search: paths run to a few hundred points and this is called for
  // every vessel on every animation frame.
  let lo = 0;
  let hi = cumulative.length - 1;
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1;
    if (cumulative[mid] <= target) lo = mid;
    else hi = mid;
  }

  const a = coords[lo];
  const b = coords[lo + 1] ?? coords[lo];
  const span = (cumulative[lo + 1] ?? cumulative[lo]) - cumulative[lo];
  const f = span > 0 ? (target - cumulative[lo]) / span : 0;
  return {
    position: [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f],
    course: bearingDeg(a, b),
    segment: lo,
  };
}

/** The sub-path between two along-track distances, endpoints included. */
export function slicePath(path: MeasuredPath, fromKm: number, toKm: number): Position[] {
  const start = Math.min(Math.max(fromKm, 0), path.km);
  const end = Math.min(Math.max(toKm, 0), path.km);
  if (end <= start) return [fixAt(path, start).position];
  const out: Position[] = [fixAt(path, start).position];
  for (let i = 0; i < path.coords.length; i += 1) {
    if (path.cumulative[i] > start && path.cumulative[i] < end) out.push(path.coords[i]);
  }
  out.push(fixAt(path, end).position);
  return out;
}

/** Along-track distance of the point on the path nearest to `point`. */
export function nearestAlongKm(path: MeasuredPath, point: Position): number {
  let bestKm = 0;
  let bestDistance = Infinity;
  for (let i = 0; i < path.coords.length; i += 1) {
    const d = haversineKm(path.coords[i], point);
    if (d < bestDistance) {
      bestDistance = d;
      bestKm = path.cumulative[i];
    }
  }
  return bestKm;
}

/* ------------------------------------------------------------ CPA / TCPA -- */

export interface CpaResult {
  /** Distance at the closest point of approach, nautical miles. */
  cpaNm: number;
  /** Minutes until that point; negative means the vessels are opening. */
  tcpaMinutes: number;
  /** Present separation, nautical miles. */
  rangeNm: number;
  /** Bearing from own ship to the other, degrees true. */
  bearing: number;
}

/**
 * Closest point of approach under constant velocity.
 *
 * Straight relative-motion geometry on a local tangent plane: at the ranges a
 * CPA is worth reading (tens of nautical miles) the curvature error is far
 * below the error already in a simulated position, and the alternative -- an
 * iterative great-circle solve -- would imply a precision this data does not
 * have. Both vessels are assumed to hold course and speed, which is the
 * standard assumption and the reason a CPA is an advisory, not a prediction.
 */
export function closestPointOfApproach(
  own: { lon: number; lat: number; cog: number; sogKn: number },
  other: { lon: number; lat: number; cog: number; sogKn: number },
): CpaResult {
  const latScale = Math.cos(((own.lat + other.lat) / 2) * DEG);
  // Nautical miles east and north of own ship.
  const rx = (other.lon - own.lon) * 60 * latScale;
  const ry = (other.lat - own.lat) * 60;

  const velocity = (cog: number, sog: number) => [
    sog * Math.sin(cog * DEG),
    sog * Math.cos(cog * DEG),
  ];
  const [ovx, ovy] = velocity(own.cog, own.sogKn);
  const [tvx, tvy] = velocity(other.cog, other.sogKn);
  const vx = tvx - ovx;
  const vy = tvy - ovy;

  const rangeNm = Math.hypot(rx, ry);
  const bearing = (Math.atan2(rx, ry) / DEG + 360) % 360;
  const closingSq = vx * vx + vy * vy;

  if (closingSq < 1e-9) {
    return { cpaNm: rangeNm, tcpaMinutes: Infinity, rangeNm, bearing };
  }
  const tcpaHours = -(rx * vx + ry * vy) / closingSq;
  const cpaX = rx + vx * tcpaHours;
  const cpaY = ry + vy * tcpaHours;
  return {
    cpaNm: Math.hypot(cpaX, cpaY),
    tcpaMinutes: tcpaHours * 60,
    rangeNm,
    bearing,
  };
}

/* ----------------------------------------------------------- formatting -- */

export function formatBearing(bearing: number | null | undefined): string {
  if (bearing == null || Number.isNaN(bearing)) return "n/a";
  return `${Math.round(((bearing % 360) + 360) % 360)
    .toString()
    .padStart(3, "0")}°`;
}

export function formatPosition(lat: number, lon: number): string {
  const fmt = (value: number, positive: string, negative: string) => {
    const hemisphere = value >= 0 ? positive : negative;
    const abs = Math.abs(value);
    const degrees = Math.floor(abs);
    const minutes = (abs - degrees) * 60;
    return `${degrees}°${minutes.toFixed(1).padStart(4, "0")}'${hemisphere}`;
  };
  return `${fmt(lat, "N", "S")} ${fmt(lon, "E", "W")}`;
}

export function formatClock(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "--:--";
  const date = new Date(ms);
  return `${String(date.getUTCHours()).padStart(2, "0")}:${String(
    date.getUTCMinutes(),
  ).padStart(2, "0")}`;
}

/** "4h 20m", "26m", "3d 04h" — a duration a watchkeeper reads at a glance. */
export function formatDuration(minutes: number | null | undefined): string {
  if (minutes == null || !Number.isFinite(minutes)) return "n/a";
  const total = Math.max(0, Math.round(minutes));
  if (total < 60) return `${total}m`;
  const hours = Math.floor(total / 60);
  if (hours < 48) return `${hours}h ${String(total % 60).padStart(2, "0")}m`;
  return `${Math.floor(hours / 24)}d ${String(hours % 24).padStart(2, "0")}h`;
}
