/**
 * Signal health: what every source is actually doing, in one strip.
 *
 * This is a trust surface rather than a dashboard, and the difference matters.
 * A dashboard invites you to look at it; this exists so that the question "is
 * what I am looking at current?" has an answer within one glance and one click,
 * at any moment, without leaving the world.
 *
 * Every row answers the same seven questions in the same order -- MODE,
 * STATUS, LAST OBSERVATION, AGE, COVERAGE, PRODUCT, LICENCE STATE -- because a
 * reader who has learned to read one row can read them all, and because a
 * source that cannot answer one of them should visibly fail to, not skip it.
 *
 * The age shown is the *reading's* age, not the age of the request that
 * fetched it. Those differ by hours for an artefact-backed source, and the
 * second one is always small and always meaningless -- a forecast issued this
 * morning and read a second ago is hours old, and a strip that said "1s" would
 * be worse than showing nothing.
 *
 * The licence state is four-valued and drawn that way. ALLOWED and PROHIBITED
 * are what the terms say; REQUIRES_REVIEW is "nobody has verified this" and is
 * not coloured as if it were permission, because a permission nobody has
 * verified is not a permission.
 */

import { useState } from "react";

import { Pill, type Tone } from "@/components/kit/primitives";
import {
  TRAFFIC_TONE,
  formatAge,
  formatInstant,
} from "@/components/fabric/signal-format";
import { cn } from "@/lib/utils";
import { requestSignalRefresh, useSignalHealth } from "@/services/os-hooks";
import type {
  LicenceState,
  SignalHealthRow,
  TrafficMode,
} from "@/types/portwatch-os";

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

const STATUS_TONE: Record<string, Tone> = {
  AVAILABLE: "ok",
  CONFIGURABLE: "unc",
  PLANNED: "neutral",
  UNAVAILABLE: "warn",
};

const LICENCE_TONE: Record<LicenceState, Tone> = {
  ALLOWED: "ok",
  PROHIBITED: "crit",
  REQUIRES_REVIEW: "unc",
  UNKNOWN: "neutral",
};

const LICENCE_LABEL: Record<LicenceState, string> = {
  ALLOWED: "allowed",
  PROHIBITED: "prohibited",
  REQUIRES_REVIEW: "requires review",
  UNKNOWN: "unknown",
};

function LicenceChip({
  state,
  label,
}: {
  state: LicenceState | null;
  label: string;
}) {
  const tone = state ? LICENCE_TONE[state] : "neutral";
  return (
    <span
      className="flex items-center gap-1"
      data-testid={`licence-${label.toLowerCase()}`}
      data-state={state ?? "NONE"}
    >
      <span className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
        {label}
      </span>
      <Pill tone={tone}>{state ? LICENCE_LABEL[state] : "n/a"}</Pill>
    </span>
  );
}

