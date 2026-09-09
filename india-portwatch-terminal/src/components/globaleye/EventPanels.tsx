/**
 * Global Eye: the event register and the impact chain.
 *
 * The chain is the product. A list of headlines is trivia; the value is in
 * showing, in one column, how a report in the Red Sea becomes a berth problem
 * at JNPA in eleven hours. So `ImpactChain` renders the hops vertically with the
 * count at each, and every hop states the measurement behind it.
 *
 * Two things are drawn differently on purpose:
 *
 *   A missing probability is a sentence, not a blank. An uncalibrated category
 *   says why, so an operator learns that the system is withholding rather than
 *   that the risk is zero.
 *
 *   A vessel that has already entered the risk area gets a distinct row style
 *   and never a diversion action. That is the whole timing gate, made visible.
 */

import { ArrowRight, Clock, ShieldAlert, Ship } from "lucide-react";
import type { ReactNode } from "react";

import { Pill, formatUtc, type Tone } from "@/components/kit/primitives";
import { cn } from "@/lib/utils";
import type {
  EventImpact,
  GlobalEvent,
  LaneExposure,
  PortExposure,
  VesselExposure,
} from "@/types/portwatch-os";

/* ------------------------------------------------------------------ tone -- */

export function severityTone(severity: number): Tone {
  if (severity >= 0.7) return "crit";
  if (severity >= 0.45) return "warn";
  return "info";
}

export function exposureTone(exposure: number): Tone {
  if (exposure >= 0.55) return "crit";
  if (exposure >= 0.3) return "warn";
  return "info";
}

const GROUP_TONE: Record<string, Tone> = {
  security: "crit",
  chokepoint: "warn",
  natural: "warn",
  operations: "info",
  policy: "unc",
  market: "unc",
};

export function groupTone(group: string): Tone {
  return GROUP_TONE[group] ?? "neutral";
}

/* ----------------------------------------------------------------- rows -- */

export function EventRow({
  event,
  selected,
  onSelect,
  exposure,
}: {
  event: GlobalEvent;
  selected?: boolean;
  onSelect?: () => void;
  /** Worst exposure this event carries, where it has been computed. */
  exposure?: number | null;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      data-testid="global-event-row"
      className={cn(
        "block w-full border-b border-[var(--line)]/60 px-2 py-1.5 text-left transition-colors last:border-0",
        selected ? "bg-[var(--panel-3)]" : "hover:bg-[var(--panel-2)]",
      )}
    >
      <div className="flex items-start gap-2">
        <span
          aria-hidden
          className="mt-[5px] h-[7px] w-[7px] shrink-0 rounded-full"
          style={{ background: `var(--${severityTone(event.severity)})` }}
        />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[11.5px] leading-tight text-[var(--text)]">
            {event.title}
          </div>
          <div className="mt-[3px] flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9.5px] text-[var(--text-3)]">
            <Pill tone={groupTone(event.categoryGroup)}>{event.categoryLabel}</Pill>
            {event.region ? <span className="truncate">{event.region}</span> : null}
            <span className="num" title="Distinct outlets that reported this">
              {event.sourceCount} src
            </span>
            <span className="num" title="Severity × corroboration">
              sev {event.severity.toFixed(2)}
            </span>
            <span className="num">conf {event.confidence.toFixed(2)}</span>
            {exposure != null ? (
              <span className={cn("num", `text-[var(--${exposureTone(exposure)})]`)}>
                exp {exposure.toFixed(2)}
              </span>
            ) : null}
          </div>
        </div>
        <span className="num shrink-0 text-[9.5px] text-[var(--text-3)]">
          {formatUtc(event.lastSeen)}
        </span>
      </div>
    </button>
  );
}

/* --------------------------------------------------------- probability -- */

