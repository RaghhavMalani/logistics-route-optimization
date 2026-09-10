/**
 * Turning the weather model into things MapLibre can draw.
 *
 * The environment layer is a **composite**, not a field picker. Weather is not a
 * variable an operator opts into one dimension at a time -- a duty officer needs
 * to see, in one look, where it is raining, where it is blowing, and where a
 * cell is severe enough to stop a crane. Making them choose "precipitation OR
 * wind" hides two thirds of the picture behind a radio button.
 *
 * So one raster carries three things at once:
 *
 *   precipitation   the base radar field. Colour and most of the opacity.
 *   wind            a texture modulation, so a windy dry area is still visible
 *                   and a calm wet one reads as flat. Wind *direction* is drawn
 *                   separately by the particle layer.
 *   severity        a hot-edged highlight where the operational impact index or
 *                   the storm flag crosses the threshold at which work stops.
 *
 * Storm cells and their motion are drawn as vector features on top, because a
 * cell has an identity an operator selects, and a raster has no identity.
 *
 * The single-field raster is kept for the port weather screen, where an analyst
 * genuinely is comparing one variable across ports.
 */

import {
  FIELD_CUTOFF_KM,
  sampleField,
  sampleWind,
  type SampledField,
} from "@/lib/maritime/weather-field";
import {
  hazardOf,
  rampColor,
  WEATHER_FIELDS,
  type WeatherFieldKey,
  type WeatherFrame,
} from "@/lib/maritime/weather-model";
import { circleRing } from "./geometry";

export interface WeatherRaster {
  url: string;
  coordinates: [[number, number], [number, number], [number, number], [number, number]];
  covered: number;
  missing: string[];
  min: number | null;
  max: number | null;
  /** What this raster actually carries. Rendered in the legend. */
  composite: boolean;
  /** Peak values across the field, for the legend's read-out. */
  peaks: {
    rainMm: number | null;
    windKn: number | null;
    impact: number | null;
    stormRisk: number | null;
  };
}

/** Degrees per raster pixel. Fine enough to look continuous once resampled. */
const RESOLUTION = 0.12;
const PAD_DEG = FIELD_CUTOFF_KM / 111;

/**
 * Opacity ceiling for the composite.
 *
 * Higher than the old single-field cap of 0.5, because the previous field was
 * so restrained that on a dark chart it read as a smudge rather than as weather.
 * It is still a ceiling: at 0.66 a vessel marker and a coastline both remain
 * legible through the heaviest cell, which is the constraint that matters.
 */
const MAX_ALPHA = 0.66;

/** Below this the pixel is left transparent: painting it would tint the basin. */
const NOISE_FLOOR = 0.035;

/**
 * Impact index at which the composite starts adding the severity highlight.
 *
 * Matched to the crane-stop threshold in the twin's simulation, so a cell that
 * looks alarming on the chart is one that actually stops work rather than one
 * that merely scores highly.
 */
const SEVERE_IMPACT = 0.22;
const SEVERE_STORM = 0.08;

/** Hot edge painted into severe cells. Distinct from every status hue. */
const SEVERE_RGB: [number, number, number] = [214, 92, 74];

function bounds(frame: WeatherFrame) {
  const lons = frame.stations.map((s) => s.lon);
  const lats = frame.stations.map((s) => s.lat);
  return {
    minLon: Math.min(...lons) - PAD_DEG,
    maxLon: Math.max(...lons) + PAD_DEG,
    minLat: Math.min(...lats) - PAD_DEG,
    maxLat: Math.max(...lats) + PAD_DEG,
  };
}

function mixRgb(
  a: [number, number, number],
  b: [number, number, number],
  t: number,
): [number, number, number] {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ];
}

/**
 * The composite environment sheet.
 *
 * One pass over the raster grid samples four fields at each pixel. That is four
 * inverse-distance interpolations per pixel over thirteen stations, which at
 * this resolution is a few hundred thousand operations -- cheap enough to rebuild
 * whenever the forecast cursor moves, and far cheaper than the geometry the
 * polygon version of this used to push at the GPU.
 */
