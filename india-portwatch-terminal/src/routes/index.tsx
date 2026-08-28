import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Chip, Sparkline } from "@/components/terminal/ui";
import { MaritimeMap } from "@/components/map/MaritimeMap";
import { fetchRadarOverview } from "@/services/ports";

export const Route = createFileRoute("/")({
  component: RadarPage,
});

function RadarPage() {
  const navigate = useNavigate();

  const radarQuery = useQuery({
    queryKey: ["radar-overview"],
    queryFn: fetchRadarOverview,
    staleTime: 30_000,
  });

  if (radarQuery.isLoading) {
    return (
      <div className="h-full grid place-items-center text-[var(--color-cyan)] text-[12px] tracking-[0.2em]">
        LOADING LIVE PORT RADAR...
      </div>
    );
  }

  if (radarQuery.isError || !radarQuery.data) {
    return (
      <div className="h-full grid place-items-center text-[var(--color-red)] text-[12px] tracking-[0.2em]">
        PORT RADAR API UNAVAILABLE
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
  const severe = ports.filter((p) => p.risk === "severe").length;
  const congested = ports.filter((p) => p.risk === "congested").length;
  const meanCong =
    (ports.reduce((a, p) => a + p.congestion, 0) / ports.length) * 100;
  const vessels = ports.reduce((a, p) => a + p.vessels, 0);
  const openPortCockpit = (portCode: string) =>
    navigate({ to: "/port", search: { port: portCode } });

  return (
    <div className="h-full flex flex-col">
      {/* Top: Map + Right rail */}
      <div className="flex-1 min-h-0 flex">
        {/* MAP */}
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
        </div>

        {/* RIGHT RAIL */}
        <aside className="w-[300px] shrink-0 bg-[oklch(0.11_0.02_240)] flex flex-col overflow-hidden">
          {/* National Stress Gauge */}
          <div className="border-b border-[var(--color-line)] p-3">
            <div className="label-xs mb-2">NATIONAL LOGISTICS STRESS</div>
            <div className="flex items-center gap-3">
              <StressGauge value={56} />
              <div className="flex flex-col text-[10px]">
                <span className="text-[var(--color-amber)] tracking-widest">
                  ELEVATED
                </span>
                <span className="text-[var(--color-red)] mt-1">↑ 8 pts</span>
                <span className="text-[var(--color-muted-foreground)]">
                  vs 24h ago
                </span>
                <Sparkline
                  data={[42, 45, 48, 50, 49, 52, 54, 56]}
                  tone="red"
                  height={20}
                />
              </div>
            </div>
          </div>

          {/* Top 5 Ports at Risk */}
          <div className="border-b border-[var(--color-line)] p-3">
            <div className="label-xs mb-2 flex justify-between">
              TOP 5 PORTS AT RISK{" "}
              <span className="text-[var(--color-cyan)] normal-case tracking-normal">
                See all
              </span>
            </div>
            <div className="space-y-1.5">
              {[...ports]
                .sort((a, b) => b.congestion - a.congestion)
                .slice(0, 5)
                .map((p, i) => (
                  <div
                    key={p.code}
                    className="grid grid-cols-[14px_1fr_32px_46px] items-center gap-2 text-[10px]"
                  >
                    <span className="text-[var(--color-muted-foreground)] tabular-nums">
                      {i + 1}.
                    </span>
                    <span className="text-[var(--color-foreground)] truncate">
                      {p.name}
                    </span>
                    <span className="tabular-nums text-right text-[var(--color-foreground)]">
                      {Math.round(p.congestion * 100)}
                    </span>
                    <Chip tone={p.risk === "severe" ? "red" : "amber"}>
                      {p.risk === "severe" ? "SEVERE" : "HIGH"}
                    </Chip>
                  </div>
                ))}
            </div>
          </div>

          {/* Active alerts */}
          <div className="border-b border-[var(--color-line)] p-3 flex-1 min-h-0 overflow-auto">
            <div className="label-xs mb-2 flex justify-between">
              ACTIVE ALERTS{" "}
              <span className="text-[var(--color-cyan)] normal-case tracking-normal">
                See all (8)
              </span>
            </div>
            <div className="space-y-1.5">
              {alerts.slice(0, 5).map((a) => (
                <div
                  key={a.id}
                  className="grid grid-cols-[52px_1fr_40px] items-start gap-2 text-[10px]"
                >
                  <Chip tone={a.severity === "severe" ? "red" : "amber"}>
                    {a.severity === "severe"
                      ? "SEVERE"
                      : a.severity === "watch"
                        ? "MEDIUM"
                        : "HIGH"}
                  </Chip>
                  <span className="text-[var(--color-foreground)] leading-snug">
                    {a.text}
                  </span>
                  <span className="tabular-nums text-right text-[var(--color-muted-foreground)]">
                    {a.ts}
                  </span>
                </div>
              ))}
              <div className="grid grid-cols-[52px_1fr_40px] items-start gap-2 text-[10px]">
                <Chip tone="cyan">INFO</Chip>
                <span className="text-[var(--color-foreground)] leading-snug">
                  Cyclonic circulation in Bay of Bengal
                </span>
                <span className="tabular-nums text-right text-[var(--color-muted-foreground)]">
                  03:05
                </span>
              </div>
            </div>
          </div>

          {/* AI Operator Summary */}
          <div className="p-3">
            <div className="label-xs mb-2 flex justify-between">
              AI OPERATOR SUMMARY{" "}
              <span className="text-[var(--color-muted-foreground)] normal-case tracking-normal">
                Updated: 03:12 UTC
              </span>
            </div>
            <div className="text-[10px] leading-relaxed text-[var(--color-foreground)]">
              West coast congestion is critical with JNPT and Mundra severely
              impacted. Bab-el-Mandeb disruptions are increasing transit times.
              Bay of Bengal shows developing cyclonic activity; monitor Paradip
              and Vizag. Activate berth reallocation and review vessel
              nominations.
            </div>
            <div className="mt-2 text-[10px] text-[var(--color-cyan)]">
              View full analysis in Decision Room →
            </div>
          </div>
        </aside>
      </div>

      {/* Bottom metric strip */}
      <div className="h-[104px] shrink-0 border-t border-[var(--color-line)] grid grid-cols-5">
        <BottomStat
          n={severe}
          unit=""
          label="SEVERE PORTS"
          tone="red"
          sub={
            <span>
              ↗ 2 vs 24h ago
              <br />
              <span className="text-[var(--color-foreground)]">
                JNPT · Mundra · Paradip · Chennai
              </span>
            </span>
          }
        />
        <BottomStat
          n={congested}
          unit=""
          label="CONGESTED PORTS"
          tone="amber"
          sub={
            <span>
              ↗ 1 vs 24h ago
              <br />
              <span className="text-[var(--color-foreground)]">
                Deendayal · Mumbai · Cochin · Vizag · Tuticorin · Kamarajar
              </span>
            </span>
          }
        />
        <div className="border-r border-[var(--color-line)] px-4 py-3 flex flex-col gap-1">
          <div className="text-[36px] leading-none tabular-nums text-[var(--color-amber)] glow-amber">
            {meanCong.toFixed(1)}
          </div>
          <div className="text-[9px] tracking-widest text-[var(--color-muted-foreground)]">
            MEAN CONGESTION SCORE
          </div>
          <div className="mt-1">
            <Sparkline
              data={[45, 48, 50, 52, 49, 51, 54, 56, 53, 55, 56.2]}
              tone="amber"
              height={22}
            />
          </div>
          <div className="text-[9px] text-[var(--color-mint)]">
            ↑ 6.8 vs 24h ago
          </div>
        </div>
        <BottomStat
          n={vessels}
          unit=""
          label="VESSELS IN FIELD"
          tone="cyan"
          sub={
            <span>
              ↗ 9 vs 24h ago
              <br />
              <span className="text-[var(--color-foreground)]">
                Cargo 84 · Tanker 19 · Others 18
              </span>
            </span>
          }
        />
        <div className="px-4 py-3 flex flex-col gap-1">
          <div className="text-[36px] leading-none tabular-nums text-[var(--color-purple)]">
            5
          </div>
          <div className="text-[9px] tracking-widest text-[var(--color-muted-foreground)]">
            WEATHER SYSTEMS TRACKED
          </div>
          <div className="text-[10px] text-[var(--color-foreground)] mt-1">
            1 Cyclone · 2 Depressions · 2 Systems
          </div>
          <div className="text-[9px] text-[var(--color-muted-foreground)]">
            Bay of Bengal · Arabian Sea
          </div>
        </div>
      </div>
    </div>
  );
}

function BottomStat({
  n,
  unit,
  label,
  tone,
  sub,
}: {
  n: number;
  unit: string;
  label: string;
  tone: "red" | "amber" | "cyan";
  sub: React.ReactNode;
}) {
  const c =
    tone === "red"
      ? "text-[var(--color-red)] glow-red"
      : tone === "amber"
        ? "text-[var(--color-amber)] glow-amber"
        : "text-[var(--color-cyan)] glow-cyan";
  return (
    <div className="border-r border-[var(--color-line)] px-4 py-3 flex flex-col gap-1">
      <div className={`text-[36px] leading-none tabular-nums ${c}`}>
        {n}
        {unit}
      </div>
      <div className="text-[9px] tracking-widest text-[var(--color-muted-foreground)]">
        {label}
      </div>
      <div className="text-[9px] text-[var(--color-muted-foreground)] leading-snug mt-1">
        {sub}
      </div>
    </div>
  );
}

function StressGauge({ value }: { value: number }) {
  const r = 44;
  const c = 2 * Math.PI * r;
  const pct = value / 100;
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
        <circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke="oklch(0.22 0.03 240)"
          strokeWidth="9"
        />
        <circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke="url(#stressG)"
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={`${c * pct} ${c}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-[28px] leading-none tabular-nums text-[var(--color-foreground)]">
          {value}
        </div>
        <div className="text-[8px] tracking-widest text-[var(--color-muted-foreground)]">
          /100
        </div>
      </div>
    </div>
  );
}

const MapCanvas = MaritimeMap;
