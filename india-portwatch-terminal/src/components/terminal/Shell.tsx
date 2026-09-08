import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Chip, ProvenanceChip, formatUtc } from "./ui";
import { cn } from "@/lib/utils";
import { fetchHealth } from "@/services/portwatch";
import { resolveScenarioKey } from "@/lib/scenario-keys";

const RAIL = [
  { key: "Port Radar", to: "/", icon: "radar" },
  { key: "Port Cockpit", to: "/port", icon: "port" },
  { key: "Decision Room", to: "/sim", icon: "sim" },
  { key: "Fleet Board", to: "/fleet", icon: "fleet" },
  { key: "Model Intel", to: "/model", icon: "model" },
  { key: "Weather Intel", to: "/wx", icon: "wx" },
  { key: "Vessel Activity", to: "/sar", icon: "sar" },
  { key: "Events / NLP", to: "/nlp", icon: "nlp" },
];

const PAGE_TITLES: Array<[string, string]> = [
  ["/port", "PORT OPERATIONS COCKPIT"],
  ["/sim", "DECISION ROOM"],
  ["/fleet", "FLEET BOARD"],
  ["/model", "MODEL INTELLIGENCE"],
  ["/wx", "WEATHER INTELLIGENCE"],
  ["/sar", "VESSEL ACTIVITY"],
  ["/nlp", "EVENT INTELLIGENCE"],
];

