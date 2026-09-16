/**
 * Draw a historical mission at its replay clock.
 *
 * The chart shows only what the mission holds: the blocked water, and the
 * illustrative hulls where the replay engine placed them on the modelled
 * lane at the clock -- the same derivation the decision engine uses, with
 * the basis carried on every point. The live world's ports, weather and
 * traffic are not drawn; they are 2026 and the clock is not.
 *
 * Once a decision is open for one hull, that hull's options are drawn by
 * the decision layers and the other hulls stay as faint marks, so the
 * operator keeps the whole fleet in view while choosing for one ship.
 */

import type { MapLabel } from "@/components/map/MaritimeMap";
import type { DecisionProblem, MissionReplayState } from "@/types/decisions";

import {
  BASELINE_COLOUR,
  SUBJECT_COLOUR,
  boundsOf,
  decisionLabels,
  decisionLayers,
} from "./decision-layers";

const BLOCKAGE_COLOUR = "#e0533d";

export function missionLayers(
  state: MissionReplayState | null | undefined,
  problem: DecisionProblem | null,
  selectedOptionId: string | null,
  compare: boolean,
): { cascade: GeoJSON.FeatureCollection; focusIds: Set<string> } {
  const decision = decisionLayers(problem, selectedOptionId, compare);
  const features: GeoJSON.Feature[] = [...decision.cascade.features];
  const focusIds = new Set(decision.focusIds);
  const geography = state?.geography;
  if (!geography)
    return { cascade: { type: "FeatureCollection", features }, focusIds };

  const subjectId = problem?.subject.id ?? null;
  for (const hull of geography.hulls) {
    if (hull.lat == null || hull.lon == null) continue;
    const isSubject = hull.vesselId === subjectId;
    // The subject's own passage is drawn by the decision layers.
    if (!isSubject && hull.lane.length > 1) {
      features.push({
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: hull.lane.map(([lat, lon]) => [lon, lat]),
        },
        properties: {
          part: "lane",
          color: BASELINE_COLOUR,
          width: 1,
          opacity: problem ? 0.28 : 0.5,
          id: `mission:lane:${hull.vesselId}`,
        },
      });
    }
    if (isSubject) continue;
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [hull.lon, hull.lat] },
      properties: {
        part: "ring",
        radius: 6,
        color: SUBJECT_COLOUR,
        width: 1.6,
        opacity: problem ? 0.5 : 0.9,
        kind: "hull",
        id: hull.vesselId,
        basis: hull.basis,
      },
    });
    focusIds.add(hull.vesselId);
  }

  // A port mission: the closed ports are the subject, drawn as rings the
  // event's own position sits between.
  for (const port of geography.ports ?? []) {
    if (port.lat == null || port.lon == null) continue;
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [port.lon, port.lat] },
      properties: {
        part: "ring",
        radius: 11,
        color: BLOCKAGE_COLOUR,
        width: 1.6,
        opacity: problem ? 0.55 : 0.9,
        kind: "port",
        id: `mission:port:${port.code}`,
      },
    });
  }

  // The blocked water. The decision layers draw it too when a problem is
  // open, from the problem's own evidence; without one, the mission says
  // where it is.
  const blockage = geography.chokepoint;
  if (!problem && blockage.lat != null && blockage.lon != null) {
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [blockage.lon, blockage.lat] },
      properties: {
        part: "ring",
        radius: 16,
        color: BLOCKAGE_COLOUR,
        width: 1.6,
        opacity: 0.9,
        kind: "chokepoint",
        id: blockage.code,
      },
    });
  }
  return { cascade: { type: "FeatureCollection", features }, focusIds };
}

export function missionLabels(
  state: MissionReplayState | null | undefined,
  problem: DecisionProblem | null,
  selectedOptionId: string | null,
  compare: boolean,
): MapLabel[] {
  const out: MapLabel[] = decisionLabels(problem, selectedOptionId, compare);
  const geography = state?.geography;
  if (!geography) return out;
  const subjectId = problem?.subject.id ?? null;
  for (const hull of geography.hulls) {
    if (hull.lat == null || hull.lon == null) continue;
    if (hull.vesselId === subjectId) continue;
    const ahead = Object.entries(hull.hoursToChokepoint)
      .filter(([, h]) => h != null && h >= 0)
      .sort((a, b) => a[1] - b[1])[0];
    const toPort =
      geography.subjectKind === "port" && hull.hoursToDestination != null
        ? `${hull.hoursToDestination.toFixed(0)} h to ${hull.destinationPort} · modelled`
        : null;
    out.push({
      id: `mission:hull:${hull.vesselId}`,
      lon: hull.lon,
      lat: hull.lat,
      text: hull.name,
      sub:
        toPort ??
        (ahead
          ? `${ahead[1].toFixed(0)} h to ${ahead[0]} · modelled`
          : "past the strait · modelled"),
      color: SUBJECT_COLOUR,
      muted: Boolean(problem),
    });
  }
  for (const port of geography.ports ?? []) {
    if (port.lat == null || port.lon == null) continue;
    out.push({
      id: `mission:port:${port.code}`,
      lon: port.lon,
      lat: port.lat,
      text: port.name,
      sub: `${port.code} · closed to arrivals as reported at the clock`,
      color: BLOCKAGE_COLOUR,
      emphasis: !problem,
    });
  }
  const blockage = geography.chokepoint;
  if (blockage.lat != null && blockage.lon != null) {
    out.push({
      id: `mission:blockage:${blockage.code}`,
      lon: blockage.lon,
      lat: blockage.lat,
      text: state?.eventTitle ?? blockage.code,
      sub: `${blockage.code} · as reported at the clock`,
      color: BLOCKAGE_COLOUR,
      emphasis: !problem,
    });
  }
  return out;
}

/**
 * The box that holds every hull, its lane and the blocked water at once. The
 * decision bounds take over when a problem is open.
 */
export function missionBounds(
  state: MissionReplayState | null | undefined,
): [[number, number], [number, number]] | null {
  const geography = state?.geography;
  if (!geography) return null;
  const points: Array<[number, number]> = [];
  for (const hull of geography.hulls) {
    if (hull.lat != null && hull.lon != null) points.push([hull.lon, hull.lat]);
    const last = hull.lane[hull.lane.length - 1];
    if (last) points.push([last[1], last[0]]);
  }
  if (geography.chokepoint.lat != null && geography.chokepoint.lon != null) {
    points.push([geography.chokepoint.lon, geography.chokepoint.lat]);
  }
  for (const port of geography.ports ?? []) {
    if (port.lat != null && port.lon != null) points.push([port.lon, port.lat]);
  }
  return boundsOf(points);
}
