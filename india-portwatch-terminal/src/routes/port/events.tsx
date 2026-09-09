import { createFileRoute } from "@tanstack/react-router";

import { PortSwitcher, usePortContext } from "@/components/app/port-context";
import { Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import {
  KeyValue,
  MiniBar,
  Num,
  Pill,
  formatUtc,
  severityTone,
} from "@/components/kit/primitives";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { DataTable, type Column } from "@/components/kit/table";
import { CHOKEPOINT_BY_CODE } from "@/lib/maritime/chokepoints";
import { useNews } from "@/services/hooks";
import type { NewsEvent } from "@/types/portwatch";

export const Route = createFileRoute("/port/events")({ component: PortEvents });

interface ExposedEvent {
  event: NewsEvent;
  exposure: number | null;
}

function PortEvents() {
  const { port, query } = usePortContext();
  const news = useNews();

  if (query.isLoading || news.isLoading || news.isError || !port) {
    return (
      <ScreenFallback
        title="Events"
        isLoading={query.isLoading || news.isLoading}
        error={news.error ?? (port ? null : new Error("No port selected."))}
        retry={() => void news.refetch()}
        label="Loading event feed"
      />
    );
  }

  const bundle = news.data;
  const events = bundle?.events ?? [];

  const exposed: ExposedEvent[] = events
    .map((event) => {
      const match = event.exposure?.find((entry) => entry.portCode === port.code);
      const affected = event.affectedPorts?.includes(port.code);
      if (!match && !affected) return null;
      return { event, exposure: match?.exposure ?? null };
    })
    .filter((row): row is ExposedEvent => row !== null)
    .sort((a, b) => (b.exposure ?? 0) - (a.exposure ?? 0));

  const alerts = (bundle?.alerts ?? []).filter((alert) => alert.portCode === port.code);
  const peakExposure = exposed.reduce<number | null>(
    (peak, row) =>
      row.exposure == null ? peak : peak == null ? row.exposure : Math.max(peak, row.exposure),
    null,
  );
  const chokepoints = new Set(
    exposed.map((row) => row.event.chokepoint).filter((code): code is string => Boolean(code)),
  );

  const columns: Array<Column<ExposedEvent>> = [
    {
      key: "severity",
      header: "Severity",
      width: 96,
      render: (row) => (
        <Pill tone={severityTone(row.event.severity)}>{row.event.severity}</Pill>
      ),
      sort: (row) => row.event.severityScore,
    },
    {
      key: "title",
      header: "Event",
      render: (row) => (
        <a
          href={row.event.url}
          target="_blank"
          rel="noreferrer noopener"
          className="text-[var(--text-2)] hover:text-[var(--info)]"
          title={row.event.title}
        >
          {row.event.title}
        </a>
      ),
      sort: (row) => row.event.title,
    },
    {
      key: "tag",
      header: "Type",
      width: 148,
      render: (row) => <span className="num text-[var(--text-3)]">{row.event.tag}</span>,
      sort: (row) => row.event.tag,
    },
    {
      key: "chokepoint",
      header: "Chokepoint",
      width: 156,
      render: (row) =>
        row.event.chokepointName ? (
          <span className="text-[var(--text-2)]">{row.event.chokepointName}</span>
        ) : (
          <span className="text-[var(--text-3)]">—</span>
        ),
      sort: (row) => row.event.chokepointName,
    },
    {
      key: "exposure",
      header: "Exposure here",
      align: "right",
      width: 132,
      hint: "Measured lane exposure of this port to the event's chokepoint",
      render: (row) => (
        <span className="flex items-center justify-end gap-2">
          <span className="w-10">
            <MiniBar
              value={row.exposure}
              tone={(row.exposure ?? 0) >= 0.4 ? "warn" : "info"}
            />
          </span>
          <Num value={row.exposure} digits={2} />
        </span>
      ),
      sort: (row) => row.exposure,
    },
    {
      key: "source",
      header: "Source",
      width: 128,
      render: (row) => <span className="num text-[var(--text-3)]">{row.event.source}</span>,
      sort: (row) => row.event.source,
    },
    {
      key: "ts",
      header: "Observed",
      align: "right",
      width: 124,
      render: (row) => (
        <span className="num text-[var(--text-3)]">{formatUtc(row.event.timestamp)}</span>
      ),
      sort: (row) => row.event.timestamp,
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Events"
        context={
          <>
            <span>{port.name}</span>
            <span className="num">{port.code}</span>
            <span>Shocks with measured exposure to this port</span>
          </>
        }
        meta={
          <span className="num">
            {bundle?.summary.dataSource ?? "event feed unavailable"}
          </span>
        }
        actions={<PortSwitcher />}
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "Events touching this port",
            value: exposed.length,
            tone: exposed.length ? "warn" : "ok",
            note: `${events.length} in the national feed`,
          },
          {
            label: "Peak exposure",
            value: peakExposure?.toFixed(2) ?? "n/a",
            tone: (peakExposure ?? 0) >= 0.4 ? "warn" : "info",
            note: "measured lane exposure, 0–1",
          },
          {
            label: "Chokepoints implicated",
            value: chokepoints.size,
            note:
              [...chokepoints]
                .map((code) => CHOKEPOINT_BY_CODE.get(code)?.name ?? code)
                .join(" · ") || "none",
          },
          {
            label: "Severe events",
            value: exposed.filter((row) => row.event.severity === "severe").length,
            tone: "crit",
            note: "severity as classified by the event expert",
          },
          {
            label: "Open alerts here",
            value: alerts.length,
            note: `${bundle?.summary.totalAlerts ?? 0} across the network`,
          },
        ]}
      />

      <PageBody className="grid grid-cols-1 gap-3 xl:grid-cols-[1fr_360px]">
        <Panel
          title="Exposure feed"
          note={`${exposed.length} events`}
          className="min-h-[320px]"
        >
          {exposed.length === 0 ? (
            <EmptyState
              title="No exposure recorded"
              detail={
                <>
                  None of the {events.length} events in the current feed reports a measured
                  exposure to {port.name}. The disruption-propagation expert only links an
                  event to a port where the lane-exposure graph carries a value for that
                  pair — an unlinked event is not evidence of safety, only of no measured
                  path.
                </>
              }
            />
          ) : (
            <DataTable
              rows={exposed}
              columns={columns}
              rowKey={(row) => row.event.id}
              initialSort="exposure"
            />
          )}
        </Panel>

        <div className="flex min-w-0 flex-col gap-3">
          <Panel title="Alerts raised for this port" note={`${alerts.length}`}>
            {alerts.length === 0 ? (
              <p className="p-3 text-[11.5px] leading-snug text-[var(--text-3)]">
                No alert was raised for {port.short} against the current forecast.
              </p>
            ) : (
              <ul>
                {alerts.map((alert) => (
                  <li
                    key={alert.id}
                    className="border-b border-[var(--line)]/50 px-3 py-2 last:border-0"
                  >
                    <div className="flex items-center gap-2">
                      <Pill tone={severityTone(alert.severity)}>{alert.severity}</Pill>
                      <span className="num ml-auto text-[10px] text-[var(--text-3)]">
                        {formatUtc(alert.ts)}
                      </span>
                    </div>
                    <p className="mt-1 text-[12px] leading-snug text-[var(--text-2)]">
                      {alert.text}
                    </p>
                    <div className="num mt-1 flex gap-3 text-[10px] text-[var(--text-3)]">
                      <span>{alert.action}</span>
                      <span>priority {alert.priority?.toFixed(2) ?? "n/a"}</span>
                      <span>conf {alert.confidence?.toFixed(2) ?? "n/a"}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Feed coverage">
            <div className="px-3 py-2">
              <KeyValue label="Events in feed" dense>
                <Num value={bundle?.summary.totalEvents} digits={0} />
              </KeyValue>
              <KeyValue label="Severe events" dense>
                <Num value={bundle?.summary.severeEvents} digits={0} />
              </KeyValue>
              <KeyValue label="Alerts" dense>
                <Num value={bundle?.summary.totalAlerts} digits={0} />
              </KeyValue>
              <KeyValue label="Feed available" dense>
                <Pill tone={bundle?.summary.eventsAvailable ? "ok" : "crit"}>
                  {bundle?.summary.eventsAvailable ? "yes" : "no"}
                </Pill>
              </KeyValue>
              <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11px] leading-snug text-[var(--text-3)]">
                {bundle?.summary.dataSource ?? "No event source reported."}
              </p>
            </div>
          </Panel>

          <Panel title="Sentiment by entity" note="mentions and risk">
            {bundle?.sentiment?.length ? (
              <div className="px-3 py-2">
                {bundle.sentiment.slice(0, 8).map((entry) => (
                  <div
                    key={entry.entity}
                    className="border-b border-[var(--line)]/50 py-1.5 last:border-0"
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-[11.5px] text-[var(--text-2)]">
                        {entry.entity}
                      </span>
                      <span className="num text-[11px] text-[var(--text-3)]">
                        {entry.mentions} mentions
                      </span>
                    </div>
                    <div className="mt-1">
                      <MiniBar
                        value={entry.riskScore}
                        tone={(entry.riskScore ?? 0) >= 0.5 ? "warn" : "info"}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="p-3 text-[11.5px] text-[var(--text-3)]">
                No sentiment rows in the current run.
              </p>
            )}
          </Panel>
        </div>
      </PageBody>
    </Page>
  );
}
