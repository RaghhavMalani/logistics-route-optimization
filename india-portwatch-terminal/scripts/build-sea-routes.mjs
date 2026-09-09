/**
 * Build the maritime routing assets.
 *
 * India PortWatch has no ocean-routing service and no network at runtime, so
 * the sea graph is produced here, once, from the Natural Earth land polygons
 * that already ship with the basemap, and committed as two assets:
 *
 *   sea-grid.json    a packed water mask -- one bit per 0.1 degree cell over
 *                    the Indian Ocean theatre, 1 where the cell centre is sea.
 *   sea-routes.json  a catalogue of water-only polylines between every port
 *                    and gateway pair the traffic engine can use, found by A*
 *                    over that mask with a penalty that keeps a route offshore
 *                    rather than scraping the coast.
 *
 * Two hand-declared corrections, because a 0.1 degree raster cannot resolve
 * either case and both change where ships may go:
 *
 *   canals    the Suez channel is narrower than a cell and would rasterise as
 *             land, closing the only route between the Red Sea and the
 *             Mediterranean.
 *   barriers  Palk Strait rasterises as open water but Adam's Bridge closes it
 *             to commercial traffic, so every route must round Sri Lanka.
 *
 * Run with: node scripts/build-sea-routes.mjs
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const GEO = path.join(ROOT, "src", "assets", "geo");

/* ------------------------------------------------------------------ grid -- */

const GRID = {
  minLon: 29,
  minLat: -20,
  maxLon: 113,
  maxLat: 40,
  step: 0.1,
};
GRID.cols = Math.round((GRID.maxLon - GRID.minLon) / GRID.step);
GRID.rows = Math.round((GRID.maxLat - GRID.minLat) / GRID.step);

const KM_PER_DEG_LAT = 110.574;
const DEG = Math.PI / 180;

const cellLon = (col) => GRID.minLon + (col + 0.5) * GRID.step;
const cellLat = (row) => GRID.minLat + (row + 0.5) * GRID.step;
const colOf = (lon) => Math.floor((lon - GRID.minLon) / GRID.step);
const rowOf = (lat) => Math.floor((lat - GRID.minLat) / GRID.step);
const idx = (col, row) => row * GRID.cols + col;

function haversineKm(a, b) {
  const dLat = (b[1] - a[1]) * DEG;
  const dLon = (b[0] - a[0]) * DEG;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a[1] * DEG) * Math.cos(b[1] * DEG) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

function round(value) {
  return Math.round(value * 1000) / 1000;
}

/* ----------------------------------------------------------- rasterising -- */

/**
 * Scanline fill, even-odd across every ring of a polygon.
 *
 * Even-odd is what makes holes work without a separate pass: a lagoon inside an
 * island crosses two more edges and falls back out of the fill.
 */
function rasterisePolygon(rings, land) {
  let minLat = Infinity;
  let maxLat = -Infinity;
  for (const ring of rings) {
    for (const point of ring) {
      if (point[1] < minLat) minLat = point[1];
      if (point[1] > maxLat) maxLat = point[1];
    }
  }
  const rowStart = Math.max(0, rowOf(minLat) - 1);
  const rowEnd = Math.min(GRID.rows - 1, rowOf(maxLat) + 1);

  for (let row = rowStart; row <= rowEnd; row += 1) {
    const y = cellLat(row);
    const crossings = [];
    for (const ring of rings) {
      for (let i = 0; i < ring.length - 1; i += 1) {
        const x1 = ring[i][0];
        const y1 = ring[i][1];
        const x2 = ring[i + 1][0];
        const y2 = ring[i + 1][1];
        if (y1 === y2) continue;
        if (y < Math.min(y1, y2) || y >= Math.max(y1, y2)) continue;
        crossings.push(x1 + ((y - y1) / (y2 - y1)) * (x2 - x1));
      }
    }
    if (crossings.length < 2) continue;
    crossings.sort((a, b) => a - b);
    for (let i = 0; i + 1 < crossings.length; i += 2) {
      const from = Math.max(0, Math.ceil((crossings[i] - GRID.minLon) / GRID.step - 0.5));
      const to = Math.min(
        GRID.cols - 1,
        Math.floor((crossings[i + 1] - GRID.minLon) / GRID.step - 0.5),
      );
      for (let col = from; col <= to; col += 1) land[idx(col, row)] = 1;
    }
  }
}

