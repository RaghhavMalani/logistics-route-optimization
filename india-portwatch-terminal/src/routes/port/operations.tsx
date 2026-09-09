import { createFileRoute } from "@tanstack/react-router";

import { PortSwitcher, usePortContext } from "@/components/app/port-context";
import { BarRanking, ColumnChart, SeriesChart } from "@/components/kit/charts";
import { Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import { KeyValue, Num, ProvenanceTag, formatDate, formatUtc } from "@/components/kit/primitives";
import { ScreenFallback } from "@/components/kit/states";
import { DataTable, type Column } from "@/components/kit/table";
import { useChain, useForecast } from "@/services/hooks";
import type { PortSnapshot } from "@/types/portwatch";

export const Route = createFileRoute("/port/operations")({ component: PortOperations });

/** Peer comparison row: this port against the rest of the network. */
interface PeerRow {
  code: string;
  name: string;
  calls: number | null;
  anchorage: number | null;
  utilisation: number | null;
  throughput: number | null;
  queue: number | null;
  isSelf: boolean;
}

function PortOperations() {
  const { port, ports, query } = usePortContext();
  const chain = useChain(port?.code);
  const forecast = useForecast(port?.code);

  if (
    query.isLoading ||
    chain.isLoading ||
    query.isError ||
    chain.isError ||
    !port ||
    !chain.data
  ) {
    return (
      <ScreenFallback
        title="Operations"
        isLoading={query.isLoading || chain.isLoading}
        error={
          query.error ??
          chain.error ??
          (port && chain.data ? null : new Error("No observed state for this port."))
        }
        retry={() => void chain.refetch()}
        label="Loading operational state"
      />
    );
  }

  const state = chain.data.state;
  const history = state.congestionHistory ?? [];
  const rows = forecast.data ?? [];

  const peers: PeerRow[] = ports.map((entry: PortSnapshot) => ({
    code: entry.code,
    name: entry.name,
    calls: entry.vesselCalls,
    anchorage: entry.anchorageCount,
    utilisation: entry.utilization,
    throughput: entry.throughputTonnes,
    queue: entry.queuePressure,
    isSelf: entry.code === port.code,
  }));

  const peerColumns: Array<Column<PeerRow>> = [
    {
      key: "name",
      header: "Port",
      render: (row) => (
        <span className={row.isSelf ? "font-medium text-[var(--text)]" : ""}>{row.name}</span>
      ),
      sort: (row) => row.name,
    },
    {
      key: "calls",
      header: "Calls / day",
      align: "right",
      width: 96,
      render: (row) => <Num value={row.calls} digits={1} />,
      sort: (row) => row.calls,
    },
    {
      key: "anchorage",
      header: "Anchorage",
      align: "right",
      width: 96,
      render: (row) => <Num value={row.anchorage} digits={1} />,
      sort: (row) => row.anchorage,
    },
    {
      key: "queue",
      header: "Queue pressure",
      align: "right",
      width: 120,
      render: (row) => <Num value={row.queue} digits={2} />,
      sort: (row) => row.queue,
    },
    {
      key: "utilisation",
      header: "Utilisation",
      align: "right",
      width: 104,
      render: (row) => <Num value={row.utilisation} digits={0} scale={100} unit="%" />,
      sort: (row) => row.utilisation,
    },
    {
      key: "throughput",
      header: "Throughput t",
      align: "right",
      width: 116,
      render: (row) => <Num value={row.throughput} digits={0} />,
      sort: (row) => row.throughput,
    },
  ];

  const pressures = [
    { label: "Queue pressure", value: state.queuePressure },
    { label: "Capacity pressure", value: state.capacityPressure },
    { label: "Berth pressure", value: state.berthPressure },
    { label: "Turnaround pressure", value: state.turnaroundPressure },
    { label: "Arrival clustering", value: state.arrivalClustering },
    { label: "Queue momentum", value: state.queueMomentum },
    { label: "Throughput stress", value: state.throughputStress },
    { label: "Anomaly score", value: state.anomalyScore },
    { label: "Disruption pressure", value: state.disruptionPressure },
    { label: "Weather impact", value: state.weatherImpact },
  ].map((item) => ({
    ...item,
    tone:
      item.value == null
        ? ("neutral" as const)
        : item.value >= 0.7
          ? ("crit" as const)
          : item.value >= 0.45
            ? ("warn" as const)
            : ("info" as const),
  }));

  return (
    <Page>
      <PageHeader
        title="Operations"
        context={
          <>
            <span>{port.name}</span>
            <span className="num">{port.code}</span>
          </>
        }
        meta={
          <>
            <span className="num">observed {formatUtc(state.observedAt)}</span>
            <ProvenanceTag status={state.dataStatus} ageHours={state.dataAgeHours} />
          </>
        }
        actions={<PortSwitcher />}
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "Calls per day",
            value: state.vesselCalls?.toFixed(1) ?? "n/a",
            note: "satellite-AIS port calls",
          },
          {
            label: "Anchorage waiting",
            value: state.anchorageCount?.toFixed(1) ?? "n/a",
            tone: (state.queuePressure ?? 0) >= 0.6 ? "warn" : "info",
            note: `queue pressure ${state.queuePressure?.toFixed(2) ?? "n/a"}`,
          },
          {
            label: "Berth utilisation",
            value: state.utilization != null ? `${(state.utilization * 100).toFixed(0)}%` : "n/a",
            note: `capacity pressure ${state.capacityPressure?.toFixed(2) ?? "n/a"}`,
          },
          {
            label: "Throughput",
            value: state.throughputTonnes?.toFixed(0) ?? "n/a",
            unit: "t",
            note: `stress ${state.throughputStress?.toFixed(2) ?? "n/a"}`,
          },
          {
            label: "Arrival clustering",
            value: state.arrivalClustering?.toFixed(2) ?? "n/a",
            tone: (state.arrivalClustering ?? 0) >= 0.5 ? "warn" : "info",
            note: "1.0 = every arrival in one window",
          },
          {
            label: "Data quality",
            value: state.dataQuality?.toFixed(2) ?? "n/a",
            tone: (state.dataQuality ?? 1) >= 0.75 ? "ok" : "warn",
            note: `AIS confidence ${state.aisConfidence?.toFixed(2) ?? "n/a"}`,
          },
        ]}
      />

      <PageBody className="grid grid-cols-1 gap-3 xl:grid-cols-[1.55fr_1fr]">
        <div className="flex min-w-0 flex-col gap-3">
          <Panel
            title="Is the queue building or draining?"
            note={`${history.length} observed days`}
          >
            <div className="p-3">
              <SeriesChart
                height={170}
                yUnit="congestion index 0–100"
                series={[
                  {
                    name: "Observed congestion",
                    tone: "info",
                    area: true,
                    points: history.map((point) => ({
                      label: formatDate(point.date),
                      value: point.value,
                    })),
                  },
                ]}
              />
              <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11.5px] leading-snug text-[var(--text-3)]">
                Observed pressure at the berth line, not a forecast. The forecast band
                for the same port is on the Forecast screen.
              </p>
            </div>
          </Panel>

          <Panel title="What load is the forecast putting on the next ten days?">
            <div className="p-3">
              {rows.length ? (
                <>
                  <ColumnChart
                    height={120}
                    threshold={50}
                    points={rows.map((row) => ({
                      label: row.dateLabel,
                      value: row.congestionIndex,
                      tone:
                        row.congestionIndex >= 65
                          ? "crit"
                          : row.congestionIndex >= 50
                            ? "warn"
                            : "ok",
                    }))}
                  />
                  <div className="mt-3 border-t border-[var(--line)] pt-2">
                    <SeriesChart
                      height={110}
                      yUnit="predicted berth wait, hours"
                      series={[
                        {
                          name: "Predicted wait",
                          tone: "warn",
                          points: rows.map((row) => ({
                            label: row.dateLabel,
                            value: row.delayHoursP50,
                          })),
                        },
                      ]}
                    />
                  </div>
                </>
              ) : (
                <p className="py-6 text-center text-[11.5px] text-[var(--text-3)]">
                  No forecast rows for this port in the current run.
                </p>
              )}
            </div>
          </Panel>

          <Panel
            title="How does this port sit against the rest of the network?"
            note={`${peers.length} ports`}
            className="min-h-[240px]"
          >
            <DataTable
              rows={peers}
              columns={peerColumns}
              rowKey={(row) => row.code}
              selectedKey={port.code}
              initialSort="calls"
              rowTone={(row) => (row.isSelf ? "var(--info)" : null)}
            />
          </Panel>
        </div>

        <div className="flex min-w-0 flex-col gap-3">
          <Panel title="Where is the pressure coming from?">
            <div className="p-3">
              <BarRanking
                items={pressures}
                valueFormatter={(value) => value.toFixed(2)}
              />
              <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11.5px] leading-snug text-[var(--text-3)]">
                Bounded 0–1 specialist features, exactly as the forecast model consumed
                them for this port on {formatDate(state.observedAt)}.
              </p>
            </div>
          </Panel>

          <Panel title="Capacity and turnaround">
            <div className="px-3 py-2">
              <KeyValue label="Capacity index (registry)">
                <Num value={state.capacityIndex} digits={2} />
              </KeyValue>
              <KeyValue label="Berths (registry)">
                <Num value={state.berthCount} digits={0} />
              </KeyValue>
              <KeyValue label="Vessel density">
                <Num value={state.vesselDensity} digits={2} />
              </KeyValue>
              <KeyValue label="Turnaround pressure">
                <Num value={state.turnaroundPressure} digits={2} />
              </KeyValue>
              <KeyValue label="Queue momentum">
                <Num value={state.queueMomentum} digits={2} />
              </KeyValue>
              <KeyValue label="Specialist stress (composite)">
                <Num value={state.specialistStress} digits={2} />
              </KeyValue>
              <KeyValue label="Disruption exposure">
                <Num value={state.disruptionExposure} digits={2} />
              </KeyValue>
              <KeyValue label="Weather persistence">
                <Num value={state.weatherPersistence} digits={2} />
              </KeyValue>
            </div>
          </Panel>
        </div>
      </PageBody>
    </Page>
  );
}
