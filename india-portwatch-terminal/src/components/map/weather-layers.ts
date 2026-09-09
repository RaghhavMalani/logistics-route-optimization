/**
 * Turning the weather model into things MapLibre can draw.
 *
 * The precipitation sheet is a raster image source rather than a grid of
 * polygons. The old polygon field quantised every reading into a 0.25 degree
 * square, which looked like a spreadsheet laid over the ocean; a raster the GPU
 * resamples bilinearly gives a continuous sheet at a fraction of the geometry,
 * and the cutoff still stops the field dead where no station supports it.
 */

import {
  FIELD_CUTOFF_KM,
  sampleField,
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
}

/** Degrees per raster pixel. Fine enough to look continuous once resampled. */
const RESOLUTION = 0.14;
const PAD_DEG = FIELD_CUTOFF_KM / 111;

export function buildWeatherRaster(
  frame: WeatherFrame,
  key: WeatherFieldKey,
): WeatherRaster | null {
  if (typeof document === "undefined") return null;
  const field: SampledField = sampleField(frame, key);
  if (!field.covered) return null;

  const lons = frame.stations.map((s) => s.lon);
  const lats = frame.stations.map((s) => s.lat);
  const minLon = Math.min(...lons) - PAD_DEG;
  const maxLon = Math.max(...lons) + PAD_DEG;
  const minLat = Math.min(...lats) - PAD_DEG;
  const maxLat = Math.max(...lats) + PAD_DEG;

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
    // Image rows run north to south.
    const lat = maxLat - ((y + 0.5) / height) * (maxLat - minLat);
    for (let x = 0; x < width; x += 1) {
      const lon = minLon + ((x + 0.5) / width) * (maxLon - minLon);
      const { value, nearestKm } = field.sample(lon, lat);
      const offset = (y * width + x) * 4;
      if (value == null) continue;

      // Fade the last third of the reach to nothing. Without it the field ends
      // on a hard circle, which reads as a data boundary rather than weather.
      const reach = 1 - Math.min(1, Math.max(0, (nearestKm - FIELD_CUTOFF_KM * 0.55) / (FIELD_CUTOFF_KM * 0.45)));
      const hazard = hazardOf(spec, value) * reach;
      // Below a twentieth of the first band there is no meaningful signal, and
      // painting it would wash the whole basin in colour that means nothing.
      if (hazard < 0.05) continue;

      const { rgb } = rampColor(spec, value);
      image.data[offset] = rgb[0];
      image.data[offset + 1] = rgb[1];
      image.data[offset + 2] = rgb[2];
      // Capped: the field is the environment under the traffic, and it must
      // never make a ship or a coastline harder to read.
      image.data[offset + 3] = Math.round(255 * Math.min(0.5, 0.03 + hazard * 0.62));
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
  };
}

/* ----------------------------------------------------------- storm cells -- */

export interface StormCell {
  portCode: string;
  name: string;
  risk: number;
  lon: number;
  lat: number;
}

/**
 * Storm envelopes, drawn only where a port actually carries a storm flag.
 *
 * There is no projected motion here on purpose: the artefact carries a storm
 * *risk index* per port from the GDACS flags, not a track, a centre pressure or
 * a forecast position. Drawing a cone of uncertainty would be an invention, so
 * the inspector says storm motion is unavailable instead.
 */
export function buildStormCells(frame: WeatherFrame): {
  data: GeoJSON.FeatureCollection;
  cells: StormCell[];
} {
  const features: GeoJSON.Feature[] = [];
  const cells: StormCell[] = [];

  for (const station of frame.stations) {
    const risk = station.stormRisk;
    if (risk == null || risk <= 0.001) continue;
    cells.push({
      portCode: station.portCode,
      name: station.name,
      risk,
      lon: station.lon,
      lat: station.lat,
    });

    const colour = risk >= 0.25 ? "#d05a4c" : risk >= 0.08 ? "#d3a02f" : "#c9853f";
    const envelopeKm = 70 + Math.min(340, risk * 1400);
    features.push({
      type: "Feature",
      properties: {
        portCode: station.portCode,
        name: station.name,
        risk,
        ring: "envelope",
        color: colour,
        opacity: 0.07 + Math.min(0.14, risk * 0.6),
      },
      geometry: {
        type: "Polygon",
        coordinates: [circleRing([station.lon, station.lat], envelopeKm)],
      },
    });
    features.push({
      type: "Feature",
      properties: {
        portCode: station.portCode,
        name: station.name,
        risk,
        ring: "core",
        color: colour,
        opacity: 0.16 + Math.min(0.22, risk * 0.9),
      },
      geometry: {
        type: "Polygon",
        coordinates: [circleRing([station.lon, station.lat], envelopeKm * 0.4)],
      },
    });
  }

  cells.sort((a, b) => b.risk - a.risk);
  return { data: { type: "FeatureCollection", features }, cells };
}

/** Formatted band edges for the legend. */
export function legendStops(key: WeatherFieldKey): Array<{ color: string; label: string }> {
  const spec = WEATHER_FIELDS[key];
  return spec.bands.map((band, index) => ({
    color: spec.colors[index] ?? spec.colors[spec.colors.length - 1],
    label:
      index === spec.bands.length - 1
        ? `${band}+`
        : String(band),
  }));
}
