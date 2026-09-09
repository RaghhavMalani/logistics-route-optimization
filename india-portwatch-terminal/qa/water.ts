/**
 * The shipped water mask, for the test runner.
 *
 * Tests read the same asset the application does, from disk, so "this route is
 * on water" means exactly what it means at runtime. Nothing here re-derives a
 * coastline: if the raster and the routes ever disagree, the test fails rather
 * than quietly measuring something else.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const GEO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "src", "assets", "geo");

interface RawGrid {
  grid: {
    minLon: number;
    minLat: number;
    maxLon: number;
    maxLat: number;
    step: number;
    cols: number;
    rows: number;
  };
  water: string;
  generatedAt: string;
  basis: string;
  method: string;
  disclaimer: string;
}

export interface RawLeg {
  from: string;
  to: string;
  km: number;
  entryKm: number;
  coords: Array<[number, number]>;
}

interface RawRoutes {
  generatedAt: string;
  disclaimer: string;
  waypoints: Record<string, { name: string; lat: number; lon: number; kind: string }>;
  legs: Record<string, RawLeg>;
}

const gridDoc = JSON.parse(fs.readFileSync(path.join(GEO, "sea-grid.json"), "utf8")) as RawGrid;
export const routesDoc = JSON.parse(
  fs.readFileSync(path.join(GEO, "sea-routes.json"), "utf8"),
) as RawRoutes;

const GRID = gridDoc.grid;
const BITS = Buffer.from(gridDoc.water, "base64");

export function isWater(lon: number, lat: number): boolean {
  const col = Math.floor((lon - GRID.minLon) / GRID.step);
  const row = Math.floor((lat - GRID.minLat) / GRID.step);
  if (col < 0 || row < 0 || col >= GRID.cols || row >= GRID.rows) return false;
  const index = row * GRID.cols + col;
  return ((BITS[index >> 3] >> (index & 7)) & 1) === 1;
}

const DEG = Math.PI / 180;

export function haversineKm(a: [number, number], b: [number, number]): number {
  const dLat = (b[1] - a[1]) * DEG;
  const dLon = (b[0] - a[0]) * DEG;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a[1] * DEG) * Math.cos(b[1] * DEG) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

/**
 * Where a polyline first leaves water, or null if it never does.
 *
 * `entryKm` at either end is exempt: those are the runs between a quay and the
 * first water cell, and a quay is on the coast by definition.
 */
export function firstLandfall(
  coords: Array<[number, number]>,
  entryKm = 30,
  sampleKm = 2,
): [number, number] | null {
  if (coords.length < 2) return null;
  let total = 0;
  for (let i = 0; i < coords.length - 1; i += 1) total += haversineKm(coords[i], coords[i + 1]);

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

/** A catalogue leg in either direction. */
export function leg(from: string, to: string): RawLeg | null {
  return routesDoc.legs[`${from}>${to}`] ?? routesDoc.legs[`${to}>${from}`] ?? null;
}

/** Does the polyline pass within `km` of this point at any sample? */
export function passesNear(
  coords: Array<[number, number]>,
  point: [number, number],
  km: number,
): boolean {
  for (let i = 0; i < coords.length - 1; i += 1) {
    const steps = Math.max(1, Math.ceil(haversineKm(coords[i], coords[i + 1]) / 10));
    for (let s = 0; s <= steps; s += 1) {
      const f = s / steps;
      const lon = coords[i][0] + (coords[i + 1][0] - coords[i][0]) * f;
      const lat = coords[i][1] + (coords[i + 1][1] - coords[i][1]) * f;
      if (haversineKm([lon, lat], point) <= km) return true;
    }
  }
  return false;
}
