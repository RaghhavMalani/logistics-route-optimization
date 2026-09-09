/**
 * The maritime route service.
 *
 * Every line this product draws between two places on water comes from here.
 * The catalogue is a build artefact (`scripts/build-sea-routes.mjs`): A* over a
 * 0.1 degree water raster derived from the same Natural Earth land polygons the
 * basemap draws, with a penalty that pushes a passage offshore instead of
 * letting it scrape a headland. Nothing is a straight line between two ports,
 * and nothing crosses land.
 *
 * The service exposes legs, not a solver: routing happened at build time, so a
 * screen asking for JNPA to Cochin gets the same polyline every time, on a
 * closed network, with no runtime cost beyond a map lookup.
 */

import catalogue from "@/assets/geo/sea-routes.json";
import {
  fixAt,
  haversineKm,
  measurePath,
  slicePath,
  type MeasuredPath,
  type Position,
} from "./geo";

export type WaypointKind = "port" | "gateway";

export interface Waypoint {
  id: string;
  name: string;
  lat: number;
  lon: number;
  kind: WaypointKind;
  /** The water cell the routing graph anchored this quay to. */
  approach: Position;
}

interface RawLeg {
  from: string;
  to: string;
  km: number;
  entryKm: number;
  coords: Position[];
}

interface RawCatalogue {
  generatedAt: string;
  generator: string;
  basis: string;
  method: string;
  corrections: { canals: string[]; barriers: string[] };
  disclaimer: string;
  waypoints: Record<string, Omit<Waypoint, "id">>;
  legs: Record<string, RawLeg>;
}

const raw = catalogue as unknown as RawCatalogue;

/**
 * What this geometry is, and what it is not.
 *
 * Shown wherever a route is drawn. A visualisation route is not a passage plan
 * and the product says so in the same breath as it draws one.
 */
export const ROUTE_PROVENANCE = {
  generatedAt: raw.generatedAt,
  basis: raw.basis,
  method: raw.method,
  corrections: raw.corrections,
  disclaimer: raw.disclaimer,
  label: "Water-only routing graph",
  short: "NON-NAVIGATIONAL",
} as const;

export const WAYPOINTS: Record<string, Waypoint> = Object.fromEntries(
  Object.entries(raw.waypoints).map(([id, value]) => [id, { id, ...value }]),
);

export const WAYPOINT_LIST: Waypoint[] = Object.values(WAYPOINTS);

export const PORT_WAYPOINTS = WAYPOINT_LIST.filter((w) => w.kind === "port");
export const GATEWAY_WAYPOINTS = WAYPOINT_LIST.filter((w) => w.kind === "gateway");

export function waypoint(id: string): Waypoint | null {
  return WAYPOINTS[id] ?? null;
}

/* ----------------------------------------------------------------- legs -- */

export interface SeaRoute {
  key: string;
  from: string;
  to: string;
  /** Oriented from `from` to `to`, whichever direction the catalogue stored. */
  path: MeasuredPath;
  km: number;
}

const cache = new Map<string, SeaRoute | null>();

/**
 * The water-only passage between two waypoints.
 *
 * The catalogue stores one direction per pair; the reverse is the same water in
 * the other order, so it is reversed here rather than routed twice.
 */
export function seaRoute(fromId: string, toId: string): SeaRoute | null {
  const key = `${fromId}>${toId}`;
  const cached = cache.get(key);
  if (cached !== undefined) return cached;

  let result: SeaRoute | null = null;
  const forward = raw.legs[key];
  if (forward) {
    result = {
      key,
      from: fromId,
      to: toId,
      path: measurePath(forward.coords),
      km: forward.km,
    };
  } else {
    const reverse = raw.legs[`${toId}>${fromId}`];
    if (reverse) {
      result = {
        key,
        from: fromId,
        to: toId,
        path: measurePath([...reverse.coords].reverse()),
        km: reverse.km,
      };
    }
  }
  cache.set(key, result);
  return result;
}

export function hasSeaRoute(fromId: string, toId: string): boolean {
  return seaRoute(fromId, toId) !== null;
}

/** Every leg in the catalogue, as unordered pairs. */
export function legPairs(): Array<{ from: string; to: string; km: number }> {
  return Object.values(raw.legs).map((leg) => ({ from: leg.from, to: leg.to, km: leg.km }));
}

