import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  Bar,
  Chip,
  ErrorState,
  Loading,
  Metric,
  MetricRow,
  Panel,
  ProvenanceChip,
  Sparkline,
  Value,
  formatDate,
  formatUtc,
  riskLabel,
  riskTone,
} from "@/components/terminal/ui";
import { fetchChain, fetchPorts, fetchWeatherForPort } from "@/services/portwatch";
import type { ChainStage, ForecastPoint } from "@/types/portwatch";

export const Route = createFileRoute("/port")({
  validateSearch: (search: Record<string, unknown>) => ({
    port: typeof search.port === "string" ? search.port : "INMAA",
  }),
  component: PortCockpit,
});

/**
 * Port cockpit -- the digital twin of a single port, arranged the way an
 * operator asks the questions:
 *
 *   NOW              what is happening at the berth line right now
 *   REGIME           what state the port is in, and how long it usually lasts
 *   NEXT 24H / 10D   what the model expects, with its uncertainty band
 *   WHY              the evidence chain from raw signal to decision
 *   WHAT TO DO       the action, its expected benefit and its fallback
 */
function PortCockpit() {
  const { port: portCode } = Route.useSearch();
  const navigate = useNavigate();

  const portsQuery = useQuery({
    queryKey: ["ports"],
    queryFn: fetchPorts,
    staleTime: 30_000,
  });
  const chainQuery = useQuery({
    queryKey: ["chain", portCode],
    queryFn: () => fetchChain(portCode),
    staleTime: 30_000,
    retry: 1,
  });
  const weatherQuery = useQuery({
    queryKey: ["weather", portCode],
    queryFn: () => fetchWeatherForPort(portCode),
    staleTime: 60_000,
    retry: 0,
  });

  if (chainQuery.isLoading || portsQuery.isLoading) {
    return <Loading label="LOADING PORT DIGITAL TWIN" />;
  }
  if (chainQuery.isError || !chainQuery.data) {
    return <ErrorState error={chainQuery.error} />;
  }

  const chain = chainQuery.data;
  const state = chain.state;
  const regime = chain.regime;
  const decision = chain.decision;
  const forecast = chain.forecast;
  const weather = weatherQuery.data;
  const ports = portsQuery.data ?? [];
  const snapshot = ports.find((p) => p.code === chain.portCode);

  const day1 = forecast[0];
  const day2 = forecast[1];
  const horizonPeak = forecast.reduce<ForecastPoint | null>(
    (peak, row) => (!peak || row.congestionIndex > peak.congestionIndex ? row : peak),
    null,
  );

  return (
    <div className="h-full grid grid-rows-[auto_1fr] gap-2 p-2 overflow-hidden">
      {/* Header: identity, risk, freshness, and the port switcher. */}
      <div className="panel px-3 py-2 flex items-center gap-3 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="text-[16px] text-[var(--color-foreground)] truncate">
              {chain.name}
            </span>
            <span className="text-[10px] text-[var(--color-muted-foreground)]">
              {chain.portCode}
            </span>
            {snapshot && (
              <Chip tone={riskTone(snapshot.risk)}>{riskLabel(snapshot.risk)}</Chip>
            )}
          </div>
          <div className="text-[9px] text-[var(--color-muted-foreground)]">
            {snapshot?.authority ?? "Port authority not in registry"}
          </div>
        </div>

        <div className="flex items-center gap-2 ml-auto flex-wrap">
          <ProvenanceChip
            status={state.dataStatus}
            ageHours={state.dataAgeHours}
            detail={`Observed ${formatUtc(state.observedAt)}`}
          />
          <span className="text-[9px] text-[var(--color-muted-foreground)]">
            OBSERVED {formatUtc(state.observedAt)} · ORIGIN{" "}
            {formatUtc(day1?.originDate ?? null)} · MODEL{" "}
            <span className="text-[var(--color-cyan)]">{day1?.source ?? "n/a"}</span>
          </span>
          <select
            aria-label="Select port"
            value={chain.portCode}
            onChange={(event) =>
              navigate({ to: "/port", search: { port: event.target.value } })
            }
            className="border border-[var(--color-line-strong)] bg-[oklch(0.10_0.02_240)] px-2 py-1 text-[10px] tracking-[0.1em] text-[var(--color-foreground)] outline-none"
          >
            {ports.map((port) => (
              <option key={port.code} value={port.code}>
                {port.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="min-h-0 grid grid-cols-[300px_1fr_320px] gap-2">
        {/* ------------------------------------------------------------ NOW */}
        <div className="min-h-0 grid grid-rows-[auto_auto_1fr] gap-2">
          <Panel title="NOW · OBSERVED" right={state.dataStatus}>
            <div className="p-2 grid grid-cols-2 gap-1.5">
              <Metric
                label="CONGESTION"
                value={state.observedCongestionIndex?.toFixed(1) ?? "n/a"}
                tone={
                  (state.observedCongestionIndex ?? 0) >= 65
                    ? "red"
                    : (state.observedCongestionIndex ?? 0) >= 50
                      ? "amber"
                      : "mint"
                }
                sub="0-100 pressure index"
              />
              <Metric
                label="BERTH WAIT"
                value={state.delayHours?.toFixed(1) ?? "n/a"}
                unit="h"
                tone="amber"
                sub="proxy from call pressure"
              />
            </div>
            <div className="px-3 pb-2">
              <MetricRow label="Daily port calls">
                <Value value={state.vesselCalls} digits={1} />
              </MetricRow>
              <MetricRow label="Queue buildup (anchorage)">
                <Value value={state.anchorageCount} digits={1} />
              </MetricRow>
              <MetricRow label="Throughput">
                <Value value={state.throughputTonnes} digits={0} unit=" t" />
              </MetricRow>
              <MetricRow label="Utilization">
                <Value value={state.utilization} digits={0} scale={100} unit="%" />
              </MetricRow>
              <MetricRow label="AIS confidence">
                <Value value={state.aisConfidence} digits={2} />
              </MetricRow>
            </div>
          </Panel>

          <Panel title="SPECIALIST PRESSURE">
            <div className="p-3 space-y-2">
              {(
                [
                  ["Queue pressure", state.queuePressure],
                  ["Capacity pressure", state.capacityPressure],
                  ["Berth pressure", state.berthPressure],
                  ["Arrival clustering", state.arrivalClustering],
                  ["Anomaly score", state.anomalyScore],
                  ["Disruption pressure", state.disruptionPressure],
                  ["Weather impact", state.weatherImpact],
                  ["Data quality", state.dataQuality],
                ] as Array<[string, number | null | undefined]>
              ).map(([label, value]) => (
                <div key={label} className="space-y-1">
                  <div className="flex justify-between text-[10px]">
                    <span className="text-[var(--color-muted-foreground)]">
                      {label}
                    </span>
                    <Value value={value} digits={2} />
                  </div>
                  <Bar
                    value={value ?? 0}
                    tone={
                      label === "Data quality"
                        ? (value ?? 1) >= 0.75
                          ? "mint"
                          : "amber"
                        : (value ?? 0) >= 0.7
                          ? "red"
                          : (value ?? 0) >= 0.45
                            ? "amber"
                            : "cyan"
                    }
                  />
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="OBSERVED HISTORY · 14 DAYS">
            <div className="p-3">
              <Sparkline
                data={state.congestionHistory.map((point) => point.value)}
                tone="cyan"
                height={54}
                fill
              />
              <div className="mt-1 flex justify-between text-[9px] text-[var(--color-muted-foreground)]">
                <span>{formatDate(state.congestionHistory[0]?.date ?? null)}</span>
                <span>
                  {formatDate(
                    state.congestionHistory[state.congestionHistory.length - 1]?.date ??
                      null,
                  )}
                </span>
              </div>
            </div>
          </Panel>
        </div>

        {/* ---------------------------------------------------- FORECAST + WHY */}
        <div className="min-h-0 grid grid-rows-[auto_1fr_auto] gap-2">
          <div className="grid grid-cols-3 gap-2">
            <Metric
              label="NEXT 24H · CONGESTION"
              value={day1?.congestionIndex.toFixed(1) ?? "n/a"}
              tone={
                (day1?.congestionIndex ?? 0) >= 65
                  ? "red"
                  : (day1?.congestionIndex ?? 0) >= 50
                    ? "amber"
                    : "mint"
              }
              sub={
                day1
                  ? `80% band ${day1.q10.toFixed(0)}–${day1.q90.toFixed(0)} · conf ${(day1.confidence * 100).toFixed(0)}%`
                  : "no forecast"
              }
            />
            <Metric
              label="NEXT 48H"
              value={day2?.congestionIndex.toFixed(1) ?? "n/a"}
              tone="cyan"
              sub={
                day2
                  ? `wait ${day2.delayHoursP50.toFixed(1)}h · band ${day2.intervalWidth.toFixed(0)}`
                  : "no forecast"
              }
            />
            <Metric
              label="10-DAY PEAK"
              value={horizonPeak?.congestionIndex.toFixed(1) ?? "n/a"}
              tone="amber"
              sub={
                horizonPeak
                  ? `day ${horizonPeak.day} (${horizonPeak.dateLabel}) · ${horizonPeak.severity}`
                  : "no forecast"
              }
            />
          </div>

          <Panel
            title="10-DAY QUANTILE FORECAST"
            right={
              day1
                ? `${day1.source}${day1.conformalOffset != null ? ` · conformal ±${day1.conformalOffset.toFixed(2)}` : ""}`
                : undefined
            }
          >
            <div className="p-2 h-full flex flex-col gap-2 min-h-0">
              <ForecastBands forecast={forecast} />
              <div className="overflow-auto">
                <table className="w-full text-[10px]">
                  <thead>
                    <tr className="label-xs text-left border-b border-[var(--color-line)]">
                      <th className="py-1 font-normal">DAY</th>
                      <th className="py-1 font-normal">DATE</th>
                      <th className="py-1 font-normal text-right">Q10</th>
                      <th className="py-1 font-normal text-right">Q50</th>
                      <th className="py-1 font-normal text-right">Q90</th>
                      <th className="py-1 font-normal text-right">WAIT</th>
                      <th className="py-1 font-normal text-right">CONF</th>
                      <th className="py-1 font-normal text-right">DISAGREE</th>
                      <th className="py-1 font-normal text-right">SEV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forecast.map((row) => (
                      <tr
                        key={row.day}
                        className="border-b border-[var(--color-line)]/30"
                      >
                        <td className="py-[3px] tabular-nums">+{row.day}</td>
                        <td className="py-[3px] text-[var(--color-muted-foreground)]">
                          {row.dateLabel}
                        </td>
                        <td className="py-[3px] text-right tabular-nums text-[var(--color-muted-foreground)]">
                          {row.q10.toFixed(1)}
                        </td>
                        <td className="py-[3px] text-right tabular-nums text-[var(--color-foreground)]">
                          {row.q50.toFixed(1)}
                        </td>
                        <td className="py-[3px] text-right tabular-nums text-[var(--color-muted-foreground)]">
                          {row.q90.toFixed(1)}
                        </td>
                        <td className="py-[3px] text-right tabular-nums">
                          {row.delayHoursP50.toFixed(1)}h
                        </td>
                        <td className="py-[3px] text-right tabular-nums text-[var(--color-cyan)]">
                          {(row.confidence * 100).toFixed(0)}%
                        </td>
                        <td className="py-[3px] text-right tabular-nums text-[var(--color-purple)]">
                          <Value value={row.modelDisagreement} digits={2} />
                        </td>
                        <td className="py-[3px] text-right">
                          <Chip tone={severityTone(row.severity)}>{row.severity}</Chip>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </Panel>

          <Panel title="WHY · RAW SIGNAL → EXPERT → REGIME → FORECAST → DECISION">
            <div className="p-2 grid grid-cols-5 gap-1.5">
              {chain.stages.map((stage, index) => (
                <ChainCard
                  key={stage.stage}
                  stage={stage}
                  isLast={index === chain.stages.length - 1}
                />
              ))}
            </div>
          </Panel>
        </div>

        {/* ------------------------------------------------ REGIME + DECISION */}
        <div className="min-h-0 grid grid-rows-[auto_auto_1fr] gap-2">
          <Panel
            title="HSMM REGIME"
            right={regime ? `conf ${(regime.confidence * 100).toFixed(0)}%` : undefined}
          >
            {regime ? (
              <div className="p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[15px] text-[var(--color-foreground)]">
                    {regime.state}
                  </span>
                  <ProvenanceChip
                    status={regime.dataStatus}
                    ageHours={regime.dataAgeHours}
                  />
                </div>
                <div className="space-y-1.5">
                  {(
                    [
                      ["p(normal)", regime.probabilities.normal, "mint"],
                      ["p(congested)", regime.probabilities.congested, "amber"],
                      ["p(severe)", regime.probabilities.severe, "red"],
                    ] as const
                  ).map(([label, value, tone]) => (
                    <div key={label}>
                      <div className="flex justify-between text-[10px]">
                        <span className="text-[var(--color-muted-foreground)]">
                          {label}
                        </span>
                        <span className="tabular-nums">{value.toFixed(3)}</span>
                      </div>
                      <Bar value={value} tone={tone} />
                    </div>
                  ))}
                </div>
                <div className="pt-1">
                  <MetricRow label="Days in state">
                    <Value value={regime.daysInState} digits={1} />
                  </MetricRow>
                  <MetricRow label="Expected remaining">
                    <Value value={regime.expectedRemainingDays} digits={1} unit="d" />
                  </MetricRow>
                  <MetricRow label="Transition risk 24h">
                    <Value value={regime.transitionRisk24h} digits={3} />
                  </MetricRow>
                </div>
              </div>
            ) : (
              <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
                No regime state for this port in the current run.
              </div>
            )}
          </Panel>

          <Panel title="MARINE WEATHER" right={weather?.weatherRegime ?? undefined}>
            {weather ? (
              <div className="p-3">
                <MetricRow label="Wind / gust">
                  <Value value={weather.windKnots} digits={1} unit="kn" />
                  <span className="text-[var(--color-muted-foreground)]"> / </span>
                  <Value value={weather.gustKnots} digits={1} unit="kn" />
                </MetricRow>
                <MetricRow label="Wave height">
                  <Value value={weather.waveHeightM} digits={2} unit="m" />
                </MetricRow>
                <MetricRow label="Rain 24h">
                  <Value value={weather.rainfallMm24h} digits={1} unit="mm" />
                </MetricRow>
                <MetricRow label="Impact index">
                  <Value value={weather.impactScore} digits={3} />
                </MetricRow>
                <MetricRow label="Shock / persistence">
                  <Value value={weather.shockScore} digits={2} />
                  <span className="text-[var(--color-muted-foreground)]"> / </span>
                  <Value value={weather.persistenceScore} digits={2} />
                </MetricRow>
                <div className="mt-2 text-[9px] leading-snug text-[var(--color-muted-foreground)]">
                  {weather.advisory}
                </div>
              </div>
            ) : (
              <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
                No measured marine weather for this port in the current run.
              </div>
            )}
          </Panel>

          <Panel title="WHAT SHOULD WE DO">
            {decision ? (
              <div className="p-3 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-[13px] text-[var(--color-foreground)] leading-tight">
                    {decision.title}
                  </span>
                  <Chip tone={riskTone(decision.severity)}>
                    {decision.severity.toUpperCase()}
                  </Chip>
                </div>
                <div className="text-[10px] text-[var(--color-cyan)]">
                  {decision.action} · {decision.target}
                </div>
                <div className="text-[11px] leading-relaxed text-[var(--color-foreground)]">
                  {decision.actions.join(" ")}
                </div>

                <div className="pt-1">
                  <MetricRow label="Expected delay saved">
                    <Value
                      value={decision.expectedDelaySavedHours}
                      digits={1}
                      unit="h"
                      tone="mint"
                    />
                  </MetricRow>
                  <MetricRow label="Congestion probability">
                    <Value value={decision.congestionProbability} digits={2} />
                  </MetricRow>
                  <MetricRow label="Decision confidence">
                    <Value value={decision.confidence} digits={2} tone="cyan" />
                  </MetricRow>
                  <MetricRow label="Uncertainty">
                    <Value value={decision.uncertainty} digits={2} tone="purple" />
                  </MetricRow>
                </div>

                {decision.topDrivers.length > 0 && (
                  <div className="pt-1">
                    <div className="label-xs mb-1">TOP CONTRIBUTING FACTORS</div>
                    {decision.topDrivers.map((driver) => (
                      <div key={driver.factor} className="mb-1">
                        <div className="flex justify-between text-[9px]">
                          <span className="text-[var(--color-muted-foreground)]">
                            {driver.factor}
                          </span>
                          <Value value={driver.contribution} digits={3} />
                        </div>
                        <Bar
                          value={(driver.contribution ?? 0) / 0.3}
                          tone="amber"
                        />
                      </div>
                    ))}
                  </div>
                )}

                <div className="pt-1 text-[9px] leading-snug text-[var(--color-muted-foreground)]">
                  <div className="text-[var(--color-foreground)]">
                    {decision.expectedImpact}
                  </div>
                  <div className="mt-1">{decision.rationale}</div>
                  <div className="mt-1">
                    <span className="text-[var(--color-amber)]">Fallback:</span>{" "}
                    {decision.alternativeAction}
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
                No decision produced for this port in the current run.
              </div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}

function severityTone(severity: string) {
  switch (severity) {
    case "SEVERE":
      return "red" as const;
    case "HIGH":
      return "amber" as const;
    case "MOD":
      return "cyan" as const;
    default:
      return "mint" as const;
  }
}

function ChainCard({ stage, isLast }: { stage: ChainStage; isLast: boolean }) {
  const entries = Object.entries(stage.metrics).filter(
    ([, value]) => value !== null && value !== undefined,
  );
  return (
    <div className="panel p-2 relative min-w-0">
      <div className="flex items-center justify-between gap-1">
        <span className="label-xs truncate">{stage.stage}</span>
        {stage.confidence != null && (
          <span className="text-[9px] tabular-nums text-[var(--color-cyan)]">
            {(stage.confidence * 100).toFixed(0)}%
          </span>
        )}
      </div>
      <div className="mt-0.5 text-[9px] text-[var(--color-muted-foreground)] leading-snug line-clamp-2">
        {stage.label}
      </div>
      <div className="mt-1 space-y-[2px]">
        {entries.slice(0, 4).map(([key, value]) => (
          <div key={key} className="flex justify-between gap-1 text-[9px]">
            <span className="text-[var(--color-muted-foreground)] truncate">
              {humanise(key)}
            </span>
            <span className="tabular-nums text-[var(--color-foreground)] shrink-0">
              {typeof value === "number" ? value.toFixed(2) : String(value)}
            </span>
          </div>
        ))}
        {!entries.length && (
          <div className="text-[9px] text-[var(--color-muted-foreground)]">
            not produced
          </div>
        )}
      </div>
      {!isLast && (
        <span className="absolute -right-[9px] top-1/2 -translate-y-1/2 text-[var(--color-cyan)] text-[10px]">
          ▶
        </span>
      )}
    </div>
  );
}

function humanise(key: string): string {
  return key
    .replace(/([A-Z])/g, " $1")
    .replace(/^./, (c) => c.toUpperCase())
    .trim();
}

/** Fan chart of the q10/q50/q90 band across the forecast horizon. */
function ForecastBands({ forecast }: { forecast: ForecastPoint[] }): ReactNode {
  if (forecast.length < 2) {
    return (
      <div className="h-[120px] grid place-items-center text-[10px] text-[var(--color-muted-foreground)]">
        Not enough forecast rows to draw a band.
      </div>
    );
  }
  const width = 100;
  const height = 120;
  const values = forecast.flatMap((row) => [row.q10, row.q90]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (index: number) => (index / (forecast.length - 1)) * width;
  const y = (value: number) => height - ((value - min) / span) * (height - 12) - 6;

  const upper = forecast.map((row, i) => `${x(i).toFixed(1)},${y(row.q90).toFixed(1)}`);
  const lower = forecast
    .map((row, i) => `${x(i).toFixed(1)},${y(row.q10).toFixed(1)}`)
    .reverse();
  const median = forecast.map((row, i) => `${x(i).toFixed(1)},${y(row.q50).toFixed(1)}`);

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="w-full"
        style={{ height }}
      >
        <polygon
          points={[...upper, ...lower].join(" ")}
          fill="var(--color-cyan)"
          opacity={0.14}
        />
        <polyline
          points={median.join(" ")}
          fill="none"
          stroke="var(--color-cyan)"
          strokeWidth={1.4}
        />
        <line
          x1="0"
          x2={width}
          y1={y(50)}
          y2={y(50)}
          stroke="var(--color-amber)"
          strokeDasharray="3 3"
          strokeWidth={0.6}
          opacity={0.7}
        />
      </svg>
      <div className="flex justify-between text-[9px] text-[var(--color-muted-foreground)]">
        <span>{forecast[0].dateLabel}</span>
        <span className="text-[var(--color-amber)]">congestion threshold 50</span>
        <span>{forecast[forecast.length - 1].dateLabel}</span>
      </div>
    </div>
  );
}
