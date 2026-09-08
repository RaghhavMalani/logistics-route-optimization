/**
 * Everything the map draws, derived from pipeline artefacts.
 *
 * The rule that governs this file: a mark exists on the map only if a number
 * behind it exists in an artefact. There is no decorative weather, no invented
 * vessel track, no synthetic storm. Where a measurement is missing the feature
 * is not emitted, and the legend says how many were dropped.
 *
 * The weather field is the one derived construction, and it is stated as such
 * wherever it is drawn: an inverse-distance interpolation of the per-port
 * Open-Meteo observations onto a 0.25° grid, cut off 420 km from the nearest
 * station so the field never extends past the stations that support it.
 */

import type {
  NewsEvent,
  PortSnapshot,
  VesselActivity,
  WeatherSignal,
} from "@/types/portwatch";

const EARTH_KM = 6371;
const DEG = Math.PI / 180;

export function haversineKm(
  a: { lat: number; lon: number },
  b: { lat: number; lon: number },
): number {
  const dLat = (b.lat - a.lat) * DEG;
  const dLon = (b.lon - a.lon) * DEG;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * DEG) * Math.cos(b.lat * DEG) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.sqrt(h));
}

/** Points along the great circle between two positions, for lane geometry. */
export function greatCircle(
  from: { lat: number; lon: number },
  to: { lat: number; lon: number },
  steps = 48,
): Array<[number, number]> {
  const φ1 = from.lat * DEG;
  const λ1 = from.lon * DEG;
  const φ2 = to.lat * DEG;
  const λ2 = to.lon * DEG;
  const d =
    2 *
    Math.asin(
      Math.sqrt(
        Math.sin((φ2 - φ1) / 2) ** 2 +
          Math.cos(φ1) * Math.cos(φ2) * Math.sin((λ2 - λ1) / 2) ** 2,
      ),
    );
  if (!Number.isFinite(d) || d === 0) {
    return [
      [from.lon, from.lat],
      [to.lon, to.lat],
    ];
  }
  const out: Array<[number, number]> = [];
  for (let i = 0; i <= steps; i += 1) {
    const f = i / steps;
    const A = Math.sin((1 - f) * d) / Math.sin(d);
    const B = Math.sin(f * d) / Math.sin(d);
    const x = A * Math.cos(φ1) * Math.cos(λ1) + B * Math.cos(φ2) * Math.cos(λ2);
    const y = A * Math.cos(φ1) * Math.sin(λ1) + B * Math.cos(φ2) * Math.sin(λ2);
    const z = A * Math.sin(φ1) + B * Math.sin(φ2);
    out.push([
      Math.atan2(y, x) / DEG,
      Math.atan2(z, Math.sqrt(x * x + y * y)) / DEG,
    ]);
  }
  return out;
}

export function circlePolygon(
  centre: { lat: number; lon: number },
  radiusKm: number,
  steps = 64,
): Array<[number, number]> {
  const ring: Array<[number, number]> = [];
  const latScale = radiusKm / 111.32;
  const lonScale = radiusKm / (111.32 * Math.max(0.15, Math.cos(centre.lat * DEG)));
  for (let i = 0; i <= steps; i += 1) {
    const θ = (i / steps) * Math.PI * 2;
    ring.push([centre.lon + lonScale * Math.cos(θ), centre.lat + latScale * Math.sin(θ)]);
  }
  return ring;
}

function sector(
  centre: { lat: number; lon: number },
  radiusKm: number,
  fromDeg: number,
  toDeg: number,
): Array<[number, number]> {
  const ring: Array<[number, number]> = [[centre.lon, centre.lat]];
  const latScale = radiusKm / 111.32;
  const lonScale = radiusKm / (111.32 * Math.max(0.15, Math.cos(centre.lat * DEG)));
  const steps = 32;
  for (let i = 0; i <= steps; i += 1) {
    const bearing = (fromDeg + ((toDeg - fromDeg) * i) / steps) * DEG;
    ring.push([
      centre.lon + lonScale * Math.sin(bearing),
      centre.lat + latScale * Math.cos(bearing),
    ]);
  }
  ring.push([centre.lon, centre.lat]);
  return ring;
}

/* ---------------------------------------------------------- chokepoints -- */

export const CHOKEPOINTS = [
  { code: "HORMUZ", name: "Strait of Hormuz", lat: 26.6, lon: 56.3, coast: "west" },
  { code: "BAB_EL_MANDEB", name: "Bab-el-Mandeb", lat: 12.6, lon: 43.3, coast: "west" },
  { code: "SUEZ", name: "Suez Canal", lat: 30.0, lon: 32.55, coast: "west" },
  { code: "MALACCA", name: "Strait of Malacca", lat: 2.5, lon: 101.0, coast: "east" },
  { code: "PANAMA", name: "Panama Canal", lat: 9.08, lon: -79.68, coast: "west" },
] as const;

