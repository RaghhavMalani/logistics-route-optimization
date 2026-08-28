import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Chip, Sparkline, Bar } from "@/components/terminal/ui";
import {
  fetchDecisionRecommendation,
  fetchForecastForPort,
  fetchHSMMRegime,
  fetchModelPipelineStatuses,
} from "@/services/model";
import { fetchNewsEvents } from "@/services/news";
import { fetchPorts, fetchPortSnapshot } from "@/services/ports";
import { getMarineWeatherIntelligence } from "@/services/weatherService";
import { fetchWeatherSignal } from "@/services/weather";

export const Route = createFileRoute("/port")({
  validateSearch: (search: Record<string, unknown>) => ({
    port: typeof search.port === "string" ? search.port : "INMAA",
  }),
  component: PortPage,
});



function PortPage() {
  const { port } = Route.useSearch();
  const selectedPortCode = port || "INMAA";
  const navigate = useNavigate({ from: "/port" });

  const portsQuery = useQuery({
    queryKey: ["ports"],
    queryFn: fetchPorts,
    staleTime: 60_000,
  });

  const availablePorts = portsQuery.data ?? [];

  const handlePortChange = (nextPort: string) => {
    navigate({
      search: (prev) => ({
        ...prev,
        port: nextPort,
      }),
    });
  };

  const portQuery = useQuery({
    queryKey: ["port", selectedPortCode],
    queryFn: () => fetchPortSnapshot(selectedPortCode),
    staleTime: 30_000,
  });

  const chn = portQuery.data;
  const activePortCode = chn?.code ?? selectedPortCode;

  const weatherQuery = useQuery({
    queryKey: ["weather", activePortCode],
    queryFn: () => fetchWeatherSignal(activePortCode),
    enabled: Boolean(chn),
    staleTime: 30_000,
  });

  const regimeQuery = useQuery({
    queryKey: ["regime", activePortCode],
    queryFn: () => fetchHSMMRegime(activePortCode),
    enabled: Boolean(chn),
    staleTime: 30_000,
  });

  const forecastQuery = useQuery({
    queryKey: ["forecast", activePortCode],
    queryFn: () => fetchForecastForPort(activePortCode),
    enabled: Boolean(chn),
    staleTime: 30_000,
  });

  const recommendationQuery = useQuery({
    queryKey: ["decision", activePortCode],
    queryFn: () => fetchDecisionRecommendation(activePortCode),
    enabled: Boolean(chn),
    staleTime: 30_000,
  });

  const expertsQuery = useQuery({
    queryKey: ["model-pipeline"],
    queryFn: fetchModelPipelineStatuses,
    staleTime: 60_000,
  });

  const newsQuery = useQuery({
    queryKey: ["news-events"],
    queryFn: fetchNewsEvents,
    staleTime: 30_000,
  });

  if (
    portQuery.isLoading ||
    weatherQuery.isLoading ||
    regimeQuery.isLoading ||
    forecastQuery.isLoading ||
    recommendationQuery.isLoading ||
    expertsQuery.isLoading ||
    newsQuery.isLoading
  ) {
    return (
      <div className="h-full grid place-items-center text-[var(--color-cyan)] text-[12px] tracking-[0.2em]">
        LOADING LIVE PORT COCKPIT...
      </div>
    );
  }

  if (
    portQuery.isError ||
    weatherQuery.isError ||
    regimeQuery.isError ||
    forecastQuery.isError ||
    recommendationQuery.isError ||
    expertsQuery.isError ||
    newsQuery.isError ||
    !chn ||
    !weatherQuery.data ||
    !regimeQuery.data ||
    !forecastQuery.data ||
    !recommendationQuery.data ||
    !expertsQuery.data
  ) {
    return (
      <div className="h-full grid place-items-center text-[var(--color-red)] text-[12px] tracking-[0.2em]">
        PORT COCKPIT API UNAVAILABLE
      </div>
    );
  }

  const weather = weatherQuery.data;
  const marine = getMarineWeatherIntelligence();
  const regime = regimeQuery.data;
  const forecastDays = forecastQuery.data;
  const recommendation = recommendationQuery.data;
  const experts = expertsQuery.data;
  const newsEvents = newsQuery.data ?? [];
  const newsForPort = newsEvents.filter((event) =>
    event.affectedPorts.includes(chn.code),
  );
  const portName = chn.name.toUpperCase();
  const riskTone =
    chn.risk === "severe" ? "red" : chn.risk === "congested" ? "amber" : "mint";
  const severityLabel =
    chn.risk === "severe"
      ? "SEVERE"
      : chn.risk === "congested"
        ? "HIGH"
        : "NORMAL";

  return (
    <div className="h-full overflow-auto">
      <div className="min-h-full p-3 space-y-3">
        {/* PAGE HEADER */}
        <div className="grid grid-cols-[1.4fr_1fr_0.9fr_1fr_1fr_1.1fr_1.1fr] gap-2 items-stretch">
          <div className="panel px-4 py-3 col-span-1">
            <div className="text-[9px] tracking-[0.24em] text-[var(--color-muted-foreground)]">
              PORT OPERATIONS COCKPIT FOR
            </div>
            <div className="text-[32px] leading-none tracking-[0.06em] text-[var(--color-foreground)] font-semibold">
              {portName}
            </div>
            <div className="text-[9px] tracking-[0.24em] text-[var(--color-muted-foreground)] mt-1">
              {chn.authority.toUpperCase()}
            </div>
          </div>
          <HdrField
            label="CURRENT PORT AUTHORITY"
            value={chn.authority}
            sub={`${chn.location.lat.toFixed(4)}° N, ${chn.location.lon.toFixed(4)}° E`}
          />
          <HdrField
            label="CURRENT REGIME"
            chip={<Chip tone={riskTone}>{severityLabel}</Chip>}
          />
          <HdrField
            label="FORECAST ORIGIN"
            value="07 MAY 2025"
            sub="03:00 UTC"
          />
          <HdrField
            label="MODEL CONFIDENCE"
            chip={<Chip tone="mint">HIGH</Chip>}
            sub={`${Math.round(chn.confidence * 100)}%`}
          />
          <div className="panel p-4">
            <div className="text-[10px] tracking-[0.35em] text-[var(--color-muted-foreground)] mb-2">
              SELECT PORT
            </div>
            <select
              value={selectedPortCode}
              onChange={(event) => handlePortChange(event.target.value)}
              className="w-full bg-transparent text-[13px] text-[var(--color-foreground)] uppercase tracking-wider outline-none"
            >
              {availablePorts.map((portOption) => (
                <option
                  key={portOption.portCode}
                  value={portOption.portCode}
                >
                  {portOption.name ?? portOption.portCode}
                </option>
              ))}
            </select>
          </div>
          <HdrField
            label="LAST UPDATED"
            value="07 May 2025 06:15 UTC"
            chip={<Chip tone="mint">● LIVE</Chip>}
          />
        </div>

        {/* TOP KPI STRIP */}
        <div className="grid grid-cols-7 gap-2">
          <Kpi
            label="SEVERITY"
            big={severityLabel}
            tone={riskTone}
            sub="HIGH IMPACT"
          />
          <Kpi
            label={`${portName} PORT CONGESTION`}
            big={(chn.congestion * 100).toFixed(1)}
            tone={riskTone}
            sub="Index (0-100)"
            spark={[45, 50, 58, 64, 68, 72, 75, chn.congestion * 100]}
            sparkTone={riskTone}
          />
          <Kpi
            label="PEAK DELAY (P95)"
            big={`${chn.delayHours.toFixed(1)} h`}
            tone={riskTone}
            sub="(next 24h)"
            spark={[
              8,
              9,
              10,
              11,
              12,
              Math.max(12, chn.delayHours - 1),
              chn.delayHours,
            ]}
            sparkTone={riskTone}
          />
          <Kpi
            label="THROUGHPUT (27D)"
            big={chn.throughput.toLocaleString()}
            tone="cyan"
            sub="TEU proxy"
            spark={[
              chn.throughput * 0.86,
              chn.throughput * 0.9,
              chn.throughput * 0.93,
              chn.throughput,
            ]}
            sparkTone="cyan"
          />
          <Kpi
            label="TRANSITION RISK"
            big={`${Math.round(regime.transitionRisk24h * 100)}%`}
            tone="amber"
            sub="(12h Horizon)"
            spark={[42, 48, 54, 58, 60, 62, regime.transitionRisk24h * 100]}
            sparkTone="amber"
          />
          <Kpi
            label="CONFIDENCE"
            big={`${Math.round(chn.confidence * 100)}%`}
            tone="mint"
            sub="Model Confidence"
            spark={[85, 88, 90, 91, 92, 93, chn.confidence * 100]}
            sparkTone="mint"
          />
          <div className="panel px-3 py-2 flex flex-col justify-between">
            <div>
              <div className="label-xs">RECOMMENDATION ({portName})</div>
              <div className="mt-1 text-[11px] text-[var(--color-foreground)] leading-snug">
                <span className="text-[var(--color-amber)]">
                  {recommendation.title}.
                </span>{" "}
                {recommendation.actions.slice(0, 3).join(". ")}.
              </div>
            </div>
            <button className="mt-1 self-end text-[var(--color-cyan)] text-[16px]">
              ›
            </button>
          </div>
        </div>

        {/* AI OPERATIONAL BRIEFING STRIP */}
        <div className="panel px-3 py-2 flex items-center gap-4 text-[11px]">
          <span className="text-[var(--color-cyan)] flex items-center gap-2 whitespace-nowrap">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-cyan)] animate-blink" />
            AI OPERATIONAL BRIEFING
          </span>
          <span className="text-[var(--color-foreground)] flex-1">
            {chn.name} congestion is {severityLabel.toLowerCase()}. Peak
            congestion is expected in the next 48h with {weather.windKnots} kt
            wind and {weather.seaState.toLowerCase()} sea state affecting
            pilotage and cargo ops.
          </span>
          <div className="flex items-center gap-3 text-[10px] text-[var(--color-mint)]">
            <span>● Activate congestion protocol</span>
            <span>● Prioritize berth allocation</span>
            <span>● Stagger arrivals</span>
            <span>● Advise vessels to slow steam</span>
          </div>
          <span className="text-[9px] text-[var(--color-muted-foreground)]">
            Generated by India PortWatch AI · {recommendation.timestamp}
          </span>
        </div>

        {/* MID GRID: twin | hsmm | weather */}
        <div
          className="grid grid-cols-[1.6fr_0.9fr_1.1fr] gap-2"
          style={{ minHeight: 380 }}
        >
          {/* MODEL-BACKED CONTEXT */}
          <div className="panel flex flex-col">
            <div className="panel-header">
              <span>MODEL-BACKED PORT CONTEXT — {portName}</span>
              <span>BACKEND OUTPUT</span>
            </div>

            <div className="p-4 space-y-4 text-[12px] leading-relaxed">
              <div>
                <div className="text-[10px] tracking-[0.32em] text-[var(--color-muted-foreground)] mb-1">
                  CURRENT DEMO MODE
                </div>
                <div className="text-[var(--color-foreground)]">
                  This cockpit is showing backend model outputs for{" "}
                  <span className="text-[var(--color-cyan)]">{portName}</span>.
                  The satellite/AIS digital-twin layer is hidden until real
                  satellite-derived vessel features are integrated.
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="panel p-3">
                  <div className="text-[10px] tracking-[0.25em] text-[var(--color-muted-foreground)]">
                    MODEL FLOW
                  </div>
                  <div className="mt-2 text-[var(--color-mint)]">
                    Features → HSMM regime → TFT forecast → Decision layer
                  </div>
                </div>

                <div className="panel p-3">
                  <div className="text-[10px] tracking-[0.25em] text-[var(--color-muted-foreground)]">
                    SELECTED PORT
                  </div>
                  <div className="mt-2 text-[var(--color-cyan)] text-[18px] font-semibold">
                    {portName}
                  </div>
                </div>

                <div className="panel p-3">
                  <div className="text-[10px] tracking-[0.25em] text-[var(--color-muted-foreground)]">
                    CURRENT SEVERITY
                  </div>
                  <div className="mt-2 text-[var(--color-amber)] text-[18px] font-semibold">
                    {severityLabel}
                  </div>
                </div>

                <div className="panel p-3">
                  <div className="text-[10px] tracking-[0.25em] text-[var(--color-muted-foreground)]">
                    FORECAST HORIZON
                  </div>
                  <div className="mt-2 text-[var(--color-mint)] text-[18px] font-semibold">
                    10 days
                  </div>
                </div>
              </div>

              <div className="text-[10px] text-[var(--color-muted-foreground)] border-t border-[var(--color-line)] pt-3">
                Planned satellite/AIS features: detected vessels, anchorage density,
                berth queue proxy, SAR confidence, AIS mismatch count, and route
                deviation.
              </div>
            </div>
          </div>

          {/* DATA READINESS */}
          <div className="panel flex flex-col">
            <div className="panel-header">
              <span>DATA READINESS</span>
              <span>REVIEW SAFE</span>
            </div>
            <div className="p-4 space-y-3 text-[11px]">
              {[
                ["HSMM regime", "model output", "mint"],
                ["TFT forecast", "model output", "mint"],
                ["Decision recommendation", "backend logic", "amber"],
                ["Weather", "backend cache", "mint"],
                ["News/NLP", "backend cache", "mint"],
                ["Satellite/AIS", "planned extension", "amber"],
              ].map(([label, status, tone]) => (
                <div
                  key={label}
                  className="grid grid-cols-[150px_1fr] gap-2 items-center"
                >
                  <span className="text-[var(--color-cyan)]">{label}</span>
                  <Chip tone={tone as any}>{status}</Chip>
                </div>
              ))}
            </div>
          </div>

          {/* HSMM + weather column */}
          <div className="grid grid-rows-2 gap-2">
            <div className="panel">
              <div className="panel-header">
                <span>HSMM REGIME INTELLIGENCE ({portName})</span>
              </div>
              <div className="p-3 space-y-2 text-[11px]">
                {[
                  ["Normal", regime.probabilities.normal * 100, "mint"],
                  ["Congested", regime.probabilities.congested * 100, "amber"],
                  ["Severe", regime.probabilities.severe * 100, "red"],
                ].map(([l, v, t]) => (
                  <div key={l as string}>
                    <div className="flex justify-between mb-1">
                      <span className="text-[var(--color-foreground)]">
                        {l}
                      </span>
                      <span
                        className={
                          t === "red"
                            ? "text-[var(--color-red)]"
                            : t === "amber"
                              ? "text-[var(--color-amber)]"
                              : "text-[var(--color-mint)]"
                        }
                      >
                        {Math.round(v as number)}%
                      </span>
                    </div>
                    <div className="h-1 bg-[var(--color-panel-2)]">
                      <div
                        className="h-full"
                        style={{
                          width: `${v}%`,
                          background:
                            t === "red"
                              ? "var(--color-red)"
                              : t === "amber"
                                ? "var(--color-amber)"
                                : "var(--color-mint)",
                        }}
                      />
                    </div>
                  </div>
                ))}
                <div className="pt-2 border-t border-[var(--color-line)] space-y-1 text-[10px]">
                  <Row k="Days in State" v={regime.daysInState.toFixed(1)} />
                  <Row
                    k="Expected remaining"
                    v={`${regime.expectedRemainingDays.toFixed(1)} day`}
                  />
                  <Row
                    k="Transition risk (24h)"
                    v={
                      <>
                        <span className="text-[var(--color-foreground)]">
                          {Math.round(regime.transitionRisk24h * 100)}%
                        </span>{" "}
                        <Chip
                          tone={
                            regime.transitionRisk24h > 0.55 ? "red" : "amber"
                          }
                        >
                          HIGH
                        </Chip>
                      </>
                    }
                  />
                  <Row
                    k="State confidence"
                    v={
                      <>
                        <span className="text-[var(--color-foreground)]">
                          {Math.round(regime.confidence * 100)}%
                        </span>{" "}
                        <Chip tone="red">HIGH</Chip>
                      </>
                    }
                  />
                </div>
              </div>
            </div>
            <div className="panel">
              <div className="panel-header">
                <span>WEATHER INTELLIGENCE · {portName} COASTAL OUTLOOK</span>
              </div>
              <div className="p-3 grid grid-cols-3 gap-x-3 gap-y-2 text-[10px]">
                <WxCell
                  l="WIND (10m)"
                  v={`${weather.windKnots} kt`}
                  sub={weather.windDirection}
                  tone="amber"
                />
                <WxCell l="GUSTS" v={`${weather.gustKnots} kt`} tone="red" />
                <WxCell
                  l="RAINFALL (24h)"
                  v={`${weather.rainfallMm24h} mm`}
                  sub={`${weather.precipRateMmH} mm/h`}
                  tone="cyan"
                />
                <WxCell
                  l="WAVE HEIGHT"
                  v={`${weather.waveHeightM} m`}
                  sub={`${marine.swell.direction} swell`}
                  tone="amber"
                />
                <WxCell l="SEA STATE" v={weather.seaState} />
                <WxCell
                  l="VISIBILITY"
                  v={`${weather.visibilityKm} km`}
                  sub={weather.visibilityKm < 8 ? "Reduced in squalls" : "Usable"}
                  tone={weather.visibilityKm < 8 ? "amber" : "mint"}
                />
                <div className="col-span-3 mt-1 border-t border-[var(--color-line)] pt-2">
                  <div className="label-xs mb-1">CYCLONE / MONSOON OPERATIONAL CONTEXT</div>
                  <div className="grid grid-cols-3 gap-2 text-[10px]">
                    <div>
                      <div className="text-[var(--color-muted-foreground)]">
                        SW Monsoon
                      </div>
                      <div className="text-[var(--color-amber)]">Active surge</div>
                    </div>
                    <div>
                      <div className="text-[var(--color-muted-foreground)]">
                        Cyclone Risk (7D)
                      </div>
                      <div className="text-[var(--color-red)]">
                        {Math.round(marine.cyclone.probability72h * 100)}% · {marine.cyclone.riskWindow}
                      </div>
                    </div>
                    <div>
                      <div className="text-[var(--color-muted-foreground)]">
                        Next Tide
                      </div>
                      <div className="text-[var(--color-foreground)]">
                        07:42 · flood +0.8m
                      </div>
                    </div>
                  </div>
                </div>
                <div className="col-span-3 border-t border-[var(--color-line)] pt-2">
                  <div className="grid grid-cols-[1fr_1fr_1fr] gap-2">
                    <WxOut k="pilotage_window" v="22:00-04:00Z" tone="red" />
                    <WxOut k="outer_band_eta" v="T+18h" />
                    <WxOut k="berth_productivity" v="-18%" tone="red" />
                  </div>
                  <div className="mt-2 text-[10px] leading-relaxed text-[var(--color-foreground)]">
                    Outer Bay rain bands and {marine.swell.heightM}m {marine.swell.direction} swell are holding deep-draft entries outside the inner harbor. Slow steaming and berth resequencing explain the elevated anchorage queue.
                  </div>
                </div>
                <div className="col-span-3 mt-1 border-t border-[var(--color-line)] pt-2">
                  <div className="label-xs mb-1">WEATHER MODULE OUTPUTS</div>
                  <div className="grid grid-cols-3 gap-2 text-[10px]">
                    <WxOut
                      k="weather_raw_score"
                      v={weather.impactScore.toFixed(2)}
                    />
                    <WxOut
                      k="weather_impact_score"
                      v={weather.impactScore.toFixed(2)}
                    />
                    <WxOut
                      k="weather_persistence"
                      v="SW_MONSOON_ACTIVE"
                      tone="mint"
                    />
                    <WxOut
                      k="weather_shock"
                      v={weather.shockSigma.toFixed(2)}
                    />
                    <WxOut
                      k="weather_hsmm_input"
                      v={weather.impactScore.toFixed(2)}
                      tone="red"
                    />
                    <WxOut
                      k="weather_tft_covariate"
                      v={weather.persistenceScore.toFixed(2)}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 10-DAY FORECAST TIMELINE */}
        <div className="panel">
          <div className="panel-header">
            <span>10-DAY FORECAST TIMELINE · {portName} PORT</span>
          </div>
          <div className="p-2 grid grid-cols-10 gap-1.5">
            {forecastDays.map((d, i) => {
              const tone =
                d.severity === "SEVERE"
                  ? "red"
                  : d.severity === "HIGH"
                    ? "amber"
                    : d.severity === "MOD"
                      ? "cyan"
                      : "mint";
              const bg =
                tone === "red"
                  ? "var(--color-red)"
                  : tone === "amber"
                    ? "var(--color-amber)"
                    : tone === "cyan"
                      ? "var(--color-cyan)"
                      : "var(--color-mint)";
              return (
                <div
                  key={i}
                  className="panel p-2 flex flex-col gap-1"
                  style={{ animation: `fade-in .5s ease-out ${i * 60}ms both` }}
                >
                  <div className="flex justify-between items-center text-[9px]">
                    <span className="text-[var(--color-muted-foreground)]">
                      DAY {d.day} · {d.dateLabel}
                    </span>
                    <span
                      className="px-1 border"
                      style={{ borderColor: bg, color: bg }}
                    >
                      {d.severity}
                    </span>
                  </div>
                  <div className="text-[16px] tabular-nums text-[var(--color-foreground)] leading-none">
                    {d.congestionIndex}
                  </div>
                  <div className="text-[9px] text-[var(--color-muted-foreground)]">
                    (±{d.uncertaintyBandHours}h)
                  </div>
                  <div className="flex items-center justify-between text-[9px]">
                    <span className="text-[var(--color-cyan)]">☁</span>
                    {d.weatherProbability > 0 && (
                      <span className="text-[var(--color-red)] tabular-nums">
                        {Math.round(d.weatherProbability * 100)}%
                      </span>
                    )}
                  </div>
                  <div
                    className="h-0.5"
                    style={{ background: bg, opacity: 0.7 }}
                  />
                </div>
              );
            })}
          </div>
        </div>

        {/* BOTTOM: DRIVERS · EXPERT CHAIN · NEWS */}
        <div className="grid grid-cols-3 gap-2">
          <div className="panel">
            <div className="panel-header">
              <span>BACKEND FORECAST SIGNALS · {portName}</span>
              <span>MODEL INPUTS</span>
            </div>
            <div className="p-2 space-y-2 text-[11px]">
              {[
                ["HSMM regime", regime.regimeLabel ?? regime.regime ?? "available", "mint"],
                ["TFT forecast", `${forecastDays.length} horizon points`, "mint"],
                ["Weather risk", `${Math.round((weather.riskScore ?? weather.weatherProbability ?? 0) * 100)}%`, "amber"],
                ["Decision layer", recommendation.severity ?? severityLabel, "amber"],
              ].map(([label, value, tone]) => (
                <div
                  key={label}
                  className="grid grid-cols-[120px_1fr_58px] items-center gap-2"
                >
                  <span className="text-[var(--color-cyan)]">{label}</span>
                  <span className="text-[var(--color-foreground)]">{value}</span>
                  <Chip tone={tone as any}>backend</Chip>
                </div>
              ))}
              <div className="text-[9px] text-[var(--color-muted-foreground)] pt-1 border-t border-[var(--color-line)]/60">
                ⓘ This panel summarizes backend/cache signals used in the cockpit.
                Detailed feature attribution is planned as a future SHAP/attention
                explanation layer.
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <span>PIPELINE MODULES · {portName}</span>
              <span>STATUS</span>
            </div>
            <div className="p-2 space-y-1.5 text-[11px]">
              {[
                ["Feature Builder", "daily port-level feature table", "mint"],
                ["HSMM Regime", "regime probabilities before TFT", "mint"],
                ["TFT Forecast", "q10/q50/q90 congestion forecast", "mint"],
                ["Decision Layer", "rule-based operational recommendation", "amber"],
                ["Satellite/AIS", "planned extension", "amber"],
              ].map(([name, detail, tone]) => (
                <div
                  key={name}
                  className="grid grid-cols-[120px_1fr_60px] gap-2 items-center"
                >
                  <span className="text-[var(--color-foreground)]">{name}</span>
                  <span className="text-[10px] text-[var(--color-muted-foreground)]">
                    {detail}
                  </span>
                  <Chip tone={tone as any}>{tone === "mint" ? "done" : "next"}</Chip>
                </div>
              ))}
              <div className="text-[9px] text-[var(--color-muted-foreground)] pt-1 border-t border-[var(--color-line)]/60">
                ⓘ This is a pipeline status view, not a fabricated expert-confidence
                output.
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <span>NEWS INTELLIGENCE · THIS PORT ({portName})</span>
              <span>Impact · Confidence</span>
            </div>
            <div className="p-2 space-y-2 text-[11px]">
              {newsForPort.length ? (
                newsForPort.slice(0, 4).map((event, i) => (
                  <div
                    key={event.id}
                    className="grid grid-cols-[14px_1fr_54px_44px] gap-2"
                  >
                    <span className="text-[var(--color-cyan)] tabular-nums">
                      {i + 1}
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-[var(--color-foreground)] font-medium">
                          {event.tag}
                        </span>
                        <Chip
                          tone={
                            event.severity === "severe"
                              ? "red"
                              : event.severity === "normal"
                                ? "mint"
                                : "amber"
                          }
                        >
                          {event.severity}
                        </Chip>
                      </div>
                      <div className="text-[10px] text-[var(--color-foreground)]">
                        {event.text}
                      </div>
                      <div className="text-[9px] text-[var(--color-muted-foreground)]">
                        {event.source} · {event.timestamp}Z
                      </div>
                    </div>
                    <span className="text-right text-[10px] text-[var(--color-foreground)] self-start">
                      {event.sentiment < -0.2 ? "High" : "Medium"}
                    </span>
                    <span className="text-right tabular-nums text-[10px] text-[var(--color-cyan)] self-start">
                      {event.confidence.toFixed(2)}
                    </span>
                  </div>
                ))
              ) : (
                <div className="text-[10px] text-[var(--color-muted-foreground)] leading-relaxed">
                  No backend news events are currently mapped to this port.
                  The News/NLP page still shows the full backend historical
                  sentiment cache.
                </div>
              )}
              <div className="text-[9px] text-[var(--color-muted-foreground)] pt-1 border-t border-[var(--color-line)]/60">
                ⓘ This panel uses backend news-cache events only. It does not fall
                back to local mock news.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

