import { createFileRoute } from "@tanstack/react-router";

import { useAuth } from "@/auth/AuthProvider";
import { ROLE_PROFILE, ROLES } from "@/auth/types";
import { Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import {
  KeyValue,
  Num,
  Pill,
  ProvenanceTag,
  formatAge,
  formatUtc,
} from "@/components/kit/primitives";
import { FailureState, LoadingPanel } from "@/components/kit/states";
import { API_BASE } from "@/services/api";
import { useBenchmark, useHealth, useProvenance } from "@/services/hooks";

export const Route = createFileRoute("/admin/system")({ component: SystemState });

function SystemState() {
  const health = useHealth();
  const provenance = useProvenance();
  const benchmark = useBenchmark();
  const { mode, adapterDescription, session } = useAuth();

  if (health.isLoading) return <LoadingPanel label="Probing the service" rows={8} />;
  if (health.isError) {
    return (
      <Page>
        <PageHeader title="System" />
        <PageBody>
          <FailureState
            error={health.error}
            retry={() => void health.refetch()}
            lastGood={null}
            hint="uvicorn backend.app.main:app --reload --port 8000"
          />
        </PageBody>
      </Page>
    );
  }

  const data = health.data;
  const artefacts = Object.entries(data?.artefacts ?? {});
  const missing = artefacts.filter(([, present]) => !present);

  return (
    <Page>
      <PageHeader
        title="System"
        context={<span>Service, artefacts and access</span>}
        meta={
          <>
            <span className="num">{data?.service ?? "—"}</span>
            <span className="num">server {formatUtc(data?.serverTimeUtc ?? null)}</span>
          </>
        }
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "Service",
            value: data?.status ?? "unknown",
            tone: data?.status === "ok" ? "ok" : "crit",
            note: API_BASE,
          },
          {
            label: "Twin state",
            value: data?.intelligence ?? "unknown",
            tone:
              data?.intelligence === "live"
                ? "ok"
                : data?.intelligence === "cached"
                  ? "info"
                  : data?.intelligence === "stale"
                    ? "warn"
                    : "crit",
            note:
              data?.cacheAgeSeconds != null
                ? `cache age ${formatAge(data.cacheAgeSeconds / 3600)}`
                : "no cache age reported",
          },
          {
            label: "Artefacts present",
            value: `${artefacts.length - missing.length}/${artefacts.length}`,
            tone: missing.length === 0 ? "ok" : "warn",
            note: missing.length ? missing.map(([name]) => name).join(", ") : "complete",
          },
          {
            label: "Ports covered",
            value: data?.ports ?? "n/a",
            note: `horizon ${data?.horizonDays ?? "n/a"} days`,
          },
          {
            label: "Benchmark",
            value: data?.benchmark.available ? "available" : "missing",
            tone: data?.benchmark.available ? "ok" : "warn",
            note: data?.benchmark.version ?? "run the benchmark to populate it",
          },
          {
            label: "Auth mode",
            value: mode,
            tone: mode === "demo" ? "unc" : "ok",
            note: mode === "demo" ? "published credentials, no security" : "identity provider",
          },
        ]}
      />

      <PageBody className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Panel title="Run">
          <div className="px-3 py-2">
            <KeyValue label="Model" dense>
              <span className="num text-[11.5px]">{data?.model ?? "n/a"}</span>
            </KeyValue>
            <KeyValue label="Forecast origin" dense>
              <span className="num text-[11.5px]">{formatUtc(data?.forecastOrigin ?? null)}</span>
            </KeyValue>
            <KeyValue label="Origin freshness" dense>
              <ProvenanceTag
                status={data?.forecastOriginStatus ?? null}
                ageHours={data?.forecastOriginAgeHours ?? null}
              />
            </KeyValue>
            <KeyValue label="Last model run" dense>
              <span className="num text-[11.5px]">{formatUtc(data?.lastRefreshUtc ?? null)}</span>
            </KeyValue>
            <KeyValue label="Benchmark generated" dense>
              <span className="num text-[11.5px]">
                {formatUtc(data?.benchmark.generatedAt ?? null)}
              </span>
            </KeyValue>
            <KeyValue label="Leading model" dense>
              <span className="num text-[11.5px]">{data?.benchmark.bestModel ?? "n/a"}</span>
            </KeyValue>
            <KeyValue label="Folds" dense>
              <Num value={data?.benchmark.folds ?? null} digits={0} />
            </KeyValue>
            <KeyValue label="Out-of-fold rows" dense>
              <Num value={benchmark.data?.summary?.testRows ?? null} digits={0} />
            </KeyValue>
          </div>
        </Panel>

        <Panel title="Artefacts">
          <div className="px-3 py-2">
            {artefacts.map(([name, present]) => (
              <div
                key={name}
                className="flex items-center justify-between gap-2 border-b border-[var(--line)]/50 py-1.5 last:border-0"
              >
                <span className="num truncate text-[11.5px] text-[var(--text-2)]">{name}</span>
                <Pill tone={present ? "ok" : "crit"}>{present ? "present" : "missing"}</Pill>
              </div>
            ))}
            {missing.length ? (
              <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11px] leading-snug text-[var(--text-3)]">
                Rebuild with{" "}
                <code className="font-mono text-[10.5px] text-[var(--text-2)]">
                  python run_award_demo.py --source portwatch
                </code>
                , then{" "}
                <code className="font-mono text-[10.5px] text-[var(--text-2)]">
                  python -m backend.pipeline.export_award_cache
                </code>
                .
              </p>
            ) : null}
          </div>
        </Panel>

        <div className="flex min-w-0 flex-col gap-3">
          <Panel title="Access">
            <div className="px-3 py-2">
              <KeyValue label="Signed in as" dense>
                <span className="text-[11.5px]">{session?.user.displayName ?? "n/a"}</span>
              </KeyValue>
              <KeyValue label="Role" dense>
                <span className="text-[11.5px]">
                  {session ? ROLE_PROFILE[session.user.role].label : "n/a"}
                </span>
              </KeyValue>
              <KeyValue label="Session issued" dense>
                <span className="num text-[11.5px]">{formatUtc(session?.issuedAt ?? null)}</span>
              </KeyValue>
              <KeyValue label="Session expires" dense>
                <span className="num text-[11.5px]">{formatUtc(session?.expiresAt ?? null)}</span>
              </KeyValue>
              <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11px] leading-snug text-[var(--text-3)]">
                {adapterDescription}
              </p>
            </div>
          </Panel>

          <Panel title="Role scopes">
            <div className="px-3 py-2">
              {ROLES.map((role) => {
                const profile = ROLE_PROFILE[role];
                return (
                  <div
                    key={role}
                    className="border-b border-[var(--line)]/50 py-2 last:border-0"
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-[12px] font-medium text-[var(--text)]">
                        {profile.label}
                      </span>
                      <span className="num text-[10.5px] text-[var(--text-3)]">
                        {profile.scope.join(" ")}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[11px] leading-snug text-[var(--text-3)]">
                      {profile.description}
                    </p>
                  </div>
                );
              })}
            </div>
          </Panel>

          <Panel title="Endpoints">
            <div className="px-3 py-2">
              <KeyValue label="API base" dense>
                <span className="num text-[11px]">{API_BASE}</span>
              </KeyValue>
              <KeyValue label="Sources registered" dense>
                <Num value={Object.keys(provenance.data?.sources ?? {}).length} digits={0} />
              </KeyValue>
              <KeyValue label="Available ports" dense>
                <span className="num text-[11px]">
                  {(data?.availablePorts ?? []).join(" ")}
                </span>
              </KeyValue>
            </div>
          </Panel>
        </div>
      </PageBody>
    </Page>
  );
}
