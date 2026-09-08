/**
 * Assembles every map source from the artefacts a screen already has.
 *
 * Both the national radar and the port-local twin draw the same geometry from
 * the same builders; only the viewport and which toggles start on differ. That
 * keeps the weather field, the exposure corridors and the port symbology
 * identical wherever they appear.
 */

import { useMemo, useState } from "react";

import type {
  NewsEvent,
  PortSnapshot,
  VesselActivity,
  WeatherSignal,
} from "@/types/portwatch";
import type { LayerKey } from "./basemap";
import type { MapLabel, MapLayerData } from "./OperationsMap";
import {
  WEATHER_FIELDS,
  buildEvents,
  buildExposureLanes,
  buildLanes,
  buildPortZones,
  buildPorts,
  buildStorms,
  buildVesselActivity,
  buildWeatherField,
  portColor,
  type Lane,
  type WeatherField,
} from "./layers";

export interface OperationalMapInput {
  ports: PortSnapshot[];
  weather: WeatherSignal[];
  vessels: VesselActivity[];
  events: NewsEvent[];
  selected?: string | null;
  emphasise?: Set<string>;
  /** Extra corridors a screen wants drawn (fleet routes, scenario lanes). */
  extraLanes?: Lane[];
  /** Draw the schematic approach geometry for this port. */
  zonesFor?: string | null;
  /** Suppress the chokepoint exposure corridors (port-local views). */
  exposureLanes?: boolean;
}

export function useOperationalMap(input: OperationalMapInput) {
  const {
    ports,
    weather,
    vessels,
    events,
    selected = null,
    emphasise,
    extraLanes = [],
    zonesFor = null,
    exposureLanes = true,
  } = input;

  const [weatherField, setWeatherField] = useState<WeatherField>("rain");

  /** Station coverage per field, so unavailable fields are visibly unavailable. */
  const availability = useMemo(() => {
    const out: Partial<Record<WeatherField, number>> = {};
    for (const spec of Object.values(WEATHER_FIELDS)) {
      out[spec.key] = weather.filter((signal) => {
        const value = spec.read(signal);
        return value != null && !Number.isNaN(value);
      }).length;
    }
    return out;
  }, [weather]);

  const field = useMemo(
    () => buildWeatherField(weather, ports, weatherField),
    [ports, weather, weatherField],
  );

  const storms = useMemo(() => buildStorms(weather, ports), [ports, weather]);

  const exposure = useMemo(
    () => buildExposureLanes(exposureLanes ? events : [], ports),
    [events, exposureLanes, ports],
  );

  const eventLayer = useMemo(() => buildEvents(events), [events]);

  const zones = useMemo(() => {
    const port = zonesFor ? ports.find((entry) => entry.code === zonesFor) : null;
    return port
      ? buildPortZones(port)
      : ({ type: "FeatureCollection", features: [] } as GeoJSON.FeatureCollection);
  }, [ports, zonesFor]);

  const data: MapLayerData = useMemo(
    () => ({
      ports: buildPorts(ports, { selected, emphasise }),
      vessels: buildVesselActivity(vessels),
      lanes: buildLanes([...exposure.lanes, ...extraLanes]),
      chokepoints: exposure.chokepoints,
      events: eventLayer.data,
      zones,
      wxfield: field.cells,
      wxstations: field.stations,
      storms: storms.data,
    }),
    [
      emphasise,
      eventLayer.data,
      exposure.chokepoints,
      exposure.lanes,
      extraLanes,
      field.cells,
      field.stations,
      ports,
      selected,
      storms.data,
      vessels,
      zones,
    ],
  );

  const labels: MapLabel[] = useMemo(
    () =>
      ports
        .filter((port) => port.location)
        .map((port) => ({
          id: port.code,
          lon: port.location!.lon,
          lat: port.location!.lat,
          text: port.short,
          color: portColor(port.risk),
          emphasis:
            port.code === selected ||
            port.risk === "severe" ||
            emphasise?.has(port.code) === true,
        })),
    [emphasise, ports, selected],
  );

  const counts: Partial<Record<LayerKey, number>> = {
    ports: ports.length,
    vessels: vessels.length,
    weather: field.covered,
    storms: storms.count,
    routes: exposure.lanes.length + extraLanes.length,
    chokepoints: exposure.chokepoints.features.length,
    events: eventLayer.placed,
  };

  const spec = WEATHER_FIELDS[weatherField];
  const weatherNote =
    field.covered > 0
      ? `${spec.label} interpolated from ${field.covered} port stations (inverse distance, 420 km cutoff, 0.35° cells).` +
        (field.missing.length
          ? ` ${field.missing.length} station${field.missing.length === 1 ? "" : "s"} carry no ${spec.label.toLowerCase()} reading.`
          : "")
      : `No ${spec.label.toLowerCase()} readings in this weather artefact.`;

  const eventNote =
    eventLayer.unplaced > 0
      ? `${eventLayer.unplaced} of ${events.length} events have no mapped chokepoint and are listed only.`
      : null;

  return {
    data,
    labels,
    counts,
    availability,
    weatherField,
    setWeatherField,
    weatherNote,
    eventNote,
    stormCount: storms.count,
  };
}
