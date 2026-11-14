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

import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";

import {
  Page,
  PageBody,
  PageHeader,
  Panel,
  Section,
} from "@/components/kit/layout";
import { Num, Pill } from "@/components/kit/primitives";
import { DataTable, type Column } from "@/components/kit/table";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { cn } from "@/lib/utils";
import {
  PortDecisionPanel,
  applyPortPlan,
} from "@/components/decision/PortDecisionPanel";
import { useDecision } from "@/services/decisions";
import {
  usePortTwin,
  useTwinOptimize,
  useTwinSimulation,
  useTwinComparison,
} from "@/services/os-hooks";
import type {
  TwinMetrics,
  TwinOptimizeRow,
  TwinCall,
  PortTwinState,
} from "@/types/portwatch-os";
import {
  OVERLAYS,
  TWIN_RAMP,
  type TwinOverlay,
  type TwinSelection,
} from "./twin-presentation";

import { usePortWeather } from "@/components/miniature/use-port-weather";
import { usePortRegistry } from "@/services/hooks";
import { createTwinPlayback } from "./twin-playback";
import { twinCallPickId, twinSelection } from "./twin-selection";
import { useTwinClock } from "./use-twin-clock";
import { TwinTransport } from "./TwinTransport";
import {
  COMPARISON_LABELS,
  TwinComparisonView,
  type ComparisonLane,
} from "./TwinComparisonView";

/** Three is 1.1 MB. It loads when this screen does, and not before. */
const PortTwinScene = lazy(() =>
  import("./PortTwinScene").then((module) => ({
    default: module.PortTwinScene,
  })),
);

const HORIZONS = [0, 2, 6, 12, 24] as const;

function SceneFallback({ label }: { label: string }) {
  return (
    <div className="grid h-full w-full place-items-center bg-[var(--bg)]">
      <span className="flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-[var(--text-3)]">
        <span className="pw-breathe h-1.5 w-1.5 rounded-full bg-[var(--info)]" />
        {label}
      </span>
    </div>
  );
}

