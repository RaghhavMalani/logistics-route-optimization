import { COLORS } from "@/components/miniature/palette";
/**
 * The maritime picture.
 *
 * One MapLibre instance owns the chart, the environment and the traffic. The
 * traffic loop lives here rather than in a parent because it runs at fifteen
 * hertz and writes straight into the GL sources: React never sees a vessel
 * position, so five hundred ships cost the reconciler nothing.
 *
 * Everything on the chart that is text -- port names, sea areas, vessel names,
 * merge counts -- is a React overlay projected from the map. That keeps the
 * product's typography on the map, removes a font-atlas fetch, and means a
 * hover card can show a measured value rather than a string baked into a tile.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";

import "maplibre-gl/dist/maplibre-gl.css";
import { loadChart } from "./chart-engine";

import { useTraffic } from "@/components/app/traffic-context";
import { MapPanelAccess } from "@/components/command/MapPanelAccess";
import type { VesselFix } from "@/lib/maritime/traffic-types";
import type { WeatherFrame } from "@/lib/maritime/weather-model";
import { cn } from "@/lib/utils";
import {
  BLANK_IMAGE,
  EMPTY,
  INDIA_VIEW,
  LAYER_GROUPS,
  REGION_BOUNDS,
  SEA_LABELS,
  buildStyle,
  type LayerKey,
  type RuntimeSource,
} from "./basemap";
import {
  buildGhostFeatures,
  buildTrafficFeatures,
  viewportTraffic,
  type ClusterMark,
  type VesselLabel,
} from "./traffic-layers";
import { corridorFeatures } from "@/lib/maritime/searoutes";
import { buildVesselIcons } from "./vessel-icons";
import type { WeatherRaster } from "./weather-layers";
import { WindLayer } from "./WindLayer";
import {
  registeredPorts,
  schematicAnchor,
  SCHEMATIC_ZOOM,
} from "./port-placement";
import { usePortMiniature } from "./usePortMiniature";

export interface MapLabel {
  id: string;
  lon: number;
  lat: number;
  text: string;
  sub?: string;
  color?: string;
  emphasis?: boolean;
  muted?: boolean;
}

export interface MapView {
  center: [number, number];
  zoom: number;
}

/** [[west, south], [east, north]]. */
export type MapBounds = [[number, number], [number, number]];
export type MapPadding = {
  top: number;
  bottom: number;
  left: number;
  right: number;
};

/**
 * One camera request. A centre with an optional zoom, or a box to frame with
 * room left for the panels over the chart; the token makes repeats fire.
 */
export type MapFocus = {
  center?: [number, number];
  zoom?: number;
  bounds?: MapBounds;
  padding?: MapPadding;
  token: number;
};

export interface MaritimeMapProps {
  layers: Partial<Record<LayerKey, boolean>>;
  data?: Partial<Record<RuntimeSource, GeoJSON.FeatureCollection>>;
  weatherRaster?: WeatherRaster | null;
  windFrame?: WeatherFrame | null;
  showWind?: boolean;
  /** Which vessels this workspace is allowed to draw. */
  vesselFilter?: (fix: VesselFix) => boolean;
  /** Drawn at full weight; anything outside is dimmed, never removed. */
  focusIds?: Set<string> | null;
  /** Never merged into a count, always named. */
  pinnedIds?: Set<string>;
  selectedVesselId?: string | null;
  onSelectVessel?: (id: string | null) => void;
  /** An observed transponder was clicked. Keyed by MMSI, never by a name. */
  onSelectObserved?: (mmsi: string | null) => void;
  onHoverVessel?: (id: string | null) => void;
  selectedPortCode?: string | null;
  onSelectPort?: (code: string) => void;
  showVectors?: boolean;
  forceVesselLabels?: boolean;
  maxVesselLabels?: number;
  labels?: MapLabel[];
  view?: MapView;
  /** Bump `token` to fly somewhere without owning the camera. */
  focus?: MapFocus | null;
  renderHoverCard?: (fix: VesselFix) => ReactNode;
  overlay?: ReactNode;
  className?: string;
  minZoom?: number;
  maxZoom?: number;
  onZoomChange?: (zoom: number) => void;
  loadingLabel?: string;
}

const RUNTIME_KEYS: RuntimeSource[] = [
  "storms",
  "zones",
  "ports",
  "routes",
  "tracks",
  "chokepoints",
  "events",
  // Consequence. Deliberately its own source rather than sharing `rings`,
  // which the traffic layer writes for own-vessel marks -- two writers on one
  // source means whichever renders last wins, silently.
  "cascade",
  "seastate",
  "observed",
];

interface Overlay {
  labels: Array<{ label: MapLabel; x: number; y: number }>;
  seas: Array<{ id: string; name: string; x: number; y: number }>;
  vessels: Array<{ label: VesselLabel; x: number; y: number }>;
  clusters: Array<{ mark: ClusterMark; x: number; y: number }>;
}

