import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { BarRanking } from "@/components/kit/charts";
import { Page, PageBody, PageHeader, Panel, StatStrip, Toolbar } from "@/components/kit/layout";
import {
  MiniBar,
  Num,
  Pill,
  formatUtc,
  severityTone,
} from "@/components/kit/primitives";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { DataTable, SearchInput, type Column } from "@/components/kit/table";
import { ContextMap } from "@/components/command/ContextMap";
import { useWorkspaceMap } from "@/components/command/useWorkspaceMap";
import { CHOKEPOINT_BY_CODE } from "@/lib/maritime/chokepoints";
import { buildExposureLayers } from "@/lib/maritime/exposure";
import { useNews, usePorts, useWeather } from "@/services/hooks";
import type { NewsEvent } from "@/types/portwatch";

export const Route = createFileRoute("/admin/intelligence")({ component: EventIntelligence });

function EventIntelligence() {
  const news = useNews();
  const ports = usePorts();
  const weather = useWeather();
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const workspace = useWorkspaceMap({
    layerOverrides: { events: true, weather: false, traffic: false, corridors: false },
  });
  const exposure = useMemo(
    () => buildExposureLayers(news.data?.events ?? [], ports.data ?? []),
    [news.data, ports.data],
  );

  const events = useMemo(() => news.data?.events ?? [], [news.data]);
  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return events;
    return events.filter(
      (event) =>
        event.title.toLowerCase().includes(term) ||
        event.tag.toLowerCase().includes(term) ||
        event.entity.toLowerCase().includes(term) ||
        (event.chokepointName ?? "").toLowerCase().includes(term),
    );
  }, [events, search]);

  if (news.isLoading || news.isError) {
    return (
      <ScreenFallback
        title="Event Intelligence"
        context={<span>Typed maritime shocks and the ports they measurably reach</span>}
        isLoading={news.isLoading}
        error={news.error}
        retry={() => void news.refetch()}
        label="Loading event feed"
      />
    );
  }

  const active = events.find((event) => event.id === selectedId) ?? rows[0] ?? null;
  const summary = news.data?.summary;
  const sentiment = news.data?.sentiment ?? [];
  const chokepointCounts = new Map<string, number>();
  for (const event of events) {
    if (!event.chokepoint) continue;
    chokepointCounts.set(event.chokepoint, (chokepointCounts.get(event.chokepoint) ?? 0) + 1);
  }

  const columns: Array<Column<NewsEvent>> = [
    {
      key: "severity",
      header: "Severity",
      width: 92,
      render: (event) => <Pill tone={severityTone(event.severity)}>{event.severity}</Pill>,
      sort: (event) => event.severityScore,
    },
    {
      key: "title",
      header: "Event",
      render: (event) => (
        <span className="text-[var(--text-2)]" title={event.title}>
          {event.title}
        </span>
      ),
      sort: (event) => event.title,
    },
    {
      key: "tag",
      header: "Type",
      width: 152,
      render: (event) => <span className="num text-[var(--text-3)]">{event.tag}</span>,
      sort: (event) => event.tag,
    },
    {
      key: "chokepoint",
      header: "Chokepoint",
      width: 150,
      render: (event) =>
        event.chokepointName ? (
          <span className="text-[var(--text-2)]">{event.chokepointName}</span>
        ) : (
          <span className="text-[var(--text-3)]">—</span>
        ),
      sort: (event) => event.chokepointName,
    },
    {
      key: "ports",
      header: "Exposed ports",
      align: "right",
      width: 124,
      render: (event) => <Num value={event.exposure?.length ?? 0} digits={0} />,
      sort: (event) => event.exposure?.length ?? 0,
    },
    {
      key: "source",
      header: "Source",
      width: 132,
      render: (event) => <span className="num text-[var(--text-3)]">{event.source}</span>,
      sort: (event) => event.source,
    },
    {
      key: "ts",
      header: "Observed",
      align: "right",
      width: 122,
      render: (event) => <span className="num text-[var(--text-3)]">{formatUtc(event.timestamp)}</span>,
      sort: (event) => event.timestamp,
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Event Intelligence"
        context={<span>Typed maritime shocks and the ports they measurably reach</span>}
        meta={<span className="num">{summary?.dataSource ?? "no event source"}</span>}
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "Events in feed",
            value: summary?.totalEvents ?? events.length,
            note: summary?.eventsAvailable ? "feed available" : "feed unavailable",
            tone: summary?.eventsAvailable ? "info" : "crit",
          },
          {
            label: "Severe",
            value: summary?.severeEvents ?? 0,
            tone: "crit",
            note: "classified severe by the event expert",
          },
          {
            label: "Alerts raised",
            value: summary?.totalAlerts ?? 0,
            tone: (summary?.totalAlerts ?? 0) > 0 ? "warn" : "ok",
            note: "by the decision layer, this run",
          },
          {
            label: "Chokepoints implicated",
            value: chokepointCounts.size,
            note:
              [...chokepointCounts.keys()]
                .map((code) => CHOKEPOINT_BY_CODE.get(code)?.name ?? code)
                .join(" · ") || "none",
          },
          {
            label: "Mapped on chart",
            value: exposure.placedEvents,
            note: exposure.note ?? "all events carry a mapped chokepoint",
          },
        ]}
      />

      <PageBody padded={false} className="flex min-h-0 overflow-hidden">
        <div className="flex min-w-0 flex-1 flex-col border-r border-[var(--line)]">
          <div className="relative h-[46%] min-h-[240px] shrink-0 border-b border-[var(--line)]">
            <ContextMap
              workspace={workspace}
              extraData={{
                events: exposure.events,
                routes: exposure.routes,
                chokepoints: exposure.chokepoints,
              }}
              // Pulled back and west so Suez, Hormuz, Bab-el-Mandeb and Malacca
              // are all on screen: this screen is about the corridors, not the coast.
              view={{ center: [62, 16], zoom: 3.1 }}
              showTraffic={false}
              note={
                <>
                  Exposure corridors follow the water-only routing graph, so their length is the
                  passage a diversion would actually run.
                  {exposure.note ? ` ${exposure.note}` : ""}
                </>
              }
            />
          </div>

          <Toolbar>
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Filter events"
              className="w-[300px]"
            />
            <span className="num ml-auto text-[11px] text-[var(--text-3)]">
              {rows.length} of {events.length}
            </span>
          </Toolbar>

          <Panel className="min-h-0 flex-1 rounded-none border-0">
            {rows.length === 0 ? (
              <EmptyState
                title="No events"
                detail={summary?.dataSource ?? "The event feed is empty for this run."}
              />
            ) : (
              <DataTable
                rows={rows}
                columns={columns}
                rowKey={(event) => event.id}
                selectedKey={active?.id ?? null}
                onRowClick={(event) => setSelectedId(event.id)}
                initialSort="severity"
                rowTone={(event) =>
                  event.severity === "severe"
                    ? "var(--crit)"
                    : event.severity === "high"
                      ? "var(--warn)"
                      : null
                }
              />
            )}
          </Panel>
        </div>

        <aside className="flex w-[400px] shrink-0 flex-col overflow-y-auto 2xl:w-[450px]">
          {active ? (
            <Panel
              title="Selected event"
              note={active.tag}
              className="shrink-0 rounded-none border-x-0 border-t-0"
            >
              <div className="p-3">
                <div className="mb-2 flex items-center gap-2">
                  <Pill tone={severityTone(active.severity)} solid>
                    {active.severity}
                  </Pill>
                  <span className="num text-[10.5px] text-[var(--text-3)]">
                    score {active.severityScore.toFixed(2)}
                  </span>
                  <span className="num ml-auto text-[10.5px] text-[var(--text-3)]">
                    {formatUtc(active.timestamp)}
                  </span>
                </div>
                <a
                  href={active.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-[13px] font-medium leading-snug text-[var(--text)] hover:text-[var(--info)]"
                >
                  {active.title}
                </a>
                <div className="num mt-1.5 text-[10.5px] text-[var(--text-3)]">
                  {active.source} · {active.entity}
                  {active.chokepointName ? ` · ${active.chokepointName}` : ""}
                </div>

                <div className="mt-3 border-t border-[var(--line)] pt-2">
                  <div className="eyebrow mb-1.5">Measured port exposure</div>
                  {active.exposure?.length ? (
                    <BarRanking
                      items={active.exposure
                        .slice()
                        .sort((a, b) => b.exposure - a.exposure)
                        .map((entry) => ({
                          label: entry.name,
                          value: entry.exposure,
                          tone: entry.exposure >= 0.4 ? ("warn" as const) : ("info" as const),
                        }))}
                      valueFormatter={(value) => value.toFixed(2)}
                    />
                  ) : (
                    <p className="text-[11.5px] leading-snug text-[var(--text-3)]">
                      The lane-exposure graph carries no path from this event to an Indian
                      port, so no exposure is claimed.
                    </p>
                  )}
                </div>
                <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11px] leading-snug text-[var(--text-3)]">
                  {active.dataSource}
                </p>
              </div>
            </Panel>
          ) : null}

          <Panel title="Chokepoint pressure" className="shrink-0 rounded-none border-x-0 border-t-0">
            <div className="px-3 py-2">
              {[...CHOKEPOINT_BY_CODE.values()].map((choke) => {
                const count = chokepointCounts.get(choke.code) ?? 0;
                return (
                  <div
                    key={choke.code}
                    className="flex items-baseline justify-between gap-2 border-b border-[var(--line)]/50 py-1.5 last:border-0"
                  >
                    <span className="min-w-0 truncate text-[11.5px] text-[var(--text-2)]">
                      {choke.name}
                    </span>
                    <span className="num shrink-0 text-[11px] text-[var(--text-3)]">
                      {count} event{count === 1 ? "" : "s"}
                    </span>
                  </div>
                );
              })}
            </div>
          </Panel>

          <Panel
            title="Entity sentiment"
            note={`${sentiment.length}`}
            className="min-h-0 flex-1 rounded-none border-x-0 border-b-0"
            scroll
          >
            {sentiment.length === 0 ? (
              <p className="p-3 text-[11.5px] text-[var(--text-3)]">
                No sentiment rows in the current run.
              </p>
            ) : (
              <div className="px-3 py-2">
                {sentiment.map((entry) => (
                  <div
                    key={entry.entity}
                    className="border-b border-[var(--line)]/50 py-1.5 last:border-0"
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-[11.5px] text-[var(--text-2)]">
                        {entry.entity}
                      </span>
                      <span className="num text-[10.5px] text-[var(--text-3)]">
                        {entry.mentions} mentions
                      </span>
                    </div>
                    <div className="mt-1">
                      <MiniBar
                        value={entry.riskScore}
                        tone={(entry.riskScore ?? 0) >= 0.5 ? "warn" : "info"}
                      />
                    </div>
                    <div className="num mt-1 flex gap-3 text-[10px] text-[var(--text-3)]">
                      <span>risk {entry.riskScore?.toFixed(2) ?? "n/a"}</span>
                      <span>sentiment {entry.sentiment?.toFixed(2) ?? "n/a"}</span>
                      <span>conf {entry.confidence?.toFixed(2) ?? "n/a"}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </aside>
      </PageBody>
    </Page>
  );
}
