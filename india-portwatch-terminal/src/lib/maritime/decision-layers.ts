/**
 * Draw a computed decision on the water.
 *
 * Every option the engine evaluated carries the passage it would run, as
 * (lat, lon) pairs the backend assembled from the same water-only routing
 * catalogue the chart draws. This module turns them into features for the
 * `cascade` source: the baseline thin and neutral, the selected option solid
 * and full weight in its own colour, the alternatives dashed in theirs, and
 * the rejected ones faint and red so an operator can see what was impossible
 * and why it is not on offer.
 *
 * The port ring is the part that makes the world change between options.
 * Its radius is the yard pressure the engine computed *for that option*, so
 * switching from "continue" to "divert" visibly changes the quay the delay
 * lands on. Nothing here is styled by a rule that lives only in the client.
 */

import type { DecisionOption, DecisionProblem } from "@/types/decisions";

import { CHOKEPOINT_BY_CODE } from "./chokepoints";

/** One colour per option letter. The baseline is deliberately colourless. */
export const OPTION_COLOURS = [
  "#e08c3d",
  "#5aa9d6",
  "#9b7cd6",
  "#3fbf9f",
  "#d96fa5",
  "#d9b23c",
] as const;
export const BASELINE_COLOUR = "#7c8ea3";
export const REJECTED_COLOUR = "#e0533d";
export const SUBJECT_COLOUR = "#f2f7fb";

const clamp01 = (n: number) => Math.max(0, Math.min(1, n));

/** Letters and colours for the feasible non-baseline options, in engine order. */
export function optionStyles(
  problem: DecisionProblem,
): Map<string, { letter: string; colour: string }> {
  const styles = new Map<string, { letter: string; colour: string }>();
  let index = 0;
  for (const option of problem.options) {
    if (option.isBaseline) {
      styles.set(option.optionId, { letter: "—", colour: BASELINE_COLOUR });
      continue;
    }
    if (option.status !== "FEASIBLE") {
      styles.set(option.optionId, { letter: "×", colour: REJECTED_COLOUR });
      continue;
    }
    styles.set(option.optionId, {
      letter: String.fromCharCode(65 + index),
      colour: OPTION_COLOURS[index % OPTION_COLOURS.length],
    });
    index += 1;
  }
  return styles;
}

function lineFor(option: DecisionOption): Array<[number, number]> | null {
  if (!option.geometry || option.geometry.length < 2) return null;
  return option.geometry.map(([lat, lon]) => [lon, lat] as [number, number]);
}

/**
 * Lines and rings for one decision.
 *
 * `compare` draws every feasible option; otherwise only the selected one and
 * the baseline, so a single choice reads cleanly. Rejected options are drawn
 * in compare mode only, faint, because their whole point is to be seen next
 * to the ones that survived.
 */
