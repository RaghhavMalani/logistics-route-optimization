/**
 * Turning a fleet of fixes into the sources MapLibre draws.
 *
 * Called on every render tick, so it allocates plain objects and nothing else:
 * no geometry libraries, no per-vessel React element, no map of maps. Five
 * hundred vessels resolve in well under a millisecond, which is what keeps the
 * traffic smooth while the rest of the application re-renders at two hertz.
 *
 * De-cluttering is deliberately shy. A traffic display that collapses the whole
 * Bay of Bengal into six bubbles is not a traffic display; ships only merge
 * where their marks would physically overlap, which in practice means the
 * twenty at anchor off one port, and those become a single count the controller
 * can click.
 */

import type { NavStatus, VesselFix } from "@/lib/maritime/traffic-types";
import { VESSEL_CLASSES } from "@/lib/maritime/traffic-types";
import { destination } from "@/lib/maritime/geo";
import { COLORS } from "@/components/miniature/palette";
import { vesselIconId } from "./vessel-icons";

const STILL: NavStatus[] = ["anchored", "waiting", "moored"];

export function isStill(status: NavStatus): boolean {
  return STILL.includes(status);
}

export function vesselColor(fix: VesselFix): string {
  return VESSEL_CLASSES[fix.vesselClass].color;
}

export interface ClusterMark {
  id: string;
  lon: number;
  lat: number;
  count: number;
  members: string[];
}

export interface VesselLabel {
  id: string;
  lon: number;
  lat: number;
  text: string;
  sub?: string;
  emphasis?: boolean;
}

export interface TrafficFeatures {
  vessels: GeoJSON.FeatureCollection;
  clusters: GeoJSON.FeatureCollection;
  vectors: GeoJSON.FeatureCollection;
  rings: GeoJSON.FeatureCollection;
  clusterMarks: ClusterMark[];
  labels: VesselLabel[];
  /** How many vessels were drawn individually. */
  drawn: number;
  /** How many were merged into a count. */
  merged: number;
}

export interface TrafficRenderOptions {
  zoom: number;
  colorByType?: boolean;
  selectedId?: string | null;
  hoveredId?: string | null;
  /** Drawn at full weight; everything else is dimmed rather than hidden. */
  focus?: Set<string> | null;
  /** Always labelled and never merged into a cluster. */
  pinned?: Set<string>;
  /** Draw velocity leaders for every moving vessel, not just the selection. */
  vectors?: boolean;
  /** Show a name against every vessel, whatever the zoom. */
  labels?: boolean;
  maxLabels?: number;
}

const SILHOUETTE_BUDGET = 128;

/** Submit only fixes near the viewport. Followed, hovered and pinned hulls
 * retain their priority even when ordinary silhouettes exhaust the budget. */
export function viewportTraffic(
  fixes: VesselFix[],
  view: {
    zoom: number;
    west: number;
    south: number;
    east: number;
    north: number;
    lon: number;
    lat: number;
  },
  { selectedId, hoveredId, pinned, focus }: TrafficRenderOptions,
): VesselFix[] {
  const { zoom, west, south, east, north, lon, lat } = view;
  // The guard band retains moving glyphs and their leaders just offscreen.
  const xPad = (east - west) * 0.13;
  const yPad = (north - south) * 0.13;
  const priority: VesselFix[] = [];
  const ordinary: VesselFix[] = [];
  for (const fix of fixes) {
    if (
      fix.owned ||
      fix.id === selectedId ||
      fix.id === hoveredId ||
      pinned?.has(fix.id)
    ) {
      priority.push(fix);
    } else if (
      fix.lon >= west - xPad &&
      fix.lon <= east + xPad &&
      fix.lat >= south - yPad &&
      fix.lat <= north + yPad
    ) {
      ordinary.push(fix);
    }
  }
  const budget = Math.max(0, SILHOUETTE_BUDGET - priority.length);
  if (zoom >= 7 && ordinary.length > budget) {
    const lonScale = Math.cos((lat * Math.PI) / 180);
    const distance = (fix: VesselFix) =>
      ((fix.lon - lon) * lonScale) ** 2 + (fix.lat - lat) ** 2;
    ordinary.sort(
      (a, b) =>
        Number(focus?.has(b.id) ?? false) - Number(focus?.has(a.id) ?? false) ||
        distance(a) - distance(b),
    );
    ordinary.length = budget;
  }
  return priority.concat(ordinary);
}