function useUtcClock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  if (!now) return "--:--:--";
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())}`;
}

export function TerminalShell({ children }: { children: React.ReactNode }) {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const navigate = useNavigate();
  const clock = useUtcClock();
  const [command, setCommand] = useState("");

  // The header reports the model run, not the wall clock: the two are
  // different numbers and conflating them is how a demo starts lying.
  const health = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    staleTime: 20_000,
    refetchInterval: 60_000,
    retry: 1,
  });

  const title =
    PAGE_TITLES.find(([prefix]) => path.startsWith(prefix))?.[1] ??
    "NATIONAL PORT RADAR";

  const runCommand = (raw: string) => {
    const cleaned = raw.trim().replace(/\s+/g, " ").toUpperCase();
    if (!cleaned) return;
    const [verb, ...rest] = cleaned.split(" ");
    const target = rest.join(" ");

    switch (verb) {
      case "RADAR":
        void navigate({ to: "/" });
        return;
      case "FLEET":
        void navigate({ to: "/fleet" });
        return;
      case "PORT":
        void navigate({ to: "/port", search: { port: target || "INMAA" } });
        return;
      case "WX":
        void navigate({ to: "/wx", search: { port: target || "INMAA" } });
        return;
      case "SAR":
        void navigate({ to: "/sar", search: { port: target || "INMAA" } });
        return;
      case "NLP":
        void navigate({ to: "/nlp", search: { entity: target || "HORMUZ" } });
        return;
      case "MODEL":
        void navigate({ to: "/model", search: { port: target || "INMAA" } });
        return;
      case "SIM": {
        const maybeIntensity = Number(rest.at(-1));
        const hasIntensity = Number.isFinite(maybeIntensity);
        const alias = (hasIntensity ? rest.slice(0, -1) : rest).join("_");
        void navigate({
          to: "/sim",
          search: {
            scenario: resolveScenarioKey(alias || "HORMUZ"),
            intensity: hasIntensity ? maybeIntensity : 1,
          },
        });
        return;
      }
      default:
        return;
    }
  };

  const data = health.data;
  const intelligenceTone =
    data?.intelligence === "live"
      ? "mint"
      : data?.intelligence === "cached"
        ? "cyan"
        : data?.intelligence === "stale"
          ? "amber"
          : "red";

  return (
    <div className="fixed inset-0 flex flex-col text-[12px] bg-[oklch(0.09_0.015_240)]">
      <header className="h-[54px] shrink-0 flex items-stretch border-b border-[var(--color-line)] bg-[linear-gradient(180deg,oklch(0.16_0.03_240)_0%,oklch(0.12_0.02_240)_100%)]">
        <div className="flex items-center gap-3 px-4 border-r border-[var(--color-line)] w-[206px]">
          <svg width="20" height="20" viewBox="0 0 22 22" className="text-[var(--color-cyan)]">
            <path
              d="M11 1 L21 11 L11 21 L1 11 Z M11 6 L16 11 L11 16 L6 11 Z"
              fill="currentColor"
              opacity="0.95"
            />
          </svg>
          <div className="leading-tight min-w-0">
            <div className="text-[12px] tracking-[0.14em] font-bold text-[var(--color-cyan)]">
              INDIA PORTWATCH
            </div>
            <div className="text-[8px] tracking-[0.24em] text-[var(--color-muted-foreground)]">
              MARITIME DIGITAL TWIN
            </div>
          </div>
        </div>

        <div className="flex-1 flex items-center gap-3 px-4 min-w-0">
          <div className="text-[14px] tracking-[0.12em] font-semibold text-[var(--color-foreground)] truncate">
            {title}
          </div>
          <form
            className="ml-auto w-[264px] flex items-center border border-[var(--color-line-strong)] bg-[oklch(0.08_0.02_240_/_0.7)] shrink-0"
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
              aria-label="Terminal command"
              className="min-w-0 flex-1 bg-transparent py-1.5 pr-2 text-[10px] tracking-[0.14em] text-[var(--color-foreground)] outline-none placeholder:text-[var(--color-muted-foreground)]"
            />
            <datalist id="portwatch-commands">
              {[
                "RADAR",
                "PORT INMAA",
                "MODEL INNSA",
                "WX INMUN",
                "SAR INMAA",
                "NLP HORMUZ",
                "SIM HORMUZ 1.5",
                "FLEET",
              ].map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </form>
        </div>

        <div className="flex items-stretch">
          <div className="px-4 flex flex-col justify-center border-l border-[var(--color-line)] min-w-[190px]">
            <div className="text-[8px] tracking-[0.22em] text-[var(--color-muted-foreground)]">
              LAST MODEL RUN
            </div>
            <div className="text-[11px] tabular-nums text-[var(--color-foreground)]">
              {formatUtc(data?.lastRefreshUtc ?? null)}
              <span className="text-[var(--color-muted-foreground)]">
                {" "}
                · now {clock}Z
              </span>
            </div>
          </div>
          <div className="px-4 flex flex-col justify-center border-l border-[var(--color-line)] min-w-[168px] gap-1">
            <div className="text-[8px] tracking-[0.22em] text-[var(--color-muted-foreground)]">
              INTELLIGENCE STATE
            </div>
            <div className="flex items-center gap-1.5">
              {health.isError ? (
                <Chip tone="red">API DOWN</Chip>
              ) : (
                <>
                  <Chip tone={intelligenceTone}>
                    {(data?.intelligence ?? "loading").toUpperCase()}
                  </Chip>
                  <ProvenanceChip
                    status={data?.forecastOriginStatus ?? null}
                    ageHours={data?.forecastOriginAgeHours ?? null}
                    detail={`Forecast origin ${formatUtc(data?.forecastOrigin ?? null)}`}
                  />
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 min-h-0 flex overflow-hidden">
        <nav className="w-[164px] shrink-0 border-r border-[var(--color-line)] bg-[oklch(0.13_0.025_240)] flex flex-col">
          <div className="flex-1">
            {RAIL.map((item) => {
              const active =
                (item.to === "/" && path === "/") ||
                (item.to !== "/" && path.startsWith(item.to));
              return (
                <Link
                  key={item.key}
                  to={item.to}
                  className={cn(
                    "relative flex items-center gap-2.5 px-3 py-2.5 border-b border-[var(--color-line)]/40 transition-colors text-[11px] tracking-[0.05em]",
                    active
                      ? "bg-[linear-gradient(90deg,oklch(0.82_0.18_195_/_0.10)_0%,transparent_100%)] text-[var(--color-cyan)]"
                      : "text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)] hover:bg-[oklch(0.18_0.03_240)]",
                  )}
                >
                  {active && (
                    <span className="absolute left-0 top-0 bottom-0 w-[2px] bg-[var(--color-cyan)]" />
                  )}
                  <RailIcon k={item.icon} />
                  <span className="font-medium truncate">{item.key}</span>
                </Link>
              );
            })}
          </div>

          {/* Source readiness lives in the rail so it is visible on every
              screen, not only on the radar. */}
          <div className="border-t border-[var(--color-line)] p-3 space-y-2">
            <div className="label-xs">DATA SOURCES</div>
            {health.isError && (
              <div className="text-[9px] text-[var(--color-red)] leading-snug">
                Backend unreachable. Start it with
                <code className="block mt-1 text-[8px] text-[var(--color-muted-foreground)]">
                  uvicorn backend.app.main:app
                </code>
              </div>
            )}
            {data && (
              <>
                <div className="flex items-baseline justify-between text-[9px]">
                  <span className="text-[var(--color-muted-foreground)]">
                    Readiness
                  </span>
                  <span className="tabular-nums text-[var(--color-cyan)]">
                    {(data.sources.readiness * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="h-1 w-full rounded-sm bg-[var(--color-panel-2)] overflow-hidden">
                  <div
                    className="h-full bg-[var(--color-cyan)]"
                    style={{ width: `${data.sources.readiness * 100}%` }}
                  />
                </div>
                <div className="space-y-1 text-[8px] text-[var(--color-muted-foreground)]">
                  {(
                    [
                      ["LIVE", data.sources.live.length, "mint"],
                      ["CACHED", data.sources.cached.length, "cyan"],
                      ["STALE", data.sources.stale.length, "amber"],
                      ["SYNTHETIC", data.sources.synthetic.length, "purple"],
                      ["MISSING", data.sources.unavailable.length, "red"],
                    ] as const
                  ).map(([label, count, tone]) => (
                    <div key={label} className="flex items-center justify-between">
                      <span
                        className="tracking-[0.14em]"
                        style={{ color: `var(--color-${tone})` }}
                      >
                        {label}
                      </span>
                      <span className="tabular-nums">{count}</span>
                    </div>
                  ))}
                </div>
                <Link
                  to="/model"
                  search={{ port: "INMAA" }}
                  className="block text-[9px] text-[var(--color-cyan)] hover:underline pt-1 border-t border-[var(--color-line)]/60"
                >
                  Full provenance →
                </Link>
              </>
            )}
          </div>
        </nav>

        <main className="flex-1 min-w-0 min-h-0 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}

function RailIcon({ k }: { k: string }) {
  const p = {
    width: 14,
    height: 14,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
  } as const;
  switch (k) {
    case "radar":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="9" />
          <circle cx="12" cy="12" r="5" />
          <line x1="12" y1="12" x2="20" y2="6" />
        </svg>
      );
    case "port":
      return (
        <svg {...p}>
          <path d="M3 20h18M6 20V10h12v10M9 10V6h6v4M12 3v3" />
        </svg>
      );
    case "sim":
      return (
        <svg {...p}>
          <path d="M4 5h16v11H8l-4 4V5z" />
          <path d="M8 10h6M8 13h4" />
        </svg>
      );
    case "fleet":
      return (
        <svg {...p}>
          <path d="M3 17l9-11 9 11M5 20h14" />
        </svg>
      );
    case "model":
      return (
        <svg {...p}>
          <circle cx="6" cy="6" r="1.6" />
          <circle cx="18" cy="6" r="1.6" />
          <circle cx="6" cy="18" r="1.6" />
          <circle cx="18" cy="18" r="1.6" />
          <circle cx="12" cy="12" r="2" />
          <path d="M8 6l3 5M16 6l-3 5M8 18l3-5M16 18l-3-5" />
        </svg>
      );
    case "wx":
      return (
        <svg {...p}>
          <path d="M4 15a5 5 0 019.5-1.5A4 4 0 1117 20H7a4 4 0 01-3-5z" />
        </svg>
      );
    case "sar":
      return (
        <svg {...p}>
          <path d="M3 12h18M12 3v18M5 5l14 14M19 5L5 19" />
        </svg>
      );
    case "nlp":
      return (
        <svg {...p}>
          <path d="M4 5h16v11H8l-4 4V5z" />
        </svg>
      );
    default:
      return null;
  }
}
