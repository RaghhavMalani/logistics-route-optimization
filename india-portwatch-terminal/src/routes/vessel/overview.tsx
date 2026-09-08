import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { useMemo, useState } from "react";

import { statusTone, useFleetIntel, type VesselIntel } from "@/components/app/fleet-context";
import { Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import {
  Dot,
  Num,
  Pill,
  formatUtc,
  riskLabel,
  riskTone,
  severityTone,
} from "@/components/kit/primitives";
import { EmptyState, FailureState, LoadingPanel } from "@/components/kit/states";
import { DataTable, type Column } from "@/components/kit/table";
import { MapControlPanel, MapLegend } from "@/components/map/MapControls";
import { OperationsMap } from "@/components/map/OperationsMap";
import type { LayerKey } from "@/components/map/basemap";
import type { Lane } from "@/components/map/layers";
import { useOperationalMap } from "@/components/map/useOperationalMap";
import { useHealth } from "@/services/hooks";

export const Route = createFileRoute("/vessel/overview")({ component: VesselOverview });

const FLEET_LAYERS: Record<LayerKey, boolean> = {
  ports: true,
  vessels: false,
  weather: true,
  stations: false,
  storms: true,
  routes: true,
  chokepoints: true,
  events: false,
  zones: false,
  graticule: true,
};

function formatEta(date: Date | null): string {
  if (!date) return "—";
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${String(date.getUTCDate()).padStart(2, "0")} ${months[date.getUTCMonth()]}`;
}

function VesselOverview() {
  const { intel, ranked, isLoading, error, refetch, ports, weather, events, alerts } =
    useFleetIntel();
  const health = useHealth();
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(FLEET_LAYERS);
  const [selected, setSelected] = useState<string | null>(null);

  /** One corridor per vessel: declared call, plus the alternative when advised. */
  const lanes = useMemo<Lane[]>(() => {
    const out: Lane[] = [];
    for (const row of intel) {
      const from = row.destination?.location;
      const to = row.alternative?.location;
      if (from && to && row.vessel.reroute) {
        out.push({
          id: `alt-${row.vessel.id}`,
          from,
          to,
          color: "#d3a02f",
          width: 1.4,
          opacity: 0.75,
          dashed: true,
          label: `${row.vessel.name} alternative call`,
        });
      }
    }
    return out;
  }, [intel]);

  const emphasise = useMemo(
    () =>
      new Set(
        intel.flatMap((row) =>
          [row.vessel.intendedPortCode, row.vessel.recommendedPortCode].filter(
            (code): code is string => Boolean(code),
          ),
        ),
      ),
    [intel],
  );

  const map = useOperationalMap({
    ports,
    weather,
    vessels: [],
    events,
    selected,
    emphasise,
    extraLanes: lanes,
  });

  if (isLoading) return <LoadingPanel label="Loading fleet exposure" rows={9} />;
  if (error) return <FailureState error={error} retry={refetch} />;

  const reroutes = intel.filter((row) => row.vessel.reroute);
  const arriving48 = intel.filter(
    (row) => (row.vessel.intendedArrivalDay ?? row.vessel.bestArrivalDay ?? 99) <= 2,
  );
  const highRisk = intel.filter(
    (row) => (row.vessel.intendedCongestionProbability ?? 0) >= 0.5,
  );
  const weatherExposed = intel.filter((row) => (row.weather?.impactScore ?? 0) >= 0.15);
  const chokepointExposed = intel.filter((row) =>
    row.exposure.some((entry) => entry.event.chokepoint),
  );

  const columns: Array<Column<VesselIntel>> = [
    {
      key: "vessel",
      header: "Vessel",
      width: 168,
      render: (row) => (
        <Link
          to="/vessel/$vesselId"
          params={{ vesselId: row.vessel.id }}
          className="flex items-center gap-1.5 text-[var(--text)] hover:text-[var(--info)]"
        >
          <Dot tone={statusTone(row.status)} />
          {row.vessel.name}
        </Link>
      ),
      sort: (row) => row.vessel.name,
    },
    {
      key: "destination",
      header: "Declared call",
      render: (row) => (
        <span className="text-[var(--text-2)]">
          {row.vessel.intendedPortName ?? row.vessel.intendedPortCode ?? "n/a"}
        </span>
      ),
      sort: (row) => row.vessel.intendedPortName,
    },
    {
      key: "eta",
      header: "ETA",
      align: "right",
      width: 108,
      render: (row) => (
        <span className="num">
          {formatEta(row.etaDate)}
          <span className="ml-1 text-[10px] text-[var(--text-3)]">
            +{row.vessel.intendedArrivalDay ?? row.vessel.bestArrivalDay ?? "?"}
          </span>
        </span>
      ),
      sort: (row) => row.vessel.intendedArrivalDay ?? row.vessel.bestArrivalDay,
    },
    {
      key: "wait",
      header: "Predicted wait",
      align: "right",
      width: 118,
      render: (row) => <Num value={row.vessel.intendedWaitHours} unit="h" />,
      sort: (row) => row.vessel.intendedWaitHours,
    },
    {
      key: "congestion",
      header: "Destination",
      align: "right",
      width: 136,
      render: (row) =>
        row.destination ? (
          <span className="flex items-center justify-end gap-2">
            <Num value={row.destination.congestionIndex} />
            <Pill tone={riskTone(row.destination.risk)}>{riskLabel(row.destination.risk)}</Pill>
          </span>
        ) : (
          <span className="num text-[var(--text-3)]">n/a</span>
        ),
      sort: (row) => row.destination?.congestionIndex ?? null,
    },
    {
      key: "wx",
      header: "Weather",
      align: "right",
      width: 96,
      render: (row) => (
        <Num
          value={row.weather?.impactScore}
          digits={3}
          tone={(row.weather?.impactScore ?? 0) >= 0.35 ? "warn" : undefined}
        />
      ),
      sort: (row) => row.weather?.impactScore ?? null,
    },
    {
      key: "status",
      header: "Status",
      width: 148,
      render: (row) => <Pill tone={statusTone(row.status)}>{row.status}</Pill>,
      sort: (row) => row.status,
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Fleet Overview"
        context={<span>Where the fleet is exposed right now</span>}
        meta={
          <>
            <span className="num">
              origin{" "}
              <span className="text-[var(--text-2)]">
                {formatUtc(intel[0]?.vessel.originDate ?? health.data?.forecastOrigin ?? null)}
              </span>
            </span>
            <span className="num">{intel[0]?.vessel.source ?? "ROUTE_OPTIMIZER"}</span>
          </>
        }
      />

      <StatStrip
        items={[
          {
            label: "Vessels scored",
            value: intel.length,
            note: "against the live quantile forecast",
          },
          {
            label: "Arriving within 48h",
            value: arriving48.length,
            tone: arriving48.length ? "info" : "neutral",
            note: arriving48.map((row) => row.vessel.name.replace("MV ", "")).join(" · ") || "none",
          },
          {
            label: "Reroutes advised",
            value: reroutes.length,
            tone: reroutes.length ? "warn" : "ok",
            note: "only where the saving clears the diversion cost",
          },
          {
            label: "High port-wait risk",
            value: highRisk.length,
            tone: highRisk.length ? "crit" : "ok",
            note: "P(congestion) ≥ 0.50 on the scored day",
          },
          {
            label: "Weather exposure",
            value: weatherExposed.length,
            tone: weatherExposed.length ? "warn" : "ok",
            note: "destination impact index ≥ 0.15",
          },
          {
            label: "Chokepoint exposure",
            value: chokepointExposed.length,
            tone: chokepointExposed.length ? "warn" : "ok",
            note: "measured lane exposure to an active event",
          },
        ]}
      />

      <PageBody padded={false} className="flex min-h-0 overflow-hidden">
        <div className="flex min-w-0 flex-1 flex-col border-r border-[var(--line)]">
          <div className="relative min-h-0 flex-1">
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
                      { key: "ports", label: "Ports", count: map.counts.ports },
                      { key: "routes", label: "Corridors", count: map.counts.routes },
                      { key: "chokepoints", label: "Chokepoints", count: map.counts.chokepoints },
                      {
                        key: "weather",
                        label: "Weather field",
                        count: map.counts.weather,
                        disabled: (map.counts.weather ?? 0) === 0,
                        disabledReason: "No weather artefact in this run",
                      },
                      {
                        key: "storms",
                        label: "Storm envelopes",
                        count: map.counts.storms,
                        disabled: (map.counts.storms ?? 0) === 0,
                        disabledReason: "No storm flag on any port in this run",
                      },
                      { key: "graticule", label: "Graticule" },
                    ]}
                    visible={layers}
                    onToggle={(key) => setLayers((prev) => ({ ...prev, [key]: !prev[key] }))}
                    weatherField={map.weatherField}
                    onWeatherField={map.setWeatherField}
                    weatherAvailability={map.availability}
                  />
                  <MapLegend
                    weatherField={map.weatherField}
                    weatherActive={layers.weather}
                    extra={[
                      { label: "Alternative call", color: "#d3a02f", shape: "line" },
                      { label: "Chokepoint", color: "#4c9fcb", shape: "ring" },
                    ]}
                    note="The routing artefact carries declared calls and arrival windows, not AIS tracks — no vessel position is drawn."
                  />
                </>
              }
            />
          </div>

          <div className="h-[268px] shrink-0 border-t border-[var(--line)]">
            <Panel
              title="Fleet"
              note={`${intel.length} vessels`}
              className="h-full rounded-none border-0"
            >
              {intel.length === 0 ? (
                <EmptyState
                  title="No vessels scored"
                  detail="The routing artefact is empty for this run."
                />
              ) : (
                <DataTable
                  rows={intel}
                  columns={columns}
                  rowKey={(row) => row.vessel.id}
                  selectedKey={selected}
                  onRowClick={(row) => setSelected(row.vessel.intendedPortCode ?? null)}
                  initialSort="eta"
                  initialDirection="asc"
                />
              )}
            </Panel>
          </div>
        </div>

        <aside className="flex w-[380px] shrink-0 flex-col overflow-y-auto 2xl:w-[430px]">
          <Panel
            title="Recommended actions"
            note={`${ranked.length}`}
            className="shrink-0 rounded-none border-x-0 border-t-0"
          >
            <ul>
              {ranked.map((row, index) => (
                <li key={row.vessel.id} className="border-b border-[var(--line)]/50 last:border-0">
                  <Link
                    to="/vessel/$vesselId"
                    params={{ vesselId: row.vessel.id }}
                    className="block px-3 py-2.5 transition-colors hover:bg-[var(--panel-2)]"
                  >
                    <div className="flex items-center gap-2">
                      <span className="num text-[10.5px] text-[var(--text-3)]">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <Pill tone={statusTone(row.status)}>{row.status}</Pill>
                      <span className="ml-auto text-[12px] font-medium text-[var(--text)]">
                        {row.vessel.name}
                      </span>
                    </div>
                    <p className="mt-1 text-[12px] leading-snug text-[var(--text-2)]">
                      {row.action}
                    </p>
                    <p className="mt-0.5 text-[11px] leading-snug text-[var(--text-3)]">
                      {row.why}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel
            title="Network alerts"
            note={`${alerts.length}`}
            className="min-h-0 flex-1 rounded-none border-x-0 border-b-0"
            scroll
          >
            {alerts.length === 0 ? (
              <p className="px-3 py-3 text-[11.5px] text-[var(--text-3)]">
                No alerts raised across the network for the current forecast.
              </p>
            ) : (
              <ul>
                {alerts.slice(0, 12).map((alert) => {
                  const touchesFleet = intel.some(
                    (row) => row.vessel.intendedPortCode === alert.portCode,
                  );
                  return (
                    <li
                      key={alert.id}
                      className="border-b border-[var(--line)]/50 px-3 py-2 last:border-0"
                    >
                      <div className="flex items-center gap-2">
                        <Pill tone={severityTone(alert.severity)}>{alert.severity}</Pill>
                        {touchesFleet ? <Pill tone="warn">on our lane</Pill> : null}
                        <span className="num ml-auto text-[10px] text-[var(--text-3)]">
                          {alert.portCode}
                        </span>
                      </div>
                      <p className="mt-1 text-[11.5px] leading-snug text-[var(--text-2)]">
                        {alert.text}
                      </p>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="border-t border-[var(--line)] px-3 py-2">
              <Link
                to="/vessel/alerts"
                className="inline-flex items-center gap-1 text-[11.5px] text-[var(--info)] hover:underline"
              >
                All alerts and events <ArrowUpRight size={11} />
              </Link>
            </div>
          </Panel>
        </aside>
      </PageBody>
    </Page>
  );
}