export function decisionLayers(
  problem: DecisionProblem | null | undefined,
  selectedOptionId: string | null,
  compare: boolean,
): { cascade: GeoJSON.FeatureCollection; focusIds: Set<string> } {
  const features: GeoJSON.Feature[] = [];
  const focusIds = new Set<string>();
  if (!problem)
    return { cascade: { type: "FeatureCollection", features }, focusIds };

  const styles = optionStyles(problem);
  const selected =
    problem.options.find((o) => o.optionId === selectedOptionId) ?? null;
  const baseline = problem.options.find((o) => o.isBaseline) ?? null;

  const visible = problem.options.filter((option) => {
    if (option.isBaseline) return true;
    if (option.optionId === selectedOptionId) return true;
    return compare;
  });

  for (const option of visible) {
    const line = lineFor(option);
    if (!line) continue;
    const style = styles.get(option.optionId)!;
    const isSelected = option.optionId === selectedOptionId;
    const rejected = option.status !== "FEASIBLE";
    features.push({
      type: "Feature",
      geometry: { type: "LineString", coordinates: line },
      properties: {
        part: option.isBaseline || isSelected ? "lane" : "flow",
        optionId: option.optionId,
        color: style.colour,
        width: isSelected
          ? 3.8
          : option.isBaseline
            ? 1.4
            : rejected
              ? 1.2
              : 2.2,
        opacity: isSelected
          ? 0.95
          : option.isBaseline
            ? 0.7
            : rejected
              ? 0.35
              : 0.8,
        letter: style.letter,
        label: option.label,
      },
    });
  }

  // The port ring: the selected option's yard pressure at its destination. In
  // compare mode every visible option lands its own ring, so a quay under
  // three different futures shows three different circles.
  const ringOptions = compare
    ? visible.filter((o) => o.status === "FEASIBLE")
    : [selected ?? baseline].filter(Boolean);
  for (const option of ringOptions as DecisionOption[]) {
    const style = styles.get(option.optionId)!;
    for (const consequence of option.evaluation?.consequences ?? []) {
      if (consequence.kind !== "port") continue;
      const pressure = consequence.quantities?.ratio?.value ?? null;
      const hours = consequence.quantities?.hours?.value ?? null;
      const point = portPoint(consequence.node.split(":")[1], problem);
      if (!point) continue;
      const weight =
        pressure != null
          ? clamp01(pressure / 0.6)
          : hours != null
            ? clamp01(hours / 480)
            : 0.2;
      features.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: point },
        properties: {
          part: "ring",
          radius: 9 + weight * 22,
          color: style.colour,
          width: option.optionId === selectedOptionId ? 2.2 : 1.2,
          opacity: option.optionId === selectedOptionId ? 0.9 : 0.55,
          kind: "port",
          id: consequence.node,
          optionId: option.optionId,
          pressure,
          delayHours: hours,
        },
      });
    }
  }

  // The hull, where the engine placed it.
  const position = problem.evidence?.position;
  if (position?.lat != null && position?.lon != null) {
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [position.lon, position.lat] },
      properties: {
        part: "ring",
        radius: 7,
        color: SUBJECT_COLOUR,
        width: 2,
        opacity: 0.95,
        kind: "subject",
        id: problem.subject.id,
        basis: position.basis,
      },
    });
    focusIds.add(problem.subject.id);
  }

  // The threatened water, from the evidence rather than a client lookup.
  const chokepoint = problem.evidence?.exposure?.attrs?.chokepoint as
    string | undefined;
  const record = chokepoint ? CHOKEPOINT_BY_CODE.get(chokepoint) : null;
  if (record) {
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [record.lon, record.lat] },
      properties: {
        part: "ring",
        radius: 14,
        color: "#e0533d",
        width: 1.4,
        opacity: 0.85,
        kind: "chokepoint",
        id: record.code,
      },
    });
  }

  return { cascade: { type: "FeatureCollection", features }, focusIds };
}

/** A port's coordinates from the option consequences' own evidence, else the registry the chart holds. */
function portPoint(
  code: string | undefined,
  problem: DecisionProblem,
): [number, number] | null {
  if (!code) return null;
  const known = PORT_POINTS[code];
  if (known) return known;
  const routes = problem.evidence?.routes;
  if (routes?.portCode === code && problem.options[0]?.geometry?.length) {
    const last =
      problem.options[0].geometry![problem.options[0].geometry!.length - 1];
    return [last[1], last[0]];
  }
  return null;
}

/** Indian port approaches, matching the routing catalogue's waypoints. */
const PORT_POINTS: Record<string, [number, number]> = {
  INIXY: [70.22, 23.03],
  INMUN: [69.71, 22.74],
  INNSA: [72.95, 18.95],
  INBOM: [72.85, 18.94],
  INMRM: [73.8, 15.41],
  INNML: [74.81, 12.92],
  INCOK: [76.27, 9.97],
  INTUT: [78.15, 8.76],
  INMAA: [80.3, 13.1],
  INENR: [80.32, 13.25],
  INKAT: [80.32, 13.25],
  INVTZ: [83.29, 17.69],
  INPRT: [86.68, 20.27],
  INCCU: [88.1, 22.03],
};

/** The chart's theatre. A passage that leaves it is labelled where it exits. */
const THEATRE = { west: -49, east: 114, south: -52, north: 58 } as const;

function insideTheatre([lon, lat]: [number, number]): boolean {
  return (
    lon >= THEATRE.west &&
    lon <= THEATRE.east &&
    lat >= THEATRE.south &&
    lat <= THEATRE.north
  );
}

/**
 * Labels for the options on the water: the letter, the action and its ETA
 * shift, placed where the passage is readable -- and, for a routing that
 * leaves the chart (the Cape, the Mediterranean), at the point it exits, so
 * a line running off the frame is named rather than mysterious.
 */
