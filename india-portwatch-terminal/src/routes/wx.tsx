import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  Chip,
  ErrorState,
  Loading,
  Metric,
  MetricRow,
  Panel,
  Sparkline,
  Value,
  formatDate,
  formatUtc,
} from "@/components/terminal/ui";
import { fetchWeather, fetchWeatherIntelligence } from "@/services/portwatch";
import type { WeatherSignal } from "@/types/portwatch";

export const Route = createFileRoute("/wx")({
  validateSearch: (search: Record<string, unknown>) => ({
    port: typeof search.port === "string" ? search.port : "INMAA",
  }),
  component: WeatherIntelligenceScreen,
});

/**
 * Weather Intelligence. Physical values come straight from Open-Meteo (surface
 * and marine), the risk decomposition is what the weather expert actually fed
 * the model, and the shock-vs-persistence split is what tells an operator
 * whether to shuffle one berth window or replan the week.
 */
function WeatherIntelligenceScreen() {
  const { port: portCode } = Route.useSearch();
  const navigate = useNavigate();

  const weatherQuery = useQuery({
    queryKey: ["weather-all"],
    queryFn: fetchWeather,
    staleTime: 60_000,
  });
  const intelQuery = useQuery({
    queryKey: ["weather-intelligence"],
    queryFn: fetchWeatherIntelligence,
    staleTime: 60_000,
    retry: 0,
  });

  if (weatherQuery.isLoading) return <Loading label="LOADING MARINE WEATHER" />;
  if (weatherQuery.isError || !weatherQuery.data) {
    return <ErrorState error={weatherQuery.error} />;
  }

  const signals = weatherQuery.data;
  const intelligence = intelQuery.data;
  const selected =
    signals.find((signal) => signal.portCode === portCode) ?? signals[0];

  const ranked = [...signals].sort(
    (a, b) => (b.impactScore ?? 0) - (a.impactScore ?? 0),
  );

  return (
    <div className="h-full grid grid-cols-[280px_1fr] gap-2 p-2 overflow-hidden">
      <div className="min-h-0 grid grid-rows-[auto_1fr] gap-2">
        <Panel title="NATIONAL MARINE PICTURE">
          {intelligence?.available ? (
            <div className="p-3">
              <MetricRow label="Mean weather impact">
                <Value value={intelligence.meanImpact} digits={3} />
              </MetricRow>
              <MetricRow label="Mean wind">
                <Value value={intelligence.meanWindKnots} digits={1} unit="kn" />
              </MetricRow>
              <MetricRow label="Mean wave height">
                <Value value={intelligence.meanWaveHeightM} digits={2} unit="m" />
              </MetricRow>
              <MetricRow label="Wind / rain / wave risk">
                <Value value={intelligence.meanWindRisk} digits={2} />
                <span className="text-[var(--color-muted-foreground)]"> · </span>
                <Value value={intelligence.meanRainRisk} digits={2} />
                <span className="text-[var(--color-muted-foreground)]"> · </span>
                <Value value={intelligence.meanWaveRisk} digits={2} />
              </MetricRow>
              <MetricRow label="Storm risk">
                <Value value={intelligence.meanStormRisk} digits={3} />
              </MetricRow>
              <MetricRow label="Highest impact port">
                <span className="text-[var(--color-amber)]">
                  {intelligence.highestImpactPort ?? "n/a"}
                </span>
              </MetricRow>
              <MetricRow label="Ports covered">
                <span className="tabular-nums">{intelligence.portsCovered ?? 0}</span>
              </MetricRow>
              {intelligence.persistentPorts?.length ? (
                <div className="mt-2 text-[9px] leading-snug">
                  <span className="text-[var(--color-amber)]">
                    Persistent disruption:
                  </span>{" "}
                  {intelligence.persistentPorts.join(" · ")}
                </div>
              ) : (
                <div className="mt-2 text-[9px] text-[var(--color-muted-foreground)]">
                  No port is currently under sustained weather disruption.
                </div>
              )}
              <div className="mt-2 pt-2 border-t border-[var(--color-line)]/50 text-[8px] text-[var(--color-muted-foreground)]">
                {intelligence.dataSource} · observed{" "}
                {formatUtc(intelligence.observedAt ?? null)}
              </div>
            </div>
          ) : (
            <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
              {intelligence?.reason ??
                "No marine weather was produced in this run."}
            </div>
          )}
        </Panel>

        <Panel title="PORTS BY WEATHER LOAD" bodyClassName="overflow-auto">
          <div className="p-1.5 space-y-0.5">
            {ranked.map((signal) => (
              <button
                key={signal.portCode}
                onClick={() =>
                  navigate({ to: "/wx", search: { port: signal.portCode } })
                }
                className={`w-full grid grid-cols-[1fr_46px_54px] items-center gap-2 px-2 py-1.5 text-[10px] transition-colors ${
                  signal.portCode === selected?.portCode
                    ? "bg-[var(--color-cyan)]/8 text-[var(--color-cyan)]"
                    : "hover:bg-[var(--color-cyan)]/5"
                }`}
              >
                <span className="text-left truncate">{signal.name}</span>
                <span className="text-right tabular-nums">
                  <Value value={signal.impactScore} digits={2} />
                </span>
                <Chip tone={regimeTone(signal.weatherRegime)}>
                  {signal.weatherRegime ?? "N/A"}
                </Chip>
              </button>
            ))}
          </div>
        </Panel>
      </div>

      {selected ? (
        <div className="min-h-0 overflow-auto space-y-2">
          <div className="grid grid-cols-5 gap-2">
            <Metric
              label="WIND"
              value={<Value value={selected.windKnots} digits={1} />}
              unit="kn"
              tone={(selected.windRisk ?? 0) >= 0.6 ? "red" : "cyan"}
              sub={`gust ${selected.gustKnots?.toFixed(1) ?? "n/a"} kn`}
            />
            <Metric
              label="WAVE HEIGHT"
              value={<Value value={selected.waveHeightM} digits={2} />}
              unit="m"
              tone={(selected.waveRisk ?? 0) >= 0.6 ? "red" : "cyan"}
              sub={selected.seaState ?? "sea state n/a"}
            />
            <Metric
              label="RAIN 24H"
              value={<Value value={selected.rainfallMm24h} digits={1} />}
              unit="mm"
              tone="cyan"
              sub={`rain risk ${selected.rainRisk?.toFixed(2) ?? "n/a"}`}
            />
            <Metric
              label="VISIBILITY"
              value={<Value value={selected.visibilityKm} digits={1} />}
              unit="km"
              tone="cyan"
              sub={`storm risk ${selected.stormRisk?.toFixed(2) ?? "n/a"}`}
            />
            <Metric
              label="IMPACT INDEX"
              value={<Value value={selected.impactScore} digits={3} />}
              tone={(selected.impactScore ?? 0) >= 0.6 ? "red" : "amber"}
              sub={`confidence ${selected.confidence?.toFixed(2) ?? "n/a"}`}
            />
          </div>

          <div className="grid grid-cols-[1fr_1fr] gap-2">
            <Panel title={`RISK DECOMPOSITION · ${selected.name.toUpperCase()}`}>
              <div className="p-3 space-y-2">
                {(
                  [
                    ["Wind risk", selected.windRisk],
                    ["Rain risk", selected.rainRisk],
                    ["Wave risk", selected.waveRisk],
                    ["Storm risk", selected.stormRisk],
                    ["Composite impact", selected.impactScore],
                  ] as Array<[string, number | null]>
                ).map(([label, value]) => (
                  <div key={label}>
                    <div className="flex justify-between text-[10px]">
                      <span className="text-[var(--color-muted-foreground)]">
                        {label}
                      </span>
                      <Value value={value} digits={3} />
                    </div>
                    <Bar
                      value={value ?? 0}
                      tone={
                        (value ?? 0) >= 0.6
                          ? "red"
                          : (value ?? 0) >= 0.35
                            ? "amber"
                            : "cyan"
                      }
                    />
                  </div>
                ))}
                <div className="pt-2 mt-1 border-t border-[var(--color-line)]/50 text-[9px] leading-snug text-[var(--color-muted-foreground)]">
                  These are the exact 0-1 features the forecasting model consumed
                  for this port. {selected.dataSource}.
                </div>
              </div>
            </Panel>

            <Panel title="SHOCK VS PERSISTENT DISRUPTION">
              <div className="p-3 space-y-3">
                <div className="grid grid-cols-3 gap-2">
                  <div className="panel px-2 py-1.5">
                    <div className="label-xs">SHOCK</div>
                    <div className="text-[15px] tabular-nums text-[var(--color-amber)]">
                      <Value value={selected.shockScore} digits={2} />
                    </div>
                  </div>
                  <div className="panel px-2 py-1.5">
                    <div className="label-xs">PERSISTENCE</div>
                    <div className="text-[15px] tabular-nums text-[var(--color-red)]">
                      <Value value={selected.persistenceScore} digits={2} />
                    </div>
                  </div>
                  <div className="panel px-2 py-1.5">
                    <div className="label-xs">FORWARD LOAD</div>
                    <div className="text-[15px] tabular-nums text-[var(--color-cyan)]">
                      <Value value={selected.forwardLoad} digits={2} />
                    </div>
                  </div>
                </div>
                <div className="text-[10px] leading-relaxed text-[var(--color-foreground)]">
                  <Chip tone={regimeTone(selected.weatherRegime)}>
                    {selected.weatherRegime ?? "UNKNOWN"}
                  </Chip>{" "}
                  {selected.advisory}
                </div>
                {selected.forecast.length > 1 && (
                  <div>
                    <div className="label-xs mb-1">
                      FORECAST WEATHER IMPACT · NEXT {selected.forecast.length} DAYS
                    </div>
                    <Sparkline
                      data={selected.forecast.map((point) => point.impact)}
                      tone="purple"
                      height={44}
                      fill
                    />
                    <div className="flex justify-between text-[9px] text-[var(--color-muted-foreground)]">
                      <span>{formatDate(selected.forecast[0]?.date ?? null)}</span>
                      <span>
                        {formatDate(
                          selected.forecast[selected.forecast.length - 1]?.date ??
                            null,
                        )}
                      </span>
                    </div>
                  </div>
                )}
                <div className="text-[9px] text-[var(--color-muted-foreground)]">
                  Forward load is a known-future covariate: a weather forecast
                  issued today is available at the forecast origin, so using it
                  is not leakage.
                </div>
              </div>
            </Panel>
          </div>

          <Panel title="ALL PORTS · MEASURED CONDITIONS">
            <div className="overflow-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="label-xs text-left border-b border-[var(--color-line)]">
                    <th className="py-1.5 px-2 font-normal">PORT</th>
                    <th className="py-1.5 px-2 font-normal text-right">WIND kn</th>
                    <th className="py-1.5 px-2 font-normal text-right">GUST kn</th>
                    <th className="py-1.5 px-2 font-normal text-right">WAVE m</th>
                    <th className="py-1.5 px-2 font-normal text-right">RAIN mm</th>
                    <th className="py-1.5 px-2 font-normal text-right">VIS km</th>
                    <th className="py-1.5 px-2 font-normal text-right">IMPACT</th>
                    <th className="py-1.5 px-2 font-normal text-right">PERSIST</th>
                    <th className="py-1.5 px-2 font-normal">REGIME</th>
                    <th className="py-1.5 px-2 font-normal">OBSERVED</th>
                  </tr>
                </thead>
                <tbody>
                  {ranked.map((signal) => (
                    <tr
                      key={signal.portCode}
                      className="border-b border-[var(--color-line)]/30"
                    >
                      <td className="py-1 px-2 truncate">{signal.name}</td>
                      <td className="py-1 px-2 text-right tabular-nums">
                        <Value value={signal.windKnots} digits={1} />
                      </td>
                      <td className="py-1 px-2 text-right tabular-nums">
                        <Value value={signal.gustKnots} digits={1} />
                      </td>
                      <td className="py-1 px-2 text-right tabular-nums">
                        <Value value={signal.waveHeightM} digits={2} />
                      </td>
                      <td className="py-1 px-2 text-right tabular-nums">
                        <Value value={signal.rainfallMm24h} digits={1} />
                      </td>
                      <td className="py-1 px-2 text-right tabular-nums">
                        <Value value={signal.visibilityKm} digits={1} />
                      </td>
                      <td className="py-1 px-2 text-right tabular-nums">
                        <Value value={signal.impactScore} digits={3} />
                      </td>
                      <td className="py-1 px-2 text-right tabular-nums">
                        <Value value={signal.persistenceScore} digits={2} />
                      </td>
                      <td className="py-1 px-2">
                        <Chip tone={regimeTone(signal.weatherRegime)}>
                          {signal.weatherRegime ?? "N/A"}
                        </Chip>
                      </td>
                      <td className="py-1 px-2 text-[var(--color-muted-foreground)]">
                        {formatUtc(signal.observedAt)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      ) : (
        <Panel title="WEATHER">
          <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
            No marine weather was produced in this run.
          </div>
        </Panel>
      )}
    </div>
  );
}

function regimeTone(regime: string | null | undefined) {
  switch (regime) {
    case "PERSISTENT":
      return "red" as const;
    case "SHOCK":
      return "amber" as const;
    case "UNSETTLED":
      return "cyan" as const;
    case "CALM":
      return "mint" as const;
    default:
      return "muted" as const;
  }
}

export type { WeatherSignal };
