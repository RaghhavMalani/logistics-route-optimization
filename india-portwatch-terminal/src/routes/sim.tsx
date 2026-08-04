import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Chip, Sparkline } from "@/components/terminal/ui";
import { cn } from "@/lib/utils";
import { listPortOperationalSnapshots } from "@/services/portService";
import { fetchScenarioDefinitions, runScenario } from "@/services/scenarios";
import { fetchNewsBundle } from "@/services/news";
import type { OperationalRiskLevel } from "@/types/portwatch";

export const Route = createFileRoute("/sim")({
  validateSearch: (search: Record<string, unknown>) => ({
    scenario: typeof search.scenario === "string" ? search.scenario : "STORM_W",
    intensity:
      typeof search.intensity === "number"
        ? search.intensity
        : Number(search.intensity ?? 1.5),
  }),
  component: DecisionRoom,
});

const EXPERTS = [
  [
    "Weather Expert",
    "Storm cell over Arabian Sea coast. High waves & strong winds.",
    0.82,
    "Wx Impact Index",
    "0.71",
    "red",
  ],
  [
    "News / NLP Expert",
    "Shipping advisories & port alerts signal operational stress.",
    0.74,
    "Event Risk",
    "0.68",
    "amber",
  ],
  [
    "Port Ops Expert",
    "Berth occupancy high. Yard utilisation at 92%.",
    0.81,
    "Ops Impact",
    "0.73",
    "amber",
  ],
  [
    "Demand Expert",
    "Festival backed demand surge anticipated (+15%).",
    0.76,
    "Demand Index",
    "0.66",
    "cyan",
  ],
  [
    "HSMM Regime",
    "Detected regime: SEVERE. Congestion Risk.",
    0.83,
    "Regime Prob.",
    "0.83",
    "red",
  ],
  [
    "TFT Forecast",
    "10-day congestion forecast with probabilistic bands.",
    0.77,
    "P90 Cong. Index",
    "0.91",
    "red",
  ],
] as const;

const STAGES = [
  ["DATA", "Multimodal Fusion", "cyan"],
  ["EXPERTS", "Domain Reasoning", "amber"],
  ["HSMM REGIME", "State Detection", "amber"],
  ["TFT FORECAST", "Probabilistic", "red"],
  ["DECISION", "Optimization", "mint"],
  ["ANALYTICS", "Insights & What to do", "cyan"],
] as const;

function riskTone(
  risk: OperationalRiskLevel,
): "red" | "amber" | "cyan" | "mint" {
  if (risk === "severe") return "red";
  if (risk === "high") return "amber";
  if (risk === "medium") return "cyan";
  return "mint";
}

function riskLabel(risk: OperationalRiskLevel): string {
  if (risk === "severe") return "SEVERE";
  if (risk === "high") return "HIGH";
  if (risk === "medium") return "MEDIUM";
  return "LOW";
}

function signedPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(0)}%`;
}

function signedHours(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}h`;
}

