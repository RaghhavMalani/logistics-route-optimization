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

import { useTraffic } from "@/components/app/traffic-context";
import type { VesselFix } from "@/lib/maritime/traffic-types";
import type { WeatherFrame } from "@/lib/maritime/weather-model";
import { cn } from "@/lib/utils";
import {
  BLANK_IMAGE,
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
  type ClusterMark,
  type VesselLabel,
} from "./traffic-layers";
import { corridorFeatures } from "@/lib/maritime/searoutes";
import { buildVesselIcons } from "./vessel-icons";
import type { WeatherRaster } from "./weather-layers";
import { WindLayer } from "./WindLayer";

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
  onHoverVessel?: (id: string | null) => void;
  selectedPortCode?: string | null;
  onSelectPort?: (code: string) => void;
  showVectors?: boolean;
  forceVesselLabels?: boolean;
  maxVesselLabels?: number;
  labels?: MapLabel[];
  view?: MapView;
  /** Bump `token` to fly somewhere without owning the camera. */
  focus?: { center: [number, number]; zoom?: number; token: number } | null;
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
];

interface Overlay {
  labels: Array<{ label: MapLabel; x: number; y: number }>;
  seas: Array<{ id: string; name: string; x: number; y: number }>;
  vessels: Array<{ label: VesselLabel; x: number; y: number }>;
  clusters: Array<{ mark: ClusterMark; x: number; y: number }>;
}

const EMPTY_OVERLAY: Overlay = { labels: [], seas: [], vessels: [], clusters: [] };

/**
 * The geometry the chart last wrote, exposed for the browser suite.
 *
 * The traffic layer has no DOM, so a test that counted markers would be testing
 * an implementation this product does not have. MapLibre's own source internals
 * are private and tile-clipped, so reading them back gives fragments rather than
 * passages. This is the same object the map just handed the GL context, which is
 * exactly what a test about "does the chart draw a route across land" needs.
 */
