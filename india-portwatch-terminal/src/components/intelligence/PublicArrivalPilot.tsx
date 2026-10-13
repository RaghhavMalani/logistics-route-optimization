import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { Panel } from "@/components/kit/layout";
import { getBlob, getJson, postJson } from "@/services/api";
import { useWorldClock } from "@/services/lenses";
import type { PublicWorkspace } from "@/services/public-arrivals";

const button =
  "rounded border border-[var(--line)] px-3 py-1.5 text-xs disabled:opacity-40";
const time = (value: string | null) =>
  value
    ? new Date(value).toISOString().replace("T", " ").replace(".000Z", " UTC")
    : "Unavailable";
const hours = (value: number | null | undefined) =>
  value == null ? "Unavailable" : `${value.toFixed(2)} h`;
function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function PublicArrivalPilot({ portCode }: { portCode: string }) {
  const { session } = useAuth();
  const clock = useWorldClock();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<unknown>(null);
  const [cohortId, setCohortId] = useState("");
  const verified = session?.mode === "production";
  const allowed =
    session?.user.role === "NATIONAL_ADMIN" ||
    (session?.user.role === "PORT_AUTHORITY" &&
      session.user.portCode === portCode);
  const live = clock.data?.mode === "LIVE";
  const suffix = `?portCode=${encodeURIComponent(portCode)}`;
  const query = useQuery({
    queryKey: [
      "public-arrivals",
      portCode,
      session?.user.id,
      clock.data?.mode,
      clock.data?.anchor,
    ],
    queryFn: ({ signal }) =>
      getJson<PublicWorkspace>(
        `/public-arrivals/workspace${suffix}`,
        {},
        { signal },
      ),
    enabled: verified && allowed && !!clock.data,
    refetchInterval: 60_000,
  });
  const state = query.data;
  const cohort =
    state?.cohorts.find((c) => c.cohortId === cohortId) ??
    state?.cohorts.filter((c) => c.status === "CLOSED").at(-1) ??
    state?.cohorts.at(-1);
  const sealedEvaluation = state?.benchmarks
    .filter((r) => r.cohortId === cohort?.cohortId)
    .at(-1);
  const visibleEvaluation =
    evaluation &&
    typeof evaluation === "object" &&
    "at" in evaluation &&
    "portCode" in evaluation &&
    evaluation.portCode === portCode &&
    "cohortId" in evaluation &&
    evaluation.cohortId === (cohort?.cohortId ?? null) &&
    state &&
    Date.parse(String(evaluation.at)) <= Date.parse(state.asOf)
      ? evaluation
      : null;
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Public pilot request failed");
    } finally {
      setBusy(false);
    }
  }
  const pdf = (id: string) =>
    action(async () =>
      download(
        await getBlob(`/public-arrivals/evidence/${id}${suffix}`),
        `${portCode}-${id.slice(0, 16)}.pdf`,
      ),
    );
  const sourceAge = state?.freshness.lastCollectionAt
    ? (Date.parse(state.asOf) - Date.parse(state.freshness.lastCollectionAt)) /
      3_600_000
    : null;
  return (
    <Panel title="Public arrival pilot" data-testid="public-arrival-pilot">
      <div className="space-y-4 p-3 text-xs">
        <p>
          Published ETA → reported arrival → reported berth. Public berth
          records are distinct from confirmed all-fast; published ETAs are
          distinct from scheduler waiting estimates.
        </p>
        {!verified || !allowed ? (
          <p>
            Sign in with this port’s verified authority or national command.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap gap-2">
              <button
                className={button}
                disabled={!live || busy}
                onClick={() =>
                  void action(async () => {
                    const result = await postJson<{ errors: string[] }>(
                      `/public-arrivals/refresh${suffix}`,
                      {},
                      {},
                      { timeoutMs: 180_000 },
                    );
                    await query.refetch();
                    if (result.errors.length)
                      setError(result.errors.join("; "));
                  })
                }
              >
                {busy ? "Working…" : "Refresh official reports"}
              </button>
              <button
                className={button}
                disabled={!state || busy}
                onClick={() =>
                  void action(async () => {
                    const data = await getJson<PublicWorkspace>(
                      `/public-arrivals/dataset${suffix}`,
                    );
                    download(
                      new Blob([JSON.stringify(data, null, 2)], {
                        type: "application/json",
                      }),
                      `${portCode}-public-pilot.json`,
                    );
                  })
                }
              >
                Export public dataset
              </button>
              <button
                className={button}
                disabled={!live || busy || !state}
                onClick={() =>
                  void action(async () => {
                    setEvaluation(
                      await postJson(
                        `/public-arrivals/evaluate${suffix}${cohort ? `&cohortId=${encodeURIComponent(cohort.cohortId)}` : ""}`,
                        {},
                      ),
                    );
                    await query.refetch();
                  })
                }
              >
                Evaluate chronological baselines
              </button>
              <button
                className={button}
                disabled={
                  !live ||
                  busy ||
                  !state ||
                  state.cohorts.some((c) => c.status === "ENROLLING")
                }
                onClick={() =>
                  void action(async () => {
                    const created = await postJson<{ cohortId: string }>(
                      `/public-arrivals/cohorts${suffix}`,
                      { enrollmentDays: 30 },
                    );
                    setCohortId(created.cohortId);
                    setEvaluation(null);
                    await query.refetch();
                  })
                }
              >
                Start 30-day cohort
              </button>
            </div>
            {!live && (
              <p>
                Replay: collection and evaluation writes are disabled. Evidence
                is filtered by its first collection time.
              </p>
            )}
            {(error || query.error) && (
              <p role="alert">{error ?? query.error?.message}</p>
            )}
            {query.isLoading && <p>Loading public evidence…</p>}
            {state && (
              <>
                <p>
                  {state.timezoneNote}. Converted timestamps below are UTC; raw
                  publisher strings remain in the dataset and evidence.
                </p>
                <p>
                  Source freshness:{" "}
                  {sourceAge == null
                    ? "Not collected"
                    : `${sourceAge.toFixed(1)} h since changed document collected${sourceAge > 36 ? " — STALE" : ""}`}
                  . Latest report:{" "}
                  {state.freshness.latestReportDate ?? "Unavailable"}. Last
                  check: {time(state.freshness.lastCheckAt)}.
                </p>
                <div
                  className="space-y-1 border border-[var(--line)] p-3"
                  data-testid="public-pilot-collection"
                >
                  <p>
                    Backend collection:{" "}
                    {state.collection.schedulerRunning === null
                      ? "Replay view"
                      : state.collection.schedulerRunning
                        ? "Scheduler running"
                        : "Scheduler stopped"}{" "}
                    ·{" "}
                    {state.collection.backendJob?.job.state ??
                      "Status unavailable"}
                    .
                  </p>
                  <p>
                    Last successful collection:{" "}
                    {time(state.collection.lastSuccessfulCollectionAt)} · Next
                    attempt:{" "}
                    {time(
                      state.collection.backendJob?.job.nextAttemptAt ??
                        state.collection.backendJob?.expiresAt ??
                        null,
                    )}
                    . Collection runs every three hours while the backend is
                    running.
                  </p>
                  {state.collection.backendJob?.job.eligibility && (
                    <p>{state.collection.backendJob.job.eligibility}</p>
                  )}
                  {((state.collection.lastRun?.errors.length ?? 0) > 0 ||
                    (state.freshness.lastCheck?.errors.length ?? 0) > 0) && (
                    <p role="alert" data-testid="public-collection-errors">
                      Collection failed:{" "}
                      {(state.collection.lastRun?.errors.length
                        ? state.collection.lastRun.errors
                        : (state.freshness.lastCheck?.errors ?? [])
                      ).join("; ")}
                      . Archived evidence and frozen cases remain available.
                    </p>
                  )}
                </div>
                <div
                  className="flex flex-wrap gap-x-6 gap-y-2"
                  data-testid="public-pilot-counts"
                >
                  {Object.entries(state.counts).map(([key, value]) => (
                    <span key={key}>
                      {key}: <strong>{value}</strong>
                    </span>
                  ))}
                </div>
                <p>
                  {state.evaluationReason}. No measured operational accuracy or
                  savings are established.
                </p>
                <div
                  className="space-y-2 border border-[var(--line)] p-3"
                  data-testid="public-pilot-cohort"
                >
                  <label className="flex flex-wrap items-center gap-2">
                    Evaluation cohort
                    <select
                      className="rounded border border-[var(--line)] bg-[var(--panel)] p-1"
                      value={cohort?.cohortId ?? ""}
                      onChange={(e) => {
                        setCohortId(e.target.value);
                        setEvaluation(null);
                      }}
                      disabled={!state.cohorts.length || busy}
                    >
                      {!state.cohorts.length && (
                        <option value="">No cohort defined</option>
                      )}
                      {state.cohorts.map((c) => (
                        <option key={c.cohortId} value={c.cohortId}>
                          {c.cohortId.slice(0, 8)} · {c.status} ·{" "}
                          {c.caseIds.length} enrolled
                        </option>
                      ))}
                    </select>
                  </label>
                  {cohort && (
                    <p>
                      Enrollment: {time(cohort.enrollmentStartAt)} through{" "}
                      {time(cohort.enrollmentEndAt)} (exclusive cutoff). Defined
                      by {cohort.createdBy} at {time(cohort.createdAt)}.{" "}
                      {cohort.caseIds.length} cases · {cohort.protocol}.
                    </p>
                  )}
                  <p>
                    Collection continues across cohorts. Only the selected
                    closed cohort enters evaluation. Unassigned frozen cases:{" "}
                    {state.unassignedCases}.
                  </p>
                </div>
                {!state.cases.length && (
                  <p>
                    No future ETA has qualified for freezing at collection time.
                  </p>
                )}
                <div className="space-y-3">
                  {state.cases.map((c) => (
                    <article
                      key={c.caseId}
                      className="space-y-1 border border-[var(--line)] p-3"
                      data-testid="public-arrival-case"
                    >
                      <div className="flex flex-wrap justify-between gap-2">
                        <strong>
                          {c.vesselName} · LOA {c.loa ?? "?"} m
                        </strong>
                        <span>{c.status}</span>
                      </div>
                      <p>
                        Frozen: {time(c.frozenAt)} · Published ETA:{" "}
                        {time(c.etaAt)}
                      </p>
                      <p>
                        Reported arrival: {time(c.outcome?.arrivalAt ?? null)} ·
                        ETA error (observed − published):{" "}
                        {hours(c.outcome?.arrivalErrorHours)}
                      </p>
                      <p>
                        Reported berth: {time(c.outcome?.berthAt ?? null)} ·
                        Arrival-to-berth wait: {hours(c.outcome?.waitingHours)}{" "}
                        · Berth {c.outcome?.berthRef ?? "Unavailable"}
                      </p>
                      {c.outcome && (
                        <p>
                          Arrival evidence collected:{" "}
                          {time(c.outcome.arrivalAvailableAt)} · Berth evidence
                          collected: {time(c.outcome.berthAvailableAt)}
                        </p>
                      )}
                      {!!c.exclusions.length && (
                        <p>Excluded targets: {c.exclusions.join(", ")}</p>
                      )}
                      {c.exclusions.some((e) =>
                        e.startsWith("CONFLICTING_REPORTED_BERTH"),
                      ) &&
                        c.berthEvidence?.map((b) => (
                          <p key={`${b.snapshotId}-${b.recordId}`}>
                            Disputed berth {b.berthRef ?? "Unavailable"} ·{" "}
                            {time(b.berthAt)} · collected {time(b.availableAt)}{" "}
                            · page {b.page}{" "}
                            <button
                              className={button}
                              onClick={() => void pdf(b.snapshotId)}
                            >
                              Disputed berth {b.berthRef ?? "unknown"} evidence
                            </button>
                          </p>
                        ))}
                      <div className="flex flex-wrap gap-2">
                        <button
                          className={button}
                          onClick={() => void pdf(c.snapshotId)}
                        >
                          Frozen ETA evidence
                        </button>
                        {c.outcome && (
                          <button
                            className={button}
                            onClick={() =>
                              void pdf(c.outcome!.arrivalSnapshotId)
                            }
                          >
                            Arrival evidence
                          </button>
                        )}
                        {c.outcome?.berthSnapshotId && (
                          <button
                            className={button}
                            onClick={() =>
                              void pdf(c.outcome!.berthSnapshotId!)
                            }
                          >
                            Berth evidence
                          </button>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
                <details>
                  <summary>
                    Optional structured vessel source (
                    {state.structuredVessels.records.length} records)
                  </summary>
                  <div
                    className="space-y-2 pt-2"
                    data-testid="structured-vessel-source"
                  >
                    <p>
                      VesselFinder:{" "}
                      {state.structuredVessels.configurationReason ??
                        "Configured"}
                      . Last check: {time(state.structuredVessels.lastCheckAt)}.{" "}
                      {state.structuredVessels.coverage}.
                    </p>
                    <p>{state.structuredVessels.statement}.</p>
                    {!!state.structuredVessels.lastErrors.length && (
                      <p role="alert">
                        {state.structuredVessels.lastErrors.join("; ")}
                      </p>
                    )}
                    {state.structuredVessels.records.map((r) => (
                      <p key={`${r.kind}-${r.recordId}`}>
                        {r.vesselName ?? "Name unavailable"} · MMSI{" "}
                        {r.mmsi ?? "Unavailable"} · IMO {r.imo ?? "Unavailable"}{" "}
                        · {r.event} {time(r.eventAt)} · AIS ETA{" "}
                        {time(r.aisEtaAt)} {r.flags.join(", ")}
                      </p>
                    ))}
                    {state.structuredVessels.snapshots.map((s) => (
                      <button
                        key={s.snapshotId}
                        className={button}
                        onClick={() =>
                          void action(async () =>
                            download(
                              await getBlob(
                                `/public-arrivals/structured-evidence/${s.snapshotId}${suffix}`,
                              ),
                              `${portCode}-vessels-${s.snapshotId.slice(0, 16)}.json`,
                            ),
                          )
                        }
                      >
                        {s.kind} evidence · {time(s.firstSeenAt)}
                      </button>
                    ))}
                  </div>
                </details>
                <details>
                  <summary>Archived reports ({state.snapshots.length})</summary>
                  <div className="space-y-2 pt-2">
                    {state.snapshots.map((s) => (
                      <div
                        key={s.snapshotId}
                        className="border border-[var(--line)] p-2"
                      >
                        <p>
                          {s.kind} · report{" "}
                          {s.reportDate ?? "Layout unavailable"} · first seen{" "}
                          {time(s.firstSeenAt)} · {s.parserVersion}
                        </p>
                        <p className="break-all">SHA-256: {s.sha256}</p>
                        <a
                          className="underline"
                          href={s.sourceUrl}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Publisher URL (may change)
                        </a>{" "}
                        <button
                          className={button}
                          onClick={() => void pdf(s.snapshotId)}
                        >
                          Download archived PDF
                        </button>
                      </div>
                    ))}
                  </div>
                </details>
                <details>
                  <summary>
                    Missing timestamps, exclusions and parser issues (
                    {state.excludedRecords.length + state.issues.length})
                  </summary>
                  <ul className="space-y-1 pt-2">
                    {state.excludedRecords.map((r, i) => (
                      <li key={`${r.recordId}-${i}`}>
                        {r.vesselName}: {r.flags.join(", ")}
                      </li>
                    ))}
                    {state.issues.map((r, i) => (
                      <li key={i}>
                        {r.code} · page {r.page ?? "?"} · {r.raw}
                      </li>
                    ))}
                  </ul>
                </details>
                {(visibleEvaluation || sealedEvaluation) && (
                  <details open>
                    <summary>Baseline evaluation</summary>
                    <pre className="overflow-auto text-[10px]">
                      {JSON.stringify(
                        visibleEvaluation ?? sealedEvaluation,
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                )}
              </>
            )}
          </>
        )}
      </div>
    </Panel>
  );
}
