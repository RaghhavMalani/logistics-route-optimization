/**
 * The freshness coordinator, as a table a person can act on.
 *
 * One row per artefact: the state the coordinator computed from the
 * artefact's own instant, its age, how far its source lags, what its job is
 * doing, and a Refresh control where a job exists. Nobody has to know a
 * pipeline command: the row says the register is EXPIRED and the button
 * asks the coordinator to refresh it, which is the same request the
 * scheduler makes on its own.
 */

import { useAuth } from "@/auth/AuthProvider";
import { Panel } from "@/components/kit/layout";
import { Pill, formatAge, formatUtc } from "@/components/kit/primitives";
import { FailureState, LoadingPanel } from "@/components/kit/states";
import {
  useFreshness,
  useRefreshArtifact,
  type FreshnessArtifact,
} from "@/services/lenses";

const STATE_TONE: Record<
  FreshnessArtifact["state"],
  "ok" | "info" | "warn" | "crit" | "unc" | "neutral"
> = {
  FRESH: "ok",
  DUE: "info",
  EXPIRED: "warn",
  STALE: "crit",
  MISSING: "crit",
  NOT_APPLICABLE: "neutral",
  SIMULATED: "unc",
};

const JOB_TONE: Record<
  FreshnessArtifact["job"]["state"],
  "ok" | "info" | "warn" | "crit" | "neutral"
> = {
  IDLE: "neutral",
  RUNNING: "info",
  RETRY_SCHEDULED: "warn",
  FAILED: "crit",
  DISABLED: "neutral",
};

function ageOf(seconds: number | null): string {
  if (seconds == null) return "never";
  return formatAge(seconds / 3600);
}

export function FreshnessPanel() {
  const { identityHeaders } = useAuth();
  const freshness = useFreshness(identityHeaders);
  const refresh = useRefreshArtifact(identityHeaders);

  if (freshness.isLoading)
    return <LoadingPanel label="Asking the freshness coordinator" rows={6} />;
  if (freshness.isError || !freshness.data) {
    return (
      <Panel title="Freshness">
        <FailureState
          error={freshness.error}
          retry={() => void freshness.refetch()}
          lastGood={null}
          hint="the coordinator answers at /api/admin/freshness for National Command"
        />
      </Panel>
    );
  }
  const data = freshness.data;
  const summary = data.summary;
  return (
    <Panel
      title="Freshness"
      note={
        <span className="flex items-center gap-1.5 text-[10px] text-[var(--text-3)]">
          <Pill tone={data.scheduler.running ? "ok" : "warn"}>
            scheduler {data.scheduler.running ? "running" : "stopped"}
          </Pill>
          <span className="num">
            {summary.FRESH ?? 0} fresh · {summary.EXPIRED ?? 0} expired ·{" "}
            {summary.STALE ?? 0} stale · {summary.MISSING ?? 0} missing
          </span>
        </span>
      }
      testId="freshness-panel"
    >
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[11px]">
          <thead>
            <tr className="border-b border-[var(--line)] text-[10.5px] uppercase tracking-wide text-[var(--text-3)]">
              <th className="px-3 py-1.5 text-left font-medium">Artefact</th>
              <th className="px-2 py-1.5 text-left font-medium">State</th>
              <th className="px-2 py-1.5 text-right font-medium">Age</th>
              <th className="px-2 py-1.5 text-right font-medium">SLA</th>
              <th className="px-2 py-1.5 text-right font-medium">Source lag</th>
              <th className="px-2 py-1.5 text-left font-medium">Job</th>
              <th className="px-2 py-1.5 text-left font-medium">
                Last attempt
              </th>
              <th className="px-3 py-1.5 text-right font-medium" />
            </tr>
          </thead>
          <tbody>
            {data.artifacts.map((row) => {
              const last = row.job.lastResult;
              const canRefresh =
                row.job.refreshable &&
                row.job.state !== "RUNNING" &&
                row.job.state !== "DISABLED";
              return (
                <tr
                  key={row.artifact}
                  className="border-b border-[var(--line)]/60"
                  data-testid="freshness-row"
                  data-artifact={row.artifact}
                  data-state={row.state}
                >
                  <td className="px-3 py-1.5">
                    <span className="block text-[var(--text)]">
                      {row.label}
                    </span>
                    <span className="block text-[10.5px] text-[var(--text-3)]">
                      {row.provider}
                      {row.reason && row.state !== "FRESH"
                        ? ` · ${row.reason}`
                        : ""}
                    </span>
                  </td>
                  <td className="px-2 py-1.5">
                    <Pill tone={STATE_TONE[row.state]}>
                      {row.state.replace("_", " ")}
                    </Pill>
                  </td>
                  <td className="num px-2 py-1.5 text-right text-[var(--text)]">
                    {ageOf(row.ageSeconds)}
                  </td>
                  <td className="num px-2 py-1.5 text-right text-[var(--text-3)]">
                    {formatAge(row.policy.freshForSeconds / 3600)}
                  </td>
                  <td className="num px-2 py-1.5 text-right text-[var(--text-3)]">
                    {row.sourceLagSeconds == null
                      ? "—"
                      : ageOf(row.sourceLagSeconds)}
                  </td>
                  <td className="px-2 py-1.5">
                    {row.job.refreshable ? (
                      <span className="flex items-center gap-1">
                        <Pill tone={JOB_TONE[row.job.state]}>
                          {row.job.state.replace("_", " ").toLowerCase()}
                        </Pill>
                        {row.job.eligibility && row.job.state === "DISABLED" ? (
                          <span
                            className="max-w-[220px] truncate text-[10.5px] text-[var(--text-3)]"
                            title={row.job.eligibility}
                          >
                            {row.job.eligibility}
                          </span>
                        ) : null}
                      </span>
                    ) : (
                      <span className="text-[10.5px] text-[var(--text-3)]">
                        derived · never scheduled
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-1.5 text-[10.5px] text-[var(--text-3)]">
                    {last ? (
                      <span
                        className={last.ok ? "" : "text-[var(--crit)]"}
                        title={last.error ?? JSON.stringify(last.detail)}
                      >
                        {formatUtc(last.finishedAt)} ·{" "}
                        {last.ok
                          ? last.changed
                            ? "changed"
                            : "no change"
                          : "failed"}
                        {last.error ? ` · ${last.error}` : ""}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {row.job.refreshable ? (
                      <button
                        type="button"
                        data-testid="freshness-refresh"
                        disabled={!canRefresh || refresh.isPending}
                        onClick={() => refresh.mutate(row.artifact)}
                        className="rounded border border-[var(--line)] px-2 py-0.5 text-[10px] text-[var(--text-2)] hover:text-[var(--text)] disabled:opacity-40"
                      >
                        Refresh now
                      </button>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="px-3 py-1.5 text-[10.5px] text-[var(--text-3)]">
        Ages are the artefacts' own recorded instants measured on the wall; a
        failed refresh leaves the last known good in place and its age
        untouched. Coordinator read {formatUtc(data.at)}.
      </p>
    </Panel>
  );
}