const EMPTY_OVERLAY: Overlay = {
  labels: [],
  seas: [],
  vessels: [],
  clusters: [],
};

const CHAPTER_CAMERA = { pitch: 50, bearing: -12 };
const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";
const UNPADDED: MapPadding = { top: 0, right: 0, bottom: 0, left: 0 };

function cameraDuration(duration: number) {
  return window.matchMedia(REDUCED_MOTION).matches ? 0 : duration;
}

function chapterTransition() {
  return {
    ...CHAPTER_CAMERA,
    duration: cameraDuration(1050),
    easing: (t: number) => t * t * t * (t * (6 * t - 15) + 10),
  };
}

function selectionPadding(map: MapLibreMap): MapPadding {
  const container = map.getContainer();
  const bounds = container.getBoundingClientRect();
  const inset = (side: "right" | "bottom") => {
    const panel = container.parentElement?.querySelector<HTMLElement>(
      `[data-map-camera-inset="${side}"]`,
    );
    const box = panel?.getBoundingClientRect();
    if (
      !box ||
      box.width === 0 ||
      box.height === 0 ||
      !panel?.childElementCount
    )
      return 0;
    const overlap =
      side === "right" ? bounds.right - box.left : bounds.bottom - box.top;
    const size = side === "right" ? bounds.width : bounds.height;
    return Math.max(0, Math.min(Math.round(overlap), size - 96));
  };
  return { ...UNPADDED, right: inset("right"), bottom: inset("bottom") };
}

function glideTo(map: MapLibreMap, center: [number, number], zoom: number) {
  map.flyTo({
    ...chapterTransition(),
    center,
    zoom: Math.min(map.getMaxZoom(), zoom),
    padding: selectionPadding(map),
  });
}

/**
 * The geometry the chart last wrote, exposed for the browser suite.
 *
 * The traffic layer has no DOM, so a test that counted markers would be testing
 * an implementation this product does not have. MapLibre's own source internals
 * are private and tile-clipped, so reading them back gives fragments rather than
 * passages. This is the same object the map just handed the GL context, which is
 * exactly what a test about "does the chart draw a route across land" needs.
 */
function publish(
  key: string,
  data: GeoJSON.FeatureCollection,
): GeoJSON.FeatureCollection {
  if (typeof window !== "undefined") {
    const registry = ((
      window as unknown as { __portwatchSources?: Record<string, unknown> }
    ).__portwatchSources ??= {});
    registry[key] = data;
  }
  return data;
}