const EMPTY: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

/** Degrees covered by one screen pixel at this zoom, at the equator. */
function degreesPerPixel(zoom: number): number {
  return 360 / (512 * 2 ** zoom);
}

export function buildTrafficFeatures(
  fixes: VesselFix[],
  options: TrafficRenderOptions,
): TrafficFeatures {
  const {
    zoom,
    selectedId = null,
    hoveredId = null,
    focus = null,
    pinned,
    vectors = false,
    labels = false,
    maxLabels = 26,
  } = options;

  if (!fixes.length) {
    return {
      vessels: EMPTY,
      clusters: EMPTY,
      vectors: EMPTY,
      rings: EMPTY,
      clusterMarks: [],
      labels: [],
      drawn: 0,
      merged: 0,
    };
  }

  /* ------------------------------------------------------------ merging -- */
  const cellDeg = degreesPerPixel(zoom) * 11;
  const buckets = new Map<string, VesselFix[]>();
  const always: VesselFix[] = [];

  for (const fix of fixes) {
    if (
      fix.owned ||
      fix.id === selectedId ||
      fix.id === hoveredId ||
      pinned?.has(fix.id) === true ||
      !isStill(fix.status)
    ) {
      // Only stopped vessels merge. A ship under way is the thing the operator
      // is watching, and hiding it inside a bubble defeats the display.
      always.push(fix);
      continue;
    }
    const key = `${Math.round(fix.lon / cellDeg)}:${Math.round(fix.lat / cellDeg)}`;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(fix);
    else buckets.set(key, [fix]);
  }

  const individual: VesselFix[] = [...always];
  const clusterMarks: ClusterMark[] = [];

  for (const [key, bucket] of buckets) {
    if (bucket.length < 4) {
      individual.push(...bucket);
      continue;
    }
    let lon = 0;
    let lat = 0;
    for (const fix of bucket) {
      lon += fix.lon;
      lat += fix.lat;
    }
    clusterMarks.push({
      id: `cluster:${key}`,
      lon: lon / bucket.length,
      lat: lat / bucket.length,
      count: bucket.length,
      members: bucket.map((fix) => fix.id),
    });
  }

  /* ----------------------------------------------------------- features -- */
  const vesselFeatures: GeoJSON.Feature[] = [];
  const vectorFeatures: GeoJSON.Feature[] = [];
  const ringFeatures: GeoJSON.Feature[] = [];
  const labelList: VesselLabel[] = [];

  const leaderMinutes = zoom >= 8 ? 24 : zoom >= 6 ? 45 : 90;
  const drawVectors = vectors && zoom >= 5.2;

  for (const fix of individual) {
    const selected = fix.id === selectedId;
    const followed = selected || fix.owned;
    const dimmed = focus !== null && !focus.has(fix.id) && !followed;
    const ink = followed
      ? "follow"
      : options.colorByType
        ? fix.vesselClass
        : "neutral";
    const stopped = isStill(fix.status) || fix.sogKn <= 0.5;

    vesselFeatures.push({
      type: "Feature",
      id: undefined,
      properties: {
        id: fix.id,
        name: fix.name,
        icon: vesselIconId(fix.vesselClass, ink, false, stopped),
        detailedIcon: vesselIconId(fix.vesselClass, ink, true, stopped),
        cog: fix.cog,
        status: fix.status,
        class: fix.vesselClass,
        scale: fix.owned ? 1.25 : selected || fix.id === hoveredId ? 1.15 : 1,
        opacity: followed ? 1 : dimmed ? 0.46 : 0.84,
        emphasis: selected ? 2 : followed ? 1 : 0,
      },
      geometry: { type: "Point", coordinates: [fix.lon, fix.lat] },
    });

    if (followed) {
      ringFeatures.push({
        type: "Feature",
        properties: {
          id: fix.id,
          radius: selected ? 17 : 14,
          opacity: selected ? 0.46 : 0.31,
        },
        geometry: { type: "Point", coordinates: [fix.lon, fix.lat] },
      });
    }

    if (!stopped && drawVectors) {
      const km = (fix.sogKn * 1.852 * leaderMinutes) / 60;
      const tip = destination([fix.lon, fix.lat], fix.cog, km);
      vectorFeatures.push({
        type: "Feature",
        properties: {
          id: fix.id,
          color: followed
            ? COLORS.signalInk
            : options.colorByType
              ? vesselColor(fix)
              : COLORS.modelInk,
          opacity: dimmed ? 0.16 : followed ? 0.76 : 0.42,
        },
        geometry: {
          type: "LineString",
          coordinates: [[fix.lon, fix.lat], tip],
        },
      });
    }
  }

  /* ------------------------------------------------------------- labels -- */
  const wantsLabels = labels || zoom >= 6.4;
  const candidates = individual
    .filter(
      (fix) =>
        fix.owned ||
        fix.id === selectedId ||
        fix.id === hoveredId ||
        pinned?.has(fix.id) === true ||
        wantsLabels,
    )
    .sort((a, b) => {
      const rank = (fix: VesselFix) =>
        (fix.owned ? 3 : 0) +
        (fix.id === selectedId ? 3 : 0) +
        (fix.id === hoveredId ? 2 : 0) +
        (pinned?.has(fix.id) ? 1.5 : 0) +
        fix.lengthM / 1000;
      return rank(b) - rank(a);
    });

  for (const fix of candidates.slice(0, maxLabels)) {
    labelList.push({
      id: fix.id,
      lon: fix.lon,
      lat: fix.lat,
      text: fix.name,
      sub: fix.sogKn > 0.5 ? `${fix.sogKn.toFixed(1)}kn` : undefined,
      emphasis: fix.owned || fix.id === selectedId,
    });
  }

  return {
    vessels: { type: "FeatureCollection", features: vesselFeatures },
    clusters: {
      type: "FeatureCollection",
      features: clusterMarks.map((mark) => ({
        type: "Feature",
        properties: { id: mark.id, count: mark.count },
        geometry: { type: "Point", coordinates: [mark.lon, mark.lat] },
      })),
    },
    vectors: { type: "FeatureCollection", features: vectorFeatures },
    rings: { type: "FeatureCollection", features: ringFeatures },
    clusterMarks,
    labels: labelList,
    drawn: individual.length,
    merged: fixes.length - individual.length,
  };
}

/**
 * The predicted fleet, drawn faintly where each vessel will be.
 *
 * Only shown while the timeline is ahead of the traffic clock: a ghost on top
 * of its own present position is noise, and a ghost twelve hours out is the
 * whole argument for having a timeline.
 */
export function buildGhostFeatures(
  fixes: VesselFix[],
  focus?: Set<string> | null,
  colorByType = false,
) {
  const features: GeoJSON.Feature[] = [];
  for (const fix of fixes) {
    if (focus && !focus.has(fix.id) && !fix.owned) continue;
    if (isStill(fix.status) && !fix.owned) continue;
    const ink = fix.owned
      ? "follow"
      : colorByType
        ? fix.vesselClass
        : "neutral";
    const stopped = isStill(fix.status) || fix.sogKn <= 0.5;
    features.push({
      type: "Feature",
      properties: {
        id: fix.id,
        icon: vesselIconId(fix.vesselClass, ink, false, stopped),
        detailedIcon: vesselIconId(fix.vesselClass, ink, true, stopped),
        cog: fix.cog,
      },
      geometry: { type: "Point", coordinates: [fix.lon, fix.lat] },
    });
  }
  return { type: "FeatureCollection", features } as GeoJSON.FeatureCollection;
}
