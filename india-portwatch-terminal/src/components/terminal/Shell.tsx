import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Chip } from "./ui";
import { cn } from "@/lib/utils";
import { getPort } from "@/services/portService";
import { resolveScenarioKey } from "@/services/scenarioService";

const RAIL = [
  { key: "Port Radar",         to: "/",       icon: "radar" },
  { key: "Port Cockpit",       to: "/port",   icon: "port" },
  { key: "Decision Room",      to: "/sim",    icon: "sim" },
  { key: "Fleet Board",        to: "/fleet",  icon: "fleet" },
  { key: "Model Intelligence", to: "/model",  icon: "model" },
  { key: "Weather Intel",      to: "/wx",     icon: "wx" },
  { key: "SAR / AIS",          to: "/sar",    icon: "sar" },
  { key: "News / NLP",         to: "/nlp",    icon: "nlp" },
];

function useUtc() {
  const [t, setT] = useState<Date | null>(null);
  useEffect(() => { setT(new Date()); const id = setInterval(() => setT(new Date()), 1000); return () => clearInterval(id); }, []);
  if (!t) return { time: "--:--:--", date: "-- --- ----", iso: "" };
  const HH = String(t.getUTCHours()).padStart(2, "0");
  const MM = String(t.getUTCMinutes()).padStart(2, "0");
  const SS = String(t.getUTCSeconds()).padStart(2, "0");
  const day = String(t.getUTCDate()).padStart(2, "0");
  const mon = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"][t.getUTCMonth()];
  return { time: `${HH}:${MM}:${SS}`, date: `${day} ${mon} ${t.getUTCFullYear()}`, iso: `${t.getUTCFullYear()}-${String(t.getUTCMonth()+1).padStart(2,"0")}-${day} ${HH}:${MM}` };
}

