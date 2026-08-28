import { useCallback, useEffect, useRef, useState } from "react";
import type {
  CSSProperties,
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
} from "react";
import blackMarbleWorldUrl from "@/assets/nasa-black-marble-world.jpg";
import type { PortOperationalSnapshot } from "@/services/portService";
import type {
  Chokepoint,
  ChokepointRoute,
  SARSignal,
  VesselProxy,
  WeatherSignal,
} from "@/types/portwatch";

interface MapAlert {
  id: string;
  portCode: string;
  severity: string;
  text: string;
  ts: string;
}

interface ViewTransform {
  x: number;
  y: number;
  scale: number;
  baseSize: number;
}

interface DragState {
  pointerId: number;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
}

const INDIA_CENTER: [number, number] = [78.9, 20.6];
const INITIAL_SCALE = 1.68;
const MIN_SCALE = 0.72;
const MAX_SCALE = 5.4;
const MERCATOR_LAT_LIMIT = 85.05112878;
const EMPTY_VIEW: ViewTransform = { x: 0, y: 0, scale: INITIAL_SCALE, baseSize: 1 };

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function lonLatToMercatorPoint(
  [longitude, latitude]: [number, number],
  size: number,
) {
  const constrainedLat = clamp(latitude, -MERCATOR_LAT_LIMIT, MERCATOR_LAT_LIMIT);
  const latRad = (constrainedLat * Math.PI) / 180;

  return {
    x: ((longitude + 180) / 360) * size,
    y:
      ((1 -
        Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) /
        2) *
      size,
  };
}

function getBaseSize(width: number, height: number) {
  return Math.max(width, height) * 1.65;
}

function keepImageInReach(
  transform: ViewTransform,
  width: number,
  height: number,
): ViewTransform {
  const visibleMargin = 96;
  const imageSize = transform.baseSize * transform.scale;
  const minX = visibleMargin - imageSize;
  const maxX = width - visibleMargin;
  const minY = visibleMargin - imageSize;
  const maxY = height - visibleMargin;

  return {
    ...transform,
    x: clamp(transform.x, minX, maxX),
    y: clamp(transform.y, minY, maxY),
  };
}

function getIndiaView(width: number, height: number): ViewTransform {
  const baseSize = getBaseSize(width, height);
  const indiaPoint = lonLatToMercatorPoint(INDIA_CENTER, baseSize);

  return keepImageInReach(
    {
      baseSize,
      scale: INITIAL_SCALE,
      x: width / 2 - indiaPoint.x * INITIAL_SCALE,
      y: height / 2 - indiaPoint.y * INITIAL_SCALE,
    },
    width,
    height,
  );
}

