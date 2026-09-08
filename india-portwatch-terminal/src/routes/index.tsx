import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Chip,
  ErrorState,
  Loading,
  ProvenanceChip,
  Sparkline,
  Value,
  formatAge,
  formatUtc,
  riskLabel,
  riskTone,
} from "@/components/terminal/ui";
import { MaritimeMap } from "@/components/map/MaritimeMap";
import { fetchRadarOverview } from "@/services/portwatch";
import type { PortSnapshot } from "@/types/portwatch";

export const Route = createFileRoute("/")({ component: RadarPage });

/**
 * National radar. The screen has one job: let an operator answer "which port
 * needs intervention right now, and why" inside five seconds. Everything is
 * ranked by the decision engine's own priority score, and every panel states
 * how fresh its data is.
 */
function RadarPage() {
  const navigate = useNavigate();
  const [focusPort, setFocusPort] = useState<string | null>(null);

  const radar = useQuery({
    queryKey: ["radar-overview"],
    queryFn: fetchRadarOverview,
    staleTime: 20_000,
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
    retry: 1,
  });

  const derived = useMemo(() => {
    if (!radar.data) return null;
    const { ports, news, health } = radar.data;

    const ranked = [...ports].sort(
      (a, b) =>
        (b.priorityScore ?? b.congestion) - (a.priorityScore ?? a.congestion),
    );
    const severe = ports.filter((p) => p.risk === "severe");
    const congested = ports.filter((p) => p.risk === "congested");
    const meanCongestion = ports.length
      ? ports.reduce((sum, p) => sum + p.congestionIndex, 0) / ports.length
      : 0;

    // National stress: the mean forecast congestion, escalated by the share of
    // ports the HSMM has actually placed in a severe state and by the number of
    // severe alerts the decision engine raised. Every term is measured.
    const severeAlerts = news.alerts.filter((a) => a.severity === "severe").length;
    const stress = Math.round(
      Math.min(
        100,
        meanCongestion * 0.7 +
          (severe.length / Math.max(ports.length, 1)) * 22 +
          Math.min(severeAlerts * 3, 8),
      ),
    );
    const stressLabel =
      stress >= 75 ? "CRITICAL" : stress >= 55 ? "ELEVATED" : stress >= 35 ? "WATCH" : "STABLE";

    const disagreements = ports
      .map((p) => p.modelDisagreement)
      .filter((v): v is number => v != null);
    const meanDisagreement = disagreements.length
      ? disagreements.reduce((a, b) => a + b, 0) / disagreements.length
      : null;
    const meanConfidence = ports.length
      ? ports.reduce((sum, p) => sum + p.confidence, 0) / ports.length
      : 0;

    const worstStatus: PortSnapshot["dataStatus"] = ports.some(
      (p) => p.dataStatus === "UNAVAILABLE",
    )
      ? "UNAVAILABLE"
      : ports.some((p) => p.dataStatus === "STALE")
        ? "STALE"
        : ports.some((p) => p.dataStatus === "SYNTHETIC")
          ? "SYNTHETIC"
          : (ports[0]?.dataStatus ?? "UNAVAILABLE");

    return {
      ranked,
      severe,
      congested,
      meanCongestion,
      stress,
      stressLabel,
      meanDisagreement,
      meanConfidence,
      worstStatus,
      health,
    };
  }, [radar.data]);

  if (radar.isLoading) {
    return <Loading label="FUSING PORT · AIS · WEATHER · EVENT SIGNALS" />;
  }
  if (radar.isError || !radar.data || !derived) {
    return <ErrorState error={radar.error} />;
  }

  const { ports, vessels, weather, news, health } = radar.data;
  const {
    ranked,
    severe,
    congested,
    meanCongestion,
    stress,
    stressLabel,
    meanDisagreement,
    meanConfidence,
    worstStatus,
  } = derived;

  const openCockpit = (portCode: string) =>
    navigate({ to: "/port", search: { port: portCode } });

  const lead = ranked[0];
  const alertPorts = news.alerts.map((a) => a.portCode);

  return (
    <div className="h-full flex flex-col bg-[oklch(0.09_0.015_240)]">
      {/* Live status strip: what the twin is actually running on. */}
      <div className="h-[32px] shrink-0 border-b border-[var(--color-line)] bg-[oklch(0.13_0.025_240)] px-3 flex items-center gap-4 text-[9px] tracking-[0.13em] overflow-x-auto">
        <span className="flex items-center gap-2 shrink-0">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              health.intelligence === "live"
                ? "bg-[var(--color-mint)] animate-blink"
                : health.intelligence === "cached"
                  ? "bg-[var(--color-cyan)]"
                  : "bg-[var(--color-amber)]"
            }`}
          />
          <span className="text-[var(--color-foreground)]">DIGITAL TWIN</span>
          <ProvenanceChip
            status={health.forecastOriginStatus}
            ageHours={health.forecastOriginAgeHours}
            detail={`Forecast origin ${formatUtc(health.forecastOrigin)}`}
          />
        </span>
        <span className="text-[var(--color-muted-foreground)] shrink-0">
          MODEL <span className="text-[var(--color-cyan)]">{health.model ?? "n/a"}</span>
        </span>
        <span className="text-[var(--color-muted-foreground)] shrink-0">
          ORIGIN{" "}
          <span className="text-[var(--color-foreground)] tabular-nums">
            {formatUtc(health.forecastOrigin)}
          </span>
        </span>
        <span className="text-[var(--color-muted-foreground)] shrink-0">
          SOURCE READINESS{" "}
          <span className="text-[var(--color-cyan)] tabular-nums">
            {(health.sources.readiness * 100).toFixed(0)}%
          </span>
        </span>
        <span className="text-[var(--color-muted-foreground)] shrink-0">
          MODEL CONF{" "}
          <span className="text-[var(--color-cyan)] tabular-nums">
            {(meanConfidence * 100).toFixed(0)}%
          </span>
        </span>
        <span className="text-[var(--color-muted-foreground)] shrink-0">
          DISAGREEMENT{" "}
          <span className="text-[var(--color-purple)] tabular-nums">
            {meanDisagreement == null ? "n/a" : `${(meanDisagreement * 100).toFixed(0)}%`}
          </span>
        </span>
        {health.sources.synthetic.length > 0 && (
          <Chip tone="purple" title={health.sources.synthetic.join(", ")}>
            {health.sources.synthetic.length} SYNTHETIC
          </Chip>
        )}
        {health.sources.stale.length > 0 && (
          <Chip tone="amber" title={health.sources.stale.join(", ")}>
            {health.sources.stale.length} STALE
          </Chip>
        )}
        <span className="ml-auto shrink-0 text-[var(--color-cyan)]">
          AIS · WX · EVENTS · CAPACITY · ANOMALY · HSMM · ENSEMBLE
        </span>
      </div>

      <div className="flex-1 min-h-0 flex">
        <div className="flex-1 relative overflow-hidden border-r border-[var(--color-line)]">
          <MaritimeMap
            ports={ports}
            vessels={vessels.vessels}
            weather={weather}
            selectedPort={focusPort}
            highlightedPorts={alertPorts}
            onPortSelect={openCockpit}
          />

          {/* MISSION NOW: the ranked intervention list, straight from the
              decision engine's priority score. */}
          <div className="absolute left-3 top-3 w-[286px] border border-[var(--color-line-strong)] bg-[oklch(0.09_0.02_240_/_0.94)] shadow-xl">
            <div className="px-3 py-2 border-b border-[var(--color-line)] flex items-center justify-between">
              <span className="label-xs">MISSION NOW</span>
              <Chip tone={stress >= 75 ? "red" : stress >= 55 ? "amber" : "cyan"}>
                {stressLabel}
              </Chip>
            </div>
            <div className="p-2 space-y-1">
              {ranked.slice(0, 4).map((port, index) => (
                <button
                  key={port.code}
                  onClick={() => openCockpit(port.code)}
                  onMouseEnter={() => setFocusPort(port.code)}
                  onMouseLeave={() => setFocusPort(null)}
                  className="w-full text-left px-1 py-1.5 hover:bg-[var(--color-cyan)]/5 transition-colors"
                >
                  <div className="grid grid-cols-[16px_1fr_auto] items-baseline gap-2">
                    <span className="text-[9px] text-[var(--color-muted-foreground)] tabular-nums">
                      {index + 1}
                    </span>
                    <span className="text-[11px] text-[var(--color-foreground)] truncate">
                      {port.short}
                    </span>
                    <span
                      className="text-[11px] tabular-nums"
                      style={{ color: `var(--color-${riskTone(port.risk) === "mint" ? "mint" : riskTone(port.risk)})` }}
                    >
                      {port.congestionIndex.toFixed(0)}
                    </span>
                  </div>
                  <div className="pl-[24px] text-[9px] text-[var(--color-muted-foreground)] leading-snug truncate">
                    {port.actionTitle ?? "No action recommended"}
                    {port.recommendedAction ? ` · ${port.recommendedAction}` : ""}
                  </div>
                </button>
              ))}
              {!ranked.length && (
                <div className="px-1 py-2 text-[10px] text-[var(--color-muted-foreground)]">
                  No ports in the current forecast.
                </div>
              )}
            </div>
          </div>

          {/* The five-second answer. */}
          {lead && (
            <div className="absolute left-3 bottom-3 w-[420px] border border-[var(--color-line-strong)] bg-[oklch(0.09_0.02_240_/_0.94)] shadow-xl">
              <div className="px-3 py-1.5 border-b border-[var(--color-line)] flex items-center justify-between">
                <span className="label-xs">WHO NEEDS INTERVENTION</span>
                <ProvenanceChip
                  status={lead.dataStatus}
                  ageHours={lead.dataAgeHours}
                />
              </div>
              <div className="p-3 space-y-1.5">
                <div className="flex items-baseline gap-2">
                  <span className="text-[15px] text-[var(--color-foreground)]">
                    {lead.name}
                  </span>
                  <Chip tone={riskTone(lead.risk)}>{riskLabel(lead.risk)}</Chip>
                  <span className="ml-auto text-[10px] text-[var(--color-muted-foreground)]">
                    priority{" "}
                    <span className="tabular-nums text-[var(--color-foreground)]">
                      {lead.priorityScore?.toFixed(2) ?? "n/a"}
                    </span>
                  </span>
                </div>
                <div className="text-[11px] leading-relaxed text-[var(--color-foreground)]">
                  {lead.actionTitle ?? "No action recommended"} ·{" "}
                  <span className="text-[var(--color-muted-foreground)]">
                    day-1 congestion {lead.congestionIndex.toFixed(1)} (
                    {lead.forecastQ10?.toFixed(0) ?? "?"}–
                    {lead.forecastQ90?.toFixed(0) ?? "?"} at 80%), expected wait{" "}
                    {lead.delayHours.toFixed(1)}h, regime {lead.regime}
                    {lead.expectedRemainingDays != null &&
                      ` for ~${lead.expectedRemainingDays.toFixed(1)}d more`}
                    .
                  </span>
                </div>
                <div className="flex gap-3 pt-1">
                  <button
                    onClick={() => openCockpit(lead.code)}
                    className="text-[10px] text-[var(--color-cyan)] hover:underline"
                  >
                    Open port cockpit →
                  </button>
                  <button
                    onClick={() =>
                      navigate({
                        to: "/sim",
                        search: { scenario: "HORMUZ", intensity: 1 },
                      })
                    }
                    className="text-[10px] text-[var(--color-cyan)] hover:underline"
                  >
                    Stress-test in the Decision Room →
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        <aside className="w-[326px] shrink-0 bg-[oklch(0.11_0.02_240)] flex flex-col overflow-hidden">
          <div className="border-b border-[var(--color-line)] p-3">
            <div className="label-xs mb-2 flex justify-between">
              NATIONAL LOGISTICS STRESS
              <ProvenanceChip status={worstStatus} />
            </div>
            <div className="flex items-center gap-3">
              <StressGauge value={stress} />
              <div className="flex-1 text-[10px] min-w-0">
                <div
                  className={`tracking-[0.16em] font-semibold ${
                    stress >= 75
                      ? "text-[var(--color-red)]"
                      : stress >= 55
                        ? "text-[var(--color-amber)]"
                        : "text-[var(--color-cyan)]"
                  }`}
                >
                  {stressLabel}
                </div>
                <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[9px]">
                  <span className="text-[var(--color-muted-foreground)]">Severe ports</span>
                  <span className="text-right tabular-nums text-[var(--color-red)]">
                    {severe.length}
                  </span>
                  <span className="text-[var(--color-muted-foreground)]">Congested</span>
                  <span className="text-right tabular-nums text-[var(--color-amber)]">
                    {congested.length}
                  </span>
                  <span className="text-[var(--color-muted-foreground)]">Mean forecast</span>
                  <span className="text-right tabular-nums">
                    {meanCongestion.toFixed(1)}
                  </span>
                  <span className="text-[var(--color-muted-foreground)]">Active alerts</span>
                  <span className="text-right tabular-nums">{news.alerts.length}</span>
                </div>
              </div>
            </div>
          </div>

          <div className="border-b border-[var(--color-line)] p-3">
            <div className="label-xs mb-2 flex justify-between">
              PRIORITY PORTS
              <span className="normal-case tracking-normal text-[var(--color-cyan)]">
                click to inspect
              </span>
            </div>
            <div className="space-y-0.5">
              {ranked.slice(0, 7).map((port, index) => (
                <button
                  key={port.code}
                  onClick={() => openCockpit(port.code)}
                  onMouseEnter={() => setFocusPort(port.code)}
                  onMouseLeave={() => setFocusPort(null)}
                  className="w-full grid grid-cols-[14px_1fr_44px_58px_28px] items-center gap-1.5 px-1 py-1 text-[10px] hover:bg-[var(--color-cyan)]/5 hover:text-[var(--color-cyan)] transition-colors"
                >
                  <span className="text-[var(--color-muted-foreground)] tabular-nums">
                    {index + 1}
                  </span>
                  <span className="text-left truncate">{port.short}</span>
                  <span className="tabular-nums text-right">
                    {port.congestionIndex.toFixed(1)}
                  </span>
                  <Chip tone={riskTone(port.risk)}>{riskLabel(port.risk)}</Chip>
                  <span className="text-right">
                    <Sparkline
                      data={port.congestionHistory.map((h) => h.value)}
                      tone={riskTone(port.risk)}
                      height={12}
                    />
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="border-b border-[var(--color-line)] p-3 flex-1 min-h-0 overflow-auto">
            <div className="label-xs mb-2 flex justify-between">
              EVENT INTELLIGENCE
              <span className="normal-case tracking-normal text-[var(--color-cyan)]">
                {news.summary.totalEvents} events · {news.alerts.length} alerts
              </span>
            </div>
            <div className="space-y-2">
              {news.alerts.slice(0, 5).map((alert) => (
                <button
                  key={alert.id}
                  onClick={() => openCockpit(alert.portCode)}
                  onMouseEnter={() => setFocusPort(alert.portCode)}
                  onMouseLeave={() => setFocusPort(null)}
                  className="w-full text-left grid grid-cols-[54px_1fr] items-start gap-2 text-[10px] hover:bg-[var(--color-cyan)]/5 px-1 py-0.5"
                >
                  <Chip tone={riskTone(alert.severity)}>
                    {alert.severity.toUpperCase()}
                  </Chip>
                  <span className="leading-snug">
                    {alert.text}
                    <span className="block text-[9px] text-[var(--color-muted-foreground)]">
                      {alert.action} · confidence{" "}
                      <Value value={alert.confidence} digits={2} />
                    </span>
                  </span>
                </button>
              ))}
              {news.events.slice(0, 4).map((event) => (
                <a
                  key={event.id}
                  href={event.url || undefined}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="block px-1 py-0.5 text-[10px] hover:bg-[var(--color-cyan)]/5"
                >
                  <div className="flex items-start gap-2">
                    <Chip tone={riskTone(event.severity)}>{event.tag}</Chip>
                    <span className="leading-snug text-[var(--color-foreground)]">
                      {event.title}
                    </span>
                  </div>
                  <div className="pl-1 text-[9px] text-[var(--color-muted-foreground)]">
                    {event.source} · {formatUtc(event.timestamp)} ·{" "}
                    {event.affectedPorts.slice(0, 3).join(" ")}
                  </div>
                </a>
              ))}
              {!news.summary.eventsAvailable && !news.alerts.length && (
                <div className="text-[10px] text-[var(--color-muted-foreground)]">
                  {news.summary.dataSource}
                </div>
              )}
            </div>
          </div>

          <div className="p-3">
            <div className="label-xs mb-1.5 flex justify-between">
              SIGNAL FRESHNESS
              <span className="normal-case tracking-normal text-[var(--color-muted-foreground)]">
                last export {formatUtc(health.lastRefreshUtc)}
              </span>
            </div>
            <div className="space-y-1 text-[9px]">
              {(
                [
                  ["LIVE", health.sources.live, "mint"],
                  ["CACHED", health.sources.cached, "cyan"],
                  ["STALE", health.sources.stale, "amber"],
                  ["SYNTHETIC", health.sources.synthetic, "purple"],
                  ["UNAVAILABLE", health.sources.unavailable, "red"],
                ] as const
              )
                .filter(([, list]) => list.length > 0)
                .map(([label, list, tone]) => (
                  <div key={label} className="grid grid-cols-[74px_1fr] gap-2">
                    <Chip tone={tone}>{label}</Chip>
                    <span className="text-[var(--color-muted-foreground)] leading-snug">
                      {list.join(" · ")}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        </aside>
      </div>

      <div className="h-[80px] shrink-0 border-t border-[var(--color-line)] grid grid-cols-5">
        <BottomStat
          n={severe.length}
          label="SEVERE PORTS"
          tone="red"
          sub={severe.map((p) => p.short).join(" · ") || "None in severe state"}
        />
        <BottomStat
          n={congested.length}
          label="CONGESTED PORTS"
          tone="amber"
          sub={congested.map((p) => p.short).join(" · ") || "None congested"}
        />
        <BottomStat
          n={Number(meanCongestion.toFixed(1))}
          label="MEAN FORECAST CONGESTION"
          tone="amber"
          sub={`National stress ${stress}/100 · horizon ${health.horizonDays ?? "?"}d`}
        />
        <BottomStat
          n={Math.round(
            vessels.vessels.reduce((sum, v) => sum + (v.dailyPortCalls ?? 0), 0),
          )}
          label="DAILY PORT CALLS"
          tone="cyan"
          sub={vessels.basis}
        />
        <BottomStat
          n={weather.filter((w) => (w.impactScore ?? 0) >= 0.35).length}
          label="PORTS UNDER WEATHER LOAD"
          tone="purple"
          sub={
            weather.length
              ? `${weather.length} ports with measured marine weather`
              : "No marine weather in this run"
          }
        />
      </div>
    </div>
  );
}

function BottomStat({
  n,
  label,
  tone,
  sub,
}: {
  n: number;
  label: string;
  tone: "red" | "amber" | "cyan" | "purple";
  sub: string;
}) {
  return (
    <div className="border-r border-[var(--color-line)] px-3 py-2 flex flex-col gap-0.5 min-w-0 last:border-r-0">
      <div
        className="text-[28px] leading-none tabular-nums"
        style={{ color: `var(--color-${tone})` }}
      >
        {n}
      </div>
      <div className="text-[8px] tracking-widest text-[var(--color-muted-foreground)]">
        {label}
      </div>
      <div className="text-[9px] text-[var(--color-muted-foreground)] leading-snug truncate">
        {sub}
      </div>
    </div>
  );
}

function StressGauge({ value }: { value: number }) {
  const r = 40;
  const circumference = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, value / 100));
  return (
    <div className="relative w-[96px] h-[96px] shrink-0">
      <svg viewBox="0 0 110 110" className="w-full h-full -rotate-90">
        <defs>
          <linearGradient id="stressGauge" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--color-mint)" />
            <stop offset="55%" stopColor="var(--color-amber)" />
            <stop offset="100%" stopColor="var(--color-red)" />
          </linearGradient>
        </defs>
        <circle
          cx="55"
          cy="55"
          r={r}
          fill="none"
          stroke="oklch(0.22 0.03 240)"
          strokeWidth="8"
        />
        <circle
          cx="55"
          cy="55"
          r={r}
          fill="none"
          stroke="url(#stressGauge)"
          strokeWidth="8"
          strokeLinecap="butt"
          strokeDasharray={`${circumference * pct} ${circumference}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-[24px] leading-none tabular-nums text-[var(--color-foreground)]">
          {value}
        </div>
        <div className="text-[8px] tracking-widest text-[var(--color-muted-foreground)]">
          /100
        </div>
      </div>
    </div>
  );
}
