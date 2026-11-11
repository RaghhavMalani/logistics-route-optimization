import { BrandMark } from "@/components/miniature/BrandMark";
import ports from "@/components/miniature/ports.generated.json";
import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { lazy, Suspense, useState, type FormEvent } from "react";

import { AUTH_MODE, DEMO_ROSTER } from "@/auth/adapters";
import { useAuth } from "@/auth/AuthProvider";
import { PublicOnly } from "@/auth/guards";
import { ROLE_PROFILE, ROLES, isRoleAllowed, type Role } from "@/auth/types";
import { Button } from "@/components/kit/layout";
import { Pill } from "@/components/kit/primitives";
import { useHealth } from "@/services/hooks";
import { cn } from "@/lib/utils";
import { useSourceHealth, ageLabel } from "@/services/source-health";
import { writeStory } from "@/services/story-session";

/** `next` is optional: a direct visit to /login carries no return address. */
interface LoginSearch {
  next?: string;
}

export const Route = createFileRoute("/login")({
  head: () => ({ meta: [{ title: "PortWatch X — Sign in" }] }),
  validateSearch: (search: Record<string, unknown>): LoginSearch =>
    typeof search.next === "string" ? { next: search.next } : {},
  component: () => (
    <PublicOnly>
      <LoginScreen />
    </PublicOnly>
  ),
});

const LoginMiniature = lazy(
  () => import("@/components/miniature/LoginMiniature"),
);

const demoRoles = {
  SHIPPING_COMPANY: ["Company", "Choose how the fleet responds."],
  VESSEL_OPERATOR: ["Vessel", "Review the passage from the bridge."],
  PORT_AUTHORITY: ["Port", "Review arrivals and issue advice."],
  NATIONAL_ADMIN: ["Admin", "See conditions across the network."],
} as const;

