import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { PortSwitcher, usePortContext } from "@/components/app/port-context";
import { QuantileChart, Sparkline } from "@/components/kit/charts";
import { Page, PageBody, PageHeader, Panel, Section, StatStrip } from "@/components/kit/layout";
import {
  KeyValue,
  Num,
  Pill,
  ProvenanceTag,
  formatDate,
  formatUtc,
  riskLabel,
  riskTone,
} from "@/components/kit/primitives";
import { FailureState, LoadingPanel } from "@/components/kit/states";
import { MapControlPanel, MapLegend } from "@/components/map/MapControls";
import { OperationsMap } from "@/components/map/OperationsMap";
import type { LayerKey } from "@/components/map/basemap";
import { useOperationalMap } from "@/components/map/useOperationalMap";
import { useForecast, useNews, useVessels, useWeather } from "@/services/hooks";

export const Route = createFileRoute("/port/overview")({ component: PortOverview });

/**
 * The port-local chart is zoomed past the weather field's own resolution, so
 * the field is off here and the station marks carry the reading instead. The
 * Weather screen shows the field at a zoom it can support.
 */
const PORT_LAYERS: Record<LayerKey, boolean> = {
  ports: true,
  vessels: true,
  weather: false,
  stations: true,
  storms: true,
  routes: false,
  chokepoints: false,
  events: false,
  zones: true,
  graticule: true,
};

