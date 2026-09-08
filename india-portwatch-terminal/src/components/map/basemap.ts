/**
 * The chart the operations map draws on.
 *
 * No tile service. The coastline and national boundaries are two clipped
 * Natural Earth GeoJSON files that ship in the repository (see
 * `scripts/build_basemap.py`), so the map renders identically on a closed
 * network, in CI, and in a room with no internet — which is the only kind of
 * basemap an operations console can rely on.
 *
 * The palette is a nautical chart, not a satellite photograph: dark water,
 * slightly lighter land, a lit coastline, and a graticule for bearing.
 */

import type { StyleSpecification } from "maplibre-gl";

import borders from "@/assets/geo/region-borders.json";
import land from "@/assets/geo/region-land.json";

/** Indian Ocean theatre: Suez and Hormuz on one edge, Malacca on the other. */
export const REGION_BOUNDS: [[number, number], [number, number]] = [
  [24, -14],
  [114, 44],
];

export const INDIA_VIEW = { center: [79.5, 15.5] as [number, number], zoom: 4.05 };

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

/** Runtime sources the operational layers write into. */
export const EMPTY: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

export function buildStyle(): StyleSpecification {
  return {
    version: 8,
    // No `glyphs` and no symbol layers: labels are React overlays, which keeps
    // the product's typography on the map and removes a font-atlas fetch.
    sources: {
      graticule: { type: "geojson", data: graticule() as never },
      land: { type: "geojson", data: land as never },
      borders: { type: "geojson", data: borders as never },
      wxfield: { type: "geojson", data: EMPTY as never },
      wxstations: { type: "geojson", data: EMPTY as never },
      storms: { type: "geojson", data: EMPTY as never },
      lanes: { type: "geojson", data: EMPTY as never },
      chokepoints: { type: "geojson", data: EMPTY as never },
      zones: { type: "geojson", data: EMPTY as never },
      ports: { type: "geojson", data: EMPTY as never },
      vessels: { type: "geojson", data: EMPTY as never },
      events: { type: "geojson", data: EMPTY as never },
    },
    layers: [
      {
        id: "sea",
        type: "background",
        paint: { "background-color": "#071822" },
      },
      {
        id: "graticule-line",
        type: "line",
        source: "graticule",
        paint: {
          "line-color": "#14252f",
          "line-width": ["case", ["==", ["get", "kind"], "major"], 0.9, 0.5],
        },
      },

      /* -------------------------------------------------- weather field -- */
      {
        id: "wx-cells",
        type: "fill",
        source: "wxfield",
        // The field is a 0.25 degree interpolation of 13 stations. Drawn past
        // this zoom each cell is wider than the harbour under it, which would
        // imply a resolution the observations do not have.
        maxzoom: 7,
        layout: { visibility: "none" },
        paint: {
          "fill-color": ["get", "color"],
          "fill-opacity": ["get", "opacity"],
          // Adjacent translucent cells would show antialiased seams and read
          // as a mesh rather than a field.
          "fill-antialias": false,
        },
      },
      {
        id: "wx-cell-edge",
        type: "line",
        source: "wxfield",
        maxzoom: 7,
        layout: { visibility: "none" },
        filter: ["==", ["get", "band"], 4],
        paint: { "line-color": ["get", "color"], "line-width": 0.6, "line-opacity": 0.55 },
      },

      /* ---------------------------------------------------------- land -- */
      {
        id: "land-fill",
        type: "fill",
        source: "land",
        paint: { "fill-color": "#111d26" },
      },
      {
        id: "land-coast",
        type: "line",
        source: "land",
        paint: {
          "line-color": "#37627a",
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.7, 8, 1.6],
        },
      },
      {
        id: "land-borders",
        type: "line",
        source: "borders",
        paint: { "line-color": "#23394a", "line-width": 0.7, "line-dasharray": [3, 2] },
      },

      /* ------------------------------------------------- storm envelope -- */
      {
        id: "storm-area",
        type: "fill",
        source: "storms",
        layout: { visibility: "none" },
        paint: { "fill-color": "#d05a4c", "fill-opacity": 0.1 },
      },
      {
        id: "storm-edge",
        type: "line",
        source: "storms",
        layout: { visibility: "none" },
        paint: { "line-color": "#d05a4c", "line-width": 1, "line-dasharray": [2, 2], "line-opacity": 0.75 },
      },

      /* ----------------------------------------- schematic port geometry -- */
      {
        id: "zone-fill",
        type: "fill",
        source: "zones",
        layout: { visibility: "none" },
        paint: { "fill-color": ["get", "color"], "fill-opacity": ["get", "opacity"] },
      },
      {
        id: "zone-edge",
        type: "line",
        source: "zones",
        layout: { visibility: "none" },
        paint: {
          "line-color": ["get", "color"],
          "line-width": 1,
          "line-opacity": 0.75,
          "line-dasharray": ["case", ["==", ["get", "dashed"], true], ["literal", [3, 3]], ["literal", [1, 0]]],
        },
      },

      /* ---------------------------------------------------------- lanes -- */
      {
        id: "lane-line",
        type: "line",
        source: "lanes",
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, ["get", "width"], 8, ["*", ["get", "width"], 2]],
          "line-opacity": ["get", "opacity"],
          "line-dasharray": ["case", ["==", ["get", "dashed"], true], ["literal", [4, 3]], ["literal", [1, 0]]],
        },
      },

      /* ---------------------------------------------------- chokepoints -- */
      {
        id: "chokepoint-mark",
        type: "circle",
        source: "chokepoints",
        paint: {
          "circle-radius": 4.5,
          "circle-color": "#071822",
          "circle-stroke-color": ["get", "color"],
          "circle-stroke-width": 1.4,
        },
      },

      /* --------------------------------------------------------- events -- */
      {
        id: "event-mark",
        type: "circle",
        source: "events",
        layout: { visibility: "none" },
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["get", "severity"], 0, 3, 1, 7],
          "circle-color": ["get", "color"],
          "circle-opacity": 0.22,
          "circle-stroke-color": ["get", "color"],
          "circle-stroke-width": 1,
        },
      },

      /* ------------------------------------------------ weather stations -- */
      {
        id: "wx-station",
        type: "circle",
        source: "wxstations",
        layout: { visibility: "none" },
        paint: {
          "circle-radius": 3,
          "circle-color": ["get", "color"],
          "circle-stroke-color": "#04121b",
          "circle-stroke-width": 1,
        },
      },

      /* ---------------------------------------------------------- ports -- */
      {
        id: "port-halo",
        type: "circle",
        source: "ports",
        filter: ["==", ["get", "emphasis"], true],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 11, 8, 20],
          "circle-color": ["get", "color"],
          "circle-opacity": 0.1,
          "circle-stroke-color": ["get", "color"],
          "circle-stroke-width": 1,
          "circle-stroke-opacity": 0.5,
        },
      },
      {
        id: "port-mark",
        type: "circle",
        source: "ports",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, ["get", "radius"], 9, ["*", ["get", "radius"], 2.2]],
          "circle-color": "#08161e",
          "circle-stroke-color": ["get", "color"],
          "circle-stroke-width": ["case", ["==", ["get", "selected"], true], 2.4, 1.6],
        },
      },
      {
        id: "port-core",
        type: "circle",
        source: "ports",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 1.6, 9, 3.4],
          "circle-color": ["get", "color"],
        },
      },

      /* -------------------------------------------------------- vessels -- */
      {
        id: "vessel-mark",
        type: "circle",
        source: "vessels",
        layout: { visibility: "none" },
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 2.6, 9, 5],
          "circle-color": ["get", "color"],
          "circle-opacity": 0.9,
          "circle-stroke-color": "#04121b",
          "circle-stroke-width": 0.8,
        },
      },
    ],
  } as StyleSpecification;
}

/** Layer ids grouped by the toggle that owns them. */
export const LAYER_GROUPS = {
  ports: ["port-halo", "port-mark", "port-core"],
  vessels: ["vessel-mark"],
  weather: ["wx-cells", "wx-cell-edge"],
  stations: ["wx-station"],
  storms: ["storm-area", "storm-edge"],
  routes: ["lane-line"],
  chokepoints: ["chokepoint-mark"],
  events: ["event-mark"],
  zones: ["zone-fill", "zone-edge"],
  graticule: ["graticule-line"],
} as const;

export type LayerKey = keyof typeof LAYER_GROUPS;
