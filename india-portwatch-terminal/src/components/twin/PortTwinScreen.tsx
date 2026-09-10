/**
 * The 3D port digital twin screen.
 *
 * The scene is the surface; the panels around it are what make it operational
 * rather than decorative. Four things sit on top of the geometry:
 *
 *   overlays      colour the same objects by utilisation, dwell, workload,
 *                 queue or storage pressure.
 *   time control  NOW / +2 / +6 / +12 / +24 h, each a real simulator state
 *                 rather than an interpolation of the current one.
 *   inspector     click a berth, block, shed, crane or vessel for its operating
 *                 numbers.
 *   optimiser     every scheduling policy run against this port's actual state,
 *                 ranked, so a controller can see what each would do today.
 *
 * The schematic banner is not dismissible and does not scroll away.
 */

import { Suspense, lazy, useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { Page, PageBody, PageHeader, Panel, Section } from "@/components/kit/layout";
import { Num, Pill } from "@/components/kit/primitives";
import { DataTable, type Column } from "@/components/kit/table";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { cn } from "@/lib/utils";
import { usePortTwin, useTwinOptimize, useTwinSimulation } from "@/services/os-hooks";
import type { TwinMetrics, TwinOptimizeRow, TwinCall } from "@/types/portwatch-os";
import { OVERLAYS, type TwinOverlay, type TwinSelection } from "./PortTwinScene";

/** Three is 1.1 MB. It loads when this screen does, and not before. */
const PortTwinScene = lazy(() =>
  import("./PortTwinScene").then((module) => ({ default: module.PortTwinScene })),
);

const HORIZONS = [0, 2, 6, 12, 24] as const;

function SceneFallback({ label }: { label: string }) {
  return (
    <div className="grid h-full w-full place-items-center bg-[#061420]">
      <span className="flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-[var(--text-3)]">
        <span className="pw-breathe h-1.5 w-1.5 rounded-full bg-[var(--info)]" />
        {label}
      </span>
    </div>
  );
}

export function PortTwinScreen({ portCode }: { portCode: string }) {
  const twin = usePortTwin(portCode);
  const [overlay, setOverlay] = useState<TwinOverlay>("utilisation");
  const [horizon, setHorizon] = useState<number>(0);
  const [selection, setSelection] = useState<TwinSelection | null>(null);
  const [policy, setPolicy] = useState("greedy");

  const simulation = useTwinSimulation(portCode, policy, 24);
  const optimize = useTwinOptimize(portCode, 24);

  // At NOW the state is the observed twin. At every other horizon it is the
  // simulator's own state at that hour -- a real forward run, not the present
  // state with a label on it.
  const state = useMemo(() => {
    if (horizon === 0 || !simulation.data) return twin.data ?? null;
    return simulation.data.finalState;
  }, [horizon, simulation.data, twin.data]);

  const metrics: TwinMetrics | null = useMemo(() => {
    if (horizon === 0) return twin.data?.metrics ?? null;
    const snapshot = simulation.data?.snapshots?.[String(horizon)];
    return snapshot ?? simulation.data?.metrics ?? null;
  }, [horizon, simulation.data, twin.data]);

  if (twin.isLoading || twin.isError) {
    return (
      <ScreenFallback
        title="Port Digital Twin"
        context={<span>Berths, yard, cranes and the queue in space</span>}
        isLoading={twin.isLoading}
        error={twin.error}
        retry={() => void twin.refetch()}
        label="Building the twin"
      />
    );
  }
  if (!state || !twin.data) return null;

  const waiting = state.calls.filter((c) => c.state === "waiting");
  const approaching = state.calls.filter((c) => c.state === "approaching");

  return (
    <Page>
      <PageHeader
        title={`${twin.data.portName} — Digital Twin`}
        context={
          <span className="flex items-center gap-2">
            <span className="num">{twin.data.portCode}</span>
            <Pill tone="unc">Schematic</Pill>
          </span>
        }
        meta={
          <>
            <span className="num">{state.berths.length} berths</span>
            <span className="num">{state.cranes.length} cranes</span>
            <span className="num">{state.yardBlocks.length} yard blocks</span>
          </>
        }
        actions={
          <div className="flex overflow-hidden rounded-[2px] border border-[var(--line-strong)]">
            {HORIZONS.map((hours) => (
              <button
                key={hours}
                type="button"
                aria-pressed={horizon === hours}
                data-testid={`twin-horizon-${hours}`}
                onClick={() => setHorizon(hours)}
                className={cn(
                  "num px-2 py-[3px] text-[11px] transition-colors",
                  horizon === hours
                    ? "bg-[var(--panel-4)] text-[var(--text)]"
                    : "text-[var(--text-3)] hover:bg-[var(--panel-3)] hover:text-[var(--text-2)]",
                )}
              >
                {hours === 0 ? "NOW" : `+${hours}h`}
              </button>
            ))}
          </div>
        }
      />

      {/* The honesty banner. Fixed under the header, never scrolled away. */}
      <div
        className="flex shrink-0 items-start gap-2 border-b border-[var(--line)] bg-[var(--unc-dim)]/25 px-4 py-1.5"
        data-testid="twin-schematic-banner"
      >
        <AlertTriangle size={12} className="mt-[1px] shrink-0 text-[var(--unc)]" />
        <p className="text-[10.5px] leading-snug text-[var(--text-2)]">
          <span className="font-semibold uppercase tracking-[0.06em] text-[var(--unc)]">
            Schematic digital twin — not a surveyed port plan.
          </span>{" "}
          {twin.data.geometryDisclaimer}
        </p>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(280px,1fr)_auto] gap-0 xl:grid-cols-[minmax(0,1fr)_330px] xl:grid-rows-1">
        {/* ------------------------------------------------------- scene -- */}
        <div className="relative min-h-0">
          <Suspense fallback={<SceneFallback label="Loading the 3D renderer" />}>
            <PortTwinScene
              state={state}
              overlay={overlay}
              metrics={metrics}
              selectedId={selection?.id ?? null}
              onSelect={setSelection}
              className="h-full w-full"
            />
          </Suspense>

          {/* Overlay picker, bottom-left over the scene. */}
          <div className="pointer-events-auto absolute bottom-2.5 left-2.5 z-10 rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)]/95 px-2 py-1.5 backdrop-blur-[3px]">
            <div className="eyebrow mb-1 text-[8.5px]">Colour by</div>
            <div className="flex flex-wrap gap-1">
              {OVERLAYS.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  title={option.hint}
                  aria-pressed={overlay === option.key}
                  data-testid={`twin-overlay-${option.key}`}
                  onClick={() => setOverlay(option.key)}
                  className={cn(
                    "rounded-[2px] border px-1.5 py-[2px] text-[10px] transition-colors",
                    overlay === option.key
                      ? "border-[var(--line-strong)] bg-[var(--panel-4)] text-[var(--text)]"
                      : "border-[var(--line)] text-[var(--text-3)] hover:text-[var(--text-2)]",
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className="mt-1.5 flex items-center gap-1.5 border-t border-[var(--line)]/60 pt-1.5">
              <span className="text-[9px] text-[var(--text-3)]">low</span>
              <span
                className="h-[6px] w-[76px] rounded-[1px]"
                style={{
                  background:
                    "linear-gradient(90deg,#3f8f6b 0%,#c9a13a 50%,#c2564a 100%)",
                }}
              />
              <span className="text-[9px] text-[var(--text-3)]">high</span>
              <span className="ml-1 text-[9px] text-[var(--text-3)]">
                drag to orbit · scroll to zoom · click to inspect
              </span>
            </div>
          </div>

          {/* Metrics strip, top-right over the scene. */}
          {metrics ? (
            <div className="pointer-events-none absolute right-2.5 top-2.5 z-10 grid grid-cols-3 gap-x-3 gap-y-1.5 rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)]/95 px-2.5 py-1.5 backdrop-blur-[3px]">
              {(
                [
                  ["Berth util.", `${(metrics.berthUtilisation * 100).toFixed(0)}%`],
                  ["Yard util.", `${(metrics.yardUtilisation * 100).toFixed(0)}%`],
                  ["Queue", String(metrics.queueLength)],
                  [
                    "Mean wait",
                    metrics.meanWaitHours == null
                      ? "n/a"
                      : `${metrics.meanWaitHours.toFixed(1)} h`,
                  ],
                  [
                    "Turnaround",
                    metrics.meanTurnaroundHours == null
                      ? "n/a"
                      : `${metrics.meanTurnaroundHours.toFixed(1)} h`,
                  ],
                  ["Crane cap.", `${metrics.craneCapacityMovesPerHour.toFixed(0)}/h`],
                ] as Array<[string, string]>
              ).map(([label, value]) => (
                <div key={label}>
                  <div className="text-[8.5px] uppercase tracking-[0.06em] text-[var(--text-3)]">
                    {label}
                  </div>
                  <div className="num text-[14px] leading-none text-[var(--text)]">{value}</div>
                </div>
              ))}
            </div>
          ) : null}
        </div>

        {/* ------------------------------------------------------ panels -- */}
        <div className="min-h-0 space-y-0 overflow-auto border-l border-[var(--line)] bg-[var(--panel)]">
          <Panel title={selection ? selection.label : "Inspector"} testId="twin-inspector">
            {selection ? (
              <Section title={selection.kind}>
                <dl className="space-y-[3px]">
                  {selection.fields.map(([label, value]) => (
                    <div key={label} className="flex items-baseline justify-between gap-3">
                      <dt className="text-[10.5px] text-[var(--text-3)]">{label}</dt>
                      <dd className="num text-right text-[11px] text-[var(--text)]">{value}</dd>
                    </div>
                  ))}
                </dl>
                <button
                  type="button"
                  onClick={() => setSelection(null)}
                  className="mt-2 text-[10px] text-[var(--text-3)] hover:text-[var(--text)]"
                >
                  Clear selection
                </button>
              </Section>
            ) : (
              <Section title="Nothing selected">
                <p className="text-[10.5px] leading-relaxed text-[var(--text-3)]">
                  Click a berth, yard block, shed, crane or waiting vessel in the scene
                  to inspect its operating state.
                </p>
              </Section>
            )}
          </Panel>

          <Panel title="Arrival queue" note={`${waiting.length} waiting`}>
            <Section title={`${approaching.length} approaching`}>
              {waiting.length === 0 ? (
                <p className="text-[10.5px] text-[var(--text-3)]">
                  No vessel is at anchor in this state.
                </p>
              ) : (
                <ul className="space-y-1">
                  {waiting.slice(0, 10).map((call) => (
                    <li key={call.call_id} className="flex items-baseline gap-2">
                      <span className="min-w-0 flex-1 truncate text-[10.5px] text-[var(--text-2)]">
                        {call.name}
                      </span>
                      <span className="num shrink-0 text-[9.5px] text-[var(--text-3)]">
                        {call.moves.toLocaleString()} mv
                      </span>
                      <span
                        className={cn(
                          "num shrink-0 text-[10.5px]",
                          call.wait_hours > 6
                            ? "text-[var(--crit)]"
                            : call.wait_hours > 2
                              ? "text-[var(--warn)]"
                              : "text-[var(--text-2)]",
                        )}
                      >
                        {call.wait_hours.toFixed(1)} h
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </Panel>

          <Panel
            title="Scheduling policies"
            note={optimize.data ? `${optimize.data.policies.length} compared` : "…"}
            testId="twin-optimizer"
          >
            {optimize.isLoading ? (
              <Section title="Running">
                <p className="text-[10.5px] text-[var(--text-3)]">
                  Running every policy against this port's observed state…
                </p>
              </Section>
            ) : optimize.data ? (
              <>
                <div className="px-2 py-1">
                  {optimize.data.policies.map((row) => (
                    <PolicyRow
                      key={row.policy.policyId}
                      row={row}
                      active={policy === row.policy.policyId}
                      onSelect={() => setPolicy(row.policy.policyId)}
                    />
                  ))}
                </div>
                <Section title="Method">
                  <p className="text-[10px] leading-relaxed text-[var(--text-3)]">
                    {optimize.data.note}
                  </p>
                </Section>
              </>
            ) : (
              <Section title="Unavailable">
                <p className="text-[10.5px] text-[var(--text-3)]">
                  The optimiser could not run against this port.
                </p>
              </Section>
            )}
          </Panel>

          {simulation.data ? (
            <Panel title="Forward run" note={simulation.data.policy.name}>
              <Section title="Reward breakdown">
                <dl className="space-y-[3px]">
                  {Object.entries(simulation.data.rewardBreakdown)
                    .filter(([key]) => key !== "total")
                    .map(([key, value]) => (
                      <div key={key} className="flex items-baseline justify-between gap-3">
                        <dt className="text-[10.5px] text-[var(--text-3)]">
                          {key.replace(/([A-Z])/g, " $1").toLowerCase()}
                        </dt>
                        <dd
                          className={cn(
                            "num text-[11px]",
                            value < 0 ? "text-[var(--crit)]" : "text-[var(--ok)]",
                          )}
                        >
                          {value.toFixed(1)}
                        </dd>
                      </div>
                    ))}
                  <div className="flex items-baseline justify-between gap-3 border-t border-[var(--line)] pt-1">
                    <dt className="text-[10.5px] font-medium text-[var(--text-2)]">Total</dt>
                    <dd className="num text-[12px] text-[var(--text)]">
                      {simulation.data.reward.toFixed(1)}
                    </dd>
                  </div>
                </dl>
              </Section>
              {simulation.data.violations.length ? (
                <Section title="Constraint violations">
                  <ul className="space-y-1">
                    {simulation.data.violations.slice(0, 4).map((violation, index) => (
                      <li key={index} className="text-[10px] text-[var(--crit)]">
                        {String((violation as Record<string, unknown>).detail ?? violation)}
                      </li>
                    ))}
                  </ul>
                </Section>
              ) : (
                <Section title="Safety">
                  <p className="text-[10.5px] text-[var(--ok)]">
                    No hard-constraint violation in this run.
                  </p>
                </Section>
              )}
            </Panel>
          ) : null}

          <Panel title="What this twin is">
            <Section title="Geometry">
              <ul className="space-y-1.5">
                {twin.data.notes.map((note) => (
                  <li
                    key={note}
                    className="text-[10px] leading-relaxed text-[var(--text-3)]"
                  >
                    {note}
                  </li>
                ))}
              </ul>
            </Section>
          </Panel>
        </div>
      </div>
    </Page>
  );
}

function PolicyRow({
  row,
  active,
  onSelect,
}: {
  row: TwinOptimizeRow;
  active: boolean;
  onSelect: () => void;
}) {
  const improvement = row.improvementVsBaseline;
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "block w-full border-b border-[var(--line)]/50 px-1 py-1 text-left transition-colors last:border-0",
        active ? "bg-[var(--panel-3)]" : "hover:bg-[var(--panel-2)]",
      )}
    >
      <div className="flex items-baseline gap-2">
        <span className="min-w-0 flex-1 truncate text-[11px] text-[var(--text)]">
          {row.policy.name}
        </span>
        <span className="num shrink-0 text-[11px] text-[var(--text-2)]">
          {row.reward.toFixed(0)}
        </span>
        {improvement != null ? (
          <span
            className={cn(
              "num w-[46px] shrink-0 text-right text-[10px]",
              improvement > 0.005
                ? "text-[var(--ok)]"
                : improvement < -0.005
                  ? "text-[var(--crit)]"
                  : "text-[var(--text-3)]",
            )}
          >
            {improvement > 0 ? "+" : ""}
            {(improvement * 100).toFixed(1)}%
          </span>
        ) : null}
      </div>
      <div className="mt-[2px] flex flex-wrap items-center gap-x-2 text-[9px] text-[var(--text-3)]">
        <span className="num">
          wait {row.metrics.meanWaitHours?.toFixed(2) ?? "n/a"} h
        </span>
        <span className="num">done {row.metrics.completedCalls}</span>
        <span className="num">missed {row.metrics.missedDepartures}</span>
        {row.violations ? (
          <span className="num text-[var(--crit)]">{row.violations} violations</span>
        ) : null}
        {row.policy.family === "learned" ? <Pill tone="unc">learned</Pill> : null}
      </div>
    </button>
  );
}
