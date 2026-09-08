import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import {
  KeyValue,
  MiniBar,
  Num,
  ProvenanceTag,
  formatUtc,
} from "@/components/kit/primitives";
import { EmptyState, FailureState, LoadingPanel } from "@/components/kit/states";
import { DataTable, type Column } from "@/components/kit/table";
import { MapControlPanel, MapLegend } from "@/components/map/MapControls";
import { OperationsMap } from "@/components/map/OperationsMap";
import type { LayerKey } from "@/components/map/basemap";
import { useOperationalMap } from "@/components/map/useOperationalMap";
import { useFeedAdapters, useNews, usePorts, useVessels, useWeather } from "@/services/hooks";
import type { FeedAdapter, VesselActivity } from "@/types/portwatch";

export const Route = createFileRoute("/admin/vessels")({ component: AdminVessels });

const LAYERS: Record<LayerKey, boolean> = {
  ports: true,
  vessels: true,
  weather: false,
  stations: false,
  storms: false,
  routes: false,
  chokepoints: true,
  events: false,
  zones: false,
  graticule: true,
};

function AdminVessels() {
  const vessels = useVessels();
  const adapters = useFeedAdapters();
  const ports = usePorts();
  const weather = useWeather();
  const news = useNews();
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(LAYERS);
  const [selected, setSelected] = useState<string | null>(null);

  const map = useOperationalMap({
    ports: ports.data ?? [],
    weather: weather.data ?? [],
    vessels: vessels.data?.vessels ?? [],
    events: news.data?.events ?? [],
    selected,
    exposureLanes: false,
  });

  if (vessels.isLoading) return <LoadingPanel label="Loading vessel activity" rows={9} />;
  if (vessels.isError) {
    return <FailureState error={vessels.error} retry={() => void vessels.refetch()} />;
  }

  const rows = vessels.data?.vessels ?? [];
  const totalCalls = rows.reduce((sum, row) => sum + (row.dailyPortCalls ?? 0), 0);
  const totalQueue = rows.reduce((sum, row) => sum + (row.queueBuildup ?? 0), 0);
  const worst = rows.reduce<VesselActivity | null>(
    (peak, row) => (!peak || row.queuePressure > peak.queuePressure ? row : peak),
    null,
  );

  const columns: Array<Column<VesselActivity>> = [
    {
      key: "name",
      header: "Port",
      render: (row) => <span className="text-[var(--text-2)]">{row.name}</span>,
      sort: (row) => row.name,
    },
    {
      key: "code",
      header: "LOCODE",
      width: 100,
      render: (row) => <span className="num text-[var(--text-3)]">{row.portCode}</span>,
      sort: (row) => row.portCode,
    },
    {
      key: "calls",
      header: "Calls / day",
      align: "right",
      width: 110,
      render: (row) => <Num value={row.dailyPortCalls} />,
      sort: (row) => row.dailyPortCalls,
    },
    {
      key: "queue",
      header: "Queue buildup",
      align: "right",
      width: 128,
      render: (row) => <Num value={row.queueBuildup} />,
      sort: (row) => row.queueBuildup,
    },
    {
      key: "waiting",
      header: "Waiting proxy",
      align: "right",
      width: 124,
      render: (row) => <Num value={row.waitingProxy} />,
      sort: (row) => row.waitingProxy,
    },
    {
      key: "pressure",
      header: "Queue pressure",
      align: "right",
      width: 134,
      render: (row) => (
        <span className="flex items-center justify-end gap-2">
          <span className="w-10">
            <MiniBar
              value={row.queuePressure}
              tone={row.queuePressure >= 0.65 ? "crit" : row.queuePressure >= 0.4 ? "warn" : "info"}
            />
          </span>
          <Num value={row.queuePressure} digits={2} />
        </span>
      ),
      sort: (row) => row.queuePressure,
    },
    {
      key: "conf",
      header: "Confidence",
      align: "right",
      width: 106,
      render: (row) => <Num value={row.confidence} digits={2} />,
      sort: (row) => row.confidence,
    },
    {
      key: "observed",
      header: "Observed",
      align: "right",
      width: 124,
      render: (row) => <span className="num text-[var(--text-3)]">{formatUtc(row.observedAt)}</span>,
      sort: (row) => row.observedAt,
    },
  ];

  const adapterColumns: Array<Column<FeedAdapter>> = [
    {
      key: "name",
      header: "Adapter",
      render: (row) => <span className="text-[var(--text-2)]">{row.name}</span>,
      sort: (row) => row.name,
    },
    {
      key: "provider",
      header: "Provider",
      width: 200,
      render: (row) => <span className="text-[var(--text-3)]">{row.provider}</span>,
      sort: (row) => row.provider,
    },
    {
      key: "granularity",
      header: "Granularity",
      width: 168,
      render: (row) => <span className="num text-[var(--text-3)]">{row.granularity}</span>,
      sort: (row) => row.granularity,
    },
    {
      key: "status",
      header: "Status",
      width: 124,
      render: (row) => <ProvenanceTag status={row.status} ageHours={row.ageHours} />,
      sort: (row) => row.status,
    },
    {
      key: "conf",
      header: "Confidence",
      align: "right",
      width: 106,
      render: (row) => <Num value={row.confidence} digits={2} />,
      sort: (row) => row.confidence,
    },
    {
      key: "observed",
      header: "Observed",
      align: "right",
      width: 124,
      render: (row) => <span className="num text-[var(--text-3)]">{formatUtc(row.observedAt)}</span>,
      sort: (row) => row.observedAt,
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Vessels"
        context={<span>Satellite-AIS activity at the berth line, and the feeds behind it</span>}
        meta={<span className="num">observed {formatUtc(vessels.data?.observedAt ?? null)}</span>}
      />

      <StatStrip
        size="sm"
        items={[
          { label: "Ports reporting", value: rows.length, note: "with an AIS activity row" },
          {
            label: "Daily port calls",
            value: totalCalls.toFixed(0),
            note: "aggregate across the network",
          },
          {
            label: "Vessels waiting",
            value: totalQueue.toFixed(1),
            tone: totalQueue > 0 ? "warn" : "ok",
            note: "anchorage buildup, summed",
          },
          {
            label: "Worst queue pressure",
            value: worst?.queuePressure?.toFixed(2) ?? "n/a",
            tone: (worst?.queuePressure ?? 0) >= 0.65 ? "crit" : "warn",
            note: worst?.name ?? "none",
          },
          {
            label: "Feed adapters",
            value: adapters.data?.length ?? 0,
            note: `${(adapters.data ?? []).filter((a) => a.status === "UNAVAILABLE").length} unavailable`,
          },
        ]}
      />

      <PageBody padded={false} className="flex min-h-0 overflow-hidden">
        <div className="relative min-w-0 flex-1 border-r border-[var(--line)]">
          <OperationsMap
            data={map.data}
            visible={layers}
            labels={map.labels}
            selected={selected}
            onSelect={setSelected}
            overlay={
              <>
                <MapControlPanel
                  toggles={[
                    { key: "vessels", label: "AIS activity", count: map.counts.vessels },
                    { key: "ports", label: "Ports", count: map.counts.ports },
                    { key: "chokepoints", label: "Chokepoints", count: map.counts.chokepoints },
                    { key: "graticule", label: "Graticule" },
                  ]}
                  visible={layers}
                  onToggle={(key) => setLayers((prev) => ({ ...prev, [key]: !prev[key] }))}
                />
                <MapLegend
                  weatherActive={false}
                  extra={[
                    { label: "Low queue pressure", color: "#4c9fcb", shape: "dot" },
                    { label: "Elevated", color: "#d3a02f", shape: "dot" },
                    { label: "High", color: "#d05a4c", shape: "dot" },
                  ]}
                  note={vessels.data?.basis}
                />
              </>
            }
          />
        </div>

        <aside className="flex w-[520px] shrink-0 flex-col overflow-hidden 2xl:w-[600px]">
          <Panel
            title="Activity by port"
            note={`${rows.length} ports`}
            className="min-h-0 flex-1 rounded-none border-x-0 border-t-0"
          >
            <DataTable
              rows={rows}
              columns={columns}
              rowKey={(row) => row.portCode}
              selectedKey={selected}
              onRowClick={(row) => setSelected(row.portCode)}
              initialSort="pressure"
            />
          </Panel>

          <Panel
            title="Feed adapters"
            note={`${adapters.data?.length ?? 0}`}
            className="h-[300px] shrink-0 rounded-none border-x-0 border-b-0"
          >
            {adapters.isLoading ? (
              <LoadingPanel label="Loading adapters" rows={4} />
            ) : (adapters.data?.length ?? 0) === 0 ? (
              <EmptyState
                title="No adapters registered"
                detail="This run exported no feed-adapter roster."
              />
            ) : (
              <DataTable
                rows={adapters.data ?? []}
                columns={adapterColumns}
                rowKey={(row) => row.key}
                initialSort="status"
                initialDirection="asc"
              />
            )}
          </Panel>
        </aside>
      </PageBody>

      <div className="shrink-0 border-t border-[var(--line)] bg-[var(--panel)] px-4 py-2">
        <KeyValue label="Basis">
          <span className="text-[11.5px] text-[var(--text-2)]">
            {vessels.data?.basis ??
              "Aggregate daily port-call activity, not per-vessel AIS tracks."}
          </span>
        </KeyValue>
      </div>
    </Page>
  );
}
