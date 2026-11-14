import { Link, createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { formatUtc } from "@/components/kit/primitives";
import { ModelStatus } from "@/components/public/ModelStatus";
import { getJson } from "@/services/api";
import type { ApiResponse } from "@/services/api-client";
import {
  ageLabel,
  expectedLagTone,
  sourceStatusLabel,
  successLabel,
  useSourceHealth,
} from "@/services/source-health";

export const Route = createFileRoute("/sources")({
  component: SourcesPage,
  head: () => ({ meta: [{ title: "Sources · PortWatch X" }] }),
});

const sourceReadingLabels: Record<string, string> = {
  "open-meteo-marine-extended": "View modelled readings",
  "open-meteo-ensemble": "View modelled readings",
  "frankfurter-ecb-fx": "View ECB reference rates",
};

function SourceReadings({ id, label }: { id: string; label: string }) {
  const [open, setOpen] = useState(false);
  const readings = useQuery({
    queryKey: ["public", "source-readings", id],
    queryFn: ({ signal }) =>
      getJson<ApiResponse<"/api/public/source-readings/{key}", "get">>(
        `/public/source-readings/${encodeURIComponent(id)}`,
        undefined,
        { signal },
      ),
    enabled: open,
    refetchInterval: 60_000,
  });
  return (
    <details
      className="mt-3 text-sm"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer underline underline-offset-2">
        {label}
      </summary>
      {readings.isFetching && !readings.data ? (
        <p role="status">Reading retained snapshot…</p>
      ) : null}
      {readings.isError || readings.data?.length === 0 ? (
        <p>No current readings available.</p>
      ) : null}
      <ul className="mt-2 grid max-h-72 gap-2 overflow-y-auto">
        {readings.data?.map((row) => (
          <li key={row.label} className="border-t border-[var(--line)] pt-2">
            <strong>{row.label}</strong> · {formatUtc(row.validAt)}
            <dl className="grid grid-cols-[1fr_auto] gap-x-3">
              {row.values.map((value) => (
                <div key={value.label} className="contents">
                  <dt>{value.label}</dt>
                  <dd>
                    {value.value == null
                      ? "Unavailable"
                      : `${value.value} ${value.unit}`}
                    {value.detail ? ` · ${value.detail}` : ""}
                  </dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
    </details>
  );
}

function SourcesPage() {
  const { data, isPending, isError } = useSourceHealth();
  return (
    <main className="min-h-screen bg-[var(--bg)] px-5 py-9 text-[var(--text)]">
      <div className="mx-auto max-w-5xl">
        <nav
          className="mb-5 flex gap-4 text-sm underline underline-offset-2"
          aria-label="PortWatch"
        >
          <Link to="/login">Workspace sign-in</Link>
          <Link to="/research">Research</Link>
        </nav>
        <p className="font-mono text-xs uppercase tracking-wider text-[var(--text-2)]">
          Data now
        </p>
        <h1 className="mb-2 text-4xl font-semibold">Sources</h1>
        <p className="mb-6 max-w-2xl text-sm text-[var(--text-2)]">
          Retained source snapshots and their age. Daily products can arrive
          within their expected publication lag. Private trials appear as
          unavailable in the workspace.
        </p>
        <ModelStatus />
        {isPending ? (
          <p role="status">Checking retained source health…</p>
        ) : null}
        {isError ? (
          <p role="status">Source health is temporarily unavailable.</p>
        ) : null}
        <ul className="grid gap-3 md:grid-cols-2">
          {data?.sources.map((source) => (
            <li
              key={source.id}
              className={`rounded border border-[var(--line)] bg-[var(--panel)] p-4 ${source.status === "stale" || source.status === "unavailable" ? "text-[var(--text-3)]" : ""}`}
            >
              <p className="font-mono text-xs uppercase text-[var(--text-2)]">
                {source.provider} ·{" "}
                {source.status === "expected_lag" ? (
                  <span className={expectedLagTone}>
                    {sourceStatusLabel[source.status]}
                  </span>
                ) : source.status === "live" &&
                  source.id === "imf-portwatch-data" ? (
                  "Current daily snapshot"
                ) : (
                  sourceStatusLabel[source.status]
                )}
              </p>
              <h2 className="mt-1 text-lg font-semibold">{source.name}</h2>
              <p className="mt-1 text-sm text-[var(--text-2)]">
                {source.detail}
              </p>
              {source.trial ? (
                <p className="mt-2 font-mono text-xs">
                  48-hour trial · {String(source.trial.phase)} ·{" "}
                  {String(source.trial.decision)}
                  {typeof source.trial.successRate7d === "number" &&
                  typeof source.trial.attempts7d === "number"
                    ? ` · ${successLabel(source.trial.successRate7d, source.trial.attempts7d)} checks succeeded`
                    : null}
                </p>
              ) : null}
              {source.portsTotal != null ? (
                <p className="mt-2 text-xs">
                  {source.portsCurrent ?? 0}/{source.portsTotal} ports within
                  policy
                </p>
              ) : null}
              {source.status === "live" && sourceReadingLabels[source.id] ? (
                <SourceReadings
                  id={source.id}
                  label={sourceReadingLabels[source.id]}
                />
              ) : null}
              {source.status !== "live" &&
              (source.observedAt || source.availableAt) ? (
                <p
                  className="mt-2 text-xs"
                  data-testid="source-latest-available"
                >
                  Latest available ·{" "}
                  {formatUtc(source.observedAt ?? source.availableAt)} (
                  {ageLabel(source.dataAgeSeconds)} old)
                </p>
              ) : null}
              <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
                {source.publicationLag ? (
                  <>
                    <dt>Provisional publication lag</dt>
                    <dd>
                      {ageLabel(source.publicationLag.medianSeconds)} ·{" "}
                      {source.publicationLag.samples} distinct daily{" "}
                      {source.publicationLag.samples === 1
                        ? "collection"
                        : "collections"}
                    </dd>
                  </>
                ) : null}
                <dt>Last successful check</dt>
                <dd>
                  {source.lastSuccess ? (
                    <time dateTime={source.lastSuccess}>
                      {formatUtc(source.lastSuccess)}
                    </time>
                  ) : (
                    "Unmeasured"
                  )}
                </dd>
                <dt>Successful attempts over 7 days</dt>
                <dd>{successLabel(source.successRate7d, source.attempts7d)}</dd>
                <dt>Median lag over 7 days</dt>
                <dd>{ageLabel(source.medianLagSeconds)}</dd>
                <dt>Latest data age</dt>
                <dd>{ageLabel(source.dataAgeSeconds)}</dd>
                <dt>Last error</dt>
                <dd className="max-w-[20rem] break-words">
                  {source.lastError ?? "None recorded"}
                </dd>
                <dt>Error time</dt>
                <dd>
                  {source.lastErrorAt
                    ? formatUtc(source.lastErrorAt)
                    : "Unmeasured"}
                </dd>
              </dl>
              <div className="mt-3 flex gap-4 text-xs underline underline-offset-2">
                {source.homepage ? (
                  <a href={source.homepage}>Official source</a>
                ) : null}
                {source.termsUrl ? <a href={source.termsUrl}>Terms</a> : null}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
