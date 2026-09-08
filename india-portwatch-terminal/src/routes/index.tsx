import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Chip, Sparkline } from "@/components/terminal/ui";
import { MaritimeMap } from "@/components/map/MaritimeMap";
import { fetchRadarOverview } from "@/services/ports";

export const Route = createFileRoute("/")({ component: RadarPage });

function RadarPage() {
  const navigate = useNavigate();
  const radarQuery = useQuery({
    queryKey: ["radar-overview"],
    queryFn: fetchRadarOverview,
    staleTime: 4_000,
    refetchInterval: 5_000,
    refetchIntervalInBackground: true,
  });

  if (radarQuery.isLoading) {
    return (
      <div className="h-full grid place-items-center text-[var(--color-cyan)] text-[12px] tracking-[0.2em]">
        FUSING PORT · AIS · WEATHER · EVENT SIGNALS...
      </div>
    );
  }

  if (radarQuery.isError || !radarQuery.data) {
    return (
      <div className="h-full grid place-items-center text-[var(--color-red)] text-[12px] tracking-[0.2em]">
        LIVE INTELLIGENCE API UNAVAILABLE
      </div>
    );
  }

  const {
    ports,
    vessels: vesselProxies,
    chokepoints,
    routes,
    alerts,
    weatherSignals,
    sarSignals,
  } = radarQuery.data;

  const sortedPorts = [...ports].sort((a, b) => b.congestion - a.congestion);
  const severePorts = sortedPorts.filter((p) => p.risk === "severe");
  const congestedPorts = sortedPorts.filter((p) => p.risk === "congested");
  const meanCong = ports.length
    ? (ports.reduce((sum, p) => sum + p.congestion, 0) / ports.length) * 100
    : 0;
  const vesselCount = ports.reduce((sum, p) => sum + p.vessels, 0);
  const severeAlertCount = alerts.filter((a) => a.severity === "severe").length;
  const nationalStress = Math.round(
    Math.min(
      100,
      meanCong * 0.68 +
        (severePorts.length / Math.max(ports.length, 1)) * 22 +
        Math.min(severeAlertCount * 3, 10),
    ),
  );
  const stressLabel =
    nationalStress >= 75 ? "CRITICAL" : nationalStress >= 55 ? "ELEVATED" : nationalStress >= 35 ? "WATCH" : "STABLE";
  const stressTone = nationalStress >= 75 ? "text-[var(--color-red)]" : "text-[var(--color-amber)]";
  const updatedAt = new Date(radarQuery.dataUpdatedAt).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const topPort = sortedPorts[0];
  const topThree = sortedPorts.slice(0, 3).map((p) => p.short ?? p.name).join(" · ");
  const liveSignals = vesselProxies.length + weatherSignals.length + sarSignals.length + alerts.length;

  const openPortCockpit = (portCode: string) =>
    navigate({ to: "/port", search: { port: portCode } });

  const operatorSummary = topPort
    ? `${topPort.name} is the highest-pressure port at ${Math.round(topPort.congestion * 100)}/100. ${severePorts.length} port${severePorts.length === 1 ? " is" : "s are"} in severe state and ${alerts.length} event alerts are active. Prioritize ${topThree || topPort.name}; use the Decision Room before committing arrivals.`
    : "National port telemetry is initializing.";

  return (
    <div className="h-full flex flex-col bg-[oklch(0.09_0.015_240)]">
      <div className="h-[34px] shrink-0 border-b border-[var(--color-line)] bg-[oklch(0.13_0.025_240)] px-3 flex items-center gap-4 text-[9px] tracking-[0.13em]">
        <span className="flex items-center gap-2 text-[var(--color-mint)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-mint)] animate-blink" />
          DIGITAL TWIN LIVE
        </span>
        <span className="text-[var(--color-muted-foreground)]">
          AUTO-REFRESH 5S · LAST FUSION <span className="text-[var(--color-foreground)] tabular-nums">{updatedAt}</span>
        </span>
        <span className="text-[var(--color-muted-foreground)]">
          SIGNALS <span className="text-[var(--color-cyan)] tabular-nums">{liveSignals}</span>
        </span>
        <span className="text-[var(--color-muted-foreground)]">
          PORTS <span className="text-[var(--color-cyan)] tabular-nums">{ports.length}</span>
        </span>
        <span className="ml-auto text-[var(--color-cyan)]">AIS · SAR · WEATHER · NLP · HSMM · ENSEMBLE</span>
      </div>

      <div className="flex-1 min-h-0 flex">
        <div className="flex-1 relative overflow-hidden border-r border-[var(--color-line)]">
          <MapCanvas
            ports={ports}
            vessels={vesselProxies}
            chokepoints={chokepoints}
            routes={routes}
            alerts={alerts}
            weatherSignals={weatherSignals}
            sarSignals={sarSignals}
            onPortSelect={openPortCockpit}
          />
          <div className="absolute left-3 top-3 w-[250px] border border-[var(--color-line-strong)] bg-[oklch(0.09_0.02_240_/_0.92)] backdrop-blur-sm shadow-xl">
            <div className="px-3 py-2 border-b border-[var(--color-line)] flex items-center justify-between">
              <span className="label-xs">MISSION NOW</span>
              <Chip tone={nationalStress >= 75 ? "red" : "amber"}>{stressLabel}</Chip>
            </div>
            <div className="p-3 space-y-2 text-[10px]">
              {sortedPorts.slice(0, 3).map((p, index) => (
                <button
                  key={p.code}
                  onClick={() => openPortCockpit(p.code)}
                  className="w-full text-left grid grid-cols-[18px_1fr_auto] gap-2 items-center group"
                >
                  <span className="text-[var(--color-muted-foreground)] tabular-nums">0{index + 1}</span>
                  <span className="text-[var(--color-foreground)] group-hover:text-[var(--color-cyan)] truncate">
                    {index === 0 ? "Intervene" : "Prepare"} · {p.short ?? p.name}
                  </span>
                  <span className={p.risk === "severe" ? "text-[var(--color-red)]" : "text-[var(--color-amber)]"}>
                    {Math.round(p.congestion * 100)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <aside className="w-[320px] shrink-0 bg-[oklch(0.11_0.02_240)] flex flex-col overflow-hidden">
          <div className="border-b border-[var(--color-line)] p-3">
            <div className="label-xs mb-2 flex justify-between">
              NATIONAL LOGISTICS STRESS
              <span className="text-[var(--color-muted-foreground)] normal-case tracking-normal">computed live</span>
            </div>
            <div className="flex items-center gap-3">
              <StressGauge value={nationalStress} />
              <div className="flex-1 text-[10px]">
                <div className={`${stressTone} tracking-[0.16em] font-semibold`}>{stressLabel}</div>
                <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[9px]">
                  <span className="text-[var(--color-muted-foreground)]">Severe ports</span><span className="text-right text-[var(--color-red)] tabular-nums">{severePorts.length}</span>
                  <span className="text-[var(--color-muted-foreground)]">Active alerts</span><span className="text-right tabular-nums">{alerts.length}</span>
                  <span className="text-[var(--color-muted-foreground)]">Mean congestion</span><span className="text-right tabular-nums">{meanCong.toFixed(1)}</span>
                </div>
                <div className="mt-2">
                  <Sparkline data={sortedPorts.slice(0, 8).map((p) => p.congestion * 100).reverse()} tone="amber" height={22} />
                </div>
              </div>
            </div>
          </div>

          <div className="border-b border-[var(--color-line)] p-3">
            <div className="label-xs mb-2 flex justify-between">
              PRIORITY PORTS
              <span className="text-[var(--color-cyan)] normal-case tracking-normal">click to inspect</span>
            </div>
            <div className="space-y-1">
              {sortedPorts.slice(0, 6).map((p, i) => (
                <button
                  key={p.code}
                  onClick={() => openPortCockpit(p.code)}
                  className="w-full grid grid-cols-[18px_1fr_38px_54px] items-center gap-2 px-1 py-1.5 text-[10px] hover:bg-[var(--color-cyan)]/5 hover:text-[var(--color-cyan)] transition-colors"
                >
                  <span className="text-[var(--color-muted-foreground)] tabular-nums">{i + 1}</span>
                  <span className="text-left truncate">{p.name}</span>
                  <span className="tabular-nums text-right">{Math.round(p.congestion * 100)}</span>
                  <Chip tone={p.risk === "severe" ? "red" : p.risk === "congested" ? "amber" : "cyan"}>
                    {p.risk === "severe" ? "SEVERE" : p.risk === "congested" ? "HIGH" : "WATCH"}
                  </Chip>
                </button>
              ))}
            </div>
          </div>

          <div className="border-b border-[var(--color-line)] p-3 flex-1 min-h-0 overflow-auto">
            <div className="label-xs mb-2 flex justify-between">
              EVENT INTELLIGENCE
              <span className="text-[var(--color-cyan)] normal-case tracking-normal">{alerts.length} active</span>
            </div>
            <div className="space-y-2">
              {alerts.slice(0, 6).map((a) => (
                <div key={a.id} className="grid grid-cols-[52px_1fr_40px] items-start gap-2 text-[10px]">
                  <Chip tone={a.severity === "severe" ? "red" : "amber"}>
                    {a.severity === "severe" ? "SEVERE" : a.severity === "watch" ? "WATCH" : "HIGH"}
                  </Chip>
                  <span className="text-[var(--color-foreground)] leading-snug">{a.text}</span>
                  <span className="tabular-nums text-right text-[var(--color-muted-foreground)]">{a.ts}</span>
                </div>
              ))}
              {!alerts.length && <div className="text-[10px] text-[var(--color-muted-foreground)]">No active event alerts.</div>}
            </div>
          </div>

          <div className="p-3 bg-[linear-gradient(180deg,transparent,oklch(0.16_0.04_220_/_0.35))]">
            <div className="label-xs mb-2 flex justify-between">
              AI OPERATOR BRIEF
              <span className="text-[var(--color-muted-foreground)] normal-case tracking-normal">{updatedAt}</span>
            </div>
            <div className="text-[10px] leading-relaxed text-[var(--color-foreground)]">{operatorSummary}</div>
            <button
              onClick={() => navigate({ to: "/sim" })}
              className="mt-2 text-[10px] text-[var(--color-cyan)] hover:underline"
            >
              Open Decision Room →
            </button>
          </div>
        </aside>
      </div>

      <div className="h-[96px] shrink-0 border-t border-[var(--color-line)] grid grid-cols-5">
        <BottomStat n={severePorts.length} label="SEVERE PORTS" tone="red" sub={severePorts.slice(0, 4).map((p) => p.short ?? p.name).join(" · ") || "No severe state"} />
        <BottomStat n={congestedPorts.length} label="CONGESTED PORTS" tone="amber" sub={congestedPorts.slice(0, 4).map((p) => p.short ?? p.name).join(" · ") || "No congested state"} />
        <BottomStat n={Number(meanCong.toFixed(1))} label="MEAN CONGESTION" tone="amber" sub={`National stress ${nationalStress}/100`} />
        <BottomStat n={vesselCount} label="VESSELS IN FIELD" tone="cyan" sub={`${vesselProxies.length} tracked proxies · ${sarSignals.length} SAR signals`} />
        <div className="px-4 py-3 flex flex-col gap-1">
          <div className="text-[34px] leading-none tabular-nums text-[var(--color-purple)]">{weatherSignals.length}</div>
          <div className="text-[9px] tracking-widest text-[var(--color-muted-foreground)]">WEATHER SIGNALS</div>
          <div className="text-[9px] text-[var(--color-foreground)] mt-1">Live marine risk layer</div>
          <div className="text-[9px] text-[var(--color-muted-foreground)]">Fused into national radar</div>
        </div>
      </div>
    </div>
  );
}

function BottomStat({ n, label, tone, sub }: { n: number; label: string; tone: "red" | "amber" | "cyan"; sub: ReactNode }) {
  const color = tone === "red" ? "text-[var(--color-red)] glow-red" : tone === "amber" ? "text-[var(--color-amber)] glow-amber" : "text-[var(--color-cyan)] glow-cyan";
  return (
    <div className="border-r border-[var(--color-line)] px-4 py-3 flex flex-col gap-1 min-w-0">
      <div className={`text-[34px] leading-none tabular-nums ${color}`}>{n}</div>
      <div className="text-[9px] tracking-widest text-[var(--color-muted-foreground)]">{label}</div>
      <div className="text-[9px] text-[var(--color-muted-foreground)] leading-snug mt-1 truncate">{sub}</div>
    </div>
  );
}

function StressGauge({ value }: { value: number }) {
  const r = 44;
  const circumference = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, value / 100));
  return (
    <div className="relative w-[108px] h-[108px]">
      <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90">
        <defs>
          <linearGradient id="stressG" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#7ef0b4" />
            <stop offset="50%" stopColor="#ffb347" />
            <stop offset="100%" stopColor="#ff5566" />
          </linearGradient>
        </defs>
        <circle cx="60" cy="60" r={r} fill="none" stroke="oklch(0.22 0.03 240)" strokeWidth="9" />
        <circle cx="60" cy="60" r={r} fill="none" stroke="url(#stressG)" strokeWidth="9" strokeLinecap="round" strokeDasharray={`${circumference * pct} ${circumference}`} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-[28px] leading-none tabular-nums text-[var(--color-foreground)]">{value}</div>
        <div className="text-[8px] tracking-widest text-[var(--color-muted-foreground)]">/100</div>
      </div>
    </div>
  );
}

const MapCanvas = MaritimeMap;
