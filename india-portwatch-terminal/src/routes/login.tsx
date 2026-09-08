import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";

import { AUTH_MODE, DEMO_ROSTER } from "@/auth/adapters";
import { useAuth } from "@/auth/AuthProvider";
import { PublicOnly } from "@/auth/guards";
import { ROLE_PROFILE, isRoleAllowed } from "@/auth/types";
import { Button } from "@/components/kit/layout";
import { Pill, formatUtc } from "@/components/kit/primitives";
import { useHealth } from "@/services/hooks";
import { cn } from "@/lib/utils";

/** `next` is optional: a direct visit to /login carries no return address. */
interface LoginSearch {
  next?: string;
}

export const Route = createFileRoute("/login")({
  validateSearch: (search: Record<string, unknown>): LoginSearch =>
    typeof search.next === "string" ? { next: search.next } : {},
  component: () => (
    <PublicOnly>
      <LoginScreen />
    </PublicOnly>
  ),
});

/**
 * A chart plate rather than an illustration: graticule, rhumb lines from a
 * compass rose, depth-contour furniture. It carries no measurement and claims
 * none -- it reads as the back of a navigation chart, which is the point.
 */
function ChartPlate() {
  const rhumb = Array.from({ length: 16 }, (_, i) => (i * 360) / 16);
  return (
    <svg
      viewBox="0 0 600 600"
      className="absolute inset-0 h-full w-full"
      aria-hidden
      preserveAspectRatio="xMidYMid slice"
    >
      <defs>
        <radialGradient id="plate-vignette" cx="42%" cy="38%" r="72%">
          <stop offset="0%" stopColor="#0d1c26" />
          <stop offset="100%" stopColor="#060e14" />
        </radialGradient>
      </defs>
      <rect width="600" height="600" fill="url(#plate-vignette)" />

      {Array.from({ length: 13 }, (_, i) => i * 50).map((v) => (
        <g key={v} stroke="#162a36" strokeWidth="0.6">
          <line x1={v} y1="0" x2={v} y2="600" />
          <line x1="0" y1={v} x2="600" y2={v} />
        </g>
      ))}

      {rhumb.map((angle) => {
        const rad = (angle * Math.PI) / 180;
        return (
          <line
            key={angle}
            x1={260}
            y1={300}
            x2={260 + Math.cos(rad) * 640}
            y2={300 + Math.sin(rad) * 640}
            stroke="#18303e"
            strokeWidth={angle % 90 === 0 ? 0.9 : 0.5}
          />
        );
      })}

      {[70, 130, 200, 280].map((r) => (
        <circle
          key={r}
          cx={260}
          cy={300}
          r={r}
          fill="none"
          stroke="#173040"
          strokeWidth="0.6"
          strokeDasharray={r % 2 === 0 ? "3 5" : undefined}
        />
      ))}

      <circle cx={260} cy={300} r={3} fill="#2b6a86" />
      <circle cx={260} cy={300} r={9} fill="none" stroke="#2b6a86" strokeWidth="0.9" />

      {/* Depth-contour motif — chart furniture, carrying no measurement. */}
      {[0, 1, 2].map((index) => (
        <path
          key={index}
          d={`M -20 ${430 + index * 54} C 120 ${390 + index * 54}, 220 ${470 + index * 54}, 340 ${412 + index * 54} S 540 ${360 + index * 54}, 640 ${400 + index * 54}`}
          fill="none"
          stroke="#152c39"
          strokeWidth="0.8"
        />
      ))}

    </svg>
  );
}

function LoginScreen() {
  const { signIn, mode, adapterDescription } = useAuth();
  const navigate = useNavigate();
  const search = Route.useSearch();
  const health = useHealth();

  const [email, setEmail] = useState(mode === "demo" ? "admin@portwatch.demo" : "");
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

  const serviceTone = health.isError ? "crit" : health.isLoading ? "neutral" : "ok";
  const serviceLabel = health.isError
    ? "Unreachable"
    : health.isLoading
      ? "Checking"
      : "Reachable";

  return (
    <div className="fixed inset-0 grid grid-cols-1 bg-[var(--bg)] lg:grid-cols-[1fr_minmax(420px,520px)]">
      {/* ------------------------------------------------------------ left -- */}
      <section className="relative hidden overflow-hidden border-r border-[var(--line)] lg:block">
        <ChartPlate />
        <div className="relative flex h-full flex-col justify-between p-10">
          <div className="flex items-center gap-3">
            <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden>
              <path d="M12 2 L21 12 L12 22 L3 12 Z" fill="none" stroke="var(--info)" strokeWidth="1.4" />
              <path d="M12 7.5 L16.5 12 L12 16.5 L7.5 12 Z" fill="var(--info)" opacity="0.85" />
            </svg>
            <span className="text-[15px] font-semibold tracking-[0.08em] text-[var(--text)]">
              INDIA PORTWATCH
            </span>
          </div>

          <div className="max-w-[430px]">
            <p className="text-[17px] leading-snug text-[var(--text)]">
              Predictive maritime operations intelligence for Indian ports.
            </p>
            <p className="mt-2.5 text-[12.5px] leading-relaxed text-[var(--text-3)]">
              Satellite-AIS port activity, marine weather and maritime events, resolved
              into a ten-day forecast with calibrated uncertainty and a bounded
              operational instruction per port.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[10.5px] uppercase tracking-[0.1em] text-[var(--text-3)]">
            <span>{health.data?.ports ?? "—"} ports</span>
            <span>{health.data?.horizonDays ?? "—"}-day horizon</span>
            <span>q10 / q50 / q90</span>
            <span>Walk-forward validated</span>
          </div>
        </div>
      </section>

      {/* ----------------------------------------------------------- right -- */}
      <section className="flex min-h-0 flex-col justify-center overflow-auto border-l border-[var(--line)] bg-[var(--panel)] px-8 py-10 lg:px-14">
        <div className="mx-auto w-full max-w-[380px]">
          <div className="lg:hidden">
            <div className="mb-6 flex items-center gap-2.5">
              <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden>
                <path d="M12 2 L21 12 L12 22 L3 12 Z" fill="none" stroke="var(--info)" strokeWidth="1.4" />
                <path d="M12 7.5 L16.5 12 L12 16.5 L7.5 12 Z" fill="var(--info)" opacity="0.85" />
              </svg>
              <span className="text-[13px] font-semibold tracking-[0.07em]">INDIA PORTWATCH</span>
            </div>
          </div>

          <h1 className="text-[15px] font-semibold text-[var(--text)]">Secure sign-in</h1>
          <p className="mt-1 text-[12px] text-[var(--text-3)]">
            Operations terminal · access is scoped to your role.
          </p>

          <form className="mt-6 flex flex-col gap-3.5" onSubmit={submit}>
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

            <Button type="submit" variant="primary" disabled={busy} className="mt-1 py-2">
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          {mode === "demo" ? (
            <div className="mt-6 border-t border-[var(--line)] pt-4">
              <div className="mb-2 flex items-center gap-2">
                <Pill tone="unc">Demo environment</Pill>
                <span className="text-[10.5px] text-[var(--text-3)]">password: portwatch</span>
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
                {formatUtc(health.data?.forecastOrigin ?? null)}
              </dd>
              <dt className="text-[var(--text-3)]">Model</dt>
              <dd className="num text-right text-[var(--text-2)]">
                {health.data?.model ?? "—"}
              </dd>
              <dt className="text-[var(--text-3)]">Auth mode</dt>
              <dd className="num text-right text-[var(--text-2)]">{AUTH_MODE}</dd>
            </dl>
          </div>
        </div>
      </section>
    </div>
  );
}