/* ------------------------------------------------------------ geometry --- */

export interface RouteSplit {
  /** Water already covered. */
  behind: Position[];
  /** Water still to run. */
  ahead: Position[];
}

/** Split a route at the vessel, so a screen can weight the two halves apart. */
export function splitRoute(route: SeaRoute, travelledKm: number): RouteSplit {
  return {
    behind: slicePath(route.path, 0, travelledKm),
    ahead: slicePath(route.path, travelledKm, route.path.km),
  };
}

/** Evenly spaced fixes along the remaining passage, for forecast sampling. */
export function sampleAhead(
  route: SeaRoute,
  travelledKm: number,
  count: number,
): Array<{ position: Position; km: number; fractionOfLeg: number }> {
  const remaining = Math.max(0, route.path.km - travelledKm);
  const out: Array<{ position: Position; km: number; fractionOfLeg: number }> = [];
  for (let i = 0; i <= count; i += 1) {
    const km = travelledKm + (remaining * i) / count;
    out.push({
      position: fixAt(route.path, km).position,
      km: km - travelledKm,
      fractionOfLeg: route.path.km > 0 ? km / route.path.km : 0,
    });
  }
  return out;
}

/**
 * The nearest catalogue waypoint to a coordinate.
 *
 * Used to attach an arbitrary position -- a port from the model registry, a
 * chokepoint from the event feed -- to the routing graph without a second
 * identifier scheme.
 */
export function nearestWaypoint(
  lon: number,
  lat: number,
  kind?: WaypointKind,
): Waypoint | null {
  let best: Waypoint | null = null;
  let bestKm = Infinity;
  for (const candidate of WAYPOINT_LIST) {
    if (kind && candidate.kind !== kind) continue;
    const km = haversineKm([lon, lat], [candidate.lon, candidate.lat]);
    if (km < bestKm) {
      bestKm = km;
      best = candidate;
    }
  }
  return best;
}

/**
 * Corridor geometry for the basemap.
 *
 * These are the trunk passages the traffic actually uses, drawn faintly under
 * the ships so the network reads even where no vessel is on it right now. They
 * are catalogue legs, not new geometry, so they inherit the same water-only
 * guarantee.
 */
export const CORRIDORS: Array<{ id: string; name: string; legs: Array<[string, string]> }> = [
  {
    id: "west-coast",
    name: "West coast corridor",
    legs: [
      ["INMUN", "INNSA"],
      ["INNSA", "INMRM"],
      ["INMRM", "INNML"],
      ["INNML", "INCOK"],
    ],
  },
  {
    id: "east-coast",
    name: "East coast corridor",
    legs: [
      ["INCCU", "INPRT"],
      ["INPRT", "INVTZ"],
      ["INVTZ", "INMAA"],
    ],
  },
  {
    id: "sri-lanka-passage",
    name: "Sri Lanka passage",
    legs: [
      ["INCOK", "LKCMB"],
      ["LKCMB", "INMAA"],
    ],
  },
  {
    id: "malacca-approach",
    name: "Malacca approach",
    legs: [
      ["INMAA", "MALACCA"],
      ["MALACCA", "SGSIN"],
    ],
  },
  {
    id: "arabian-gulf",
    name: "Arabian Sea and Gulf approach",
    legs: [
      ["INNSA", "AEJEA"],
      ["AEJEA", "HORMUZ"],
    ],
  },
  {
    id: "suez-route",
    name: "Suez route",
    legs: [
      ["INMUN", "OMSLL"],
      ["OMSLL", "BAB_EL_MANDEB"],
      ["BAB_EL_MANDEB", "SUEZ"],
    ],
  },
  {
    id: "bay-of-bengal",
    name: "Bay of Bengal",
    legs: [
      ["INMAA", "BDCGP"],
      ["INCCU", "MMRGN"],
    ],
  },
];

export function corridorFeatures(): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (const corridor of CORRIDORS) {
    for (const [from, to] of corridor.legs) {
      const route = seaRoute(from, to);
      if (!route) continue;
      features.push({
        type: "Feature",
        properties: { corridor: corridor.id, name: corridor.name },
        geometry: { type: "LineString", coordinates: route.path.coords },
      });
    }
  }
  return { type: "FeatureCollection", features };
}