/** Stamp a corridor of cells along a polyline, `halfWidthCells` either side. */
function stampCorridor(line, halfWidthCells, value, land) {
  for (let i = 0; i < line.length - 1; i += 1) {
    const x1 = line[i][0];
    const y1 = line[i][1];
    const x2 = line[i + 1][0];
    const y2 = line[i + 1][1];
    const steps = Math.max(
      2,
      Math.ceil((Math.abs(x2 - x1) + Math.abs(y2 - y1)) / (GRID.step * 0.4)),
    );
    for (let s = 0; s <= steps; s += 1) {
      const f = s / steps;
      const col = colOf(x1 + (x2 - x1) * f);
      const row = rowOf(y1 + (y2 - y1) * f);
      for (let dc = -halfWidthCells; dc <= halfWidthCells; dc += 1) {
        for (let dr = -halfWidthCells; dr <= halfWidthCells; dr += 1) {
          const c = col + dc;
          const r = row + dr;
          if (c < 0 || r < 0 || c >= GRID.cols || r >= GRID.rows) continue;
          land[idx(c, r)] = value;
        }
      }
    }
  }
}

/** Navigable channels a 0.1 degree raster closes. */
const CANALS = [
  {
    name: "Suez Canal",
    halfWidth: 1,
    line: [
      [32.56, 29.93],
      [32.57, 30.45],
      [32.35, 30.95],
      [32.31, 31.26],
      [32.3, 31.62],
    ],
  },
  {
    // The Hooghly is the only approach to Haldia and Kolkata and is narrower
    // than a cell for its whole length; without it the eastern-most Indian port
    // in the registry has no water route to anywhere.
    name: "Hooghly approach channel",
    // Three cells wide, which is far wider than the river. A single-cell carve
    // is not four-connected everywhere it bends, and the router refuses to cut
    // a diagonal corner, so the narrower channel leaves Kolkata unreachable.
    halfWidth: 1,
    line: [
      [88.05, 20.9],
      [88.08, 21.3],
      [88.12, 21.7],
      [88.08, 22.03],
      [88.17, 22.24],
      [88.26, 22.42],
      [88.31, 22.55],
    ],
  },
];

/** Water a raster opens that commercial traffic cannot actually use. */
const BARRIERS = [
  {
    // One continuous sill from the Indian mainland across Pamban and Rameswaram
    // to Mannar Island. Both halves matter: the raster leaves the Pamban Pass
    // open, and a route through it would put deep-draught traffic over a
    // two-metre channel spanned by a rail bridge.
    name: "Adam's Bridge and Pamban Pass",
    line: [
      [78.55, 9.38],
      [78.85, 9.28],
      [79.15, 9.22],
      [79.45, 9.15],
      [79.75, 9.1],
      [80.05, 9.1],
      [80.3, 9.15],
    ],
  },
];

/* ------------------------------------------------------------- distances -- */

/**
 * Distance from every water cell to the nearest land cell, in cells, saturating
 * at `cap`. Routing multiplies its step cost by a penalty read off this field,
 * which is what stops a route hugging a headland.
 */