export const CHOKEPOINT_BY_CODE = new Map<string, (typeof CHOKEPOINTS)[number]>(
  CHOKEPOINTS.map((choke) => [choke.code, choke] as const),
);

/* -------------------------------------------------------- weather field -- */

export type WeatherField = "rain" | "wind" | "gust" | "visibility" | "impact" | "storm";

export interface FieldSpec {
  key: WeatherField;
  label: string;
  unit: string;
  /** Upper edge of each band, ascending. */
  bands: number[];
  colors: string[];
  /** True when a *low* reading is the hazardous one (visibility). */
  inverted?: boolean;
  read: (signal: WeatherSignal) => number | null;
  format: (value: number) => string;
}

/* A restrained radar ramp: it reads as intensity without turning the chart
   into a rainbow, and it stays clear of the five status hues. */
const RAIN_RAMP = ["#1d5470", "#22786f", "#4a8f52", "#9d9337", "#bd7a37", "#bc5343"];
const WIND_RAMP = ["#1c4c66", "#276f8c", "#3f93a4", "#8a9750", "#b8823a", "#bc5343"];
const RISK_RAMP = ["#1d5470", "#2b7188", "#7d8f57", "#b8823a", "#bc5343", "#a63f3f"];

export const WEATHER_FIELDS: Record<WeatherField, FieldSpec> = {
  rain: {
    key: "rain",
    label: "Precipitation",
    unit: "mm/24h",
    bands: [1, 4, 10, 20, 40, 80],
    colors: RAIN_RAMP,
    read: (s) => s.rainfallMm24h,
    format: (v) => `${v.toFixed(1)} mm`,
  },
  wind: {
    key: "wind",
    label: "Wind speed",
    unit: "kn",
    bands: [5, 10, 16, 22, 30, 45],
    colors: WIND_RAMP,
    read: (s) => s.windKnots,
    format: (v) => `${v.toFixed(1)} kn`,
  },
  gust: {
    key: "gust",
    label: "Gust",
    unit: "kn",
    bands: [10, 18, 25, 34, 45, 60],
    colors: WIND_RAMP,
    read: (s) => s.gustKnots,
    format: (v) => `${v.toFixed(1)} kn`,
  },
  visibility: {
    key: "visibility",
    label: "Visibility",
    unit: "km",
    bands: [1, 3, 6, 10, 16, 25],
    colors: [...RISK_RAMP].reverse(),
    inverted: true,
    read: (s) => s.visibilityKm,
    format: (v) => `${v.toFixed(1)} km`,
  },
  impact: {
    key: "impact",
    label: "Weather impact",
    unit: "index",
    bands: [0.05, 0.1, 0.18, 0.3, 0.45, 0.7],
    colors: RISK_RAMP,
    read: (s) => s.impactScore,
    format: (v) => v.toFixed(3),
  },
  storm: {
    key: "storm",
    label: "Storm risk",
    unit: "index",
    bands: [0.02, 0.05, 0.12, 0.25, 0.45, 0.7],
    colors: RISK_RAMP,
    read: (s) => s.stormRisk,
    format: (v) => v.toFixed(3),
  },
};

export function bandOf(spec: FieldSpec, value: number): number {
  for (let i = 0; i < spec.bands.length; i += 1) {
    if (value <= spec.bands[i]) return i;
  }
  return spec.bands.length - 1;
}

