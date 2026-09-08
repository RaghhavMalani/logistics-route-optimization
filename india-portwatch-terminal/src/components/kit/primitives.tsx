/**
 * The vocabulary every screen is built from.
 *
 * Two rules hold this together. Colour means state and nothing else, so `Tone`
 * is the only way a component gets coloured. And a number that the pipeline did
 * not produce renders as `n/a` with a reason on hover -- never as a zero, never
 * as a dash that could be mistaken for one.
 */

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import type { DataStatus } from "@/types/portwatch";

export type Tone = "ok" | "info" | "warn" | "crit" | "unc" | "neutral";

export const TONE_VAR: Record<Tone, string> = {
  ok: "var(--ok)",
  info: "var(--info)",
  warn: "var(--warn)",
  crit: "var(--crit)",
  unc: "var(--unc)",
  neutral: "var(--text-3)",
};

export const TONE_DIM: Record<Tone, string> = {
  ok: "var(--ok-dim)",
  info: "var(--info-dim)",
  warn: "var(--warn-dim)",
  crit: "var(--crit-dim)",
  unc: "var(--unc-dim)",
  neutral: "var(--panel-3)",
};

export const TONE_TEXT: Record<Tone, string> = {
  ok: "text-[var(--ok)]",
  info: "text-[var(--info)]",
  warn: "text-[var(--warn)]",
  crit: "text-[var(--crit)]",
  unc: "text-[var(--unc)]",
  neutral: "text-[var(--text-2)]",
};

/* ------------------------------------------------------------ formatting -- */

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function formatUtc(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const dd = String(date.getUTCDate()).padStart(2, "0");
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const mm = String(date.getUTCMinutes()).padStart(2, "0");
  return `${dd} ${MONTHS[date.getUTCMonth()]} ${hh}:${mm}Z`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return `${String(date.getUTCDate()).padStart(2, "0")} ${MONTHS[date.getUTCMonth()]}`;
}

export function formatAge(hours: number | null | undefined): string {
  if (hours == null || Number.isNaN(hours)) return "";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m`;
  if (hours < 48) return `${hours.toFixed(0)}h`;
  return `${Math.round(hours / 24)}d`;
}

export function formatCompact(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "n/a";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return value.toFixed(0);
}

/* ---------------------------------------------------------------- values -- */

export function Num({
  value,
  digits = 1,
  unit,
  tone,
  scale = 1,
  signed = false,
  className,
  missing = "n/a",
}: {
  value: number | null | undefined;
  digits?: number;
  unit?: string;
  tone?: Tone;
  scale?: number;
  signed?: boolean;
  className?: string;
  missing?: string;
}) {
  if (value == null || Number.isNaN(value)) {
    return (
      <span
        className={cn("num text-[var(--text-3)]", className)}
        title="Not produced by this pipeline run"
      >
        {missing}
      </span>
    );
  }
  const scaled = value * scale;
  return (
    <span className={cn("num", tone && TONE_TEXT[tone], className)}>
      {signed && scaled > 0 ? "+" : ""}
      {scaled.toFixed(digits)}
      {unit ? <span className="ml-0.5 text-[var(--text-3)]">{unit}</span> : null}
    </span>
  );
}

/** A change where the sign carries meaning: red is worse unless inverted. */
export function Delta({
  value,
  digits = 1,
  unit,
  invert = false,
  className,
}: {
  value: number | null | undefined;
  digits?: number;
  unit?: string;
  invert?: boolean;
  className?: string;
}) {
  if (value == null || Number.isNaN(value)) {
    return <span className={cn("num text-[var(--text-3)]", className)}>n/a</span>;
  }
  const neutral = Math.abs(value) < 1e-9;
  const worse = invert ? value < 0 : value > 0;
  const tone: Tone = neutral ? "neutral" : worse ? "crit" : "ok";
  return (
    <span className={cn("num", TONE_TEXT[tone], className)}>
      {value > 0 ? "+" : ""}
      {value.toFixed(digits)}
      {unit}
    </span>
  );
}

/* ----------------------------------------------------------------- pills -- */

export function Pill({
  tone = "neutral",
  children,
  title,
  solid = false,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
  solid?: boolean;
  className?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-[2px] px-1.5 py-[1px]",
        "text-[10px] font-semibold uppercase tracking-[0.08em]",
        className,
      )}
      style={
        solid
          ? { background: TONE_VAR[tone], color: "#06121a" }
          : {
              background: TONE_DIM[tone],
              color: TONE_VAR[tone],
              boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${TONE_VAR[tone]} 34%, transparent)`,
            }
      }
    >
      {children}
    </span>
  );
}

