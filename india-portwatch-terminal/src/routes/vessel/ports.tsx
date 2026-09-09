import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { useFleetIntel } from "@/components/app/fleet-context";
import { QuantileChart, Sparkline } from "@/components/kit/charts";
import { Page, PageBody, PageHeader, Panel, SegmentedControl, StatStrip, Toolbar } from "@/components/kit/layout";
import {
  KeyValue,
  MiniBar,
  Num,
  Pill,
  ProvenanceTag,
  formatUtc,
  riskLabel,
  riskTone,
} from "@/components/kit/primitives";
import { ScreenFallback } from "@/components/kit/states";
import { DataTable, SearchInput, type Column } from "@/components/kit/table";
import { useForecast } from "@/services/hooks";
import type { PortSnapshot } from "@/types/portwatch";

export const Route = createFileRoute("/vessel/ports")({ component: DestinationPorts });

type Scope = "fleet" | "all";

function DestinationPorts() {
  const { intel, ports, weather, isLoading, error, refetch } = useFleetIntel();
  const [scope, setScope] = useState<Scope>("fleet");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const fleetCodes = useMemo(
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

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    return ports.filter((port) => {
      if (scope === "fleet" && !fleetCodes.has(port.code)) return false;
      if (!term) return true;
      return (
        port.name.toLowerCase().includes(term) ||
        port.code.toLowerCase().includes(term) ||
        port.short.toLowerCase().includes(term)
      );
    });
  }, [fleetCodes, ports, scope, search]);

  const activeCode = selected ?? rows[0]?.code ?? null;
  const active = ports.find((port) => port.code === activeCode) ?? null;
  const forecast = useForecast(activeCode);

  if (isLoading || error) {
    return (
      <ScreenFallback
        title="Destination Ports"
        context={<span>Congestion and wait exposure at the ports the fleet calls</span>}
        isLoading={isLoading}
        error={error}
        retry={refetch}
        label="Loading destination ports"
      />
    );
  }

  const weatherByCode = new Map(weather.map((signal) => [signal.portCode, signal]));
  const callsByCode = new Map<string, string[]>();
  for (const row of intel) {
    if (!row.vessel.intendedPortCode) continue;
    const list = callsByCode.get(row.vessel.intendedPortCode) ?? [];
    list.push(row.vessel.name);
    callsByCode.set(row.vessel.intendedPortCode, list);
  }

  const columns: Array<Column<PortSnapshot>> = [
    {
      key: "name",
      header: "Port",
      render: (port) => (
        <span className="flex items-center gap-2">
          <span className={fleetCodes.has(port.code) ? "text-[var(--text)]" : "text-[var(--text-2)]"}>
            {port.name}
          </span>
          {callsByCode.has(port.code) ? <Pill tone="info">declared call</Pill> : null}
        </span>
      ),
      sort: (port) => port.name,
    },
    {
      key: "regime",
      header: "Regime",
      width: 132,
      render: (port) => <Pill tone={riskTone(port.risk)}>{riskLabel(port.risk)}</Pill>,
      sort: (port) => port.congestionIndex,
    },
    {
      key: "observed",
      header: "Observed",
      align: "right",
      width: 96,
      render: (port) => <Num value={port.observedCongestionIndex} />,
      sort: (port) => port.observedCongestionIndex,
    },
    {
      key: "day1",
      header: "Day-1",
      align: "right",
      width: 90,
      render: (port) => <Num value={port.congestionIndex} />,
      sort: (port) => port.congestionIndex,
    },
    {
      key: "band",
      header: "80% band",
      align: "right",
      width: 106,
      render: (port) => (
        <span className="num text-[var(--text-3)]">
          {port.forecastQ10?.toFixed(0) ?? "—"}–{port.forecastQ90?.toFixed(0) ?? "—"}
        </span>
      ),
      sort: (port) => (port.forecastQ90 ?? 0) - (port.forecastQ10 ?? 0),
    },
    {
      key: "wait",
      header: "Berth wait",
      align: "right",
      width: 104,
      render: (port) => <Num value={port.delayHours} unit="h" />,
      sort: (port) => port.delayHours,
    },
    {
      key: "peak",
      header: "10-day peak",
      align: "right",
      width: 116,
      render: (port) => (
        <span className="num">
          {port.peakCongestionIndex.toFixed(1)}
          <span className="ml-1 text-[10px] text-[var(--text-3)]">d{port.peakDay}</span>
        </span>
      ),
      sort: (port) => port.peakCongestionIndex,
    },
    {
      key: "wx",
      header: "Weather",
      align: "right",
      width: 96,
      render: (port) => (
        <Num
          value={weatherByCode.get(port.code)?.impactScore}
          digits={3}
          tone={(weatherByCode.get(port.code)?.impactScore ?? 0) >= 0.35 ? "warn" : undefined}
        />
      ),
      sort: (port) => weatherByCode.get(port.code)?.impactScore ?? null,
    },
    {
      key: "conf",
      header: "Confidence",
      align: "right",
      width: 108,
      render: (port) => (
        <span className="flex items-center justify-end gap-2">
          <span className="w-9">
            <MiniBar value={port.confidence} tone={port.confidence >= 0.6 ? "ok" : "warn"} />
          </span>
          <Num value={port.confidence} digits={0} scale={100} unit="%" />
        </span>
      ),
      sort: (port) => port.confidence,
    },
    {
      key: "trend",
      header: "14-day trend",
      width: 96,
      render: (port) => (
        <Sparkline
          data={port.congestionHistory.map((point) => point.value)}
          tone={riskTone(port.risk)}
          height={16}
          fill={false}
        />
      ),
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Destination Ports"
        context={<span>Congestion and wait exposure at the ports the fleet calls</span>}
        meta={<span className="num">{ports.length} ports in the network</span>}
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "Ports on fleet lanes",
            value: fleetCodes.size,
            note: `${ports.length} in the national network`,
          },
          {
            label: "Severe destinations",
            value: [...fleetCodes].filter(
              (code) => ports.find((port) => port.code === code)?.risk === "severe",
            ).length,
            tone: "crit",
            note: "regime SEVERE at the forecast origin",
          },
          {
            label: "Worst berth wait",
            value: Math.max(
              0,
              ...[...fleetCodes].map(
                (code) => ports.find((port) => port.code === code)?.delayHours ?? 0,
              ),
            ).toFixed(1),
            unit: "h",
            tone: "warn",
            note: "predicted, across declared and alternative calls",
          },
          {
            label: "Weather-exposed",
            value: [...fleetCodes].filter(
              (code) => (weatherByCode.get(code)?.impactScore ?? 0) >= 0.15,
            ).length,
            note: "impact index ≥ 0.15",
          },
        ]}
      />

      <Toolbar>
        <SegmentedControl
          ariaLabel="Port scope"
          value={scope}
          onChange={setScope}
          options={[
            { value: "fleet", label: "Fleet lanes" },
            { value: "all", label: "All ports" },
          ]}
        />
        <SearchInput value={search} onChange={setSearch} placeholder="Filter ports" className="w-[240px]" />
        <span className="num ml-auto text-[11px] text-[var(--text-3)]">{rows.length} shown</span>
      </Toolbar>

      <PageBody padded={false} className="flex min-h-0 overflow-hidden">
        <Panel className="min-w-0 flex-1 rounded-none border-0 border-r border-[var(--line)]">
          <DataTable
            rows={rows}
            columns={columns}
            rowKey={(port) => port.code}
            selectedKey={activeCode}
            onRowClick={(port) => setSelected(port.code)}
            initialSort="day1"
            rowTone={(port) => (fleetCodes.has(port.code) ? "var(--info)" : null)}
          />
        </Panel>

        <aside className="flex w-[400px] shrink-0 flex-col overflow-y-auto 2xl:w-[450px]">
          {active ? (
            <>
              <Panel
                title={active.name}
                note={active.code}
                className="shrink-0 rounded-none border-x-0 border-t-0"
              >
                <div className="px-3 py-2">
                  <div className="mb-2 flex items-center gap-2">
                    <Pill tone={riskTone(active.risk)} solid>
                      {riskLabel(active.risk)}
                    </Pill>
                    <span className="text-[11.5px] text-[var(--text-2)]">{active.regime}</span>
                    <ProvenanceTag
                      status={active.dataStatus}
                      ageHours={active.dataAgeHours}
                      detail={`Observed ${formatUtc(active.observedAt)}`}
                      className="ml-auto"
                    />
                  </div>
                  <KeyValue label="Authority" dense>
                    <span className="text-[11.5px]">{active.authority ?? "n/a"}</span>
                  </KeyValue>
                  <KeyValue label="Calls declared here" dense>
                    <span className="text-[11.5px]">
                      {callsByCode.get(active.code)?.join(", ") ?? "none"}
                    </span>
                  </KeyValue>
                  <KeyValue label="Daily port calls" dense>
                    <Num value={active.vesselCalls} />
                  </KeyValue>
                  <KeyValue label="Anchorage waiting" dense>
                    <Num value={active.anchorageCount} />
                  </KeyValue>
                  <KeyValue label="Berth utilisation" dense>
                    <Num value={active.utilization} digits={0} scale={100} unit="%" />
                  </KeyValue>
                  <KeyValue label="Transition risk 24h" dense>
                    <Num value={active.transitionRisk24h} digits={3} />
                  </KeyValue>
                  <KeyValue label="Recommended action" dense>
                    <span className="text-[11.5px]">{active.actionTitle ?? "none issued"}</span>
                  </KeyValue>
                </div>
              </Panel>

              <Panel
                title="Ten-day forecast"
                note={forecast.data?.[0]?.source}
                className="shrink-0 rounded-none border-x-0 border-t-0"
              >
                <div className="p-3">
                  <QuantileChart
                    height={165}
                    threshold={50}
                    thresholdLabel="threshold 50"
                    points={(forecast.data ?? []).map((point) => ({
                      label: point.dateLabel,
                      q10: point.q10,
                      q50: point.q50,
                      q90: point.q90,
                    }))}
                  />
                </div>
              </Panel>

              <Panel
                title="Marine conditions"
                className="min-h-0 flex-1 rounded-none border-x-0 border-b-0"
              >
                {weatherByCode.get(active.code) ? (
                  <div className="px-3 py-2">
                    {(
                      [
                        ["Wind", weatherByCode.get(active.code)?.windKnots, "kn"],
                        ["Gust", weatherByCode.get(active.code)?.gustKnots, "kn"],
                        ["Rain 24h", weatherByCode.get(active.code)?.rainfallMm24h, "mm"],
                        ["Visibility", weatherByCode.get(active.code)?.visibilityKm, "km"],
                        ["Wave height", weatherByCode.get(active.code)?.waveHeightM, "m"],
                        ["Impact index", weatherByCode.get(active.code)?.impactScore, ""],
                      ] as Array<[string, number | null | undefined, string]>
                    ).map(([label, value, unit]) => (
                      <KeyValue key={label} label={label} dense>
                        <Num value={value ?? null} digits={unit === "" ? 3 : 1} unit={unit} />
                      </KeyValue>
                    ))}
                    <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11px] leading-snug text-[var(--text-3)]">
                      {weatherByCode.get(active.code)?.advisory}
                    </p>
                  </div>
                ) : (
                  <p className="p-3 text-[11.5px] text-[var(--text-3)]">
                    No marine feed row for this port in the current run.
                  </p>
                )}
              </Panel>
            </>
          ) : null}
        </aside>
      </PageBody>
    </Page>
  );
}
