/**
 * Everything the three map workspaces share.
 *
 * National command, the port cockpit and the vessel bridge draw the same chart
 * from the same artefacts; only the camera, the filter and the inspector differ.
 * Assembling that once here is what keeps the weather field, the port symbology
 * and the traffic filter identical wherever they appear -- and it means the
 * expensive pieces (the weather raster, the port features) are memoised on the
 * one thing that actually changes them.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useClockState, useTraffic } from "@/components/app/traffic-context";
import type { MapLabel, MapView } from "@/components/map/MaritimeMap";
import type { LayerKey } from "@/components/map/basemap";
import type { WeatherRaster } from "@/components/map/weather-layers";
import {
  buildCompositeRaster,
  buildStormCells,
  buildWeatherRaster,
} from "@/components/map/weather-layers";
import { CHOKEPOINTS } from "@/lib/maritime/chokepoints";
import { anchorageRadiusKm, seawardBearing } from "@/lib/maritime/port-geometry";
import type { NavStatus, VesselClass, VesselFix } from "@/lib/maritime/traffic-types";
import {
  buildWeatherTimeline,
  type WeatherFieldKey,
  type WeatherFrame,
} from "@/lib/maritime/weather-model";
import { useEnrichedPorts, useHealth, useNews, useWeather } from "@/services/hooks";
import type { PortSnapshot } from "@/types/portwatch";
import { bearingLine, circleRing, sectorRing } from "@/components/map/geometry";

/* ---------------------------------------------------------------- layers -- */

/**
 * How finely the weather raster follows the forecast cursor.
 *
 * The frame beneath it is interpolated between forecast days, so half an hour of
 * cursor movement is below the resolution of the data. Rebuilding for less than
 * that spends a per-pixel interpolation and a PNG encode to produce the same
 * image.
 */
const RASTER_QUANTUM_HOURS = 0.5;

/** Cached rasters. A full forecast span at the quantum above fits inside this. */
const RASTER_CACHE_LIMIT = 400;

export const DEFAULT_LAYERS: Record<LayerKey, boolean> = {
  traffic: true,
  ghosts: true,
  // Weather is the environment, not a variable a user has to opt into.
  weather: true,
  storms: true,
  ports: true,
  corridors: true,
  routes: true,
  tracks: true,
  vectors: true,
  chokepoints: true,
  events: false,
  zones: true,
  graticule: true,
};

export interface TrafficFilterState {
  classes: Set<VesselClass>;
  statuses: Set<NavStatus>;
  /** Only draw the vessels in this set. Used by selected-vessel isolation. */
  isolate: string | null;
}

const ALL_CLASSES: VesselClass[] = [
  "container",
  "tanker",
  "bulk",
  "lng",
  "roro",
  "cargo",
  "passenger",
  "service",
];

const ALL_STATUSES: NavStatus[] = [
  "underway",
  "inbound",
  "outbound",
  "anchored",
  "waiting",
  "moored",
  "service",
];

/* ------------------------------------------------------------------ ports -- */

export function portColor(risk: string | null | undefined): string {
  switch ((risk ?? "normal").toLowerCase()) {
    case "severe":
      return "#d05a4c";
    case "congested":
    case "high":
      return "#d3a02f";
    case "medium":
      return "#4c9fcb";
    default:
      return "#56b28d";
  }
}

function portFeatures(
  ports: PortSnapshot[],
  selected: string | null,
): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: ports
      .filter((port) => port.location)
      .map((port) => ({
        type: "Feature" as const,
        properties: {
          id: port.code,
          code: port.code,
          name: port.name,
          risk: port.risk,
          color: portColor(port.risk),
          pressure: Math.min(1, (port.queuePressure ?? 0) * 0.7 + (port.capacityPressure ?? 0) * 0.4),
          selected: selected === port.code,
        },
        geometry: {
          type: "Point" as const,
          coordinates: [port.location!.lon, port.location!.lat],
        },
      })),
  };
}

/**
 * Approach geometry for a port.
 *
 * Schematic, and every screen that shows it says so. The bearing comes from the
 * shipped water mask, the anchorage radius from the measured anchorage count and
 * queue pressure, and the fairway is the centreline of the approach sector. No
 * berth layout is claimed: this is a pressure diagram drawn in the right place.
 */