function Field({
  label,
  children,
  testId,
}: {
  label: string;
  children: React.ReactNode;
  testId?: string;
}) {
  return (
    <div className="flex items-baseline gap-1.5" data-testid={testId}>
      <span className="w-[92px] shrink-0 text-[10px] uppercase tracking-wide text-[var(--text-3)]">
        {label}
      </span>
      <span className="num text-[10.5px] text-[var(--text-2)]">{children}</span>
    </div>
  );
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
        <span className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
          Signals…
        </span>
      </div>
    );
  }

  const { signals, traffic, unwired } = health.data;
  const worst = signals.find(
    (s) => s.freshness === "STALE" || s.freshness === "UNKNOWN",
  );

  if (!open) {
    return (
      <button
        type="button"
        data-testid="signal-health"
        data-worst={worst?.freshness ?? "OK"}
        data-traffic={traffic.mode}
        onClick={() => setOpen(true)}
        className={cn(
          "pointer-events-auto flex items-center gap-1.5 rounded border border-[var(--line)]",
          "bg-[var(--surface)]/92 px-2 py-1 backdrop-blur transition-colors",
          "hover:border-[var(--text-3)]",
        )}
      >
        <span className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
          Signals
        </span>
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{
            background: `var(--${TRAFFIC_TONE[traffic.mode] === "neutral" ? "text-3" : TRAFFIC_TONE[traffic.mode]})`,
          }}
        />
        <span className="num text-[10px] text-[var(--text-3)]">ais</span>
        {signals
          .filter((signal) => signal.capability !== "ais")
          .slice(0, 4)
          .map((signal) => (
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
              <span className="num text-[10px] text-[var(--text-3)]">
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
      className="pointer-events-auto w-[360px] rounded border border-[var(--line)] bg-[var(--surface)]/95 backdrop-blur"
    >
      <div className="flex items-center gap-2 border-b border-[var(--line)] px-2 py-1.5">
        <span className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
          Signal health
        </span>
        <Pill tone="neutral">{health.data.mode}</Pill>
        <button
          type="button"
          onClick={requestSignalRefresh}
          data-testid="signal-refresh"
          className="ml-auto text-[10px] uppercase tracking-wide text-[var(--text-3)] hover:text-[var(--text)]"
        >
          refresh
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Close"
          className="text-[10px] text-[var(--text-3)] hover:text-[var(--text)]"
        >
          ✕
        </button>
      </div>

      <TrafficBlock traffic={traffic} />

      <div className="max-h-[52vh] overflow-y-auto">
        {signals.map((signal) => (
          <SignalRow
            key={signal.capability}
            signal={signal}
            expanded={expanded === signal.capability}
            onToggle={() =>
              setExpanded(
                expanded === signal.capability ? null : signal.capability,
              )
            }
          />
        ))}
      </div>

      {unwired.length ? (
        <p className="border-t border-[var(--line)] px-2 py-1.5 text-[10px] leading-relaxed text-[var(--text-3)]">
          Not wired in this build: {unwired.join(", ")}. Registered with a
          licence and a status, and read by nothing yet.
        </p>
      ) : null}
    </div>
  );
}

/**
 * Traffic is called out on its own: it is the claim most likely to be misread,
 * and the one a buyer asks about first. The mode is the *picture*; the health
 * beneath it is the *pipe*, and the two are shown apart so that "connected and
 * receiving nothing" cannot be read as live.
 */
function TrafficBlock({ traffic }: { traffic: TrafficMode }) {
  const health = traffic.health;
  const lastGood = health?.lastGoodObservationAt ?? null;
  return (
    <div
      className="border-b border-[var(--line)] px-2 py-1.5"
      data-testid="traffic-mode"
      data-mode={traffic.mode}
      data-socket={health?.health ?? "NONE"}
    >
      <div className="flex items-center gap-1.5">
        <span className="num min-w-[64px] text-[10px] text-[var(--text-2)]">
          TRAFFIC
        </span>
        <Pill tone={TRAFFIC_TONE[traffic.mode]}>{traffic.mode}</Pill>
        {health ? (
          <Pill
            tone={
              health.health === "LIVE"
                ? "ok"
                : health.health === "AUTH_FAILED"
                  ? "crit"
                  : "neutral"
            }
          >
            socket {health.health}
          </Pill>
        ) : null}
      </div>
      <p className="mt-1 text-[10px] leading-relaxed text-[var(--text-3)]">
        {traffic.statement}
      </p>
      <div className="mt-1 space-y-0.5">
        <Field label="Mode">{traffic.mode}</Field>
        <Field label="Status">{traffic.availability.status}</Field>
        <Field label="Last observation" testId="traffic-last-observation">
          {formatInstant(lastGood)}
        </Field>
        <Field label="Age" testId="traffic-age">
          {formatAge(health?.lastGoodAgeSeconds ?? null)}
        </Field>
        <Field label="Coverage">{health?.coverage ?? "—"}</Field>
        <Field label="Product">{traffic.providerId ?? "none"}</Field>
        {traffic.vessels ? (
          <Field label="Vessels" testId="traffic-vessels">
            {traffic.vessels.live} live · {traffic.vessels.stale} stale
            {health ? ` · ${health.messagesConsumed} consumed` : ""}
          </Field>
        ) : null}
        {health?.lastError ? (
          <p className="text-[10px] leading-relaxed text-[var(--warn)]">
            {health.lastError}
          </p>
        ) : null}
      </div>
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
      data-product={signal.productId ?? ""}
      data-commercial={signal.commercialUse ?? "NONE"}
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
        <span className="truncate text-[10px] text-[var(--text-3)]">
          {signal.productName ?? signal.providerName}
        </span>
        <span className="num ml-auto text-[10.5px] text-[var(--text-3)]">
          {formatAge(signal.ageSeconds)}
        </span>
      </button>

      {expanded ? (
        <div
          className="space-y-0.5 px-2 pb-2 pt-0.5"
          data-testid="signal-evidence"
        >
          <Field label="Mode">{signal.licenceMode}</Field>
          <Field label="Status">
            <Pill tone={STATUS_TONE[signal.availability.status] ?? "neutral"}>
              {signal.availability.status}
            </Pill>
          </Field>
          <Field label="Last observation">
            {signal.ageSeconds === null
              ? "none"
              : formatInstant(
                  new Date(Date.now() - signal.ageSeconds * 1000).toISOString(),
                )}
          </Field>
          <Field label="Age">
            {formatAge(signal.ageSeconds)}
            {signal.freshness === "UNKNOWN" ? " (source time unknown)" : ""}
          </Field>
          <Field label="Coverage">{signal.coverage}</Field>
          <Field label="Product" testId="signal-product">
            {signal.productName ?? "—"}
            <span className="text-[var(--text-3)]">
              {" "}
              · {signal.providerName}
            </span>
          </Field>
          <div
            className="flex items-baseline gap-1.5"
            data-testid="signal-licence"
          >
            <span className="w-[92px] shrink-0 text-[10px] uppercase tracking-wide text-[var(--text-3)]">
              Licence state
            </span>
            <span className="flex flex-wrap items-center gap-2">
              <LicenceChip state={signal.commercialUse} label="Commercial" />
              <LicenceChip state={signal.governmentUse} label="Government" />
            </span>
          </div>
          {signal.attributionRequired ? (
            <p className="pl-[98px] text-[10px] text-[var(--text-3)]">
              attribution required
            </p>
          ) : null}
          {signal.termsUrl ? (
            <p className="pl-[98px] text-[10px] text-[var(--text-3)]">
              terms reviewed {signal.termsReviewedAt ?? "—"} ·{" "}
              <a
                href={signal.termsUrl}
                target="_blank"
                rel="noreferrer"
                className="underline decoration-dotted hover:text-[var(--text)]"
              >
                source
              </a>
            </p>
          ) : (
            <p className="pl-[98px] text-[10px] text-[var(--text-3)]">
              no published terms found
              {signal.termsReviewedAt
                ? ` (checked ${signal.termsReviewedAt})`
                : ""}
            </p>
          )}

          {signal.availability.reason ? (
            <p className="mt-1 text-[10px] leading-relaxed text-[var(--text-3)]">
              {signal.availability.reason}
            </p>
          ) : null}
          {signal.availability.needs.length ? (
            <ul className="mt-1">
              {signal.availability.needs.map((need) => (
                <li key={need} className="text-[10px] text-[var(--text-3)]">
                  needs · {need}
                </li>
              ))}
            </ul>
          ) : null}
          {signal.quality?.reasons.length ? (
            <ul className="mt-1">
              {signal.quality.reasons.map((reason) => (
                <li key={reason} className="text-[10px] text-[var(--warn)]">
                  {reason}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