export function buildCompositeRaster(frame: WeatherFrame): WeatherRaster | null {
  if (typeof document === "undefined") return null;

  const rain: SampledField = sampleField(frame, "precipitation");
  const wind: SampledField = sampleField(frame, "wind");
  const impact: SampledField = sampleField(frame, "impact");
  const storm: SampledField = sampleField(frame, "storm");
  if (!rain.covered && !wind.covered && !impact.covered) return null;

  const { minLon, maxLon, minLat, maxLat } = bounds(frame);
  const width = Math.max(2, Math.round((maxLon - minLon) / RESOLUTION));
  const height = Math.max(2, Math.round((maxLat - minLat) / RESOLUTION));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const image = ctx.createImageData(width, height);
  const rainSpec = WEATHER_FIELDS.precipitation;
  const windSpec = WEATHER_FIELDS.wind;

  const peaks = {
    rainMm: null as number | null,
    windKn: null as number | null,
    impact: null as number | null,
    stormRisk: null as number | null,
  };

  for (let y = 0; y < height; y += 1) {
    // Image rows run north to south.
    const lat = maxLat - ((y + 0.5) / height) * (maxLat - minLat);
    for (let x = 0; x < width; x += 1) {
      const lon = minLon + ((x + 0.5) / width) * (maxLon - minLon);
      const offset = (y * width + x) * 4;

      const rainSample = rain.sample(lon, lat);
      const windSample = wind.sample(lon, lat);
      const impactSample = impact.sample(lon, lat);
      const stormSample = storm.sample(lon, lat);

      const nearest = Math.min(
        rainSample.nearestKm,
        windSample.nearestKm,
        impactSample.nearestKm,
      );
      if (
        rainSample.value == null &&
        windSample.value == null &&
        impactSample.value == null
      ) {
        continue;
      }

      // Fade the last third of the reach to nothing. Without it the field ends
      // on a hard circle, which reads as a data boundary rather than weather.
      const reach =
        1 -
        Math.min(
          1,
          Math.max(0, (nearest - FIELD_CUTOFF_KM * 0.55) / (FIELD_CUTOFF_KM * 0.45)),
        );

      const rainHazard = rainSample.value == null
        ? 0 : hazardOf(rainSpec, rainSample.value) * reach;
      const windHazard = windSample.value == null
        ? 0 : hazardOf(windSpec, windSample.value) * reach;
      const impactValue = impactSample.value ?? 0;
      const stormValue = stormSample.value ?? 0;

      // Wind contributes at a third of precipitation's weight. Rain is what a
      // radar sheet is *about*; wind is why a dry but blowing basin should not
      // read as empty.
      const combined = Math.max(rainHazard, windHazard * 0.55, rainHazard * 0.7 + windHazard * 0.45);
      if (combined < NOISE_FLOOR) continue;

      let rgb: [number, number, number] = rainSample.value != null && rainHazard >= windHazard * 0.5
        ? rampColor(rainSpec, rainSample.value).rgb
        : windSample.value != null
          ? rampColor(windSpec, windSample.value).rgb
          : rampColor(rainSpec, rainSample.value ?? 0).rgb;

      // The severity highlight. A cell that would stop a crane gets pulled
      // toward the hot edge in proportion to how far past the threshold it is,
      // so a severe cell is visible at a glance and a marginal one is not
      // dressed up as one.
      const severity = Math.max(
        impactValue > SEVERE_IMPACT
          ? (impactValue - SEVERE_IMPACT) / (0.6 - SEVERE_IMPACT)
          : 0,
        stormValue > SEVERE_STORM
          ? (stormValue - SEVERE_STORM) / (0.4 - SEVERE_STORM)
          : 0,
      );
      let alpha = combined;
      if (severity > 0) {
        const t = Math.min(1, severity) * reach;
        rgb = mixRgb(rgb, SEVERE_RGB, t * 0.7);
        alpha = Math.min(1, alpha + t * 0.3);
      }

      image.data[offset] = rgb[0];
      image.data[offset + 1] = rgb[1];
      image.data[offset + 2] = rgb[2];
      image.data[offset + 3] = Math.round(
        255 * Math.min(MAX_ALPHA, 0.05 + alpha * 0.82),
      );

      if (rainSample.value != null) {
        peaks.rainMm = Math.max(peaks.rainMm ?? 0, rainSample.value);
      }
      if (windSample.value != null) {
        peaks.windKn = Math.max(peaks.windKn ?? 0, windSample.value);
      }
      if (impactSample.value != null) {
        peaks.impact = Math.max(peaks.impact ?? 0, impactSample.value);
      }
      if (stormSample.value != null) {
        peaks.stormRisk = Math.max(peaks.stormRisk ?? 0, stormSample.value);
      }
    }
  }

  ctx.putImageData(image, 0, 0);

  const missing = new Set<string>([...rain.missing, ...wind.missing]);
  return {
    url: canvas.toDataURL("image/png"),
    coordinates: [
      [minLon, maxLat],
      [maxLon, maxLat],
      [maxLon, minLat],
      [minLon, minLat],
    ],
    covered: Math.max(rain.covered, wind.covered, impact.covered),
    missing: [...missing],
    min: rain.min,
    max: rain.max,
    composite: true,
    peaks,
  };
}

