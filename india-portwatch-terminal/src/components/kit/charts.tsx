/**
 * Charts.
 *
 * Hand-drawn SVG rather than a charting library, because every one of these has
 * a specific operational job: show a band and where the threshold cuts it, show
 * a series against its own history, rank contributions. A generic chart
 * component would need more configuration than the drawing takes.
 *
 * Shared conventions: hairline grid, mono tick labels, no legend unless two
 * series overlap, and a gap wherever the pipeline produced no value.
 */

import { useId, useMemo, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";
import { TONE_VAR, type Tone } from "./primitives";

/* ------------------------------------------------------------------ util -- */

function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    return [min];
  }
  const span = max - min;
  const raw = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? magnitude * 10;
  const start = Math.ceil(min / step) * step;
  const out: number[] = [];
  for (let value = start; value <= max + 1e-9; value += step) out.push(Number(value.toFixed(6)));
  return out;
}

/* ------------------------------------------------------------- sparkline -- */

export function Sparkline({
  data,
  tone = "info",
  height = 22,
  fill = true,
  className,
}: {
  data: Array<number | null | undefined>;
  tone?: Tone;
  height?: number;
  fill?: boolean;
  className?: string;
}) {
  const points = data.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (points.length < 2) {
    return (
      <div
        className={cn(
          "grid w-full place-items-center text-[10px] text-[var(--text-3)]",
          className,
        )}
        style={{ height }}
      >
        no history
      </div>
    );
  }
  const max = Math.max(...points);
  const min = Math.min(...points);
  const span = max - min || 1;
  const width = 100;
  const coords = points.map((value, index) => {
    const x = (index / (points.length - 1)) * width;
    const y = height - 1 - ((value - min) / span) * (height - 2);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={cn("w-full", className)}
      style={{ height }}
      aria-hidden
    >
      {fill ? (
        <polygon
          points={`0,${height} ${coords.join(" ")} ${width},${height}`}
          fill={TONE_VAR[tone]}
          opacity={0.14}
        />
      ) : null}
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke={TONE_VAR[tone]}
        strokeWidth={1.1}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

/* ------------------------------------------------------- quantile ribbon -- */

export interface QuantilePoint {
  label: string;
  q10: number | null;
  q50: number | null;
  q90: number | null;
  observed?: number | null;
}

/**
 * The forecast band. The whole point of the screen is that the uncertainty is
 * legible, so the ribbon is the loudest mark and q50 sits inside it as a line.
 */
export function QuantileChart({
  points,
  threshold,
  thresholdLabel,
  height = 190,
  yLabel,
  className,
}: {
  points: QuantilePoint[];
  threshold?: number | null;
  thresholdLabel?: string;
  height?: number;
  yLabel?: string;
  className?: string;
}) {
  const gradientId = useId();
  const [hover, setHover] = useState<number | null>(null);

  const model = useMemo(() => {
    const values = points.flatMap((p) =>
      [p.q10, p.q50, p.q90, p.observed].filter(
        (v): v is number => typeof v === "number" && Number.isFinite(v),
      ),
    );
    if (!values.length) return null;
    const rawMin = Math.min(...values, threshold ?? Number.POSITIVE_INFINITY);
    const rawMax = Math.max(...values, threshold ?? Number.NEGATIVE_INFINITY);
    const pad = Math.max((rawMax - rawMin) * 0.15, 1);
    return { min: rawMin - pad, max: rawMax + pad };
  }, [points, threshold]);

  if (!model || points.length < 2) {
    return (
      <div
        className={cn("grid w-full place-items-center text-[11px] text-[var(--text-3)]", className)}
        style={{ height }}
      >
        No forecast in this artefact
      </div>
    );
  }

  const padL = 40;
  const padR = 10;
  const padT = 10;
  const padB = 22;
  const width = 720;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const x = (index: number) => padL + (index / (points.length - 1)) * plotW;
  const y = (value: number) =>
    padT + plotH - ((value - model.min) / (model.max - model.min)) * plotH;

  const upper = points.map((p, i) => `${x(i)},${y(p.q90 ?? p.q50 ?? model.min)}`);
  const lower = points
    .map((p, i) => `${x(i)},${y(p.q10 ?? p.q50 ?? model.min)}`)
    .reverse();
  const median = points
    .map((p, i) => (p.q50 == null ? null : `${x(i)},${y(p.q50)}`))
    .filter((v): v is string => v !== null);

  const ticks = niceTicks(model.min, model.max, 4);
  const active = hover != null ? points[hover] : null;

  return (
    <div className={cn("relative w-full", className)}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="w-full"
        style={{ height }}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const ratio = (event.clientX - rect.left) / rect.width;
          const svgX = ratio * width;
          const index = Math.round(((svgX - padL) / plotW) * (points.length - 1));
          setHover(Math.min(points.length - 1, Math.max(0, index)));
        }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--info)" stopOpacity="0.26" />
            <stop offset="100%" stopColor="var(--info)" stopOpacity="0.08" />
          </linearGradient>
        </defs>

        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={padL}
              x2={width - padR}
              y1={y(tick)}
              y2={y(tick)}
              stroke="var(--line)"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={padL - 6}
              y={y(tick) + 3}
              textAnchor="end"
              className="num"
              fill="var(--text-3)"
              fontSize={9}
            >
              {tick.toFixed(0)}
            </text>
          </g>
        ))}

        <polygon points={[...upper, ...lower].join(" ")} fill={`url(#${gradientId})`} />
        <polyline
          points={upper.join(" ")}
          fill="none"
          stroke="var(--info)"
          strokeOpacity={0.4}
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />
        <polyline
          points={points.map((p, i) => `${x(i)},${y(p.q10 ?? p.q50 ?? model.min)}`).join(" ")}
          fill="none"
          stroke="var(--info)"
          strokeOpacity={0.4}
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />

        {threshold != null ? (
          <>
            <line
              x1={padL}
              x2={width - padR}
              y1={y(threshold)}
              y2={y(threshold)}
              stroke="var(--warn)"
              strokeWidth={1}
              strokeDasharray="4 4"
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={width - padR}
              y={y(threshold) - 4}
              textAnchor="end"
              fill="var(--warn)"
              fontSize={9}
            >
              {thresholdLabel ?? `threshold ${threshold}`}
            </text>
          </>
        ) : null}

        <polyline
          points={median.join(" ")}
          fill="none"
          stroke="var(--info)"
          strokeWidth={1.8}
          vectorEffect="non-scaling-stroke"
        />

        {points.map((point, index) =>
          point.observed == null ? null : (
            <circle
              key={`obs-${point.label}`}
              cx={x(index)}
              cy={y(point.observed)}
              r={2.2}
              fill="var(--text)"
            />
          ),
        )}

        {hover != null ? (
          <line
            x1={x(hover)}
            x2={x(hover)}
            y1={padT}
            y2={padT + plotH}
            stroke="var(--text-2)"
            strokeOpacity={0.5}
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
        ) : null}

        {points.map((point, index) => {
          const step = Math.max(1, Math.ceil(points.length / 10));
          if (index % step !== 0 && index !== points.length - 1) return null;
          return (
            <text
              key={`x-${point.label}-${index}`}
              x={x(index)}
              y={height - 6}
              textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"}
              className="num"
              fill="var(--text-3)"
              fontSize={9}
            >
              {point.label}
            </text>
          );
        })}
      </svg>

      {yLabel ? (
        <span className="eyebrow absolute left-0 top-0 text-[9px]">{yLabel}</span>
      ) : null}

      {active ? (
        <div className="pointer-events-none absolute right-2 top-2 rounded-[2px] border border-[var(--line-strong)] bg-[var(--panel-2)]/95 px-2 py-1 text-[10.5px]">
          <div className="mb-0.5 text-[var(--text-2)]">{active.label}</div>
          <div className="num flex gap-2.5 text-[var(--text-3)]">
            <span>
              q10 <span className="text-[var(--text)]">{active.q10?.toFixed(1) ?? "n/a"}</span>
            </span>
            <span>
              q50 <span className="text-[var(--info)]">{active.q50?.toFixed(1) ?? "n/a"}</span>
            </span>
            <span>
              q90 <span className="text-[var(--text)]">{active.q90?.toFixed(1) ?? "n/a"}</span>
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------ line chart -- */

export interface SeriesPoint {
  label: string;
  value: number | null;
}

export function SeriesChart({
  series,
  height = 130,
  bands,
  className,
  yUnit,
}: {
  series: Array<{ name: string; tone: Tone; points: SeriesPoint[]; area?: boolean; dashed?: boolean }>;
  height?: number;
  /** Optional shaded x-range, e.g. the forecast half of a timeline. */
  bands?: Array<{ fromIndex: number; toIndex: number; label?: string }>;
  className?: string;
  yUnit?: string;
}) {
  const gradientId = useId();
  const length = series[0]?.points.length ?? 0;
  const values = series.flatMap((s) =>
    s.points.map((p) => p.value).filter((v): v is number => typeof v === "number" && Number.isFinite(v)),
  );

  if (!values.length || length < 2) {
    return (
      <div
        className={cn("grid w-full place-items-center text-[11px] text-[var(--text-3)]", className)}
        style={{ height }}
      >
        No series in this artefact
      </div>
    );
  }

  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const pad = Math.max((rawMax - rawMin) * 0.18, Math.abs(rawMax) * 0.05, 0.4);
  const min = rawMin - pad;
  const max = rawMax + pad;

  const padL = 36;
  const padR = 8;
  const padT = 8;
  const padB = 18;
  const width = 640;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const x = (i: number) => padL + (i / (length - 1)) * plotW;
  const y = (v: number) => padT + plotH - ((v - min) / (max - min)) * plotH;
  const ticks = niceTicks(min, max, 3);

  return (
    <div className={cn("relative w-full", className)}>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.22" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {bands?.map((band) => (
          <rect
            key={`${band.fromIndex}-${band.toIndex}`}
            x={x(band.fromIndex)}
            width={Math.max(0, x(band.toIndex) - x(band.fromIndex))}
            y={padT}
            height={plotH}
            fill="var(--panel-3)"
            opacity={0.55}
          />
        ))}

        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={padL}
              x2={width - padR}
              y1={y(tick)}
              y2={y(tick)}
              stroke="var(--line)"
              vectorEffect="non-scaling-stroke"
            />
            <text x={padL - 5} y={y(tick) + 3} textAnchor="end" className="num" fill="var(--text-3)" fontSize={9}>
              {Math.abs(tick) >= 1000 ? `${(tick / 1000).toFixed(0)}k` : tick.toFixed(Math.abs(tick) < 10 ? 1 : 0)}
            </text>
          </g>
        ))}

        {series.map((s) => {
          const coords = s.points
            .map((p, i) => (p.value == null ? null : `${x(i)},${y(p.value)}`))
            .filter((v): v is string => v !== null);
          if (coords.length < 2) return null;
          return (
            <g key={s.name} style={{ color: TONE_VAR[s.tone] }}>
              {s.area ? (
                <polygon
                  points={`${x(0)},${padT + plotH} ${coords.join(" ")} ${x(length - 1)},${padT + plotH}`}
                  fill={`url(#${gradientId})`}
                />
              ) : null}
              <polyline
                points={coords.join(" ")}
                fill="none"
                stroke={TONE_VAR[s.tone]}
                strokeWidth={1.5}
                strokeDasharray={s.dashed ? "4 3" : undefined}
                vectorEffect="non-scaling-stroke"
              />
            </g>
          );
        })}

        {series[0]?.points.map((point, index) => {
          const step = Math.max(1, Math.ceil(length / 8));
          if (index % step !== 0 && index !== length - 1) return null;
          return (
            <text
              key={`${point.label}-${index}`}
              x={x(index)}
              y={height - 5}
              textAnchor={index === 0 ? "start" : index === length - 1 ? "end" : "middle"}
              className="num"
              fill="var(--text-3)"
              fontSize={9}
            >
              {point.label}
            </text>
          );
        })}
      </svg>

      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
        {series.map((s) => (
          <span key={s.name} className="flex items-center gap-1.5 text-[10.5px] text-[var(--text-3)]">
            <span className="h-[2px] w-4" style={{ background: TONE_VAR[s.tone] }} />
            {s.name}
          </span>
        ))}
        {yUnit ? <span className="ml-auto text-[10px] text-[var(--text-3)]">{yUnit}</span> : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ bar ranking -- */

export function BarRanking({
  items,
  className,
  valueFormatter = (v) => v.toFixed(3),
}: {
  items: Array<{ label: string; value: number | null; tone?: Tone; note?: ReactNode }>;
  className?: string;
  valueFormatter?: (value: number) => string;
}) {
  const max = Math.max(
    ...items.map((i) => (i.value == null ? 0 : Math.abs(i.value))),
    1e-9,
  );
  return (
    <div className={cn("flex flex-col", className)}>
      {items.map((item) => (
        <div
          key={item.label}
          className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 border-b border-[var(--line)]/50 py-1.5 last:border-0"
        >
          <div className="min-w-0">
            <div className="truncate text-[11.5px] text-[var(--text-2)]">{item.label}</div>
            <div className="mt-1 h-[3px] w-full overflow-hidden rounded-[1px] bg-[var(--panel-3)]">
              <div
                className="h-full"
                style={{
                  width: `${item.value == null ? 0 : (Math.abs(item.value) / max) * 100}%`,
                  background: TONE_VAR[item.tone ?? "info"],
                }}
              />
            </div>
          </div>
          <div className="num shrink-0 text-right text-[11.5px] text-[var(--text)]">
            {item.value == null ? (
              <span className="text-[var(--text-3)]">n/a</span>
            ) : (
              valueFormatter(item.value)
            )}
            {item.note ? (
              <div className="text-[10px] font-normal text-[var(--text-3)]">{item.note}</div>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

/* --------------------------------------------------------- column series -- */

export function ColumnChart({
  points,
  tone = "info",
  height = 110,
  threshold,
  className,
}: {
  points: Array<{ label: string; value: number | null; tone?: Tone }>;
  tone?: Tone;
  height?: number;
  threshold?: number | null;
  className?: string;
}) {
  const values = points
    .map((p) => p.value)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!values.length) {
    return (
      <div
        className={cn("grid w-full place-items-center text-[11px] text-[var(--text-3)]", className)}
        style={{ height }}
      >
        No measurements
      </div>
    );
  }
  const max = Math.max(...values, threshold ?? 0) * 1.12 || 1;
  return (
    <div className={cn("w-full", className)}>
      <div className="relative flex items-end justify-center gap-[3px]" style={{ height }}>
        {threshold != null ? (
          <div
            className="pointer-events-none absolute inset-x-0 border-t border-dashed border-[var(--warn)]/70"
            style={{ bottom: `${(threshold / max) * 100}%` }}
          />
        ) : null}
        {points.map((point, index) => (
          <div
            key={`${point.label}-${index}`}
            className="group relative flex-1"
            style={{ maxWidth: 30 }}
            title={`${point.label} · ${point.value?.toFixed(1) ?? "n/a"}`}
          >
            <div
              className="w-full rounded-[1px] transition-opacity group-hover:opacity-100"
              style={{
                height: point.value == null ? 2 : `${Math.max(2, (point.value / max) * height)}px`,
                background: point.value == null ? "var(--panel-3)" : TONE_VAR[point.tone ?? tone],
                opacity: 0.86,
              }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[9.5px] text-[var(--text-3)]">
        <span className="num">{points[0]?.label}</span>
        <span className="num">{points[points.length - 1]?.label}</span>
      </div>
    </div>
  );
}
