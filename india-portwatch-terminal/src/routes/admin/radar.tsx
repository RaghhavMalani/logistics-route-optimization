import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { useMemo, useState } from "react";

import { useAuth } from "@/auth/AuthProvider";
import { Sparkline } from "@/components/kit/charts";
import { Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import {
  Dot,
  Num,
  Pill,
  ProvenanceTag,
  formatUtc,
  riskLabel,
  riskTone,
  severityTone,
} from "@/components/kit/primitives";
import { FailureState, LoadingPanel } from "@/components/kit/states";
import { MapControlPanel, MapLegend } from "@/components/map/MapControls";
import { OperationsMap } from "@/components/map/OperationsMap";
import type { LayerKey } from "@/components/map/basemap";
import { useOperationalMap } from "@/components/map/useOperationalMap";
import { useHealth, useNews, usePorts, useVessels, useWeather } from "@/services/hooks";
import type { PortSnapshot } from "@/types/portwatch";

export const Route = createFileRoute("/admin/radar")({ component: NationalRadar });

const DEFAULT_LAYERS: Record<LayerKey, boolean> = {
  ports: true,
  vessels: true,
  weather: true,
  storms: true,
  routes: true,
  chokepoints: true,
  events: false,
  zones: false,
  graticule: true,
};

function NationalRadar() {
  const health = useHealth();
  const ports = usePorts();
  const weather = useWeather();
  const vessels = useVessels();
  const news = useNews();
  const { setPortCode } = useAuth();

  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(DEFAULT_LAYERS);

  const portList = useMemo(
    () => [...(ports.data ?? [])].sort((a, b) => (b.priorityScore ?? 0) - (a.priorityScore ?? 0)),
    [ports.data],
  );

  const map = useOperationalMap({
    ports: ports.data ?? [],
    weather: weather.data ?? [],
    vessels: vessels.data?.vessels ?? [],
    events: news.data?.events ?? [],
    selected,
    emphasise: useMemo(
      () => new Set(portList.slice(0, 3).map((port) => port.code)),
      [portList],
    ),
  });

  if (ports.isLoading) return <LoadingPanel label="Acquiring national picture" rows={10} />;
  if (ports.isError) {
    return <FailureState error={ports.error} retry={() => void ports.refetch()} />;
  }

  const all = ports.data ?? [];
  const severe = all.filter((port) => port.risk === "severe");
  const congested = all.filter((port) => port.risk === "congested");
  const meanForecast = all.length
    ? all.reduce((sum, port) => sum + port.congestionIndex, 0) / all.length
    : null;
  const dailyCalls = (vessels.data?.vessels ?? []).reduce(
    (sum, vessel) => sum + (vessel.dailyPortCalls ?? 0),
    0,
  );
  const peakWeather = (weather.data ?? []).reduce<number | null>(
    (peak, signal) =>
      signal.impactScore == null ? peak : peak == null ? signal.impactScore : Math.max(peak, signal.impactScore),
    null,
  );

  const selectedPort = selected ? all.find((port) => port.code === selected) ?? null : null;
  const alerts = news.data?.alerts ?? [];
  const events = news.data?.events ?? [];

  return (
    <Page>
      <PageHeader
        title="National Port Radar"
        context={
          <>
            <span>Where intervention matters right now</span>
          </>
        }
        meta={
          <>
            <span className="num">
              model <span className="text-[var(--text-2)]">{health.data?.model ?? "—"}</span>
            </span>
            <span className="num">
              origin{" "}
              <span className="text-[var(--text-2)]">
                {formatUtc(health.data?.forecastOrigin ?? null)}
              </span>
            </span>
            <ProvenanceTag
              status={health.data?.forecastOriginStatus ?? null}
              ageHours={health.data?.forecastOriginAgeHours ?? null}
              detail="Age of the forecast origin against wall clock"
            />
          </>
        }
      />

      <StatStrip
        items={[
          {
            label: "Severe ports",
            value: severe.length,
            tone: severe.length ? "crit" : "ok",
            note: severe.map((port) => port.short).join(" · ") || "none",
          },
          {
            label: "Congested",
            value: congested.length,
            tone: congested.length ? "warn" : "ok",
            note: congested.map((port) => port.short).join(" · ") || "none",
          },
          {
            label: "Mean day-1 congestion",
            value: meanForecast?.toFixed(1) ?? "n/a",
            note: `across ${all.length} ports · index 0–100`,
          },
          {
            label: "Daily port calls",
            value: dailyCalls ? dailyCalls.toFixed(0) : "n/a",
            note: "aggregate satellite-AIS activity",
          },
          {
            label: "Peak weather impact",
            value: peakWeather?.toFixed(2) ?? "n/a",
            tone: (peakWeather ?? 0) >= 0.35 ? "warn" : "info",
            note: `${(weather.data ?? []).filter((s) => (s.impactScore ?? 0) >= 0.35).length} of ${weather.data?.length ?? 0} above watch`,
          },
          {
            label: "Open alerts",
            value: alerts.length,
            tone: alerts.length ? "warn" : "ok",
            note: `${events.filter((e) => e.severity === "severe").length} severe events in feed`,
          },
        ]}
      />

      <PageBody padded={false} className="flex min-h-0 overflow-hidden">
        {/* ------------------------------------------------------------ map -- */}
        <div className="relative min-w-0 flex-1 border-r border-[var(--line)]">
          <OperationsMap
            data={map.data}
            visible={layers}
            labels={map.labels}
            selected={selected}
            hovered={hovered}
            onHover={setHovered}
            onSelect={(code) => setSelected(code)}
            renderTooltip={(code) => {
              const port = all.find((entry) => entry.code === code);
              if (!port) return null;
              const signal = (weather.data ?? []).find((entry) => entry.portCode === code);
              const activity = (vessels.data?.vessels ?? []).find((entry) => entry.portCode === code);
              return (
                <div>
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <span className="truncate text-[12px] font-medium text-[var(--text)]">
                      {port.name}
                    </span>
                    <Pill tone={riskTone(port.risk)}>{riskLabel(port.risk)}</Pill>
                  </div>
                  <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-[3px] text-[11px]">
                    {(
                      [
                        ["Observed", <Num key="o" value={port.observedCongestionIndex} />],
                        ["Day 1 forecast", <Num key="f" value={port.congestionIndex} />],
                        [
                          "80% band",
                          <span key="b" className="num text-[var(--text-2)]">
                            {port.forecastQ10?.toFixed(0) ?? "—"}–{port.forecastQ90?.toFixed(0) ?? "—"}
                          </span>,
                        ],
                        ["Berth wait", <Num key="w" value={port.delayHours} unit="h" />],
                        ["Daily calls", <Num key="c" value={activity?.dailyPortCalls ?? port.vesselCalls} digits={0} />],
                        ["Weather impact", <Num key="wx" value={signal?.impactScore} digits={3} />],
                        ["Regime", <span key="r" className="text-[var(--text-2)]">{port.regime}</span>],
                      ] as const
                    ).map(([label, value]) => (
                      <div key={label} className="contents">
                        <dt className="text-[var(--text-3)]">{label}</dt>
                        <dd className="text-right">{value}</dd>
                      </div>
                    ))}
                  </dl>
                  <div className="mt-1.5 border-t border-[var(--line)] pt-1.5 text-[10px] text-[var(--info)]">
                    Click to pin this port to the panel
                  </div>
                </div>
              );
            }}
            overlay={
              <>
                <MapControlPanel
                  toggles={[
                    { key: "ports", label: "Ports", count: map.counts.ports },
                    { key: "vessels", label: "AIS activity", count: map.counts.vessels },
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
                      disabledReason: "No port carries a storm flag in this run",
                    },
                    { key: "routes", label: "Exposure corridors", count: map.counts.routes },
                    { key: "chokepoints", label: "Chokepoints", count: map.counts.chokepoints },
                    {
                      key: "events",
                      label: "Events",
                      count: map.counts.events,
                      disabled: (map.counts.events ?? 0) === 0,
                      disabledReason: "No event in the feed carries a mapped location",
                    },
                    { key: "graticule", label: "Graticule" },
                  ]}
                  visible={layers}
                  onToggle={(key) => setLayers((prev) => ({ ...prev, [key]: !prev[key] }))}
                  weatherField={map.weatherField}
                  onWeatherField={map.setWeatherField}
                  weatherAvailability={map.availability}
                  footer={map.eventNote}
                />
                <MapLegend
                  weatherField={map.weatherField}
                  weatherActive={layers.weather}
                  extra={[
                    { label: "AIS activity", color: "#4c9fcb", shape: "dot" },
                    { label: "Exposure corridor", color: "#d3a02f", shape: "line" },
                    { label: "Chokepoint", color: "#4c9fcb", shape: "ring" },
                  ]}
                  note={layers.weather ? map.weatherNote : undefined}
                />
              </>
            }
          />
        </div>

        {/* ----------------------------------------------------------- rail -- */}
        <aside className="flex w-[360px] shrink-0 flex-col overflow-hidden 2xl:w-[420px]">
          {selectedPort ? (
            <SelectedPort
              port={selectedPort}
              onClear={() => setSelected(null)}
              onOpen={() => setPortCode(selectedPort.code)}
            />
          ) : null}

          <Panel
            title="Priority ports"
            note={`${portList.length} ranked`}
            className="min-h-0 flex-1 rounded-none border-x-0 border-t-0"
            scroll
          >
            <ul>
              {portList.map((port, index) => (
                <li key={port.code}>
                  <button
                    type="button"
                    onClick={() => setSelected(port.code)}
                    onMouseEnter={() => setHovered(port.code)}
                    onMouseLeave={() => setHovered(null)}
                    className={`grid w-full grid-cols-[18px_1fr_54px_60px_46px] items-center gap-2 border-b border-[var(--line)]/50 px-2.5 py-[6px] text-left transition-colors ${
                      selected === port.code ? "bg-[var(--panel-3)]" : "hover:bg-[var(--panel-2)]"
                    }`}
                  >
                    <span className="num text-[10.5px] text-[var(--text-3)]">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="flex min-w-0 items-center gap-1.5">
                      <Dot tone={riskTone(port.risk)} />
                      <span className="truncate text-[12px] text-[var(--text)]">{port.name}</span>
                    </span>
                    <Num value={port.congestionIndex} className="text-right text-[12px]" />
                    <span className="flex justify-end">
                      <Pill tone={riskTone(port.risk)}>{riskLabel(port.risk)}</Pill>
                    </span>
                    <Sparkline
                      data={port.congestionHistory.map((point) => point.value)}
                      tone={riskTone(port.risk)}
                      height={16}
                      fill={false}
                    />
                  </button>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel
            title="Action queue"
            note={`${alerts.length} open`}
            className="h-[236px] shrink-0 rounded-none border-x-0 border-b-0"
            scroll
          >
            {alerts.length === 0 ? (
              <p className="p-3 text-[11.5px] text-[var(--text-3)]">
                The decision layer issued no action for the current forecast.
              </p>
            ) : (
              <ul>
                {alerts.map((alert, index) => (
                  <li
                    key={alert.id}
                    className="border-b border-[var(--line)]/50 px-2.5 py-2 last:border-0"
                  >
                    <div className="flex items-baseline gap-2">
                      <span className="num text-[10px] text-[var(--text-3)]">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <Pill tone={severityTone(alert.severity)}>{alert.severity}</Pill>
                      <span className="num ml-auto text-[10px] text-[var(--text-3)]">
                        conf {alert.confidence?.toFixed(2) ?? "n/a"}
                      </span>
                    </div>
                    <p className="mt-1 text-[11.5px] leading-snug text-[var(--text-2)]">
                      {alert.text}
                    </p>
                    <div className="num mt-0.5 text-[10px] text-[var(--text-3)]">
                      {alert.action} · priority {alert.priority?.toFixed(2) ?? "n/a"}
                    </div>
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

function SelectedPort({
  port,
  onClear,
  onOpen,
}: {
  port: PortSnapshot;
  onClear: () => void;
  onOpen: () => void;
}) {
  return (
    <Panel
      title={port.name}
      note={port.code}
      actions={
        <button
          type="button"
          onClick={onClear}
          className="text-[10px] uppercase tracking-[0.08em] hover:text-[var(--text)]"
        >
          Clear
        </button>
      }
      className="shrink-0 rounded-none border-x-0 border-t-0"
    >
      <div className="p-2.5">
        <div className="mb-2 flex items-center gap-2">
          <Pill tone={riskTone(port.risk)} solid>
            {riskLabel(port.risk)}
          </Pill>
          <span className="text-[11.5px] text-[var(--text-2)]">{port.regime}</span>
          <ProvenanceTag
            status={port.dataStatus}
            ageHours={port.dataAgeHours}
            detail={`Observed ${formatUtc(port.observedAt)}`}
            className="ml-auto"
          />
        </div>

        <div className="grid grid-cols-3 gap-x-3 gap-y-2">
          {(
            [
              ["Day 1", <Num key="1" value={port.congestionIndex} className="text-[15px]" />],
              ["Peak", <Num key="2" value={port.peakCongestionIndex} className="text-[15px]" />],
              ["Wait", <Num key="3" value={port.delayHours} unit="h" className="text-[15px]" />],
              [
                "80% band",
                <span key="4" className="num text-[12px] text-[var(--text-2)]">
                  {port.forecastQ10?.toFixed(0) ?? "—"}–{port.forecastQ90?.toFixed(0) ?? "—"}
                </span>,
              ],
              [
                "Confidence",
                <Num key="5" value={port.confidence} digits={0} scale={100} unit="%" className="text-[12px]" />,
              ],
              [
                "Disagreement",
                <Num key="6" value={port.modelDisagreement} digits={2} className="text-[12px]" />,
              ],
            ] as const
          ).map(([label, value]) => (
            <div key={label}>
              <div className="eyebrow text-[9px]">{label}</div>
              <div className="mt-0.5">{value}</div>
            </div>
          ))}
        </div>

        {port.actionTitle ? (
          <div className="mt-2.5 border-t border-[var(--line)] pt-2">
            <div className="eyebrow mb-1">Recommended action</div>
            <div className="text-[12.5px] text-[var(--text)]">{port.actionTitle}</div>
            <div className="num mt-0.5 text-[10.5px] text-[var(--text-3)]">
              {port.recommendedAction} · priority {port.priorityScore?.toFixed(2) ?? "n/a"}
            </div>
          </div>
        ) : null}

        <div className="mt-2.5 flex flex-wrap gap-2 border-t border-[var(--line)] pt-2">
          <Link
            to="/port/overview"
            onClick={onOpen}
            className="inline-flex items-center gap-1 rounded-[2px] border border-[var(--line-strong)] px-2 py-[4px] text-[11px] text-[var(--text-2)] hover:text-[var(--text)]"
          >
            Open port twin <ArrowUpRight size={11} />
          </Link>
          <Link
            to="/admin/scenarios"
            className="inline-flex items-center gap-1 rounded-[2px] border border-[var(--line-strong)] px-2 py-[4px] text-[11px] text-[var(--text-2)] hover:text-[var(--text)]"
          >
            Stress-test <ArrowUpRight size={11} />
          </Link>
        </div>
      </div>
    </Panel>
  );
}