function distanceToLand(land, cap = 8) {
  const dist = new Uint8Array(GRID.cols * GRID.rows).fill(cap);
  let frontier = [];
  for (let i = 0; i < land.length; i += 1) {
    if (land[i]) {
      dist[i] = 0;
      frontier.push(i);
    }
  }
  for (let d = 1; d <= cap && frontier.length; d += 1) {
    const next = [];
    for (const i of frontier) {
      const col = i % GRID.cols;
      const row = (i - col) / GRID.cols;
      for (let dc = -1; dc <= 1; dc += 1) {
        for (let dr = -1; dr <= 1; dr += 1) {
          const c = col + dc;
          const r = row + dr;
          if (c < 0 || r < 0 || c >= GRID.cols || r >= GRID.rows) continue;
          const j = idx(c, r);
          if (dist[j] > d) {
            dist[j] = d;
            next.push(j);
          }
        }
      }
    }
    frontier = next;
  }
  return dist;
}

/** How much a route is charged for passing this close to shore. */
function penalty(distCells) {
  if (distCells <= 1) return 3.4;
  if (distCells === 2) return 1.9;
  if (distCells === 3) return 1.35;
  if (distCells === 4) return 1.12;
  return 1;
}

/* -------------------------------------------------------------------- A* -- */

class MinHeap {
  constructor() {
    this.keys = [];
    this.values = [];
  }
  get size() {
    return this.keys.length;
  }
  push(key, value) {
    this.keys.push(key);
    this.values.push(value);
    let i = this.keys.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (this.keys[parent] <= this.keys[i]) break;
      this.swap(i, parent);
      i = parent;
    }
  }
  pop() {
    const top = this.values[0];
    const lastKey = this.keys.pop();
    const lastValue = this.values.pop();
    if (this.keys.length) {
      this.keys[0] = lastKey;
      this.values[0] = lastValue;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1;
        const r = l + 1;
        let smallest = i;
        if (l < this.keys.length && this.keys[l] < this.keys[smallest]) smallest = l;
        if (r < this.keys.length && this.keys[r] < this.keys[smallest]) smallest = r;
        if (smallest === i) break;
        this.swap(i, smallest);
        i = smallest;
      }
    }
    return top;
  }
  swap(a, b) {
    const key = this.keys[a];
    this.keys[a] = this.keys[b];
    this.keys[b] = key;
    const value = this.values[a];
    this.values[a] = this.values[b];
    this.values[b] = value;
  }
}

const NEIGHBOURS = [
  [1, 0], [-1, 0], [0, 1], [0, -1],
  [1, 1], [1, -1], [-1, 1], [-1, -1],
];

function findRoute(land, dist, startCell, goalCell) {
  const total = GRID.cols * GRID.rows;
  const g = new Float32Array(total).fill(Infinity);
  const from = new Int32Array(total).fill(-1);
  const closed = new Uint8Array(total);
  const goalCol = goalCell % GRID.cols;
  const goalRow = (goalCell - goalCol) / GRID.cols;
  const goalPoint = [cellLon(goalCol), cellLat(goalRow)];

  const heap = new MinHeap();
  g[startCell] = 0;
  heap.push(0, startCell);

  while (heap.size) {
    const current = heap.pop();
    if (closed[current]) continue;
    closed[current] = 1;
    if (current === goalCell) break;

    const col = current % GRID.cols;
    const row = (current - col) / GRID.cols;
    const lat = cellLat(row);
    const dyKm = GRID.step * KM_PER_DEG_LAT;
    const dxKm = GRID.step * 111.32 * Math.cos(lat * DEG);

    for (const step of NEIGHBOURS) {
      const c = col + step[0];
      const r = row + step[1];
      if (c < 0 || r < 0 || c >= GRID.cols || r >= GRID.rows) continue;
      const next = idx(c, r);
      if (land[next] || closed[next]) continue;
      // No corner cutting: a diagonal step whose two orthogonal neighbours are
      // land squeezes a route through a headland the raster says is closed.
      if (step[0] !== 0 && step[1] !== 0) {
        if (land[idx(col + step[0], row)] || land[idx(col, row + step[1])]) continue;
      }
      const stepKm = Math.hypot(step[0] * dxKm, step[1] * dyKm);
      const cost = g[current] + stepKm * penalty(dist[next]);
      if (cost >= g[next]) continue;
      g[next] = cost;
      from[next] = current;
      heap.push(cost + haversineKm([cellLon(c), cellLat(r)], goalPoint), next);
    }
  }

  if (from[goalCell] === -1 && startCell !== goalCell) return null;

  const cells = [];
  let cursor = goalCell;
  while (cursor !== -1) {
    cells.push(cursor);
    if (cursor === startCell) break;
    cursor = from[cursor];
  }
  cells.reverse();
  return {
    coords: cells.map((cell) => {
      const col = cell % GRID.cols;
      return [cellLon(col), cellLat((cell - col) / GRID.cols)];
    }),
    km: g[goalCell],
  };
}

