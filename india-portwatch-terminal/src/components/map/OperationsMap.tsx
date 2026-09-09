/**
 * The operations map.
 *
 * MapLibre GL draws the geometry — coastline, weather field, corridors, port
 * and activity marks — because it gives real projection, real zoom and GPU
 * compositing of a dozen layers. Labels and tooltips are React overlays
 * positioned from the map's own projection, so they use the product's
 * typography instead of a glyph atlas, and so a hover card can show measured
 * values rather than a string baked into a tile.
 *
 * MapLibre is imported only in an effect: the module touches `window` at load,
 * and this app server-renders.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Map as MapLibreMap } from "maplibre-gl";

import "maplibre-gl/dist/maplibre-gl.css";

import { cn } from "@/lib/utils";
import { INDIA_VIEW, LAYER_GROUPS, REGION_BOUNDS, buildStyle, type LayerKey } from "./basemap";

export interface MapLayerData {
  ports?: GeoJSON.FeatureCollection;
  vessels?: GeoJSON.FeatureCollection;
  lanes?: GeoJSON.FeatureCollection;
  chokepoints?: GeoJSON.FeatureCollection;
  events?: GeoJSON.FeatureCollection;
  zones?: GeoJSON.FeatureCollection;
  wxfield?: GeoJSON.FeatureCollection;
  wxstations?: GeoJSON.FeatureCollection;
  storms?: GeoJSON.FeatureCollection;
}

export interface MapLabel {
  id: string;
  lon: number;
  lat: number;
  text: string;
  sub?: string;
  color?: string;
  emphasis?: boolean;
  /** Secondary furniture (chokepoints): smaller, tinted, never bold. */
  muted?: boolean;
}

export interface OperationsMapProps {
  data: MapLayerData;
  visible: Partial<Record<LayerKey, boolean>>;
  labels?: MapLabel[];
  center?: [number, number];
  zoom?: number;
  minZoom?: number;
  maxZoom?: number;
  selected?: string | null;
  onSelect?: (id: string) => void;
  hovered?: string | null;
  onHover?: (id: string | null) => void;
  renderTooltip?: (id: string) => ReactNode;
  /** Rendered above the canvas, inside the map frame. */
  overlay?: ReactNode;
  className?: string;
  /** Label shown while the GL context is being created. */
  loadingLabel?: string;
}

const SOURCE_KEYS: Array<keyof MapLayerData> = [
  "ports",
  "vessels",
  "lanes",
  "chokepoints",
  "events",
  "zones",
  "wxfield",
  "wxstations",
  "storms",
];