export function ProbabilityBadge({ event }: { event: GlobalEvent }) {
  if (event.probability == null) {
    return (
      <div className="rounded-[2px] border border-dashed border-[var(--line-strong)] px-2 py-1.5">
        <div className="flex items-center gap-1.5">
          <Pill tone="unc">No calibrated probability</Pill>
        </div>
        <p className="mt-1 text-[10px] leading-snug text-[var(--text-3)]">
          {event.calibrationNote ??
            "Not enough resolved outcomes in this category to state a probability. Severity and corroboration are shown instead."}
        </p>
      </div>
    );
  }
  return (
    <div className="rounded-[2px] border border-[var(--line-strong)] bg-[var(--panel-2)] px-2 py-1.5">
      <div className="flex items-baseline gap-2">
        <span className="num text-[20px] leading-none text-[var(--text)]">
          {(event.probability * 100).toFixed(0)}%
        </span>
        <span className="text-[10px] text-[var(--text-2)]">
          {event.claim ?? "operational impact"}
        </span>
        <span className="num ml-auto text-[9.5px] text-[var(--text-3)]">
          within {event.horizonHours.toFixed(0)}h
        </span>
      </div>
      <p className="mt-1 text-[9.5px] leading-snug text-[var(--text-3)]">
        {event.calibrationNote}
      </p>
    </div>
  );
}

/* -------------------------------------------------------------- chain --- */

function Hop({
  index,
  label,
  count,
  unit,
  tone = "neutral",
  children,
  basis,
}: {
  index: number;
  label: string;
  count: number | string;
  unit?: string;
  tone?: Tone;
  children?: ReactNode;
  basis: string;
}) {
  return (
    <li className="relative pl-5">
      {/* The spine. Drawn as a border rather than a pseudo-element so the last
          hop can stop it cleanly without a wrapper. */}
      <span
        aria-hidden
        className="absolute left-[6px] top-[14px] bottom-0 w-px bg-[var(--line-strong)] last:hidden"
      />
      <span
        aria-hidden
        className="absolute left-0 top-[7px] grid h-[13px] w-[13px] place-items-center rounded-full border border-[var(--line-strong)] bg-[var(--panel)]"
      >
        <span
          className="h-[5px] w-[5px] rounded-full"
          style={{ background: `var(--${tone})` }}
        />
      </span>
      <div className="pb-2.5">
        <div className="flex items-baseline gap-2">
          <span className="eyebrow text-[8.5px]">{label}</span>
          <span className="num text-[13px] leading-none text-[var(--text)]">
            {count}
            {unit ? (
              <span className="ml-0.5 text-[9px] text-[var(--text-3)]">{unit}</span>
            ) : null}
          </span>
        </div>
        <p className="mt-[2px] text-[10px] leading-snug text-[var(--text-3)]">{basis}</p>
        {children}
      </div>
    </li>
  );
}

export function ImpactChain({ impact }: { impact: EventImpact }) {
  const committed = impact.vessels.filter((v) => v.alreadyEntered);
  const actionable = impact.vessels.filter((v) => !v.alreadyEntered);

  return (
    <ol className="px-2 py-1.5" data-testid="impact-chain">
      <Hop
        index={0}
        label="Event"
        count={impact.sourceCount}
        unit="sources"
        tone={severityTone(impact.severity)}
        basis={`${impact.categoryLabel} · severity ${impact.severity.toFixed(2)} · confidence ${impact.confidence.toFixed(2)}`}
      />
      <Hop
        index={1}
        label="Chokepoints"
        count={impact.chokepoints.length}
        tone={impact.chokepoints.length ? "warn" : "neutral"}
        basis={
          impact.chokepoints.length
            ? impact.chokepoints.join(", ").replace(/_/g, "-")
            : "No chokepoint in the catalogue matches this event, so no lane exposure follows."
        }
      />
      <Hop
        index={2}
        label="Trade lanes"
        count={impact.lanes.length}
        tone={impact.lanes.length ? exposureTone(impact.worstExposure) : "neutral"}
        basis={
          impact.lanes.length
            ? "Lanes whose primary routing transits an affected chokepoint."
            : "No lane in the catalogue transits an affected chokepoint."
        }
      >
        {impact.lanes.length ? (
          <div className="mt-1 space-y-[3px]">
            {impact.lanes.slice(0, 4).map((lane) => (
              <LaneRow key={`${lane.laneCode}-${lane.chokepoint}`} lane={lane} />
            ))}
          </div>
        ) : null}
      </Hop>
      <Hop
        index={3}
        label="Vessels"
        count={impact.vessels.length}
        tone={actionable.length ? "warn" : impact.vessels.length ? "unc" : "neutral"}
        basis={
          impact.vessels.length
            ? `${actionable.length} can still divert · ${committed.length} already inside the exposed water`
            : "No fleet is in scope, so no vessel-level exposure is computed."
        }
      />
      <Hop
        index={4}
        label="Ports"
        count={impact.ports.length}
        tone={impact.ports.length ? exposureTone(impact.ports[0]?.exposure ?? 0) : "neutral"}
        basis={
          impact.ports.length
            ? impact.ports.slice(0, 4).map((p) => `${p.portCode} ${p.exposure.toFixed(2)}`).join(" · ")
            : "No Indian port is reached by an exposed lane."
        }
      />
      <Hop
        index={5}
        label="Actions"
        count={impact.actions.length}
        tone={impact.actions.length ? "info" : "neutral"}
        basis={
          impact.actions.length
            ? "Each action names the measurement that justifies it."
            : "The chain supports no action: nothing measurable follows from this event."
        }
      />
    </ol>
  );
}