export function PortTwinScreen({ portCode }: { portCode: string }) {
  const twin = usePortTwin(portCode);
  const location = usePortRegistry().data?.find((port) => port.code === portCode)?.location;
  const { weather, label: weatherLabel } = usePortWeather(portCode, location?.lat, location?.lon);
  const [overlay, setOverlay] = useState<TwinOverlay>("utilisation");
  const [showModel, setShowModel] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [selectionLane, setSelectionLane] =
    useState<ComparisonLane>("baseline");
  const [selected, setSelected] = useState<{ id: string; port: string } | null>(
    null,
  );
  const setSelection = (item: TwinSelection | null) => {
    setSelected(item ? { id: item.id, port: portCode } : null);
  };
  const [policy, setPolicy] = useState("greedy");

  const simulation = useTwinSimulation(portCode, policy, 24);
  const optimize = useTwinOptimize(portCode, 24);
  const comparison = useTwinComparison(portCode, comparing);
  const comparisonRuns = useMemo(() => {
    if (!comparison.data) return null;
    const baseline = createTwinPlayback(comparison.data.baseline);
    const lookahead = createTwinPlayback(comparison.data.lookahead);
    return baseline && lookahead ? { baseline, lookahead } : null;
  }, [comparison.data]);
  const playback = useMemo(
    () => (simulation.data ? createTwinPlayback(simulation.data) : null),
    [simulation.data],
  );

  // A port decision, when one is open: the scene shows the selected option's
  // berth plan, and the metrics strip its simulated figures.
  const [decisionId, setDecisionId] = useState<string | null>(null);
  const [decisionOptionId, setDecisionOptionId] = useState<string | null>(null);
  const decision = useDecision(decisionId);
  const decisionOption = useMemo(
    () =>
      decision.data?.options.find((o) => o.optionId === decisionOptionId) ??
      null,
    [decision.data, decisionOptionId],
  );

  const duration = playback?.duration ?? 24;
  const modelAvailable = Boolean(
    (comparing ? comparisonRuns : playback) && !decisionOption,
  );
  const transport = useTwinClock(duration, modelAvailable);
  const horizon = transport.position;
  const stage = useRef<HTMLDivElement>(null);
  const autoplayed = useRef(false);
  const { play } = transport;
  useEffect(() => {
    if (!comparing || !modelAvailable || autoplayed.current || !stage.current) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let visible = false;
    const start = () => {
      if (!visible || document.hidden || autoplayed.current) return;
      autoplayed.current = true;
      play();
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      start();
    }, { threshold: 0.15 });
    observer.observe(stage.current);
    document.addEventListener("visibilitychange", start);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", start);
    };
  }, [comparing, modelAvailable, play]);
  const seekModel = (hour: number) => {
    transport.pause();
    setShowModel(true);
    transport.seek(hour);
  };
  const selectHorizon = (hour: number) => {
    transport.pause();
    setShowModel(comparing || hour > 0);
    transport.seek(hour);
  };

  // At NOW the state is the observed twin. At every other horizon it is the
  // simulator's own state at that hour -- a real forward run, not the present
  // state with a label on it. With a decision option selected it is the
  // observed twin with that option's plan written onto its berths.
  const state = useMemo(() => {
    if (decisionOption && twin.data) {
      const camera = decision.data?.evidence.cameraPlanning as
        { scenarioState?: PortTwinState } | undefined;
      return applyPortPlan(camera?.scenarioState ?? twin.data, decisionOption);
    }
    if (comparing && comparisonRuns)
      return comparisonRuns[selectionLane].sample(horizon).state;
    if (!showModel || !simulation.data) return twin.data ?? null;
    return playback?.sample(horizon).state ?? simulation.data.finalState;
  }, [
    decision.data,
    decisionOption,
    horizon,
    simulation.data,
    twin.data,
    playback,
    showModel,
    comparing,
    comparisonRuns,
    selectionLane,
  ]);

  const metrics: TwinMetrics | null = useMemo(() => {
    if (decisionOption?.evaluation) {
      const port = decisionOption.evaluation.consequences.find(
        (c) => c.kind === "port",
      );
      const simulated = port?.metrics as TwinMetrics | undefined;
      if (simulated) return simulated;
    }
    if (!showModel) return twin.data?.metrics ?? null;
    const snapshot = simulation.data?.snapshots?.[String(horizon)];
    return (
      playback?.sample(horizon).state.metrics ??
      snapshot ??
      simulation.data?.metrics ??
      null
    );
  }, [
    decisionOption,
    horizon,
    simulation.data,
    twin.data,
    playback,
    showModel,
    comparing,
    comparisonRuns,
    selectionLane,
  ]);

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

  const selection =
    selected?.port === portCode ? twinSelection(state, selected.id) : null;
  const selectionSource =
    selection?.kind === "rail"
      ? "Tour rail builder · schematic geometry"
      : decisionOption
        ? "Selected decision option · modelled berth plan"
        : comparing || showModel
          ? "Port twin engine · modelled simulation frame"
          : "Port twin state · schematic operating inputs";
  const waiting = state.calls.filter((c) => c.state === "waiting");
  const approaching = state.calls.filter((c) => c.state === "approaching");

  return (
    <Page className={comparing ? "overflow-y-auto" : undefined}>
      <PageHeader
        title={`${twin.data.portName} — Digital Twin`}
        context={
          <span className="flex items-center gap-2">
            <span className="num">{twin.data.portCode}</span>
            <span className="group relative" data-testid="twin-schematic-banner">
              <button type="button" aria-describedby="twin-geometry-basis">
                <Pill tone="unc">SCHEMATIC</Pill>
              </button>
              <span
                id="twin-geometry-basis"
                role="tooltip"
                className="pointer-events-none invisible absolute left-0 top-full z-30 w-64 border border-[var(--line)] bg-[var(--panel)] p-2 text-xs shadow-[var(--shadow-floating)] group-hover:visible group-focus-within:visible"
              >
                Schematic digital twin — not a surveyed port plan. {twin.data.geometryDisclaimer}
                {" "}Vessel and crane motion use modelled simulation steps. Yard stacks and trucks
                illustrate modelled throughput.
              </span>
            </span>
            <span data-testid="twin-weather-status" className="text-xs">{weatherLabel}</span>
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
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              aria-pressed={comparing}
              data-testid="twin-compare-toggle"
              className="rounded border border-[var(--line)] px-2 py-1 text-[11px] font-semibold aria-pressed:border-[var(--signal-ink)] aria-pressed:text-[var(--signal-ink)]"
              onClick={() => {
                transport.pause();
                setDecisionOptionId(null);
                setSelection(null);
                setSelectionLane("baseline");
                setShowModel(!comparing);
                setComparing(!comparing);
              }}
            >
              {comparing ? "Single twin" : "Compare policies"}
            </button>
            <div className="flex overflow-hidden rounded-[2px] border border-[var(--line-strong)]">
              {HORIZONS.map((hours) => (
                <button
                  key={hours}
                  type="button"
                  aria-pressed={
                    hours === 0 ? !showModel : Math.abs(horizon - hours) < 0.01
                  }
                  data-testid={`twin-horizon-${hours}`}
                  onClick={() => selectHorizon(hours)}
                  className={cn(
                    "num px-2 py-[3px] text-[11px] transition-colors",
                    (
                      hours === 0
                        ? !showModel
                        : Math.abs(horizon - hours) < 0.01
                    )
                      ? "bg-[var(--panel-4)] text-[var(--text)]"
                      : "text-[var(--text-3)] hover:bg-[var(--panel-3)] hover:text-[var(--text-2)]",
                  )}
                >
                  {hours === 0 ? "NOW" : `+${hours}h`}
                </button>
              ))}
            </div>
          </div>
        }
      />

      <div className={cn(
        "grid gap-0 xl:grid-cols-[minmax(0,1fr)_330px]",
        comparing
          ? "grid-cols-1 grid-rows-[auto_auto] xl:grid-rows-1"
          : "min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(280px,1fr)_auto] xl:grid-rows-1",
      )}>
        <div className="flex min-h-0 flex-col">
          <div ref={stage} className={cn("relative min-h-0", !comparing && "flex-1")}>
            <Suspense
              fallback={<SceneFallback label="Loading the 3D renderer" />}
            >
              {comparing ? (
                comparisonRuns && comparison.data ? (
                  <TwinComparisonView
                    {...comparisonRuns}
                    winner={comparison.data.winner}
                    hour={horizon}
                    transport={
                      <TwinTransport
                        compact
                        transport={transport}
                        duration={duration}
                        enabled={modelAvailable}
                        onSeek={seekModel}
                        onPlay={transport.toggle}
                      />
                    }
                    renderScene={(lane, run, laneState) => (
                      <PortTwinScene
                        framing="comparison"
                        state={laneState}
                        overlay={overlay}
                        weather={weather}
                        playback={run}
                        clock={transport.clock}
                        selectedId={
                          selectionLane === lane ? selection?.id : null
                        }
                        onSelect={(item) => {
                          setSelectionLane(lane);
                          setSelection(item);
                        }}
                        className="h-full w-full"
                      />
                    )}
                  />
                ) : comparison.isError ? (
                  <div className="grid h-full place-items-center text-xs">
                    <button
                      type="button"
                      className="underline"
                      onClick={() => void comparison.refetch()}
                    >
                      Comparison unavailable · retry
                    </button>
                  </div>
                ) : (
                  <SceneFallback label="Running both policies from the same snapshot" />
                )
              ) : (
                <PortTwinScene
                  state={state}
                  overlay={overlay}
                  metrics={metrics}
                  weather={weather}
                  playback={showModel && !decisionOption ? playback : null}
                  clock={transport.clock}
                  selectedId={selection?.id ?? null}
                  onSelect={setSelection}
                  className="h-full w-full"
                />
              )}
            </Suspense>

            {decisionOption ? (
              <div
                className="pointer-events-none absolute left-2.5 top-2.5 z-10 rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)]/95 px-2.5 py-1.5 backdrop-blur-[3px]"
                data-testid="twin-decision-badge"
              >
                <div className="text-[10px] uppercase tracking-[0.06em] text-[var(--text-3)]">
                  Scene shows option
                </div>
                <div className="text-[11px] text-[var(--text)]">
                  {decisionOption.isBaseline
                    ? "Continue current plan"
                    : decisionOption.label}
                </div>
                <div className="num text-[10px] text-[var(--text-3)]">
                  simulated berth plan ·{" "}
                  {decisionOption.evaluation?.derived.policy as string}
                </div>
              </div>
            ) : null}

            {/* Metrics strip, top-right over the scene. */}
            {metrics && !comparing ? (
              <div className="pointer-events-none absolute right-2.5 top-2.5 z-10 grid grid-cols-3 gap-x-3 gap-y-1.5 rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)]/95 px-2.5 py-1.5 backdrop-blur-[3px]">
                {(
                  [
                    [
                      "Berth util.",
                      `${(metrics.berthUtilisation * 100).toFixed(0)}%`,
                    ],
                    [
                      "Yard util.",
                      `${(metrics.yardUtilisation * 100).toFixed(0)}%`,
                    ],
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
                    [
                      "Crane cap.",
                      `${metrics.craneCapacityMovesPerHour.toFixed(0)}/h`,
                    ],
                  ] as Array<[string, string]>
                ).map(([label, value]) => (
                  <div key={label}>
                    <div className="text-[10px] uppercase tracking-[0.06em] text-[var(--text-3)]">
                      {label}
                    </div>
                    <div className="num text-[14px] leading-none text-[var(--text)]">
                      {value}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-t border-[var(--line)] bg-[var(--panel)] px-3 py-2">
            <div className="eyebrow text-[10px]">Colour by</div>
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
            <div className="flex flex-wrap items-center gap-2 text-[10px]">
              <span>Low</span>
              <span
                aria-hidden="true"
                className="h-2 w-20 rounded"
                style={{
                  background: `linear-gradient(90deg,${TWIN_RAMP.join(",")})`,
                }}
              />
              <span>High</span>
              <span className="font-medium">
                {OVERLAYS.find((item) => item.key === overlay)?.hint}
              </span>
            </div>
            <div className="text-[10px]">
              {selection ? (
                <strong>Selected · {selection.label}</strong>
              ) : (
                "Click an item to inspect it"
              )}
            </div>
          </div>
          {!comparing ? (
          <TwinTransport
            transport={transport}
            duration={duration}
            enabled={modelAvailable}
            onSeek={seekModel}
            onPlay={() => {
              setShowModel(true);
              transport.toggle();
            }}
          />
          ) : null}
        </div>

        {/* ------------------------------------------------------ panels -- */}
        <div className={cn(
          "min-h-0 space-y-0 overflow-auto border-l border-[var(--line)] bg-[var(--panel)]",
          comparing && "xl:max-h-[calc(100svh-9rem)]",
        )}>
          {optimize.data ? (
            <PolicyBeforeAfter rows={optimize.data.policies} />
          ) : null}
          <PortDecisionPanel
            portCode={twin.data.portCode}
            decisionId={decisionId}
            onDecision={setDecisionId}
            selectedOptionId={decisionOptionId}
            onSelectOption={(id) => {
              transport.pause();
              if (id) setComparing(false);
              setDecisionOptionId(id);
            }}
          />
          <Panel
            title={selection ? selection.label : "Inspector"}
            testId="twin-inspector"
          >
            {selection ? (
              <Section
                title={
                  selection.kind[0].toUpperCase() + selection.kind.slice(1)
                }
              >
                <dl className="space-y-[3px]">
                  {selection.fields.map(([label, value]) => (
                    <div
                      key={label}
                      className="flex items-baseline justify-between gap-3"
                    >
                      <dt className="text-[10.5px] text-[var(--text-3)]">
                        {label}
                      </dt>
                      <dd className="num text-right text-[11px] text-[var(--text)]">
                        {value}
                      </dd>
                    </div>
                  ))}
                </dl>
                <p
                  data-testid="twin-inspector-source"
                  className="mt-2 border-t border-[var(--line)] pt-1 text-[10px] text-[var(--text-2)]"
                >
                  <span className="eyebrow mr-1">Source</span> {selectionSource}
                  {comparing && selection?.kind !== "rail"
                    ? ` · ${COMPARISON_LABELS[selectionLane]}`
                    : ""}
                </p>
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
                  Click a hull, crane, yard block, truck, gate or rail in the
                  scene to inspect its numbers and source.
                </p>
              </Section>
            )}
          </Panel>

          <Panel
            title="Arrival queue"
            note={`${waiting.length} waiting${comparing ? " · " + COMPARISON_LABELS[selectionLane] : ""}`}
          >
            <Section title={`${approaching.length} approaching`}>
              {waiting.length === 0 ? (
                <p className="text-[10.5px] text-[var(--text-3)]">
                  No vessel is at anchor in this state.
                </p>
              ) : (
                <ul className="space-y-1">
                  {waiting.slice(0, 10).map((call, index) => (
                    <li
                      key={twinCallPickId(call, index)}
                      className="flex items-baseline gap-2"
                    >
                      <span className="min-w-0 flex-1 truncate text-[10.5px] text-[var(--text-2)]">
                        {call.name}
                      </span>
                      <span className="num shrink-0 text-[10.5px] text-[var(--text-3)]">
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
            note={
              optimize.data ? `${optimize.data.policies.length} compared` : "…"
            }
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
                      onSelect={() => {
                        transport.pause();
                        setPolicy(row.policy.policyId);
                      }}
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
                      <div
                        key={key}
                        className="flex items-baseline justify-between gap-3"
                      >
                        <dt className="text-[10.5px] text-[var(--text-3)]">
                          {key.replace(/([A-Z])/g, " $1").toLowerCase()}
                        </dt>
                        <dd
                          className={cn(
                            "num text-[11px]",
                            value < 0
                              ? "text-[var(--crit)]"
                              : "text-[var(--ok)]",
                          )}
                        >
                          {value.toFixed(1)}
                        </dd>
                      </div>
                    ))}
                  <div className="flex items-baseline justify-between gap-3 border-t border-[var(--line)] pt-1">
                    <dt className="text-[10.5px] font-medium text-[var(--text-2)]">
                      Total
                    </dt>
                    <dd className="num text-[12px] text-[var(--text)]">
                      {simulation.data.reward.toFixed(1)}
                    </dd>
                  </div>
                </dl>
              </Section>
              {simulation.data.violations.length ? (
                <Section title="Constraint violations">
                  <ul className="space-y-1">
                    {simulation.data.violations
                      .slice(0, 4)
                      .map((violation, index) => (
                        <li
                          key={index}
                          className="text-[10px] text-[var(--crit)]"
                        >
                          {String(
                            (violation as Record<string, unknown>).detail ??
                              violation,
                          )}
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

function PolicyBeforeAfter({ rows }: { rows: TwinOptimizeRow[] }) {
  const baseline = rows.find((row) => row.policy.policyId === "fcfs");
  const lookahead = rows.find((row) => row.policy.policyId === "lookahead");
  if (!baseline || !lookahead) return null;
  const winner =
    baseline.reward === lookahead.reward
      ? "The two policies tie on the modeled objective."
      : `${lookahead.reward > baseline.reward ? "Constrained lookahead" : "First come, first served"} wins on the modeled objective.`;
  const hours = (value: number | null) =>
    value == null ? "Unavailable" : `${value.toFixed(2)} h`;
  return (
    <section
      aria-label="Scheduling before and after"
      className="border-b border-[var(--line)] bg-[var(--panel-2)] p-2 text-xs"
    >
      <p className="font-semibold">{winner}</p>
      <table className="mt-2 w-full text-left leading-snug">
        <thead>
          <tr>
            <th scope="col">Modeled metric</th>
            <th scope="col">
              Before
              <br />
              FCFS
            </th>
            <th scope="col">
              After
              <br />
              Lookahead
            </th>
          </tr>
        </thead>
        <tbody className="num">
          <tr>
            <th scope="row">Mean wait</th>
            <td>{hours(baseline.metrics.meanWaitHours)}</td>
            <td>{hours(lookahead.metrics.meanWaitHours)}</td>
          </tr>
          <tr>
            <th scope="row">Turnaround</th>
            <td>{hours(baseline.metrics.meanTurnaroundHours)}</td>
            <td>{hours(lookahead.metrics.meanTurnaroundHours)}</td>
          </tr>
          <tr>
            <th scope="row">Missed departures</th>
            <td>{baseline.metrics.missedDepartures}</td>
            <td>{lookahead.metrics.missedDepartures}</td>
          </tr>
        </tbody>
      </table>
    </section>
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
      <div className="mt-[2px] flex flex-wrap items-center gap-x-2 text-[10px] text-[var(--text-3)]">
        <span className="num">
          wait {row.metrics.meanWaitHours?.toFixed(2) ?? "n/a"} h
        </span>
        <span className="num">done {row.metrics.completedCalls}</span>
        <span className="num">missed {row.metrics.missedDepartures}</span>
        {row.violations ? (
          <span className="num text-[var(--crit)]">
            {row.violations} violations
          </span>
        ) : null}
        {row.policy.family === "learned" ? (
          <Pill tone="unc">learned</Pill>
        ) : null}
      </div>
    </button>
  );
}
