/**
 * Geometry for the sea state and for observed AIS.
 *
 * Both are things the server observed or forecast, never things this client
 * derived, and the two builders here do nothing but re-shape a payload into
 * features. If a value is null on the wire it is absent on the feature, and
 * the style draws its absence (a faint disc, no stroke) rather than a zero.
 */

import type { MarineCell, ObservedTrack } from "@/types/portwatch-os";

import { EMPTY } from "./basemap";

const NM_PER_DEG_LAT = 60;

/** A short segment from a point along a bearing, sized in nautical miles. */
function stroke(
  lon: number,
  lat: number,
  bearingDeg: number,
  lengthNm: number,
): GeoJSON.Position[] {
  const rad = (bearingDeg * Math.PI) / 180;
  const dLat = (Math.cos(rad) * lengthNm) / NM_PER_DEG_LAT;
  const dLon =
    (Math.sin(rad) * lengthNm) /
    (NM_PER_DEG_LAT * Math.max(0.2, Math.cos((lat * Math.PI) / 180)));
  return [
    [lon, lat],
    [lon + dLon, lat + dLat],
  ];
}

/**
 * Sea-state features: one cell disc per sample point, a swell stroke pointing
 * *from* where the swell comes (the mariner's convention), and a current
 * stroke pointing *to* where the water goes (the oceanographer's), each
 * labelled so the legend can say which is which.
 */
export function seaStateFeatures(
  cells: MarineCell[],
  withinHorizon = true,
): GeoJSON.FeatureCollection {
  if (!cells.length) return EMPTY;
  const features: GeoJSON.Feature[] = [];
  for (const cell of cells) {
    features.push({
      type: "Feature",
      properties: {
        kind: "cell",
        id: cell.label,
        label: cell.label,
        // The clock is outside the forecast's window: what is drawn is the
        // nearest hour the service has, and the style fades it to say so.
        outsideHorizon: !withinHorizon,
        waveHeightM: cell.waveHeightM ?? undefined,
        wavePeriodS: cell.wavePeriodS ?? undefined,
        swellHeightM: cell.swellHeightM ?? undefined,
        sstC: cell.sstC ?? undefined,
        currentSpeedKn: cell.currentSpeedKn ?? undefined,
        validAt: cell.validAt,
        productId: cell.productId,
      },
      geometry: { type: "Point", coordinates: [cell.lon, cell.lat] },
    });
    if (
      cell.swellDirectionDeg != null &&
      cell.swellHeightM != null &&
      cell.swellHeightM > 0.05
    ) {
      // Swell "from" 270 arrives travelling east; the stroke is drawn back
      // towards its origin so it reads as a fetch, not a heading.
      features.push({
        type: "Feature",
        properties: {
          kind: "swell",
          id: `${cell.label}-swell`,
          swellHeightM: cell.swellHeightM,
        },
        geometry: {
          type: "LineString",
          coordinates: stroke(
            cell.lon,
            cell.lat,
            cell.swellDirectionDeg,
            18 + cell.swellHeightM * 14,
          ),
        },
      });
    }
    if (
      cell.currentDirectionDeg != null &&
      cell.currentSpeedKn != null &&
      cell.currentSpeedKn > 0.05
    ) {
      features.push({
        type: "Feature",
        properties: {
          kind: "current",
          id: `${cell.label}-current`,
          currentSpeedKn: cell.currentSpeedKn,
        },
        geometry: {
          type: "LineString",
          coordinates: stroke(
            cell.lon,
            cell.lat,
            cell.currentDirectionDeg,
            12 + cell.currentSpeedKn * 20,
          ),
        },
      });
    }
  }
  return { type: "FeatureCollection", features };
}

/** Observed transponders: a mark at the latest position and the track behind it. */
export function observedFeatures(
  tracks: ObservedTrack[],
  selectedMmsi: string | null,
): GeoJSON.FeatureCollection {
  if (!tracks.length) return EMPTY;
  const features: GeoJSON.Feature[] = [];
  for (const track of tracks) {
    const latest = track.latest;
    if (!latest) continue;
    features.push({
      type: "Feature",
      properties: {
        kind: "mark",
        id: track.mmsi,
        mmsi: track.mmsi,
        name: track.name ?? undefined,
        imo: track.imo ?? undefined,
        freshness: track.freshness,
        lastSeen: track.lastSeen,
        sog: latest.sogKnots ?? undefined,
        cog: latest.cogDegrees ?? undefined,
        selected: track.mmsi === selectedMmsi,
        source: track.source,
      },
      geometry: { type: "Point", coordinates: [latest.lon, latest.lat] },
    });
    if (track.history.length >= 2) {
      features.push({
        type: "Feature",
        properties: {
          kind: "track",
          id: `${track.mmsi}-track`,
          mmsi: track.mmsi,
          freshness: track.freshness,
        },
        geometry: {
          type: "LineString",
          coordinates: track.history.map((p) => [p.lon, p.lat]),
        },
      });
    }
  }
  return { type: "FeatureCollection", features };
}