function publish(key: string, data: GeoJSON.FeatureCollection): GeoJSON.FeatureCollection {
  if (typeof window !== "undefined") {
    const registry = ((window as unknown as { __portwatchSources?: Record<string, unknown> })
      .__portwatchSources ??= {});
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
  selectedVesselId = null,
  onSelectVessel,
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
  maxZoom = 13,
  onZoomChange,
  loadingLabel = "Initialising chart",
}: MaritimeMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [hovered, setHovered] = useState<{ id: string; x: number; y: number } | null>(null);
  const [overlayState, setOverlayState] = useState<Overlay>(EMPTY_OVERLAY);

  const { clock, fixesAt } = useTraffic();
  const hoveredRef = useRef<string | null>(null);
  hoveredRef.current = hovered?.id ?? null;

  /* Props the animation loop reads. Refs, so changing a filter never restarts
     the loop and never drops a frame. */
  const settings = useRef({
    vesselFilter,
    focusIds,
    pinnedIds,
    selectedVesselId,
    showVectors,
    forceVesselLabels,
    maxVesselLabels,
    labels,
    trafficOn: layers.traffic !== false,
  });
  settings.current = {
    vesselFilter,
    focusIds,
    pinnedIds,
    selectedVesselId,
    showVectors,
    forceVesselLabels,
    maxVesselLabels,
    labels,
    trafficOn: layers.traffic !== false,
  };

  const handlers = useRef({ onSelectVessel, onHoverVessel, onSelectPort, onZoomChange });
  handlers.current = { onSelectVessel, onHoverVessel, onSelectPort, onZoomChange };

  /* ------------------------------------------------------------- create -- */
  useEffect(() => {
    let alive = true;
    let instance: MapLibreMap | null = null;

    void import("maplibre-gl")
      .then(({ Map }) => {
        if (!alive || !containerRef.current) return;
        instance = new Map({
          container: containerRef.current,
          style: buildStyle(),
          center: view?.center ?? INDIA_VIEW.center,
          zoom: view?.zoom ?? INDIA_VIEW.zoom,
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
        (window as unknown as { __portwatchMap?: MapLibreMap }).__portwatchMap = instance;

        instance.on("load", () => {
          if (!alive || !instance) return;
          publish("corridors", corridorFeatures());
          for (const icon of buildVesselIcons()) {
            if (!instance.hasImage(icon.id)) {
              instance.addImage(icon.id, icon.data, { pixelRatio: icon.pixelRatio });
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
        const pickable = ["vessel-mark", "cluster-mark", "port-mark", "port-core"];

        instance.on("mousemove", (event: MapMouseEvent) => {
          if (!instance) return;
          const features = instance.queryRenderedFeatures(event.point, { layers: pickable });
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
          const features = instance.queryRenderedFeatures(event.point, { layers: pickable });
          const top = features[0];
          if (!top) {
            handlers.current.onSelectVessel?.(null);
            return;
          }
          const id = top.properties?.id;
          if (top.layer.id === "vessel-mark" && typeof id === "string") {
            handlers.current.onSelectVessel?.(id);
            return;
          }
          if (top.layer.id === "cluster-mark") {
            instance.easeTo({
              center: (top.geometry as GeoJSON.Point).coordinates as [number, number],
              zoom: Math.min(maxZoom, instance.getZoom() + 2.2),
              duration: 420,
            });
            return;
          }
          const code = top.properties?.code;
          if (typeof code === "string") handlers.current.onSelectPort?.(code);
        });
      })
      .catch((error: unknown) => {
        if (!alive) return;
        setFailed(error instanceof Error ? error.message : "MapLibre failed to load");
      });

    return () => {
      alive = false;
      instance?.remove();
      mapRef.current = null;
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
      const source = instance.getSource(key) as
        | { setData: (value: GeoJSON.FeatureCollection) => void }
        | undefined;
      if (!source) continue;
      source.setData(publish(key, data?.[key] ?? { type: "FeatureCollection", features: [] }));
    }
  }, [data, ready]);

  /* ------------------------------------------------------ weather raster -- */
  useEffect(() => {
    const instance = mapRef.current;
    if (!instance || !ready) return;
    const source = instance.getSource("wxraster") as
      | {
          updateImage: (options: { url: string; coordinates: number[][] }) => void;
        }
      | undefined;
    if (!source) return;
    if (weatherRaster) {
      source.updateImage({ url: weatherRaster.url, coordinates: weatherRaster.coordinates });
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
    instance.easeTo({ center: view.center, zoom: view.zoom, duration: 520 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, view?.center[0], view?.center[1], view?.zoom]);

  useEffect(() => {
    const instance = mapRef.current;
    if (!instance || !ready || !focus) return;
    instance.flyTo({
      center: focus.center,
      zoom: focus.zoom ?? Math.max(instance.getZoom(), 7),
      duration: 900,
      essential: true,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.token, ready]);

  /* --------------------------------------------------------- traffic loop -- */
  useEffect(() => {
    const instance = mapRef.current;
    if (!instance || !ready) return undefined;

    let raf = 0;
    let lastWrite = 0;
    let lastOverlay = 0;

    const sourceOf = (key: RuntimeSource | "vessels" | "clusters" | "vectors" | "ghosts" | "rings") =>
      instance.getSource(key) as
        | { setData: (value: GeoJSON.FeatureCollection) => void }
        | undefined;

    const write = () => {
      const config = settings.current;
      const at = clock.now();
      const all = fixesAt(at);
      const visible = config.vesselFilter ? all.filter(config.vesselFilter) : all;

      const built = buildTrafficFeatures(visible, {
        zoom: instance.getZoom(),
        selectedId: config.selectedVesselId,
        hoveredId: hoveredRef.current,
        focus: config.focusIds,
        pinned: config.pinnedIds,
        vectors: config.showVectors,
        labels: config.forceVesselLabels,
        maxLabels: config.maxVesselLabels,
      });

      sourceOf("vessels")?.setData(
        publish(
          "vessels",
          config.trafficOn ? built.vessels : { type: "FeatureCollection", features: [] },
        ),
      );
      sourceOf("clusters")?.setData(publish("clusters", built.clusters));
      sourceOf("vectors")?.setData(publish("vectors", built.vectors));
      sourceOf("rings")?.setData(publish("rings", built.rings));

      const offset = clock.offsetHours();
      const ghosts =
        offset > 0.01
          ? buildGhostFeatures(
              config.vesselFilter
                ? fixesAt(clock.forecastAt()).filter(config.vesselFilter)
                : fixesAt(clock.forecastAt()),
              config.focusIds,
            )
          : ({ type: "FeatureCollection", features: [] } as GeoJSON.FeatureCollection);
      sourceOf("ghosts")?.setData(publish("ghosts", ghosts));

      return built;
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
      const boxes: Array<[number, number, number, number]> = [];
      const fits = (x: number, y: number, width: number, height = 13) => {
        const box: [number, number, number, number] = [x, y - height / 2, x + width, y + height / 2];
        for (const other of boxes) {
          if (box[0] < other[2] && box[2] > other[0] && box[1] < other[3] && box[3] > other[1]) {
            return false;
          }
        }
        boxes.push(box);
        return true;
      };

      const placedLabels: Overlay["labels"] = [];
      for (const label of [...settings.current.labels].sort(
        (a, b) => Number(b.emphasis ?? false) - Number(a.emphasis ?? false),
      )) {
        const point = project(label.lon, label.lat);
        if (!inFrame(point)) continue;
        const width = 14 + label.text.length * 6.2 + (label.sub?.length ?? 0) * 5.2;
        if (!fits(point.x + 8, point.y, width)) continue;
        placedLabels.push({ label, x: point.x, y: point.y });
      }

      const placedVessels: Overlay["vessels"] = [];
      for (const label of latest.labels) {
        const point = project(label.lon, label.lat);
        if (!inFrame(point)) continue;
        const width = 12 + label.text.length * 5.6;
        if (!label.emphasis && !fits(point.x + 9, point.y - 9, width, 12)) continue;
        placedVessels.push({ label, x: point.x, y: point.y });
      }

      const placedClusters: Overlay["clusters"] = [];
      for (const mark of latest.clusterMarks) {
        const point = project(mark.lon, mark.lat);
        if (!inFrame(point)) continue;
        placedClusters.push({ mark, x: point.x, y: point.y });
      }

      const seas = SEA_LABELS.filter((sea) => currentZoom >= sea.minZoom)
        .map((sea) => ({ sea, point: project(sea.lon, sea.lat) }))
        .filter(({ point }) => inFrame(point))
        .map(({ sea, point }) => ({ id: sea.id, name: sea.name, x: point.x, y: point.y }));

      setOverlayState({
        labels: placedLabels,
        seas,
        vessels: placedVessels,
        clusters: placedClusters,
      });
    };

    const loop = (time: number) => {
      raf = requestAnimationFrame(loop);
      // Fifteen hertz for geometry: smooth at any replay rate, and an order of
      // magnitude cheaper than writing a GeoJSON source every frame.
      if (time - lastWrite >= 66) {
        lastWrite = time;
        latest = write();
      }
      if (time - lastOverlay >= 140) {
        lastOverlay = time;
        paintOverlay();
      }
    };

    raf = requestAnimationFrame(loop);
    const invalidate = () => {
      lastOverlay = 0;
    };
    instance.on("move", invalidate);

    return () => {
      cancelAnimationFrame(raf);
      instance.off("move", invalidate);
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
    instance.easeTo({ zoom: instance.getZoom() + factor, duration: 220 });
  }, []);

  return (
    <div className={cn("relative h-full w-full overflow-hidden bg-[#061520]", className)}>
      <div ref={containerRef} className="pw-map h-full w-full" />

      <WindLayer map={map} frame={windFrame ?? null} enabled={showWind && ready} />

      {/* Chart text: the product's typography, positioned from the projection. */}
      <div className="pointer-events-none absolute inset-0 z-10 overflow-hidden">
        {overlayState.seas.map((sea) => (
          <span
            key={sea.id}
            className="absolute -translate-x-1/2 -translate-y-1/2 whitespace-nowrap text-[9.5px] font-medium uppercase tracking-[0.26em] text-[#33637d]"
            style={{ left: sea.x, top: sea.y }}
          >
            {sea.name}
          </span>
        ))}

        {overlayState.vessels.map(({ label, x, y }) => (
          <span
            key={label.id}
            className={cn(
              "absolute whitespace-nowrap text-[9.5px] leading-none",
              label.emphasis ? "font-semibold text-[#eaf3f9]" : "font-medium text-[#a9c2d2]",
            )}
            style={{
              left: x + 9,
              top: y - 9,
              textShadow: "0 0 3px #04121b, 0 0 6px #04121b, 1px 1px 0 #04121b",
            }}
          >
            {label.text}
            {label.sub ? (
              <span className="num ml-1 text-[8.5px] text-[#7d97a8]">{label.sub}</span>
            ) : null}
          </span>
        ))}

        {overlayState.clusters.map(({ mark, x, y }) => (
          <span
            key={mark.id}
            className="num absolute -translate-x-1/2 -translate-y-1/2 text-[9.5px] font-semibold text-[#bcd6e5]"
            style={{ left: x, top: y }}
          >
            {mark.count}
          </span>
        ))}

        {overlayState.labels.map(({ label, x, y }) => (
          <button
            key={label.id}
            type="button"
            onClick={() => onSelectPort?.(label.id)}
            className={cn(
              "pointer-events-auto absolute -translate-y-1/2 whitespace-nowrap px-1 text-left leading-tight",
              "tracking-[0.02em] transition-colors",
              label.muted ? "text-[9.5px] font-normal uppercase" : "text-[10.5px]",
              label.emphasis ? "font-semibold" : label.muted ? "" : "font-medium",
            )}
            style={{
              left: x + 9,
              top: y,
              color: label.muted
                ? (label.color ?? "var(--text-3)")
                : label.emphasis
                  ? (label.color ?? "var(--text)")
                  : "var(--text-2)",
              textShadow: "0 0 3px #04121b, 0 0 6px #04121b, 1px 1px 0 #04121b, -1px -1px 0 #04121b",
            }}
          >
            {label.text}
            {label.sub ? (
              <span className="num ml-1 text-[9.5px] text-[var(--text-3)]">{label.sub}</span>
            ) : null}
          </button>
        ))}
      </div>

      {hovered && hoverFix && renderHoverCard ? (
        <div
          className="pointer-events-none absolute z-30 w-[230px] rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)]/97 p-2 shadow-[0_10px_28px_rgba(0,0,0,0.6)]"
          style={{
            left: Math.min(hovered.x + 16, (containerRef.current?.clientWidth ?? 900) - 244),
            top: Math.max(8, Math.min(hovered.y - 10, (containerRef.current?.clientHeight ?? 600) - 168)),
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
              duration: 520,
            })
          }
          className="grid h-[22px] w-[22px] place-items-center text-[var(--text-2)] hover:bg-[var(--panel-3)] hover:text-[var(--text)]"
        >
          <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M2 6V2h4M14 10v4h-4M14 6V2h-4M2 10v4h4" />
          </svg>
        </button>
      </div>

      {overlay}

      {!ready && !failed ? (
        <div className="absolute inset-0 grid place-items-center bg-[#061520]">
          <span className="flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-[var(--text-3)]">
            <span className="pw-breathe h-1.5 w-1.5 rounded-full bg-[var(--info)]" />
            {loadingLabel}
          </span>
        </div>
      ) : null}

      {failed ? (
        <div className="absolute inset-0 grid place-items-center bg-[#061520] p-6 text-center">
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
