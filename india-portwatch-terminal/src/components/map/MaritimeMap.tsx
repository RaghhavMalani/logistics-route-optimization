import { useCallback, useEffect, useRef, useState } from "react";
import type {
  CSSProperties,
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
} from "react";
import blackMarbleWorldUrl from "@/assets/nasa-black-marble-world.jpg";
import { TONE_HEX, formatAge, riskLabel, riskTone } from "@/components/terminal/ui";
import type {
  PortSnapshot,
  VesselActivity,
  WeatherSignal,
} from "@/types/portwatch";

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
  moved: boolean;
}

/** Chokepoints drawn on the national radar, with their exposed Indian coast. */
const CHOKEPOINTS = [
  { code: "HORMUZ", name: "Strait of Hormuz", lat: 26.6, lon: 56.3 },
  { code: "BAB_EL_MANDEB", name: "Bab-el-Mandeb", lat: 12.6, lon: 43.3 },
  { code: "SUEZ", name: "Suez Canal", lat: 30.0, lon: 32.55 },
  { code: "MALACCA", name: "Strait of Malacca", lat: 2.5, lon: 101.0 },
] as const;

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
      ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) *
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
  return {
    ...transform,
    x: clamp(transform.x, visibleMargin - imageSize, width - visibleMargin),
    y: clamp(transform.y, visibleMargin - imageSize, height - visibleMargin),
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

export function MaritimeMap({
  ports,
  vessels,
  weather,
  selectedPort,
  highlightedPorts,
  onPortSelect,
}: {
  ports: PortSnapshot[];
  vessels: VesselActivity[];
  weather: WeatherSignal[];
  selectedPort?: string | null;
  highlightedPorts?: string[];
  onPortSelect: (portCode: string) => void;
}) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const hasInteractedRef = useRef(false);
  const [view, setView] = useState<ViewTransform>(EMPTY_VIEW);
  const [hovered, setHovered] = useState<string | null>(null);

  const getViewportSize = useCallback(() => {
    const rect = viewportRef.current?.getBoundingClientRect();
    return { width: rect?.width ?? 0, height: rect?.height ?? 0 };
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
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    drag.moved = true;
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
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
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

  const zoomAroundCentre = (factor: number) => {
    const rect = viewportRef.current?.getBoundingClientRect();
    if (!rect) return;
    const cx = rect.width / 2;
    const cy = rect.height / 2;
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
        rect.width,
        rect.height,
      );
    });
  };

  const resetToIndia = () => {
    const { width, height } = getViewportSize();
    if (!width || !height) return;
    hasInteractedRef.current = false;
    setView(getIndiaView(width, height));
  };

  const project = (lon: number, lat: number) => {
    const point = lonLatToMercatorPoint([lon, lat], view.baseSize);
    return { left: view.x + point.x * view.scale, top: view.y + point.y * view.scale };
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

  const weatherByPort = new Map(weather.map((w) => [w.portCode, w]));
  const vesselByPort = new Map(vessels.map((v) => [v.portCode, v]));
  const highlighted = new Set(highlightedPorts ?? []);
  const hoveredPort = ports.find((port) => port.code === hovered) ?? null;

  return (
    <div
      ref={viewportRef}
      aria-label="National maritime radar"
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

      {/* Sea lanes from the exposed coast to each chokepoint. */}
      <svg className="pointer-events-none absolute inset-0 h-full w-full">
        {CHOKEPOINTS.map((choke) => {
          const target = project(choke.lon, choke.lat);
          const anchorPort =
            ports.find((p) =>
              choke.code === "MALACCA" ? p.coast === "east" : p.coast === "west",
            ) ?? ports[0];
          if (!anchorPort?.location) return null;
          const origin = project(anchorPort.location.lon, anchorPort.location.lat);
          const midX = (origin.left + target.left) / 2;
          const midY = (origin.top + target.top) / 2 - 40;
          return (
            <path
              key={choke.code}
              d={`M ${origin.left} ${origin.top} Q ${midX} ${midY} ${target.left} ${target.top}`}
              fill="none"
              stroke="var(--color-cyan)"
              strokeOpacity={0.22}
              strokeWidth={1}
              strokeDasharray="4 5"
            />
          );
        })}
      </svg>

      {/* Chokepoint nodes. */}
      {CHOKEPOINTS.map((choke) => {
        const { left, top } = project(choke.lon, choke.lat);
        return (
          <div
            key={choke.code}
            className="pointer-events-none absolute"
            style={{ transform: `translate3d(${left - 4}px, ${top - 4}px, 0)` }}
          >
            <div className="h-2 w-2 rotate-45 border border-[var(--color-cyan)]/70 bg-[var(--color-cyan)]/20" />
            <span className="absolute left-3 -top-1 whitespace-nowrap text-[8px] tracking-[0.14em] text-[var(--color-cyan)]/70">
              {choke.name.toUpperCase()}
            </span>
          </div>
        );
      })}

      {/* Port markers, coloured and sized by the model's own risk assessment. */}
      {ports.map((port) => {
        if (!port.location) return null;
        const { left, top } = project(port.location.lon, port.location.lat);
        const tone = riskTone(port.risk);
        const isSelected = selectedPort === port.code;
        const isHighlighted = highlighted.has(port.code);
        const size = port.risk === "severe" ? 9 : port.risk === "congested" ? 7 : 5;
        return (
          <div
            key={port.code}
            className="group absolute pointer-events-auto"
            style={{ transform: `translate3d(${left}px, ${top}px, 0)` }}
            onMouseEnter={() => setHovered(port.code)}
            onMouseLeave={() => setHovered((c) => (c === port.code ? null : c))}
          >
            {(isSelected || isHighlighted || port.risk === "severe") && (
              <span
                className="absolute rounded-full"
                style={{
                  left: -(size + 6) / 2 + size / 2,
                  top: -(size + 6) / 2 + size / 2,
                  width: size + 6,
                  height: size + 6,
                  border: `1px solid ${TONE_HEX[tone]}`,
                  opacity: 0.55,
                }}
              />
            )}
            <button
              type="button"
              aria-label={`${port.name} — ${riskLabel(port.risk)}`}
              onClick={(event) => {
                event.stopPropagation();
                onPortSelect(port.code);
              }}
              className="rounded-full border border-black/30 shadow-sm"
              style={{
                width: size,
                height: size,
                background: TONE_HEX[tone],
                transform: `translate(${-size / 2}px, ${-size / 2}px)`,
              }}
            />
            <span className="absolute left-2.5 -top-2 whitespace-nowrap text-[8px] tracking-[0.12em] text-white/70 opacity-0 transition-opacity group-hover:opacity-100">
              {port.short}
            </span>
          </div>
        );
      })}

      {/* Compact operational tooltip for the hovered port. */}
      {hoveredPort?.location && (
        <div
          className="pointer-events-none absolute z-30 w-[212px] border border-[var(--color-line-strong)] bg-[oklch(0.09_0.02_240_/_0.96)] p-2 shadow-xl"
          style={(() => {
            const { left, top } = project(
              hoveredPort.location.lon,
              hoveredPort.location.lat,
            );
            return { left: Math.min(left + 14, (getViewportSize().width || 800) - 226), top: Math.max(top - 60, 8) };
          })()}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-semibold text-[var(--color-foreground)] truncate">
              {hoveredPort.name}
            </span>
            <span
              className="text-[9px] tracking-widest"
              style={{ color: TONE_HEX[riskTone(hoveredPort.risk)] }}
            >
              {riskLabel(hoveredPort.risk)}
            </span>
          </div>
          <div className="mt-1 grid grid-cols-2 gap-x-2 gap-y-[2px] text-[9px]">
            <span className="text-[var(--color-muted-foreground)]">Observed</span>
            <span className="text-right tabular-nums">
              {hoveredPort.observedCongestionIndex?.toFixed(1) ?? "n/a"}
            </span>
            <span className="text-[var(--color-muted-foreground)]">Day 1 fc</span>
            <span className="text-right tabular-nums">
              {hoveredPort.congestionIndex.toFixed(1)}
            </span>
            <span className="text-[var(--color-muted-foreground)]">Wait</span>
            <span className="text-right tabular-nums">
              {hoveredPort.delayHours.toFixed(1)}h
            </span>
            <span className="text-[var(--color-muted-foreground)]">Calls/day</span>
            <span className="text-right tabular-nums">
              {vesselByPort.get(hoveredPort.code)?.dailyPortCalls?.toFixed(1) ??
                hoveredPort.vesselCalls?.toFixed(1) ??
                "n/a"}
            </span>
            <span className="text-[var(--color-muted-foreground)]">Wx impact</span>
            <span className="text-right tabular-nums">
              {weatherByPort.get(hoveredPort.code)?.impactScore?.toFixed(2) ?? "n/a"}
            </span>
            <span className="text-[var(--color-muted-foreground)]">Regime</span>
            <span className="text-right">{hoveredPort.regime}</span>
            <span className="text-[var(--color-muted-foreground)]">Data</span>
            <span className="text-right">
              {hoveredPort.dataStatus}
              {hoveredPort.dataAgeHours != null &&
                ` · ${formatAge(hoveredPort.dataAgeHours)}`}
            </span>
          </div>
          <div className="mt-1 border-t border-[var(--color-line)]/60 pt-1 text-[8px] text-[var(--color-cyan)]">
            Click to open the port cockpit
          </div>
        </div>
      )}

      <div className="absolute right-3 top-3 z-20 flex flex-col gap-1.5">
        {[
          { label: "+", action: () => zoomAroundCentre(1.2), title: "Zoom in" },
          { label: "−", action: () => zoomAroundCentre(1 / 1.2), title: "Zoom out" },
          { label: "⤢", action: resetToIndia, title: "Reset to India" },
        ].map((control) => (
          <button
            key={control.title}
            aria-label={control.title}
            title={control.title}
            onClick={control.action}
            className="h-7 w-7 rounded-sm border border-[var(--color-line)] bg-[oklch(0.12_0.02_240)]/85 text-[var(--color-foreground)]"
          >
            {control.label}
          </button>
        ))}
      </div>

      <div className="absolute bottom-3 left-3 z-20 flex items-center gap-3 border border-[var(--color-line)] bg-[oklch(0.09_0.02_240_/_0.9)] px-2 py-1 text-[8px] tracking-[0.14em]">
        {(["severe", "congested", "normal"] as const).map((risk) => (
          <span key={risk} className="flex items-center gap-1">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: TONE_HEX[riskTone(risk)] }}
            />
            {riskLabel(risk)}
          </span>
        ))}
        <span className="flex items-center gap-1 text-[var(--color-cyan)]">
          <span className="h-1.5 w-1.5 rotate-45 border border-[var(--color-cyan)]" />
          CHOKEPOINT
        </span>
      </div>
    </div>
  );
}
