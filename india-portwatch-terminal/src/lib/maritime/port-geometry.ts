/**
 * Where the sea is, relative to a port.
 *
 * Anchorages, approach sectors and fairways all need one number that the port
 * registry does not carry: the bearing of open water from the quay. The `coast`
 * field is too coarse to place them -- "east coast" covers Chennai's
 * east-north-easterly approach, Paradip's south-easterly one and Kolkata's
 * hundred-kilometre river -- so the bearing is read off the shipped water mask
 * instead, and cached because it never changes.
 */

import { DEG, destination } from "./geo";
import { isWater } from "./water";

const cache = new Map<string, number>();

export function seawardBearing(key: string, lon: number, lat: number): number {
  const cached = cache.get(key);
  if (cached !== undefined) return cached;

  /*
   * The bearing of the water's centre of mass, not the first clear ray.
   *
   * Scanning rays and keeping the longest run of water ties constantly -- from
   * Chennai, due north and due east are both open for forty kilometres -- and a
   * tie broken by the lowest bearing pointed the approach sector up the coast
   * instead of out to sea. Averaging the direction of every water sample in a
   * disc has no ties to break and lands on the true seaward heading.
   */
  let x = 0;
  let y = 0;
  for (let bearing = 0; bearing < 360; bearing += 6) {
    for (let km = 6; km <= 70; km += 4) {
      const point = destination([lon, lat], bearing, km);
      if (!isWater(point[0], point[1])) continue;
      // Weight by range so open ocean counts for more than a sheltered bay.
      const weight = km;
      x += Math.sin(bearing * DEG) * weight;
      y += Math.cos(bearing * DEG) * weight;
    }
  }

  const best = x === 0 && y === 0 ? 90 : (Math.atan2(x, y) / DEG + 360) % 360;
  cache.set(key, best);
  return best;
}

/**
 * How far offshore a port's anchorage sits.
 *
 * Scaled by the number of vessels the AIS aggregate counted waiting and by the
 * queue pressure the pipeline measured, so a congested port's holding area is
 * visibly larger than a quiet one's. It is a pressure diagram drawn in the right
 * place, not a survey, and every screen that shows it says so.
 */
export function anchorageRadiusKm(anchorageCount: number | null, queuePressure: number | null): number {
  return 7 + Math.min(20, (anchorageCount ?? 0) * 2.6 + (queuePressure ?? 0) * 13);
}
