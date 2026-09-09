/**
 * Small geometry helpers the map layers share.
 *
 * Rings and sectors only, in degrees, using a local scale factor rather than a
 * projection: at the radii these are used for -- an anchorage, a storm
 * envelope, a range ring around a ship -- the error is well under a pixel, and
 * a proper geodesic ring would cost a hundred destination-point solves per
 * feature per frame.
 */

import { destination, type Position } from "@/lib/maritime/geo";

const DEG = Math.PI / 180;

export function circleRing(centre: Position, radiusKm: number, steps = 72): Position[] {
  const ring: Position[] = [];
  const latScale = radiusKm / 110.574;
  const lonScale = radiusKm / (111.32 * Math.max(0.15, Math.cos(centre[1] * DEG)));
  for (let i = 0; i <= steps; i += 1) {
    const θ = (i / steps) * Math.PI * 2;
    ring.push([centre[0] + lonScale * Math.cos(θ), centre[1] + latScale * Math.sin(θ)]);
  }
  return ring;
}

/** A pie slice centred on `bearing`, used for approach sectors. */
export function sectorRing(
  centre: Position,
  radiusKm: number,
  bearing: number,
  halfAngle: number,
  steps = 40,
): Position[] {
  const ring: Position[] = [centre];
  for (let i = 0; i <= steps; i += 1) {
    const angle = bearing - halfAngle + ((halfAngle * 2) * i) / steps;
    ring.push(destination(centre, angle, radiusKm));
  }
  ring.push(centre);
  return ring;
}

/** A straight run out from a point on a bearing, for a fairway centreline. */
export function bearingLine(from: Position, bearing: number, km: number, steps = 8): Position[] {
  const out: Position[] = [];
  for (let i = 0; i <= steps; i += 1) {
    out.push(destination(from, bearing, (km * i) / steps));
  }
  return out;
}
