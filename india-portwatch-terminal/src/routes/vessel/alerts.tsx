import { Link, createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { useFleetIntel } from "@/components/app/fleet-context";
import { Page, PageBody, PageHeader, Panel, SegmentedControl, StatStrip, Toolbar } from "@/components/kit/layout";
import {
  MiniBar,
  Num,
  Pill,
  formatUtc,
  severityTone,
} from "@/components/kit/primitives";
import { EmptyState, FailureState, LoadingPanel } from "@/components/kit/states";
import { DataTable, SearchInput, type Column } from "@/components/kit/table";
import { CHOKEPOINT_BY_CODE } from "@/components/map/layers";
import type { NewsEvent } from "@/types/portwatch";

export const Route = createFileRoute("/vessel/alerts")({ component: FleetAlerts });

type Scope = "lanes" | "all";

interface AlertRow {
  event: NewsEvent;
  /** Highest measured exposure of any fleet destination to this event. */
  exposure: number | null;
  vessels: string[];
}

function FleetAlerts() {
  const { intel, events, alerts, isLoading, error, refetch } = useFleetIntel();
  const [scope, setScope] = useState<Scope>("lanes");
  const [search, setSearch] = useState("");

  const rows = useMemo<AlertRow[]>(() => {
    const byPort = new Map<string, string[]>();
    for (const row of intel) {
      for (const code of [row.vessel.intendedPortCode, row.vessel.recommendedPortCode]) {
        if (!code) continue;
        const list = byPort.get(code) ?? [];
        list.push(row.vessel.name);
        byPort.set(code, list);
      }
    }

    return events
      .map((event) => {
        let exposure: number | null = null;
        const vessels = new Set<string>();
        for (const entry of event.exposure ?? []) {
          const names = byPort.get(entry.portCode);
          if (!names) continue;
          exposure = exposure == null ? entry.exposure : Math.max(exposure, entry.exposure);
          for (const name of names) vessels.add(name);
        }
        for (const code of event.affectedPorts ?? []) {
          for (const name of byPort.get(code) ?? []) vessels.add(name);
        }
        return { event, exposure, vessels: [...vessels] };
      })
      .filter((row) => (scope === "lanes" ? row.vessels.length > 0 : true))
      .filter((row) => {
        const term = search.trim().toLowerCase();
        if (!term) return true;
        return (
          row.event.title.toLowerCase().includes(term) ||
          row.event.tag.toLowerCase().includes(term) ||
          (row.event.chokepointName ?? "").toLowerCase().includes(term)
        );
      })
      .sort((a, b) => (b.exposure ?? 0) - (a.exposure ?? 0));
  }, [events, intel, scope, search]);

  if (isLoading) return <LoadingPanel label="Loading alerts" rows={9} />;
  if (error) return <FailureState error={error} retry={refetch} />;

  const fleetPorts = new Set(
    intel.map((row) => row.vessel.intendedPortCode).filter((code): code is string => Boolean(code)),
  );
  const fleetAlerts = alerts.filter((alert) => fleetPorts.has(alert.portCode));
  const onLane = rows.filter((row) => row.vessels.length > 0);
  const chokepoints = new Set(
    onLane.map((row) => row.event.chokepoint).filter((code): code is string => Boolean(code)),
  );

  const columns: Array<Column<AlertRow>> = [
    {
      key: "severity",
      header: "Severity",
      width: 92,
      render: (row) => <Pill tone={severityTone(row.event.severity)}>{row.event.severity}</Pill>,
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
      width: 150,
      render: (row) => <span className="num text-[var(--text-3)]">{row.event.tag}</span>,
      sort: (row) => row.event.tag,
    },
    {
      key: "chokepoint",
      header: "Chokepoint",
      width: 150,
      render: (row) =>
        row.event.chokepointName ? (
          <span className="text-[var(--text-2)]">{row.event.chokepointName}</span>
        ) : (
          <span className="text-[var(--text-3)]">—</span>
        ),
      sort: (row) => row.event.chokepointName,
    },
    {
      key: "vessels",
      header: "Our vessels",
      width: 190,
      render: (row) =>
        row.vessels.length ? (
          <span className="text-[var(--text-2)]">{row.vessels.join(", ")}</span>
        ) : (
          <span className="text-[var(--text-3)]">not on our lanes</span>
        ),
      sort: (row) => row.vessels.length,
    },
    {
      key: "exposure",
      header: "Exposure",
      align: "right",
      width: 116,
      render: (row) => (
        <span className="flex items-center justify-end gap-2">
          <span className="w-9">
            <MiniBar value={row.exposure} tone={(row.exposure ?? 0) >= 0.4 ? "warn" : "info"} />
          </span>
          <Num value={row.exposure} digits={2} />
        </span>
      ),
      sort: (row) => row.exposure,
    },
    {
      key: "ts",
      header: "Observed",
      align: "right",
      width: 122,
      render: (row) => (
        <span className="num text-[var(--text-3)]">{formatUtc(row.event.timestamp)}</span>
      ),
      sort: (row) => row.event.timestamp,
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Alerts"
        context={<span>Events with a measured exposure to the fleet's declared calls</span>}
        meta={<span className="num">{events.length} events in the national feed</span>}
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "On our lanes",
            value: onLane.length,
            tone: onLane.length ? "warn" : "ok",
            note: `${events.length} events in the feed`,
          },
          {
            label: "Severe",
            value: onLane.filter((row) => row.event.severity === "severe").length,
            tone: "crit",
            note: "as classified by the event expert",
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
            label: "Port alerts on our calls",
            value: fleetAlerts.length,
            note: `${alerts.length} raised across the network`,
          },
        ]}
      />

      <Toolbar>
        <SegmentedControl
          ariaLabel="Alert scope"
          value={scope}
          onChange={setScope}
          options={[
            { value: "lanes", label: "Our lanes" },
            { value: "all", label: "Whole feed" },
          ]}
        />
        <SearchInput value={search} onChange={setSearch} placeholder="Filter events" className="w-[260px]" />
        <span className="num ml-auto text-[11px] text-[var(--text-3)]">{rows.length} shown</span>
      </Toolbar>

      <PageBody padded={false} className="flex min-h-0 overflow-hidden">
        <Panel className="min-w-0 flex-1 rounded-none border-0 border-r border-[var(--line)]">
          {rows.length === 0 ? (
            <EmptyState
              title={scope === "lanes" ? "Nothing on our lanes" : "No events"}
              detail={
                scope === "lanes"
                  ? "No event in the current feed reports a measured exposure to a port this fleet calls at. Switch to the whole feed to see the national picture."
                  : "The event feed is empty for this run."
              }
            />
          ) : (
            <DataTable
              rows={rows}
              columns={columns}
              rowKey={(row) => row.event.id}
              initialSort="exposure"
              rowTone={(row) => (row.vessels.length ? "var(--warn)" : null)}
            />
          )}
        </Panel>

        <aside className="flex w-[360px] shrink-0 flex-col overflow-y-auto">
          <Panel
            title="Port alerts on our calls"
            note={`${fleetAlerts.length}`}
            className="shrink-0 rounded-none border-x-0 border-t-0"
          >
            {fleetAlerts.length === 0 ? (
              <p className="px-3 py-3 text-[11.5px] leading-snug text-[var(--text-3)]">
                The decision layer raised no alert at a port this fleet calls at.
              </p>
            ) : (
              <ul>
                {fleetAlerts.map((alert) => (
                  <li
                    key={alert.id}
                    className="border-b border-[var(--line)]/50 px-3 py-2 last:border-0"
                  >
                    <div className="flex items-center gap-2">
                      <Pill tone={severityTone(alert.severity)}>{alert.severity}</Pill>
                      <span className="num ml-auto text-[10px] text-[var(--text-3)]">
                        {alert.portCode}
                      </span>
                    </div>
                    <p className="mt-1 text-[11.5px] leading-snug text-[var(--text-2)]">
                      {alert.text}
                    </p>
                    <div className="num mt-0.5 flex gap-3 text-[10px] text-[var(--text-3)]">
                      <span>{alert.action}</span>
                      <span>conf {alert.confidence?.toFixed(2) ?? "n/a"}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel
            title="Fleet status"
            className="min-h-0 flex-1 rounded-none border-x-0 border-b-0"
            scroll
          >
            <ul>
              {intel.map((row) => (
                <li key={row.vessel.id} className="border-b border-[var(--line)]/50 last:border-0">
                  <Link
                    to="/vessel/$vesselId"
                    params={{ vesselId: row.vessel.id }}
                    className="block px-3 py-2 transition-colors hover:bg-[var(--panel-2)]"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[12px] text-[var(--text)]">{row.vessel.name}</span>
                      <Pill tone={row.exposure.length ? "warn" : "ok"}>
                        {row.exposure.length} exposed
                      </Pill>
                    </div>
                    <div className="num mt-0.5 text-[10.5px] text-[var(--text-3)]">
                      {row.vessel.intendedPortName ?? row.vessel.intendedPortCode}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>
        </aside>
      </PageBody>
    </Page>
  );
}
