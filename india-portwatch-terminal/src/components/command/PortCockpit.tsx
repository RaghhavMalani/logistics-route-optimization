/**
 * The port controller's cockpit.
 *
 * Four things a duty controller actually needs, in the order they need them:
 * who is out there and what they are doing, who arrives next and whether the
 * berths can take them, what the weather will do to the next shift, and what the
 * decision layer wants done about it.
 *
 * The arrival sequence is the piece worth arguing over. It runs a deterministic
 * berth queue across the predicted arrivals, using the departures the traffic
 * source already knows about to decide when each berth frees. The recommended
 * arrival is the same berthing slot reached by steaming slower -- so the panel
 * can show, in hours, what staggering buys.
 */

import { useMemo, useState } from "react";

import { useTrafficTick } from "@/components/app/traffic-context";
import { Num, Pill, ProvenanceTag, riskTone } from "@/components/kit/primitives";
import { formatDuration } from "@/lib/maritime/geo";
import { waypoint } from "@/lib/maritime/searoutes";
import {
  NAV_STATUS_LABEL,
  VESSEL_CLASSES,
  type NavStatus,
  type VesselFix,
} from "@/lib/maritime/traffic-types";
import {
  distanceNm,
  STATUS_TONE,
  type ArrivalPlan,
  type PortTraffic,
} from "@/lib/maritime/traffic-views";
import { sampleField } from "@/lib/maritime/weather-field";
import type { WeatherTimeline } from "@/lib/maritime/weather-model";
import { cn } from "@/lib/utils";
import type { Decision, PortSnapshot } from "@/types/portwatch";
import { EmptyNote, Field, PanelSection } from "./panels";

function clockZ(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "—";
  const date = new Date(ms);
  return `${String(date.getUTCHours()).padStart(2, "0")}:${String(date.getUTCMinutes()).padStart(2, "0")}`;
}

/* --------------------------------------------------------- traffic board -- */

type SortKey = "eta" | "distance" | "speed" | "wait" | "risk" | "name";

const COLUMNS: Array<{ key: SortKey | null; label: string; className: string }> = [
  { key: "name", label: "Vessel", className: "w-[142px]" },
  { key: null, label: "Type", className: "w-[64px]" },
  { key: null, label: "Status", className: "w-[62px]" },
  { key: "speed", label: "SOG", className: "w-[46px] text-right" },
  { key: null, label: "COG", className: "w-[42px] text-right" },
  { key: null, label: "From", className: "w-[86px]" },
  { key: null, label: "To", className: "w-[86px]" },
  { key: "eta", label: "ETA", className: "w-[46px] text-right" },
  { key: "distance", label: "Dist", className: "w-[50px] text-right" },
  { key: "wait", label: "Wait", className: "w-[46px] text-right" },
  { key: "risk", label: "Risk", className: "w-[52px]" },
  { key: null, label: "Action", className: "min-w-[124px]" },
];