function hexToRgb(hex: string): [number, number, number] {
  const value = parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function mix(a: string, b: string, t: number): string {
  const [ar, ag, ab] = hexToRgb(a);
  const [br, bg, bb] = hexToRgb(b);
  const channel = (x: number, y: number) => Math.round(x + (y - x) * t);
  return `rgb(${channel(ar, br)}, ${channel(ag, bg)}, ${channel(ab, bb)})`;
}

/**
 * Continuous colour across the ramp.
 *
 * Snapping each cell to a band colour turns the field into a visible quilt at
 * mid zoom, which reads as an artefact of the grid rather than as weather.
 * Interpolating between the two neighbouring band colours keeps the legend's
 * meaning while letting the field vary smoothly.
 */
export function rampColor(spec: FieldSpec, value: number): { color: string; intensity: number } {
  const bands = spec.bands;
  const first = bands[0];
  const last = bands[bands.length - 1];

  if (value <= first) {
    const t = Math.max(0, value / Math.max(first, 1e-9));
    return { color: mix(spec.colors[0], spec.colors[1] ?? spec.colors[0], t * 0.5), intensity: t * 0.5 };
  }
  if (value >= last) {
    return { color: spec.colors[spec.colors.length - 1], intensity: 1 };
  }
  for (let i = 1; i < bands.length; i += 1) {
    if (value <= bands[i]) {
      const span = bands[i] - bands[i - 1] || 1;
      const t = (value - bands[i - 1]) / span;
      return {
        color: mix(spec.colors[i - 1], spec.colors[i], t),
        intensity: (i - 1 + t) / (bands.length - 1),
      };
    }
  }
  return { color: spec.colors[spec.colors.length - 1], intensity: 1 };
}

const GRID_STEP = 0.25;
const MAX_STATION_KM = 420;

export interface WeatherFieldResult {
  cells: GeoJSON.FeatureCollection;
  stations: GeoJSON.FeatureCollection;
  /** Stations that carried a reading for this field. */
  covered: number;
  /** Stations whose reading was absent — the field does not cover them. */
  missing: string[];
  max: number | null;
}

/**
 * Interpolate the per-port observations onto a grid.
 *
 * Inverse distance weighting with a 420 km cutoff. The quantisation is left
 * visible on purpose: a smooth field would imply a resolution the 13 stations
 * do not have.
 */
export function buildWeatherField(
  signals: WeatherSignal[],
  ports: PortSnapshot[],
  field: WeatherField,
): WeatherFieldResult {
  const spec = WEATHER_FIELDS[field];
  const byCode = new Map(ports.map((port) => [port.code, port]));

  const stations = signals
    .map((signal) => {
      const port = byCode.get(signal.portCode);
      const value = spec.read(signal);
      if (!port?.location || value == null || Number.isNaN(value)) return null;
      return { signal, port, value, location: port.location };
    })
    .filter((s): s is NonNullable<typeof s> => s !== null);

  const missing = signals
    .filter((signal) => {
      const value = spec.read(signal);
      return value == null || Number.isNaN(value);
    })
    .map((signal) => signal.name);

  if (!stations.length) {
    return {
      cells: { type: "FeatureCollection", features: [] },
      stations: { type: "FeatureCollection", features: [] },
      covered: 0,
      missing,
      max: null,
    };
  }

  const lats = stations.map((s) => s.location.lat);
  const lons = stations.map((s) => s.location.lon);
  const pad = MAX_STATION_KM / 111;
  const minLat = Math.min(...lats) - pad;
  const maxLat = Math.max(...lats) + pad;
  const minLon = Math.min(...lons) - pad;
  const maxLon = Math.max(...lons) + pad;

  const features: GeoJSON.Feature[] = [];
  let maxValue = -Infinity;

  for (let lat = minLat; lat <= maxLat; lat += GRID_STEP) {
    for (let lon = minLon; lon <= maxLon; lon += GRID_STEP) {
      const centre = { lat: lat + GRID_STEP / 2, lon: lon + GRID_STEP / 2 };
      let weighted = 0;
      let weights = 0;
      let nearest = Infinity;
      for (const station of stations) {
        const km = haversineKm(centre, station.location);
        if (km > MAX_STATION_KM) continue;
        nearest = Math.min(nearest, km);
        const w = 1 / Math.max(km, 12) ** 2;
        weighted += station.value * w;
        weights += w;
      }
      if (!weights || nearest > MAX_STATION_KM) continue;

      const value = weighted / weights;
      maxValue = Math.max(maxValue, value);
      const { color, intensity } = rampColor(spec, value);
      const hazard = spec.inverted ? 1 - intensity : intensity;
      // Below a tenth of the first band the reading is "no meaningful signal";
      // drawing it would wash the whole coast in colour and say nothing.
      if (hazard < 0.06) continue;
      features.push({
        type: "Feature",
        properties: {
          value,
          band: Math.round(hazard * (spec.bands.length - 1)),
          color,
          // Capped low: the field is context under the operational marks, and
          // it must never make the coastline or a port harder to read.
          opacity: 0.07 + Math.min(0.26, hazard * 0.34),
        },
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [lon, lat],
              [lon + GRID_STEP, lat],
              [lon + GRID_STEP, lat + GRID_STEP],
              [lon, lat + GRID_STEP],
              [lon, lat],
            ],
          ],
        },
      });
    }
  }

  return {
    cells: { type: "FeatureCollection", features },
    stations: {
      type: "FeatureCollection",
      features: stations.map((station) => ({
        type: "Feature",
        properties: {
          portCode: station.port.code,
          name: station.port.name,
          value: station.value,
          label: spec.format(station.value),
          color: rampColor(spec, station.value).color,
        },
        geometry: {
          type: "Point",
          coordinates: [station.location.lon, station.location.lat],
        },
      })),
    },
    covered: stations.length,
    missing,
    max: Number.isFinite(maxValue) ? maxValue : null,
  };
}

