/**
 * Signal health: what every source is actually doing, in one strip.
 *
 * This is a trust surface rather than a dashboard, and the difference matters.
 * A dashboard invites you to look at it; this exists so that the question "is
 * what I am looking at current?" has an answer within one glance and one click,
 * at any moment, without leaving the world.
 *
 * The number shown is the *reading's* age, not the age of the request that
 * fetched it. Those differ by hours for an artefact-backed source, and the
 * second one is always small and always meaningless -- a forecast issued this
 * morning and read a second ago is hours old, and a strip that said "1s" would
 * be worse than showing nothing.
 *
 * Expanding a row shows the licence and what the source is missing. That is the
 * differentiator: most products can tell you a feed is down, and very few can
 * tell you whether you are allowed to sell what it produced.
 */

import { useState } from "react";

import { Pill, type Tone } from "@/components/kit/primitives";
import { cn } from "@/lib/utils";
import { useSignalHealth } from "@/services/os-hooks";
import type { SignalHealthRow } from "@/types/portwatch-os";

const FRESHNESS_TONE: Record<string, Tone> = {
  LIVE: "ok",
  CACHED: "info",
  STALE: "warn",
  EXPIRED: "warn",
  // Not knowing how old something is is a different state from knowing it is
  // old, and it is deliberately not coloured as if it were fine.
  UNKNOWN: "unc",
  UNAVAILABLE: "neutral",
};

/** An age an operator reads at a glance: "4s", "6m", "2h", "13d". */
export function formatAge(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86_400)}d`;
}

export function SignalHealth({ mode = "DEMO" }: { mode?: string }) {
  const health = useSignalHealth(mode);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  if (health.isLoading || !health.data) {
    return (
      <div
        data-testid="signal-health"
        className="pointer-events-auto rounded border border-[var(--line)] bg-[var(--surface)]/92 px-2 py-1 backdrop-blur"
      >
        <span className="text-[9px] uppercase tracking-wide text-[var(--text-3)]">
          Signals…
        </span>
      </div>
    );
  }

  const { signals, traffic, unwired } = health.data;
  const worst = signals.find((s) => s.freshness === "STALE" || s.freshness === "UNKNOWN");

  if (!open) {
    return (
      <button
        type="button"
        data-testid="signal-health"
        data-worst={worst?.freshness ?? "OK"}
        onClick={() => setOpen(true)}
        className={cn(
          "pointer-events-auto flex items-center gap-1.5 rounded border border-[var(--line)]",
          "bg-[var(--surface)]/92 px-2 py-1 backdrop-blur transition-colors",
          "hover:border-[var(--text-3)]",
        )}
      >
        <span className="text-[9px] uppercase tracking-wide text-[var(--text-3)]">
          Signals
        </span>
        {signals.slice(0, 4).map((signal) => (
          <span key={signal.capability} className="flex items-center gap-0.5">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{
                background:
                  signal.freshness === "LIVE"
                    ? "var(--ok)"
                    : signal.freshness === "CACHED"
                      ? "var(--info)"
                      : signal.freshness === "UNAVAILABLE"
                        ? "var(--text-3)"
                        : "var(--warn)",
              }}
            />
            <span className="num text-[9px] text-[var(--text-3)]">
              {signal.capability.slice(0, 3)}
            </span>
          </span>
        ))}
      </button>
    );
  }

  return (
    <div
      data-testid="signal-health-panel"
      className="pointer-events-auto w-[330px] rounded border border-[var(--line)] bg-[var(--surface)]/95 backdrop-blur"
    >
      <div className="flex items-center gap-2 border-b border-[var(--line)] px-2 py-1.5">
        <span className="text-[9px] uppercase tracking-wide text-[var(--text-3)]">
          Signal health
        </span>
        <Pill tone="neutral">{health.data.mode}</Pill>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Close"
          className="ml-auto text-[10px] text-[var(--text-3)] hover:text-[var(--text)]"
        >
          ✕
        </button>
      </div>

      {/* Traffic is called out on its own: it is the claim most likely to be
          misread, and the one a buyer asks about first. */}
      <div className="border-b border-[var(--line)] px-2 py-1.5" data-testid="traffic-mode">
        <div className="flex items-center gap-1.5">
          <span className="num min-w-[64px] text-[10px] text-[var(--text-2)]">
            TRAFFIC
          </span>
          <Pill tone={traffic.mode === "LIVE_AIS" ? "ok" : "neutral"}>
            {traffic.mode}
          </Pill>
        </div>
        <p className="mt-1 text-[9px] leading-relaxed text-[var(--text-3)]">
          {traffic.statement}
        </p>
      </div>

      <div>
        {signals.map((signal) => (
          <SignalRow
            key={signal.capability}
            signal={signal}
            expanded={expanded === signal.capability}
            onToggle={() =>
              setExpanded(expanded === signal.capability ? null : signal.capability)
            }
          />
        ))}
      </div>

      {unwired.length ? (
        <p className="border-t border-[var(--line)] px-2 py-1.5 text-[9px] leading-relaxed text-[var(--text-3)]">
          Not wired in this build: {unwired.join(", ")}. Registered with a licence
          and a status, and read by nothing yet.
        </p>
      ) : null}
    </div>
  );
}

function SignalRow({
  signal,
  expanded,
  onToggle,
}: {
  signal: SignalHealthRow;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className="border-b border-[var(--line)] last:border-b-0"
      data-testid="signal-row"
      data-capability={signal.capability}
      data-freshness={signal.freshness}
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-1.5 px-2 py-1.5 text-left hover:bg-[var(--surface-2)]"
      >
        <span className="num min-w-[64px] text-[10px] uppercase text-[var(--text-2)]">
          {signal.capability}
        </span>
        <Pill tone={FRESHNESS_TONE[signal.freshness] ?? "neutral"}>
          {signal.freshness}
        </Pill>
        <span className="num ml-auto text-[9.5px] text-[var(--text-3)]">
          {formatAge(signal.ageSeconds)}
        </span>
      </button>

      {expanded ? (
        <div className="px-2 pb-2 pt-0.5" data-testid="signal-evidence">
          <p className="text-[9.5px] text-[var(--text-2)]">{signal.providerName}</p>
          {signal.availability.reason ? (
            <p className="mt-0.5 text-[9px] leading-relaxed text-[var(--text-3)]">
              {signal.availability.reason}
            </p>
          ) : null}
          {signal.availability.needs.length ? (
            <ul className="mt-1">
              {signal.availability.needs.map((need) => (
                <li key={need} className="text-[9px] text-[var(--text-3)]">
                  needs · {need}
                </li>
              ))}
            </ul>
          ) : null}
          {signal.quality?.reasons.length ? (
            <ul className="mt-1">
              {signal.quality.reasons.map((reason) => (
                <li key={reason} className="text-[9px] text-[var(--warn)]">
                  {reason}
                </li>
              ))}
            </ul>
          ) : null}
          <p className="mt-1 text-[9px] text-[var(--text-3)]">
            {signal.commercialUse === null
              ? "licence unknown"
              : signal.commercialUse
                ? "commercial use permitted"
                : "non-commercial licence"}
            {signal.attributionRequired ? " · attribution required" : ""}
          </p>
        </div>
      ) : null}
    </div>
  );
}
