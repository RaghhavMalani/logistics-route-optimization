import { Link, createFileRoute } from "@tanstack/react-router";

import { formatUtc } from "@/components/kit/primitives";
import {
  ageLabel,
  successLabel,
  useSourceHealth,
} from "@/services/source-health";

export const Route = createFileRoute("/sources")({
  component: SourcesPage,
  head: () => ({ meta: [{ title: "Sources · PortWatch X" }] }),
});

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
          Health of the source snapshots monitored here. Daily products can be
          current and still lag the present. Private trials appear as
          unavailable in the workspace.
        </p>
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
              className="rounded border border-[var(--line)] bg-[var(--panel)] p-4"
            >
              <p className="font-mono text-xs uppercase text-[var(--text-2)]">
                {source.provider} ·{" "}
                {source.status === "live" && source.id === "imf-portwatch-data"
                  ? "Current daily snapshot"
                  : source.status}
              </p>
              <h2 className="mt-1 text-lg font-semibold">{source.name}</h2>
              <p className="mt-1 text-sm text-[var(--text-2)]">
                {source.detail}
              </p>
              <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
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
