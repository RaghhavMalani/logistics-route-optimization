import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { DataStatus } from "@/types/portwatch";

export type Tone = "cyan" | "mint" | "amber" | "red" | "purple" | "muted";

export const TONE_TEXT: Record<Tone, string> = {
  cyan: "text-[var(--color-cyan)]",
  mint: "text-[var(--color-mint)]",
  amber: "text-[var(--color-amber)]",
  red: "text-[var(--color-red)]",
  purple: "text-[var(--color-purple)]",
  muted: "text-[var(--color-muted-foreground)]",
};

export const TONE_HEX: Record<Tone, string> = {
  cyan: "var(--color-cyan)",
  mint: "var(--color-mint)",
  amber: "var(--color-amber)",
  red: "var(--color-red)",
  purple: "var(--color-purple)",
  muted: "var(--color-muted-foreground)",
};

/* ------------------------------------------------------------- primitives */

export function Panel({
  title,
  right,
  children,
  className,
  bodyClassName,
}: {
  title?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <div className={cn("panel flex flex-col overflow-hidden", className)}>
      {title && (
        <div className="panel-header">
          <span className="truncate">{title}</span>
          {right && (
            <span className="text-[9px] tracking-widest text-[var(--color-muted-foreground)] shrink-0 ml-2">
              {right}
            </span>
          )}
        </div>
      )}
      <div className={cn("flex-1 min-h-0 overflow-auto", bodyClassName)}>
        {children}
      </div>
    </div>
  );
}

export function Chip({
  tone = "muted",
  children,
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
}) {
  const map: Record<Tone, string> = {
    cyan: "border-[var(--color-cyan)]/50 text-[var(--color-cyan)] bg-[var(--color-cyan)]/5",
    mint: "border-[var(--color-mint)]/40 text-[var(--color-mint)] bg-[var(--color-mint)]/5",
    amber:
      "border-[var(--color-amber)]/50 text-[var(--color-amber)] bg-[var(--color-amber)]/5",
    red: "border-[var(--color-red)]/60 text-[var(--color-red)] bg-[var(--color-red)]/10",
    purple:
      "border-[var(--color-purple)]/50 text-[var(--color-purple)] bg-[var(--color-purple)]/10",
    muted: "border-[var(--color-line-strong)] text-[var(--color-muted-foreground)]",
  };
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 border px-1.5 py-[1px] rounded-sm text-[9px] tracking-widest uppercase font-semibold whitespace-nowrap",
        map[tone],
      )}
    >
      {children}
    </span>
  );
}

export function Bar({
  value,
  tone = "cyan",
}: {
  value: number | null | undefined;
  tone?: Tone;
}) {
  const width = value == null ? 0 : Math.min(100, Math.max(0, value * 100));
  return (
    <div className="h-1 w-full rounded-sm bg-[var(--color-panel-2)] overflow-hidden">
      <div
        className="h-full"
        style={{ width: `${width}%`, background: TONE_HEX[tone] }}
      />
    </div>
  );
}

export function Sparkline({
  data,
  tone = "cyan",
  height = 24,
  fill = false,
}: {
  data: Array<number | null | undefined>;
  tone?: Tone;
  height?: number;
  fill?: boolean;
}) {
  const points = data.filter((v): v is number => typeof v === "number" && !Number.isNaN(v));
  if (points.length < 2) {
    return (
      <div
        className="w-full grid place-items-center text-[9px] text-[var(--color-muted-foreground)]"
        style={{ height }}
      >
        no history
      </div>
    );
  }
  const max = Math.max(...points);
  const min = Math.min(...points);
  const w = 100;
  const span = max - min || 1;
  const coords = points.map((v, i) => {
    const x = (i / (points.length - 1)) * w;
    const y = height - ((v - min) / span) * (height - 2) - 1;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg
      viewBox={`0 0 ${w} ${height}`}
      preserveAspectRatio="none"
      className="w-full"
      style={{ height }}
    >
      {fill && (
        <polygon
          points={`0,${height} ${coords.join(" ")} ${w},${height}`}
          fill={TONE_HEX[tone]}
          opacity={0.12}
        />
      )}
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke={TONE_HEX[tone]}
        strokeWidth={1.2}
      />
    </svg>
  );
}

/* ------------------------------------------------------------- provenance */

const STATUS_TONE: Record<DataStatus, Tone> = {
  LIVE: "mint",
  CACHED_LIVE: "cyan",
  STALE: "amber",
  SYNTHETIC: "purple",
  UNAVAILABLE: "red",
};

const STATUS_LABEL: Record<DataStatus, string> = {
  LIVE: "LIVE",
  CACHED_LIVE: "CACHED",
  STALE: "STALE",
  SYNTHETIC: "SYNTHETIC",
  UNAVAILABLE: "NO DATA",
};

/**
 * The single component that states where a number came from. Every screen uses
 * it so a viewer never has to guess whether a panel is live or replayed.
 */
export function ProvenanceChip({
  status,
  ageHours,
  detail,
}: {
  status: DataStatus | null | undefined;
  ageHours?: number | null;
  detail?: string;
}) {
  const resolved: DataStatus = status ?? "UNAVAILABLE";
  return (
    <Chip
      tone={STATUS_TONE[resolved]}
      title={detail ?? `Data status: ${resolved}`}
    >
      {STATUS_LABEL[resolved]}
      {ageHours != null && <span className="tabular-nums">{formatAge(ageHours)}</span>}
    </Chip>
  );
}

export function formatAge(hours: number | null | undefined): string {
  if (hours == null || Number.isNaN(hours)) return "";
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 48) return `${hours.toFixed(0)}h`;
  return `${Math.round(hours / 24)}d`;
}