export function portZones(port: PortSnapshot | null): GeoJSON.FeatureCollection {
  if (!port?.location) return { type: "FeatureCollection", features: [] };
  const centre: [number, number] = [port.location.lon, port.location.lat];
  const seaward = seawardBearing(port.code, centre[0], centre[1]);
  const queue = port.queuePressure ?? 0;

  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { kind: "approach", label: "Approach sector", color: "#4c9fcb", opacity: 0.05 },
        geometry: { type: "Polygon", coordinates: [sectorRing(centre, 62, seaward, 32)] },
      },
      {
        type: "Feature",
        properties: {
          kind: "anchorage",
          label: `Anchorage · ${(port.anchorageCount ?? 0).toFixed(1)} waiting`,
          color: queue >= 0.6 ? "#d05a4c" : queue >= 0.35 ? "#d3a02f" : "#56b28d",
          opacity: 0.1,
        },
        geometry: {
          type: "Polygon",
          coordinates: [circleRing(centre, anchorageRadiusKm(port.anchorageCount, queue))],
        },
      },
      {
        type: "Feature",
        properties: { kind: "terminal", label: "Terminal area", color: "#8a7fc4", opacity: 0.16 },
        geometry: { type: "Polygon", coordinates: [circleRing(centre, 2.6, 24)] },
      },
      {
        type: "Feature",
        properties: { kind: "fairway", label: "Approach channel", color: "#6fb2d6" },
        geometry: { type: "LineString", coordinates: bearingLine(centre, seaward, 58) },
      },
    ],
  };
}

/* ------------------------------------------------------------------ hook -- */

export interface WorkspaceMap {
  ports: PortSnapshot[];
  portByCode: Map<string, PortSnapshot>;
  health: ReturnType<typeof useHealth>;
  portsQuery: ReturnType<typeof useEnrichedPorts>["query"];
  weatherQuery: ReturnType<typeof useWeather>;
  newsQuery: ReturnType<typeof useNews>;

  layers: Record<LayerKey, boolean>;
  toggleLayer: (key: LayerKey) => void;
  setLayer: (key: LayerKey, on: boolean) => void;

  filters: TrafficFilterState;
  toggleClass: (value: VesselClass) => void;
  toggleStatus: (value: NavStatus) => void;
  resetFilters: () => void;
  setIsolate: (id: string | null) => void;
  vesselFilter: (fix: VesselFix) => boolean;
  filterActive: boolean;

  /** Null means the composite. A key means a single-field comparison view. */
  weatherField: WeatherFieldKey | null;
  setWeatherField: (key: WeatherFieldKey | null) => void;
  timeline: ReturnType<typeof buildWeatherTimeline>;
  frame: WeatherFrame;
  raster: ReturnType<typeof buildCompositeRaster>;
  storms: ReturnType<typeof buildStormCells>;
  /** The frame three hours behind, from which storm motion is inferred. */
  previousFrame: WeatherFrame | null;
  showWind: boolean;
  setShowWind: (on: boolean) => void;

  data: {
    ports: GeoJSON.FeatureCollection;
    zones: GeoJSON.FeatureCollection;
    chokepoints: GeoJSON.FeatureCollection;
    storms: GeoJSON.FeatureCollection;
  };
  labels: MapLabel[];

  selectedPortCode: string | null;
  setSelectedPortCode: (code: string | null) => void;
  selectedVesselId: string | null;
  setSelectedVesselId: (id: string | null) => void;
  hoveredVesselId: string | null;
  setHoveredVesselId: (id: string | null) => void;

  focus: { center: [number, number]; zoom?: number; token: number } | null;
  flyTo: (center: [number, number], zoom?: number) => void;

  /** The instant the weather panel is showing. */
  weatherAt: number;
  offsetHours: number;
}