/** Nearest water cell to a coordinate, spiralling outward. */
function nearestWater(land, lon, lat, maxRings = 40) {
  const col0 = colOf(lon);
  const row0 = rowOf(lat);
  if (col0 >= 0 && row0 >= 0 && col0 < GRID.cols && row0 < GRID.rows && !land[idx(col0, row0)]) {
    return idx(col0, row0);
  }
  for (let ring = 1; ring <= maxRings; ring += 1) {
    let best = null;
    let bestKm = Infinity;
    for (let dc = -ring; dc <= ring; dc += 1) {
      for (let dr = -ring; dr <= ring; dr += 1) {
        if (Math.max(Math.abs(dc), Math.abs(dr)) !== ring) continue;
        const c = col0 + dc;
        const r = row0 + dr;
        if (c < 0 || r < 0 || c >= GRID.cols || r >= GRID.rows) continue;
        if (land[idx(c, r)]) continue;
        const km = haversineKm([lon, lat], [cellLon(c), cellLat(r)]);
        if (km < bestKm) {
          bestKm = km;
          best = idx(c, r);
        }
      }
    }
    if (best !== null) return best;
  }
  return null;
}

/* ------------------------------------------------------------ simplifying -- */

function perpendicularKm(point, a, b) {
  const lat = (a[1] + b[1]) / 2;
  const kx = 111.32 * Math.cos(lat * DEG);
  const ky = KM_PER_DEG_LAT;
  const ax = a[0] * kx;
  const ay = a[1] * ky;
  const bx = b[0] * kx;
  const by = b[1] * ky;
  const px = point[0] * kx;
  const py = point[1] * ky;
  const dx = bx - ax;
  const dy = by - ay;
  const lengthSq = dx * dx + dy * dy;
  if (lengthSq === 0) return Math.hypot(px - ax, py - ay);
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lengthSq));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function simplify(points, toleranceKm, land) {
  if (points.length < 3) return points.slice();
  const keep = new Uint8Array(points.length);
  keep[0] = 1;
  keep[points.length - 1] = 1;
  const stack = [[0, points.length - 1]];
  while (stack.length) {
    const span = stack.pop();
    const first = span[0];
    const last = span[1];
    if (last - first < 2) continue;
    let worst = 0;
    let index = -1;
    for (let i = first + 1; i < last; i += 1) {
      const d = perpendicularKm(points[i], points[first], points[last]);
      if (d > worst) {
        worst = d;
        index = i;
      }
    }
    // A shortcut is only allowed if the straight line it implies is itself
    // water, otherwise simplification would quietly cut across a headland the
    // router went round.
    const shortcutOk = segmentIsWater(land, points[first], points[last]);
    if (index !== -1 && (worst > toleranceKm || !shortcutOk)) {
      keep[index] = 1;
      stack.push([first, index], [index, last]);
    }
  }
  return points.filter((_, i) => keep[i] === 1);
}