export function formatUtc(iso: string | null | undefined): string {
  if (!iso) return "--";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "--";
  const day = String(date.getUTCDate()).padStart(2, "0");
  const month = [
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
  ][date.getUTCMonth()];
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const mm = String(date.getUTCMinutes()).padStart(2, "0");
  return `${day} ${month} ${hh}:${mm}Z`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "--";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "--";
  const day = String(date.getUTCDate()).padStart(2, "0");
  const month = [
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
  ][date.getUTCMonth()];
  return `${day} ${month}`;
}

/* ------------------------------------------------------------ value cells */

/** Renders a number, or an explicit "not measured" marker when it is absent. */
export function Value({
  value,
  unit,
  digits = 1,
  tone,
  scale = 1,
  className,
}: {
  value: number | null | undefined;
  unit?: string;
  digits?: number;
  tone?: Tone;
  scale?: number;
  className?: string;
}) {
  if (value == null || Number.isNaN(value)) {
    return (
      <span
        className={cn("text-[var(--color-muted-foreground)]", className)}
        title="Not measured in this run"
      >
        n/a
      </span>
    );
  }
  return (
    <span className={cn("tabular-nums", tone && TONE_TEXT[tone], className)}>
      {(value * scale).toFixed(digits)}
      {unit && (
        <span className="text-[var(--color-muted-foreground)] ml-0.5">{unit}</span>
      )}
    </span>
  );
}

export function Delta({
  value,
  unit,
  digits = 1,
  invert = false,
}: {
  value: number | null | undefined;
  unit?: string;
  digits?: number;
  invert?: boolean;
}) {
  if (value == null || Number.isNaN(value)) {
    return <span className="text-[var(--color-muted-foreground)]">n/a</span>;
  }
  const worse = invert ? value < 0 : value > 0;
  const tone: Tone = Math.abs(value) < 1e-9 ? "muted" : worse ? "red" : "mint";
  return (
    <span className={cn("tabular-nums", TONE_TEXT[tone])}>
      {value > 0 ? "+" : ""}
      {value.toFixed(digits)}
      {unit}
    </span>
  );
}

export function MetricRow({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <div
      className="grid grid-cols-[1fr_auto] items-baseline gap-2 py-[3px] border-b border-[var(--color-line)]/30 last:border-0"
      title={hint}
    >
      <span className="text-[10px] text-[var(--color-muted-foreground)] truncate">
        {label}
      </span>
      <span className="text-[11px] text-right">{children}</span>
    </div>
  );
}

export function Metric({
  label,
  value,
  unit,
  tone = "cyan",
  sub,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  tone?: Tone;
  sub?: ReactNode;
}) {
  return (
    <div className="panel px-3 py-2 flex flex-col gap-0.5 min-w-0">
      <div className="label-xs truncate">{label}</div>
      <div className="flex items-baseline gap-1">
        <span className={cn("num-lg tabular-nums", TONE_TEXT[tone])}>{value}</span>
        {unit && (
          <span className="text-[10px] text-[var(--color-muted-foreground)]">
            {unit}
          </span>
        )}
      </div>
      {sub && (
        <div className="text-[10px] text-[var(--color-muted-foreground)] truncate">
          {sub}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------- messages */

export function ScreenMessage({
  tone = "cyan",
  title,
  detail,
  action,
}: {
  tone?: Tone;
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="h-full grid place-items-center p-8">
      <div className="max-w-[560px] text-center space-y-3">
        <div
          className={cn(
            "text-[12px] tracking-[0.2em] uppercase",
            TONE_TEXT[tone],
          )}
        >
          {title}
        </div>
        {detail && (
          <p className="text-[11px] leading-relaxed text-[var(--color-muted-foreground)] whitespace-pre-wrap">
            {detail}
          </p>
        )}
        {action}
      </div>
    </div>
  );
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="h-full grid place-items-center">
      <div className="flex items-center gap-2 text-[11px] tracking-[0.2em] text-[var(--color-cyan)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-cyan)] animate-blink" />
        {label}
      </div>
    </div>
  );
}

export function ErrorState({ error, hint }: { error: unknown; hint?: string }) {
  const message =
    error instanceof Error ? error.message : "Unknown error contacting the API.";
  const detail =
    error && typeof error === "object" && "detail" in error
      ? String((error as { detail: unknown }).detail)
      : message;
  return (
    <ScreenMessage
      tone="red"
      title="Intelligence API unavailable"
      detail={`${detail}\n\n${hint ?? "Start the backend with `uvicorn backend.app.main:app --reload`, then run `python run_award_demo.py --source portwatch` to build the artefacts."}`}
    />
  );
}

/* ------------------------------------------------------------ risk tones */

export function riskTone(risk: string | null | undefined): Tone {
  switch ((risk ?? "").toLowerCase()) {
    case "severe":
      return "red";
    case "congested":
    case "high":
      return "amber";
    case "medium":
      return "cyan";
    case "lowconf":
      return "purple";
    default:
      return "mint";
  }
}

export function riskLabel(risk: string | null | undefined): string {
  switch ((risk ?? "").toLowerCase()) {
    case "severe":
      return "SEVERE";
    case "congested":
      return "CONGESTED";
    case "high":
      return "HIGH";
    case "medium":
      return "WATCH";
    default:
      return "NORMAL";
  }
}