/** Storm envelopes, drawn only where a port actually carries a storm flag. */
export function buildStorms(
  signals: WeatherSignal[],
  ports: PortSnapshot[],
): { data: GeoJSON.FeatureCollection; count: number } {
  const byCode = new Map(ports.map((port) => [port.code, port]));
  const features: GeoJSON.Feature[] = [];
  for (const signal of signals) {
    const risk = signal.stormRisk;
    const port = byCode.get(signal.portCode);
    if (!port?.location || risk == null || risk <= 0.01) continue;
    features.push({
      type: "Feature",
      properties: {
        portCode: signal.portCode,
        name: signal.name,
        risk,
      },
      geometry: {
        type: "Polygon",
        coordinates: [circlePolygon(port.location, 90 + risk * 320)],
      },
    });
  }
  return { data: { type: "FeatureCollection", features }, count: features.length };
}

/* ---------------------------------------------------------------- ports -- */

const RISK_COLOR: Record<string, string> = {
  severe: "#d05a4c",
  congested: "#d3a02f",
  high: "#d3a02f",
  medium: "#4c9fcb",
  normal: "#56b28d",
};

export function portColor(risk: string | null | undefined): string {
  return RISK_COLOR[(risk ?? "normal").toLowerCase()] ?? "#56b28d";
}

export function buildPorts(
  ports: PortSnapshot[],
  options: { selected?: string | null; emphasise?: Set<string> } = {},
): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: ports
      .filter((port) => port.location)
      .map((port) => {
        const calls = port.vesselCalls ?? 0;
        return {
          type: "Feature" as const,
          properties: {
            code: port.code,
            name: port.name,
            short: port.short,
            risk: port.risk,
            color: portColor(port.risk),
            radius: 3.6 + Math.min(4.4, Math.sqrt(Math.max(calls, 0)) * 1.1),
            selected: options.selected === port.code,
            emphasis:
              options.selected === port.code ||
              options.emphasise?.has(port.code) === true ||
              port.risk === "severe",
          },
          geometry: {
            type: "Point" as const,
            coordinates: [port.location!.lon, port.location!.lat],
          },
        };
      }),
  };
}

/* -------------------------------------------------------------- vessels -- */

/**
 * AIS-derived activity, one mark per port. These are daily port-call counts
 * from IMF PortWatch, not per-vessel tracks, so they are drawn as an activity
 * proxy at the port and labelled that way everywhere they appear.
 */
export function buildVesselActivity(
  vessels: VesselActivity[],
): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: vessels
      .filter((vessel) => vessel.location)
      .map((vessel) => ({
        type: "Feature" as const,
        properties: {
          portCode: vessel.portCode,
          name: vessel.name,
          calls: vessel.dailyPortCalls,
          queue: vessel.queueBuildup,
          color:
            vessel.queuePressure >= 0.65
              ? "#d05a4c"
              : vessel.queuePressure >= 0.4
                ? "#d3a02f"
                : "#4c9fcb",
        },
        geometry: {
          type: "Point" as const,
          coordinates: [vessel.location.lon, vessel.location.lat],
        },
      })),
  };
}

/* ---------------------------------------------------------------- lanes -- */

export interface Lane {
  id: string;
  from: { lat: number; lon: number };
  to: { lat: number; lon: number };
  color: string;
  width: number;
  opacity: number;
  dashed?: boolean;
  label?: string;
}

export function buildLanes(lanes: Lane[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: lanes.map((lane) => ({
      type: "Feature" as const,
      properties: {
        id: lane.id,
        color: lane.color,
        width: lane.width,
        opacity: lane.opacity,
        dashed: lane.dashed === true,
        label: lane.label ?? "",
      },
      geometry: {
        type: "LineString" as const,
        coordinates: greatCircle(lane.from, lane.to),
      },
    })),
  };
}

/**
 * Corridors from each chokepoint to the ports the event feed measured as
 * exposed to it. No exposure measurement, no lane.
 */
