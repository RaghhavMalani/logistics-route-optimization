/**
 * The chart the maritime picture is drawn on.
 *
 * No tile service. The coastline and national boundaries are two clipped
 * Natural Earth GeoJSON files that ship in the repository (see
 * `scripts/build_basemap.py`), so the map renders identically on a closed
 * network, in CI, and in a room with no internet -- which is the only kind of
 * basemap an operations console can rely on.
 *
 * The palette is a working nautical chart. Ocean is the dominant surface and
 * carries a shelf gradient built from blurred coast strokes, because a flat
 * blue rectangle reads as a placeholder and a real chart tells you where the
 * water gets deep. Land is deliberately quiet: it is context for the traffic,
 * never the subject. Shipping corridors sit just above the sea so the network
 * is legible even where no vessel happens to be.
 *
 * There are no symbol layers for text and no `glyphs` URL. Labels are React
 * overlays positioned from the map's own projection, which keeps the product's
 * typography on the chart and removes a font-atlas fetch.
 */

import type { StyleSpecification } from "maplibre-gl";

import borders from "@/assets/geo/region-borders.json";
import land from "@/assets/geo/region-land.json";
import { corridorFeatures } from "@/lib/maritime/searoutes";

/** Indian Ocean theatre: Suez and Hormuz on one edge, Malacca on the other. */
export const REGION_BOUNDS: [[number, number], [number, number]] = [
  [24, -14],
  [114, 44],
];

export const INDIA_VIEW = { center: [79.5, 14.5] as [number, number], zoom: 4.15 };

/** A transparent pixel, so the weather raster source exists before it has data. */
export const BLANK_IMAGE =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";

function graticule(step = 10): GeoJSON.FeatureCollection {
  const lines: GeoJSON.Feature[] = [];
  for (let lon = 20; lon <= 120; lon += step) {
    lines.push({
      type: "Feature",
      properties: { kind: lon % 30 === 0 ? "major" : "minor" },
      geometry: { type: "LineString", coordinates: [[lon, -20], [lon, 50]] },
    });
  }
  for (let lat = -20; lat <= 50; lat += step) {
    lines.push({
      type: "Feature",
      properties: { kind: lat === 0 ? "major" : "minor" },
      geometry: { type: "LineString", coordinates: [[20, lat], [120, lat]] },
    });
  }
  return { type: "FeatureCollection", features: lines };
}

export const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

/** Sources the operational layers write into at runtime. */
const RUNTIME_SOURCES = [
  "storms",
  "zones",
  "ports",
  "routes",
  "tracks",
  "vectors",
  "ghosts",
  "vessels",
  "clusters",
  "chokepoints",
  "events",
  "rings",
] as const;

export type RuntimeSource = (typeof RUNTIME_SOURCES)[number];

