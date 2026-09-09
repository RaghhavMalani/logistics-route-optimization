/**
 * Floating chrome for a map-first workspace.
 *
 * Every panel in these screens sits over the chart rather than beside it. That
 * is the whole layout decision: the map is the product, so it gets the full
 * frame, and the panels are furniture that can be folded away. They are opaque
 * enough to read against moving traffic and bounded in height so they never
 * become a second page.
 */

import { ChevronDown, X } from "lucide-react";
import { useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

export function FloatPanel({
  title,
  note,
  actions,
  children,
  className,
  width,
  collapsible = false,
  defaultOpen = true,
  onClose,
  scroll = true,
  footer,
  testId,
}: {
  title?: ReactNode;
  note?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  width?: number;
  collapsible?: boolean;
  defaultOpen?: boolean;
  onClose?: () => void;
  scroll?: boolean;
  footer?: ReactNode;
  /** Stable hook for the browser suite. */
  testId?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section
      data-testid={testId}
      style={width ? { width } : undefined}
      className={cn(
        "pointer-events-auto flex min-h-0 flex-col overflow-hidden rounded-[3px]",
        "border border-[var(--line-strong)] bg-[var(--panel)]/95 backdrop-blur-[3px]",
        "shadow-[0_10px_30px_rgba(0,0,0,0.45)]",
        className,
      )}
    >
      {title ? (
        <header className="flex h-[26px] shrink-0 items-center gap-2 border-b border-[var(--line)] bg-[var(--panel-2)]/85 px-2">
          {collapsible ? (
            /* The whole header is the control when a panel folds: a bare
               chevron has no accessible name, and "the thing you click to open
               Layers and filters" should be called that. */
            <button
              type="button"
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
              className="flex min-w-0 flex-1 items-center gap-2 text-left text-[10px] font-semibold uppercase tracking-[0.09em] text-[var(--text-2)] hover:text-[var(--text)]"
            >
              <ChevronDown
                size={12}
                className={cn("shrink-0 transition-transform", open ? "" : "-rotate-90")}
              />
              <span className="min-w-0 flex-1 truncate">{title}</span>
            </button>
          ) : (
            <span className="min-w-0 flex-1 truncate text-[10px] font-semibold uppercase tracking-[0.09em] text-[var(--text-2)]">
              {title}
            </span>
          )}
          {note ? (
            <span className="shrink-0 text-[10px] text-[var(--text-3)]">{note}</span>
          ) : null}
          {actions}
          {onClose ? (
            <button
              type="button"
              aria-label="Close panel"
              onClick={onClose}
              className="shrink-0 text-[var(--text-3)] hover:text-[var(--text)]"
            >
              <X size={12} />
            </button>
          ) : null}
        </header>
      ) : null}
      {open ? (
        <div className={cn("min-h-0 flex-1", scroll ? "overflow-y-auto" : "overflow-hidden")}>
          {children}
        </div>
      ) : null}
      {open && footer ? (
        <div className="shrink-0 border-t border-[var(--line)] bg-[var(--panel-2)]/70 px-2 py-1 text-[9.5px] leading-snug text-[var(--text-3)]">
          {footer}
        </div>
      ) : null}
    </section>
  );
}

export function PanelTabs<T extends string>({
  value,
  onChange,
  tabs,
}: {
  value: T;
  onChange: (next: T) => void;
  tabs: Array<{ value: T; label: string; count?: number }>;
}) {
  return (
    <div role="tablist" className="flex shrink-0 border-b border-[var(--line)] bg-[var(--panel-2)]/60">
      {tabs.map((tab) => {
        const active = tab.value === value;
        return (
          <button
            key={tab.value}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onChange(tab.value)}
            className={cn(
              "relative flex-1 px-2 py-[5px] text-[10.5px] font-medium transition-colors",
              active
                ? "text-[var(--text)]"
                : "text-[var(--text-3)] hover:text-[var(--text-2)]",
            )}
          >
            {tab.label}
            {tab.count != null ? (
              <span className="num ml-1 text-[9.5px] text-[var(--text-3)]">{tab.count}</span>
            ) : null}
            {active ? (
              <span className="absolute inset-x-0 bottom-0 h-[1.5px] bg-[var(--info)]" />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

/** A label/value row tuned for an inspector: dense, aligned, quiet. */
export function Field({
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
      title={hint}
      className="flex items-baseline justify-between gap-3 border-b border-[var(--line)]/50 py-[3.5px] last:border-0"
    >
      <span className="min-w-0 truncate text-[10.5px] text-[var(--text-3)]">{label}</span>
      <span className="shrink-0 text-right text-[11.5px] text-[var(--text)]">{children}</span>
    </div>
  );
}

export function PanelSection({
  title,
  right,
  children,
}: {
  title: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="border-b border-[var(--line)] last:border-0">
      <div className="flex h-[22px] items-center justify-between gap-2 px-2">
        <span className="eyebrow truncate text-[9px]">{title}</span>
        {right ? <span className="shrink-0 text-[9.5px] text-[var(--text-3)]">{right}</span> : null}
      </div>
      <div className="px-2 pb-2">{children}</div>
    </div>
  );
}

export function Chip({
  active,
  onClick,
  children,
  color,
  title,
  disabled,
}: {
  active?: boolean;
  onClick?: () => void;
  children: ReactNode;
  color?: string;
  title?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[2px] border px-1.5 py-[2px] text-[10px] transition-colors",
        disabled && "cursor-not-allowed opacity-40",
        active
          ? "border-[var(--line-strong)] bg-[var(--panel-4)] text-[var(--text)]"
          : "border-[var(--line)] bg-transparent text-[var(--text-3)] hover:text-[var(--text-2)]",
      )}
    >
      {color ? (
        <span
          aria-hidden
          className="h-[7px] w-[7px] shrink-0 rounded-[1px]"
          style={{ background: active ? color : "transparent", boxShadow: `inset 0 0 0 1px ${color}` }}
        />
      ) : null}
      {children}
    </button>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return (
    <p className="px-2 py-3 text-[11px] leading-relaxed text-[var(--text-3)]">{children}</p>
  );
}
