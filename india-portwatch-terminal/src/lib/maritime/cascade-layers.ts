/**
 * Draw a computed cascade on the water.
 *
 * Every visual weight here is read from a quantity the World State Engine
 * produced. A lane is thick because the engine said the consequence reaching it
 * is large, a port ring is wide because the engine computed that much pressure,
 * and a vessel is amber rather than red because the attention engine put it in
 * ACT_SOON. Nothing on this map is styled by a rule that lives only in the
 * frontend, because a second implementation of consequence is a second
 * implementation that will drift -- and the one on the screen is the one a
 * customer would believe.
 *
 * `reveal` (0..1) is the single animation channel. The screen raises it once
 * when a cascade is opened and leaves it there. Nothing loops: a control room
 * that blinks permanently is one whose operators stop seeing the blinking.
 */

import type { CascadeAffected, CascadeSubject, WorldQuantity } from "@/types/portwatch-os";

import { CHOKEPOINT_BY_CODE } from "./chokepoints";
import { seaRoute } from "./searoutes";

/** Consequence palette. Deliberately three steps, not a continuous ramp. */
export const CASCADE_COLOR = {
  /** The event and the water it threatens. */
  source: "#e0533d",
  /** Carried consequence: lanes and exposed hulls. */
  carried: "#e08c3d",
  /** Where it lands: destination ports. */
  landing: "#d9b23c",
  /** Committed, nothing to be done. Deliberately cool, never alarm-coloured. */
  committed: "#7c8ea3",
} as const;

/** The order the reveal walks, and the share of `reveal` each stage owns. */
export const CASCADE_STAGES = ["event", "chokepoint", "lanes", "vessels", "ports"] as const;
export type CascadeStage = (typeof CASCADE_STAGES)[number];

/**
 * How far through the reveal a stage is, 0..1.
 *
 * Staged rather than simultaneous because the point of the animation is to show
 * that consequence *travelled*: event, then water, then routes, then hulls,
 * then quays. All five appearing together would be a state change, not an
 * explanation.
 */
export function stageProgress(reveal: number, stage: CascadeStage): number {
  const index = CASCADE_STAGES.indexOf(stage);
  const span = 1 / CASCADE_STAGES.length;
  const start = index * span;
  return Math.max(0, Math.min(1, (reveal - start) / span));
}

const clamp01 = (n: number) => Math.max(0, Math.min(1, n));

/** A magnitude normalised against the scale at which it is a full problem. */
function magnitude(quantity: WorldQuantity | undefined, scale: number): number {
  if (!quantity) return 0;
  return clamp01(Math.abs(quantity.value) / scale);
}

/**
 * The lanes a cascade reached, as flow lines across the water.
 *
 * Geometry comes from the existing sea-route catalogue rather than a straight
 * line between endpoints: a consequence line that crossed Arabia would discredit
 * every number attached to it.
 */
export function cascadeLaneFeatures(
  affected: CascadeAffected | undefined,
  reveal: number,
): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  if (!affected) return { type: "FeatureCollection", features };

  const progress = stageProgress(reveal, "lanes");
  if (progress <= 0) return { type: "FeatureCollection", features };

  for (const lane of affected.lanes) {
    const risk = lane.quantities.risk;
    const weight = risk ? clamp01(risk.value) : 0.3;
    const codes = (lane.attrs.chokepoints as string[] | undefined) ?? [];

    // One line per affected port this lane reaches: the leg that actually
    // carries the consequence is threatened water to affected quay, which is
    // also the leg an operator is reasoning about.
    for (const port of affected.ports) {
      const path = legGeometry(codes, affected, port);
      if (!path || path.length < 2) continue;
      features.push({
        type: "Feature",
        geometry: { type: "LineString", coordinates: path },
        properties: {
          part: "lane",
          laneCode: lane.id,
          portCode: port.id,
          color: CASCADE_COLOR.carried,
          // 1.4 to 5.2 px: heavy enough to read as consequence, light enough
          // that several overlapping lanes stay separable.
          width: 1.4 + weight * 3.8,
          opacity: 0.75 * progress,
          risk: risk?.value ?? null,
          confidence: risk?.confidence ?? null,
          chokepoints: codes.join(","),
        },
      });
    }
  }
  return { type: "FeatureCollection", features };
}