function PortOverview() {
  const { port, ports, query } = usePortContext();
  const weather = useWeather();
  const vessels = useVessels();
  const news = useNews();
  const forecast = useForecast(port?.code);
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(PORT_LAYERS);

  const map = useOperationalMap({
    ports,
    weather: weather.data ?? [],
    vessels: vessels.data?.vessels ?? [],
    events: news.data?.events ?? [],
    selected: port?.code ?? null,
    zonesFor: port?.code ?? null,
    exposureLanes: false,
  });

  const centre = useMemo<[number, number]>(
    () => (port?.location ? [port.location.lon, port.location.lat] : [79.5, 15.5]),
    [port?.location],
  );

  if (query.isLoading) return <LoadingPanel label="Loading port digital twin" rows={10} />;
  if (query.isError) return <FailureState error={query.error} retry={() => void query.refetch()} />;
  if (!port) {
    return <FailureState error={new Error("No port in the current artefact set.")} />;
  }

  const signal = (weather.data ?? []).find((entry) => entry.portCode === port.code) ?? null;
  const activity = (vessels.data?.vessels ?? []).find((entry) => entry.portCode === port.code) ?? null;
  const rows = forecast.data ?? [];
  const next24 = rows[0] ?? null;
  const peak = rows.reduce<(typeof rows)[number] | null>(
    (best, row) => (!best || row.congestionIndex > best.congestionIndex ? row : best),
    null,
  );
  const portAlerts = (news.data?.alerts ?? []).filter((alert) => alert.portCode === port.code);

  return (
    <Page>
      <PageHeader
        title={port.name}
        context={
          <>
            <span className="num">{port.code}</span>
            <Pill tone={riskTone(port.risk)}>{riskLabel(port.risk)}</Pill>
            <span className="truncate">{port.authority ?? "Authority not in registry"}</span>
          </>
        }
        meta={
          <>
            <span className="num">observed {formatUtc(port.observedAt)}</span>
            <ProvenanceTag
              status={port.dataStatus}
              ageHours={port.dataAgeHours}
              detail={`Port activity observed ${formatUtc(port.observedAt)}`}
            />
          </>
        }
        actions={<PortSwitcher />}
      />

      <StatStrip
        items={[
          {
            label: "Operating regime",
            value: port.regime,
            tone: riskTone(port.risk),
            note: `confidence ${((port.regimeConfidence ?? 0) * 100).toFixed(0)}% · ${port.expectedRemainingDays?.toFixed(1) ?? "n/a"}d expected remaining`,
          },
          {
            label: "Observed congestion",
            value: port.observedCongestionIndex?.toFixed(1) ?? "n/a",
            note: "index 0–100 · satellite-AIS derived",
          },
          {
            label: "Day-1 forecast",
            value: port.congestionIndex.toFixed(1),
            tone: port.congestionIndex >= 65 ? "crit" : port.congestionIndex >= 50 ? "warn" : "ok",
            note: `80% band ${port.forecastQ10?.toFixed(0) ?? "—"}–${port.forecastQ90?.toFixed(0) ?? "—"}`,
          },
          {
            label: "Berth wait",
            value: port.delayHours.toFixed(1),
            unit: "h",
            note: "predicted, from call pressure",
          },
          {
            label: "Anchorage",
            value: port.anchorageCount?.toFixed(1) ?? "n/a",
            tone: (port.queuePressure ?? 0) >= 0.6 ? "warn" : "info",
            note: `queue pressure ${port.queuePressure?.toFixed(2) ?? "n/a"}`,
          },
          {
            label: "Weather impact",
            value: signal?.impactScore?.toFixed(3) ?? "n/a",
            tone: (signal?.impactScore ?? 0) >= 0.35 ? "warn" : "ok",
            note: signal?.weatherRegime ?? "no marine feed",
          },
        ]}
      />

      <PageBody padded={false} className="flex min-h-0 overflow-hidden">
        <div className="relative min-w-0 flex-1 border-r border-[var(--line)]">
          <OperationsMap
            data={map.data}
            visible={layers}
            labels={map.labels}
            selected={port.code}
            center={centre}
            zoom={8.6}
            loadingLabel="Initialising port chart"
            overlay={
              <>
                <MapControlPanel
                  toggles={[
                    { key: "zones", label: "Approach geometry" },
                    { key: "ports", label: "Ports", count: map.counts.ports },
                    { key: "vessels", label: "AIS activity", count: map.counts.vessels },
                    {
                      key: "stations",
                      label: "Weather stations",
                      count: map.counts.stations,
                      disabled: (map.counts.stations ?? 0) === 0,
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
                  footer="Weather field resolution is coarser than this view; the regional field is on the Weather screen."
                />
                <MapLegend
                  weatherActive={false}
                  extra={[
                    { label: "Anchorage", color: "#d3a02f", shape: "ring" },
                    { label: "Approach sector", color: "#4c9fcb", shape: "ring" },
                    { label: "Terminal area", color: "#8a7fc4", shape: "dot" },
                  ]}
                  note={
                    layers.zones
                      ? "Approach geometry is schematic: radii scale with the measured anchorage count and queue pressure, and the sector faces the seaward approach. It is not a surveyed berth plan."
                      : undefined
                  }
                />
              </>
            }
          />
        </div>

        <aside className="flex w-[380px] shrink-0 flex-col overflow-y-auto 2xl:w-[440px]">
          <Panel title="Now" className="shrink-0 rounded-none border-x-0 border-t-0">
            <div className="px-3 py-2">
              <KeyValue label="Daily port calls" dense>
                <Num value={activity?.dailyPortCalls ?? port.vesselCalls} digits={1} />
              </KeyValue>
              <KeyValue label="Queue buildup (anchorage)" dense>
                <Num value={activity?.queueBuildup ?? port.anchorageCount} digits={1} />
              </KeyValue>
              <KeyValue label="Throughput" dense>
                <Num value={port.throughputTonnes} digits={0} unit=" t" />
              </KeyValue>
              <KeyValue label="Berth utilisation" dense>
                <Num value={port.utilization} digits={0} scale={100} unit="%" />
              </KeyValue>
              <KeyValue label="AIS confidence" dense>
                <Num value={port.aisConfidence} digits={2} />
              </KeyValue>
              <KeyValue label="Data quality" dense>
                <Num value={port.dataQuality} digits={2} />
              </KeyValue>
            </div>

            <Section title="Observed congestion · 14 days">
              <Sparkline
                data={port.congestionHistory.map((point) => point.value)}
                tone={riskTone(port.risk)}
                height={44}
              />
              <div className="num mt-1 flex justify-between text-[10px] text-[var(--text-3)]">
                <span>{formatDate(port.congestionHistory[0]?.date ?? null)}</span>
                <span>
                  {formatDate(
                    port.congestionHistory[port.congestionHistory.length - 1]?.date ?? null,
                  )}
                </span>
              </div>
            </Section>
          </Panel>

          <Panel
            title="Next 24 hours"
            note={next24 ? next24.source : undefined}
            className="shrink-0 rounded-none border-x-0 border-t-0"
          >
            {next24 ? (
              <div className="px-3 py-2">
                <div className="mb-2 flex items-baseline gap-3">
                  <span className="metric-lg" style={{ color: "var(--info)" }}>
                    {next24.congestionIndex.toFixed(1)}
                  </span>
                  <span className="num text-[11.5px] text-[var(--text-3)]">
                    q10 {next24.q10.toFixed(1)} · q90 {next24.q90.toFixed(1)}
                  </span>
                  <Pill tone={riskTone(next24.severity)} className="ml-auto">
                    {next24.severity}
                  </Pill>
                </div>
                <KeyValue label="Predicted berth wait" dense>
                  <Num value={next24.delayHoursP50} unit="h" />
                </KeyValue>
                <KeyValue label="Model confidence" dense>
                  <Num value={next24.confidence} digits={0} scale={100} unit="%" />
                </KeyValue>
                <KeyValue label="Model disagreement" dense>
                  <Num value={next24.modelDisagreement} digits={2} />
                </KeyValue>
                <KeyValue label="Transition risk 24h" dense>
                  <Num value={port.transitionRisk24h} digits={3} />
                </KeyValue>
              </div>
            ) : (
              <p className="px-3 py-3 text-[11.5px] text-[var(--text-3)]">
                No forecast rows for this port in the current run.
              </p>
            )}
          </Panel>

          <Panel
            title="Next 10 days"
            note={peak ? `peak day ${peak.day}` : undefined}
            className="shrink-0 rounded-none border-x-0 border-t-0"
          >
            <div className="px-2 pb-2 pt-1">
              <QuantileChart
                height={150}
                threshold={50}
                thresholdLabel="congestion threshold 50"
                points={rows.map((row) => ({
                  label: row.dateLabel,
                  q10: row.q10,
                  q50: row.q50,
                  q90: row.q90,
                }))}
              />
            </div>
            <div className="border-t border-[var(--line)] px-3 py-2">
              <KeyValue label="10-day peak" dense>
                <Num value={peak?.congestionIndex} />
                {peak ? (
                  <span className="ml-1 text-[10.5px] text-[var(--text-3)]">
                    on {peak.dateLabel}
                  </span>
                ) : null}
              </KeyValue>
              <KeyValue label="Mean band width" dense>
                <Num
                  value={
                    rows.length
                      ? rows.reduce((sum, row) => sum + row.intervalWidth, 0) / rows.length
                      : null
                  }
                />
              </KeyValue>
              <KeyValue label="Conformal offset" dense>
                <Num value={next24?.conformalOffset} digits={2} />
              </KeyValue>
            </div>
          </Panel>

          <Panel
            title="Open actions"
            note={`${portAlerts.length} for this port`}
            className="min-h-0 flex-1 rounded-none border-x-0 border-b-0"
            scroll
          >
            {portAlerts.length === 0 ? (
              <p className="px-3 py-3 text-[11.5px] leading-snug text-[var(--text-3)]">
                The decision layer issued no action for {port.short} against the current
                forecast. Standard monitoring applies.
              </p>
            ) : (
              <ul>
                {portAlerts.map((alert) => (
                  <li key={alert.id} className="border-b border-[var(--line)]/50 px-3 py-2 last:border-0">
                    <div className="flex items-center gap-2">
                      <Pill tone={riskTone(alert.severity)}>{alert.severity}</Pill>
                      <span className="num ml-auto text-[10px] text-[var(--text-3)]">
                        conf {alert.confidence?.toFixed(2) ?? "n/a"}
                      </span>
                    </div>
                    <p className="mt-1 text-[12px] leading-snug text-[var(--text-2)]">{alert.text}</p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </aside>
      </PageBody>
    </Page>
  );
}
