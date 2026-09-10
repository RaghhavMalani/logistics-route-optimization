/**
 * Page furniture.
 *
 * The deliberate omission here is the card. Operational screens are read as
 * columns and rows, so structure comes from hairlines and headers -- a `Panel`
 * is a bordered region with a header, and it does not nest inside another one.
 */

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { TONE_TEXT, TONE_VAR, type Tone } from "./primitives";

/* ------------------------------------------------------------ page frame -- */

/** Full-height workspace column: a fixed header strip over a scroll region. */
export function Page({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex h-full min-h-0 flex-col bg-[var(--bg)]", className)}>
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  context,
  meta,
  actions,
}: {
  title: string;
  context?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex h-[46px] shrink-0 items-center gap-4 border-b border-[var(--line)] bg-[var(--panel)] px-4">
      <div className="flex min-w-0 items-baseline gap-3">
        <h1 className="truncate text-[15px] font-semibold tracking-[-0.01em] text-[var(--text)]">
          {title}
        </h1>
        {context ? (
          <div className="flex min-w-0 items-center gap-2 text-[12px] text-[var(--text-3)]">
            {context}
          </div>
        ) : null}
      </div>
      {meta ? (
        <div className="ml-auto flex shrink-0 items-center gap-4 text-[11px] text-[var(--text-3)]">
          {meta}
        </div>
      ) : null}
      {actions ? (
        <div className={cn("flex shrink-0 items-center gap-2", !meta && "ml-auto")}>
          {actions}
        </div>
      ) : null}
    </header>
  );
}

/** The scrolling body of a page. */
export function PageBody({
  children,
  className,
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <div
      className={cn(
        "min-h-0 flex-1 overflow-auto",
        padded && "p-3",
        className,
      )}
    >
      {children}
    </div>
  );
}

/* ---------------------------------------------------------------- panels -- */

export function Panel({
  title,
  note,
  actions,
  children,
  className,
  bodyClassName,
  scroll = false,
  testId,
}: {
  title?: ReactNode;
  note?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  scroll?: boolean;
  /** Stable hook for the browser suite. */
  testId?: string;
}) {
  return (
    <section
      data-testid={testId}
      className={cn("panel flex min-h-0 min-w-0 flex-col overflow-hidden", className)}
    >
      {title ? (
        <div className="panel-head">
          <span className="min-w-0 truncate">{title}</span>
          <span className="flex shrink-0 items-center gap-2 text-[10px] font-normal normal-case tracking-normal text-[var(--text-3)]">
            {note}
            {actions}
          </span>
        </div>
      ) : null}
      <div
        className={cn(
          "min-h-0 flex-1",
          scroll ? "overflow-auto" : "overflow-hidden",
          bodyClassName,
        )}
      >
        {children}
      </div>
    </section>
  );
}

/** A titled band inside a panel — hairline separation, no second border box. */
export function Section({
  title,
  right,
  children,
  className,
}: {
  title: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("border-b border-[var(--line)] last:border-0", className)}>
      <div className="flex h-[26px] items-center justify-between gap-2 px-3">
        <span className="eyebrow truncate">{title}</span>
        {right ? <span className="shrink-0 text-[10px] text-[var(--text-3)]">{right}</span> : null}
      </div>
      <div className="px-3 pb-3">{children}</div>
    </div>
  );
}

/* ----------------------------------------------------------------- stats -- */

export interface StatItem {
  label: string;
  value: ReactNode;
  unit?: string;
  tone?: Tone;
  note?: ReactNode;
}

/** A row of measurements divided by hairlines, not a row of cards. */
export function StatStrip({
  items,
  className,
  size = "lg",
}: {
  items: StatItem[];
  className?: string;
  size?: "lg" | "sm";
}) {
  return (
    <div
      className={cn(
        "grid divide-x divide-[var(--line)] border-y border-[var(--line)] bg-[var(--panel)]",
        className,
      )}
      style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}
    >
      {items.map((item) => (
        <div key={item.label} className={cn("min-w-0", size === "lg" ? "px-4 py-2.5" : "px-3 py-2")}>
          <div className="eyebrow truncate">{item.label}</div>
          <div className="mt-1 flex items-baseline gap-1">
            <span
              className={cn(size === "lg" ? "metric-xl" : "metric-lg")}
              style={{ color: item.tone ? TONE_VAR[item.tone] : "var(--text)" }}
            >
              {item.value}
            </span>
            {item.unit ? (
              <span className="text-[11px] text-[var(--text-3)]">{item.unit}</span>
            ) : null}
          </div>
          {item.note ? (
            <div className="mt-0.5 truncate text-[11px] text-[var(--text-3)]">{item.note}</div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

/** A compact figure for use inside a panel body. */
export function Stat({
  label,
  value,
  unit,
  tone,
  note,
}: StatItem) {
  return (
    <div className="min-w-0">
      <div className="eyebrow truncate">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-1">
        <span className={cn("metric-lg", tone && TONE_TEXT[tone])}>{value}</span>
        {unit ? <span className="text-[11px] text-[var(--text-3)]">{unit}</span> : null}
      </div>
      {note ? <div className="truncate text-[11px] text-[var(--text-3)]">{note}</div> : null}
    </div>
  );
}

/* --------------------------------------------------------------- toolbar -- */

export function Toolbar({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "flex h-[34px] shrink-0 items-center gap-2 border-b border-[var(--line)] bg-[var(--panel)] px-3",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (next: T) => void;
  ariaLabel?: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="flex overflow-hidden rounded-[2px] border border-[var(--line-strong)]"
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "px-2.5 py-[3px] text-[11px] font-medium transition-colors",
              active
                ? "bg-[var(--panel-4)] text-[var(--text)]"
                : "bg-transparent text-[var(--text-3)] hover:bg-[var(--panel-3)] hover:text-[var(--text-2)]",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function SelectControl({
  value,
  options,
  onChange,
  ariaLabel,
  className,
}: {
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (next: string) => void;
  ariaLabel: string;
  className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <select
        aria-label={ariaLabel}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          "w-full appearance-none rounded-[2px] border border-[var(--line-strong)] bg-[var(--panel-2)]",
          "py-[4px] pl-2 pr-7 text-[12px] text-[var(--text)] outline-none",
          "hover:border-[#35505f] focus:border-[var(--info)]",
        )}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} className="bg-[var(--panel-2)]">
            {option.label}
          </option>
        ))}
      </select>
      <svg
        className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-3)]"
        width="9"
        height="9"
        viewBox="0 0 10 10"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
      >
        <path d="M2 4l3 3 3-3" />
      </svg>
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "default",
  type = "button",
  disabled,
  className,
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "default" | "primary" | "ghost";
  type?: "button" | "submit";
  disabled?: boolean;
  className?: string;
  title?: string;
}) {
  return (
    <button
      type={type}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-[2px] px-2.5 py-[5px]",
        "text-[11.5px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45",
        variant === "primary" &&
          "bg-[var(--info)] text-[#04121b] hover:bg-[#5cb0dc]",
        variant === "default" &&
          "border border-[var(--line-strong)] bg-[var(--panel-2)] text-[var(--text-2)] hover:border-[#35505f] hover:text-[var(--text)]",
        variant === "ghost" && "text-[var(--text-3)] hover:text-[var(--text)]",
        className,
      )}
    >
      {children}
    </button>
  );
}
