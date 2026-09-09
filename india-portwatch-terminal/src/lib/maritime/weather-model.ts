/**
 * The forecast weather model behind the map's environment layer.
 *
 * What the artefact actually carries, per port: one set of surface observations
 * at a single instant, and a daily series of the weather-impact index out to
 * nine days. Everything this module produces is built from those two things,
 * and every derivation is named rather than blended into the picture:
 *
 *   observed    wind, gust, precipitation, visibility and storm risk at the
 *               observation instant. Measured.
 *   forecast    the impact index on each forecast day. Model output.
 *   derived     sub-daily values between forecast days, and the surface fields
 *               scaled to them. Interpolation, labelled DERIVED wherever shown.
 *   modelled    wind direction, which the feed does not carry at all. A monsoon
 *               climatology, labelled MODELLED and never called an observation.
 *   unavailable significant wave height. The marine feed returned nothing, and
 *               the product says so instead of substituting a sea state.
 */

import type { PortSnapshot, WeatherSignal } from "@/types/portwatch";
import { DEG } from "./geo";

export type WeatherFieldKey =
  | "precipitation"
  | "wind"
  | "gust"
  | "visibility"
  | "impact"
  | "storm";

export interface WeatherFieldSpec {
  key: WeatherFieldKey;
  label: string;
  unit: string;
  /** Upper edge of each band, ascending. Standard meteorological steps. */
  bands: number[];
  colors: string[];
  /** True when a low reading is the hazardous one. */
  inverted?: boolean;
  read: (station: WeatherStation) => number | null;
  format: (value: number) => string;
}

/* A radar ramp: cold and translucent at the bottom, hot and opaque at the top.
   It stays clear of the five status hues so a weather cell never reads as an
   alert severity. */
const RAIN_RAMP = ["#1c5e77", "#1f7f7a", "#3f9b5c", "#8faa3c", "#c99a2f", "#cf6a3c", "#b8433f"];
const WIND_RAMP = ["#1a5470", "#237392", "#3796a6", "#69a271", "#b4993a", "#c3703c", "#b8433f"];
const RISK_RAMP = ["#1c5e77", "#2a7b93", "#5d9482", "#a4a144", "#c48437", "#c05a41", "#a63f3f"];

export const WEATHER_FIELDS: Record<WeatherFieldKey, WeatherFieldSpec> = {
  precipitation: {
    key: "precipitation",
    label: "Precipitation",
    unit: "mm/24h",
    // Near-logarithmic, the way a precipitation radar is scaled: light rain has
    // to be visible, and a downpour must not saturate everything below it.
    bands: [0.2, 0.5, 1, 2.5, 6, 15, 40],
    colors: RAIN_RAMP,
    read: (s) => s.rainMm,
    format: (v) => `${v.toFixed(1)} mm`,
  },
  wind: {
    key: "wind",
    label: "Wind speed",
    unit: "kn",
    bands: [3, 6, 10, 14, 19, 25, 34],
    colors: WIND_RAMP,
    read: (s) => s.windKn,
    format: (v) => `${v.toFixed(1)} kn`,
  },
  gust: {
    key: "gust",
    label: "Gust",
    unit: "kn",
    bands: [8, 13, 18, 24, 30, 38, 48],
    colors: WIND_RAMP,
    read: (s) => s.gustKn,
    format: (v) => `${v.toFixed(1)} kn`,
  },
  visibility: {
    key: "visibility",
    label: "Visibility",
    unit: "km",
    bands: [1, 2, 4, 7, 11, 16, 24],
    colors: [...RISK_RAMP].reverse(),
    inverted: true,
    read: (s) => s.visibilityKm,
    format: (v) => `${v.toFixed(1)} km`,
  },
  impact: {
    key: "impact",
    label: "Operational impact",
    unit: "index",
    bands: [0.04, 0.08, 0.12, 0.18, 0.26, 0.4, 0.6],
    colors: RISK_RAMP,
    read: (s) => s.impact,
    format: (v) => v.toFixed(3),
  },
  storm: {
    key: "storm",
    label: "Storm risk",
    unit: "index",
    bands: [0.005, 0.015, 0.035, 0.07, 0.15, 0.3, 0.5],
    colors: RISK_RAMP,
    read: (s) => s.stormRisk,
    format: (v) => v.toFixed(3),
  },
};

export const WEATHER_FIELD_LIST = Object.values(WEATHER_FIELDS);

/* -------------------------------------------------------------- stations -- */

export interface WeatherStation {
  portCode: string;
  name: string;
  lon: number;
  lat: number;
  rainMm: number | null;
  windKn: number | null;
  gustKn: number | null;
  visibilityKm: number | null;
  stormRisk: number | null;
  impact: number | null;
  /** Direction the wind is blowing FROM, degrees true. Modelled, not observed. */
  windFromDeg: number;
  /** Significant wave height. Always null: the marine feed carries none. */
  waveHeightM: null;
  regime: string | null;
  advisory: string;
}

