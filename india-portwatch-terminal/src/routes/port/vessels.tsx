import { Link, createFileRoute } from "@tanstack/react-router";

import { PortSwitcher, usePortContext } from "@/components/app/port-context";
import { ColumnChart } from "@/components/kit/charts";
import { Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import {
  KeyValue,
  Num,
  Pill,
  ProvenanceTag,
  formatUtc,
  riskTone,
} from "@/components/kit/primitives";
import { EmptyState, FailureState, LoadingPanel } from "@/components/kit/states";
import { DataTable, type Column } from "@/components/kit/table";
import { useFleet, useForecast, useVessels } from "@/services/hooks";
import type { FleetRow, ForecastPoint } from "@/types/portwatch";

export const Route = createFileRoute("/port/vessels")({ component: PortVessels });

interface CallRow {
  vessel: FleetRow;
  role: "declared call" | "diverting here" | "may divert away";
  day: number | null;
  target: ForecastPoint | null;
}

function PortVessels() {
  const { port, query } = usePortContext();
  const fleet = useFleet();
  const vessels = useVessels();
  const forecast = useForecast(port?.code);

  if (query.isLoading) return <LoadingPanel label="Loading arrivals" rows={8} />;
  if (!port) return <FailureState error={new Error("No port selected.")} />;

  const rows = forecast.data ?? [];
  const byDay = new Map(rows.map((row) => [row.day, row]));
  const activity = (vessels.data?.vessels ?? []).find((entry) => entry.portCode === port.code) ?? null;

  const calls: CallRow[] = (fleet.data ?? [])
    .filter(
      (vessel) =>
        vessel.intendedPortCode === port.code || vessel.recommendedPortCode === port.code,
    )
    .map((vessel) => {
      const day = vessel.bestArrivalDay == null ? null : Math.round(vessel.bestArrivalDay);
      const role: CallRow["role"] =
        vessel.intendedPortCode === port.code && vessel.recommendedPortCode === port.code
          ? "declared call"
          : vessel.recommendedPortCode === port.code
            ? "diverting here"
            : "may divert away";
      return { vessel, role, day, target: day == null ? null : (byDay.get(day) ?? null) };
    });

  const lowestWait = rows.reduce<ForecastPoint | null>(
    (best, row) => (!best || row.delayHoursP50 < best.delayHoursP50 ? row : best),
    null,
  );

  const columns: Array<Column<CallRow>> = [
    {
      key: "vessel",
      header: "Vessel",
      render: (row) => (
        <Link
          to="/vessel/$vesselId"
          params={{ vesselId: row.vessel.id }}
          className="text-[var(--text)] hover:text-[var(--info)]"
        >
          {row.vessel.name}
        </Link>
      ),
      sort: (row) => row.vessel.name,
    },
    {
      key: "id",
      header: "Vessel ID",
      width: 138,
      hint: "Optimizer identifier — this artefact carries no IMO number",
      render: (row) => <span className="num text-[var(--text-3)]">{row.vessel.id}</span>,
      sort: (row) => row.vessel.id,
    },
    {
      key: "role",
      header: "Relationship",
      width: 138,
      render: (row) => (
        <Pill tone={row.role === "may divert away" ? "warn" : "info"}>{row.role}</Pill>
      ),
      sort: (row) => row.role,
    },
    {
      key: "day",
      header: "Arrival day",
      align: "right",
      width: 104,
      render: (row) =>
        row.day == null ? (
          <span className="num text-[var(--text-3)]">n/a</span>
        ) : (
          <span className="num">
            +{row.day}
            <span className="ml-1 text-[10px] text-[var(--text-3)]">{row.target?.dateLabel}</span>
          </span>
        ),
      sort: (row) => row.day,
    },
    {
      key: "wait",
      header: "Predicted wait",
      align: "right",
      width: 120,
      render: (row) => <Num value={row.target?.delayHoursP50} unit="h" />,
      sort: (row) => row.target?.delayHoursP50 ?? null,
    },
    {
      key: "congestion",
      header: "Congestion that day",
      align: "right",
      width: 152,
      render: (row) =>
        row.target ? (
          <span className="num">
            {row.target.q50.toFixed(1)}
            <span className="ml-1 text-[10px] text-[var(--text-3)]">
              {row.target.q10.toFixed(0)}–{row.target.q90.toFixed(0)}
            </span>
          </span>
        ) : (
          <span className="num text-[var(--text-3)]">n/a</span>
        ),
      sort: (row) => row.target?.q50 ?? null,
    },
    {
      key: "buffer",
      header: "Buffer",
      align: "right",
      width: 84,
      render: (row) => <Num value={row.vessel.bufferHours} digits={0} unit="h" />,
      sort: (row) => row.vessel.bufferHours,
    },
    {
      key: "conf",
      header: "Confidence",
      align: "right",
      width: 104,
      render: (row) => <Num value={row.target?.confidence} digits={0} scale={100} unit="%" />,
      sort: (row) => row.target?.confidence ?? null,
    },
    {
      key: "action",
      header: "Action",
      width: 176,
      render: (row) => (
        <span className="text-[var(--text-2)]">
          {row.vessel.reroute
            ? row.vessel.recommendedPortCode === port.code
              ? "Accept diverted call"
              : "Reroute advised"
            : "Keep intended call"}
        </span>
      ),
      sort: (row) => (row.vessel.reroute ? 1 : 0),
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Vessels"
        context={
          <>
            <span>{port.name}</span>
            <span className="num">{port.code}</span>
          </>
        }
        meta={
          <>
            <span className="num">observed {formatUtc(activity?.observedAt ?? port.observedAt)}</span>
            <ProvenanceTag status={port.dataStatus} ageHours={port.dataAgeHours} />
          </>
        }
        actions={<PortSwitcher />}
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "Daily port calls",
            value: activity?.dailyPortCalls?.toFixed(1) ?? port.vesselCalls?.toFixed(1) ?? "n/a",
            note: "satellite-AIS aggregate, not per-vessel tracks",
          },
          {
            label: "Queue buildup",
            value: activity?.queueBuildup?.toFixed(1) ?? "n/a",
            tone: (activity?.queuePressure ?? 0) >= 0.6 ? "warn" : "info",
            note: `queue pressure ${activity?.queuePressure?.toFixed(2) ?? "n/a"}`,
          },
          {
            label: "Declared calls tracked",
            value: calls.length,
            note: `${fleet.data?.length ?? 0} vessels in the routing roster`,
          },
          {
            label: "Lowest predicted wait",
            value: lowestWait ? lowestWait.delayHoursP50.toFixed(1) : "n/a",
            unit: "h",
            tone: "ok",
            note: lowestWait ? `day +${lowestWait.day} · ${lowestWait.dateLabel}` : "no forecast",
          },
          {
            label: "AIS confidence",
            value: activity?.confidence?.toFixed(2) ?? port.aisConfidence?.toFixed(2) ?? "n/a",
            note: "feed-level, not per vessel",
          },
        ]}
      />

      <PageBody className="grid grid-cols-1 gap-3 xl:grid-cols-[1fr_340px]">
        <Panel
          title="Calls scored against this port's forecast"
          note={`${calls.length} of ${fleet.data?.length ?? 0}`}
          className="min-h-[280px]"
        >
          {calls.length === 0 ? (
            <EmptyState
              title="No declared calls"
              detail={
                <>
                  The routing roster in this run carries{" "}
                  <span className="num">{fleet.data?.length ?? 0}</span> vessels and none of
                  them declares {port.short} as an intended or alternative call. Aggregate
                  arrival pressure for the port is still measured — see the AIS activity
                  panel.
                </>
              }
            />
          ) : (
            <DataTable
              rows={calls}
              columns={columns}
              rowKey={(row) => row.vessel.id}
              initialSort="day"
              initialDirection="asc"
            />
          )}
        </Panel>

        <div className="flex min-w-0 flex-col gap-3">
          <Panel title="When should arrivals be scheduled?">
            <div className="p-3">
              {rows.length ? (
                <>
                  <ColumnChart
                    height={116}
                    points={rows.map((row) => ({
                      label: row.dateLabel,
                      value: row.delayHoursP50,
                      tone: row.day === lowestWait?.day ? "ok" : "info",
                    }))}
                  />
                  <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11.5px] leading-snug text-[var(--text-3)]">
                    Predicted berth wait per horizon day. The green column is the lowest
                    predicted wait in the window — it is a description of the forecast, not
                    a scheduling instruction; the instruction is on the Decisions screen.
                  </p>
                </>
              ) : (
                <p className="py-6 text-center text-[11.5px] text-[var(--text-3)]">
                  No forecast rows for this port.
                </p>
              )}
            </div>
          </Panel>

          <Panel title="AIS activity" note={activity ? "IMF PortWatch" : undefined}>
            {activity ? (
              <div className="px-3 py-2">
                <KeyValue label="Daily port calls" dense>
                  <Num value={activity.dailyPortCalls} digits={1} />
                </KeyValue>
                <KeyValue label="Queue buildup" dense>
                  <Num value={activity.queueBuildup} digits={1} />
                </KeyValue>
                <KeyValue label="Waiting proxy" dense>
                  <Num value={activity.waitingProxy} digits={1} />
                </KeyValue>
                <KeyValue label="Queue pressure" dense>
                  <Num value={activity.queuePressure} digits={2} />
                </KeyValue>
                <KeyValue label="Observed" dense>
                  <span className="num text-[11px]">{formatUtc(activity.observedAt)}</span>
                </KeyValue>
                <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11px] leading-snug text-[var(--text-3)]">
                  {activity.basis}
                </p>
              </div>
            ) : (
              <p className="p-3 text-[11.5px] text-[var(--text-3)]">
                No AIS activity row for this port in the current run.
              </p>
            )}
          </Panel>

          <Panel title="Entry risk">
            <div className="px-3 py-2">
              <KeyValue label="Regime" dense>
                <Pill tone={riskTone(port.risk)}>{port.regime}</Pill>
              </KeyValue>
              <KeyValue label="Transition risk 24h" dense>
                <Num value={port.transitionRisk24h} digits={3} />
              </KeyValue>
              <KeyValue label="Model disagreement" dense>
                <Num value={port.modelDisagreement} digits={2} tone="unc" />
              </KeyValue>
              <KeyValue label="Weather impact" dense>
                <Num value={port.weatherImpact} digits={3} />
              </KeyValue>
            </div>
          </Panel>
        </div>
      </PageBody>
    </Page>
  );
}
