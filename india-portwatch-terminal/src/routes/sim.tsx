import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  Chip,
  Delta,
  ErrorState,
  Loading,
  Metric,
  MetricRow,
  Panel,
  Value,
  formatUtc,
  riskTone,
} from "@/components/terminal/ui";
import { fetchScenarios, runScenario } from "@/services/portwatch";
import { resolveScenarioKey } from "@/lib/scenario-keys";
import type { ScenarioPortImpact } from "@/types/portwatch";

export const Route = createFileRoute("/sim")({
  validateSearch: (search: Record<string, unknown>) => ({
    scenario:
      typeof search.scenario === "string"
        ? resolveScenarioKey(search.scenario)
        : "HORMUZ",
    intensity: Number.isFinite(Number(search.intensity))
      ? Number(search.intensity)
      : 1,
  }),
  component: DecisionRoom,
});

/**
 * Decision Room. Baseline versus shock, computed by re-forecasting through the
 * impact model rather than read from a table of constants. Every delta on this
 * screen is a difference between two forecasts the system actually produced.
 */
function DecisionRoom() {
  const search = Route.useSearch();
  const navigate = useNavigate();
  const [scenarioKey, setScenarioKey] = useState(search.scenario);
  const [intensity, setIntensity] = useState(search.intensity);
  const [runId, setRunId] = useState(0);
  const [focusPort, setFocusPort] = useState<string | null>(null);

  useEffect(() => {
    setScenarioKey(search.scenario);
    setIntensity(search.intensity);
  }, [search.scenario, search.intensity]);

  const scenariosQuery = useQuery({
    queryKey: ["scenarios"],
    queryFn: fetchScenarios,
    staleTime: 300_000,
  });

  const resultQuery = useQuery({
    queryKey: ["scenario-result", scenarioKey, intensity, runId],
    queryFn: () => runScenario(scenarioKey, intensity, runId),
    enabled: Boolean(scenarioKey),
    staleTime: 30_000,
    retry: 1,
  });

  if (scenariosQuery.isLoading) return <Loading label="LOADING SCENARIO CATALOGUE" />;
  if (scenariosQuery.isError) return <ErrorState error={scenariosQuery.error} />;

  const scenarios = scenariosQuery.data ?? [];
  const active = scenarios.find((s) => s.key === scenarioKey) ?? scenarios[0];
  const result = resultQuery.data;
  const focused =
    result?.affectedPorts.find((p) => p.portCode === focusPort) ??
    result?.affectedPorts[0];

  const apply = (key: string, value: number) => {
    setScenarioKey(key);
    setIntensity(value);
    void navigate({ to: "/sim", search: { scenario: key, intensity: value } });
  };

  return (
    <div className="h-full grid grid-cols-[228px_1fr] gap-2 p-2 overflow-hidden">
      {/* Scenario selector. */}
      <div className="min-h-0 flex flex-col gap-2">
        <Panel title="SCENARIO" bodyClassName="overflow-auto">
          <div className="p-1.5 space-y-1">
            {scenarios.map((scenario) => (
              <button
                key={scenario.key}
                onClick={() => apply(scenario.key, intensity)}
                className={`w-full text-left px-2 py-1.5 border transition-colors ${
                  scenario.key === scenarioKey
                    ? "border-[var(--color-cyan)] bg-[var(--color-cyan)]/5 text-[var(--color-cyan)]"
                    : "border-[var(--color-line)]/60 text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]"
                }`}
              >
                <div className="text-[10px] leading-tight">{scenario.name}</div>
                <div className="text-[8px] tracking-[0.1em] uppercase opacity-70">
                  {scenario.scope}
                  {scenario.chokepoint ? ` · ${scenario.chokepoint}` : ""}
                </div>
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="INTENSITY">
          <div className="p-3 space-y-2">
            <input
              type="range"
              min={0.25}
              max={2}
              step={0.25}
              value={intensity}
              aria-label="Scenario intensity"
              onChange={(event) => apply(scenarioKey, Number(event.target.value))}
              className="w-full accent-[var(--color-cyan)]"
            />
            <div className="flex justify-between text-[9px] text-[var(--color-muted-foreground)]">
              <span>0.25x</span>
              <span className="text-[var(--color-cyan)] tabular-nums">
                {intensity.toFixed(2)}x
              </span>
              <span>2.0x</span>
            </div>
            <div className="text-[9px] leading-snug text-[var(--color-muted-foreground)]">
              Intensity scales the shock severity. Effective severity for this
              run:{" "}
              <span className="text-[var(--color-foreground)] tabular-nums">
                {result ? `${(result.severity * 100).toFixed(0)}%` : "—"}
              </span>
            </div>
            <button
              onClick={() => setRunId((id) => id + 1)}
              className="w-full border border-[var(--color-cyan)]/60 bg-[var(--color-cyan)]/5 px-2 py-1.5 text-[10px] tracking-[0.16em] text-[var(--color-cyan)]"
            >
              RE-RUN PROPAGATION
            </button>
          </div>
        </Panel>

        {active && (
          <Panel title="WHAT THIS ASKS" className="flex-1 min-h-0">
            <div className="p-3 space-y-2 text-[10px] leading-relaxed">
              <div className="text-[var(--color-foreground)]">{active.question}</div>
              <div className="text-[var(--color-muted-foreground)]">
                {active.desc}
              </div>
              <div className="pt-1 border-t border-[var(--color-line)]/50">
                <div className="label-xs mb-1">CALIBRATION ANALOGUE</div>
                <div className="text-[9px] text-[var(--color-muted-foreground)] leading-snug">
                  {active.analogue}
                </div>
              </div>
              <MetricRow label="Assumed duration">
                <span className="tabular-nums">{active.durationDays}d</span>
              </MetricRow>
              <MetricRow label="Default severity">
                <span className="tabular-nums">
                  {(active.defaultSeverity * 100).toFixed(0)}%
                </span>
              </MetricRow>
            </div>
          </Panel>
        )}
      </div>

      {/* Result. */}
      <div className="min-h-0 overflow-auto space-y-2">
        {resultQuery.isLoading && <Loading label="PROPAGATING SHOCK" />}
        {resultQuery.isError && <ErrorState error={resultQuery.error} />}

        {result && (
          <>
            <div className="grid grid-cols-5 gap-2">
              <Metric
                label="NETWORK CONGESTION Δ"
                value={
                  <Delta value={result.congestionDelta} digits={1} />
                }
                sub="mean across ports and horizon"
              />
              <Metric
                label="EXPECTED WAIT Δ"
                value={<Delta value={result.delayDeltaHours} digits={2} unit="h" />}
                sub="mean berth wait change"
              />
              <Metric
                label="THROUGHPUT Δ"
                value={
                  <Delta value={result.throughputDelta} digits={1} unit="%" invert />
                }
                sub="mean tonnage change"
              />
              <Metric
                label="FREIGHT / OIL"
                value={
                  <span className="text-[16px]">
                    <Delta value={result.freightDelta} digits={1} unit="%" />
                    <span className="text-[var(--color-muted-foreground)]"> / </span>
                    <Delta value={result.oilDelta} digits={1} unit="%" />
                  </span>
                }
                tone="amber"
                sub="first-order market response"
              />
              <Metric
                label="PROPAGATION CONFIDENCE"
                value={(result.confidence * 100).toFixed(0)}
                unit="%"
                tone="cyan"
                sub={`baseline model ${result.baselineModel}`}
              />
            </div>

            <Panel
              title={`PROPAGATION · ${result.scenarioName.toUpperCase()}`}
              right={`origin ${formatUtc(result.forecastOrigin)}`}
            >
              <div className="p-2 flex items-stretch gap-1.5 overflow-x-auto">
                {result.propagation.map((step, index) => (
                  <div
                    key={`${step.step}-${index}`}
                    className="panel p-2 min-w-[172px] flex-1 relative"
                  >
                    <div className="label-xs">{step.step}</div>
                    <div className="mt-0.5 text-[11px] text-[var(--color-foreground)] leading-tight">
                      {step.label}
                    </div>
                    <div className="mt-1 text-[12px] tabular-nums text-[var(--color-cyan)]">
                      {step.value}
                    </div>
                    <div className="mt-1 text-[9px] leading-snug text-[var(--color-muted-foreground)]">
                      {step.detail}
                    </div>
                    {index < result.propagation.length - 1 && (
                      <span className="absolute -right-[8px] top-1/2 -translate-y-1/2 text-[var(--color-cyan)] text-[10px]">
                        ▶
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </Panel>

            <div className="grid grid-cols-[1.5fr_1fr] gap-2">
              <Panel title="BASELINE VS SHOCK · BY PORT">
                <div className="overflow-auto">
                  <table className="w-full text-[10px]">
                    <thead>
                      <tr className="label-xs text-left border-b border-[var(--color-line)]">
                        <th className="py-1.5 px-2 font-normal">PORT</th>
                        <th className="py-1.5 px-2 font-normal text-right">EXPOSURE</th>
                        <th className="py-1.5 px-2 font-normal text-right">BASE</th>
                        <th className="py-1.5 px-2 font-normal text-right">SHOCK</th>
                        <th className="py-1.5 px-2 font-normal text-right">Δ CONG</th>
                        <th className="py-1.5 px-2 font-normal text-right">Δ WAIT</th>
                        <th className="py-1.5 px-2 font-normal text-right">Δ P(CONG)</th>
                        <th className="py-1.5 px-2 font-normal text-right">CONF</th>
                        <th className="py-1.5 px-2 font-normal text-right">RISK</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.affectedPorts.map((port) => (
                        <tr
                          key={port.portCode}
                          onMouseEnter={() => setFocusPort(port.portCode)}
                          className={`border-b border-[var(--color-line)]/30 cursor-default ${
                            focused?.portCode === port.portCode
                              ? "bg-[var(--color-cyan)]/5"
                              : ""
                          }`}
                        >
                          <td className="py-1 px-2 truncate max-w-[150px]">
                            {port.name}
                          </td>
                          <td className="py-1 px-2 text-right tabular-nums text-[var(--color-muted-foreground)]">
                            {port.exposure.toFixed(2)}
                          </td>
                          <td className="py-1 px-2 text-right tabular-nums text-[var(--color-muted-foreground)]">
                            {port.baselineCongestion.toFixed(1)}
                          </td>
                          <td className="py-1 px-2 text-right tabular-nums">
                            {port.shockCongestion.toFixed(1)}
                          </td>
                          <td className="py-1 px-2 text-right">
                            <Delta value={port.congestionDelta} digits={1} />
                          </td>
                          <td className="py-1 px-2 text-right">
                            <Delta value={port.delayDeltaHours} digits={2} unit="h" />
                          </td>
                          <td className="py-1 px-2 text-right">
                            <Delta value={port.probabilityDelta} digits={3} />
                          </td>
                          <td className="py-1 px-2 text-right tabular-nums text-[var(--color-cyan)]">
                            {port.confidence.toFixed(2)}
                          </td>
                          <td className="py-1 px-2 text-right">
                            <Chip tone={riskTone(port.riskLevel)}>
                              {port.riskLevel.toUpperCase()}
                            </Chip>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>

              <div className="grid grid-rows-[auto_1fr] gap-2 min-h-0">
                <Panel title="RECOMMENDED ACTION UNDER SHOCK">
                  {result.recommendation.available ? (
                    <div className="p-3 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-[13px] text-[var(--color-foreground)] leading-tight">
                          {result.recommendation.title}
                        </span>
                        <Chip tone={riskTone(result.recommendation.severity)}>
                          {(result.recommendation.severity ?? "").toUpperCase()}
                        </Chip>
                      </div>
                      <div className="text-[10px] text-[var(--color-cyan)]">
                        {result.recommendation.action} ·{" "}
                        {result.recommendation.target}
                      </div>
                      <div className="text-[11px] leading-relaxed text-[var(--color-foreground)]">
                        {result.recommendation.instruction}
                      </div>
                      <MetricRow label="Expected delay saved">
                        <Value
                          value={result.recommendation.expectedDelaySavedHours}
                          digits={1}
                          unit="h"
                          tone="mint"
                        />
                      </MetricRow>
                      <MetricRow label="Decision confidence">
                        <Value
                          value={result.recommendation.confidence}
                          digits={2}
                          tone="cyan"
                        />
                      </MetricRow>
                      <MetricRow label="Changed from baseline">
                        <span
                          className={
                            result.recommendation.changedFromBaseline
                              ? "text-[var(--color-amber)]"
                              : "text-[var(--color-muted-foreground)]"
                          }
                        >
                          {result.recommendation.changedFromBaseline
                            ? `yes (was ${result.recommendation.baselineAction})`
                            : "no"}
                        </span>
                      </MetricRow>
                      <div className="text-[9px] leading-snug text-[var(--color-muted-foreground)]">
                        {result.recommendation.expectedImpact}
                        <div className="mt-1">
                          <span className="text-[var(--color-amber)]">Fallback:</span>{" "}
                          {result.recommendation.alternativeAction}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
                      {result.recommendation.reason}
                    </div>
                  )}
                </Panel>

                <Panel title="CHOKEPOINTS AND CORRIDORS">
                  <div className="p-2 space-y-1">
                    {result.chokepointImpacts.map((choke) => (
                      <div
                        key={choke.code}
                        className="grid grid-cols-[1fr_auto_auto] items-center gap-2 px-1 py-1 text-[10px] border-b border-[var(--color-line)]/30 last:border-0"
                      >
                        <span
                          className={
                            choke.isShocked
                              ? "text-[var(--color-red)]"
                              : "text-[var(--color-foreground)]"
                          }
                        >
                          {choke.name}
                        </span>
                        <span className="text-[9px] text-[var(--color-muted-foreground)]">
                          {choke.hasAlternative
                            ? `+${choke.rerouteDays}d reroute`
                            : "no bypass"}
                        </span>
                        <Chip tone={riskTone(choke.riskLevel)}>
                          {choke.riskLevel.toUpperCase()}
                        </Chip>
                      </div>
                    ))}
                    <div className="pt-1.5 mt-1 border-t border-[var(--color-line)]/50 space-y-1">
                      {result.routeImpacts.map((route) => (
                        <div
                          key={route.name}
                          className="grid grid-cols-[1fr_auto_auto] items-center gap-2 text-[10px]"
                        >
                          <span
                            className={
                              route.inScope
                                ? "text-[var(--color-foreground)]"
                                : "text-[var(--color-muted-foreground)]"
                            }
                          >
                            {route.name}
                          </span>
                          <Delta value={route.delayDeltaHours} digits={2} unit="h" />
                          <Chip tone={riskTone(route.riskLevel)}>
                            {route.riskLevel.toUpperCase()}
                          </Chip>
                        </div>
                      ))}
                    </div>
                  </div>
                </Panel>
              </div>
            </div>

            <div className="panel px-3 py-2 text-[9px] leading-relaxed text-[var(--color-muted-foreground)]">
              <span className="text-[var(--color-amber)]">METHOD · </span>
              {result.method}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export type { ScenarioPortImpact };
