/**
 * Chokepoint exposure, drawn as water.
 *
 * The event feed measures how exposed each port is to a disruption at a
 * chokepoint. That exposure used to be drawn as a straight line from the strait
 * to the quay, which put the Suez corridor across Saudi Arabia and the Malacca
 * corridor over Sumatra. It is now the actual passage a ship would run between
 * the two, taken from the routing catalogue, so a corridor's length on the chart
 * is the length of the diversion it represents.
 */

import { CHOKEPOINTS, CHOKEPOINT_BY_CODE } from "./chokepoints";
import { seaRoute } from "./searoutes";
import type { NewsEvent, PortSnapshot } from "@/types/portwatch";

export interface ExposureLayers {
  routes: GeoJSON.FeatureCollection;
  events: GeoJSON.FeatureCollection;
  chokepoints: GeoJSON.FeatureCollection;
  corridors: number;
  placedEvents: number;
  unplacedEvents: number;
  /** Corridors the routing graph could not draw, and why. */
  note: string | null;
}

function severityColour(severity: number): string {
  return severity >= 0.7 ? "#d05a4c" : severity >= 0.4 ? "#d3a02f" : "#4c9fcb";
}

export function buildExposureLayers(
  events: NewsEvent[],
  ports: PortSnapshot[],
): ExposureLayers {
  const byCode = new Map(ports.map((port) => [port.code, port]));
  const worst = new Map<string, { severity: number; exposure: Map<string, number> }>();

  for (const event of events) {
    if (!event.chokepoint) continue;
    const entry = worst.get(event.chokepoint) ?? {
      severity: 0,
      exposure: new Map<string, number>(),
    };
    entry.severity = Math.max(entry.severity, event.severityScore ?? 0);
    for (const exposure of event.exposure ?? []) {
      entry.exposure.set(
        exposure.portCode,
        Math.max(entry.exposure.get(exposure.portCode) ?? 0, exposure.exposure),
      );
    }
    worst.set(event.chokepoint, entry);
  }

  const routeFeatures: GeoJSON.Feature[] = [];
  const chokeFeatures: GeoJSON.Feature[] = [];
  let unroutable = 0;

  for (const choke of CHOKEPOINTS) {
    const entry = worst.get(choke.code);
    const severity = entry?.severity ?? 0;
    const colour = severityColour(severity);

    chokeFeatures.push({
      type: "Feature",
      properties: {
        id: choke.code,
        code: choke.code,
        name: choke.name,
        severity,
        color: colour,
        exposedPorts: entry ? entry.exposure.size : 0,
      },
      geometry: { type: "Point", coordinates: [choke.lon, choke.lat] },
    });

    if (!entry || !choke.waypointId) {
      if (entry) unroutable += entry.exposure.size;
      continue;
    }

    const ranked = [...entry.exposure.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
    for (const [portCode, exposure] of ranked) {
      const port = byCode.get(portCode);
      if (!port?.location) continue;
      const route = seaRoute(choke.waypointId, portCode);
      if (!route) {
        unroutable += 1;
        continue;
      }
      routeFeatures.push({
        type: "Feature",
        properties: {
          part: "exposure",
          id: `${choke.code}-${portCode}`,
          color: colour,
          width: 0.8 + exposure * 2.2,
          opacity: 0.25 + exposure * 0.5,
          label: `${choke.name} → ${port.short} · exposure ${exposure.toFixed(2)}`,
        },
        geometry: { type: "LineString", coordinates: route.path.coords },
      });
    }
  }

  const eventFeatures: GeoJSON.Feature[] = [];
  let unplaced = 0;
  for (const event of events) {
    const choke = event.chokepoint ? CHOKEPOINT_BY_CODE.get(event.chokepoint) : null;
    if (!choke) {
      unplaced += 1;
      continue;
    }
    eventFeatures.push({
      type: "Feature",
      properties: {
        id: event.id,
        title: event.title,
        severity: event.severityScore,
        color: severityColour(event.severityScore),
      },
      geometry: { type: "Point", coordinates: [choke.lon, choke.lat] },
    });
  }

  const notes: string[] = [];
  if (unplaced > 0) {
    notes.push(`${unplaced} of ${events.length} events carry no mapped chokepoint and are listed only.`);
  }
  if (unroutable > 0) {
    notes.push(`${unroutable} exposure pairs have no water route in the catalogue and are not drawn.`);
  }

  return {
    routes: { type: "FeatureCollection", features: routeFeatures },
    events: { type: "FeatureCollection", features: eventFeatures },
    chokepoints: { type: "FeatureCollection", features: chokeFeatures },
    corridors: routeFeatures.length,
    placedEvents: eventFeatures.length,
    unplacedEvents: unplaced,
    note: notes.length ? notes.join(" ") : null,
  };
}
