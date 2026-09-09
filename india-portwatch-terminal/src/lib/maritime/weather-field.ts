/**
 * Sampling the weather between the stations.
 *
 * Thirteen port stations is not a field, so anything drawn between them is an
 * interpolation and is treated as one: inverse distance weighting with a hard
 * cutoff, so the field simply stops rather than being extrapolated across an
 * ocean nobody measured. The cutoff is what keeps "calm" distinguishable from
 * "not observed".
 */

import { haversineKm, type Position } from "./geo";
import {
  hazardOf,
  WEATHER_FIELDS,
  type WeatherFieldKey,
  type WeatherFieldSpec,
  type WeatherFrame,
  type WeatherStation,
} from "./weather-model";

/**
 * Beyond this range from every station the field carries no value at all.
 *
 * Deliberately tight. Thirteen stations interpolated across half an ocean
 * produce enormous soft discs that read as weather but are really one port's
 * rain gauge painted over a thousand kilometres of water nobody measured. At
 * 320 km the field stays over the coastal water the stations can speak for, and
 * the open ocean stays honestly empty.
 */
export const FIELD_CUTOFF_KM = 320;

export interface FieldSample {
  value: number | null;
  /** Distance to the nearest station that carried a reading, km. */
  nearestKm: number;
}

function readingsFor(
  frame: WeatherFrame,
  spec: WeatherFieldSpec,
): Array<{ station: WeatherStation; value: number }> {
  const out: Array<{ station: WeatherStation; value: number }> = [];
  for (const station of frame.stations) {
    const value = spec.read(station);
    if (value == null || Number.isNaN(value)) continue;
    out.push({ station, value });
  }
  return out;
}

export interface SampledField {
  spec: WeatherFieldSpec;
  covered: number;
  missing: string[];
  min: number | null;
  max: number | null;
  sample(lon: number, lat: number): FieldSample;
}

export function sampleField(frame: WeatherFrame, key: WeatherFieldKey): SampledField {
  const spec = WEATHER_FIELDS[key];
  const readings = readingsFor(frame, spec);
  const missing = frame.stations
    .filter((station) => {
      const value = spec.read(station);
      return value == null || Number.isNaN(value);
    })
    .map((station) => station.name);

  const values = readings.map((r) => r.value);

  return {
    spec,
    covered: readings.length,
    missing,
    min: values.length ? Math.min(...values) : null,
    max: values.length ? Math.max(...values) : null,
    sample(lon: number, lat: number): FieldSample {
      let weighted = 0;
      let weights = 0;
      let nearest = Infinity;
      for (const { station, value } of readings) {
        const km = haversineKm([lon, lat], [station.lon, station.lat]);
        if (km < nearest) nearest = km;
        if (km > FIELD_CUTOFF_KM) continue;
        // Cubic falloff rather than inverse-square: a station's reading stays
        // its own near the port instead of being averaged into a neighbour's
        // three hundred kilometres away.
        const w = 1 / Math.max(km, 12) ** 3;
        weighted += value * w;
        weights += w;
      }
      if (!weights) return { value: null, nearestKm: nearest };
      return { value: weighted / weights, nearestKm: nearest };
    },
  };
}

/* ------------------------------------------------------------------ wind -- */

export interface WindSample {
  speedKn: number;
  /** Direction the wind blows FROM, degrees true. Modelled, not observed. */
  fromDeg: number;
  /** Vector components in knots, blowing towards. */
  u: number;
  v: number;
}

/**
 * The wind at a point, for the flow animation.
 *
 * Speed comes from the observations. Direction comes from the monsoon
 * climatology on each station and is interpolated as a vector so two stations
 * either side of a shear line average to something between them rather than
 * cancelling.
 */
export function sampleWind(frame: WeatherFrame, lon: number, lat: number): WindSample | null {
  let ux = 0;
  let uy = 0;
  let weights = 0;
  let nearest = Infinity;

  for (const station of frame.stations) {
    if (station.windKn == null) continue;
    const km = haversineKm([lon, lat], [station.lon, station.lat]);
    if (km < nearest) nearest = km;
    if (km > FIELD_CUTOFF_KM) continue;
    const w = 1 / Math.max(km, 25) ** 2.5;
    // Blowing towards is the reciprocal of blowing from.
    const towards = ((station.windFromDeg + 180) % 360) * (Math.PI / 180);
    ux += Math.sin(towards) * station.windKn * w;
    uy += Math.cos(towards) * station.windKn * w;
    weights += w;
  }
  if (!weights) return null;

  const u = ux / weights;
  const v = uy / weights;
  const speedKn = Math.hypot(u, v);
  return {
    speedKn,
    fromDeg: ((Math.atan2(u, v) * 180) / Math.PI + 180 + 360) % 360,
    u,
    v,
  };
}

