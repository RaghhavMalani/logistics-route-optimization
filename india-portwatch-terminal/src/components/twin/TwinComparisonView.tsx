import { Fragment, useState, type ReactNode } from "react";
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
  transport,
  renderScene,
}: {
  baseline: TwinPlayback;
  lookahead: TwinPlayback;
  winner: "fcfs" | "lookahead" | null;
  hour: number;
  transport: ReactNode;
  renderScene: (
    lane: ComparisonLane,
    playback: TwinPlayback,
    state: PortTwinState,
  ) => ReactNode;
}) {
  const [split, setSplit] = useState(50);
  const resize = (value: number) => setSplit(Math.min(70, Math.max(30, value)));
  return (
    <section
      data-testid="twin-comparison"
      className="flex h-full min-h-0 flex-col bg-[var(--panel)]"
      aria-label="Modelled policy comparison"
    >
      <div className="flex flex-wrap items-center border-b border-[var(--line)]">
      <p
        data-testid="twin-comparison-winner"
        className="px-3 py-1.5 text-xs text-[var(--text-2)]"
      >
        <span className="eyebrow mr-2">24-hour result</span>
        <strong>
          {winner === null
            ? "The two policies tie on the modelled objective."
            : `${COMPARISON_LABELS[winner === "fcfs" ? "baseline" : "lookahead"]} wins on the modelled objective.`}
        </strong>
      </p>
      {transport}
      </div>
      <div
        className="grid min-h-0 flex-1"
        style={{ gridTemplateColumns: `minmax(0,${split}fr) 10px minmax(0,${100 - split}fr)` }}
      >
        {lanes.map((lane) => {
          const playback = lane === "baseline" ? baseline : lookahead;
          const { state } = playback.sample(hour);
          return (
            <Fragment key={lane}>
            {lane === "lookahead" ? (
              <div
                role="separator"
                tabIndex={0}
                aria-label="Resize policy comparison panes"
                aria-orientation="vertical"
                aria-valuemin={30}
                aria-valuemax={70}
                aria-valuenow={Math.round(split)}
                className="z-20 grid cursor-col-resize touch-none place-items-center bg-[var(--panel-3)] outline-offset-[-2px] hover:bg-[var(--panel-4)] focus-visible:outline focus-visible:outline-2"
                onPointerDown={(event) => event.currentTarget.setPointerCapture(event.pointerId)}
                onPointerMove={(event) => {
                  if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
                  const track = event.currentTarget.parentElement?.getBoundingClientRect();
                  if (track) resize(((event.clientX - track.left) / track.width) * 100);
                }}
                onKeyDown={(event) => {
                  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
                  event.preventDefault();
                  resize(split + (event.key === "ArrowLeft" ? -2 : 2));
                }}
              >
                <span aria-hidden="true" className="h-9 w-0.5 rounded-full bg-[var(--line-strong)]" />
              </div>
            ) : null}
            <figure
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
                className="relative min-h-[calc(65svh+1px)] flex-1"
                data-testid={`twin-pane-${lane}`}
              >
                <div className="absolute inset-0">{renderScene(lane, playback, state)}</div>
                <ComparisonMetrics metrics={state.metrics} lane={lane} />
              </div>
            </figure>
            </Fragment>
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
      className="pointer-events-none absolute inset-x-2 bottom-2 z-10 grid grid-cols-3 gap-1.5 rounded border border-[var(--line)] bg-[var(--panel)]/95 px-2 py-1.5"
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