export function TrafficBoard({
  traffic,
  plan,
  port,
  selectedId,
  onSelect,
  onHover,
  className,
}: {
  traffic: PortTraffic;
  plan: ArrivalPlan;
  port: PortSnapshot;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onHover?: (id: string | null) => void;
  className?: string;
}) {
  const [sort, setSort] = useState<SortKey>("eta");
  const [descending, setDescending] = useState(false);

  const slotFor = useMemo(
    () => new Map(plan.slots.map((slot) => [slot.fix.id, slot])),
    [plan.slots],
  );

  const rows = useMemo(() => {
    const list = [...traffic.all];
    const value = (fix: VesselFix) => {
      const slot = slotFor.get(fix.id);
      switch (sort) {
        case "eta":
          return fix.etaMs ?? Number.MAX_SAFE_INTEGER;
        case "distance":
          return port.location ? distanceNm(fix, port.location) : 0;
        case "speed":
          return fix.sogKn;
        case "wait":
          return slot?.waitHours ?? -1;
        case "risk":
          return slot ? { low: 0, medium: 1, high: 2 }[slot.risk] : -1;
        default:
          return 0;
      }
    };
    list.sort((a, b) => {
      if (sort === "name") return descending ? b.name.localeCompare(a.name) : a.name.localeCompare(b.name);
      const delta = value(a) - value(b);
      return descending ? -delta : delta;
    });
    return list;
  }, [descending, port.location, slotFor, sort, traffic.all]);

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div className="grid shrink-0 grid-cols-[142px_64px_62px_46px_42px_86px_86px_46px_50px_46px_52px_minmax(124px,1fr)] items-center gap-1.5 border-b border-[var(--line)] bg-[var(--panel-2)]/80 px-2 py-[3px]">
        {COLUMNS.map((column) => (
          <button
            key={column.label}
            type="button"
            disabled={!column.key}
            onClick={() => {
              if (!column.key) return;
              if (sort === column.key) setDescending((v) => !v);
              else {
                setSort(column.key);
                setDescending(false);
              }
            }}
            className={cn(
              "eyebrow truncate text-[8.5px]",
              column.className,
              column.key ? "hover:text-[var(--text-2)]" : "cursor-default",
              sort === column.key && "text-[var(--info)]",
            )}
          >
            {column.label}
            {sort === column.key ? (descending ? " ↓" : " ↑") : ""}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {rows.length === 0 ? (
          <EmptyNote>No traffic within the approach at this time.</EmptyNote>
        ) : (
          rows.map((fix) => {
            const slot = slotFor.get(fix.id);
            const spec = VESSEL_CLASSES[fix.vesselClass];
            return (
              <button
                key={fix.id}
                type="button"
                onClick={() => onSelect(fix.id)}
                onMouseEnter={() => onHover?.(fix.id)}
                onMouseLeave={() => onHover?.(null)}
                className={cn(
                  "grid w-full grid-cols-[142px_64px_62px_46px_42px_86px_86px_46px_50px_46px_52px_minmax(124px,1fr)]",
                  "items-center gap-1.5 border-b border-[var(--line)]/45 px-2 py-[3px] text-left transition-colors",
                  selectedId === fix.id ? "bg-[var(--panel-3)]" : "hover:bg-[var(--panel-2)]",
                )}
              >
                <span className="flex min-w-0 items-center gap-1.5">
                  <span
                    aria-hidden
                    className="h-[7px] w-[7px] shrink-0 rounded-[1px]"
                    style={{ background: spec.color }}
                  />
                  <span className="truncate text-[11px] text-[var(--text)]">{fix.name}</span>
                </span>
                <span className="truncate text-[10px] text-[var(--text-3)]">{spec.label}</span>
                <span>
                  <Pill tone={STATUS_TONE[fix.status]}>{NAV_STATUS_LABEL[fix.status]}</Pill>
                </span>
                <span className="num text-right text-[10.5px] text-[var(--text-2)]">
                  {fix.sogKn.toFixed(1)}
                </span>
                <span className="num text-right text-[10.5px] text-[var(--text-3)]">
                  {Math.round(fix.cog).toString().padStart(3, "0")}
                </span>
                <span className="truncate text-[10px] text-[var(--text-3)]">
                  {waypoint(fix.originId)?.name.split(" (")[0] ?? "—"}
                </span>
                <span className="truncate text-[10px] text-[var(--text-2)]">
                  {waypoint(fix.destinationId)?.name.split(" (")[0] ?? "—"}
                </span>
                <span className="num text-right text-[10.5px] text-[var(--text-2)]">
                  {clockZ(fix.etaMs)}
                </span>
                <span className="num text-right text-[10.5px] text-[var(--text-3)]">
                  {port.location ? `${distanceNm(fix, port.location).toFixed(0)}nm` : "—"}
                </span>
                <span
                  className={cn(
                    "num text-right text-[10.5px]",
                    (slot?.waitHours ?? 0) >= 6
                      ? "text-[var(--crit)]"
                      : (slot?.waitHours ?? 0) >= 2
                        ? "text-[var(--warn)]"
                        : "text-[var(--text-3)]",
                  )}
                >
                  {slot ? `${slot.waitHours.toFixed(1)}h` : "—"}
                </span>
                <span>
                  {slot ? (
                    <Pill
                      tone={slot.risk === "high" ? "crit" : slot.risk === "medium" ? "warn" : "ok"}
                    >
                      {slot.risk}
                    </Pill>
                  ) : (
                    <span className="text-[10px] text-[var(--text-3)]">—</span>
                  )}
                </span>
                <span className="truncate text-[10px] text-[var(--text-2)]">
                  {slot
                    ? slot.waitHours < 1
                      ? "Proceed to berth"
                      : slot.recommendedSpeedKn != null && fix.sogKn - slot.recommendedSpeedKn > 0.3
                        ? `Slow ${(fix.sogKn - slot.recommendedSpeedKn).toFixed(1)} kn → ${clockZ(slot.alongsideMs)}`
                        : `Hold, berth at ${clockZ(slot.alongsideMs)}`
                    : fix.status === "moored"
                      ? `Sails ${clockZ(fix.etaMs)}`
                      : "Monitor"}
                </span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------ arrival sequence -- */

export function ArrivalSequence({
  plan,
  onSelect,
  selectedId,
}: {
  plan: ArrivalPlan;
  onSelect: (id: string) => void;
  selectedId: string | null;
}) {
  const slots = plan.slots.slice(0, 14);
  if (!slots.length) {
    return <EmptyNote>No arrivals predicted inside the current horizon.</EmptyNote>;
  }

  const first = slots[0].etaMs;
  const last = Math.max(...slots.map((slot) => Math.max(slot.etaMs, slot.alongsideMs)));
  const span = Math.max(1, last - first);

  return (
    <div className="px-2 pb-2">
      <div className="mb-1.5 flex items-baseline justify-between gap-2 text-[10px] text-[var(--text-3)]">
        <span>
          <span className="num text-[var(--text-2)]">{plan.berths}</span> berths ·{" "}
          <span className="num text-[var(--text-2)]">{plan.occupied}</span> occupied
        </span>
        <span>
          anchor time in queue{" "}
          <span
            className={cn(
              "num",
              plan.totalWaitHours >= 12 ? "text-[var(--crit)]" : "text-[var(--warn)]",
            )}
          >
            {plan.totalWaitHours.toFixed(1)}h
          </span>{" "}
          → <span className="num text-[var(--ok)]">0.0h</span> if staggered
        </span>
      </div>

      <ul className="space-y-[3px]">
        {slots.map((slot) => {
          const left = ((slot.etaMs - first) / span) * 100;
          const width = Math.max(2, ((slot.alongsideMs - slot.etaMs) / span) * 100);
          return (
            <li key={slot.fix.id}>
              <button
                type="button"
                onClick={() => onSelect(slot.fix.id)}
                className={cn(
                  "grid w-full grid-cols-[42px_1fr_46px] items-center gap-2 rounded-[2px] px-1 py-[2px] text-left",
                  selectedId === slot.fix.id ? "bg-[var(--panel-3)]" : "hover:bg-[var(--panel-2)]",
                )}
              >
                <span className="num text-[10.5px] text-[var(--text-2)]">{clockZ(slot.etaMs)}</span>
                <span className="min-w-0">
                  <span className="block truncate text-[10.5px] text-[var(--text)]">
                    {slot.fix.name}
                  </span>
                  <span className="relative mt-[2px] block h-[4px] w-full rounded-[1px] bg-[var(--panel-3)]">
                    <span
                      className="absolute top-0 h-full rounded-[1px]"
                      style={{
                        left: `${left}%`,
                        width: `${width}%`,
                        background:
                          slot.risk === "high"
                            ? "var(--crit)"
                            : slot.risk === "medium"
                              ? "var(--warn)"
                              : "var(--ok)",
                      }}
                    />
                  </span>
                </span>
                <span
                  className={cn(
                    "num text-right text-[10px]",
                    slot.waitHours >= 6
                      ? "text-[var(--crit)]"
                      : slot.waitHours >= 2
                        ? "text-[var(--warn)]"
                        : "text-[var(--text-3)]",
                  )}
                  title={`Berth ${slot.berth + 1} free at ${clockZ(slot.alongsideMs)}`}
                >
                  {slot.waitHours.toFixed(1)}h
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <p className="mt-1.5 text-[9px] leading-snug text-[var(--text-3)]">
        Berth queue over predicted arrivals. Occupancy comes from the departures the traffic source
        carries; berth-hours are class envelopes scaled by length, not measured turnarounds.
      </p>
    </div>
  );
}

/* ---------------------------------------------------------- port weather -- */

export function PortWeatherPanel({
  port,
  timeline,
  baseAt,
}: {
  port: PortSnapshot;
  timeline: WeatherTimeline;
  baseAt: number;
}) {
  const steps = [0, 6, 12, 18, 24];

  const readings = useMemo(() => {
    if (!port.location || !timeline.available) return [];
    return steps.map((hours) => {
      const at = baseAt + hours * 3_600_000;
      const frame = timeline.frameAt(at);
      const station = frame.stations.find((entry) => entry.portCode === port.code);
      const rain = station?.rainMm ?? sampleField(frame, "precipitation").sample(port.location!.lon, port.location!.lat).value;
      const wind = station?.windKn ?? null;
      const impact = station?.impact ?? null;
      return { hours, at, rain, wind, impact, derived: frame.derived };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseAt, port.code, port.location, timeline]);

  if (!timeline.available) {
    return <EmptyNote>No weather artefact in this run; the forecast panel is unavailable.</EmptyNote>;
  }

  const peak = readings.reduce<{ hours: number; impact: number } | null>((worst, row) => {
    if (row.impact == null) return worst;
    if (!worst || row.impact > worst.impact) return { hours: row.hours, impact: row.impact };
    return worst;
  }, null);

  const rising = peak != null && readings[0]?.impact != null && peak.impact > readings[0].impact * 1.15;

  return (
    <div className="px-2 pb-2">
      <table className="w-full text-[10.5px]">
        <thead>
          <tr className="text-[var(--text-3)]">
            <th className="eyebrow py-[2px] text-left text-[8.5px]">Time</th>
            <th className="eyebrow py-[2px] text-right text-[8.5px]">Rain</th>
            <th className="eyebrow py-[2px] text-right text-[8.5px]">Wind</th>
            <th className="eyebrow py-[2px] text-right text-[8.5px]">Impact</th>
          </tr>
        </thead>
        <tbody>
          {readings.map((row) => (
            <tr key={row.hours} className="border-t border-[var(--line)]/50">
              <td className="num py-[3px] text-[var(--text-2)]">
                {clockZ(row.at)}
                {row.hours === 0 ? (
                  <span className="ml-1 text-[9px] text-[var(--text-3)]">now</span>
                ) : (
                  <span className="ml-1 text-[9px] text-[var(--text-3)]">+{row.hours}h</span>
                )}
              </td>
              <td className="num py-[3px] text-right text-[var(--text-2)]">
                {row.rain != null ? `${row.rain.toFixed(1)} mm` : "n/a"}
              </td>
              <td className="num py-[3px] text-right text-[var(--text-2)]">
                {row.wind != null ? `${row.wind.toFixed(0)} kn` : "n/a"}
              </td>
              <td
                className={cn(
                  "num py-[3px] text-right",
                  (row.impact ?? 0) >= 0.24
                    ? "text-[var(--crit)]"
                    : (row.impact ?? 0) >= 0.12
                      ? "text-[var(--warn)]"
                      : "text-[var(--text-2)]",
                )}
              >
                {row.impact != null ? row.impact.toFixed(3) : "n/a"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-2 space-y-[3px] border-t border-[var(--line)] pt-1.5">
        {(
          [
            ["Anchorage pressure", rising, "More vessels hold offshore as the impact index climbs."],
            ["Arrival window risk", rising, "Arrival windows tighten when the impact index peaks."],
            [
              "Turnaround risk",
              (peak?.impact ?? 0) >= 0.18,
              "Crane and mooring operations slow above an impact of about 0.18.",
            ],
          ] as Array<[string, boolean, string]>
        ).map(([label, up, hint]) => (
          <div key={label} className="flex items-center justify-between gap-2" title={hint}>
            <span className="text-[10.5px] text-[var(--text-3)]">{label}</span>
            <span
              className={cn(
                "text-[10.5px] font-medium",
                up ? "text-[var(--warn)]" : "text-[var(--ok)]",
              )}
            >
              {up ? "rising ↑" : "steady"}
            </span>
          </div>
        ))}
      </div>

      <p className="mt-1.5 text-[9px] leading-snug text-[var(--text-3)]">
        Significant wave height <span className="text-[var(--crit)]">UNAVAILABLE</span> in this run.
        Sub-daily values are interpolated from the daily impact forecast.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------ port state -- */

export function PortSummary({
  port,
  traffic,
  plan,
  decision,
  decisionMissing = false,
  onSelect,
}: {
  port: PortSnapshot;
  traffic: PortTraffic;
  /** The berth queue, so the state tab can carry the next few arrivals. */
  plan?: ArrivalPlan | null;
  decision?: Decision | null;
  /** The decision artefact 404'd for this port in this run. */
  decisionMissing?: boolean;
  onSelect?: (id: string) => void;
}) {
  const counts: Array<[string, number, NavStatus]> = [
    ["Inbound", traffic.inbound.length, "inbound"],
    ["Waiting", traffic.waiting.length, "waiting"],
    ["Anchored", traffic.anchored.length, "anchored"],
    ["Alongside", traffic.moored.length, "moored"],
    ["Outbound", traffic.outbound.length, "outbound"],
    ["Passing", traffic.passing.length, "underway"],
  ];

  return (
    <>
      <PanelSection title="Traffic now" right={`${traffic.all.length} in the approach`}>
        <div className="grid grid-cols-3 gap-x-2 gap-y-1.5">
          {counts.map(([label, count, status]) => (
            <div key={label}>
              <div className="flex items-center gap-1">
                <span
                  aria-hidden
                  className="h-[6px] w-[6px] rounded-[1px]"
                  style={{
                    background: `var(--${
                      STATUS_TONE[status] === "neutral" ? "text-3" : STATUS_TONE[status]
                    })`,
                  }}
                />
                <span className="text-[9.5px] uppercase tracking-[0.06em] text-[var(--text-3)]">
                  {label}
                </span>
              </div>
              <div className="num mt-[1px] text-[16px] leading-none text-[var(--text)]">{count}</div>
            </div>
          ))}
        </div>
      </PanelSection>

      <PanelSection title="Port state" right={port.regime}>
        <Field label="Observed congestion">
          <Num value={port.observedCongestionIndex} digits={1} />
        </Field>
        <Field label="Day-1 forecast">
          <Num value={port.congestionIndex} digits={1} />
        </Field>
        <Field label="80% band">
          <span className="num">
            {port.forecastQ10?.toFixed(0) ?? "—"}–{port.forecastQ90?.toFixed(0) ?? "—"}
          </span>
        </Field>
        <Field label="Predicted berth wait">
          <Num value={port.delayHours} digits={1} unit="h" />
        </Field>
        <Field label="Transition risk 24h">
          <Num value={port.transitionRisk24h} digits={2} />
        </Field>
        <div className="mt-1 flex items-center gap-1.5">
          <Pill tone={riskTone(port.risk)}>{port.risk}</Pill>
          <ProvenanceTag
            status={port.dataStatus}
            ageHours={port.dataAgeHours}
            detail={`Observed ${port.observedAt ?? "—"}`}
          />
        </div>
      </PanelSection>

      {plan && plan.slots.length ? (
        <PanelSection title="Next arrivals" right={`${plan.slots.length} in 48h`}>
          <ul className="space-y-[1px]">
            {plan.slots.slice(0, 6).map((slot) => (
              <li key={slot.fix.id}>
                <button
                  type="button"
                  onClick={() => onSelect?.(slot.fix.id)}
                  className="grid w-full grid-cols-[38px_1fr_42px] items-baseline gap-2 rounded-[2px] px-1 py-[2px] text-left hover:bg-[var(--panel-2)]"
                >
                  <span className="num text-[10.5px] text-[var(--text-2)]">
                    {clockZ(slot.etaMs)}
                  </span>
                  <span className="min-w-0 truncate text-[10.5px] text-[var(--text)]">
                    <span
                      aria-hidden
                      className="mr-1 inline-block h-[6px] w-[6px] rounded-[1px] align-middle"
                      style={{ background: VESSEL_CLASSES[slot.fix.vesselClass].color }}
                    />
                    {slot.fix.name}
                  </span>
                  <span
                    className={cn(
                      "num text-right text-[10px]",
                      slot.waitHours >= 6
                        ? "text-[var(--crit)]"
                        : slot.waitHours >= 2
                          ? "text-[var(--warn)]"
                          : "text-[var(--text-3)]",
                    )}
                  >
                    {slot.waitHours.toFixed(1)}h
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </PanelSection>
      ) : null}

      {!decision && decisionMissing ? (
        <PanelSection title="Decision queue" right="unavailable">
          <p className="text-[10.5px] leading-snug text-[var(--text-3)]">
            <span className="text-[var(--crit)]">Artefact not in this run.</span> The pipeline
            exported no decision for {port.name}, so there is nothing to act on here — not an
            empty queue, a missing one.
          </p>
        </PanelSection>
      ) : null}

      {decision ? (
        <PanelSection title="Decision queue" right={decision.severity}>
          <div className="text-[11.5px] font-medium text-[var(--text)]">{decision.title}</div>
          <p className="mt-1 text-[10.5px] leading-snug text-[var(--text-2)]">
            {decision.rationale}
          </p>
          <div className="num mt-1 text-[9.5px] text-[var(--text-3)]">
            priority {decision.priorityScore.toFixed(2)} · confidence{" "}
            {decision.confidence.toFixed(2)}
            {decision.expectedDelaySavedHours != null
              ? ` · saves ${decision.expectedDelaySavedHours.toFixed(1)}h`
              : ""}
          </div>
        </PanelSection>
      ) : null}
    </>
  );
}

export { formatDuration };
export function useNow(): number {
  return useTrafficTick(1);
}
