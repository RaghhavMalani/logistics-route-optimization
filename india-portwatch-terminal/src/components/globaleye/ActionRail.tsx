/**
 * The action rail: at most five things, each one an instruction.
 *
 * This replaces the KPI panel, and the difference is not cosmetic. A KPI tells
 * an operator the state of the world; an action item tells them what to do
 * about it, by when, and what it costs to do nothing. Five is a deliberate cap:
 * a queue nobody can finish is a queue nobody starts.
 *
 * Selecting an item drives the world -- it selects the subject, plays that
 * cascade, and flies the camera. The rail is a control surface, not a table
 * that happens to sit beside a map.
 */

import { Pill, type Tone } from "@/components/kit/primitives";
import { cn } from "@/lib/utils";
import type { AttentionItem, AttentionStatus } from "@/types/portwatch-os";

const STATUS_TONE: Record<AttentionStatus, Tone> = {
  ACT_NOW: "crit",
  ACT_SOON: "warn",
  WATCH: "info",
  // Deliberately not an alarm colour. An exposed hull nobody can help is not an
  // emergency, and colouring it like one trains operators to ignore the colour.
  MONITOR_ONLY: "neutral",
  NO_ACTION_AVAILABLE: "neutral",
};

const STATUS_LABEL: Record<AttentionStatus, string> = {
  ACT_NOW: "ACT NOW",
  ACT_SOON: "ACT SOON",
  WATCH: "WATCH",
  MONITOR_ONLY: "MONITOR",
  NO_ACTION_AVAILABLE: "NO ACTION",
};

/** A window as an operator would say it: "2h 14m", not "2.23 hours". */
export function formatWindow(hours: number | null): string | null {
  if (hours === null || hours <= 0) return null;
  const whole = Math.floor(hours);
  const minutes = Math.round((hours - whole) * 60);
  if (whole === 0) return `${minutes}m`;
  if (minutes === 0) return `${whole}h`;
  return `${whole}h ${minutes}m`;
}

export function ActionRail({
  items,
  selectedId,
  onSelect,
  onInspect,
  total,
  loading,
}: {
  items: AttentionItem[];
  selectedId: string | null;
  onSelect: (item: AttentionItem) => void;
  onInspect: (item: AttentionItem) => void;
  total: number;
  loading?: boolean;
}) {
  if (loading) {
    return (
      <p className="px-2 py-3 text-[10.5px] text-[var(--text-3)]">
        Ranking consequences…
      </p>
    );
  }

  if (items.length === 0) {
    return (
      <p className="px-2 py-3 text-[10.5px] leading-relaxed text-[var(--text-3)]">
        Nothing in the live event register reaches this workspace with an action
        attached. That is a computed absence, not an empty feed.
      </p>
    );
  }

  return (
    <div className="flex flex-col">
      {items.map((item) => {
        const window = formatWindow(item.interventionWindowHours);
        const selected = item.attentionId === selectedId;
        const effect = item.expectedOperationalEffect;
        return (
          <div
            key={item.attentionId}
            data-testid="attention-item"
            data-status={item.status}
            data-subject={item.subjectId}
            className={cn(
              "group relative border-b border-[var(--line)] transition-colors",
              "hover:bg-[var(--surface-2)]",
              selected && "bg-[var(--surface-2)]",
            )}
          >
          <button
            type="button"
            onClick={() => onSelect(item)}
            onDoubleClick={() => onInspect(item)}
            className="w-full px-2 py-2 text-left"
          >
            <div className="flex items-center gap-1.5">
              <Pill tone={STATUS_TONE[item.status]}>{STATUS_LABEL[item.status]}</Pill>
              <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-[var(--text)]">
                {item.subjectLabel}
              </span>
              {window ? (
                <span
                  className="num shrink-0 text-[10px] text-[var(--text-2)]"
                  title="Time until this option closes"
                >
                  {window}
                </span>
              ) : null}
            </div>

            <p className="mt-1 truncate text-[10px] text-[var(--text-2)]">
              {item.recommendedAction?.summary ?? item.doNothingOutcome}
            </p>

            <div className="mt-1 flex items-center gap-2 text-[9.5px] text-[var(--text-3)]">
              {effect.available ? (
                <span className="num truncate">{effect.statement}</span>
              ) : (
                <span className="truncate italic">
                  {effect.unavailableBecause}
                </span>
              )}
              <span className="num ml-auto shrink-0" title="Model confidence">
                {(item.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </button>

          <button
            type="button"
            data-testid="inspect-item"
            onClick={() => onInspect(item)}
            title="Show the computation behind this"
            className={cn(
              "absolute right-1.5 top-1.5 rounded px-1 py-0.5 text-[9px] uppercase tracking-wide",
              "text-[var(--text-3)] opacity-0 transition-opacity",
              "hover:bg-[var(--surface)] hover:text-[var(--text)]",
              "focus:opacity-100 group-hover:opacity-100",
            )}
          >
            why
          </button>
          </div>
        );
      })}

      {total > items.length ? (
        <p className="px-2 py-1.5 text-[9.5px] text-[var(--text-3)]">
          {total - items.length} further ranked below the cut.
        </p>
      ) : null}
    </div>
  );
}
