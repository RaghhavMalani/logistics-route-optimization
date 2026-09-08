/**
 * Loading, empty and failure states.
 *
 * A control room does not want a red wall when a feed drops. It wants to know
 * what is missing, how old the last good state was, and the one command that
 * fixes it -- in the same layout, so the screen does not jump.
 */

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api";
import { Button } from "./layout";
import { Pill, type Tone } from "./primitives";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("pw-skeleton", className)} />;
}

/** Restrained progress: a header bar, a few rows, no spinner theatre. */
export function LoadingPanel({
  label = "Loading",
  rows = 6,
  className,
}: {
  label?: string;
  rows?: number;
  className?: string;
}) {
  return (
    <div className={cn("flex h-full min-h-0 flex-col gap-2 p-3", className)} aria-busy>
      <div className="flex items-center gap-2">
        <span className="pw-breathe h-1.5 w-1.5 rounded-full bg-[var(--info)]" />
        <span className="eyebrow">{label}</span>
      </div>
      <div className="flex flex-col gap-1.5">
        {Array.from({ length: rows }).map((_, index) => (
          <Skeleton
            key={index}
            className="h-[18px] w-full"
            /* Slight width falloff keeps the block from reading as a solid slab. */
          />
        ))}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  detail,
  action,
  tone = "neutral",
}: {
  title: string;
  detail?: ReactNode;
  action?: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="grid h-full min-h-[160px] w-full place-items-center p-6">
      <div className="max-w-[440px] text-center">
        <div className="mb-1.5 flex justify-center">
          <Pill tone={tone}>{title}</Pill>
        </div>
        {detail ? (
          <p className="text-[12px] leading-relaxed text-[var(--text-3)]">{detail}</p>
        ) : null}
        {action ? <div className="mt-3 flex justify-center">{action}</div> : null}
      </div>
    </div>
  );
}

function describe(error: unknown): { headline: string; detail: string } {
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return {
        headline: "Artefact not in this run",
        detail: error.detail,
      };
    }
    if (error.status === 503) {
      return {
        headline: "Operational data service unavailable",
        detail: error.detail,
      };
    }
    return { headline: `Service returned ${error.status}`, detail: error.detail };
  }
  if (error instanceof Error) {
    return {
      headline: "Operational data service unavailable",
      detail: error.message,
    };
  }
  return { headline: "Operational data service unavailable", detail: "Unknown fault." };
}

/**
 * Inline failure. It states what is unreachable and what restores it, and it
 * stays inside the panel that failed rather than taking the screen.
 */
export function FailureState({
  error,
  retry,
  lastGood,
  hint,
}: {
  error: unknown;
  retry?: () => void;
  /** Age of the newest state the operator can still trust, if any. */
  lastGood?: { label: string; age?: string | null } | null;
  hint?: string;
}) {
  const { headline, detail } = describe(error);
  return (
    <div className="flex h-full min-h-[140px] w-full items-center justify-center p-5">
      <div className="w-full max-w-[520px]">
        <div className="mb-2 flex items-center gap-2">
          <Pill tone="crit">Feed down</Pill>
          <span className="text-[13px] font-medium text-[var(--text)]">{headline}</span>
        </div>
        <p className="text-[12px] leading-relaxed text-[var(--text-3)]">{detail}</p>
        {lastGood ? (
          <div className="mt-2.5 flex items-center gap-2 border-t border-[var(--line)] pt-2.5 text-[11.5px] text-[var(--text-3)]">
            <span className="eyebrow">Last known good</span>
            <span className="text-[var(--text-2)]">{lastGood.label}</span>
            {lastGood.age ? <span className="num text-[var(--warn)]">{lastGood.age}</span> : null}
          </div>
        ) : null}
        <div className="mt-3 flex items-center gap-2">
          {retry ? (
            <Button variant="default" onClick={retry}>
              Retry
            </Button>
          ) : null}
          <code className="truncate rounded-[2px] bg-[var(--panel-2)] px-2 py-[5px] font-mono text-[10.5px] text-[var(--text-3)]">
            {hint ?? "uvicorn backend.app.main:app --reload --port 8000"}
          </code>
        </div>
      </div>
    </div>
  );
}

/** Wraps a query result so the three states are handled in one place. */
export function QueryBoundary({
  isLoading,
  error,
  retry,
  label,
  children,
  rows,
}: {
  isLoading: boolean;
  error: unknown;
  retry?: () => void;
  label?: string;
  children: ReactNode;
  rows?: number;
}) {
  if (isLoading) return <LoadingPanel label={label ?? "Loading"} rows={rows} />;
  if (error) return <FailureState error={error} retry={retry} />;
  return <>{children}</>;
}
