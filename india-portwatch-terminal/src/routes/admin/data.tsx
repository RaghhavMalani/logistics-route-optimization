import { createFileRoute } from "@tanstack/react-router";
import { useMemo } from "react";

import { Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import {
  KeyValue,
  MiniBar,
  Num,
  Pill,
  ProvenanceTag,
  STATUS_LABEL,
  formatAge,
  formatUtc,
  statusTone,
} from "@/components/kit/primitives";
import { ScreenFallback } from "@/components/kit/states";
import { DataTable, type Column } from "@/components/kit/table";
import { useHealth, useProvenance } from "@/services/hooks";
import type { DataStatus, ProvenanceSource } from "@/types/portwatch";

export const Route = createFileRoute("/admin/data")({ component: DataSources });

const ORDER: Record<DataStatus, number> = {
  UNAVAILABLE: 0,
  STALE: 1,
  SYNTHETIC: 2,
  CACHED_LIVE: 3,
  LIVE: 4,
};

function DataSources() {
  const provenance = useProvenance();
  const health = useHealth();

  const rows = useMemo(
    () => Object.values(provenance.data?.sources ?? {}),
    [provenance.data],
  );

  if (provenance.isLoading || provenance.isError) {
    return (
      <ScreenFallback
        title="Data Sources"
        context={<span>Where every number on every screen came from</span>}
        isLoading={provenance.isLoading}
        error={provenance.error}
        retry={() => void provenance.refetch()}
        label="Loading provenance"
      />
    );
  }

  const counts = provenance.data?.counts ?? {};
  const readiness = provenance.data?.readiness ?? 0;
  const overdue = rows.filter(
    (source) =>
      source.ageHours != null &&
      source.status !== "LIVE" &&
      source.status !== "CACHED_LIVE",
  );

  const columns: Array<Column<ProvenanceSource>> = [
    {
      key: "source",
      header: "Source",
      render: (row) => (
        <span className="text-[var(--text)]" title={row.detail}>
          {row.source}
        </span>
      ),
      sort: (row) => row.source,
    },
    {
      key: "provider",
      header: "Provider",
      width: 250,
      render: (row) => <span className="text-[var(--text-3)]">{row.provider}</span>,
      sort: (row) => row.provider,
    },
    {
      key: "status",
      header: "Status",
      width: 128,
      render: (row) => <Pill tone={statusTone(row.status)}>{STATUS_LABEL[row.status]}</Pill>,
      sort: (row) => ORDER[row.status],
    },
    {
      key: "observed",
      header: "Last observed",
      align: "right",
      width: 130,
      render: (row) => <span className="num text-[var(--text-2)]">{formatUtc(row.observed_at)}</span>,
      sort: (row) => row.observed_at,
    },
    {
      key: "fetched",
      header: "Last fetched",
      align: "right",
      width: 130,
      render: (row) => <span className="num text-[var(--text-3)]">{formatUtc(row.fetched_at)}</span>,
      sort: (row) => row.fetched_at,
    },
    {
      key: "age",
      header: "Age",
      align: "right",
      width: 88,
      render: (row) => (
        <span
          className={`num ${
            row.status === "STALE" || row.status === "UNAVAILABLE"
              ? "text-[var(--warn)]"
              : "text-[var(--text-2)]"
          }`}
        >
          {row.ageHours == null ? "n/a" : formatAge(row.ageHours)}
        </span>
      ),
      sort: (row) => row.ageHours,
    },
    {
      key: "rows",
      header: "Rows",
      align: "right",
      width: 94,
      render: (row) => <Num value={row.rows} digits={0} />,
      sort: (row) => row.rows,
    },
    {
      key: "confidence",
      header: "Confidence",
      align: "right",
      width: 118,
      render: (row) => (
        <span className="flex items-center justify-end gap-2">
          <span className="w-10">
            <MiniBar value={row.confidence} tone={row.confidence >= 0.75 ? "ok" : "warn"} />
          </span>
          <Num value={row.confidence} digits={2} />
        </span>
      ),
      sort: (row) => row.confidence,
    },
    {
      key: "fallback",
      header: "Fallback",
      width: 190,
      render: (row) => (
        <span className="text-[var(--text-3)]">{row.fallback ?? "none — fails visibly"}</span>
      ),
      sort: (row) => row.fallback,
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Data Sources"
        context={<span>Where every number on every screen came from</span>}
        meta={
          <>
            <span className="num">generated {formatUtc(provenance.data?.generatedAt ?? null)}</span>
            <ProvenanceTag
              status={health.data?.forecastOriginStatus ?? null}
              ageHours={health.data?.forecastOriginAgeHours ?? null}
              detail="Forecast origin age"
            />
          </>
        }
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "Feed readiness",
            value: `${(readiness * 100).toFixed(0)}%`,
            tone: readiness >= 0.8 ? "ok" : readiness >= 0.5 ? "warn" : "crit",
            note: `${rows.length} sources registered`,
          },
          { label: "Live", value: counts.LIVE ?? 0, tone: "ok", note: "fetched inside its budget" },
          { label: "Cached", value: counts.CACHED_LIVE ?? 0, tone: "info", note: "served from the local response cache" },
          { label: "Stale", value: counts.STALE ?? 0, tone: "warn", note: "older than its freshness budget" },
          { label: "Synthetic", value: counts.SYNTHETIC ?? 0, tone: "unc", note: "generated, never presented as observed" },
          { label: "Unavailable", value: counts.UNAVAILABLE ?? 0, tone: "crit", note: "the screen renders the gap" },
        ]}
      />

      <PageBody padded={false} className="flex min-h-0 overflow-hidden">
        <Panel
          title="Source register"
          note={`${rows.length} feeds`}
          className="min-w-0 flex-1 rounded-none border-0 border-r border-[var(--line)]"
        >
          <DataTable
            rows={rows}
            columns={columns}
            rowKey={(row) => row.source}
            initialSort="status"
            initialDirection="asc"
            rowTone={(row) =>
              row.status === "UNAVAILABLE"
                ? "var(--crit)"
                : row.status === "STALE"
                  ? "var(--warn)"
                  : row.status === "SYNTHETIC"
                    ? "var(--unc)"
                    : null
            }
          />
        </Panel>

        <aside className="flex w-[400px] shrink-0 flex-col overflow-y-auto 2xl:w-[440px]">
          <Panel title="What the states mean" className="shrink-0 rounded-none border-x-0 border-t-0">
            <div className="px-3 py-2">
              {(
                [
                  ["LIVE", "Fetched this run, inside the source's freshness budget."],
                  ["CACHED", "Served from the local response cache; the upstream call did not run or did not answer."],
                  ["STALE", "Real data, older than its freshness budget. The age is shown wherever the number is."],
                  ["SYNTHETIC", "Generated. Never rendered as an observation, and counted separately in readiness."],
                  ["NO DATA", "Absent. The screen renders the gap as n/a rather than substituting a plausible value."],
                ] as Array<[string, string]>
              ).map(([label, detail]) => (
                <div key={label} className="border-b border-[var(--line)]/50 py-2 last:border-0">
                  <Pill
                    tone={
                      label === "LIVE"
                        ? "ok"
                        : label === "CACHED"
                          ? "info"
                          : label === "STALE"
                            ? "warn"
                            : label === "SYNTHETIC"
                              ? "unc"
                              : "crit"
                    }
                  >
                    {label}
                  </Pill>
                  <p className="mt-1 text-[11.5px] leading-snug text-[var(--text-3)]">{detail}</p>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Attention" note={`${overdue.length}`} className="shrink-0 rounded-none border-x-0 border-t-0">
            {overdue.length === 0 ? (
              <p className="px-3 py-3 text-[11.5px] text-[var(--text-3)]">
                Every registered source is live or cached inside its budget.
              </p>
            ) : (
              <div className="px-3 py-2">
                {overdue.map((source) => (
                  <div key={source.source} className="border-b border-[var(--line)]/50 py-2 last:border-0">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="min-w-0 truncate text-[11.5px] text-[var(--text-2)]">
                        {source.source}
                      </span>
                      <ProvenanceTag status={source.status} ageHours={source.ageHours} />
                    </div>
                    <p className="mt-1 text-[11px] leading-snug text-[var(--text-3)]">
                      Budget {source.freshness_budget_hours ?? "n/a"}h.{" "}
                      {source.fallback
                        ? `Falling back to ${source.fallback}.`
                        : "No fallback configured — the screens render the gap."}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Run" className="min-h-0 flex-1 rounded-none border-x-0 border-b-0">
            <div className="px-3 py-2">
              <KeyValue label="Forecast origin" dense>
                <span className="num text-[11.5px]">
                  {formatUtc(provenance.data?.forecastOrigin ?? health.data?.forecastOrigin ?? null)}
                </span>
              </KeyValue>
              <KeyValue label="Cache age" dense>
                <span className="num text-[11.5px]">
                  {provenance.data?.cacheAgeSeconds != null
                    ? formatAge(provenance.data.cacheAgeSeconds / 3600)
                    : "n/a"}
                </span>
              </KeyValue>
              <KeyValue label="Model" dense>
                <span className="num text-[11.5px]">{health.data?.model ?? "n/a"}</span>
              </KeyValue>
              <KeyValue label="Horizon" dense>
                <span className="num text-[11.5px]">{health.data?.horizonDays ?? "n/a"} days</span>
              </KeyValue>
              <KeyValue label="Ports covered" dense>
                <span className="num text-[11.5px]">{health.data?.ports ?? "n/a"}</span>
              </KeyValue>
              <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11px] leading-snug text-[var(--text-3)]">
                Rebuild the artefacts with{" "}
                <code className="font-mono text-[10.5px] text-[var(--text-2)]">
                  python run_award_demo.py --source portwatch
                </code>
                .
              </p>
            </div>
          </Panel>
        </aside>
      </PageBody>
    </Page>
  );
}