/**
 * A single-field raster.
 *
 * Kept for the port weather screen, where an analyst really is comparing one
 * variable across ports and the composite would get in the way.
 */
export function buildWeatherRaster(
  frame: WeatherFrame,
  key: WeatherFieldKey,
): WeatherRaster | null {
  if (typeof document === "undefined") return null;
  const field: SampledField = sampleField(frame, key);
  if (!field.covered) return null;

  const { minLon, maxLon, minLat, maxLat } = bounds(frame);
  const width = Math.max(2, Math.round((maxLon - minLon) / RESOLUTION));
  const height = Math.max(2, Math.round((maxLat - minLat) / RESOLUTION));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const image = ctx.createImageData(width, height);
  const spec = WEATHER_FIELDS[key];

  for (let y = 0; y < height; y += 1) {
    const lat = maxLat - ((y + 0.5) / height) * (maxLat - minLat);
    for (let x = 0; x < width; x += 1) {
      const lon = minLon + ((x + 0.5) / width) * (maxLon - minLon);
      const { value, nearestKm } = field.sample(lon, lat);
      const offset = (y * width + x) * 4;
      if (value == null) continue;

      const reach =
        1 -
        Math.min(
          1,
          Math.max(0, (nearestKm - FIELD_CUTOFF_KM * 0.55) / (FIELD_CUTOFF_KM * 0.45)),
        );
      const hazard = hazardOf(spec, value) * reach;
      if (hazard < NOISE_FLOOR) continue;

      const { rgb } = rampColor(spec, value);
      image.data[offset] = rgb[0];
      image.data[offset + 1] = rgb[1];
      image.data[offset + 2] = rgb[2];
      image.data[offset + 3] = Math.round(255 * Math.min(0.58, 0.04 + hazard * 0.7));
    }
  }

  ctx.putImageData(image, 0, 0);

  return {
    url: canvas.toDataURL("image/png"),
    coordinates: [
      [minLon, maxLat],
      [maxLon, maxLat],
      [maxLon, minLat],
      [minLon, minLat],
    ],
    covered: field.covered,
    missing: field.missing,
    min: field.min,
    max: field.max,
    composite: false,
    peaks: { rainMm: null, windKn: null, impact: null, stormRisk: null },
  };
}

/* ----------------------------------------------------------- storm cells -- */

export interface StormCell {
  portCode: string;
  name: string;
  risk: number;
  lon: number;
  lat: number;
  /** Direction the cell is moving toward, degrees true. Null when unavailable. */
  motionDeg: number | null;
  motionKn: number | null;
  /** True only when the feed carried an actual forecast track. */
  hasTrack: boolean;
}

/**
 * Storm envelopes, centres and motion.
 *
 * Motion is derived, and the inspector says so: the artefact carries a storm
 * *risk index* per port across the forecast series, not a track. Where the risk
 * is rising at one station and falling at a neighbour, the difference gives a
 * direction of travel -- which is a real inference from the data, unlike a cone
 * of uncertainty, which would be an invention. Where the series is flat, no
 * motion is drawn at all.
 */