/** A small square that carries state without taking a whole pill's width. */
export function Dot({ tone = "neutral", title }: { tone?: Tone; title?: string }) {
  return (
    <span
      title={title}
      className="inline-block h-[7px] w-[7px] shrink-0 rounded-[1px]"
      style={{ background: TONE_VAR[tone] }}
    />
  );
}

/* ----------------------------------------------------------- provenance --- */

const STATUS_TONE: Record<DataStatus, Tone> = {
  LIVE: "ok",
  CACHED_LIVE: "info",
  STALE: "warn",
  SYNTHETIC: "unc",
  UNAVAILABLE: "crit",
};

const STATUS_LABEL: Record<DataStatus, string> = {
  LIVE: "Live",
  CACHED_LIVE: "Cached",
  STALE: "Stale",
  SYNTHETIC: "Synthetic",
  UNAVAILABLE: "No data",
};

export function statusTone(status: DataStatus | null | undefined): Tone {
  return STATUS_TONE[status ?? "UNAVAILABLE"];
}

/**
 * The one component that states where a number came from. Every screen uses it,
 * so nobody has to guess whether a panel is live or replayed.
 */
export function ProvenanceTag({
  status,
  ageHours,
  detail,
  className,
}: {
  status: DataStatus | null | undefined;
  ageHours?: number | null;
  detail?: string;
  className?: string;
}) {
  const resolved: DataStatus = status ?? "UNAVAILABLE";
  const age = formatAge(ageHours);
  return (
    <Pill
      tone={STATUS_TONE[resolved]}
      title={detail ?? `Data status: ${resolved}`}
      className={className}
    >
      {STATUS_LABEL[resolved]}
      {age ? <span className="num font-normal opacity-80">{age}</span> : null}
    </Pill>
  );
}

/* ---------------------------------------------------------------- gauges -- */

export function MiniBar({
  value,
  tone = "info",
  height = 3,
  title,
}: {
  value: number | null | undefined;
  tone?: Tone;
  height?: number;
  title?: string;
}) {
  const pct = value == null || Number.isNaN(value) ? 0 : Math.min(100, Math.max(0, value * 100));
  return (
    <div
      title={title}
      className="w-full overflow-hidden rounded-[1px] bg-[var(--panel-3)]"
      style={{ height }}
    >
      <div className="h-full" style={{ width: `${pct}%`, background: TONE_VAR[tone] }} />
    </div>
  );
}

/* ------------------------------------------------------------------ rows -- */

export function KeyValue({
  label,
  children,
  hint,
  dense = false,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
  dense?: boolean;
}) {
  return (
    <div
      title={hint}
      className={cn(
        "flex items-baseline justify-between gap-3 border-b border-[var(--line)]/60 last:border-0",
        dense ? "py-[3px]" : "py-1.5",
      )}
    >
      <span className="min-w-0 truncate text-[11.5px] text-[var(--text-3)]">{label}</span>
      <span className="shrink-0 text-right text-[12px] text-[var(--text)]">{children}</span>
    </div>
  );
}

/* ------------------------------------------------------------ risk tones -- */

export function riskTone(risk: string | null | undefined): Tone {
  switch ((risk ?? "").toLowerCase()) {
    case "severe":
      return "crit";
    case "congested":
    case "high":
      return "warn";
    case "medium":
    case "watch":
      return "info";
    case "lowconf":
      return "unc";
    default:
      return "ok";
  }
}

export function riskLabel(risk: string | null | undefined): string {
  switch ((risk ?? "").toLowerCase()) {
    case "severe":
      return "Severe";
    case "congested":
      return "Congested";
    case "high":
      return "High";
    case "medium":
      return "Watch";
    case "normal":
      return "Normal";
    default:
      return risk ? risk.charAt(0).toUpperCase() + risk.slice(1).toLowerCase() : "Normal";
  }
}

export function severityTone(severity: string | null | undefined): Tone {
  switch ((severity ?? "").toLowerCase()) {
    case "critical":
    case "severe":
      return "crit";
    case "high":
      return "warn";
    case "medium":
    case "moderate":
    case "mod":
      return "info";
    case "watch":
    case "low":
      return "neutral";
    default:
      return "neutral";
  }
}