export function buildStyle(): StyleSpecification {
  const sources: StyleSpecification["sources"] = {
    graticule: { type: "geojson", data: graticule() as never },
    land: { type: "geojson", data: land as never },
    borders: { type: "geojson", data: borders as never },
    corridors: { type: "geojson", data: corridorFeatures() as never },
    wxraster: {
      type: "image",
      url: BLANK_IMAGE,
      coordinates: [
        [60, 30],
        [61, 30],
        [61, 29],
        [60, 29],
      ],
    },
  };
  for (const key of RUNTIME_SOURCES) {
    sources[key] = { type: "geojson", data: EMPTY as never };
  }

  return {
    version: 8,
    sources,
    layers: [
      { id: "sea", type: "background", paint: { "background-color": "#061520" } },

      /* --------------------------------------------------- shelf gradient -- */
      /* Three blurred coast strokes stand in for bathymetry. The shelf is the
         one piece of ocean structure a mariner reads without thinking, and its
         absence is most of why a flat fill looks unfinished. */
      {
        id: "shelf-deep",
        type: "line",
        source: "land",
        paint: {
          "line-color": "#0a2433",
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 46, 8, 150],
          "line-blur": ["interpolate", ["linear"], ["zoom"], 3, 40, 8, 130],
          // The shelf is basin-scale orientation. Inside a harbour view the
          // whole frame is shelf, and holding it at full strength lifts the
          // coastal water to the same value as the land beside it.
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 3, 0.6, 7, 0.45, 9, 0.15],
        },
      },
      {
        id: "shelf-mid",
        type: "line",
        source: "land",
        paint: {
          "line-color": "#0d2b3c",
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 18, 8, 60],
          "line-blur": ["interpolate", ["linear"], ["zoom"], 3, 16, 8, 52],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 3, 0.7, 7, 0.5, 9, 0.16],
        },
      },
      {
        id: "shelf-near",
        type: "line",
        source: "land",
        paint: {
          "line-color": "#103446",
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 6, 8, 22],
          "line-blur": ["interpolate", ["linear"], ["zoom"], 3, 6, 8, 20],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 3, 0.75, 7, 0.55, 9, 0.18],
        },
      },

      /* ---------------------------------------------------------- land -- */
      { id: "land-fill", type: "fill", source: "land", paint: { "fill-color": "#182634" } },

      /* -------------------------------------------------- weather raster -- */
      /* Above the land fill and below the coastline, the way a radar composite
         sits on a chart: the weather is the sheet, the coast stays readable. */
      {
        id: "wx-field",
        type: "raster",
        source: "wxraster",
        layout: { visibility: "none" },
        paint: {
          // The field is interpolated from thirteen coastal stations, so it
          // carries no detail a harbour view could use. It stays strong at
          // basin zoom, where it is the environment, and fades as the chart
          // closes in, where it would otherwise flood the approach in colour
          // and imply a resolution the observations do not have.
          "raster-opacity": [
            "interpolate", ["linear"], ["zoom"],
            3, 0.85,
            6, 0.58,
            7.5, 0.2,
            9, 0.1,
          ],
          "raster-fade-duration": 0,
          "raster-resampling": "linear",
        },
      },

      /* ------------------------------------------------- storm envelopes -- */
      {
        id: "storm-area",
        type: "fill",
        source: "storms",
        layout: { visibility: "none" },
        paint: { "fill-color": ["get", "color"], "fill-opacity": ["get", "opacity"] },
      },
      {
        id: "storm-edge",
        type: "line",
        source: "storms",
        layout: { visibility: "none" },
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["case", ["==", ["get", "ring"], "core"], 1.6, 1],
          "line-dasharray": [2, 2],
          "line-opacity": 0.8,
        },
      },

      /* ---------------------------------------------------- graticule -- */
      {
        id: "graticule-line",
        type: "line",
        source: "graticule",
        paint: {
          "line-color": "#10222d",
          "line-width": ["case", ["==", ["get", "kind"], "major"], 0.8, 0.45],
        },
      },

      /* -------------------------------------------------- sea corridors -- */
      {
        id: "corridor-line",
        type: "line",
        source: "corridors",
        paint: {
          "line-color": "#1c4257",
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 1.4, 9, 4],
          "line-opacity": 0.55,
        },
      },

      /* ------------------------------------------------------ coastline -- */
      {
        id: "land-coast",
        type: "line",
        source: "land",
        paint: {
          "line-color": "#5b93b0",
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 1, 8, 2.2],
        },
      },
      {
        id: "land-borders",
        type: "line",
        source: "borders",
        paint: { "line-color": "#233d4f", "line-width": 0.7, "line-dasharray": [3, 2] },
      },

      /* ------------------------------------------------ port-local zones -- */
      {
        id: "zone-fill",
        type: "fill",
        source: "zones",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": ["get", "color"], "fill-opacity": ["get", "opacity"] },
      },
      {
        id: "zone-edge",
        type: "line",
        source: "zones",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: {
          "line-color": ["get", "color"],
          "line-width": 1,
          "line-opacity": 0.7,
          "line-dasharray": [3, 3],
        },
      },
      {
        id: "zone-channel",
        type: "line",
        source: "zones",
        filter: ["==", ["geometry-type"], "LineString"],
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["interpolate", ["linear"], ["zoom"], 6, 1.2, 12, 3],
          "line-opacity": 0.8,
          "line-dasharray": [4, 3],
        },
      },

      /* ---------------------------------------------------------- routes -- */
      /* A passage is drawn in two weights: water already run, and water still
         to run. The difference is what turns a line into a voyage. */
      {
        id: "route-behind",
        type: "line",
        source: "routes",
        filter: ["==", ["get", "part"], "behind"],
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 1, 9, 2],
          "line-opacity": 0.3,
          "line-dasharray": [2, 2],
        },
      },
      {
        id: "route-alternative",
        type: "line",
        source: "routes",
        filter: ["==", ["get", "part"], "alternative"],
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 1.1, 9, 2.4],
          "line-opacity": 0.62,
          "line-dasharray": [4, 3],
        },
      },
      {
        id: "route-exposure",
        type: "line",
        source: "routes",
        filter: ["==", ["get", "part"], "exposure"],
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["get", "width"],
          "line-opacity": ["get", "opacity"],
          "line-dasharray": [4, 3],
        },
      },
      {
        id: "route-ahead",
        type: "line",
        source: "routes",
        filter: ["==", ["get", "part"], "ahead"],
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 1.8, 9, 3.6],
          "line-opacity": 0.9,
        },
      },

      /* ---------------------------------------------------------- tracks -- */
      {
        id: "track-line",
        type: "line",
        source: "tracks",
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.8, 9, 1.6],
          "line-opacity": 0.5,
        },
      },

      /* ------------------------------------------------ velocity leaders -- */
      {
        id: "vector-line",
        type: "line",
        source: "vectors",
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["interpolate", ["linear"], ["zoom"], 4, 0.6, 10, 1.4],
          "line-opacity": ["get", "opacity"],
        },
      },

      /* ----------------------------------------------------- chokepoints -- */
      {
        id: "chokepoint-mark",
        type: "circle",
        source: "chokepoints",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 4, 8, 6.5],
          "circle-color": "#061520",
          "circle-stroke-color": ["get", "color"],
          "circle-stroke-width": 1.4,
          "circle-opacity": 0.9,
        },
      },
      {
        id: "event-mark",
        type: "circle",
        source: "events",
        layout: { visibility: "none" },
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["get", "severity"], 0, 4, 1, 11],
          "circle-color": ["get", "color"],
          "circle-opacity": 0.16,
          "circle-stroke-color": ["get", "color"],
          "circle-stroke-width": 1,
        },
      },

      /* ----------------------------------------------------------- ports -- */
      {
        id: "port-pressure",
        type: "circle",
        source: "ports",
        paint: {
          "circle-radius": [
            "interpolate", ["linear"], ["zoom"],
            3, ["+", 6, ["*", 10, ["get", "pressure"]]],
            9, ["+", 16, ["*", 30, ["get", "pressure"]]],
          ],
          "circle-color": ["get", "color"],
          "circle-opacity": 0.1,
          "circle-stroke-color": ["get", "color"],
          "circle-stroke-width": 0.8,
          "circle-stroke-opacity": 0.32,
        },
      },
      {
        id: "port-mark",
        type: "circle",
        source: "ports",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 4.2, 9, 8],
          "circle-color": "#08161e",
          "circle-stroke-color": ["get", "color"],
          "circle-stroke-width": ["case", ["==", ["get", "selected"], true], 2.6, 1.8],
        },
      },
      {
        id: "port-core",
        type: "circle",
        source: "ports",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 1.7, 9, 3.4],
          "circle-color": ["get", "color"],
        },
      },

      /* ------------------------------------------- predicted ghost fleet -- */
      {
        id: "ghost-mark",
        type: "symbol",
        source: "ghosts",
        layout: {
          "icon-image": ["get", "icon"],
          "icon-rotate": ["get", "cog"],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
          "icon-size": ["interpolate", ["linear"], ["zoom"], 3, 0.3, 7, 0.46, 11, 0.66],
        },
        paint: { "icon-opacity": 0.32 },
      },

      /* -------------------------------------------------------- clusters -- */
      {
        id: "cluster-mark",
        type: "circle",
        source: "clusters",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["get", "count"], 2, 7, 40, 17],
          "circle-color": "#0b202c",
          "circle-opacity": 0.88,
          "circle-stroke-color": "#3f7f9e",
          "circle-stroke-width": 1,
        },
      },

      /* ---------------------------------------- selection and own-ship -- */
      {
        id: "ring-mark",
        type: "circle",
        source: "rings",
        paint: {
          "circle-radius": ["get", "radius"],
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": ["get", "color"],
          "circle-stroke-width": ["get", "width"],
          "circle-stroke-opacity": ["get", "opacity"],
        },
      },

      /* --------------------------------------------------------- vessels -- */
      {
        id: "vessel-mark",
        type: "symbol",
        source: "vessels",
        layout: {
          "icon-image": ["get", "icon"],
          "icon-rotate": ["get", "cog"],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
          "icon-size": [
            "interpolate", ["linear"], ["zoom"],
            3, ["*", 0.4, ["get", "scale"]],
            6, ["*", 0.56, ["get", "scale"]],
            9, ["*", 0.78, ["get", "scale"]],
            12, ["*", 1, ["get", "scale"]],
          ],
        },
        paint: { "icon-opacity": ["get", "opacity"] },
      },
    ],
  } as StyleSpecification;
}