function LoginScreen() {
  const { signIn, startDemo, mode, adapterDescription } = useAuth();
  const navigate = useNavigate();
  const search = Route.useSearch();
  const health = useHealth();

  const [email, setEmail] = useState(
    mode === "demo" ? "admin@portwatch.demo" : "",
  );
  const [password, setPassword] = useState(mode === "demo" ? "portwatch" : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await signIn({ email, password });
      const target =
        search.next && isRoleAllowed(session.user.role, search.next)
          ? search.next
          : ROLE_PROFILE[session.user.role].home;
      await navigate({ to: target });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  };

  const openDemo = async (role: Role, story = false) => {
    setBusy(true);
    setError(null);
    try {
      const session = await startDemo(role);
      writeStory(
        story && session.demoId
          ? {
              step: 0,
              reached: 0,
              demoId: session.demoId,
              requestId: crypto.randomUUID(),
            }
          : null,
      );
      await navigate({ to: ROLE_PROFILE[session.user.role].home });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Demo could not open.");
    } finally {
      setBusy(false);
    }
  };

  const serviceTone = health.isError
    ? "crit"
    : health.isLoading
      ? "neutral"
      : "ok";
  const serviceLabel = health.isError
    ? "Unreachable"
    : health.isLoading
      ? "Checking"
      : "Reachable";

  const forecast = health.isError ? undefined : health.data;
  const sourceHealth = useSourceHealth();
  const originAt = Date.parse(forecast?.forecastOrigin ?? "");
  const originStatus = {
    LIVE: "Current",
    CACHED_LIVE: "Cached",
    STALE: "Stale",
    SYNTHETIC: "Synthetic",
    UNAVAILABLE: "Unavailable",
  }[forecast?.forecastOriginStatus ?? "UNAVAILABLE"];
  const targets = {
    CURRENT_HORIZON: "Current horizon",
    PARTIAL_HORIZON: "Partial horizon",
    EXPIRED: "Expired",
    UNAVAILABLE: "Unavailable",
  }[forecast?.targetStatus ?? "UNAVAILABLE"];

  return (
    <div className="fixed inset-0 grid grid-cols-1 bg-[var(--bg)] lg:grid-cols-[1fr_minmax(420px,520px)]">
      {/* ------------------------------------------------------------ left -- */}
      <section className="relative hidden overflow-hidden border-r border-[var(--line)] lg:block">
        <Suspense fallback={null}>
          <LoginMiniature />
        </Suspense>
        <div className="relative flex h-full flex-col justify-between p-10">
          <div>
            <BrandMark />
          </div>

          <div className="max-w-[410px] self-start border border-[var(--line)] bg-[var(--map-overlay)] p-5 shadow-[var(--shadow-floating)]">
            <p className="text-[17px] leading-snug text-[var(--text)]">
              Maritime decisions for Indian ports.
            </p>
            <p className="mt-2.5 text-[12.5px] leading-relaxed text-[var(--text-3)]">
              Compare passage, berth and cargo plans with source-linked weather,
              port activity and maritime intelligence. Data availability varies
              by source.
            </p>
          </div>

          <div />
        </div>
      </section>

      {/* ----------------------------------------------------------- right -- */}
      <section className="flex min-h-0 flex-col overflow-auto border-l border-[var(--line)] bg-[var(--panel)] px-6 py-8 lg:px-12">
        <div className="m-auto w-full max-w-[380px]">
          <div className="mb-6 lg:hidden">
            <BrandMark />
          </div>

          <h1 className="text-balance text-4xl font-semibold leading-[1.05] tracking-tight text-[var(--text)]">
            Follow a voyage through PortWatch
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-[var(--text-3)]">
            See how a fictional shipping company, port and vessel agree on a
            passage plan.
          </p>
          <Button
            variant="primary"
            className="mt-5 w-full justify-center py-3.5 text-base"
            disabled={busy}
            onClick={() => void openDemo("SHIPPING_COMPANY", true)}
          >
            Start the 3-minute demo
          </Button>
          {error ? (
            <p role="alert" className="mt-3 text-sm text-[var(--crit)]">
              {error}
            </p>
          ) : null}

          <div className="mt-5 border-y border-[var(--line)] py-4">
            <div className="eyebrow mb-2">Explore a role in the demo</div>
            <div className="grid grid-cols-2 gap-2">
              {ROLES.map((role) => (
                <button
                  key={role}
                  type="button"
                  aria-label={`${demoRoles[role][0]} demo`}
                  disabled={busy}
                  onClick={() => void openDemo(role)}
                  className="border border-[var(--line)] bg-[var(--bg)] px-3 py-2.5 text-left transition-colors hover:border-[var(--signal)] focus-visible:outline-[var(--signal)] disabled:opacity-60"
                >
                  <span className="block text-sm font-semibold">
                    {demoRoles[role][0]}
                  </span>
                  <span className="mt-0.5 block text-xs leading-snug text-[var(--text-3)]">
                    {demoRoles[role][1]}
                  </span>
                </button>
              ))}
            </div>
            <p className="mt-2 text-[10.5px] text-[var(--text-3)]">
              Your own sandbox, with the original maps and workflows.
            </p>
          </div>
          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-medium">
              Operator access
            </summary>
            <form className="mt-4 flex flex-col gap-3.5" onSubmit={submit}>
              <label className="flex flex-col gap-1.5">
                <span className="eyebrow">Email</span>
                <input
                  type="email"
                  required
                  autoComplete="username"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className={cn(
                    "rounded-[2px] border border-[var(--line-strong)] bg-[var(--panel-2)] px-2.5 py-2",
                    "text-[13px] text-[var(--text)] outline-none placeholder:text-[var(--text-3)]",
                    "focus:border-[var(--info)]",
                  )}
                  placeholder="name@authority.gov.in"
                />
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="eyebrow">Password</span>
                <input
                  type="password"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className={cn(
                    "rounded-[2px] border border-[var(--line-strong)] bg-[var(--panel-2)] px-2.5 py-2",
                    "text-[13px] text-[var(--text)] outline-none focus:border-[var(--info)]",
                  )}
                  placeholder="••••••••"
                />
              </label>

              <Button
                type="submit"
                variant="primary"
                disabled={busy}
                className="mt-1 py-2"
              >
                {busy ? "Signing in…" : "Sign in"}
              </Button>
            </form>

            {mode === "demo" ? (
              <div className="mt-6 border-t border-[var(--line)] pt-4">
                <div className="mb-2 flex items-center gap-2">
                  <Pill tone="unc">Demo environment</Pill>
                  <span className="text-[10.5px] text-[var(--text-3)]">
                    password: portwatch
                  </span>
                </div>
                <div className="flex flex-col divide-y divide-[var(--line)]/70 overflow-hidden rounded-[2px] border border-[var(--line)]">
                  {DEMO_ROSTER.map((account) => (
                    <button
                      key={account.email}
                      type="button"
                      onClick={() => {
                        setEmail(account.email);
                        setPassword("portwatch");
                        setError(null);
                      }}
                      className="flex items-center justify-between gap-3 px-2.5 py-2 text-left transition-colors hover:bg-[var(--panel-2)]"
                    >
                      <span className="min-w-0">
                        <span className="num block truncate text-[11.5px] text-[var(--text-2)]">
                          {account.email}
                        </span>
                        <span className="block truncate text-[10.5px] text-[var(--text-3)]">
                          {account.label}
                        </span>
                      </span>
                      <span className="shrink-0 text-[10px] uppercase tracking-[0.08em] text-[var(--text-3)]">
                        {ROLE_PROFILE[account.role].label}
                      </span>
                    </button>
                  ))}
                </div>
                <p className="mt-2 text-[10.5px] leading-snug text-[var(--text-3)]">
                  {adapterDescription} Set{" "}
                  <code className="font-mono text-[10px] text-[var(--text-2)]">
                    VITE_PORTWATCH_AUTH_MODE=production
                  </code>{" "}
                  to require a real identity provider.
                </p>
              </div>
            ) : null}
          </details>

          {/* ----------------------------------------------- system footer -- */}
          <Link
            to="/tour"
            className="mt-5 inline-block text-[12px] text-[var(--text-2)] underline underline-offset-4"
          >
            Take the tour →
          </Link>
          <details className="mt-5 border-t border-[var(--line)] pt-3.5">
            <summary className="flex cursor-pointer flex-wrap items-center gap-x-2 gap-y-1 text-xs">
              <strong>Live status</strong>
              <span className="inline-flex items-center gap-1">
                <span
                  aria-hidden
                  className={cn(
                    "size-1.5 rounded-full",
                    serviceTone === "ok"
                      ? "bg-emerald-700"
                      : serviceTone === "crit"
                        ? "bg-red-700"
                        : "bg-neutral-400",
                  )}
                />
                <span className="sr-only">Data service</span>
                <span>{serviceLabel}</span>
              </span>
              <span
                className="inline-flex items-center gap-1"
                data-testid="login-source-freshness"
              >
                <span
                  aria-hidden
                  className={cn(
                    "size-1.5 rounded-full",
                    sourceHealth.data
                      ? sourceHealth.data.degraded
                        ? "bg-amber-600"
                        : "bg-emerald-700"
                      : "bg-neutral-400",
                  )}
                />
                <span>
                  {sourceHealth.data
                    ? sourceHealth.data.degraded
                      ? "Degraded · latest available data"
                      : "Core sources within policy"
                    : "Unmeasured"}
                </span>
              </span>
              <span aria-hidden className="text-[var(--text-3)]">
                ▾
              </span>
            </summary>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[11px]">
              <dt className="text-[var(--text-3)]">Twin state</dt>
              <dd className="num text-right text-[var(--text-2)]">
                {health.data?.intelligence ?? "—"}
              </dd>
              <dt className="text-[var(--text-3)]">Forecast origin</dt>
              <dd className="num text-right text-[var(--text-2)]">
                {Number.isFinite(originAt)
                  ? `${originStatus === "Stale" ? "Latest available · " : ""}${new Date(originAt).toISOString().slice(0, 16).replace("T", " ")}Z · ${originStatus ?? "Unknown"} (${ageLabel(forecast?.forecastOriginAgeHours == null ? null : forecast.forecastOriginAgeHours * 3600)} old)`
                  : "Unavailable"}
              </dd>
              <dt className="text-[var(--text-3)]">Forecast targets</dt>
              <dd className="num text-right text-[var(--text-2)]">
                {targets}
                {forecast?.targetThrough && targets !== "Unavailable"
                  ? ` · through ${forecast.targetThrough}`
                  : ""}
              </dd>
              <dt className="text-[var(--text-3)]">Port coverage</dt>
              <dd className="num text-right text-[var(--text-2)]">
                {ports.length} registered
                {forecast?.ports != null
                  ? ` · ${forecast.ports} in forecast export`
                  : ""}
              </dd>
              <dt className="text-[var(--text-3)]">Model</dt>
              <dd className="num text-right text-[var(--text-2)]">
                {health.data?.model ?? "—"}
              </dd>
              <dt className="text-[var(--text-3)]">Auth mode</dt>
              <dd className="num text-right text-[var(--text-2)]">
                {AUTH_MODE}
              </dd>
            </dl>
          </details>
        </div>
      </section>
    </div>
  );
}