export function OperationsMap({
  data,
  visible,
  labels = [],
  center = INDIA_VIEW.center,
  zoom = INDIA_VIEW.zoom,
  minZoom = 2.4,
  maxZoom = 11,
  selected,
  onSelect,
  hovered,
  onHover,
  renderTooltip,
  overlay,
  className,
  loadingLabel = "Initialising chart",
}: OperationsMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [projection, setProjection] = useState(0);
  const onSelectRef = useRef(onSelect);
  const onHoverRef = useRef(onHover);
  onSelectRef.current = onSelect;
  onHoverRef.current = onHover;

  /* ------------------------------------------------------------- create -- */
  useEffect(() => {
    let alive = true;
    let map: MapLibreMap | null = null;

    void import("maplibre-gl")
      .then(({ Map }) => {
        if (!alive || !containerRef.current) return;
        map = new Map({
          container: containerRef.current,
          style: buildStyle(),
          center,
          zoom,
          minZoom,
          maxZoom,
          maxBounds: REGION_BOUNDS,
          attributionControl: false,
          dragRotate: false,
          pitchWithRotate: false,
          fadeDuration: 0,
          renderWorldCopies: false,
        });
        map.touchZoomRotate.disableRotation();
        if (import.meta.env.DEV) {
          // Dev affordance: the QA harness inspects the live GL map here.
          (window as unknown as { __portwatchMap?: MapLibreMap }).__portwatchMap = map;
        }
        map.keyboard.enable();
        mapRef.current = map;

        const bump = () => setProjection((n) => n + 1);
        map.on("move", bump);
        map.on("zoom", bump);
        map.on("resize", bump);

        map.on("load", () => {
          if (!alive) return;
          setReady(true);
          bump();
        });
        map.on("error", (event) => {
          // A style/source warning must not take the screen down; the panel
          // keeps rendering and the console carries the detail.
          console.warn("[map]", event.error?.message ?? event);
        });

        for (const layer of ["port-mark", "port-core", "chokepoint-mark", "vessel-mark"]) {
          map.on("mouseenter", layer, () => {
            if (map) map.getCanvas().style.cursor = "pointer";
          });
          map.on("mouseleave", layer, () => {
            if (map) map.getCanvas().style.cursor = "";
            onHoverRef.current?.(null);
          });
        }
        map.on("mousemove", "port-mark", (event) => {
          const code = event.features?.[0]?.properties?.code;
          if (typeof code === "string") onHoverRef.current?.(code);
        });
        map.on("click", "port-mark", (event) => {
          const code = event.features?.[0]?.properties?.code;
          if (typeof code === "string") onSelectRef.current?.(code);
        });
      })
      .catch((error: unknown) => {
        if (!alive) return;
        setFailed(error instanceof Error ? error.message : "MapLibre failed to load");
      });

    return () => {
      alive = false;
      map?.remove();
      mapRef.current = null;
    };
    // Intentionally created once: view changes go through the imperative
    // effects below rather than tearing the GL context down.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* -------------------------------------------------------------- sizing -- */
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return undefined;
    const observer = new ResizeObserver(() => {
      mapRef.current?.resize();
      setProjection((n) => n + 1);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  /* ---------------------------------------------------------------- data -- */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    for (const key of SOURCE_KEYS) {
      const source = map.getSource(key) as
        | { setData: (value: GeoJSON.FeatureCollection) => void }
        | undefined;
      if (!source) continue;
      source.setData(data[key] ?? { type: "FeatureCollection", features: [] });
    }
  }, [data, ready]);

  /* -------------------------------------------------------- layer toggles -- */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    for (const [group, ids] of Object.entries(LAYER_GROUPS)) {
      const on = visible[group as LayerKey] ?? false;
      for (const id of ids) {
        if (map.getLayer(id)) {
          map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
        }
      }
    }
  }, [ready, visible]);

  /* ---------------------------------------------------------------- view -- */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.easeTo({ center, zoom, duration: 420 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, center[0], center[1], zoom]);

  const project = useCallback(
    (lon: number, lat: number) => {
      const map = mapRef.current;
      if (!map) return null;
      const point = map.project([lon, lat]);
      return { x: point.x, y: point.y };
    },
    // `projection` is the invalidation signal for the overlay positions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projection],
  );

  /**
   * Greedy label de-collision. Two ports 15 km apart overlap at national zoom;
   * dropping the lower-priority label is better than printing both on top of
   * each other, and zooming in restores it.
   */
  const placed = useMemo(() => {
    const projected = labels
      .map((label) => {
        const point = project(label.lon, label.lat);
        return point ? { label, point } : null;
      })
      .filter((entry): entry is { label: MapLabel; point: { x: number; y: number } } => entry !== null)
      .sort((a, b) => Number(b.label.emphasis ?? false) - Number(a.label.emphasis ?? false));

    const frame = containerRef.current;
    const frameW = frame?.clientWidth ?? 0;
    const frameH = frame?.clientHeight ?? 0;

    const kept: Array<{ label: MapLabel; point: { x: number; y: number } }> = [];
    const boxes: Array<[number, number, number, number]> = [];
    for (const entry of projected) {
      // A mark panned off the edge would otherwise leave its label clipped
      // against the frame, reading as a truncated word rather than a place.
      if (
        frameW > 0 &&
        (entry.point.x < 4 ||
          entry.point.y < 4 ||
          entry.point.x > frameW - 12 ||
          entry.point.y > frameH - 4)
      ) {
        continue;
      }
      const width = 12 + entry.label.text.length * 6.2 + (entry.label.sub?.length ?? 0) * 5.4;
      const box: [number, number, number, number] = [
        entry.point.x + 7,
        entry.point.y - 7,
        entry.point.x + 7 + width,
        entry.point.y + 7,
      ];
      const clashes = boxes.some(
        ([x0, y0, x1, y1]) => box[0] < x1 && box[2] > x0 && box[1] < y1 && box[3] > y0,
      );
      if (clashes) continue;
      boxes.push(box);
      kept.push(entry);
    }
    return kept;
  }, [labels, project]);

  const tooltipFor = hovered ?? selected ?? null;
  const tooltipAnchor = tooltipFor
    ? placed.find((entry) => entry.label.id === tooltipFor)
    : undefined;

  const zoomBy = (factor: number) => {
    const map = mapRef.current;
    if (!map) return;
    map.easeTo({ zoom: map.getZoom() + factor, duration: 200 });
  };

  return (
    <div className={cn("relative h-full w-full overflow-hidden bg-[var(--sea-deep)]", className)}>
      {/* `maplibre-gl.css` forces `position: relative` on its container, which
          would defeat an absolutely-positioned box; size it directly instead. */}
      <div ref={containerRef} className="pw-map h-full w-full" />

      {/* Port labels ride above the canvas so they use the product's type. */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        {ready &&
          placed.map(({ label, point }) => (
            <button
              key={label.id}
              type="button"
              onClick={() => onSelect?.(label.id)}
              onMouseEnter={() => onHover?.(label.id)}
              onMouseLeave={() => onHover?.(null)}
              className={cn(
                "pointer-events-auto absolute -translate-y-1/2 whitespace-nowrap px-1 text-left",
                "leading-tight tracking-[0.02em] transition-colors",
                label.muted ? "text-[9.5px] font-normal uppercase" : "text-[10.5px]",
                label.emphasis ? "font-semibold" : label.muted ? "" : "font-medium",
              )}
              style={{
                left: point.x + 9,
                top: point.y,
                color: label.muted
                  ? (label.color ?? "var(--text-3)")
                  : label.emphasis
                    ? (label.color ?? "var(--text)")
                    : "var(--text-2)",
                textShadow:
                  "0 0 3px #04121b, 0 0 6px #04121b, 1px 1px 0 #04121b, -1px -1px 0 #04121b",
              }}
            >
              {label.text}
              {label.sub ? (
                <span className="num ml-1 text-[9.5px] text-[var(--text-3)]">{label.sub}</span>
              ) : null}
            </button>
          ))}
      </div>

      {tooltipAnchor && renderTooltip ? (
        <div
          className="pointer-events-none absolute z-30 w-[236px] rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)]/97 p-2 shadow-[0_8px_24px_rgba(0,0,0,0.55)]"
          style={{
            left: Math.min(
              tooltipAnchor.point.x + 14,
              (containerRef.current?.clientWidth ?? 900) - 248,
            ),
            top: Math.max(
              8,
              Math.min(
                tooltipAnchor.point.y - 12,
                (containerRef.current?.clientHeight ?? 600) - 190,
              ),
            ),
          }}
        >
          {renderTooltip(tooltipAnchor.label.id)}
        </div>
      ) : null}

      <div className="absolute right-2.5 top-2.5 z-20 flex flex-col overflow-hidden rounded-[2px] border border-[var(--line-strong)] bg-[var(--panel)]/92">
        {[
          { label: "+", title: "Zoom in", action: () => zoomBy(0.7) },
          { label: "−", title: "Zoom out", action: () => zoomBy(-0.7) },
        ].map((control) => (
          <button
            key={control.title}
            type="button"
            title={control.title}
            aria-label={control.title}
            onClick={control.action}
            className="h-6 w-6 border-b border-[var(--line)] text-[13px] leading-none text-[var(--text-2)] last:border-0 hover:bg-[var(--panel-3)] hover:text-[var(--text)]"
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
              center: INDIA_VIEW.center,
              zoom: INDIA_VIEW.zoom,
              duration: 500,
            })
          }
          className="grid h-6 w-6 place-items-center text-[var(--text-2)] hover:bg-[var(--panel-3)] hover:text-[var(--text)]"
        >
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
            <path d="M2 6V2h4M14 10v4h-4M14 6V2h-4M2 10v4h4" />
          </svg>
        </button>
      </div>

      {overlay}

      {!ready && !failed ? (
        <div className="absolute inset-0 grid place-items-center bg-[var(--sea-deep)]">
          <span className="flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-[var(--text-3)]">
            <span className="pw-breathe h-1.5 w-1.5 rounded-full bg-[var(--info)]" />
            {loadingLabel}
          </span>
        </div>
      ) : null}

      {failed ? (
        <div className="absolute inset-0 grid place-items-center bg-[var(--sea-deep)] p-6 text-center">
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