export function buildExposureLanes(
  events: NewsEvent[],
  ports: PortSnapshot[],
): { lanes: Lane[]; chokepoints: GeoJSON.FeatureCollection } {
  const byCode = new Map(ports.map((port) => [port.code, port]));
  const worst = new Map<string, { severity: number; exposure: Map<string, number> }>();

  for (const event of events) {
    if (!event.chokepoint) continue;
    const entry = worst.get(event.chokepoint) ?? {
      severity: 0,
      exposure: new Map<string, number>(),
    };
    entry.severity = Math.max(entry.severity, event.severityScore ?? 0);
    for (const exposure of event.exposure ?? []) {
      entry.exposure.set(
        exposure.portCode,
        Math.max(entry.exposure.get(exposure.portCode) ?? 0, exposure.exposure),
      );
    }
    worst.set(event.chokepoint, entry);
  }

  const lanes: Lane[] = [];
  const chokeFeatures: GeoJSON.Feature[] = [];

  for (const choke of CHOKEPOINTS) {
    const entry = worst.get(choke.code);
    const severity = entry?.severity ?? 0;
    const color = severity >= 0.7 ? "#d05a4c" : severity >= 0.4 ? "#d3a02f" : "#4c9fcb";
    chokeFeatures.push({
      type: "Feature",
      properties: {
        code: choke.code,
        name: choke.name,
        severity,
        color,
        exposedPorts: entry ? entry.exposure.size : 0,
      },
      geometry: { type: "Point", coordinates: [choke.lon, choke.lat] },
    });

    if (!entry) continue;
    const ranked = [...entry.exposure.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4);
    for (const [portCode, exposure] of ranked) {
      const port = byCode.get(portCode);
      if (!port?.location) continue;
      lanes.push({
        id: `${choke.code}-${portCode}`,
        from: { lat: choke.lat, lon: choke.lon },
        to: port.location,
        color,
        width: 0.6 + exposure * 1.8,
        opacity: 0.2 + exposure * 0.5,
        dashed: true,
        label: `${choke.name} → ${port.short} · exposure ${exposure.toFixed(2)}`,
      });
    }
  }

  return {
    lanes,
    chokepoints: { type: "FeatureCollection", features: chokeFeatures },
  };
}

/* --------------------------------------------------------------- events -- */

export function buildEvents(events: NewsEvent[]): {
  data: GeoJSON.FeatureCollection;
  placed: number;
  unplaced: number;
} {
  const features: GeoJSON.Feature[] = [];
  let unplaced = 0;
  for (const event of events) {
    const choke = event.chokepoint ? CHOKEPOINT_BY_CODE.get(event.chokepoint) : null;
    if (!choke) {
      unplaced += 1;
      continue;
    }
    features.push({
      type: "Feature",
      properties: {
        id: event.id,
        title: event.title,
        severity: event.severityScore,
        color: event.severityScore >= 0.7 ? "#d05a4c" : "#d3a02f",
      },
      geometry: { type: "Point", coordinates: [choke.lon, choke.lat] },
    });
  }
  return {
    data: { type: "FeatureCollection", features },
    placed: features.length,
    unplaced,
  };
}

/* -------------------------------------------- schematic port-local zones -- */

/**
 * Approach geometry for the port-local view.
 *
 * These are schematic, and every screen that shows them says so. The radii come
 * from measured anchorage counts and queue pressure; the bearings come from the
 * port's coast. No berth layout is claimed — this is a pressure diagram drawn
 * in the right place, not a survey.
 */
export function buildPortZones(port: PortSnapshot): GeoJSON.FeatureCollection {
  if (!port.location) return { type: "FeatureCollection", features: [] };

  const seaward =
    port.coast === "east" ? 90 : port.coast === "south" ? 180 : 270;
  const anchorageKm = 6 + Math.min(18, (port.anchorageCount ?? 0) * 3.2);
  const queue = port.queuePressure ?? 0;

  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {
          kind: "approach",
          label: "Approach sector",
          color: "#4c9fcb",
          opacity: 0.07,
          dashed: true,
        },
        geometry: {
          type: "Polygon",
          coordinates: [sector(port.location, 46, seaward - 34, seaward + 34)],
        },
      },
      {
        type: "Feature",
        properties: {
          kind: "anchorage",
          label: `Anchorage · ${(port.anchorageCount ?? 0).toFixed(1)} waiting`,
          color: queue >= 0.6 ? "#d05a4c" : queue >= 0.35 ? "#d3a02f" : "#56b28d",
          opacity: 0.12,
          dashed: false,
        },
        geometry: {
          type: "Polygon",
          coordinates: [circlePolygon(port.location, anchorageKm)],
        },
      },
      {
        type: "Feature",
        properties: {
          kind: "terminal",
          label: "Terminal area",
          color: "#8a7fc4",
          opacity: 0.14,
          dashed: false,
        },
        geometry: {
          type: "Polygon",
          coordinates: [circlePolygon(port.location, 2.4, 20)],
        },
      },
    ],
  };
}
