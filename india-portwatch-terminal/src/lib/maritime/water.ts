/**
 * The water mask the routing graph was built on.
 *
 * Shipped so the running application, and the test suite, can ask the same
 * question the builder asked -- "is this point sea?" -- against exactly the same
 * raster. That is what makes "no route crosses land" a property the product can
 * prove rather than a claim about a script that ran once.
 */

import grid from "@/assets/geo/sea-grid.json";
import { haversineKm, type Position } from "./geo";

interface RawGrid {
  generatedAt: string;
  basis: string;
  method: string;
  grid: {
    minLon: number;
    minLat: number;
    maxLon: number;
    maxLat: number;
    step: number;
    cols: number;
    rows: number;
  };
  landCells: number;
  water: string;
}

const raw = grid as unknown as RawGrid;
export const SEA_GRID = raw.grid;

/** Base64 to bytes, without assuming a Buffer or an atob polyfill. */
function decode(base64: string): Uint8Array {
  if (typeof atob === "function") {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }
  // Node, during server rendering and in the test runner.
  return new Uint8Array(
    (globalThis as { Buffer?: { from(s: string, e: string): Uint8Array } }).Buffer!.from(
      base64,
      "base64",
    ),
  );
}

let bits: Uint8Array | null = null;

function mask(): Uint8Array {
  if (!bits) bits = decode(raw.water);
  return bits;
}

/**
 * Is this coordinate on water?
 *
 * Off-grid answers false. The grid covers the Indian Ocean theatre the product
 * operates in, and a router that treats the unknown as land will refuse to draw
 * rather than draw something wrong.
 */
export function isWater(lon: number, lat: number): boolean {
  const { minLon, minLat, step, cols, rows } = SEA_GRID;
  const col = Math.floor((lon - minLon) / step);
  const row = Math.floor((lat - minLat) / step);
  if (col < 0 || row < 0 || col >= cols || row >= rows) return false;
  const index = row * cols + col;
  return ((mask()[index >> 3] >> (index & 7)) & 1) === 1;
}

export function isLand(lon: number, lat: number): boolean {
  return !isWater(lon, lat);
}

/**
 * Where a polyline first leaves water, or null if it never does.
 *
 * `entryKm` at either end is exempt: those segments are the run between a quay
 * and the first water cell, and a quay is on the coast by definition.
 */
export function firstLandfall(
  coords: Position[],
  entryKm = 30,
  sampleKm = 2,
): Position | null {
  if (coords.length < 2) return null;
  let total = 0;
  for (let i = 0; i < coords.length - 1; i += 1) {
    total += haversineKm(coords[i], coords[i + 1]);
  }

  let travelled = 0;
  for (let i = 0; i < coords.length - 1; i += 1) {
    const a = coords[i];
    const b = coords[i + 1];
    const segmentKm = haversineKm(a, b);
    const steps = Math.max(1, Math.ceil(segmentKm / sampleKm));
    for (let s = 0; s <= steps; s += 1) {
      const f = s / steps;
      const along = travelled + segmentKm * f;
      if (along < entryKm || total - along < entryKm) continue;
      const lon = a[0] + (b[0] - a[0]) * f;
      const lat = a[1] + (b[1] - a[1]) * f;
      if (!isWater(lon, lat)) return [lon, lat];
    }
    travelled += segmentKm;
  }
  return null;
}

export function crossesLand(coords: Position[], entryKm = 30): boolean {
  return firstLandfall(coords, entryKm) !== null;
}

/**
 * The nearest water cell centre to a coordinate.
 *
 * Anchorage and holding positions are placed by bearing and range from a port,
 * which occasionally lands a mark inside a bay the raster calls land; nudging it
 * to real water is better than drawing a ship in a field.
 */
export function nudgeToWater(lon: number, lat: number, maxRings = 12): Position {
  if (isWater(lon, lat)) return [lon, lat];
  const { minLon, minLat, step, cols, rows } = SEA_GRID;
  const col0 = Math.floor((lon - minLon) / step);
  const row0 = Math.floor((lat - minLat) / step);
  for (let ring = 1; ring <= maxRings; ring += 1) {
    let best: Position | null = null;
    let bestKm = Infinity;
    for (let dc = -ring; dc <= ring; dc += 1) {
      for (let dr = -ring; dr <= ring; dr += 1) {
        if (Math.max(Math.abs(dc), Math.abs(dr)) !== ring) continue;
        const col = col0 + dc;
        const row = row0 + dr;
        if (col < 0 || row < 0 || col >= cols || row >= rows) continue;
        const candidate: Position = [
          minLon + (col + 0.5) * step,
          minLat + (row + 0.5) * step,
        ];
        if (!isWater(candidate[0], candidate[1])) continue;
        const km = haversineKm([lon, lat], candidate);
        if (km < bestKm) {
          bestKm = km;
          best = candidate;
        }
      }
    }
    if (best) return best;
  }
  return [lon, lat];
}