/** Every sampled point on the segment falls on a water cell. */
function segmentIsWater(land, a, b, sampleKm = 2) {
  const steps = Math.max(1, Math.ceil(haversineKm(a, b) / sampleKm));
  for (let i = 0; i <= steps; i += 1) {
    const f = i / steps;
    const lon = a[0] + (b[0] - a[0]) * f;
    const lat = a[1] + (b[1] - a[1]) * f;
    const col = colOf(lon);
    const row = rowOf(lat);
    if (col < 0 || row < 0 || col >= GRID.cols || row >= GRID.rows) return false;
    if (land[idx(col, row)]) return false;
  }
  return true;
}

/**
 * Where a polyline first leaves water, ignoring `entryKm` at either end.
 *
 * The endpoints are the quays themselves, which sit inside the raster's
 * shoreline by construction; everything between them must be sea. Returns null
 * when the whole passage is clear. Both the builder and the shipped route test
 * use this, so "valid" means the same thing in both places.
 */
function firstLandfall(land, coords, entryKm = 30) {
  let total = 0;
  for (let i = 0; i < coords.length - 1; i += 1) total += haversineKm(coords[i], coords[i + 1]);
  let travelled = 0;
  for (let i = 0; i < coords.length - 1; i += 1) {
    const a = coords[i];
    const b = coords[i + 1];
    const segKm = haversineKm(a, b);
    const steps = Math.max(1, Math.ceil(segKm / 2));
    for (let s = 0; s <= steps; s += 1) {
      const f = s / steps;
      const along = travelled + segKm * f;
      if (along < entryKm || total - along < entryKm) continue;
      const lon = a[0] + (b[0] - a[0]) * f;
      const lat = a[1] + (b[1] - a[1]) * f;
      const col = colOf(lon);
      const row = rowOf(lat);
      if (col < 0 || row < 0 || col >= GRID.cols || row >= GRID.rows) continue;
      if (land[idx(col, row)]) return [lon, lat];
    }
    travelled += segKm;
  }
  return null;
}

/** Chaikin corner cutting, reverted wherever the smoothed corner touches land. */
function smooth(points, land, passes = 2) {
  let current = points;
  for (let pass = 0; pass < passes; pass += 1) {
    const next = [current[0]];
    for (let i = 0; i < current.length - 1; i += 1) {
      const a = current[i];
      const b = current[i + 1];
      const q = [a[0] + 0.25 * (b[0] - a[0]), a[1] + 0.25 * (b[1] - a[1])];
      const r = [a[0] + 0.75 * (b[0] - a[0]), a[1] + 0.75 * (b[1] - a[1])];
      if (segmentIsWater(land, next[next.length - 1], q) && segmentIsWater(land, q, r)) {
        next.push(q, r);
      } else {
        next.push(a, b);
      }
    }
    next.push(current[current.length - 1]);
    current = next;
  }
  return current;
}

/* ------------------------------------------------------------- waypoints -- */

/** Indian ports, from the model registry. */
const PORTS = [
  ["INIXY", "Deendayal (Kandla)", 23.02, 70.22],
  ["INMUN", "Mundra", 22.74, 69.7],
  ["INNSA", "JNPA / Nhava Sheva", 18.95, 72.95],
  ["INBOM", "Mumbai", 18.96, 72.84],
  ["INMRM", "Mormugao", 15.4, 73.8],
  ["INNML", "New Mangalore", 12.92, 74.8],
  ["INCOK", "Cochin (Vallarpadam)", 9.97, 76.27],
  ["INTUT", "Tuticorin", 8.75, 78.2],
  ["INMAA", "Chennai", 13.1, 80.3],
  ["INENR", "Kamarajar (Ennore)", 13.25, 80.33],
  ["INVTZ", "Visakhapatnam", 17.69, 83.22],
  ["INPRT", "Paradip", 20.26, 86.67],
  ["INCCU", "Kolkata (Haldia)", 22.55, 88.31],
];