/* ------------------------------------------------------- route exposure -- */

export type ExposureLevel = "normal" | "watch" | "severe";

export interface ExposureSegment {
  coords: Position[];
  /** Hours from now that the vessel reaches the start of this segment. */
  leadHours: number;
  level: ExposureLevel;
  impact: number | null;
  windKn: number | null;
  rainMm: number | null;
  stormRisk: number | null;
  label: string;
}

export function exposureLevel(impact: number | null, storm: number | null): ExposureLevel {
  const worst = Math.max(impact ?? 0, (storm ?? 0) * 2.2);
  if (worst >= 0.24) return "severe";
  if (worst >= 0.12) return "watch";
  return "normal";
}

export const EXPOSURE_COLOR: Record<ExposureLevel, string> = {
  normal: "#56b28d",
  watch: "#d3a02f",
  severe: "#d05a4c",
};

/**
 * What a vessel will meet along the water still ahead of it.
 *
 * Each sample is taken from the forecast frame for the time the vessel actually
 * reaches that point, not from the present frame -- which is the whole point of
 * having a timeline. Segments are merged where the level does not change, so a
 * long calm passage is one green run rather than forty.
 */
export function routeExposure(
  ahead: Position[],
  options: {
    /** Departure instant for the first point. */
    at: number;
    speedKn: number;
    frameAt: (at: number) => WeatherFrame;
    /** Samples along the passage. Twelve reads well without going soft. */
    samples?: number;
  },
): ExposureSegment[] {
  if (ahead.length < 2) return [];
  const samples = options.samples ?? 12;

  // Along-track distance so the sample times are right.
  const cumulative: number[] = [0];
  for (let i = 1; i < ahead.length; i += 1) {
    cumulative.push(cumulative[i - 1] + haversineKm(ahead[i - 1], ahead[i]));
  }
  const totalKm = cumulative[cumulative.length - 1];
  if (totalKm <= 0) return [];

  const kmPerHour = Math.max(1, options.speedKn * 1.852);
  const points: Array<{ index: number; leadHours: number }> = [];
  for (let i = 0; i <= samples; i += 1) {
    const km = (totalKm * i) / samples;
    let index = 0;
    while (index < cumulative.length - 1 && cumulative[index + 1] < km) index += 1;
    points.push({ index, leadHours: km / kmPerHour });
  }

  const raw = points.map((point) => {
    const position = ahead[Math.min(point.index, ahead.length - 1)];
    const frame = options.frameAt(options.at + point.leadHours * 3_600_000);
    const impact = sampleField(frame, "impact").sample(position[0], position[1]).value;
    const storm = sampleField(frame, "storm").sample(position[0], position[1]).value;
    const wind = sampleField(frame, "wind").sample(position[0], position[1]).value;
    const rain = sampleField(frame, "precipitation").sample(position[0], position[1]).value;
    return {
      ...point,
      impact,
      storm,
      wind,
      rain,
      level: exposureLevel(impact, storm),
    };
  });

  const segments: ExposureSegment[] = [];
  let start = 0;
  for (let i = 1; i <= raw.length - 1; i += 1) {
    const changed = raw[i].level !== raw[start].level;
    const last = i === raw.length - 1;
    if (!changed && !last) continue;
    const end = changed ? i : raw.length - 1;
    const coords = ahead.slice(raw[start].index, Math.max(raw[start].index + 2, raw[end].index + 1));
    if (coords.length >= 2) {
      const head = raw[start];
      segments.push({
        coords,
        leadHours: head.leadHours,
        level: head.level,
        impact: head.impact,
        windKn: head.wind,
        rainMm: head.rain,
        stormRisk: head.storm,
        label:
          head.level === "severe"
            ? "Severe weather on this leg"
            : head.level === "watch"
              ? "Weather exposure on this leg"
              : "No significant weather forecast",
      });
    }
    start = i;
  }
  return segments;
}

/** The single worst thing along a passage, for a one-line summary. */
export function worstExposure(segments: ExposureSegment[]): ExposureSegment | null {
  const order: Record<ExposureLevel, number> = { normal: 0, watch: 1, severe: 2 };
  let worst: ExposureSegment | null = null;
  for (const segment of segments) {
    if (!worst || order[segment.level] > order[worst.level]) worst = segment;
  }
  return worst;
}

export { hazardOf };
