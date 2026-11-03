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

  const openDemo = async (role: Role) => {
    setBusy(true);
    setError(null);
    try {
      const session = await startDemo(role);
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
  const originAt = Date.parse(forecast?.forecastOrigin ?? "");
  const originStatus = {
    LIVE: "Current", CACHED_LIVE: "Cached", STALE: "Stale",
    SYNTHETIC: "Synthetic", UNAVAILABLE: "Unavailable",
  }[forecast?.forecastOriginStatus ?? "UNAVAILABLE"];
  const targets = {
    CURRENT_HORIZON: "Current horizon", PARTIAL_HORIZON: "Partial horizon",
    EXPIRED: "Expired", UNAVAILABLE: "Unavailable",
  }[forecast?.targetStatus ?? "UNAVAILABLE"];

  return (
    <div className="fixed inset-0 grid grid-cols-1 bg-[var(--bg)] lg:grid-cols-[1fr_minmax(420px,520px)]">
      {/* ------------------------------------------------------------ left -- */}
      <section className="relative hidden overflow-hidden border-r border-[var(--line)] lg:block">
        <Suspense fallback={null}>
          <LoginMiniature />
        </Suspense>
        <div className="relative flex h-full flex-col justify-between p-10">
          <div><BrandMark /></div>

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
      <section className="flex min-h-0 flex-col overflow-auto border-l border-[var(--line)] bg-[var(--panel)] px-8 py-10 lg:px-14">
        <div className="m-auto w-full max-w-[380px]">
          <div className="mb-6 lg:hidden"><BrandMark /></div>

          <h1 className="text-[15px] font-semibold text-[var(--text)]">
            Secure sign-in
          </h1>
          <p className="mt-1 text-[12px] text-[var(--text-3)]">
            Operations terminal · access is scoped to your role.
          </p>

          <div className="mt-4 border-y border-[var(--line)] py-3">
            <div className="eyebrow mb-2">Explore a fictional demo</div>
            <div className="grid grid-cols-2 gap-2">
              {ROLES.map((role) => (
                <Button
                  key={role}
                  disabled={busy}
                  onClick={() => void openDemo(role)}
                >
                  {
                    {
                      SHIPPING_COMPANY: "Company",
                      VESSEL_OPERATOR: "Vessel",
                      PORT_AUTHORITY: "Port",
                      NATIONAL_ADMIN: "Admin",
                    }[role]
                  }{" "}
                  demo
                </Button>
              ))}
            </div>
            <p className="mt-2 text-[10.5px] text-[var(--text-3)]">
              Your own sandbox, with the original maps and workflows.
            </p>
          </div>
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

            {error ? (
              <div className="rounded-[2px] border border-[var(--crit)]/40 bg-[var(--crit-dim)] px-2.5 py-2 text-[11.5px] leading-snug text-[var(--crit)]">
                {error}
              </div>
            ) : null}

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

          {/* ----------------------------------------------- system footer -- */}
          <Link
            to="/tour"
            className="mt-5 inline-block text-[12px] text-[var(--text-2)] underline underline-offset-4"
          >
            Take the tour →
          </Link>
          <div className="mt-7 border-t border-[var(--line)] pt-3.5">
            <div className="eyebrow mb-2">Environment</div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[11px]">
              <dt className="text-[var(--text-3)]">Data service</dt>
              <dd className="flex justify-end">
                <Pill tone={serviceTone}>{serviceLabel}</Pill>
              </dd>
              <dt className="text-[var(--text-3)]">Twin state</dt>
              <dd className="num text-right text-[var(--text-2)]">
                {health.data?.intelligence ?? "—"}
              </dd>
              <dt className="text-[var(--text-3)]">Forecast origin</dt>
              <dd className="num text-right text-[var(--text-2)]">
                {Number.isFinite(originAt)
                  ? `${new Date(originAt).toISOString().slice(0, 16).replace("T", " ")}Z · ${originStatus ?? "Unknown"}`
                  : "Unavailable"}
              </dd>
              <dt className="text-[var(--text-3)]">Forecast targets</dt>
              <dd className="num text-right text-[var(--text-2)]">
                {targets}{forecast?.targetThrough && targets !== "Unavailable" ? ` · through ${forecast.targetThrough}` : ""}
              </dd>
              <dt className="text-[var(--text-3)]">Port coverage</dt>
              <dd className="num text-right text-[var(--text-2)]">
                {ports.length} registered
                {forecast?.ports != null ? ` · ${forecast.ports} in forecast export` : ""}
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
          </div>
        </div>
      </section>
    </div>
  );
}