function DecisionRoom() {
  const newsBundleQuery = useQuery({
    queryKey: ["decision-room-news"],
    queryFn: fetchNewsBundle,
    staleTime: 30_000,
  });

  const backendNewsEvents = newsBundleQuery.data?.events ?? [];
  const selectedBackendNewsEvent = backendNewsEvents[0];

  const search = Route.useSearch();
  const [sel, setSel] = useState(search.scenario);
  const [intensity, setIntensity] = useState(
    Number.isFinite(search.intensity) ? search.intensity : 1.5,
  );
  const [runId, setRunId] = useState(0);
  const [askQuestion, setAskQuestion] = useState("");
  const [activeQuestion, setActiveQuestion] = useState(
    "Why is this port marked at this risk level?",
  );

  const scenariosQuery = useQuery({
    queryKey: ["scenario-definitions"],
    queryFn: fetchScenarioDefinitions,
    staleTime: 60_000,
  });

  const ports = listPortOperationalSnapshots();
  const defaultPortCode =
    ports.find((port) => port.portCode === "INNSA")?.portCode ??
    ports[0]?.portCode ??
    "INMAA";
  const [selectedPortCode, setSelectedPortCode] = useState(defaultPortCode);

  const scenarioResultQuery = useQuery({
    queryKey: ["scenario-result", sel, intensity, runId],
    queryFn: () => runScenario(sel, intensity, 1247 + runId),
    enabled: Boolean(sel),
    staleTime: 5_000,
  });

  useEffect(() => {
    setSel(search.scenario);
    setIntensity(Number.isFinite(search.intensity) ? search.intensity : 1.5);
  }, [search.scenario, search.intensity]);

  if (scenariosQuery.isLoading || scenarioResultQuery.isLoading) {
    return (
      <div className="h-full grid place-items-center text-[var(--color-cyan)] text-[12px] tracking-[0.2em]">
        LOADING LIVE SCENARIO SIMULATOR...
      </div>
    );
  }

  if (
    scenariosQuery.isError ||
    scenarioResultQuery.isError ||
    !scenariosQuery.data ||
    !scenarioResultQuery.data
  ) {
    return (
      <div className="h-full grid place-items-center text-[var(--color-red)] text-[12px] tracking-[0.2em]">
        SCENARIO API UNAVAILABLE
      </div>
    );
  }

  const scenarios = scenariosQuery.data;
  const result = scenarioResultQuery.data;
  const impactByPort = new Map(
    result.affectedPorts.map((impact) => [impact.portCode, impact]),
  );

  const selectedPort =
    ports.find((port) => port.portCode === selectedPortCode) ?? ports[0];
  const selectedImpact = impactByPort.get(selectedPortCode);

  const selectedRisk = (selectedImpact?.riskLevel ?? "low") as OperationalRiskLevel;
  const selectedRiskLabel = riskLabel(selectedRisk);
  const selectedRiskTone = riskTone(selectedRisk);

  const focusCongestionDelta = selectedImpact?.congestionDelta ?? 0;
  const focusDelayDeltaHours = selectedImpact?.delayDeltaHours ?? 0;
  const focusThroughputDelta = selectedImpact?.throughputDelta ?? 0;
  const focusImpactScore = selectedImpact?.impactScore ?? 0;
  const focusFreightDelta =
    selectedImpact && result.congestionDelta
      ? result.freightDelta * (focusCongestionDelta / result.congestionDelta)
      : 0;

  const topAffectedPorts = [...result.affectedPorts]
    .sort((a, b) => b.impactScore - a.impactScore)
    .slice(0, 5);

  const highestDelayPorts = [...result.affectedPorts]
    .sort((a, b) => b.delayDeltaHours - a.delayDeltaHours)
    .slice(0, 3);

  const backendNewsCount = backendNewsEvents.length;
  const selectedPortName = selectedPort?.name ?? selectedPortCode;

  const askSuggestions = [
    `Why is ${selectedPortName} marked ${selectedRiskLabel.toLowerCase()} risk?`,
    "Which ports are most exposed in this scenario?",
    "Which routes have highest delay risk?",
    "What should operators do next?",
    "What backend signals support this decision?",
  ];

  const submitAskQuestion = (question?: string) => {
    const finalQuestion = (question ?? askQuestion).trim() || askSuggestions[0];
    setActiveQuestion(finalQuestion);
    setAskQuestion("");
  };

  const q = activeQuestion.toLowerCase();

  const answerTitle = q.includes("route")
    ? "Route delay risk is driven by the scenario-level route impact output."
    : q.includes("exposed") || q.includes("ports")
      ? "The most exposed ports are ranked from the backend scenario impact output."
      : q.includes("operator") || q.includes("what should") || q.includes("next")
        ? "Recommended actions come from the backend scenario decision layer."
        : q.includes("signal") || q.includes("backend")
          ? "This answer is grounded in backend scenario, news, and model-cache signals."
          : `${selectedPortName} is marked ${selectedRiskLabel} based on its selected-port scenario impact.`;

  const answerBullets = q.includes("route")
    ? [
        `West/east route impacts are scenario-wide and remain tied to the selected disruption.`,
        `Selected focus port delay delta: ${signedHours(focusDelayDeltaHours)}.`,
        `Freight impact proxy for this focus: ${signedPercent(focusFreightDelta)}.`,
      ]
    : q.includes("exposed") || q.includes("ports")
      ? topAffectedPorts.map(
          (portImpact) =>
            `${portImpact.portName ?? portImpact.portCode}: ${riskLabel(
              portImpact.riskLevel,
            )} risk, impact score ${portImpact.impactScore.toFixed(2)}, delay ${signedHours(
              portImpact.delayDeltaHours,
            )}.`,
        )
      : q.includes("operator") || q.includes("what should") || q.includes("next")
        ? result.recommendation.actions.slice(0, 4)
        : q.includes("signal") || q.includes("backend")
          ? [
              `Scenario API output: ${result.scenarioName ?? sel} at ${intensity.toFixed(1)}x intensity.`,
              `Selected port impact: congestion ${signedPercent(
                focusCongestionDelta,
              )}, delay ${signedHours(focusDelayDeltaHours)}, throughput ${signedPercent(
                focusThroughputDelta,
              )}.`,
              `Backend news cache events available: ${backendNewsCount}.`,
              `Pipeline shown: data fusion → HSMM regime → TFT forecast → decision layer.`,
            ]
          : [
              `Risk level: ${selectedRiskLabel}.`,
              `Congestion delta for selected port: ${signedPercent(focusCongestionDelta)}.`,
              `Delay delta for selected port: ${signedHours(focusDelayDeltaHours)}.`,
              `Throughput delta for selected port: ${signedPercent(focusThroughputDelta)}.`,
            ];

  const answerConfidence = selectedImpact
    ? Math.min(0.95, 0.65 + Math.abs(focusImpactScore) / 100)
    : 0.62;

  return (
    <div className="h-full overflow-auto overflow-x-hidden">
      <div className="min-h-full p-2 space-y-2">
        {/* Focus header */}
        <div className="panel px-3 py-1.5 flex items-center gap-3 text-[10px] flex-wrap">
          <span className="flex items-center gap-2 text-[10px] tracking-widest text-[var(--color-muted-foreground)]">
            What-if ·{" "}
            <span className="text-[var(--color-foreground)]">Why</span> · What
            to do
          </span>
          <span className="text-[var(--color-muted-foreground)]">
            Current focus:
          </span>
          <span className="text-[var(--color-foreground)]">
            {selectedPort?.name ?? selectedPortCode}
          </span>
          <span className="text-[var(--color-muted-foreground)]">
            — {selectedRiskLabel} scenario focus
          </span>
          <Chip tone={selectedRiskTone}>{selectedRiskLabel}</Chip>
          <div className="ml-auto flex items-center gap-1.5 text-[9px] flex-wrap justify-end">
            <span className="text-[var(--color-muted-foreground)]">
              Select Port
            </span>
            <select
              value={selectedPortCode}
              onChange={(event) => setSelectedPortCode(event.target.value)}
              className="border border-[var(--color-line-strong)] bg-[var(--color-panel)] px-2 py-1 min-w-[180px] text-[var(--color-foreground)] outline-none focus:border-[var(--color-cyan)]"
            >
              {ports.map((portOption) => (
                <option key={portOption.portCode} value={portOption.portCode}>
                  {portOption.name ?? portOption.portCode}
                </option>
              ))}
            </select>
            <button className="border border-[var(--color-line-strong)] px-2 py-1 text-[var(--color-cyan)]">
              ↗ Share Scenario
            </button>
            <button className="border border-[var(--color-line-strong)] px-2 py-1 text-[var(--color-cyan)]">
              ↥ Export
            </button>
            <button className="border border-[var(--color-line-strong)] px-2 py-1 text-[var(--color-muted-foreground)]">
              ···
            </button>
          </div>
        </div>

        {/* THREE-COLUMN */}
        <div className="grid grid-cols-[0.9fr_1.42fr_1fr] gap-2 items-start">
          {/* 1 · SCENARIO SIMULATOR */}
          <div className="panel min-w-0 overflow-hidden">
            <div className="panel-header">
              <span className="flex items-center gap-2">
                <NumBadge n={1} /> SCENARIO SIMULATOR
              </span>
            </div>
            <div className="px-2 py-1.5 text-[9px] text-[var(--color-muted-foreground)]">
              Explore what-if situations and their impact
            </div>
            <div className="px-2 pb-2 grid grid-cols-2 gap-1.5">
              {scenarios.map((sc) => (
                <button
                  key={sc.key}
                  onClick={() => setSel(sc.key)}
                  className={cn(
                    "panel text-left p-1.5 transition-colors",
                    sel === sc.key
                      ? "border-[var(--color-cyan)] shadow-[0_0_0_1px_var(--color-cyan)_inset,0_0_18px_-6px_var(--color-cyan)]"
                      : "hover:border-[var(--color-line-strong)]",
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <ScIcon k={sc.icon} />
                    <span className="text-[10px] text-[var(--color-foreground)] font-medium leading-tight">
                      {sc.name}
                    </span>
                  </div>
                  <div className="text-[9px] text-[var(--color-muted-foreground)] leading-snug">
                    {sc.desc}
                  </div>
                </button>
              ))}
            </div>
            <div className="px-2 pb-1.5">
              <div className="flex items-center justify-between text-[10px]">
                <span className="label-xs">SCENARIO INTENSITY</span>
                <span className="text-[var(--color-cyan)] tabular-nums">
                  {intensity.toFixed(1)}x
                </span>
              </div>
              <input
                type="range"
                min={0.5}
                max={2}
                step={0.1}
                value={intensity}
                onChange={(e) => setIntensity(parseFloat(e.target.value))}
                className="w-full mt-2 accent-[var(--color-cyan)]"
              />
              <div className="grid grid-cols-4 text-[9px] tabular-nums text-[var(--color-muted-foreground)] mt-1">
                <span>
                  0.5x
                  <br />
                  <span className="opacity-70">Low</span>
                </span>
                <span>
                  1.0x
                  <br />
                  <span className="opacity-70">Base</span>
                </span>
                <span className="text-[var(--color-cyan)]">
                  1.5x
                  <br />
                  High
                </span>
                <span className="text-right">
                  2.0x
                  <br />
                  <span className="opacity-70">Extreme</span>
                </span>
              </div>
            </div>
            <div className="p-2">
              <button
                onClick={() => setRunId((id) => id + 1)}
                className="w-full py-3 bg-[var(--color-red)] text-white tracking-[0.24em] text-[13px] font-semibold rounded-sm shadow-[0_0_20px_-4px_var(--color-red)] hover:brightness-110 active:brightness-95 transition-all"
              >
                ▶ RUN SIMULATION
              </button>
              <div className="text-[9px] text-[var(--color-muted-foreground)] text-center mt-2">
                AI will propagate impact across ports, routes & operations
              </div>
            </div>
          </div>

          {/* 2 · DECISION IMPACT VIEW */}
          <div className="panel min-w-0 overflow-hidden">
            <div className="panel-header">
              <span className="flex items-center gap-2">
                <NumBadge n={2} /> DECISION IMPACT VIEW
              </span>
              <span className="flex items-center gap-2 text-[10px]">
                <span className="text-[var(--color-mint)] flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-mint)] animate-blink" />
                  RUN #{String(1247 + runId).padStart(4, "0")}
                </span>
                <span className="text-[var(--color-muted-foreground)]">
                  View:
                </span>
                <span className="border border-[var(--color-line-strong)] px-2 py-0.5">
                  Impact Summary ▾
                </span>
              </span>
            </div>
            <div className="p-2 text-[10px] text-[var(--color-muted-foreground)]">
              Before vs After impact for selected focus port:{" "}
              <span className="text-[var(--color-cyan)]">
                {selectedPort?.name ?? selectedPortCode}
              </span>
              . Scenario-wide route and chokepoint impacts remain unchanged.
              {!selectedImpact && (
                <span className="text-[var(--color-amber)]">
                  {" "}This port is not directly affected in the current scenario output.
                </span>
              )}
            </div>
            <div className="px-2 grid grid-cols-5 gap-1.5" key={runId}>
              <ImpactCard
                label="Congestion Increase"
                avg={signedPercent(focusCongestionDelta)}
                tone={selectedRiskTone === "red" ? "red" : selectedRiskTone === "mint" ? "mint" : "amber"}
                data={[0, 8, 16, 24, focusCongestionDelta]}
                sub={`Risk ${selectedRiskLabel}`}
                delay={0}
              />
              <ImpactCard
                label="Delay Increase"
                avg={signedHours(focusDelayDeltaHours)}
                tone="red"
                data={[0, 2, 4, 6, focusDelayDeltaHours]}
                sub="fleet ETA delta"
                delay={80}
              />
              <ImpactCard
                label="Throughput Drop"
                avg={signedPercent(focusThroughputDelta)}
                tone="mint"
                data={[100, 98, 96, 94, 100 + focusThroughputDelta]}
                sub="TEU/day proxy"
                invert
                delay={160}
              />
              <ImpactCard
                label="Freight Impact"
                avg={signedPercent(focusFreightDelta)}
                tone="red"
                data={[100, 101, 102, 103, 100 + focusFreightDelta]}
                sub="per TEU proxy"
                delay={240}
              />
              <div
                className="panel p-1.5 flex flex-col gap-1 text-[9px] animate-impact overflow-hidden"
                style={{ animationDelay: "320ms" }}
              >
                <div className="label-xs">Recommended Operational Response</div>
                <ul className="text-[10px] leading-snug space-y-0.5 text-[var(--color-foreground)]">
                  {result.recommendation.actions.map((action, index) => (
                    <li
                      key={action}
                      className={
                        index < 2
                          ? "text-[var(--color-mint)]"
                          : "text-[var(--color-amber)]"
                      }
                    >
                      ● {action}
                    </li>
                  ))}
                </ul>
                <button className="mt-1 text-[10px] text-[var(--color-cyan)] border border-[var(--color-cyan)]/40 px-2 py-1">
                  View Full Playbook →
                </button>
              </div>
            </div>

            {/* Affected ports + map + chokepoints */}
            <div className="p-2 grid grid-cols-[0.9fr_1fr_0.78fr] gap-1.5">
              <div className="panel">
                <div className="panel-header">
                  <span>AFFECTED PORTS</span>
                  <span>(Top 8)</span>
                </div>
                <div className="grid grid-cols-[16px_1fr_36px_54px] px-2 py-1 border-b border-[var(--color-line)]/60 text-[9px] tracking-widest text-[var(--color-muted-foreground)]">
                  <span></span>
                  <span>PORT</span>
                  <span className="text-right">IMPACT SCORE</span>
                  <span></span>
                </div>
                <div className="p-1 text-[10px]">
                  {result.affectedPorts.map((impact, index) => {
                    const port = ports.find(
                      (item) => item.code === impact.portCode,
                    );
                    return (
                      <div
                        key={impact.portCode}
                        className="grid grid-cols-[16px_1fr_36px_54px] items-center px-1 py-1 gap-1"
                      >
                        <span className="text-[var(--color-muted-foreground)] tabular-nums">
                          {index + 1}.
                        </span>
                        <span className="text-[var(--color-foreground)] truncate">
                          {port?.name ?? impact.portCode}
                        </span>
                        <span className="text-right tabular-nums text-[var(--color-foreground)]">
                          {impact.impactScore}
                        </span>
                        <Chip tone={riskTone(impact.riskLevel)}>
                          {riskLabel(impact.riskLevel)}
                        </Chip>
                      </div>
                    );
                  })}
                  <div className="text-[10px] text-[var(--color-cyan)] px-1 py-1">
                    View all 121 ports →
                  </div>
                </div>
                <div className="p-2 border-t border-[var(--color-line)]">
                  <div className="label-xs mb-1">Risk Level</div>
                  <div className="flex items-center gap-2 text-[9px] flex-wrap">
                    <LegendDot c="#ff5566" t="Severe" />
                    <LegendDot c="#ffb347" t="High" />
                    <LegendDot c="#c58cff" t="Medium" />
                    <LegendDot c="#7dd3fc" t="Low" />
                    <LegendDot c="#7ef0b4" t="Normal" />
                    <span className="w-full flex items-center gap-2 mt-1">
                      <span className="w-4 border-t border-[var(--color-cyan)]" />{" "}
                      Sea Route Impact{" "}
                      <span className="ml-2 text-[var(--color-red)]">⚠</span>{" "}
                      Chokepoint Impact
                    </span>
                  </div>
                </div>
              </div>

              {/* Mini India map */}
              <div className="panel relative overflow-hidden min-h-[210px]">
                <div
                  className="absolute inset-0"
                  style={{
                    background:
                      "radial-gradient(ellipse at 40% 45%, oklch(0.24 0.05 220 / 0.5) 0%, oklch(0.14 0.02 240) 70%)",
                  }}
                />
                <svg
                  viewBox="0 0 240 320"
                  className="absolute inset-0 w-full h-full"
                >
                  <defs>
                    <linearGradient id="landG" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0" stopColor="oklch(0.26 0.04 220)" />
                      <stop offset="1" stopColor="oklch(0.18 0.03 240)" />
                    </linearGradient>
                    <filter id="miniShadow">
                      <feDropShadow
                        dx="0"
                        dy="1"
                        stdDeviation="1"
                        floodColor="#000"
                        floodOpacity="0.6"
                      />
                    </filter>
                  </defs>
                  <path
                    d="M 90 30 Q 120 20 150 40 L 175 90 L 195 150 L 175 210 L 140 275 L 100 300 L 70 260 L 50 210 L 45 160 L 55 100 Z"
                    fill="url(#landG)"
                    stroke="oklch(0.55 0.09 195 / 0.7)"
                    strokeWidth="1"
                  />
                  {/* subtle lat/long grid */}
                  {[80, 140, 200, 260].map((y) => (
                    <line
                      key={y}
                      x1="0"
                      y1={y}
                      x2="240"
                      y2={y}
                      stroke="oklch(0.35 0.05 200 / 0.15)"
                      strokeWidth="0.4"
                      strokeDasharray="2 4"
                    />
                  ))}
                  {[60, 120, 180].map((x) => (
                    <line
                      key={x}
                      x1={x}
                      y1="0"
                      x2={x}
                      y2="320"
                      stroke="oklch(0.35 0.05 200 / 0.15)"
                      strokeWidth="0.4"
                      strokeDasharray="2 4"
                    />
                  ))}
                  {/* Routes (behind ports) */}
                  <path
                    d="M 75 155 Q 30 100 -10 40"
                    stroke="#7dd3fc"
                    strokeWidth="1"
                    fill="none"
                    strokeDasharray="3 3"
                    style={{ animation: "dash-flow 4s linear infinite" }}
                  />
                  <path
                    d="M 155 220 Q 220 260 240 300"
                    stroke="#ff5566"
                    strokeWidth="1.4"
                    fill="none"
                    strokeDasharray="4 4"
                    style={{ animation: "dash-flow 3s linear infinite" }}
                  />
                  <path
                    d="M 175 155 Q 230 130 240 100"
                    stroke="#ffb347"
                    strokeWidth="1"
                    fill="none"
                    strokeDasharray="3 3"
                    style={{ animation: "dash-flow 4s linear infinite" }}
                  />
                  {/* ports */}
                  {[
                    ["INIXY", "Kandla", 60, 90],
                    ["INMUN", "Mundra", 55, 100],
                    ["INNSA", "JNPT", 75, 155],
                    ["INMRM", "Marmagao", 90, 190],
                    ["ININM", "Mangaluru", 95, 220],
                    ["INCOK", "Kochi", 110, 255],
                    ["INMAA", "Chennai", 155, 220],
                    ["INVTZ", "Visakhapatnam", 175, 155],
                    ["INPRT", "Paradip", 175, 115],
                    ["INHAL", "Kolkata", 190, 70],
                  ].map(([code, n, x, y]) => {
                    const impact = impactByPort.get(code as string);
                    const tone = impact ? riskTone(impact.riskLevel) : "cyan";
                    const c =
                      tone === "red"
                        ? "#ff5566"
                        : tone === "amber"
                          ? "#ffb347"
                          : tone === "mint"
                            ? "#7ef0b4"
                            : "#7dd3fc";
                    return (
                      <g key={n as string}>
                        <circle
                          cx={x as number}
                          cy={y as number}
                          r="12"
                          fill={`${c}18`}
                          className="animate-halo"
                          style={{
                            transformBox: "fill-box",
                            transformOrigin: "center",
                          }}
                        />
                        <circle
                          cx={x as number}
                          cy={y as number}
                          r="7"
                          fill="none"
                          stroke={c}
                          strokeWidth="0.8"
                          opacity="0.7"
                        />
                        <circle
                          cx={x as number}
                          cy={y as number}
                          r="2.4"
                          fill={c}
                          filter="url(#miniShadow)"
                        />
                        <text
                          x={(x as number) + 8}
                          y={(y as number) + 3}
                          fontSize="7.5"
                          fill="oklch(0.95 0 0)"
                          className="label-halo"
                          fontWeight="600"
                        >
                          {n}
                        </text>
                      </g>
                    );
                  })}
                  <g>
                    <rect
                      x="4"
                      y="10"
                      width="70"
                      height="14"
                      fill="oklch(0.10 0.02 240 / 0.75)"
                      stroke="#ffb347"
                      strokeWidth="0.5"
                    />
                    <text
                      x="10"
                      y="20"
                      fontSize="7"
                      fill="#ffb347"
                      letterSpacing="1.4"
                      fontWeight="600"
                    >
                      ◆ HORMUZ
                    </text>
                  </g>
                  <g>
                    <rect
                      x="166"
                      y="282"
                      width="70"
                      height="14"
                      fill="oklch(0.10 0.02 240 / 0.75)"
                      stroke="#ff5566"
                      strokeWidth="0.5"
                    />
                    <text
                      x="172"
                      y="292"
                      fontSize="7"
                      fill="#ff5566"
                      letterSpacing="1.4"
                      fontWeight="600"
                    >
                      ◆ MALACCA
                    </text>
                  </g>
                </svg>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <span>AFFECTED CHOKEPOINTS</span>
                  <span>RISK</span>
                </div>
                <div className="p-2 text-[10px] space-y-1">
                  {result.chokepointImpacts.map((impact) => (
                    <div
                      key={impact.name}
                      className="flex items-center justify-between border-b border-[var(--color-line)]/50 py-1"
                    >
                      <span className="text-[var(--color-foreground)]">
                        {impact.name}
                      </span>
                      <Chip tone={riskTone(impact.riskLevel)}>
                        {riskLabel(impact.riskLevel)}
                      </Chip>
                    </div>
                  ))}
                </div>
                <div className="panel-header border-t border-[var(--color-line)]">
                  <span>SEA ROUTE IMPACT</span>
                  <span>DELAY (HRS)</span>
                </div>
                <div className="p-2 text-[10px] space-y-1">
                  {result.routeImpacts.map((impact) => (
                    <div
                      key={impact.name}
                      className="flex items-center justify-between border-b border-[var(--color-line)]/50 py-1"
                    >
                      <span className="text-[var(--color-foreground)]">
                        {impact.name}
                      </span>
                      <span className="text-[var(--color-red)] tabular-nums">
                        {signedHours(impact.delayDeltaHours)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* 3 · MODEL INTELLIGENCE LAYER */}
          <div className="panel min-w-0 overflow-hidden">
            <div className="panel-header">
              <span className="flex items-center gap-2">
                <NumBadge n={3} /> MODEL INTELLIGENCE LAYER
              </span>
            </div>
            <div className="px-2 py-1.5 text-[9px] text-[var(--color-muted-foreground)]">
              End-to-end AI pipeline powering this decision
            </div>
            <div className="px-2 pb-2 grid grid-cols-3 gap-1">
              {STAGES.map(([k, s, t]) => (
                <div
                  key={k as string}
                  className={
                    "border px-2 py-1.5 flex flex-col " +
                    (t === "red"
                      ? "border-[var(--color-red)]/50 bg-[var(--color-red)]/5"
                      : t === "amber"
                        ? "border-[var(--color-amber)]/50 bg-[var(--color-amber)]/5"
                        : t === "mint"
                          ? "border-[var(--color-mint)]/50 bg-[var(--color-mint)]/5"
                          : "border-[var(--color-cyan)]/50 bg-[var(--color-cyan)]/5")
                  }
                >
                  <span
                    className={
                      "text-[9px] tracking-widest font-semibold " +
                      (t === "red"
                        ? "text-[var(--color-red)]"
                        : t === "amber"
                          ? "text-[var(--color-amber)]"
                          : t === "mint"
                            ? "text-[var(--color-mint)]"
                            : "text-[var(--color-cyan)]")
                    }
                  >
                    {k}
                  </span>
                  <span className="text-[9px] text-[var(--color-muted-foreground)]">
                    {s}
                  </span>
                </div>
              ))}
            </div>

            <div className="panel-header border-t border-[var(--color-line)]">
              <span>EXPERT CHAIN — JNPT (NHAVA SHEVA)</span>
              <span>
                Confidence (Overall){" "}
                <span className="text-[var(--color-mint)] tabular-nums">
                  0.78
                </span>
              </span>
            </div>
            <div className="p-2 grid grid-cols-2 gap-1.5">
              {EXPERTS.map(([name, note, conf, ki, kv, tone]) => (
                <div
                  key={name as string}
                  className="border border-[var(--color-line)] p-1.5 flex flex-col gap-1 min-h-[112px] overflow-hidden"
                >
                  <div className="w-7 h-7 border border-[var(--color-line-strong)] flex items-center justify-center text-[var(--color-cyan)] text-[12px] self-center">
                    ◉
                  </div>
                  <div className="text-[9px] text-[var(--color-foreground)] font-medium text-center leading-tight">
                    {name}
                  </div>
                  <div className="text-[8px] text-[var(--color-muted-foreground)] leading-snug text-center flex-1">
                    {note}
                  </div>
                  <div className="text-[9px] text-[var(--color-muted-foreground)] tabular-nums">
                    Conf.{" "}
                    <span className="text-[var(--color-foreground)]">
                      {(conf as number).toFixed(2)}
                    </span>
                  </div>
                  <div className="text-[9px] text-[var(--color-muted-foreground)]">
                    {ki}
                  </div>
                  <div
                    className={
                      "text-[13px] tabular-nums " +
                      (tone === "red"
                        ? "text-[var(--color-red)]"
                        : tone === "amber"
                          ? "text-[var(--color-amber)]"
                          : "text-[var(--color-cyan)]")
                    }
                  >
                    {kv}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* BOTTOM ROW: NEWS · ASK · AI RESPONSE */}
        <div className="grid grid-cols-[1.35fr_0.9fr_1.15fr] gap-2">
          <div className="panel">
            <div className="panel-header">
              <span>BACKEND NEWS / NLP CACHE</span>
              <span>Historical sentiment events & TFT-linked alerts</span>
            </div>
            <div className="grid grid-cols-2 gap-2 p-2">
              <div className="space-y-2">
                {newsBundleQuery.isLoading ? (
                  <div className="text-[10px] text-[var(--color-muted-foreground)]">
                    Loading backend news cache...
                  </div>
                ) : backendNewsEvents.length ? (
                  backendNewsEvents.slice(0, 5).map((event) => {
                    const sentiment = Number(event.sentiment ?? 0);
                    const tone =
                      event.severity === "severe"
                        ? "red"
                        : event.severity === "normal"
                          ? "mint"
                          : "amber";

                    return (
                      <div
                        key={event.id}
                        className="border-l-2 pl-2 py-1"
                        style={{
                          borderColor:
                            tone === "red"
                              ? "var(--color-red)"
                              : tone === "amber"
                                ? "var(--color-amber)"
                                : "var(--color-mint)",
                        }}
                      >
                        <div className="flex items-center gap-2">
                          <Chip tone={tone as any}>
                            {(event.severity ?? "event").toUpperCase()}
                          </Chip>
                          <span className="text-[10px] text-[var(--color-foreground)]">
                            {event.tag}
                          </span>
                          <span className="ml-auto text-[9px] text-[var(--color-muted-foreground)]">
                            {event.timestamp}Z
                          </span>
                        </div>
                        <div className="text-[10px] text-[var(--color-foreground)] leading-snug mt-1">
                          {event.text}
                        </div>
                        <div className="text-[9px] text-[var(--color-muted-foreground)]">
                          {event.source} · sentiment{" "}
                          {sentiment >= 0 ? "+" : ""}
                          {sentiment.toFixed(2)}
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="text-[10px] text-[var(--color-muted-foreground)]">
                    No backend news events available.
                  </div>
                )}
              </div>

              <div className="panel p-2 text-[10px] space-y-1.5">
                <div className="flex justify-between text-[9px] tracking-widest text-[var(--color-muted-foreground)]">
                  <span>SELECTED BACKEND EVENT</span>
                  <span className="text-[var(--color-cyan)]">
                    CACHE SOURCE
                  </span>
                </div>

                {selectedBackendNewsEvent ? (
                  (() => {
                    const sentiment = Number(selectedBackendNewsEvent.sentiment ?? 0);
                    const confidence = Number(selectedBackendNewsEvent.confidence ?? 0);
                    const tone =
                      selectedBackendNewsEvent.severity === "severe"
                        ? "red"
                        : selectedBackendNewsEvent.severity === "normal"
                          ? "mint"
                          : "amber";

                    return (
                      <>
                        <div className="text-[11px] text-[var(--color-foreground)] font-medium">
                          {selectedBackendNewsEvent.text}
                        </div>
                        <div className="grid grid-cols-[86px_1fr] gap-y-1 text-[10px] mt-1">
                          <span className="text-[var(--color-muted-foreground)]">
                            Source
                          </span>
                          <span className="text-[var(--color-foreground)]">
                            {selectedBackendNewsEvent.source}
                          </span>
                          <span className="text-[var(--color-muted-foreground)]">
                            Tag / Entity
                          </span>
                          <span className="text-[var(--color-foreground)]">
                            {selectedBackendNewsEvent.tag} / {selectedBackendNewsEvent.entity}
                          </span>
                          <span className="text-[var(--color-muted-foreground)]">
                            Sentiment
                          </span>
                          <span className="text-[var(--color-foreground)] flex items-center gap-2">
                            <Chip tone={tone as any}>
                              {(selectedBackendNewsEvent.severity ?? "event").toUpperCase()}
                            </Chip>
                            <span className="tabular-nums">
                              {sentiment >= 0 ? "+" : ""}
                              {sentiment.toFixed(2)}
                            </span>
                          </span>
                          <span className="text-[var(--color-muted-foreground)]">
                            Affected Ports
                          </span>
                          <span className="text-[var(--color-foreground)]">
                            {selectedBackendNewsEvent.affectedPorts?.length
                              ? selectedBackendNewsEvent.affectedPorts.join(", ")
                              : "Not mapped"}
                          </span>
                        </div>
                        <div className="pt-1 flex items-center gap-2 text-[9px]">
                          <span className="text-[var(--color-muted-foreground)]">
                            NLP Confidence
                          </span>
                          <div className="flex-1 h-1 bg-[var(--color-panel-2)]">
                            <div
                              className="h-full bg-[var(--color-mint)]"
                              style={{
                                width: `${Math.round(confidence * 100)}%`,
                              }}
                            />
                          </div>
                          <span className="text-[var(--color-mint)] tabular-nums">
                            {confidence.toFixed(2)}
                          </span>
                        </div>
                      </>
                    );
                  })()
                ) : (
                  <div className="text-[var(--color-muted-foreground)]">
                    No backend event selected.
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <span>ASK PORTWATCH</span>
              <span>Ask questions in natural language</span>
            </div>
            <div className="p-3 space-y-2 text-[10px]">
              {askSuggestions.map((q) => (
                <button
                  key={q}
                  onClick={() => submitAskQuestion(q)}
                  className="w-full text-left px-3 py-2 border border-[var(--color-line-strong)] hover:border-[var(--color-cyan)] hover:text-[var(--color-cyan)] text-[var(--color-foreground)]"
                >
                  {q}
                </button>
              ))}
              <div className="mt-2 flex items-center gap-2">
                <input
                  value={askQuestion}
                  onChange={(event) => setAskQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      submitAskQuestion();
                    }
                  }}
                  placeholder="Type your question…"
                  className="flex-1 bg-[var(--color-panel-2)] border border-[var(--color-line-strong)] px-2 py-2 outline-none focus:border-[var(--color-cyan)] text-[11px]"
                />
                <button
                  onClick={() => submitAskQuestion()}
                  className="w-9 h-9 border border-[var(--color-cyan)]/60 text-[var(--color-cyan)] flex items-center justify-center"
                >
                  ▸
                </button>
              </div>
            </div>
          </div>

          <div className="relative border border-[var(--color-cyan)]/40 bg-gradient-to-br from-[oklch(0.20_0.04_220)] via-[oklch(0.16_0.03_240)] to-[oklch(0.14_0.02_240)] shadow-[0_0_0_1px_oklch(0.82_0.18_195/0.10),0_0_24px_-6px_oklch(0.82_0.18_195/0.45)]">
            <span className="absolute left-0 top-0 bottom-0 w-[3px] bg-gradient-to-b from-[var(--color-cyan)] via-[var(--color-mint)] to-transparent" />
            <div className="flex items-center justify-between px-3 py-1.5 border-b border-[var(--color-cyan)]/25 bg-gradient-to-r from-[oklch(0.82_0.18_195/0.12)] to-transparent">
              <span className="text-[10px] tracking-[0.2em] text-[var(--color-cyan)] font-semibold flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-cyan)] animate-blink" />
                SCENARIO RESPONSE
              </span>
              <span className="text-[9px] tracking-widest text-[var(--color-muted-foreground)]">
                RULE-BASED SYNTHESIS · {answerConfidence.toFixed(2)} CONF
              </span>
            </div>
            <div className="p-3 text-[11px] leading-relaxed text-[var(--color-foreground)] space-y-2">
              <div className="text-[var(--color-muted-foreground)] text-[10px] tracking-wide">
                Q · {activeQuestion}
              </div>

              <div className="text-[12px]">
                {answerTitle}
              </div>

              <ul className="space-y-1 text-[10px] border-l border-[var(--color-cyan)]/30 pl-3">
                {answerBullets.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>

              <div className="text-[10px] text-[var(--color-mint)] border-t border-[var(--color-line)] pt-2">
                ▸ Recommendation: {result.recommendation.actions[0]}
              </div>

              <div className="flex items-center gap-2 pt-1 text-[9px] text-[var(--color-muted-foreground)]">
                <span>
                  Sources: scenario API · selected port impact · backend news cache
                </span>
                <span className="ml-auto flex gap-1">
                  <button className="px-2 py-0.5 border border-[var(--color-line-strong)] hover:border-[var(--color-mint)] hover:text-[var(--color-mint)]">
                    Helpful
                  </button>
                  <button className="px-2 py-0.5 border border-[var(--color-line-strong)] hover:border-[var(--color-red)]">
                    Improve
                  </button>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function NumBadge({ n }: { n: number }) {
  return (
    <span className="w-5 h-5 rounded-full bg-[var(--color-cyan)] text-[oklch(0.10_0.02_240)] text-[11px] font-bold flex items-center justify-center">
      {n}
    </span>
  );
}

function ImpactCard({
  label,
  avg,
  tone,
  data,
  sub,
  invert,
  delay = 0,
}: {
  label: string;
  avg: string;
  tone: "red" | "mint" | "amber" | "cyan";
  data: number[];
  sub: string;
  invert?: boolean;
  delay?: number;
}) {
  const c =
    tone === "red"
      ? "text-[var(--color-red)] glow-red"
      : tone === "mint"
        ? "text-[var(--color-mint)]"
        : tone === "amber"
          ? "text-[var(--color-amber)]"
          : "text-[var(--color-cyan)]";
  const accent =
    tone === "red"
      ? "var(--color-red)"
      : tone === "mint"
        ? "var(--color-mint)"
        : tone === "amber"
          ? "var(--color-amber)"
          : "var(--color-cyan)";
  return (
    <div
      className="panel relative p-1.5 flex flex-col gap-0.5 overflow-hidden animate-impact min-h-[94px]"
      style={{ animationDelay: `${delay}ms` }}
    >
      <span
        className="absolute left-0 top-0 bottom-0 w-[2px]"
        style={{
          background: `linear-gradient(180deg, ${accent}, transparent)`,
          opacity: 0.9,
        }}
      />
      <div className="text-[8px] tracking-widest text-[var(--color-muted-foreground)] leading-tight">
        {label}
        <br />
        <span className="text-[8px] opacity-70">(Avg)</span>
      </div>
      <div
        className={`text-[18px] leading-none tabular-nums font-semibold ${c}`}
      >
        {avg}
      </div>
      <div className="text-[8px] text-[var(--color-muted-foreground)]">
        {sub}
      </div>
      <Sparkline
        data={invert ? data.map((v) => 200 - v) : data}
        tone={tone === "mint" ? "mint" : "red"}
        height={18}
      />
    </div>
  );
}

function ScIcon({ k }: { k: string }) {
  const p = {
    width: 16,
    height: 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
  } as const;
  const c = "text-[var(--color-cyan)]";
  switch (k) {
    case "storm":
      return (
        <svg {...p} className={c}>
          <path d="M4 15a5 5 0 019.5-1.5A4 4 0 1117 20H7a4 4 0 01-3-5z" />
          <path d="M11 22l2-4h-3l2-4" />
        </svg>
      );
    case "cyc":
      return (
        <svg {...p} className={c}>
          <path d="M12 3a9 9 0 019 9h-9V3z M12 21a9 9 0 01-9-9h9v9z" />
          <circle cx="12" cy="12" r="2" />
        </svg>
      );
    case "worker":
      return (
        <svg {...p} className={c}>
          <circle cx="12" cy="6" r="2.5" />
          <path d="M6 20l3-8h6l3 8" />
        </svg>
      );
    case "crane":
      return (
        <svg {...p} className={c}>
          <path d="M4 20V4h4v6l10-3v3l-10 3v7" />
        </svg>
      );
    case "cargo":
      return (
        <svg {...p} className={c}>
          <rect x="3" y="8" width="18" height="10" />
          <path d="M3 13h18M9 8v10M15 8v10" />
        </svg>
      );
    case "gate":
      return (
        <svg {...p} className={c}>
          <rect x="3" y="4" width="18" height="16" />
          <path d="M9 4v16M15 4v16" />
        </svg>
      );
    case "drop":
      return (
        <svg {...p} className={c}>
          <path d="M12 3s6 7 6 12a6 6 0 01-12 0c0-5 6-12 6-12z" />
        </svg>
      );
    case "fuel":
      return (
        <svg {...p} className={c}>
          <rect x="4" y="4" width="10" height="16" rx="1" />
          <path d="M14 8h3v10a2 2 0 01-2 2" />
        </svg>
      );
    default:
      return null;
  }
}

function LegendDot({ c, t }: { c: string; t: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: c }} />
      {t}
    </span>
  );
}