/**
 * The water-only leg from a threatened chokepoint to an affected port.
 *
 * Geometry comes from the sea-route catalogue, whose node ids are chokepoint
 * codes and port locodes alike, so the consequence line follows the same water
 * a vessel would. Drawing a straight line instead would put consequence across
 * Arabia, and a line across land discredits every number attached to it -- so a
 * leg the catalogue does not hold is omitted rather than approximated.
 */
function legGeometry(
  codes: string[],
  affected: CascadeAffected,
  port: CascadeSubject,
): Array<[number, number]> | null {
  const chokepoint = affected.chokepoints.find((c) => codes.includes(c.id))
    ?? affected.chokepoints[0];
  if (!chokepoint) return null;

  const route = seaRoute(chokepoint.id, port.id);
  if (!route || route.path.coords.length < 2) return null;
  return route.path.coords.map((c) => [c[0], c[1]] as [number, number]);
}

function chokepointPoint(code: string): [number, number] | null {
  const record = CHOKEPOINT_BY_CODE.get(code);
  if (!record) return null;
  return [record.lon, record.lat];
}

/**
 * Impact rings: the threatened water, and the quays the consequence lands on.
 *
 * Radius encodes computed magnitude, so a port with 57% projected yard pressure
 * draws a visibly larger ring than one at 12%. That is the whole point of
 * putting it on the map instead of in a table.
 */
export function cascadeRingFeatures(
  affected: CascadeAffected | undefined,
  reveal: number,
): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  if (!affected) return { type: "FeatureCollection", features };

  const chokeProgress = stageProgress(reveal, "chokepoint");
  for (const chokepoint of affected.chokepoints) {
    const point = chokepointPoint(chokepoint.id);
    if (!point || chokeProgress <= 0) continue;
    const risk = chokepoint.quantities.risk;
    const weight = risk ? clamp01(risk.value) : 0.5;
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: point },
      properties: {
        radius: 10 + weight * 16,
        color: CASCADE_COLOR.source,
        width: 1.4,
        opacity: 0.85 * chokeProgress,
        kind: "chokepoint",
        id: chokepoint.id,
      },
    });
  }

  const portProgress = stageProgress(reveal, "ports");
  for (const port of affected.ports) {
    if (port.lat == null || port.lon == null || portProgress <= 0) continue;
    // Pressure if the engine computed it, otherwise the aggregate delay, so a
    // port always draws at the strongest thing actually known about it.
    const pressure = port.quantities.ratio;
    const delay = port.quantities.hours;
    const weight = pressure
      ? magnitude(pressure, 0.6)
      : magnitude(delay, 480);
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [port.lon, port.lat] },
      properties: {
        radius: 9 + weight * 22,
        color: CASCADE_COLOR.landing,
        width: 1.6,
        opacity: 0.8 * portProgress,
        kind: "port",
        id: port.id,
        pressure: pressure?.value ?? null,
        delayHours: delay?.value ?? null,
      },
    });
  }

  return { type: "FeatureCollection", features };
}

/**
 * Which vessels the cascade touched, and how they should read.
 *
 * A committed hull is deliberately cool-coloured: it is exposed and nothing can
 * be done, and colouring it like an alarm would put it in the operator's eye at
 * the same weight as something they can still fix.
 */
export function cascadeVesselEmphasis(
  affected: CascadeAffected | undefined,
  reveal: number,
): { focusIds: Set<string>; committedIds: Set<string> } {
  const focusIds = new Set<string>();
  const committedIds = new Set<string>();
  if (!affected || stageProgress(reveal, "vessels") <= 0) {
    return { focusIds, committedIds };
  }
  for (const vessel of affected.vessels) {
    const risk = vessel.quantities.risk;
    const committed = Boolean(risk?.attrs?.already_entered);
    if (committed) committedIds.add(vessel.id);
    else focusIds.add(vessel.id);
  }
  return { focusIds, committedIds };
}

/** Everything the map needs for one cascade, in one pass. */
export function cascadeLayers(affected: CascadeAffected | undefined, reveal: number) {
  return {
    cascade: cascadeLaneFeatures(affected, reveal),
    rings: cascadeRingFeatures(affected, reveal),
    ...cascadeVesselEmphasis(affected, reveal),
  };
}