export function TerminalShell({ children }: { children: React.ReactNode }) {
  const path = useRouterState({ select: s => s.location.pathname });
  const navigate = useNavigate();
  const { time, date } = useUtc();
  const [command, setCommand] = useState("");

  const pageTitle =
    path === "/" ? { eyebrow: "NATIONAL PORT RADAR", chip: "AI SATELLITE PROXY MODE" } :
    path.startsWith("/port") ? { eyebrow: "PORT OPERATIONS COCKPIT · CHENNAI", chip: "LIVE OPS" } :
    path.startsWith("/sim")  ? { eyebrow: "AI DECISION ROOM · MODEL INTELLIGENCE", chip: "WHAT-IF · WHY · WHAT TO DO" } :
    path.startsWith("/fleet")? { eyebrow: "FLEET BOARD", chip: "AIS + SAR FUSED" } :
    path.startsWith("/model")? { eyebrow: "MODEL INTELLIGENCE", chip: "TFT-HSMM v4.2" } :
    path.startsWith("/wx")   ? { eyebrow: "WEATHER INTELLIGENCE", chip: "IMD · INCOIS · ECMWF" } :
    path.startsWith("/sar")  ? { eyebrow: "SAR / AIS PROXY", chip: "SENTINEL-1 · S1-IW" } :
    { eyebrow: "NEWS / NLP INTELLIGENCE", chip: "BACKEND NEWS CACHE" };

  const runCommand = (raw: string) => {
    const cleaned = raw.trim().replace(/\s+/g, " ").toUpperCase();
    if (!cleaned) return;
    if (cleaned === "RADAR") {
      void navigate({ to: "/" });
      return;
    }
    if (cleaned === "FLEET") {
      void navigate({ to: "/fleet" });
      return;
    }
    const [verb, ...rest] = cleaned.split(" ");
    const target = rest.join(" ");
    if (verb === "PORT") {
      void navigate({ to: "/port", search: { port: getPort(target || "CHENNAI").code } });
      return;
    }
    if (verb === "WX") {
      void navigate({ to: "/wx", search: { port: getPort(target || "CHENNAI").code } });
      return;
    }
    if (verb === "SAR") {
      void navigate({ to: "/sar", search: { port: getPort(target || "CHENNAI").code } });
      return;
    }
    if (verb === "NLP") {
      void navigate({ to: "/nlp", search: { entity: target || "HORMUZ" } });
      return;
    }
    if (verb === "MODEL") {
      void navigate({ to: "/model", search: { port: getPort(target || "CHENNAI").code } });
      return;
    }
    if (verb === "SIM") {
      const intensityText = rest.at(-1);
      const parsedIntensity = Number(intensityText);
      const scenarioAlias = Number.isFinite(parsedIntensity) ? rest.slice(0, -1).join("_") : rest.join("_");
      void navigate({
        to: "/sim",
        search: {
          scenario: resolveScenarioKey(scenarioAlias || "CYCLONE_EAST"),
          intensity: Number.isFinite(parsedIntensity) ? parsedIntensity : 1.5,
        },
      });
    }
  };

  return (
    <div className="fixed inset-0 flex flex-col text-[12px] bg-[oklch(0.09_0.015_240)]">
      {/* TOP BAR */}
      <header className="h-[60px] shrink-0 flex items-stretch border-b border-[var(--color-line)] bg-[linear-gradient(180deg,oklch(0.16_0.03_240)_0%,oklch(0.12_0.02_240)_100%)]">
        <div className="flex items-center gap-3 px-4 border-r border-[var(--color-line)] w-[220px]">
          <svg width="22" height="22" viewBox="0 0 22 22" className="text-[var(--color-cyan)]"><path d="M11 1 L21 11 L11 21 L1 11 Z M11 6 L16 11 L11 16 L6 11 Z" fill="currentColor" opacity="0.95"/></svg>
          <div className="leading-tight">
            <div className="text-[13px] tracking-[0.14em] font-bold text-[var(--color-cyan)] glow-cyan">INDIA PORTWATCH</div>
            <div className="text-[9px] tracking-[0.28em] text-[var(--color-muted-foreground)]">AI MARITIME COMMAND</div>
          </div>
        </div>

        <div className="flex-1 flex items-center gap-3 px-5">
          <div className="text-[16px] tracking-[0.12em] font-semibold text-[var(--color-foreground)]">{pageTitle.eyebrow}</div>
          <span className="px-2 py-[3px] border border-[var(--color-cyan)]/50 text-[9px] tracking-[0.18em] text-[var(--color-cyan)] bg-[var(--color-cyan)]/5 rounded-sm">{pageTitle.chip}</span>
          <form
            className="ml-auto w-[300px] flex items-center border border-[var(--color-line-strong)] bg-[oklch(0.08_0.02_240_/_0.7)]"
            onSubmit={(event) => {
              event.preventDefault();
              runCommand(command);
              setCommand("");
            }}
          >
            <span className="px-2 text-[var(--color-cyan)] text-[11px]">▸</span>
            <input
              value={command}
              onChange={(event) => setCommand(event.target.value)}
              placeholder="COMMAND"
              list="portwatch-commands"
              className="min-w-0 flex-1 bg-transparent py-1.5 pr-2 text-[10px] tracking-[0.14em] text-[var(--color-foreground)] outline-none placeholder:text-[var(--color-muted-foreground)]"
            />
            <datalist id="portwatch-commands">
              {[
                "RADAR",
                "PORT CHENNAI",
                "WX CHENNAI",
                "SAR CHENNAI",
                "NLP HORMUZ",
                "MODEL CHENNAI",
                "SIM CYCLONE_EAST 1.5",
                "FLEET",
              ].map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </form>
        </div>

        <div className="flex items-stretch">
          <div className="px-4 flex flex-col justify-center border-l border-[var(--color-line)]">
            <div className="text-[9px] tracking-[0.22em] text-[var(--color-muted-foreground)]">MODEL RUN</div>
            <div className="text-[12px] tabular-nums text-[var(--color-foreground)]">{date} · <span className="text-[var(--color-cyan)]">{time.slice(0,5)} UTC</span></div>
          </div>
          <button className="px-4 my-2 mr-2 border border-[var(--color-mint)]/50 bg-[var(--color-mint)]/5 text-[10px] tracking-[0.18em] text-[var(--color-mint)] flex items-center gap-2 rounded-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-mint)] animate-blink" /> LIVE MODEL OUTPUTS
          </button>
          <div className="px-4 flex flex-col justify-center border-l border-[var(--color-line)] min-w-[180px]">
            <div className="text-[9px] tracking-[0.22em] text-[var(--color-muted-foreground)]">VIEW</div>
            <div className="text-[12px] text-[var(--color-foreground)] flex items-center justify-between gap-2">NATIONAL OVERVIEW <span className="text-[var(--color-cyan)]">▾</span></div>
          </div>
        </div>
      </header>

      {/* MID */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        {/* LEFT RAIL */}
        <nav className="w-[172px] shrink-0 border-r border-[var(--color-line)] bg-[oklch(0.13_0.025_240)] flex flex-col">
          <div className="flex-1">
            {RAIL.map(r => {
              const active = (r.to === "/" && path === "/") || (r.to !== "/" && path.startsWith(r.to));
              return (
                <Link key={r.key} to={r.to} className={cn(
                  "relative flex items-center gap-3 px-4 py-2.5 border-b border-[var(--color-line)]/40 transition-colors text-[11px] tracking-[0.06em]",
                  active
                    ? "bg-[linear-gradient(90deg,oklch(0.82_0.18_195_/_0.10)_0%,transparent_100%)] text-[var(--color-cyan)]"
                    : "text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)] hover:bg-[oklch(0.18_0.03_240)]"
                )}>
                  {active && <span className="absolute left-0 top-0 bottom-0 w-[2px] bg-[var(--color-cyan)] shadow-[0_0_8px_var(--color-cyan)]" />}
                  <RailIcon k={r.icon} />
                  <span className="font-medium">{r.key}</span>
                </Link>
              );
            })}
          </div>

          {/* Weather overlay control */}
          <div className="border-t border-[var(--color-line)] p-3 text-[10px] space-y-2">
            <div className="label-xs">WEATHER OVERLAY</div>
            <button className="w-full flex items-center justify-between border border-[var(--color-line-strong)] px-2 py-1.5 text-[var(--color-foreground)]">
              Wind + Precipitation <span className="text-[var(--color-cyan)]">▾</span>
            </button>
            <div className="space-y-1 text-[9px] text-[var(--color-muted-foreground)]">
              <div className="flex items-center gap-1.5"><span className="w-3 border-t border-dashed border-[var(--color-cyan)]" /> Monsoon Trough</div>
              <div className="flex items-center gap-1.5"><span className="text-[var(--color-cyan)]">→</span> Wind Direction (10m)</div>
            </div>
            <div>
              <div className="text-[9px] tracking-widest text-[var(--color-muted-foreground)] mb-1">Precipitation</div>
              <div className="h-1.5 rounded-sm" style={{ background: "linear-gradient(90deg, oklch(0.35 0.10 260), oklch(0.55 0.18 200), oklch(0.72 0.20 145), oklch(0.82 0.18 75), oklch(0.68 0.24 25))" }} />
              <div className="flex justify-between text-[8px] text-[var(--color-muted-foreground)] mt-0.5"><span>Light</span><span>Heavy</span></div>
            </div>
            <div>
              <div className="text-[9px] tracking-widest text-[var(--color-muted-foreground)] mb-1">Cyclone Activity</div>
              <div className="flex justify-between text-[9px]">
                <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-[var(--color-red)] animate-blink" />Active</span>
                <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-[var(--color-amber)]" />Watch</span>
              </div>
            </div>
            <div className="text-[9px] text-[var(--color-muted-foreground)] pt-1 border-t border-[var(--color-line)]/60">Last Updated: <span className="tabular-nums text-[var(--color-cyan)]">{time}Z</span></div>
          </div>
        </nav>

        {/* MAIN */}
        <main className="flex-1 min-w-0 min-h-0 overflow-hidden">{children}</main>
      </div>

    </div>
  );
}

function RailIcon({ k }: { k: string }) {
  const p = { width: 15, height: 15, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.5 } as const;
  switch (k) {
    case "radar": return <svg {...p}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><line x1="12" y1="12" x2="20" y2="6"/></svg>;
    case "port":  return <svg {...p}><path d="M3 20h18M6 20V10h12v10M9 10V6h6v4M12 3v3"/></svg>;
    case "sim":   return <svg {...p}><path d="M4 5h16v11H8l-4 4V5z"/><path d="M8 10h6M8 13h4"/></svg>;
    case "fleet": return <svg {...p}><path d="M3 17l9-11 9 11M5 20h14"/></svg>;
    case "model": return <svg {...p}><circle cx="6" cy="6" r="1.6"/><circle cx="18" cy="6" r="1.6"/><circle cx="6" cy="18" r="1.6"/><circle cx="18" cy="18" r="1.6"/><circle cx="12" cy="12" r="2"/><path d="M8 6l3 5M16 6l-3 5M8 18l3-5M16 18l-3-5"/></svg>;
    case "wx":    return <svg {...p}><path d="M4 15a5 5 0 019.5-1.5A4 4 0 1117 20H7a4 4 0 01-3-5z"/></svg>;
    case "sar":   return <svg {...p}><path d="M3 12h18M12 3v18M5 5l14 14M19 5L5 19"/></svg>;
    case "nlp":   return <svg {...p}><path d="M4 5h16v11H8l-4 4V5z"/></svg>;
    default: return null;
  }
}