/** Foreign calls and chokepoints the traffic engine routes to and from. */
const GATEWAYS = [
  ["LKCMB", "Colombo", 6.95, 79.78],
  ["SGSIN", "Singapore", 1.26, 103.75],
  ["MYPKG", "Port Klang", 2.99, 101.32],
  ["MALACCA", "Strait of Malacca", 4.6, 98.6],
  ["AEJEA", "Jebel Ali", 25.0, 55.05],
  ["AEFJR", "Fujairah", 25.15, 56.42],
  ["HORMUZ", "Strait of Hormuz", 26.55, 56.5],
  ["OMSLL", "Salalah", 16.9, 54.0],
  ["YEADE", "Aden", 12.75, 45.05],
  ["BAB_EL_MANDEB", "Bab-el-Mandeb", 12.6, 43.4],
  ["SUEZ", "Suez Canal", 30.5, 32.4],
  ["EGPSD", "Port Said", 31.45, 32.35],
  ["PKKHI", "Karachi", 24.83, 66.9],
  ["BDCGP", "Chittagong", 22.1, 91.75],
  ["MMRGN", "Yangon", 16.2, 96.2],
  ["MVMLE", "Male", 4.18, 73.5],
  ["KEMBA", "Mombasa", -4.05, 39.75],
  ["IDBLW", "Sunda approach", -5.9, 105.5],
];

const WAYPOINTS = [
  ...PORTS.map((p) => ({ id: p[0], name: p[1], lat: p[2], lon: p[3], kind: "port" })),
  ...GATEWAYS.map((g) => ({ id: g[0], name: g[1], lat: g[2], lon: g[3], kind: "gateway" })),
];

/* ------------------------------------------------------------------ main -- */

console.log(`grid ${GRID.cols}x${GRID.rows} cells at ${GRID.step} deg`);

const landGeo = JSON.parse(fs.readFileSync(path.join(GEO, "region-land.json"), "utf8"));
const land = new Uint8Array(GRID.cols * GRID.rows);

for (const feature of landGeo.features) {
  const geometry = feature.geometry;
  const polygons =
    geometry.type === "MultiPolygon" ? geometry.coordinates : [geometry.coordinates];
  for (const rings of polygons) rasterisePolygon(rings, land);
}

const countLand = () => land.reduce((sum, v) => sum + v, 0);
console.log(`rasterised land: ${countLand()} cells`);

for (const canal of CANALS) stampCorridor(canal.line, canal.halfWidth, 0, land);
for (const barrier of BARRIERS) stampCorridor(barrier.line, 0, 1, land);
const landCells = countLand();
console.log(`after canals and barriers: ${landCells} cells`);

const dist = distanceToLand(land);

/* Anchor every waypoint on a water cell, and remember the entry segment from
   the quay to that cell -- the one place a route is allowed to touch land. */
const anchors = new Map();
for (const waypoint of WAYPOINTS) {
  const cell = nearestWater(land, waypoint.lon, waypoint.lat);
  if (cell === null) throw new Error(`no water cell near ${waypoint.id}`);
  const col = cell % GRID.cols;
  const row = (cell - col) / GRID.cols;
  const approach = [round(cellLon(col)), round(cellLat(row))];
  anchors.set(waypoint.id, {
    cell,
    approach,
    entryKm: haversineKm([waypoint.lon, waypoint.lat], approach),
  });
}

const pairs = [];
for (let i = 0; i < WAYPOINTS.length; i += 1) {
  for (let j = i + 1; j < WAYPOINTS.length; j += 1) {
    const a = WAYPOINTS[i];
    const b = WAYPOINTS[j];
    // Gateway-to-gateway legs are not useful: the traffic engine never routes
    // Colombo to Mombasa without touching India.
    if (a.kind === "gateway" && b.kind === "gateway") continue;
    pairs.push([a, b]);
  }
}

console.log(`routing ${pairs.length} legs`);
const started = Date.now();
const legs = {};
let done = 0;
let failed = 0;

