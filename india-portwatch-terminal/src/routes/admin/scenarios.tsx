import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { Button, Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import {
  Delta,
  KeyValue,
  MiniBar,
  Num,
  Pill,
  formatUtc,
  riskTone,
} from "@/components/kit/primitives";
import { FailureState, LoadingPanel } from "@/components/kit/states";
import { DataTable, type Column } from "@/components/kit/table";
import { MapControlPanel, MapLegend } from "@/components/map/MapControls";
import { OperationsMap } from "@/components/map/OperationsMap";
import type { LayerKey } from "@/components/map/basemap";
import { CHOKEPOINT_BY_CODE, type Lane } from "@/components/map/layers";
import { useOperationalMap } from "@/components/map/useOperationalMap";
import { cn } from "@/lib/utils";
import { runScenario } from "@/services/portwatch";
import { useNews, usePorts, useScenarios, useWeather } from "@/services/hooks";
import type { ScenarioPortImpact } from "@/types/portwatch";

export const Route = createFileRoute("/admin/scenarios")({ component: ScenarioRoom });

const LAYERS: Record<LayerKey, boolean> = {
  ports: true,
  vessels: false,
  weather: false,
  stations: false,
  storms: false,
  routes: true,
  chokepoints: true,
  events: false,
  zones: false,
  graticule: true,
};

function ScenarioRoom() {
  const catalogue = useScenarios();
  const ports = usePorts();
  const weather = useWeather();
  const news = useNews();

  const [scenarioKey, setScenarioKey] = useState<string | null>(null);
  const [intensity, setIntensity] = useState(1);
  const [runId, setRunId] = useState(0);
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(LAYERS);

  const activeKey = scenarioKey ?? catalogue.data?.[0]?.key ?? null;
  const definition = catalogue.data?.find((entry) => entry.key === activeKey) ?? null;

  const result = useQuery({
    queryKey: ["scenario", activeKey, intensity, runId],
    queryFn: () => runScenario(activeKey as string, intensity, runId),
    enabled: Boolean(activeKey),
    staleTime: Infinity,
  });

  // Stable identity: the memos below key off this array.
  const impacts = useMemo(() => result.data?.affectedPorts ?? [], [result.data]);
  /** Corridors from the shocked chokepoint to the ports it actually reaches. */
  const lanes = useMemo<Lane[]>(() => {
    const shocked = result.data?.chokepointImpacts?.filter((entry) => entry.isShocked) ?? [];
    const portByCode = new Map((ports.data ?? []).map((port) => [port.code, port]));
    const out: Lane[] = [];
    for (const choke of shocked) {
      for (const impact of impacts.slice(0, 8)) {
        const port = portByCode.get(impact.portCode);
        if (!port?.location) continue;
        out.push({
          id: `${choke.code}-${impact.portCode}`,
          from: choke.location,
          to: port.location,
          color: impact.riskLevel === "severe" ? "#d05a4c" : "#d3a02f",
          width: 0.6 + impact.exposure * 2.2,
          opacity: 0.25 + impact.exposure * 0.5,
          dashed: true,
          label: `${choke.name} → ${impact.name}`,
        });
      }
    }
    return out;
  }, [impacts, ports.data, result.data?.chokepointImpacts]);

  const emphasise = useMemo(
    () => new Set(impacts.slice(0, 6).map((impact) => impact.portCode)),
    [impacts],
  );

  const map = useOperationalMap({
    ports: ports.data ?? [],
    weather: weather.data ?? [],
    vessels: [],
    events: news.data?.events ?? [],
    emphasise,
    extraLanes: lanes,
    exposureLanes: false,
  });

  if (catalogue.isLoading) return <LoadingPanel label="Loading scenario catalogue" rows={9} />;
  if (catalogue.isError) {
    return <FailureState error={catalogue.error} retry={() => void catalogue.refetch()} />;
  }

  const outcome = result.data;
  const recommendation = outcome?.recommendation;

  const columns: Array<Column<ScenarioPortImpact>> = [
    {
      key: "name",
      header: "Port",
      render: (row) => <span className="text-[var(--text-2)]">{row.name}</span>,
      sort: (row) => row.name,
    },
    {
      key: "exposure",
      header: "Exposure",
      align: "right",
      width: 116,
      hint: "Measured lane exposure of this port to the shocked corridor",
      render: (row) => (
        <span className="flex items-center justify-end gap-2">
          <span className="w-9">
            <MiniBar value={row.exposure} tone={row.exposure >= 0.4 ? "warn" : "info"} />
          </span>
          <Num value={row.exposure} digits={2} />
        </span>
      ),
      sort: (row) => row.exposure,
    },
    { key: "base", header: "Baseline", align: "right", width: 96, render: (row) => <Num value={row.baselineCongestion} />, sort: (row) => row.baselineCongestion },
    { key: "shock", header: "Under shock", align: "right", width: 110, render: (row) => <Num value={row.shockCongestion} className="text-[var(--text)]" />, sort: (row) => row.shockCongestion },
    { key: "dcong", header: "Δ congestion", align: "right", width: 118, render: (row) => <Delta value={row.congestionDelta} />, sort: (row) => row.congestionDelta },
    { key: "dwait", header: "Δ wait", align: "right", width: 96, render: (row) => <Delta value={row.delayDeltaHours} unit="h" />, sort: (row) => row.delayDeltaHours },
    { key: "dprob", header: "Δ P(cong)", align: "right", width: 106, render: (row) => <Delta value={row.probabilityDelta} digits={3} />, sort: (row) => row.probabilityDelta },
    { key: "steam", header: "Extra steaming", align: "right", width: 130, render: (row) => <Num value={row.extraSteamingDays} digits={1} unit="d" />, sort: (row) => row.extraSteamingDays },
    { key: "conf", header: "Confidence", align: "right", width: 108, render: (row) => <Num value={row.confidence} digits={2} />, sort: (row) => row.confidence },
    {
      key: "risk",
      header: "Risk",
      align: "right",
      width: 96,
      render: (row) => <Pill tone={riskTone(row.riskLevel)}>{row.riskLevel}</Pill>,
      sort: (row) => row.impactScore,
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Scenario Room"
        context={
          <>
            <span>{definition?.name ?? "Select a scenario"}</span>
            {outcome ? <Pill tone={riskTone(outcome.riskLevel)}>{outcome.riskLevel}</Pill> : null}
          </>
        }
        meta={
          <>
            <span className="num">origin {formatUtc(outcome?.forecastOrigin ?? null)}</span>
            <span className="num">{outcome?.baselineModel ?? "—"}</span>
          </>
        }
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "Network congestion Δ",
            value: outcome ? `${outcome.congestionDelta > 0 ? "+" : ""}${outcome.congestionDelta.toFixed(1)}` : "—",
            tone: (outcome?.congestionDelta ?? 0) > 0 ? "crit" : "ok",
            note: "mean across ports and horizon",
          },
          {
            label: "Expected wait Δ",
            value: outcome ? `${outcome.delayDeltaHours > 0 ? "+" : ""}${outcome.delayDeltaHours.toFixed(2)}` : "—",
            unit: "h",
            tone: (outcome?.delayDeltaHours ?? 0) > 0 ? "crit" : "ok",
            note: "mean berth wait change",
          },
          {
            label: "Throughput Δ",
            // The API already reports these three as percentages.
            value: outcome ? `${outcome.throughputDelta.toFixed(1)}%` : "—",
            tone: (outcome?.throughputDelta ?? 0) < 0 ? "crit" : "ok",
            note: "mean tonnage change",
          },
          {
            label: "Freight / oil",
            value: outcome
              ? `${outcome.freightDelta > 0 ? "+" : ""}${outcome.freightDelta.toFixed(1)}% / ${outcome.oilDelta > 0 ? "+" : ""}${outcome.oilDelta.toFixed(1)}%`
              : "—",
            tone: "warn",
            note: "first-order market response",
          },
          {
            label: "Propagation confidence",
            value: outcome ? `${(outcome.confidence * 100).toFixed(0)}%` : "—",
            note: `severity ${outcome ? (outcome.severity * 100).toFixed(0) : "—"}% · ${outcome?.durationDays ?? "—"}d`,
          },
        ]}
      />

      <PageBody padded={false} className="flex min-h-0 overflow-hidden">
        {/* --------------------------------------------------- configure -- */}
        <div className="flex w-[248px] shrink-0 flex-col border-r border-[var(--line)]">
          <div className="panel-head rounded-none">Scenario</div>
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {(catalogue.data ?? []).map((entry) => (
              <li key={entry.key}>
                <button
                  type="button"
                  onClick={() => setScenarioKey(entry.key)}
                  className={cn(
                    "w-full border-b border-[var(--line)]/50 px-3 py-2 text-left transition-colors",
                    activeKey === entry.key
                      ? "bg-[var(--panel-3)]"
                      : "hover:bg-[var(--panel-2)]",
                  )}
                >
                  <div className="truncate text-[12px] text-[var(--text)]">{entry.name}</div>
                  <div className="num mt-0.5 truncate text-[10px] uppercase tracking-[0.07em] text-[var(--text-3)]">
                    {entry.shockType} · {entry.scope}
                  </div>
                </button>
              </li>
            ))}
          </ul>

          <div className="shrink-0 border-t border-[var(--line)] p-3">
            <div className="eyebrow mb-2">Intensity</div>
            <input
              type="range"
              min={0.25}
              max={2}
              step={0.05}
              value={intensity}
              aria-label="Scenario intensity"
              onChange={(event) => setIntensity(Number(event.target.value))}
              className="w-full accent-[var(--info)]"
            />
            <div className="num mt-1 flex justify-between text-[10px] text-[var(--text-3)]">
              <span>0.25×</span>
              <span className="text-[var(--text)]">{intensity.toFixed(2)}×</span>
              <span>2.0×</span>
            </div>
            <p className="mt-2 text-[11px] leading-snug text-[var(--text-3)]">
              Intensity scales the declared shock severity. Effective severity for this run:{" "}
              <span className="num text-[var(--text-2)]">
                {outcome ? `${(outcome.severity * 100).toFixed(0)}%` : "—"}
              </span>
              .
            </p>
            <Button
              variant="primary"
              className="mt-2 w-full"
              onClick={() => setRunId((value) => value + 1)}
              disabled={result.isFetching}
            >
              {result.isFetching ? "Propagating…" : "Re-run propagation"}
            </Button>
          </div>

          {definition ? (
            <div className="shrink-0 border-t border-[var(--line)] p-3">
              <div className="eyebrow mb-1.5">What this asks</div>
              <p className="text-[11.5px] leading-snug text-[var(--text-2)]">
                {definition.question}
              </p>
              <p className="mt-2 text-[11px] leading-snug text-[var(--text-3)]">
                {definition.analogue}
              </p>
              <div className="mt-2 border-t border-[var(--line)] pt-2">
                <KeyValue label="Assumed duration" dense>
                  <span className="num text-[11.5px]">{definition.durationDays}d</span>
                </KeyValue>
                <KeyValue label="Default severity" dense>
                  <span className="num text-[11.5px]">
                    {(definition.defaultSeverity * 100).toFixed(0)}%
                  </span>
                </KeyValue>
                <KeyValue label="Chokepoint" dense>
                  <span className="text-[11.5px]">
                    {definition.chokepoint
                      ? (CHOKEPOINT_BY_CODE.get(definition.chokepoint)?.name ?? definition.chokepoint)
                      : "n/a"}
                  </span>
                </KeyValue>
              </div>
            </div>
          ) : null}
        </div>

        {/* ------------------------------------------------ map + ledger -- */}
        <div className="flex min-w-0 flex-1 flex-col border-r border-[var(--line)]">
          <div className="relative min-h-0 flex-1">
            <OperationsMap
              data={map.data}
              visible={layers}
              labels={map.labels}
              overlay={
                <>
                  <MapControlPanel
                    toggles={[
                      { key: "ports", label: "Ports", count: map.counts.ports },
                      { key: "routes", label: "Propagation", count: map.counts.routes },
                      { key: "chokepoints", label: "Chokepoints", count: map.counts.chokepoints },
                      {
                        key: "weather",
                        label: "Weather field",
                        count: map.counts.weather,
                        disabled: (map.counts.weather ?? 0) === 0,
                        disabledReason: "No weather artefact in this run",
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
                    extra={[{ label: "Propagation path", color: "#d3a02f", shape: "line" }]}
                    note="Corridors are drawn only from a shocked chokepoint to ports the measured lane-exposure graph connects to it."
                  />
                </>
              }
            />
          </div>

          <div className="h-[300px] shrink-0 border-t border-[var(--line)]">
            <Panel
              title="Baseline versus shock, by port"
              note={`${impacts.length} ports`}
              className="h-full rounded-none border-0"
            >
              {result.isLoading ? (
                <LoadingPanel label="Propagating shock" rows={6} />
              ) : result.isError ? (
                <FailureState error={result.error} retry={() => void result.refetch()} />
              ) : (
                <DataTable
                  rows={impacts}
                  columns={columns}
                  rowKey={(row) => row.portCode}
                  initialSort="exposure"
                  rowTone={(row) =>
                    row.riskLevel === "severe"
                      ? "var(--crit)"
                      : row.riskLevel === "high"
                        ? "var(--warn)"
                        : null
                  }
                />
              )}
            </Panel>
          </div>
        </div>

        {/* ------------------------------------------------------ impact -- */}
        <aside className="flex w-[400px] shrink-0 flex-col overflow-y-auto 2xl:w-[450px]">
          <Panel title="Propagation" className="shrink-0 rounded-none border-x-0 border-t-0">
            {outcome ? (
              <ol>
                {outcome.propagation.map((step, index) => (
                  <li
                    key={step.step}
                    className="flex gap-2.5 border-b border-[var(--line)]/50 px-3 py-2 last:border-0"
                  >
                    <span className="num mt-[2px] w-4 shrink-0 text-[10px] text-[var(--text-3)]">
                      {index + 1}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="eyebrow block">{step.label}</span>
                      <span className="mt-0.5 block text-[12px] text-[var(--text)]">
                        {step.value}
                      </span>
                      <span className="mt-0.5 block text-[11px] leading-snug text-[var(--text-3)]">
                        {step.detail}
                      </span>
                    </span>
                  </li>
                ))}
              </ol>
            ) : null}
          </Panel>

          {recommendation?.available ? (
            <Panel
              title="Recommended action under shock"
              note={recommendation.severity}
              className="shrink-0 rounded-none border-x-0 border-t-0"
            >
              <div className="p-3">
                <h2 className="text-[14px] font-medium leading-snug text-[var(--text)]">
                  {recommendation.title}
                </h2>
                <div className="num mt-1 text-[10.5px] text-[var(--text-3)]">
                  {recommendation.action} · {recommendation.target}
                </div>
                <p className="mt-2 text-[12px] leading-relaxed text-[var(--text-2)]">
                  {recommendation.instruction ?? recommendation.rationale}
                </p>
                <div className="mt-2 border-t border-[var(--line)] pt-2">
                  <KeyValue label="Expected delay saved" dense>
                    <Num value={recommendation.expectedDelaySavedHours} unit="h" tone="ok" />
                  </KeyValue>
                  <KeyValue label="Decision confidence" dense>
                    <Num value={recommendation.confidence} digits={2} />
                  </KeyValue>
                  <KeyValue label="Uncertainty" dense>
                    <Num value={recommendation.uncertainty} digits={2} tone="unc" />
                  </KeyValue>
                  <KeyValue label="Changed from baseline" dense>
                    <Pill tone={recommendation.changedFromBaseline ? "warn" : "neutral"}>
                      {recommendation.changedFromBaseline ? "yes" : "no"}
                    </Pill>
                  </KeyValue>
                </div>
                {recommendation.alternativeAction ? (
                  <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11.5px] leading-snug text-[var(--text-3)]">
                    <span className="text-[var(--warn)]">Fallback:</span>{" "}
                    {recommendation.alternativeAction}
                  </p>
                ) : null}
              </div>
            </Panel>
          ) : null}

          <Panel
            title="Chokepoints and corridors"
            className="shrink-0 rounded-none border-x-0 border-t-0"
          >
            {outcome ? (
              <div className="px-3 py-2">
                {outcome.chokepointImpacts.map((choke) => (
                  <div
                    key={choke.code}
                    className="flex items-baseline justify-between gap-2 border-b border-[var(--line)]/50 py-1.5 last:border-0"
                  >
                    <span
                      className={cn(
                        "min-w-0 truncate text-[11.5px]",
                        choke.isShocked ? "text-[var(--crit)]" : "text-[var(--text-2)]",
                      )}
                    >
                      {choke.name}
                    </span>
                    <span className="num shrink-0 text-[10.5px] text-[var(--text-3)]">
                      {choke.hasAlternative ? `+${choke.rerouteDays}d reroute` : "no bypass"}
                    </span>
                    <Pill tone={riskTone(choke.riskLevel)}>{choke.riskLevel}</Pill>
                  </div>
                ))}
                <div className="mt-2 border-t border-[var(--line)] pt-2">
                  {outcome.routeImpacts.map((route) => (
                    <div
                      key={route.name}
                      className="flex items-baseline justify-between gap-2 py-1"
                    >
                      <span className="min-w-0 truncate text-[11.5px] text-[var(--text-2)]">
                        {route.name}
                      </span>
                      <Delta value={route.delayDeltaHours} unit="h" />
                      <Pill tone={riskTone(route.riskLevel)}>{route.riskLevel}</Pill>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </Panel>

          <Panel title="Method" className="min-h-0 flex-1 rounded-none border-x-0 border-b-0">
            <p className="p-3 text-[11.5px] leading-relaxed text-[var(--text-3)]">
              {outcome?.method ??
                "Select a scenario to propagate it against the live forecast."}
            </p>
          </Panel>
        </aside>
      </PageBody>
    </Page>
  );
}