export interface WeatherFrame {
  /** The instant this frame describes. */
  at: number;
  stations: WeatherStation[];
  /** True when values were scaled off the daily forecast rather than observed. */
  derived: boolean;
  /** Hours ahead of the observation instant. */
  leadHours: number;
}

export interface WeatherTimeline {
  /** Instant of the surface observations. */
  observedAt: number;
  /** First and last instants the forecast series covers. */
  from: number;
  to: number;
  /** Every instant the artefact carries a forecast value for. */
  steps: number[];
  /** National mean impact at each step, for the scrubber's own read-out. */
  meanImpact: number[];
  frameAt(at: number): WeatherFrame;
  available: boolean;
  /** One sentence naming what the field is and how it was made. */
  note: string;
}

/* ------------------------------------------------------ wind climatology -- */

/**
 * Wind direction from monsoon climatology.
 *
 * The Open-Meteo extract this product ingests carries wind *speed* but no
 * direction, and a flow animation needs one. Rather than draw arrows in an
 * arbitrary direction, this returns the prevailing direction for the season and
 * basin -- south-westerly over both coasts through the summer monsoon, backing
 * to north-easterly from November -- and every surface that shows it says
 * MODELLED. Speed on the same screen is measured; direction is not.
 */
export function climatologicalWindFrom(lon: number, lat: number, at: number): number {
  const month = new Date(at).getUTCMonth();
  // Southwest monsoon runs June to September; northeast monsoon December to
  // February; the rest is transition, interpolated between the two.
  const summer = month >= 5 && month <= 8 ? 1 : month === 4 || month === 9 ? 0.5 : month >= 11 || month <= 1 ? 0 : 0.35;

  // Over the Bay of Bengal the summer flow is more southerly than over the
  // Arabian Sea, and the winter flow comes off the subcontinent from the north.
  const bay = lon > 80 ? 1 : lon < 72 ? 0 : (lon - 72) / 8;
  const summerFrom = 235 - bay * 40;
  const winterFrom = 35 + bay * 20;
  const base = winterFrom + (summerFrom - winterFrom) * summer;

  // A gentle latitude shear so the field is not a single uniform arrow.
  const shear = Math.sin(lat * DEG * 2) * 12;
  return (base + shear + 360) % 360;
}

/* --------------------------------------------------------------- builder -- */

function parse(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
  return Number.isNaN(ms) ? null : ms;
}

interface Series {
  times: number[];
  impacts: number[];
}

function interpolate(series: Series, at: number): number | null {
  const { times, impacts } = series;
  if (!times.length) return null;
  if (at <= times[0]) return impacts[0];
  if (at >= times[times.length - 1]) return impacts[impacts.length - 1];
  for (let i = 1; i < times.length; i += 1) {
    if (at <= times[i]) {
      const span = times[i] - times[i - 1];
      const f = span > 0 ? (at - times[i - 1]) / span : 0;
      return impacts[i - 1] + (impacts[i] - impacts[i - 1]) * f;
    }
  }
  return impacts[impacts.length - 1];
}

const EMPTY_TIMELINE: WeatherTimeline = {
  observedAt: 0,
  from: 0,
  to: 0,
  steps: [],
  meanImpact: [],
  frameAt: (at) => ({ at, stations: [], derived: false, leadHours: 0 }),
  available: false,
  note: "No weather artefact in this run. The environment layer is unavailable.",
};