type HarborVesselMeta = {
  readonly id: string;
  readonly x: number;
  readonly y: number;
  readonly heading: number;
  readonly color: string;
  readonly label: string;
  readonly status: string;
};

function HarborVessel({
  vessel,
  berth,
  anchored,
  underway,
  service,
}: {
  vessel: HarborVesselMeta;
  berth?: boolean;
  anchored?: boolean;
  underway?: boolean;
  service?: boolean;
}) {
  const scale = service ? 0.74 : berth ? 0.92 : 0.82;
  const hull =
    vessel.label === "TUG" || vessel.label === "SRV"
      ? "M 0 -7 C 4 -4 5 3 2 7 L 0 9 L -2 7 C -5 3 -4 -4 0 -7 Z"
      : "M 0 -10 C 6 -6 7 5 3 10 L 0 12 L -3 10 C -7 5 -6 -6 0 -10 Z";

  return (
    <g
      transform={`translate(${vessel.x} ${vessel.y}) rotate(${vessel.heading}) scale(${scale})`}
      style={{ animation: anchored || service ? "vessel-drift 5.8s ease-in-out infinite" : undefined }}
    >
      <title>
        {vessel.id} · {vessel.label} · {vessel.status}
      </title>
      {anchored && (
        <circle
          r="16"
          fill="none"
          stroke={vessel.color}
          strokeWidth="0.45"
          strokeDasharray="2 5"
          opacity="0.35"
        />
      )}
      {(underway || service) && (
        <line
          x1="0"
          y1="14"
          x2="0"
          y2="28"
          stroke={vessel.color}
          strokeWidth="0.7"
          strokeDasharray="2 4"
          opacity="0.45"
        />
      )}
      {berth && (
        <line
          x1="-11"
          y1="0"
          x2="-21"
          y2="0"
          stroke={vessel.color}
          strokeWidth="0.55"
          strokeDasharray="1 3"
          opacity="0.48"
        />
      )}
      <path
        d={hull}
        fill={vessel.color}
        opacity="0.98"
        stroke="#020711"
        strokeWidth="0.72"
        filter="url(#vShip)"
      />
      <path
        d="M -2.8 -1.8 H 2.8 M -2.4 2 H 2.4 M 0 -6 V 7"
        stroke="#07111d"
        strokeWidth="0.72"
        strokeLinecap="round"
        opacity="0.75"
      />
    </g>
  );
}

