import type { ReactNode } from "react";
import type { PortTwinState, TwinMetrics } from "@/types/portwatch-os";
import type { TwinPlayback } from "./twin-playback";

export type ComparisonLane = "baseline" | "lookahead";
export const COMPARISON_LABELS: Record<ComparisonLane, string> = {
  baseline: "First come, first served",
  lookahead: "Constrained lookahead",
};

const lanes = ["baseline", "lookahead"] as const;

export function TwinComparisonView({
  baseline,
  lookahead,
  winner,
  hour,
  renderScene,
}: {
  baseline: TwinPlayback;
  lookahead: TwinPlayback;
  winner: "fcfs" | "lookahead" | null;
  hour: number;
  renderScene: (
    lane: ComparisonLane,
    playback: TwinPlayback,
    state: PortTwinState,
  ) => ReactNode;
}) {
  return (
    <section
      data-testid="twin-comparison"
      className="flex h-full min-h-0 flex-col bg-[var(--panel)]"
      aria-label="Modelled policy comparison"
    >
      <p
        data-testid="twin-comparison-winner"
        className="border-b border-[var(--line)] px-3 py-2 text-xs text-[var(--text-2)]"
      >
        <span className="eyebrow mr-2">24-hour result</span>
        <strong>
          {winner === null
            ? "The two policies tie on the modelled objective."
            : `${COMPARISON_LABELS[winner === "fcfs" ? "baseline" : "lookahead"]} wins on the modelled objective.`}
        </strong>
      </p>
      <div className="grid min-h-0 flex-1 grid-cols-2 divide-x divide-[var(--line)]">
        {lanes.map((lane) => {
          const playback = lane === "baseline" ? baseline : lookahead;
          const { state } = playback.sample(hour);
          return (
            <figure
              key={lane}
              className="flex min-h-0 min-w-0 flex-col"
              aria-label={COMPARISON_LABELS[lane]}
            >
              <figcaption className="shrink-0 border-b border-[var(--line)] px-3 py-1.5">
                <span className="eyebrow mr-2">
                  {lane === "baseline" ? "01 / FCFS" : "02 / Lookahead"}
                </span>
                <strong className="text-xs">{COMPARISON_LABELS[lane]}</strong>
              </figcaption>
              <div
                className="relative min-h-0 flex-1"
                data-testid={`twin-pane-${lane}`}
              >
                {renderScene(lane, playback, state)}
              </div>
              <ComparisonMetrics metrics={state.metrics} lane={lane} />
            </figure>
          );
        })}
      </div>
    </section>
  );
}

function ComparisonMetrics({
  metrics,
  lane,
}: {
  metrics: TwinMetrics;
  lane: ComparisonLane;
}) {
  const hours = (value: number | null) =>
    value == null ? "—" : `${value.toFixed(1)} h`;
  const figures = [
    ["Mean wait", hours(metrics.meanWaitHours)],
    ["Turnaround", hours(metrics.meanTurnaroundHours)],
    ["Missed departures", String(metrics.missedDepartures)],
  ];
  return (
    <dl
      className="grid shrink-0 grid-cols-3 gap-1.5 border-t border-[var(--line)] px-3 py-2"
      data-testid={`twin-metrics-${lane}`}
      data-hour={metrics.hour}
    >
      {figures.map(([label, value]) => (
        <div key={label}>
          <dt className="text-[10px] text-[var(--text-2)]">{label}</dt>
          <dd className="num text-[13px] font-semibold">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