export function buildStormCells(
  frame: WeatherFrame,
  previous?: WeatherFrame | null,
): {
  data: GeoJSON.FeatureCollection;
  cells: StormCell[];
} {
  const features: GeoJSON.Feature[] = [];
  const cells: StormCell[] = [];

  const before = new Map(
    (previous?.stations ?? []).map((s) => [s.portCode, s.stormRisk ?? 0]),
  );

  for (const station of frame.stations) {
    const risk = station.stormRisk;
    if (risk == null || risk <= 0.001) continue;

    // Motion from the risk gradient across neighbouring stations: a cell
    // strengthening to the east of a weakening one is travelling east.
    let motionDeg: number | null = null;
    let motionKn: number | null = null;
    const trend = risk - (before.get(station.portCode) ?? risk);
    if (Math.abs(trend) > 0.004) {
      let dx = 0;
      let dy = 0;
      let weight = 0;
      for (const other of frame.stations) {
        if (other.portCode === station.portCode || other.stormRisk == null) continue;
        const dLon = other.lon - station.lon;
        const dLat = other.lat - station.lat;
        const distance = Math.hypot(dLon, dLat);
        if (distance < 0.2 || distance > 8) continue;
        const gradient = (other.stormRisk - risk) / distance;
        dx += (dLon / distance) * gradient;
        dy += (dLat / distance) * gradient;
        weight += 1;
      }
      if (weight >= 2 && Math.hypot(dx, dy) > 1e-4) {
        // A strengthening cell moves toward higher risk; a weakening one away.
        const sign = trend > 0 ? 1 : -1;
        motionDeg = (((Math.atan2(dx * sign, dy * sign) * 180) / Math.PI) + 360) % 360;
        motionKn = Math.min(28, Math.abs(trend) * 900);
      }
    }

    cells.push({
      portCode: station.portCode,
      name: station.name,
      risk,
      lon: station.lon,
      lat: station.lat,
      motionDeg,
      motionKn,
      hasTrack: false,
    });

    const colour = risk >= 0.25 ? "#d05a4c" : risk >= 0.08 ? "#d3a02f" : "#c9853f";
    const envelopeKm = 70 + Math.min(340, risk * 1400);

    features.push({
      type: "Feature",
      properties: {
        portCode: station.portCode, name: station.name, risk,
        ring: "envelope", color: colour,
        opacity: 0.09 + Math.min(0.16, risk * 0.65),
      },
      geometry: {
        type: "Polygon",
        coordinates: [circleRing([station.lon, station.lat], envelopeKm)],
      },
    });
    features.push({
      type: "Feature",
      properties: {
        portCode: station.portCode, name: station.name, risk,
        ring: "core", color: colour,
        opacity: 0.2 + Math.min(0.26, risk * 0.95),
      },
      geometry: {
        type: "Polygon",
        coordinates: [circleRing([station.lon, station.lat], envelopeKm * 0.4)],
      },
    });

    if (motionDeg != null && motionKn != null && motionKn > 1) {
      // Six hours of travel at the inferred speed. Shown as a vector, never as
      // a forecast track -- the data does not support one.
      const km = motionKn * 1.852 * 6;
      const rad = (motionDeg * Math.PI) / 180;
      const dLat = (km / 111) * Math.cos(rad);
      const dLon = (km / (111 * Math.cos((station.lat * Math.PI) / 180))) * Math.sin(rad);
      features.push({
        type: "Feature",
        properties: {
          portCode: station.portCode, name: station.name, risk,
          ring: "motion", color: colour, opacity: 0.85,
        },
        geometry: {
          type: "LineString",
          coordinates: [
            [station.lon, station.lat],
            [station.lon + dLon, station.lat + dLat],
          ],
        },
      });
    }
  }

  cells.sort((a, b) => b.risk - a.risk);
  return { data: { type: "FeatureCollection", features }, cells };
}

/** Formatted band edges for the legend. */
export function legendStops(key: WeatherFieldKey): Array<{ color: string; label: string }> {
  const spec = WEATHER_FIELDS[key];
  return spec.bands.map((band, index) => ({
    color: spec.colors[index] ?? spec.colors[spec.colors.length - 1],
    label: index === spec.bands.length - 1 ? `${band}+` : String(band),
  }));
}

/** What the composite is showing, for the legend. */
export const COMPOSITE_LAYERS = [
  { key: "precipitation", label: "Rain", unit: "mm/24h" },
  { key: "wind", label: "Wind", unit: "kn" },
  { key: "storm", label: "Severe", unit: "index" },
] as const;