export function LaneRow({ lane }: { lane: LaneExposure }) {
  return (
    <div className="rounded-[2px] border border-[var(--line)] px-1.5 py-1">
      <div className="flex items-baseline gap-1.5">
        <span className="min-w-0 flex-1 truncate text-[10.5px] text-[var(--text-2)]">
          {lane.laneName}
        </span>
        <span className={cn("num text-[10.5px]", `text-[var(--${exposureTone(lane.exposure)})]`)}>
          {lane.exposure.toFixed(2)}
        </span>
      </div>
      <div className="mt-[2px] flex items-center gap-1.5 text-[9px] text-[var(--text-3)]">
        {lane.alternative ? (
          <>
            <span className="truncate">via {lane.alternative}</span>
            <ArrowRight size={8} className="shrink-0" />
            <span className="num shrink-0">
              +{lane.detourNm?.toLocaleString()} nm · +{lane.detourHours?.toFixed(0)} h
            </span>
          </>
        ) : (
          <span className="text-[var(--crit)]">No alternative routing exists</span>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- vessels -- */

export function VesselExposureRow({
  row,
  onSelect,
  selected,
}: {
  row: VesselExposure & { eventTitle?: string; eventCategoryLabel?: string };
  onSelect?: () => void;
  selected?: boolean;
}) {
  const committed = row.alreadyEntered;
  return (
    <button
      type="button"
      onClick={onSelect}
      data-testid="vessel-exposure-row"
      className={cn(
        "block w-full border-b border-[var(--line)]/60 px-2 py-1.5 text-left transition-colors last:border-0",
        selected ? "bg-[var(--panel-3)]" : "hover:bg-[var(--panel-2)]",
        // A committed vessel is deliberately quieter: nothing can be done about
        // it, and it must not compete for attention with the ones that can.
        committed && "opacity-70",
      )}
    >
      <div className="flex items-baseline gap-2">
        {committed ? (
          <ShieldAlert size={11} className="shrink-0 text-[var(--unc)]" />
        ) : (
          <Ship size={11} className="shrink-0 text-[var(--warn)]" />
        )}
        <span className="min-w-0 flex-1 truncate text-[11.5px] text-[var(--text)]">
          {row.vesselName}
        </span>
        <span className={cn("num text-[11px]", `text-[var(--${exposureTone(row.exposure)})]`)}>
          {row.exposure.toFixed(2)}
        </span>
      </div>
      <div className="mt-[2px] flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9.5px] text-[var(--text-3)]">
        {committed ? (
          <Pill tone="unc">In the risk area</Pill>
        ) : row.hoursToRiskArea != null ? (
          <span className="num flex items-center gap-1">
            <Clock size={8} />
            {row.hoursToRiskArea.toFixed(0)}h to {row.chokepoint.replace(/_/g, "-")}
          </span>
        ) : null}
        {row.destinationPort ? <span className="num">→ {row.destinationPort}</span> : null}
        {!committed && row.delayHoursIfDiverted != null ? (
          <span className="num">diversion +{row.delayHoursIfDiverted.toFixed(0)}h</span>
        ) : null}
      </div>
      <p className="mt-[3px] text-[9.5px] leading-snug text-[var(--text-3)]">{row.actionBasis}</p>
    </button>
  );
}

export function PortExposureRow({ row }: { row: PortExposure }) {
  return (
    <div className="flex items-baseline gap-2 border-b border-[var(--line)]/50 py-[3px] last:border-0">
      <span className="num w-[46px] shrink-0 text-[10.5px] text-[var(--text-2)]">
        {row.portCode}
      </span>
      <span className="min-w-0 flex-1 truncate text-[10.5px] text-[var(--text)]">
        {row.portName}
      </span>
      {row.meanArrivalShiftHours != null ? (
        <span className="num shrink-0 text-[10px] text-[var(--text-3)]">
          +{row.meanArrivalShiftHours.toFixed(1)}h
        </span>
      ) : null}
      <span
        className={cn("num shrink-0 text-[11px]", `text-[var(--${exposureTone(row.exposure)})]`)}
      >
        {row.exposure.toFixed(2)}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------- sources -- */

export function SourceList({ event }: { event: GlobalEvent }) {
  const byOutlet = new Map<string, { outlet: string; url: string | null; feed: string }>();
  for (const source of event.sources) {
    if (!byOutlet.has(source.outlet)) {
      byOutlet.set(source.outlet, {
        outlet: source.outlet,
        url: source.url,
        feed: source.feed,
      });
    }
  }

  return (
    <ul className="space-y-[3px]">
      {[...byOutlet.values()].map((source) => (
        <li key={source.outlet} className="flex items-baseline gap-1.5 text-[10px]">
          <span className="num shrink-0 text-[9px] text-[var(--text-3)]">{source.feed}</span>
          {source.url ? (
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer noopener"
              className="min-w-0 flex-1 truncate text-[var(--text-2)] underline-offset-2 hover:text-[var(--text)] hover:underline"
            >
              {source.outlet}
            </a>
          ) : (
            <span className="min-w-0 flex-1 truncate text-[var(--text-2)]">{source.outlet}</span>
          )}
        </li>
      ))}
      {event.reportCount > byOutlet.size ? (
        <li className="text-[9.5px] text-[var(--text-3)]">
          {event.reportCount} reports merged into this event from {byOutlet.size} distinct
          outlets. Confidence is built from the outlet count, not the report count.
        </li>
      ) : null}
    </ul>
  );
}

/* --------------------------------------------------------------- actions -- */

export function ActionList({ actions }: { actions: EventImpact["actions"] }) {
  if (!actions.length) {
    return (
      <p className="px-2 py-3 text-[11px] leading-relaxed text-[var(--text-3)]">
        This event supports no computable action. That is a finding, not a gap: the
        chain reached no vessel or port with a measurable consequence.
      </p>
    );
  }
  return (
    <ul className="space-y-1.5">
      {actions.map((action) => (
        <li
          key={action.action}
          className="rounded-[2px] border border-[var(--line)] px-1.5 py-1"
        >
          <div className="flex items-baseline gap-2">
            <span className="min-w-0 flex-1 text-[11px] text-[var(--text)]">{action.label}</span>
            <span className="num shrink-0 text-[11px] text-[var(--text-2)]">{action.count}</span>
          </div>
          {action.meanCostHours != null ? (
            <div className="num mt-[2px] text-[9.5px] text-[var(--text-3)]">
              mean cost {action.meanCostHours.toFixed(1)} h
              {action.earliestDeadline
                ? ` · earliest deadline ${formatUtc(action.earliestDeadline)}`
                : ""}
            </div>
          ) : null}
          {action.meanShiftHours != null ? (
            <div className="num mt-[2px] text-[9.5px] text-[var(--text-3)]">
              mean arrival shift {action.meanShiftHours.toFixed(1)} h
            </div>
          ) : null}
          <p className="mt-[3px] text-[9.5px] leading-snug text-[var(--text-3)]">{action.basis}</p>
        </li>
      ))}
    </ul>
  );
}