export function useWorkspaceMap(options: {
  /** Port whose approach geometry is drawn, if any. */
  zonesFor?: string | null;
  /** Layers this workspace overrides at mount. */
  layerOverrides?: Partial<Record<LayerKey, boolean>>;
  initialSelectedPort?: string | null;
  /** Start on a single field instead of the composite. */
  weatherField?: WeatherFieldKey | null;
} = {}): WorkspaceMap {
  const { ports: enrichedPorts, query: portsQuery } = useEnrichedPorts();
  const weatherQuery = useWeather();
  const newsQuery = useNews();
  const health = useHealth();
  const clockState = useClockState();

  const ports = enrichedPorts;
  const portByCode = useMemo(
    () => new Map(ports.map((port) => [port.code, port])),
    [ports],
  );

  const [layers, setLayers] = useState<Record<LayerKey, boolean>>({
    ...DEFAULT_LAYERS,
    ...options.layerOverrides,
  });
  const toggleLayer = useCallback((key: LayerKey) => {
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);
  const setLayer = useCallback((key: LayerKey, on: boolean) => {
    setLayers((prev) => ({ ...prev, [key]: on }));
  }, []);

  const [classes, setClasses] = useState<Set<VesselClass>>(() => new Set(ALL_CLASSES));
  const [statuses, setStatuses] = useState<Set<NavStatus>>(() => new Set(ALL_STATUSES));
  const [isolate, setIsolate] = useState<string | null>(null);

  const toggleClass = useCallback((value: VesselClass) => {
    setClasses((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }, []);
  const toggleStatus = useCallback((value: NavStatus) => {
    setStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }, []);
  const resetFilters = useCallback(() => {
    setClasses(new Set(ALL_CLASSES));
    setStatuses(new Set(ALL_STATUSES));
    setIsolate(null);
  }, []);

  const vesselFilter = useCallback(
    (fix: VesselFix) => {
      if (isolate) return fix.id === isolate || fix.owned;
      return classes.has(fix.vesselClass) && statuses.has(fix.status);
    },
    [classes, isolate, statuses],
  );

  const filterActive =
    isolate !== null || classes.size !== ALL_CLASSES.length || statuses.size !== ALL_STATUSES.length;

  /* --------------------------------------------------------------- weather -- */
  /**
   * The environment layer is a composite by default.
   *
   * `weatherField` still exists because the port weather screen compares one
   * variable across ports, and a composite there would be the wrong tool. On a
   * map-first workspace it is null, and the raster carries precipitation, wind
   * and severity together -- an operator should not have to discover that it is
   * blowing by switching away from the rain.
   */
  const [weatherField, setWeatherField] = useState<WeatherFieldKey | null>(
    options.weatherField ?? null,
  );
  const [showWind, setShowWind] = useState(true);

  const timeline = useMemo(
    () => buildWeatherTimeline(weatherQuery.data ?? [], ports),
    [ports, weatherQuery.data],
  );

  // The weather clock is the forecast series, not the replay clock: a raster
  // rebuilt on every animation frame would cost more than the traffic does.
  const offsetHours = clockState.offsetHours;
  const weatherAt = timeline.available
    ? timeline.from + offsetHours * 3_600_000
    : clockState.at + offsetHours * 3_600_000;

  // Tell the clock how far the forecast actually reaches, so the scrubber and
  // the play control cannot run past the data.
  const clock = useTraffic().clock;
  useEffect(() => {
    if (!timeline.available) return;
    clock.setMaxOffsetHours(
      Math.max(6, Math.round((timeline.to - timeline.from) / 3_600_000)),
    );
  }, [clock, timeline.available, timeline.from, timeline.to]);

  const frame = useMemo(() => timeline.frameAt(weatherAt), [timeline, weatherAt]);

  // The previous frame, so storm motion can be inferred from the risk trend
  // rather than invented. Three hours back: long enough for a cell to have
  // moved, short enough that it is the same cell.
  const previousFrame = useMemo(
    () => (timeline.available ? timeline.frameAt(weatherAt - 3 * 3_600_000) : null),
    [timeline, weatherAt],
  );

  /**
   * The raster is the expensive part of the frame and the least sensitive to a
   * few minutes of cursor movement.
   *
   * Building it is a per-pixel inverse-distance interpolation over every station
   * followed by a PNG encode. The frame underneath is interpolated between
   * forecast *days*, so two cursor positions half an hour apart produce visually
   * identical output -- rebuilding for both is pure cost. So the raster is keyed
   * on a quantised offset and cached: scrubbing back over ground already covered
   * is free, and the play loop pays for each half-hour once instead of on every
   * throttled tick.
   *
   * Everything else -- the read-out, the storm cells, the port values -- still
   * follows the un-quantised cursor, so nothing an operator reads is coarsened.
   */
  const rasterOffsetHours =
    Math.round(offsetHours / RASTER_QUANTUM_HOURS) * RASTER_QUANTUM_HOURS;
  const rasterAt = timeline.available
    ? timeline.from + rasterOffsetHours * 3_600_000
    : clockState.at + rasterOffsetHours * 3_600_000;

  const rasterCache = useRef<{
    timeline: unknown;
    field: WeatherFieldKey | null;
    entries: Map<number, WeatherRaster | null>;
  }>({ timeline: null, field: null, entries: new Map() });

  const raster = useMemo(() => {
    if (!layers.weather) return null;
    const store = rasterCache.current;
    // Invalidated here rather than in an effect. An effect runs *after* the
    // render that changed the timeline, so the first render with new weather
    // data would be served a raster built from the old one -- which is how an
    // empty legend appears on a screen whose data has just arrived.
    if (store.timeline !== timeline || store.field !== weatherField) {
      store.timeline = timeline;
      store.field = weatherField;
      store.entries = new Map();
    }

    const hit = store.entries.get(rasterOffsetHours);
    if (hit !== undefined) return hit;

    const built = weatherField
      ? buildWeatherRaster(timeline.frameAt(rasterAt), weatherField)
      : buildCompositeRaster(timeline.frameAt(rasterAt));
    // Bounded: a full forecast span at this quantum is a few hundred entries,
    // and each is one small PNG data URL. Oldest out first.
    if (store.entries.size >= RASTER_CACHE_LIMIT) {
      const oldest = store.entries.keys().next();
      if (!oldest.done) store.entries.delete(oldest.value);
    }
    store.entries.set(rasterOffsetHours, built);
    return built;
    // `timeline` and `rasterAt` are the frame's inputs; `frame` itself is not,
    // because the raster deliberately runs on the quantised cursor.
  }, [layers.weather, rasterAt, rasterOffsetHours, timeline, weatherField]);

  const storms = useMemo(
    () => buildStormCells(frame, previousFrame),
    [frame, previousFrame],
  );

  /* ----------------------------------------------------------- selections -- */
  const [selectedPortCode, setSelectedPortCode] = useState<string | null>(
    options.initialSelectedPort ?? null,
  );
  const [selectedVesselId, setSelectedVesselId] = useState<string | null>(null);
  const [hoveredVesselId, setHoveredVesselId] = useState<string | null>(null);

  const [focus, setFocus] = useState<
    { center: [number, number]; zoom?: number; token: number } | null
  >(null);
  const token = useRef(0);
  const flyTo = useCallback((center: [number, number], zoom?: number) => {
    token.current += 1;
    setFocus({ center, zoom, token: token.current });
  }, []);

  /* --------------------------------------------------------------- sources -- */
  const zonePort = options.zonesFor ? (portByCode.get(options.zonesFor) ?? null) : null;

  const data = useMemo(
    () => ({
      ports: portFeatures(ports, selectedPortCode),
      zones: portZones(zonePort),
      chokepoints: {
        type: "FeatureCollection" as const,
        features: CHOKEPOINTS.map((choke) => ({
          type: "Feature" as const,
          properties: { id: choke.code, code: choke.code, name: choke.name, color: "#4c9fcb" },
          geometry: { type: "Point" as const, coordinates: [choke.lon, choke.lat] },
        })),
      },
      storms: storms.data,
    }),
    [ports, selectedPortCode, storms.data, zonePort],
  );

  const labels = useMemo<MapLabel[]>(
    () =>
      ports
        .filter((port) => port.location)
        .map((port) => ({
          id: port.code,
          lon: port.location!.lon,
          lat: port.location!.lat,
          text: port.short,
          color: portColor(port.risk),
          emphasis: port.code === selectedPortCode || port.risk === "severe",
        })),
    [ports, selectedPortCode],
  );

  return {
    ports,
    portByCode,
    health,
    portsQuery,
    weatherQuery,
    newsQuery,
    layers,
    toggleLayer,
    setLayer,
    filters: { classes, statuses, isolate },
    toggleClass,
    toggleStatus,
    resetFilters,
    setIsolate,
    vesselFilter,
    filterActive,
    weatherField,
    setWeatherField,
    timeline,
    frame,
    raster,
    storms,
    previousFrame,
    showWind,
    setShowWind,
    data,
    labels,
    selectedPortCode,
    setSelectedPortCode,
    selectedVesselId,
    setSelectedVesselId,
    hoveredVesselId,
    setHoveredVesselId,
    focus,
    flyTo,
    weatherAt,
    offsetHours,
  };
}

export { ALL_CLASSES, ALL_STATUSES };
export type { WeatherFieldKey };