/** Layer ids grouped by the toggle that owns them. */
export const LAYER_GROUPS = {
  traffic: ["vessel-mark", "cluster-mark", "ring-mark"],
  ghosts: ["ghost-mark"],
  weather: ["wx-field"],
  storms: ["storm-area", "storm-edge"],
  ports: ["port-pressure", "port-mark", "port-core"],
  corridors: ["corridor-line"],
  routes: ["route-behind", "route-exposure", "route-ahead", "route-alternative"],
  tracks: ["track-line"],
  vectors: ["vector-line"],
  chokepoints: ["chokepoint-mark"],
  events: ["event-mark"],
  zones: ["zone-fill", "zone-edge", "zone-channel"],
  graticule: ["graticule-line"],
} as const;

export type LayerKey = keyof typeof LAYER_GROUPS;

/**
 * Sea areas, drawn as React overlays.
 *
 * Named water is orientation: it tells a reader at a glance that the traffic
 * bending south of Sri Lanka is in the Gulf of Mannar and not lost.
 */
export const SEA_LABELS = [
  { id: "arabian", name: "ARABIAN SEA", lon: 64.5, lat: 17.5, minZoom: 3.2 },
  { id: "bengal", name: "BAY OF BENGAL", lon: 87.5, lat: 15.5, minZoom: 3.2 },
  { id: "laccadive", name: "LACCADIVE SEA", lon: 73.5, lat: 7.5, minZoom: 4.2 },
  { id: "andaman", name: "ANDAMAN SEA", lon: 95.5, lat: 11.5, minZoom: 3.8 },
  { id: "indian", name: "INDIAN OCEAN", lon: 76, lat: -6, minZoom: 3.2 },
  { id: "oman", name: "GULF OF OMAN", lon: 58.5, lat: 24.6, minZoom: 4.6 },
  { id: "aden", name: "GULF OF ADEN", lon: 47.5, lat: 12.4, minZoom: 4.4 },
  { id: "red", name: "RED SEA", lon: 38.5, lat: 21, minZoom: 4.2 },
  { id: "mannar", name: "GULF OF MANNAR", lon: 78.6, lat: 7.9, minZoom: 5.6 },
  { id: "palk", name: "PALK BAY", lon: 79.4, lat: 9.8, minZoom: 6.2 },
  { id: "kutch", name: "GULF OF KUTCH", lon: 69.4, lat: 22.5, minZoom: 6 },
  { id: "khambhat", name: "GULF OF KHAMBHAT", lon: 72.2, lat: 21.2, minZoom: 6 },
  { id: "malacca", name: "STRAIT OF MALACCA", lon: 99.4, lat: 4.4, minZoom: 4.8 },
] as const;
