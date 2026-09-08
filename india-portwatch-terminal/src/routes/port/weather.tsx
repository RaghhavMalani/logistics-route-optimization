import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { PortSwitcher, usePortContext } from "@/components/app/port-context";
import { BarRanking, SeriesChart } from "@/components/kit/charts";
import { Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import { KeyValue, Num, Pill, formatDate, formatUtc } from "@/components/kit/primitives";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { DataTable, type Column } from "@/components/kit/table";
import { MapControlPanel, MapLegend } from "@/components/map/MapControls";
import { OperationsMap } from "@/components/map/OperationsMap";
import type { LayerKey } from "@/components/map/basemap";
import { useOperationalMap } from "@/components/map/useOperationalMap";
import { useNews, useVessels, useWeather, useWeatherIntelligence } from "@/services/hooks";
import type { WeatherSignal } from "@/types/portwatch";

export const Route = createFileRoute("/port/weather")({ component: PortWeather });

const WEATHER_LAYERS: Record<LayerKey, boolean> = {
  ports: true,
  vessels: false,
  weather: true,
  stations: true,
  storms: true,
  routes: false,
  chokepoints: false,
  events: false,
  zones: false,
  graticule: true,
};

function PortWeather() {
  const { port, ports, query } = usePortContext();
  const weather = useWeather();
  const intelligence = useWeatherIntelligence();
  const vessels = useVessels();
  const news = useNews();
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(WEATHER_LAYERS);

  const map = useOperationalMap({
    ports,
    weather: weather.data ?? [],
    vessels: vessels.data?.vessels ?? [],
    events: news.data?.events ?? [],
    selected: port?.code ?? null,
    exposureLanes: false,
  });

  const centre = useMemo<[number, number]>(
    () => (port?.location ? [port.location.lon, port.location.lat] : [79.5, 15.5]),
    [port?.location],
  );

  if (query.isLoading || weather.isLoading || weather.isError || !port) {
    return (
      <ScreenFallback
        title="Weather"
        isLoading={query.isLoading || weather.isLoading}
        error={weather.error ?? (port ? null : new Error("No port selected."))}
        retry={() => void weather.refetch()}
        label="Loading marine conditions"
      />
    );
  }

  const signals = weather.data ?? [];
  const signal = signals.find((entry) => entry.portCode === port.code) ?? null;
  const summary = intelligence.data;

  const columns: Array<Column<WeatherSignal>> = [
    {
      key: "name",
      header: "Port",
      render: (row) => (
        <span className={row.portCode === port.code ? "font-medium text-[var(--text)]" : ""}>
          {row.name}
        </span>
      ),
      sort: (row) => row.name,
    },
    {
      key: "wind",
      header: "Wind kn",
      align: "right",
      width: 90,
      render: (row) => <Num value={row.windKnots} />,
      sort: (row) => row.windKnots,
    },
    {
      key: "gust",
      header: "Gust kn",
      align: "right",
      width: 90,
      render: (row) => <Num value={row.gustKnots} />,
      sort: (row) => row.gustKnots,
    },
    {
      key: "wave",
      header: "Wave m",
      align: "right",
      width: 88,
      hint: "Significant wave height — absent from the marine feed in most runs",
      render: (row) => <Num value={row.waveHeightM} digits={2} />,
      sort: (row) => row.waveHeightM,
    },
    {
      key: "rain",
      header: "Rain mm",
      align: "right",
      width: 94,
      render: (row) => <Num value={row.rainfallMm24h} />,
      sort: (row) => row.rainfallMm24h,
    },
    {
      key: "vis",
      header: "Vis km",
      align: "right",
      width: 88,
      render: (row) => <Num value={row.visibilityKm} />,
      sort: (row) => row.visibilityKm,
    },
    {
      key: "impact",
      header: "Impact",
      align: "right",
      width: 90,
      render: (row) => (
        <Num
          value={row.impactScore}
          digits={3}
          tone={(row.impactScore ?? 0) >= 0.35 ? "warn" : undefined}
        />
      ),
      sort: (row) => row.impactScore,
    },
    {
      key: "persist",
      header: "Persistence",
      align: "right",
      width: 110,
      render: (row) => <Num value={row.persistenceScore} digits={2} />,
      sort: (row) => row.persistenceScore,
    },
    {
      key: "regime",
      header: "Regime",
      width: 108,
      render: (row) => (
        <Pill tone={row.weatherRegime === "CALM" ? "ok" : "warn"}>
          {row.weatherRegime ?? "n/a"}
        </Pill>
      ),
      sort: (row) => row.weatherRegime,
    },
    {
      key: "observed",
      header: "Observed",
      align: "right",
      width: 122,
      render: (row) => <span className="num text-[var(--text-3)]">{formatUtc(row.observedAt)}</span>,
      sort: (row) => row.observedAt,
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Weather"
        context={
          <>
            <span>{port.name}</span>
            <span className="num">{port.code}</span>
            {signal ? (
              <Pill tone={signal.weatherRegime === "CALM" ? "ok" : "warn"}>
                {signal.weatherRegime ?? "unclassified"}
              </Pill>
            ) : null}
          </>
        }
        meta={<span className="num">observed {formatUtc(signal?.observedAt ?? null)}</span>}
        actions={<PortSwitcher />}
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "Wind / gust",
            value: signal?.windKnots?.toFixed(1) ?? "n/a",
            unit: "kn",
            note: `gust ${signal?.gustKnots?.toFixed(1) ?? "n/a"} kn`,
          },
          {
            label: "Rain 24h",
            value: signal?.rainfallMm24h?.toFixed(1) ?? "n/a",
            unit: "mm",
            note: `rain risk ${signal?.rainRisk?.toFixed(2) ?? "n/a"}`,
          },
          {
            label: "Wave height",
            value: signal?.waveHeightM?.toFixed(2) ?? "n/a",
            unit: "m",
            tone: signal?.waveHeightM == null ? "neutral" : "info",
            note: signal?.waveHeightM == null ? "not carried by this feed" : "significant height",
          },
          {
            label: "Visibility",
            value: signal?.visibilityKm?.toFixed(1) ?? "n/a",
            unit: "km",
            note: `storm risk ${signal?.stormRisk?.toFixed(3) ?? "n/a"}`,
          },
          {
            label: "Impact index",
            value: signal?.impactScore?.toFixed(3) ?? "n/a",
            tone: (signal?.impactScore ?? 0) >= 0.35 ? "warn" : "ok",
            note: `confidence ${signal?.confidence?.toFixed(2) ?? "n/a"}`,
          },
          {
            label: "Forward load",
            value: signal?.forwardLoad?.toFixed(3) ?? "n/a",
            tone: "info",
            note: "known-future covariate at the forecast origin",
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
            // Wide enough that the interpolated field reads as a field rather
            // than a wash over the one port in view.
            zoom={4.7}
            loadingLabel="Initialising weather chart"
            overlay={
              <>
                <MapControlPanel
                  toggles={[
                    {
                      key: "weather",
                      label: "Weather field",
                      count: map.counts.weather,
                      disabled: (map.counts.weather ?? 0) === 0,
                      disabledReason: "No weather artefact in this run",
                    },
                    {
                      key: "stations",
                      label: "Station readings",
                      count: map.counts.stations,
                      disabled: (map.counts.stations ?? 0) === 0,
                      disabledReason: "No weather artefact in this run",
                    },
                    {
                      key: "storms",
                      label: "Storm envelopes",
                      count: map.counts.storms,
                      disabled: (map.counts.storms ?? 0) === 0,
                      disabledReason: "No port carries a storm flag in this run",
                    },
                    { key: "ports", label: "Ports", count: map.counts.ports },
                    { key: "vessels", label: "AIS activity", count: map.counts.vessels },
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
                  extra={[{ label: "Storm envelope", color: "#d05a4c", shape: "ring" }]}
                  note={map.weatherNote}
                />
              </>
            }
          />
        </div>

        <aside className="flex w-[400px] shrink-0 flex-col overflow-y-auto 2xl:w-[460px]">
          <Panel title="Risk decomposition" className="shrink-0 rounded-none border-x-0 border-t-0">
            {signal ? (
              <div className="p-3">
                <BarRanking
                  items={[
                    { label: "Wind risk", value: signal.windRisk, tone: "info" },
                    { label: "Rain risk", value: signal.rainRisk, tone: "info" },
                    { label: "Wave risk", value: signal.waveRisk, tone: "info" },
                    { label: "Storm risk", value: signal.stormRisk, tone: "crit" },
                    { label: "Composite impact", value: signal.impactScore, tone: "warn" },
                  ]}
                />
                <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11.5px] leading-snug text-[var(--text-3)]">
                  These are the exact bounded 0–1 features the forecasting model consumed
                  for {port.short}. {signal.dataSource}.
                </p>
              </div>
            ) : (
              <EmptyState
                title="No marine feed"
                detail={`The weather artefact carries no row for ${port.name} in this run.`}
              />
            )}
          </Panel>

          <Panel
            title="Shock versus sustained disruption"
            className="shrink-0 rounded-none border-x-0 border-t-0"
          >
            {signal ? (
              <div className="p-3">
                <div className="mb-3 grid grid-cols-3 gap-3">
                  {(
                    [
                      ["Shock", signal.shockScore],
                      ["Persistence", signal.persistenceScore],
                      ["Forward load", signal.forwardLoad],
                    ] as const
                  ).map(([label, value]) => (
                    <div key={label}>
                      <div className="eyebrow">{label}</div>
                      <div className="metric-lg mt-0.5 text-[var(--text)]">
                        {value?.toFixed(2) ?? "n/a"}
                      </div>
                    </div>
                  ))}
                </div>
                <SeriesChart
                  height={120}
                  yUnit="forecast weather impact"
                  series={[
                    {
                      name: "Impact, next days",
                      tone: "unc",
                      area: true,
                      points: signal.forecast.map((point) => ({
                        label: formatDate(point.date),
                        value: point.impact,
                      })),
                    },
                  ]}
                />
                <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11.5px] leading-snug text-[var(--text-2)]">
                  {signal.advisory}
                </p>
              </div>
            ) : null}
          </Panel>

          <Panel title="National marine picture" className="min-h-0 flex-1 rounded-none border-x-0 border-b-0">
            <div className="px-3 py-2">
              <KeyValue label="Mean weather impact" dense>
                <Num value={summary?.meanImpact} digits={3} />
              </KeyValue>
              <KeyValue label="Mean wind" dense>
                <Num value={summary?.meanWindKnots} unit="kn" />
              </KeyValue>
              <KeyValue label="Mean wave height" dense>
                <Num value={summary?.meanWaveHeightM} digits={2} unit="m" />
              </KeyValue>
              <KeyValue label="Mean storm risk" dense>
                <Num value={summary?.meanStormRisk} digits={3} />
              </KeyValue>
              <KeyValue label="Highest impact port" dense>
                <span className="num text-[11.5px]">{summary?.highestImpactPort ?? "n/a"}</span>
              </KeyValue>
              <KeyValue label="Ports covered" dense>
                <Num value={summary?.portsCovered} digits={0} />
              </KeyValue>
              <KeyValue label="Under sustained disruption" dense>
                <span className="text-[11.5px]">
                  {summary?.persistentPorts?.length
                    ? summary.persistentPorts.join(", ")
                    : "none"}
                </span>
              </KeyValue>
            </div>
          </Panel>
        </aside>
      </PageBody>

      <div className="h-[262px] shrink-0 border-t border-[var(--line)]">
        <Panel
          title="All ports · measured conditions"
          note={`${signals.length} stations`}
          className="h-full rounded-none border-0"
        >
          <DataTable
            rows={signals}
            columns={columns}
            rowKey={(row) => row.portCode}
            selectedKey={port.code}
            initialSort="impact"
            rowTone={(row) => (row.portCode === port.code ? "var(--info)" : null)}
          />
        </Panel>
      </div>
    </Page>
  );
}