export function decisionLabels(
  problem: DecisionProblem | null | undefined,
  selectedOptionId: string | null,
  compare: boolean,
): Array<{
  id: string;
  lon: number;
  lat: number;
  text: string;
  sub?: string;
  color?: string;
  emphasis?: boolean;
  muted?: boolean;
}> {
  if (!problem) return [];
  const styles = optionStyles(problem);
  const out: Array<{
    id: string;
    lon: number;
    lat: number;
    text: string;
    sub?: string;
    color?: string;
    emphasis?: boolean;
    muted?: boolean;
  }> = [];
  const visible = problem.options.filter(
    (o) =>
      o.isBaseline ||
      o.optionId === selectedOptionId ||
      (compare && o.status === "FEASIBLE"),
  );
  for (const option of visible) {
    const line = lineFor(option);
    if (!line) continue;
    const style = styles.get(option.optionId)!;
    const eta = option.evaluation?.objectives.eta;
    const shift =
      eta?.available && eta.value != null
        ? `${eta.value >= 0 ? "+" : ""}${eta.value.toFixed(0)} h`
        : "ETA n/a";
    // The last point inside the theatre before the passage leaves it, else
    // the middle of the passage.
    let anchor: [number, number] | null = null;
    let leaves = false;
    for (let i = 0; i < line.length; i += 1) {
      if (!insideTheatre(line[i])) {
        anchor = i > 0 ? line[i - 1] : null;
        leaves = true;
        break;
      }
    }
    if (!anchor) anchor = line[Math.floor(line.length * 0.55)];
    if (!anchor) continue;
    out.push({
      id: `decision:${option.optionId}`,
      lon: anchor[0],
      lat: anchor[1],
      text: option.isBaseline
        ? `Current plan · ${shift}`
        : `${style.letter} · ${option.label}`,
      sub: option.isBaseline
        ? undefined
        : `${shift}${leaves ? " · continues off the chart" : ""}`,
      color: style.colour,
      emphasis: option.optionId === selectedOptionId,
      muted: option.status !== "FEASIBLE",
    });
  }
  const position = problem.evidence?.position;
  if (position?.lat != null && position?.lon != null) {
    out.push({
      id: `decision:subject:${problem.subject.id}`,
      lon: position.lon,
      lat: position.lat,
      text: problem.subject.label,
      sub: position.observed
        ? "observed position"
        : "modelled position on the lane",
      color: SUBJECT_COLOUR,
      emphasis: true,
    });
  }
  return out;
}

/**
 * The box that holds every visible passage, with a little water around it.
 *
 * The chart frames it with room left for the panels; the Cape routing pulls
 * the frame out to the basin, a strait-to-quay leg keeps it close. Returned
 * as [[west, south], [east, north]].
 */
export function decisionBounds(
  problem: DecisionProblem | null | undefined,
  selectedOptionId: string | null,
  compare: boolean,
): [[number, number], [number, number]] | null {
  if (!problem) return null;
  const lines = problem.options
    .filter(
      (o) =>
        o.isBaseline ||
        o.optionId === selectedOptionId ||
        (compare && o.status === "FEASIBLE"),
    )
    .map(lineFor)
    .filter((line): line is Array<[number, number]> => Boolean(line));
  const points = lines.flat();
  const position = problem.evidence?.position;
  if (position?.lat != null && position?.lon != null) {
    points.push([position.lon, position.lat]);
  }
  return boundsOf(points);
}

/** A box round some points, padded by a share of its own span and never thinner than a few degrees. */
export function boundsOf(
  points: Array<[number, number]>,
): [[number, number], [number, number]] | null {
  if (!points.length) return null;
  const lons = points.map((p) => p[0]);
  const lats = points.map((p) => p[1]);
  let minLon = Math.min(...lons),
    maxLon = Math.max(...lons);
  let minLat = Math.min(...lats),
    maxLat = Math.max(...lats);
  const padLon = Math.max((maxLon - minLon) * 0.08, 2);
  const padLat = Math.max((maxLat - minLat) * 0.08, 2);
  minLon -= padLon;
  maxLon += padLon;
  minLat -= padLat;
  maxLat += padLat;
  return [
    [Math.max(THEATRE.west, minLon), Math.max(THEATRE.south, minLat)],
    [Math.min(THEATRE.east, maxLon), Math.min(THEATRE.north, maxLat)],
  ];
}