export function buildWeatherTimeline(
  signals: WeatherSignal[],
  ports: PortSnapshot[],
): WeatherTimeline {
  if (!signals.length) return EMPTY_TIMELINE;

  const byCode = new Map(ports.map((port) => [port.code, port]));
  const located = signals
    .map((signal) => {
      const port = byCode.get(signal.portCode);
      if (!port?.location) return null;
      return { signal, lon: port.location.lon, lat: port.location.lat };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null);

  if (!located.length) return EMPTY_TIMELINE;

  const observedAt =
    parse(located[0].signal.observedAt) ?? Date.now();

  const seriesByCode = new Map<string, Series>();
  const stepSet = new Set<number>();
  for (const entry of located) {
    const times: number[] = [observedAt];
    const impacts: number[] = [entry.signal.impactScore ?? 0];
    for (const point of entry.signal.forecast ?? []) {
      const ms = parse(point.date);
      if (ms == null || point.impact == null) continue;
      times.push(ms);
      impacts.push(point.impact);
      stepSet.add(ms);
    }
    seriesByCode.set(entry.signal.portCode, { times, impacts });
  }

  const steps = [...stepSet].sort((a, b) => a - b);
  const from = steps.length ? Math.min(steps[0], observedAt) : observedAt;
  const to = steps.length ? steps[steps.length - 1] : observedAt;

  const frameAt = (at: number): WeatherFrame => {
    const clamped = Math.min(Math.max(at, from), to);
    const stations: WeatherStation[] = located.map(({ signal, lon, lat }) => {
      const series = seriesByCode.get(signal.portCode);
      const baseImpact = signal.impactScore ?? 0;
      const impact = series ? interpolate(series, clamped) : baseImpact;
      // The forecast moves the impact index; the surface fields ride on it in
      // proportion, which is the only defensible way to animate observations
      // the feed only reports once.
      const ratio = baseImpact > 1e-6 && impact != null ? impact / baseImpact : 1;
      const scale = (value: number | null, sensitivity = 1) =>
        value == null ? null : value * (1 + (ratio - 1) * sensitivity);

      return {
        portCode: signal.portCode,
        name: signal.name,
        lon,
        lat,
        rainMm: scale(signal.rainfallMm24h, 1),
        windKn: scale(signal.windKnots, 0.55),
        gustKn: scale(signal.gustKnots, 0.55),
        // Poor visibility travels with the weather, so it moves the other way.
        visibilityKm:
          signal.visibilityKm == null
            ? null
            : signal.visibilityKm / Math.max(0.4, 1 + (ratio - 1) * 0.4),
        stormRisk: scale(signal.stormRisk, 1.2),
        impact,
        windFromDeg: climatologicalWindFrom(lon, lat, clamped),
        waveHeightM: null,
        regime: signal.weatherRegime,
        advisory: signal.advisory,
      };
    });

    return {
      at: clamped,
      stations,
      derived: Math.abs(clamped - observedAt) > 60_000,
      leadHours: (clamped - observedAt) / 3_600_000,
    };
  };

  const meanImpact = steps.map((step) => {
    const frame = frameAt(step);
    const values = frame.stations
      .map((station) => station.impact)
      .filter((value): value is number => value != null);
    return values.length ? values.reduce((sum, v) => sum + v, 0) / values.length : 0;
  });

  return {
    observedAt,
    from,
    to,
    steps,
    meanImpact,
    frameAt,
    available: true,
    note:
      "Surface values are Open-Meteo observations at 13 port stations. Values away " +
      "from the observation instant are scaled by the model's daily weather-impact " +
      "forecast and interpolated between forecast days. Wind direction is monsoon " +
      "climatology, not an observation. Significant wave height is unavailable.",
  };
}

/* ---------------------------------------------------------------- colour -- */

function hexToRgb(hex: string): [number, number, number] {
  const value = parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function mix(a: [number, number, number], b: [number, number, number], t: number) {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ] as [number, number, number];
}

const RAMP_CACHE = new Map<string, Array<[number, number, number]>>();

function rampFor(spec: WeatherFieldSpec): Array<[number, number, number]> {
  const cached = RAMP_CACHE.get(spec.key);
  if (cached) return cached;
  const rgb = spec.colors.map(hexToRgb);
  RAMP_CACHE.set(spec.key, rgb);
  return rgb;
}

/**
 * Continuous colour across the ramp.
 *
 * Snapping each sample to a band turns the field into a visible quilt;
 * interpolating between neighbouring band colours keeps the legend's meaning
 * while letting the field vary smoothly.
 */
export function rampColor(
  spec: WeatherFieldSpec,
  value: number,
): { rgb: [number, number, number]; intensity: number } {
  const colors = rampFor(spec);
  const bands = spec.bands;
  if (value <= bands[0]) {
    const t = Math.max(0, value / Math.max(bands[0], 1e-9));
    return { rgb: mix(colors[0], colors[1] ?? colors[0], t * 0.4), intensity: t * (1 / bands.length) };
  }
  const last = bands[bands.length - 1];
  if (value >= last) return { rgb: colors[colors.length - 1], intensity: 1 };
  for (let i = 1; i < bands.length; i += 1) {
    if (value <= bands[i]) {
      const span = bands[i] - bands[i - 1] || 1;
      const t = (value - bands[i - 1]) / span;
      return {
        rgb: mix(colors[i - 1], colors[i], t),
        intensity: (i - 1 + t) / (bands.length - 1),
      };
    }
  }
  return { rgb: colors[colors.length - 1], intensity: 1 };
}

/** Hazard, 0 to 1, with the inverted fields turned the right way up. */
export function hazardOf(spec: WeatherFieldSpec, value: number): number {
  const { intensity } = rampColor(spec, value);
  return spec.inverted ? 1 - intensity : intensity;
}