function HdrField({
  label,
  value,
  sub,
  chip,
}: {
  label: string;
  value?: string;
  sub?: string;
  chip?: React.ReactNode;
}) {
  return (
    <div className="panel px-3 py-2 flex flex-col justify-center min-h-[68px]">
      <div className="text-[9px] tracking-[0.2em] text-[var(--color-muted-foreground)]">
        {label}
      </div>
      {chip ? (
        <div className="mt-1">{chip}</div>
      ) : (
        value && (
          <div className="text-[12px] text-[var(--color-foreground)] mt-0.5">
            {value}
          </div>
        )
      )}
      {sub && (
        <div className="text-[9px] text-[var(--color-muted-foreground)] mt-0.5">
          {sub}
        </div>
      )}
    </div>
  );
}

function Kpi({
  label,
  big,
  tone,
  sub,
  spark,
  sparkTone,
}: {
  label: string;
  big: string;
  tone: "red" | "amber" | "cyan" | "mint";
  sub?: string;
  spark?: number[];
  sparkTone?: "red" | "amber" | "cyan" | "mint";
}) {
  const c =
    tone === "red"
      ? "text-[var(--color-red)] glow-red"
      : tone === "amber"
        ? "text-[var(--color-amber)] glow-amber"
        : tone === "cyan"
          ? "text-[var(--color-cyan)]"
          : "text-[var(--color-mint)]";
  const accent =
    tone === "red"
      ? "var(--color-red)"
      : tone === "amber"
        ? "var(--color-amber)"
        : tone === "cyan"
          ? "var(--color-cyan)"
          : "var(--color-mint)";
  return (
    <div className="panel relative px-3 py-2.5 flex flex-col gap-1.5 overflow-hidden">
      <span
        className="absolute left-0 top-0 bottom-0 w-[2px]"
        style={{
          background: `linear-gradient(180deg, ${accent}, transparent)`,
          opacity: 0.8,
        }}
      />
      <div className="label-xs">{label}</div>
      <div
        className={`text-[22px] leading-none tabular-nums font-semibold ${c}`}
      >
        {big}
      </div>
      {sub && (
        <div className="text-[9px] text-[var(--color-muted-foreground)]">
          {sub}
        </div>
      )}
      {spark && (
        <div className="-mx-1">
          <Sparkline data={spark} tone={sparkTone || "cyan"} height={20} />
        </div>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-[var(--color-line)]/50 pb-1">
      <span className="text-[var(--color-muted-foreground)]">{k}</span>
      <span className="flex items-center gap-1">{v}</span>
    </div>
  );
}

function WxCell({
  l,
  v,
  sub,
  tone,
}: {
  l: string;
  v: string;
  sub?: string;
  tone?: "mint" | "amber" | "red" | "cyan";
}) {
  const c =
    tone === "mint"
      ? "text-[var(--color-mint)]"
      : tone === "amber"
        ? "text-[var(--color-amber)]"
        : tone === "red"
          ? "text-[var(--color-red)]"
          : "text-[var(--color-foreground)]";
  return (
    <div>
      <div className="text-[9px] tracking-widest text-[var(--color-muted-foreground)]">
        {l}
      </div>
      <div className={`text-[14px] tabular-nums ${c}`}>{v}</div>
      {sub && (
        <div className="text-[9px] text-[var(--color-muted-foreground)]">
          {sub}
        </div>
      )}
    </div>
  );
}

function WxOut({
  k,
  v,
  tone,
}: {
  k: string;
  v: string;
  tone?: "mint" | "red";
}) {
  const c =
    tone === "mint"
      ? "text-[var(--color-mint)]"
      : tone === "red"
        ? "text-[var(--color-red)]"
        : "text-[var(--color-foreground)]";
  return (
    <div>
      <div className="text-[9px] text-[var(--color-muted-foreground)]">{k}</div>
      <div className={`text-[11px] tabular-nums ${c}`}>{v}</div>
    </div>
  );
}

function LegendPill({ c, t }: { c: string; t: string }) {
  return (
    <span className="flex items-center gap-1 text-[var(--color-muted-foreground)]">
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: c, boxShadow: `0 0 4px ${c}` }}
      />
      {t}
    </span>
  );
}
