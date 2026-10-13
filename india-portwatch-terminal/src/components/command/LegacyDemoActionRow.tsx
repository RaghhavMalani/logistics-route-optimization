// Compatibility for the retained October preview; not used by restored routes.
import { exposureTone } from "@/components/globaleye/EventPanels";
import { Pill, formatUtc } from "@/components/kit/primitives";
import { cn } from "@/lib/utils";
import type { CompanyRiskRow } from "@/types/portwatch-os";

export function ActionRow({
  row,
  index,
  onSelect,
  selected,
}: {
  row: CompanyRiskRow;
  index: number;
  onSelect: () => void;
  selected: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      data-testid="action-required-row"
      className={cn(
        "block w-full border-b border-[var(--line)]/60 px-2 py-1.5 text-left transition-colors last:border-0",
        selected ? "bg-[var(--panel-3)]" : "hover:bg-[var(--panel-2)]",
      )}
    >
      <div className="flex items-baseline gap-2">
        <span className="num shrink-0 text-[10px] text-[var(--text-3)]">
          {String(index + 1).padStart(2, "0")}
        </span>
        <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-[var(--text)]">
          {row.vesselName}
        </span>
        <span
          className={cn(
            "num shrink-0 text-[11px]",
            `text-[var(--${exposureTone(row.exposure)})]`,
          )}
        >
          {row.exposure.toFixed(2)}
        </span>
      </div>

      <div className="mt-[3px] text-[10.5px] leading-snug text-[var(--text-2)]">
        {row.eventCategoryLabel} · {row.chokepoint.replace(/_/g, "-")}
      </div>

      <div className="mt-[3px] flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10.5px] text-[var(--text-3)]">
        {row.hoursToRiskArea != null ? (
          <span className="num">
            {row.hoursToRiskArea.toFixed(0)}h to the risk area
          </span>
        ) : null}
        {row.delayHoursIfDiverted != null ? (
          <span className="num">
            diversion costs {row.delayHoursIfDiverted.toFixed(0)}h
          </span>
        ) : null}
        {row.destinationPort ? (
          <span className="num">→ {row.destinationPort}</span>
        ) : null}
      </div>

      <div className="mt-1 flex items-center gap-1.5">
        <Pill
          tone={
            row.recommendedAction === "evaluate_diversion" ? "warn" : "info"
          }
        >
          {row.recommendedAction.replace(/_/g, " ")}
        </Pill>
        {row.diversionDeadline ? (
          <span className="num text-[10.5px] text-[var(--warn)]">
            by {formatUtc(row.diversionDeadline)}
          </span>
        ) : null}
      </div>
    </button>
  );
}