export function MaritimeMap(props: {
  ports: PortOperationalSnapshot[];
  vessels: VesselProxy[];
  chokepoints: Chokepoint[];
  routes: ChokepointRoute[];
  alerts: readonly MapAlert[];
  weatherSignals: WeatherSignal[];
  sarSignals: SARSignal[];
  onPortSelect: (portCode: string) => void;
}) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const hasInteractedRef = useRef(false);
  const [view, setView] = useState<ViewTransform>(EMPTY_VIEW);

  const getViewportSize = useCallback(() => {
    const rect = viewportRef.current?.getBoundingClientRect();
    return {
      width: rect?.width ?? 0,
      height: rect?.height ?? 0,
    };
  }, []);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return undefined;

    const updateSize = () => {
      const { width, height } = getViewportSize();
      if (!width || !height) return;

      setView((current) => {
        if (!hasInteractedRef.current || current.baseSize <= 1) {
          return getIndiaView(width, height);
        }

        const nextBaseSize = getBaseSize(width, height);
        const ratio = nextBaseSize / current.baseSize;
        return keepImageInReach(
          {
            ...current,
            baseSize: nextBaseSize,
            x: current.x * ratio,
            y: current.y * ratio,
          },
          width,
          height,
        );
      });
    };

    updateSize();
    const resizeObserver = new ResizeObserver(updateSize);
    resizeObserver.observe(viewport);

    return () => resizeObserver.disconnect();
  }, [getViewportSize]);

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;

    hasInteractedRef.current = true;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: view.x,
      originY: view.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    const { width, height } = getViewportSize();
    setView((current) =>
      keepImageInReach(
        {
          ...current,
          x: drag.originX + event.clientX - drag.startX,
          y: drag.originY + event.clientY - drag.startY,
        },
        width,
        height,
      ),
    );
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null;
    }

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const handleWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    hasInteractedRef.current = true;

    const viewport = viewportRef.current;
    if (!viewport) return;

    const rect = viewport.getBoundingClientRect();
    const cursorX = event.clientX - rect.left;
    const cursorY = event.clientY - rect.top;
    const zoomFactor = Math.exp(-event.deltaY * 0.0012);

    setView((current) => {
      const nextScale = clamp(current.scale * zoomFactor, MIN_SCALE, MAX_SCALE);
      const worldX = (cursorX - current.x) / current.scale;
      const worldY = (cursorY - current.y) / current.scale;

      return keepImageInReach(
        {
          ...current,
          scale: nextScale,
          x: cursorX - worldX * nextScale,
          y: cursorY - worldY * nextScale,
        },
        rect.width,
        rect.height,
      );
    });
  };

  const zoomAroundPoint = (factor: number, cx: number, cy: number) => {
    setView((current) => {
      const nextScale = clamp(current.scale * factor, MIN_SCALE, MAX_SCALE);
      const worldX = (cx - current.x) / current.scale;
      const worldY = (cy - current.y) / current.scale;

      return keepImageInReach(
        {
          ...current,
          scale: nextScale,
          x: cx - worldX * nextScale,
          y: cy - worldY * nextScale,
        },
        viewportRef.current?.getBoundingClientRect().width ?? 0,
        viewportRef.current?.getBoundingClientRect().height ?? 0,
      );
    });
  };

  const zoomIn = () => {
    const rect = viewportRef.current?.getBoundingClientRect();
    if (!rect) return;
    zoomAroundPoint(1.2, rect.width / 2, rect.height / 2);
  };

  const zoomOut = () => {
    const rect = viewportRef.current?.getBoundingClientRect();
    if (!rect) return;
    zoomAroundPoint(1 / 1.2, rect.width / 2, rect.height / 2);
  };

  const resetToIndia = () => {
    const { width, height } = getViewportSize();
    if (!width || !height) return;
    hasInteractedRef.current = false;
    setView(getIndiaView(width, height));
  };

  const imageStyle: CSSProperties = {
    width: view.baseSize,
    height: view.baseSize,
    maxWidth: "none",
    maxHeight: "none",
    objectFit: "fill",
    transform: `translate3d(${view.x}px, ${view.y}px, 0) scale(${view.scale})`,
    transformOrigin: "0 0",
    filter: "brightness(1.42) contrast(1.28) saturate(1.08)",
  };

  return (
    <div
      ref={viewportRef}
      aria-label="NASA Black Marble world image map"
      className="absolute inset-0 overflow-hidden bg-black"
      role="application"
      onDoubleClick={resetToIndia}
      onPointerCancel={handlePointerUp}
      onPointerDown={handlePointerDown}
      onPointerLeave={handlePointerUp}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onWheel={handleWheel}
      style={{ cursor: dragRef.current ? "grabbing" : "grab", touchAction: "none" }}
    >
      <img
        src={blackMarbleWorldUrl}
        alt=""
        className="absolute left-0 top-0 max-w-none select-none will-change-transform"
        draggable={false}
        style={imageStyle}
      />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,transparent_55%,oklch(0_0_0/0.28)_100%)]" />
      {/* Port markers (positioned in world coordinates so they follow pans/zoom) */}
      {/* Only show the main Indian ports the project focuses on */}
      {(() => {
        const target = [
          "Mumbai",
          "JNPT",
          "Kandla",
          "Mormugao",
          "New Mangalore",
          "Kochi",
          "Tuticorin",
          "Chennai",
          "Ennore",
          "Visakhapatnam",
          "Paradip",
          "Kolkata",
          "Haldia",
          "Port Blair",
          "Dhamra",
          "Krishnapatnam",
          "Hazira",
          "Mundra",
        ].map((s) => s.toLowerCase().replace(/[_\s]+/g, " "));

        function norm(s: string) {
          return s.toLowerCase().replace(/[_\s]+/g, " ");
        }

        return props.ports
          .filter((port) => {
            const n = norm(port.name);
            const short = norm(port.short ?? "");
            return (
              target.some((t) => n.includes(t) || short.includes(t) || port.code.toLowerCase().includes(t.replace(/ /g, "")))
            );
          })
          .map((port) => {
        const pt = lonLatToMercatorPoint([port.location.lon, port.location.lat], view.baseSize);
        const left = view.x + pt.x * view.scale;
        const top = view.y + pt.y * view.scale;
        const markerStyle: CSSProperties = {
          position: "absolute",
          left: 0,
          top: 0,
          transform: `translate3d(${left}px, ${top}px, 0)`,
          transformOrigin: "0 0",
          pointerEvents: "auto",
        };

        return (
          <div key={port.code} style={markerStyle} className="group pointer-events-auto">
            <button
              title={port.name}
              onClick={() => props.onPortSelect(port.code)}
              className="rounded-full bg-[var(--color-red)] border border-white/10 shadow-sm twinkle"
              style={{ width: 6, height: 6 }}
            />
            <span className="marker-tooltip absolute left-3 -top-1 opacity-0 pointer-events-none transition-opacity duration-150 group-hover:opacity-100">
              {port.name}
            </span>
          </div>
        );
      });
    })()
      }

      {/* Zoom controls */}
      <div className="absolute right-3 top-3 z-20 flex flex-col gap-2">
        <button
          aria-label="Zoom in"
          onClick={zoomIn}
          className="w-8 h-8 rounded bg-[oklch(0.12_0.02_240)]/80 flex items-center justify-center text-[var(--color-foreground)] border border-[var(--color-line)]"
        >
          +
        </button>
        <button
          aria-label="Zoom out"
          onClick={zoomOut}
          className="w-8 h-8 rounded bg-[oklch(0.12_0.02_240)]/80 flex items-center justify-center text-[var(--color-foreground)] border border-[var(--color-line)]"
        >
          −
        </button>
        <button
          aria-label="Reset to India"
          onClick={resetToIndia}
          className="w-8 h-8 rounded bg-[oklch(0.12_0.02_240)]/80 flex items-center justify-center text-[var(--color-foreground)] border border-[var(--color-line)]"
        >
          ⤢
        </button>
      </div>
    </div>
  );
}