export function MaritimeMap({
  layers,
  data,
  weatherRaster,
  windFrame,
  showWind = false,
  vesselFilter,
  focusIds = null,
  pinnedIds,
  selectedVesselId: vesselSelection,
  onSelectVessel,
  onSelectObserved,
  onHoverVessel,
  selectedPortCode = null,
  onSelectPort,
  showVectors = true,
  forceVesselLabels = false,
  maxVesselLabels = 26,
  labels = [],
  view,
  focus,
  renderHoverCard,
  overlay,
  className,
  minZoom = 2.6,
  maxZoom = 14,
  onZoomChange,
  loadingLabel = "Initialising chart",
}: MaritimeMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const sent = useRef<
    Partial<Record<RuntimeSource, GeoJSON.FeatureCollection>>
  >({});
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [suspended, setSuspended] = useState(false);
  const [mapSelection, setMapSelection] = useState<string | null>(null);
  const selectedVesselId =
    vesselSelection === undefined ? mapSelection : vesselSelection;
  const registered = useMemo(() => registeredPorts(data?.ports), [data?.ports]);
  const portIds = useMemo(
    () => new Set(registered.map((port) => port.code)),
    [registered],
  );
  const miniature = usePortMiniature(
    map,
    registered,
    layers.ports !== false && !suspended,
  );
  const miniatureRef = useRef(miniature);
  miniatureRef.current = miniature;
  const cameraSelection = useRef({
    port: selectedPortCode,
    vessel: selectedVesselId,
    focus: focus?.token,
  });
  const suspendedRef = useRef(false);
  useEffect(() => {
    // Keep the original chart, camera and selections while the additional globe
    // is active, without running two animated renderers behind one another.
    const suspend = (event: Event) => {
      suspendedRef.current = Boolean((event as CustomEvent<boolean>).detail);
      setSuspended(suspendedRef.current);
    };
    window.addEventListener("portwatch:intelligence-globe", suspend);
    return () =>
      window.removeEventListener("portwatch:intelligence-globe", suspend);
  }, []);
  const [failed, setFailed] = useState<string | null>(null);
  const [hovered, setHovered] = useState<{
    id: string;
    x: number;
    y: number;
  } | null>(null);
  const [overlayState, setOverlayState] = useState<Overlay>(EMPTY_OVERLAY);

  const { clock, fixesAt, colorByType } = useTraffic();
  const hoveredRef = useRef<string | null>(null);
  hoveredRef.current = hovered?.id ?? null;

  /* Props the animation loop reads. Refs, so changing a filter never restarts
     the loop and never drops a frame. */
  const trafficOn = layers.traffic !== false;
  const portsOn = layers.ports !== false;
  const trafficSettings = useMemo(
    () => ({
      vesselFilter,
      focusIds,
      pinnedIds,
      selectedVesselId,
      showVectors,
      forceVesselLabels,
      maxVesselLabels,
      labels,
      colorByType,
      trafficOn,
      portsOn,
      portIds,
    }),
    [
      vesselFilter,
      focusIds,
      pinnedIds,
      selectedVesselId,
      showVectors,
      forceVesselLabels,
      maxVesselLabels,
      labels,
      colorByType,
      trafficOn,
      portsOn,
      portIds,
    ],
  );
  const settings = useRef(trafficSettings);
  settings.current = trafficSettings;

  const handlers = useRef({
    onSelectVessel: onSelectVessel ?? setMapSelection,
    onSelectObserved,
    onHoverVessel,
    onSelectPort,
    onZoomChange,
  });
  handlers.current = {
    onSelectVessel: onSelectVessel ?? setMapSelection,
    onSelectObserved,
    onHoverVessel,
    onSelectPort,
    onZoomChange,
  };

  /* ------------------------------------------------------------- create -- */
  useEffect(() => {
    let alive = true;
    let instance: MapLibreMap | null = null;

    void loadChart()
      .then(({ Map }) => {
        if (!alive || !containerRef.current) return;
        instance = new Map({
          container: containerRef.current,
          style: buildStyle(),
          center: view?.center ?? INDIA_VIEW.center,
          zoom: view?.zoom ?? INDIA_VIEW.zoom,
          ...CHAPTER_CAMERA,
          minZoom,
          maxZoom,
          maxBounds: REGION_BOUNDS,
          attributionControl: false,
          dragRotate: false,
          pitchWithRotate: false,
          fadeDuration: 0,
          renderWorldCopies: false,
        });
        instance.touchZoomRotate.disableRotation();
        instance.keyboard.enable();
        mapRef.current = instance;
        // The browser suite drives the live GL map through this handle.
        (window as unknown as { __portwatchMap?: MapLibreMap }).__portwatchMap =
          instance;

        instance.on("load", () => {
          if (!alive || !instance) return;
          publish("corridors", corridorFeatures());
          for (const icon of buildVesselIcons()) {
            if (!instance.hasImage(icon.id)) {
              instance.addImage(icon.id, icon.data, {
                pixelRatio: icon.pixelRatio,
              });
            }
          }
          setReady(true);
          setMap(instance);
          handlers.current.onZoomChange?.(instance.getZoom());
        });

        instance.on("zoomend", () => {
          if (instance) handlers.current.onZoomChange?.(instance.getZoom());
        });

        instance.on("error", (event) => {
          console.warn("[map]", event.error?.message ?? event);
        });

        /* --------------------------------------------------- interaction -- */
        const pickable = [
          "observed-mark",
          "vessel-mark",
          "cluster-mark",
          "port-mark",
          "port-core",
        ];

        instance.on("mousemove", (event: MapMouseEvent) => {
          if (!instance) return;
          const features = instance.queryRenderedFeatures(event.point, {
            layers: pickable,
          });
          const top = features[0];
          const id = top?.properties?.id;
          if (top?.layer.id === "vessel-mark" && typeof id === "string") {
            instance.getCanvas().style.cursor = "pointer";
            setHovered({ id, x: event.point.x, y: event.point.y });
            handlers.current.onHoverVessel?.(id);
            return;
          }
          instance.getCanvas().style.cursor = top ? "pointer" : "";
          setHovered(null);
          handlers.current.onHoverVessel?.(null);
        });

        instance.on("mouseout", () => {
          setHovered(null);
          handlers.current.onHoverVessel?.(null);
        });

        instance.on("click", (event: MapMouseEvent) => {
          if (!instance) return;
          const features = instance.queryRenderedFeatures(event.point, {
            layers: pickable,
          });
          const top =
            features.find((feature) => feature.layer.id === "port-core") ??
            features[0];
          if (!top) {
            handlers.current.onSelectVessel?.(null);
            handlers.current.onSelectObserved?.(null);
            return;
          }
          const id = top.properties?.id;
          const center = (top.geometry as GeoJSON.Point).coordinates as [
            number,
            number,
          ];
          if (top.layer.id === "observed-mark" && typeof id === "string") {
            handlers.current.onSelectObserved?.(id);
            handlers.current.onSelectVessel?.(null);
            glideTo(instance, center, Math.max(instance.getZoom(), 8));
            return;
          }
          if (top.layer.id === "vessel-mark" && typeof id === "string") {
            cameraSelection.current.vessel = id;
            handlers.current.onSelectVessel?.(id);
            handlers.current.onSelectObserved?.(null);
            glideTo(instance, center, Math.max(instance.getZoom(), 8));
            return;
          }
          if (top.layer.id === "cluster-mark") {
            glideTo(instance, center, instance.getZoom() + 2.2);
            return;
          }
          const code = top.properties?.code;
          if (typeof code === "string") {
            cameraSelection.current.port = code;
            handlers.current.onSelectPort?.(code);
            glideTo(instance, center, Math.max(instance.getZoom(), 11.5));
          }
        });
      })
      .catch((error: unknown) => {
        if (!alive) return;
        setFailed(
          error instanceof Error ? error.message : "MapLibre failed to load",
        );
      });

    return () => {
      alive = false;
      instance?.remove();
      mapRef.current = null;
      sent.current = {};
      setMap(null);
    };
    // Created once: view changes go through the imperative effects below rather
    // than tearing the GL context down.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* -------------------------------------------------------------- sizing -- */
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return undefined;
    const observer = new ResizeObserver(() => mapRef.current?.resize());
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  /* ---------------------------------------------------------- static data -- */
  useEffect(() => {
    const instance = mapRef.current;
    if (!instance || !ready) return;
    for (const key of RUNTIME_KEYS) {
      const features = data?.[key] ?? EMPTY;
      if (sent.current[key] === features) continue;
      const source = instance.getSource(key) as
        { setData: (value: GeoJSON.FeatureCollection) => void } | undefined;
      if (!source) continue;
      source.setData(publish(key, features));
      sent.current[key] = features;
    }
  }, [data, ready]);

  /* ------------------------------------------------------ weather raster -- */
  useEffect(() => {
    const instance = mapRef.current;
    if (!instance || !ready) return;
    const source = instance.getSource("wxraster") as
      | {
          updateImage: (options: {
            url: string;
            coordinates: number[][];
          }) => void;
        }
      | undefined;
    if (!source) return;
    if (weatherRaster) {
      source.updateImage({
        url: weatherRaster.url,
        coordinates: weatherRaster.coordinates,
      });
    } else {
      source.updateImage({
        url: BLANK_IMAGE,
        coordinates: [
          [60, 30],
          [61, 30],
          [61, 29],
          [60, 29],
        ],
      });
    }
  }, [ready, weatherRaster]);

  /* -------------------------------------------------------- layer toggles -- */
  useEffect(() => {
    const instance = mapRef.current;
    if (!instance || !ready) return;
    for (const [group, ids] of Object.entries(LAYER_GROUPS)) {
      const on = layers[group as LayerKey] ?? false;
      for (const id of ids) {
        if (instance.getLayer(id)) {
          instance.setLayoutProperty(id, "visibility", on ? "visible" : "none");
        }
      }
    }
  }, [layers, ready]);

  /* ----------------------------------------------------------------- view -- */
  useEffect(() => {
    const instance = mapRef.current;
    if (!instance || !ready || !view) return;
    const center = instance.getCenter();
    const padding = instance.getPadding();
    if (
      Math.abs(center.lng - view.center[0]) < 0.000001 &&
      Math.abs(center.lat - view.center[1]) < 0.000001 &&
      instance.getZoom() === view.zoom &&
      !padding.top && !padding.right && !padding.bottom && !padding.left
    )
      return;
    instance.easeTo({
      center: view.center,
      zoom: view.zoom,
      padding: UNPADDED,
      duration: cameraDuration(520),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, view?.center[0], view?.center[1], view?.zoom]);

  useEffect(() => {
    const instance = mapRef.current;
    if (!instance || !ready || !focus) return;
    if (focus.bounds) {
      const box = instance.getContainer();
      const padding = focus.padding ?? {
        top: 40,
        bottom: 40,
        left: 40,
        right: 40,
      };
      // Padding wider than the chart itself would throw; a narrow pane frames
      // the box with what room it has.
      const fits =
        padding.left + padding.right < box.clientWidth - 80 &&
        padding.top + padding.bottom < box.clientHeight - 80;
      instance.fitBounds(focus.bounds, {
        ...chapterTransition(),
        padding: fits ? padding : 24,
        maxZoom: 7,
      });
      return;
    }
    if (!focus.center) return;
    const [lon, lat] = focus.center;
    const outside =
      lon < REGION_BOUNDS[0][0] ||
      lon > REGION_BOUNDS[1][0] ||
      lat < REGION_BOUNDS[0][1] ||
      lat > REGION_BOUNDS[1][1];
    // Explicit global asset selection may leave the original clipped theatre.
    // Reuse its chart and bundled Natural Earth context, not a generated route.
    instance.setMaxBounds(
      outside
        ? [
            [
              Math.max(-179, Math.min(REGION_BOUNDS[0][0], lon - 5)),
              Math.max(-80, Math.min(REGION_BOUNDS[0][1], lat - 5)),
            ],
            [
              Math.min(179, Math.max(REGION_BOUNDS[1][0], lon + 5)),
              Math.min(80, Math.max(REGION_BOUNDS[1][1], lat + 5)),
            ],
          ]
        : REGION_BOUNDS,
    );
    if (outside && !instance.getSource("global-land-context")) {
      instance.addSource("global-land-context", {
        type: "geojson",
        data: "/maps/world-countries.json",
      });
      instance.addLayer(
        {
          id: "global-land-context",
          type: "fill",
          source: "global-land-context",
          paint: { "fill-color": COLORS.land, "fill-opacity": 0.8 },
        },
        "land-fill",
      );
      instance.addLayer(
        {
          id: "global-coast-context",
          type: "line",
          source: "global-land-context",
          paint: { "line-color": COLORS.coast, "line-width": 1 },
        },
        "land-fill",
      );
    }
    for (const id of ["global-land-context", "global-coast-context"])
      if (instance.getLayer(id))
        instance.setLayoutProperty(
          id,
          "visibility",
          outside ? "visible" : "none",
        );
    glideTo(
      instance,
      focus.center,
      focus.zoom ?? Math.max(instance.getZoom(), 7),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.token, ready]);

  useEffect(() => {
    const previous = cameraSelection.current;
    cameraSelection.current = {
      port: selectedPortCode,
      vessel: selectedVesselId,
      focus: focus?.token,
    };
    if (!map || previous.focus !== focus?.token) return;
    if (selectedPortCode && selectedPortCode !== previous.port) {
      const port = registered.find(
        (candidate) => candidate.code === selectedPortCode,
      );
      if (port) glideTo(map, port.center, Math.max(map.getZoom(), 11.5));
    } else if (selectedVesselId && selectedVesselId !== previous.vessel) {
      const fix = fixesAt(clock.now()).find(
        (candidate) => candidate.id === selectedVesselId,
      );
      if (fix) glideTo(map, [fix.lon, fix.lat], Math.max(map.getZoom(), 8));
    }
  }, [
    clock,
    fixesAt,
    focus?.token,
    map,
    registered,
    selectedPortCode,
    selectedVesselId,
  ]);

  /* --------------------------------------------------------- traffic loop -- */
  useEffect(() => {
    const instance = mapRef.current;
    if (!instance || !ready) return undefined;

    let raf = 0;
    let lastWrite = 0;
    let lastOverlay = 0;
    let cameraVersion = 0;
    let paintedVersion = -1;
    let overlayDirty = true;
    let previousAt: number | undefined;
    let previousOffset: number | undefined;
    let previousHover: string | null | undefined;
    let previousSettings: typeof settings.current | undefined;
    let previousMiniature = miniatureRef.current;

    const sourceOf = (
      key:
        RuntimeSource | "vessels" | "clusters" | "vectors" | "ghosts" | "rings",
    ) =>
      instance.getSource(key) as
        { setData: (value: GeoJSON.FeatureCollection) => void } | undefined;

    const write = () => {
      const config = settings.current;
      const at = clock.now();
      const offset = clock.offsetHours();
      const hover = hoveredRef.current;
      if (
        previousAt === at &&
        previousOffset === offset &&
        previousHover === hover &&
        previousSettings === config &&
        paintedVersion === cameraVersion
      )
        return null;
      previousAt = at;
      previousOffset = offset;
      previousHover = hover;
      previousSettings = config;
      paintedVersion = cameraVersion;

      const zoom = instance.getZoom();
      const bounds = instance.getBounds();
      const center = instance.getCenter();
      const viewport = {
        zoom,
        west: bounds.getWest(),
        south: bounds.getSouth(),
        east: bounds.getEast(),
        north: bounds.getNorth(),
        lon: center.lng,
        lat: center.lat,
      };
      const options = {
        zoom,
        selectedId: config.selectedVesselId,
        hoveredId: hover,
        focus: config.focusIds,
        pinned: config.pinnedIds,
        vectors: config.showVectors,
        labels: config.forceVesselLabels,
        maxLabels: config.maxVesselLabels,
        colorByType: config.colorByType,
      };
      const trafficAt = (instant: number) => {
        const all = fixesAt(instant);
        const filtered = config.vesselFilter
          ? all.filter(config.vesselFilter)
          : all;
        return viewportTraffic(filtered, viewport, options);
      };
      const built = buildTrafficFeatures(
        config.trafficOn ? trafficAt(at) : [],
        options,
      );

      sourceOf("vessels")?.setData(
        publish(
          "vessels",
          config.trafficOn
            ? built.vessels
            : { type: "FeatureCollection", features: [] },
        ),
      );
      const portMarkers = config.portsOn
        ? config.labels
            .filter((label) => config.portIds.has(label.id))
            .map((label) => instance.project([label.lon, label.lat]))
        : [];
      const clusterMarks = built.clusterMarks.filter((cluster) => {
        const point = instance.project([cluster.lon, cluster.lat]);
        return !portMarkers.some(
          (port) => Math.hypot(port.x - point.x, port.y - point.y) < 18,
        );
      });
      const clusterIds = new Set(clusterMarks.map((cluster) => cluster.id));
      sourceOf("clusters")?.setData(
        publish("clusters", {
          type: "FeatureCollection",
          features: built.clusters.features.filter((feature) =>
            clusterIds.has(feature.properties?.id),
          ),
        }),
      );
      sourceOf("vectors")?.setData(publish("vectors", built.vectors));
      sourceOf("rings")?.setData(publish("rings", built.rings));

      const ghosts =
        config.trafficOn && offset > 0.01
          ? buildGhostFeatures(
              trafficAt(clock.forecastAt()),
              config.focusIds,
              config.colorByType,
            )
          : ({
              type: "FeatureCollection",
              features: [],
            } as GeoJSON.FeatureCollection);
      sourceOf("ghosts")?.setData(publish("ghosts", ghosts));

      return { ...built, clusterMarks };
    };

    let latest = write();

    const paintOverlay = () => {
      const project = (lon: number, lat: number) => {
        const point = instance.project([lon, lat]);
        return { x: point.x, y: point.y };
      };
      const frameW = instance.getContainer().clientWidth;
      const frameH = instance.getContainer().clientHeight;
      const inFrame = (p: { x: number; y: number }) =>
        p.x > 6 && p.y > 6 && p.x < frameW - 10 && p.y < frameH - 10;

      const currentZoom = instance.getZoom();
      const active =
        currentZoom >= SCHEMATIC_ZOOM ? miniatureRef.current : null;
      const boxes: Array<[number, number, number, number]> = [];
      const fits = (x: number, y: number, width: number, height = 13) => {
        const box: [number, number, number, number] = [
          x,
          y - height / 2,
          x + width,
          y + height / 2,
        ];
        for (const other of boxes) {
          if (
            box[0] < other[2] &&
            box[2] > other[0] &&
            box[1] < other[3] &&
            box[3] > other[1]
          ) {
            return false;
          }
        }
        boxes.push(box);
        return true;
      };

      const placedLabels: Overlay["labels"] = [];
      const markerPoints = [...settings.current.labels]
        .filter(
          (label) =>
            settings.current.portsOn && settings.current.portIds.has(label.id),
        )
        .map((label) => project(label.lon, label.lat))
        .filter(inFrame);
      for (const label of [...settings.current.labels].sort(
        (a, b) =>
          Number(b.id === active?.code) - Number(a.id === active?.code) ||
          Number(b.emphasis ?? false) - Number(a.emphasis ?? false),
      )) {
        const point = project(label.lon, label.lat);
        if (!inFrame(point)) continue;
        const portLabel = settings.current.portIds.has(label.id);
        if (portLabel && !settings.current.portsOn) continue;
        const isSchematic = active?.code === label.id;
        const width =
          14 +
          label.text.length * 6.2 +
          (label.sub?.length ?? 0) * 5.2 +
          (isSchematic ? 65 : 0);
        let x =
          point.x + 12 + width < frameW ? point.x + 12 : point.x - width - 12;
        let y = point.y - 11;
        if (isSchematic) {
          const inland = instance.project(schematicAnchor(active, currentZoom));
          const dx = inland.x - point.x;
          const dy = inland.y - point.y;
          // Put the label on the seaward side of the pin in screen space.
          const seawardX = dx >= 0 ? point.x - width - 14 : point.x + 14;
          if (
            Math.abs(dx) >= 0.6 * Math.abs(dy) &&
            seawardX >= 6 &&
            seawardX + width <= frameW - 6
          ) {
            x = seawardX;
          } else {
            x = Math.max(6, Math.min(frameW - width - 6, point.x - width / 2));
            y = point.y + (dy >= 0 ? -22 : 22);
          }
        }
        if (x < 6 || x + width > frameW - 6 || !fits(x, y, width)) continue;
        placedLabels.push({ label, x, y });
      }

      // No traffic, no traffic names: a chart whose hulls are hidden must not
      // keep naming them.
      const placedVessels: Overlay["vessels"] = [];
      for (const label of settings.current.trafficOn
        ? (latest?.labels ?? [])
        : []) {
        const point = project(label.lon, label.lat);
        if (!inFrame(point)) continue;
        const width = 12 + label.text.length * 5.6;
        if (!label.emphasis && !fits(point.x + 9, point.y - 9, width, 12))
          continue;
        placedVessels.push({ label, x: point.x, y: point.y });
      }

      const placedClusters: Overlay["clusters"] = [];
      for (const mark of settings.current.trafficOn && currentZoom >= 4
        ? (latest?.clusterMarks ?? [])
        : []) {
        const point = project(mark.lon, mark.lat);
        if (!inFrame(point)) continue;
        const width = 6 + String(mark.count).length * 7;
        const y = [point.y, point.y - 13, point.y + 13].find(
          (top) =>
            inFrame({ x: point.x, y: top }) &&
            fits(point.x - width / 2, top, width) &&
            !markerPoints.some((port) => Math.hypot(port.x - point.x, port.y - top) < 18),
        );
        if (y !== undefined) placedClusters.push({ mark, x: point.x, y });
      }

      const seas = SEA_LABELS.filter((sea) => currentZoom >= sea.minZoom)
        .map((sea) => ({ sea, point: project(sea.lon, sea.lat) }))
        .filter(({ point }) => inFrame(point))
        .map(({ sea, point }) => ({
          id: sea.id,
          name: sea.name,
          x: point.x,
          y: point.y,
        }));

      setOverlayState({
        labels: placedLabels,
        seas,
        vessels: placedVessels,
        clusters: placedClusters,
      });
    };

    const loop = (time: number) => {
      if (document.hidden) return;
      raf = requestAnimationFrame(loop);
      if (suspendedRef.current) return;
      if (previousMiniature !== miniatureRef.current) {
        previousMiniature = miniatureRef.current;
        overlayDirty = true;
      }
      // Fifteen hertz for geometry: smooth at any replay rate, and an order of
      // magnitude cheaper than writing a GeoJSON source every frame.
      if (time - lastWrite >= (instance.isMoving() ? 100 : 66)) {
        lastWrite = time;
        const changed = write();
        if (changed) {
          latest = changed;
          overlayDirty = true;
        }
      }
      if (overlayDirty && time - lastOverlay >= 140) {
        lastOverlay = time;
        overlayDirty = false;
        paintOverlay();
      }
    };

    const invalidate = () => {
      cameraVersion += 1;
      overlayDirty = true;
    };
    const syncVisibility = () => {
      cancelAnimationFrame(raf);
      if (document.hidden) {
        instance.stop();
        return;
      }
      invalidate();
      raf = requestAnimationFrame(loop);
    };
    document.addEventListener("visibilitychange", syncVisibility);
    syncVisibility();
    const motion = window.matchMedia(REDUCED_MOTION);
    const stopMotion = () => {
      if (motion.matches) instance.stop();
    };
    instance.on("move", invalidate);
    instance.on("resize", invalidate);
    motion.addEventListener("change", stopMotion);

    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", syncVisibility);
      instance.off("move", invalidate);
      instance.off("resize", invalidate);
      motion.removeEventListener("change", stopMotion);
    };
  }, [clock, fixesAt, ready]);

  const hoverFix = useMemo(() => {
    if (!hovered) return null;
    const at = clock.now();
    return fixesAt(at).find((fix) => fix.id === hovered.id) ?? null;
    // The hover card is re-derived whenever the pointer moves, which is often
    // enough for a card that shows speed to a tenth of a knot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hovered?.id, hovered?.x, hovered?.y]);

  const zoomBy = useCallback((factor: number) => {
    const instance = mapRef.current;
    if (!instance) return;
    instance.easeTo({
      zoom: instance.getZoom() + factor,
      duration: cameraDuration(220),
    });
  }, []);

  return (
    <div
      className={cn(
        "relative h-full w-full overflow-hidden bg-[var(--sea)]",
        className,
      )}
    >
      <div ref={containerRef} className="pw-map h-full w-full" />

      <WindLayer
        map={map}
        frame={windFrame ?? null}
        enabled={showWind && ready && !suspended}
      />

      {/* Chart text: the product's typography, positioned from the projection. */}
      <div className="pointer-events-none absolute inset-0 z-10 overflow-hidden">
        {overlayState.seas.map((sea) => (
          <span
            key={sea.id}
            className="absolute -translate-x-1/2 -translate-y-1/2 whitespace-nowrap text-[10.5px] font-medium uppercase tracking-[0.26em] text-[var(--text-2)]"
            style={{ left: sea.x, top: sea.y }}
          >
            {sea.name}
          </span>
        ))}

        {overlayState.vessels.map(({ label, x, y }) => (
          <span
            key={label.id}
            className={cn(
              "absolute whitespace-nowrap text-[10.5px] leading-none",
              label.emphasis
                ? "font-semibold text-[var(--signal-ink)]"
                : "font-medium text-[var(--text)]",
            )}
            style={{
              left: x + 9,
              top: y - 9,
              textShadow:
                "0 0 3px var(--panel), 0 0 6px var(--panel), 1px 1px 0 var(--panel)",
            }}
          >
            {label.text}
            {label.sub ? (
              <span className="num ml-1 text-[10px] text-[var(--text-2)]">
                {label.sub}
              </span>
            ) : null}
          </span>
        ))}

        {overlayState.clusters.map(({ mark, x, y }) => (
          <span
            key={mark.id}
            data-map-cluster-count
            className="num absolute -translate-x-1/2 -translate-y-1/2 text-[10.5px] font-semibold text-[var(--text)]"
            style={{ left: x, top: y }}
          >
            {mark.count}
          </span>
        ))}

        {overlayState.labels.map(({ label, x, y }) => (
          <button
            key={label.id}
            data-map-port-label
            type="button"
            onClick={() => {
              const port = registered.find(
                (candidate) => candidate.code === label.id,
              );
              if (map && port) {
                cameraSelection.current.port = port.code;
                glideTo(map, port.center, Math.max(map.getZoom(), 11.5));
              }
              onSelectPort?.(label.id);
            }}
            className={cn(
              "pointer-events-auto absolute -translate-y-1/2 whitespace-nowrap px-1 text-left leading-tight",
              "tracking-[0.02em] transition-colors",
              label.muted
                ? "text-[10.5px] font-normal uppercase"
                : "text-[10.5px]",
              label.emphasis
                ? "font-semibold"
                : label.muted
                  ? ""
                  : "font-medium",
            )}
            style={{
              left: x,
              top: y,
              color: label.muted
                ? (label.color ?? "var(--text-3)")
                : label.emphasis
                  ? (label.color ?? "var(--text)")
                  : "var(--text-2)",
              textShadow:
                "0 0 3px var(--panel), 0 0 6px var(--panel), 1px 1px 0 var(--panel), -1px -1px 0 var(--panel)",
            }}
          >
            {label.text}
            {miniature?.code === label.id ? (
              <span
                data-testid="port-miniature-label"
                className="num ml-1 text-[10px] text-[var(--text-3)]"
              >
                · schematic
              </span>
            ) : null}
            {label.sub ? (
              <span className="num ml-1 text-[10.5px] text-[var(--text-3)]">
                {label.sub}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {hovered && hoverFix && renderHoverCard ? (
        <div
          className="pointer-events-none absolute z-30 w-[230px] rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)]/97 p-2 shadow-[0_10px_28px_rgba(0,0,0,0.6)]"
          style={{
            left: Math.min(
              hovered.x + 16,
              (containerRef.current?.clientWidth ?? 900) - 244,
            ),
            top: Math.max(
              8,
              Math.min(
                hovered.y - 10,
                (containerRef.current?.clientHeight ?? 600) - 168,
              ),
            ),
          }}
        >
          {renderHoverCard(hoverFix)}
        </div>
      ) : null}

      <div className="absolute right-2.5 top-2.5 z-20 flex flex-col overflow-hidden rounded-[2px] border border-[var(--line-strong)] bg-[var(--panel)]/92">
        {[
          { label: "+", title: "Zoom in", action: () => zoomBy(0.8) },
          { label: "−", title: "Zoom out", action: () => zoomBy(-0.8) },
        ].map((control) => (
          <button
            key={control.title}
            type="button"
            title={control.title}
            aria-label={control.title}
            onClick={control.action}
            className="h-[22px] w-[22px] border-b border-[var(--line)] text-[13px] leading-none text-[var(--text-2)] last:border-0 hover:bg-[var(--panel-3)] hover:text-[var(--text)]"
          >
            {control.label}
          </button>
        ))}
        <button
          type="button"
          title="Reset view"
          aria-label="Reset view"
          onClick={() =>
            mapRef.current?.easeTo({
              center: view?.center ?? INDIA_VIEW.center,
              zoom: view?.zoom ?? INDIA_VIEW.zoom,
              padding: UNPADDED,
              duration: cameraDuration(520),
            })
          }
          className="grid h-[22px] w-[22px] place-items-center text-[var(--text-2)] hover:bg-[var(--panel-3)] hover:text-[var(--text)]"
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M2 6V2h4M14 10v4h-4M14 6V2h-4M2 10v4h4" />
          </svg>
        </button>
      </div>

      <MapPanelAccess>{overlay}</MapPanelAccess>
      <a
        className="pw-map-attribution"
        href="https://www.naturalearthdata.com/about/terms-of-use/"
        target="_blank"
        rel="noreferrer"
      >
        Basemap: Natural Earth · non-navigational
      </a>

      {!ready && !failed ? (
        <div className="absolute inset-0 grid place-items-center bg-[var(--sea)]">
          <span className="flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-[var(--text-3)]">
            <span
              aria-hidden="true"
              className="h-1.5 w-8 rounded bg-[var(--line-strong)]"
            />
            {loadingLabel}
          </span>
        </div>
      ) : null}

      {failed ? (
        <div className="absolute inset-0 grid place-items-center bg-[var(--sea)] p-6 text-center">
          <div className="max-w-[380px]">
            <div className="mb-1 text-[12px] font-medium text-[var(--crit)]">
              Chart renderer unavailable
            </div>
            <p className="text-[11.5px] leading-relaxed text-[var(--text-3)]">
              {failed}. Tabular views on this screen are unaffected.
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export { INDIA_VIEW };