for (const pair of pairs) {
  const a = pair[0];
  const b = pair[1];
  const from = anchors.get(a.id);
  const to = anchors.get(b.id);
  const found = findRoute(land, dist, from.cell, to.cell);
  done += 1;
  if (done % 40 === 0) {
    console.log(`  ${done}/${pairs.length} (${((Date.now() - started) / 1000).toFixed(0)}s)`);
  }
  if (!found) {
    failed += 1;
    console.warn(`  ! no water route ${a.id} -> ${b.id}`);
    continue;
  }

  const assemble = (middle) =>
    [
      [round(a.lon), round(a.lat)],
      ...middle.map((point) => [round(point[0]), round(point[1])]),
      [round(b.lon), round(b.lat)],
    ].filter(
      (point, i, all) => i === 0 || point[0] !== all[i - 1][0] || point[1] !== all[i - 1][1],
    );

  const plain = simplify(found.coords, 3.5, land);
  // Smoothing reads far better on screen, but a rounded corner can clip a
  // headland the router avoided. Take the smoothed line only when it is clean.
  const candidate = assemble(smooth(plain, land, 2));
  const coords = firstLandfall(land, candidate) === null ? candidate : assemble(plain);

  let km = 0;
  for (let i = 0; i < coords.length - 1; i += 1) km += haversineKm(coords[i], coords[i + 1]);

  legs[`${a.id}>${b.id}`] = {
    from: a.id,
    to: b.id,
    km: Math.round(km),
    entryKm: Math.round((from.entryKm + to.entryKm) * 10) / 10,
    coords,
  };
}

console.log(`routed ${Object.keys(legs).length} legs, ${failed} unreachable`);

/* ------------------------------------------------------------ validation -- */

let crossings = 0;
for (const key of Object.keys(legs)) {
  const bad = firstLandfall(land, legs[key].coords);
  if (bad) {
    crossings += 1;
    console.warn(`  ! ${key} crosses land at ${bad[0].toFixed(2)},${bad[1].toFixed(2)}`);
  }
}
console.log(
  crossings === 0 ? "validation: no leg crosses land" : `validation: ${crossings} legs cross land`,
);

/* ----------------------------------------------------------------- write -- */

const packed = Buffer.alloc(Math.ceil(land.length / 8));
for (let i = 0; i < land.length; i += 1) {
  // 1 means water, so a decoder reading past the end answers "land", which is
  // the safe direction for a router to be wrong in.
  if (!land[i]) packed[i >> 3] |= 1 << (i & 7);
}

const provenance = {
  generatedAt: new Date().toISOString(),
  generator: "scripts/build-sea-routes.mjs",
  basis: "Natural Earth 1:50m land polygons clipped to the Indian Ocean theatre",
  method:
    "A* over a 0.1 degree water raster with an offshore-distance penalty, " +
    "Douglas-Peucker at 3.5 km, then land-checked Chaikin smoothing",
  corrections: {
    canals: CANALS.map((c) => c.name),
    barriers: BARRIERS.map((b) => b.name),
  },
  disclaimer:
    "VISUALISATION ONLY. These polylines are not a navigational product. They carry " +
    "no depth, traffic separation or notice-to-mariners information and must not be " +
    "used for passage planning.",
};

fs.writeFileSync(
  path.join(GEO, "sea-grid.json"),
  JSON.stringify({ ...provenance, grid: GRID, landCells, water: packed.toString("base64") }),
);

fs.writeFileSync(
  path.join(GEO, "sea-routes.json"),
  JSON.stringify({
    ...provenance,
    waypoints: Object.fromEntries(
      WAYPOINTS.map((w) => [
        w.id,
        {
          name: w.name,
          lat: w.lat,
          lon: w.lon,
          kind: w.kind,
          approach: anchors.get(w.id).approach,
        },
      ]),
    ),
    legs,
  }),
);

console.log(
  `wrote sea-grid.json (${(packed.length / 1024).toFixed(0)} KB packed) and sea-routes.json`,
);
if (crossings > 0) process.exitCode = 1;
