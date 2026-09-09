/**
 * Geometry for whatever is selected.
 *
 * The passage is drawn in three weights so it reads as a voyage rather than a
 * line: water already run, water still to run, and -- where the routing artefact
 * recommends one -- the alternative call. The forward half is cut into the
 * weather-exposure segments the forecast produced, so the colour on the chart
 * and the colour in the inspector are the same computation.
 */

import { seaRoute } from "@/lib/maritime/searoutes";
import { slicePath, type Position } from "@/lib/maritime/geo";
import type { VesselFix } from "@/lib/maritime/traffic-types";
import { EXPOSURE_COLOR, type ExposureSegment } from "@/lib/maritime/weather-field";

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export interface SelectionGeometry {
  routes: GeoJSON.FeatureCollection;
  tracks: GeoJSON.FeatureCollection;
}

export function selectionGeometry(
  fix: VesselFix | null,
  exposure: ExposureSegment[],
  options: { alternativeTo?: string | null; trackKm?: number } = {},
): SelectionGeometry {
  if (!fix?.routeKey) return { routes: EMPTY, tracks: EMPTY };

  const [from, to] = fix.routeKey.split(">");
  const route = seaRoute(from, to);
  if (!route) return { routes: EMPTY, tracks: EMPTY };

  const behind = slicePath(route.path, 0, fix.travelledKm);
  const ahead = slicePath(route.path, fix.travelledKm, route.path.km);

  const features: GeoJSON.Feature[] = [];

  if (behind.length >= 2) {
    features.push({
      type: "Feature",
      properties: { part: "behind", color: "#5f8298", id: fix.id },
      geometry: { type: "LineString", coordinates: behind },
    });
  }

  if (exposure.length > 0) {
    for (const segment of exposure) {
      if (segment.coords.length < 2) continue;
      features.push({
        type: "Feature",
        properties: {
          part: "ahead",
          color: EXPOSURE_COLOR[segment.level],
          level: segment.level,
          leadHours: segment.leadHours,
          id: fix.id,
        },
        geometry: { type: "LineString", coordinates: segment.coords },
      });
    }
  } else if (ahead.length >= 2) {
    features.push({
      type: "Feature",
      properties: { part: "ahead", color: "#7cc4e8", id: fix.id },
      geometry: { type: "LineString", coordinates: ahead },
    });
  }

  if (options.alternativeTo && options.alternativeTo !== fix.destinationId) {
    const alternative = seaRoute(fix.destinationId === from ? to : from, options.alternativeTo);
    const direct = seaRoute(from, options.alternativeTo);
    const chosen = direct ?? alternative;
    if (chosen) {
      features.push({
        type: "Feature",
        properties: { part: "alternative", color: "#8a7fc4", id: `${fix.id}:alt` },
        geometry: {
          type: "LineString",
          coordinates: nearestForward(chosen.path.coords, [fix.lon, fix.lat]),
        },
      });
    }
  }

  const trackKm = options.trackKm ?? 900;
  const track = slicePath(route.path, Math.max(0, fix.travelledKm - trackKm), fix.travelledKm);

  return {
    routes: { type: "FeatureCollection", features },
    tracks:
      track.length >= 2
        ? {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: { color: "#7f9db0", id: fix.id },
                geometry: { type: "LineString", coordinates: track },
              },
            ],
          }
        : EMPTY,
  };
}

/**
 * The part of an alternative passage that lies ahead of the vessel.
 *
 * An alternative leg starts at the origin quay, and drawing all of it would put
 * a line behind a ship that has already covered that water. Cutting it at the
 * nearest point keeps the comparison honest: two lines from here, to two places.
 */
function nearestForward(coords: Position[], point: Position): Position[] {
  let best = 0;
  let bestDistance = Infinity;
  for (let i = 0; i < coords.length; i += 1) {
    const dx = coords[i][0] - point[0];
    const dy = coords[i][1] - point[1];
    const d = dx * dx + dy * dy;
    if (d < bestDistance) {
      bestDistance = d;
      best = i;
    }
  }
  return [point, ...coords.slice(best)];
}
