import { useEffect, useMemo, useRef, useState } from "react";
import type {
  GlobeContext,
  GlobeRoute,
  GlobeVessel,
} from "./IntelligenceGlobe";
import { routeHeading } from "./globe-geometry";

/** SVG geographic lens: genuine pan/zoom/picking, including when WebGL is absent. */
export function GeographicMap({
  context,
  routes,
  vessels,
  portCode,
  selectedVesselId,
  onPort,
  onEvent,
  onVessel,
  fitKey,
}: {
  context: GlobeContext;
  routes: GlobeRoute[];
  vessels: GlobeVessel[];
  portCode: string | null;
  selectedVesselId?: string | null;
  onPort(code: string): void;
  onEvent(id: string): void;
  onVessel?(id: string): void;
  fitKey: string;
}) {
  const [land, setLand] = useState<string[]>([]);
  const [box, setBox] = useState([150, 30, 145, 95]);
  const host = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState({ width: 1366, height: 768 });
  const unit = Math.max(box[2] / size.width, box[3] / size.height);
  const drag = useRef<{ x: number; y: number; box: number[] } | null>(null);
  const geometry = useRef(routes);
  geometry.current = routes;
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width && entry.contentRect.height)
        setSize({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const portLabels = useMemo(() => {
    const occupied: { x: number; y: number; width: number }[] = vessels
      .filter((v) => v.id === selectedVesselId)
      .map((v) => ({
        x: (v.lon + 180) / unit + 12,
        y: (90 - v.lat) / unit,
        width: v.name.length * 6.6,
      }));
    const visible = new Set<string>();
    [...context.ports]
      .sort((a, b) => Number(b.code === portCode) - Number(a.code === portCode))
      .forEach((p) => {
        if (p.code !== portCode && box[2] > 70) return;
        const x = p.location.lon + 180,
          y = 90 - p.location.lat;
        if (
          x < box[0] ||
          x > box[0] + box[2] ||
          y < box[1] ||
          y > box[1] + box[3]
        )
          return;
        const label = { x: x / unit + 8, y: y / unit - 8, width: 28 };
        if (
          p.code !== portCode &&
          occupied.some(
            (r) =>
              Math.abs(r.y - label.y) < 20 &&
              label.x < r.x + r.width + 6 &&
              label.x + label.width + 6 > r.x,
          )
        )
          return;
        visible.add(p.code);
        occupied.push(label);
      });
    return visible;
  }, [context.ports, portCode, selectedVesselId, vessels, box, unit]);
  useEffect(() => {
    const controller = new AbortController();
    void fetch("/maps/world-countries.json", { signal: controller.signal })
      .then((r) => r.json())
      .then((world: GeoJSON.FeatureCollection) => {
        setLand(
          world.features.flatMap((f) => {
            if (
              !f.geometry ||
              !["Polygon", "MultiPolygon"].includes(f.geometry.type)
            )
              return [];
            const g = f.geometry as GeoJSON.Polygon | GeoJSON.MultiPolygon;
            const polygons =
              g.type === "Polygon" ? [g.coordinates] : g.coordinates;
            return polygons.map((p) =>
              p
                .map(
                  (r) =>
                    r
                      .map(
                        ([lon, lat], i) =>
                          `${i ? "L" : "M"}${lon + 180},${90 - lat}`,
                      )
                      .join(" ") + " Z",
                )
                .join(" "),
            );
          }),
        );
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const coords = geometry.current
      .filter((r) => r.selected)
      .flatMap((r) => r.positions);
    if (!coords.length) return;
    const xs = coords.map((p) => p[1] + 180),
      ys = coords.map((p) => 90 - p[0]);
    const w = Math.max(30, Math.max(...xs) - Math.min(...xs)),
      h = Math.max(25, Math.max(...ys) - Math.min(...ys));
    setBox([
      Math.min(...xs) - w * 0.22,
      Math.min(...ys) - h * 0.18,
      w * 1.65,
      h * 1.36,
    ]);
  }, [fitKey]);
  return (
    <svg
      ref={host}
      className="geographic-map"
      role="application"
      tabIndex={0}
      aria-label="Interactive nautical map"
      viewBox={box.join(" ")}
      onKeyDown={(e) => {
        if (
          ![
            "+",
            "=",
            "-",
            "ArrowLeft",
            "ArrowRight",
            "ArrowUp",
            "ArrowDown",
          ].includes(e.key)
        )
          return;
        e.preventDefault();
        if (["+", "=", "-"].includes(e.key)) {
          const k = e.key === "-" ? 1.2 : 0.83;
          setBox(([x, y, w, h]) => [
            x + (w * (1 - k)) / 2,
            y + (h * (1 - k)) / 2,
            w * k,
            h * k,
          ]);
        } else
          setBox(([x, y, w, h]) => [
            x +
              (e.key === "ArrowRight"
                ? 0.08
                : e.key === "ArrowLeft"
                  ? -0.08
                  : 0) *
                w,
            y +
              (e.key === "ArrowDown" ? 0.08 : e.key === "ArrowUp" ? -0.08 : 0) *
                h,
            w,
            h,
          ]);
      }}
      onWheel={(e) => {
        e.preventDefault();
        const k = e.deltaY > 0 ? 1.15 : 0.87;
        setBox(([x, y, w, h]) => [
          x + (w * (1 - k)) / 2,
          y + (h * (1 - k)) / 2,
          Math.min(360, Math.max(8, w * k)),
          Math.min(180, Math.max(8, h * k)),
        ]);
      }}
      onPointerDown={(e) => {
        if ((e.target as Element).closest("[data-asset]")) return;
        e.currentTarget.setPointerCapture(e.pointerId);
        drag.current = { x: e.clientX, y: e.clientY, box };
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (!d) return;
        const rect = e.currentTarget.getBoundingClientRect();
        setBox([
          d.box[0] - ((e.clientX - d.x) * d.box[2]) / rect.width,
          d.box[1] - ((e.clientY - d.y) * d.box[3]) / rect.height,
          d.box[2],
          d.box[3],
        ]);
      }}
      onPointerUp={() => {
        drag.current = null;
      }}
    >
      <rect x="0" y="0" width="360" height="180" fill="#071923" />
      {Array.from({ length: 25 }, (_, i) => (
        <path
          key={`x${i}`}
          d={`M${i * 15},0V180`}
          stroke="#16323e"
          strokeWidth=".5"
          vectorEffect="non-scaling-stroke"
        />
      ))}
      {Array.from({ length: 13 }, (_, i) => (
        <path
          key={`y${i}`}
          d={`M0,${i * 15}H360`}
          stroke="#16323e"
          strokeWidth=".5"
          vectorEffect="non-scaling-stroke"
        />
      ))}
      {land.map((d, i) => (
        <path
          key={i}
          d={d}
          fill="#203744"
          fillRule="evenodd"
          stroke="#658596"
          strokeWidth=".7"
          vectorEffect="non-scaling-stroke"
        />
      ))}
      {routes.map((r) => (
        <polyline
          key={r.id}
          points={r.positions
            .map(([lat, lon]) => `${lon + 180},${90 - lat}`)
            .join(" ")}
          fill="none"
          stroke={r.rejected ? "#d05a4c" : r.selected ? "#e2ad4e" : "#4c9fcb"}
          strokeWidth={r.selected ? 2 : 1.2}
          strokeDasharray={r.rejected ? "6 4" : undefined}
          vectorEffect="non-scaling-stroke"
        />
      ))}
      {context.ports.map((p) => (
        <g
          key={p.code}
          data-asset="port"
          tabIndex={0}
          role="button"
          aria-label={p.name}
          onClick={() => onPort(p.code)}
          onKeyDown={(e) => e.key === "Enter" && onPort(p.code)}
          transform={`translate(${p.location.lon + 180},${90 - p.location.lat})`}
        >
          <title>{p.name}</title>
          <circle r={12 * unit} fill="transparent" />
          <circle
            r={(p.code === portCode ? 5 : 3.5) * unit}
            fill="#83c7d8"
            stroke="#10212c"
            strokeWidth={unit}
          />
          {portLabels.has(p.code) ? (
            <text
              x={8 * unit}
              y={-8 * unit}
              fontSize={11 * unit}
              fill="#a4bccc"
            >
              {p.code.slice(2)}
            </text>
          ) : null}
        </g>
      ))}
      {context.news.events
        .filter((e) => e.coordinates)
        .map((e) => (
          <g
            key={e.eventId}
            data-asset="event"
            tabIndex={0}
            role="button"
            aria-label={e.title}
            onClick={() => onEvent(e.eventId)}
            onKeyDown={(k) => k.key === "Enter" && onEvent(e.eventId)}
            transform={`translate(${e.coordinates!.lon + 180},${90 - e.coordinates!.lat})`}
          >
            <circle r={12 * unit} fill="transparent" />
            <path
              d="M0,-1L1,0L0,1L-1,0Z"
              transform={`scale(${6 * unit})`}
              fill="#e2ad4e"
            />
            <title>{e.title}</title>
          </g>
        ))}
      {vessels.map((v) => (
        <g
          key={v.id}
          data-asset="vessel"
          role="button"
          tabIndex={0}
          aria-label={v.name}
          onClick={() => onVessel?.(v.id)}
          onKeyDown={(e) => e.key === "Enter" && onVessel?.(v.id)}
          transform={`translate(${v.lon + 180},${90 - v.lat})`}
        >
          <title>{v.name}</title>
          <circle r={12 * unit} fill="transparent" />
          <path
            d="M0,-1.1L.65,.7L0,.4L-.65,.7Z"
            transform={`rotate(${routeHeading(v, routes)}) scale(${9 * unit})`}
            fill={v.id === selectedVesselId ? "#ffcf73" : "#4c9fcb"}
            stroke="#071923"
            strokeWidth=".2"
          />
          <text x={12 * unit} fontSize={11 * unit} fill="#e0ecf2">
            {v.id === selectedVesselId ? v.name : ""}
          </text>
        </g>
      ))}
    </svg>
  );
}
