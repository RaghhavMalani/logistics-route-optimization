import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { useMemo, useState } from "react";

import { useAuth } from "@/auth/AuthProvider";
import { QuantileChart, Sparkline } from "@/components/kit/charts";
import { Page, PageBody, PageHeader, Panel, StatStrip, Toolbar } from "@/components/kit/layout";
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
import { useDecision, useForecast, usePorts, useWeather } from "@/services/hooks";
import type { PortSnapshot } from "@/types/portwatch";

export const Route = createFileRoute("/admin/ports")({ component: AdminPorts });

function AdminPorts() {
  const ports = usePorts();
  const weather = useWeather();
  const { setPortCode } = useAuth();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return ports.data ?? [];
    return (ports.data ?? []).filter(
      (port) =>
        port.name.toLowerCase().includes(term) ||
        port.code.toLowerCase().includes(term) ||
        port.short.toLowerCase().includes(term) ||
        (port.authority ?? "").toLowerCase().includes(term),
    );
  }, [ports.data, search]);

  const activeCode = selected ?? rows[0]?.code ?? null;
  const active = (ports.data ?? []).find((port) => port.code === activeCode) ?? null;
  const forecast = useForecast(activeCode);
  const decision = useDecision(activeCode);

  if (ports.isLoading || ports.isError) {
    return (
      <ScreenFallback
        title="Ports"
        context={<span>Every port in the network, ranked by decision priority</span>}
        isLoading={ports.isLoading}
        error={ports.error}
        retry={() => void ports.refetch()}
        label="Loading the port network"
      />
    );
  }

  const all = ports.data ?? [];
  const weatherByCode = new Map((weather.data ?? []).map((signal) => [signal.portCode, signal]));

  const columns: Array<Column<PortSnapshot>> = [
    {
      key: "priority",
      header: "Priority",
      align: "right",
      width: 96,
      hint: "Decision-layer ranking across the network",
      render: (port) => <Num value={port.priorityScore} digits={2} />,
      sort: (port) => port.priorityScore,
    },
    {
      key: "name",
      header: "Port",
      render: (port) => (
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate text-[var(--text)]">{port.name}</span>
          <span className="num shrink-0 text-[10px] text-[var(--text-3)]">{port.code}</span>
        </span>
      ),
      sort: (port) => port.name,
    },
    {
      key: "risk",
      header: "Risk",
      width: 118,
      render: (port) => <Pill tone={riskTone(port.risk)}>{riskLabel(port.risk)}</Pill>,
      sort: (port) => port.congestionIndex,
    },
    { key: "regime", header: "Regime", width: 118, render: (port) => <span className="num text-[var(--text-2)]">{port.regime}</span>, sort: (port) => port.regime },
    { key: "observed", header: "Observed", align: "right", width: 96, render: (port) => <Num value={port.observedCongestionIndex} />, sort: (port) => port.observedCongestionIndex },
    { key: "day1", header: "Day-1", align: "right", width: 88, render: (port) => <Num value={port.congestionIndex} />, sort: (port) => port.congestionIndex },
    { key: "peak", header: "Peak", align: "right", width: 100, render: (port) => (<span className="num">{port.peakCongestionIndex.toFixed(1)}<span className="ml-1 text-[10px] text-[var(--text-3)]">d{port.peakDay}</span></span>), sort: (port) => port.peakCongestionIndex },
    { key: "wait", header: "Wait", align: "right", width: 88, render: (port) => <Num value={port.delayHours} unit="h" />, sort: (port) => port.delayHours },
    { key: "calls", header: "Calls/day", align: "right", width: 100, render: (port) => <Num value={port.vesselCalls} />, sort: (port) => port.vesselCalls },
    { key: "queue", header: "Queue", align: "right", width: 92, render: (port) => <Num value={port.queuePressure} digits={2} />, sort: (port) => port.queuePressure },
    {
      key: "wx",
      header: "Weather",
      align: "right",
      width: 96,
      render: (port) => <Num value={weatherByCode.get(port.code)?.impactScore} digits={3} />,
      sort: (port) => weatherByCode.get(port.code)?.impactScore ?? null,
    },
    {
      key: "conf",
      header: "Confidence",
      align: "right",
      width: 106,
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
      key: "action",
      header: "Action",
      width: 168,
      render: (port) => <span className="text-[var(--text-2)]">{port.actionTitle ?? "—"}</span>,
      sort: (port) => port.actionTitle,
    },
    {
      key: "data",
      header: "Data",
      align: "right",
      width: 108,
      render: (port) => <ProvenanceTag status={port.dataStatus} ageHours={port.dataAgeHours} />,
      sort: (port) => port.dataAgeHours,
    },
    {
      key: "trend",
      header: "14 days",
      width: 92,
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
        title="Ports"
        context={<span>Every port in the network, ranked by decision priority</span>}
        meta={<span className="num">{all.length} ports</span>}
      />

      <StatStrip
        size="sm"
        items={[
          { label: "Ports", value: all.length, note: "in the registry and the panel" },
          {
            label: "Severe",
            value: all.filter((port) => port.risk === "severe").length,
            tone: "crit",
            note: all.filter((port) => port.risk === "severe").map((port) => port.short).join(" · ") || "none",
          },
          {
            label: "Congested",
            value: all.filter((port) => port.risk === "congested").length,
            tone: "warn",
            note: "index at or above the watch threshold",
          },
          {
            label: "Mean berth wait",
            value: all.length
              ? (all.reduce((sum, port) => sum + port.delayHours, 0) / all.length).toFixed(1)
              : "n/a",
            unit: "h",
            note: "predicted, across the network",
          },
          {
            label: "Stale feeds",
            value: all.filter((port) => port.dataStatus === "STALE").length,
            tone: all.some((port) => port.dataStatus === "STALE") ? "warn" : "ok",
            note: "port activity older than its freshness budget",
          },
        ]}
      />

      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Filter ports" className="w-[280px]" />
        <span className="num ml-auto text-[11px] text-[var(--text-3)]">
          {rows.length} of {all.length}
        </span>
      </Toolbar>

      <PageBody padded={false} className="flex min-h-0 overflow-hidden">
        <Panel className="min-w-0 flex-1 rounded-none border-0 border-r border-[var(--line)]">
          <DataTable
            rows={rows}
            columns={columns}
            rowKey={(port) => port.code}
            selectedKey={activeCode}
            onRowClick={(port) => setSelected(port.code)}
            initialSort="priority"
            rowTone={(port) =>
              port.risk === "severe"
                ? "var(--crit)"
                : port.risk === "congested"
                  ? "var(--warn)"
                  : null
            }
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
                  <KeyValue label="Coast" dense>
                    <span className="text-[11.5px]">{active.coast ?? "n/a"}</span>
                  </KeyValue>
                  <KeyValue label="Regime confidence" dense>
                    <Num value={active.regimeConfidence} digits={2} />
                  </KeyValue>
                  <KeyValue label="Expected remaining" dense>
                    <Num value={active.expectedRemainingDays} unit="d" />
                  </KeyValue>
                  <KeyValue label="Transition risk 24h" dense>
                    <Num value={active.transitionRisk24h} digits={3} />
                  </KeyValue>
                  <KeyValue label="Model disagreement" dense>
                    <Num value={active.modelDisagreement} digits={2} tone="unc" />
                  </KeyValue>
                  <div className="mt-2 flex flex-wrap gap-2 border-t border-[var(--line)] pt-2">
                    <Link
                      to="/port/overview"
                      onClick={() => setPortCode(active.code)}
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
                title="Decision"
                note={decision.data?.severity}
                className="min-h-0 flex-1 rounded-none border-x-0 border-b-0"
              >
                {decision.data ? (
                  <div className="p-3">
                    <h2 className="text-[13.5px] font-medium leading-snug text-[var(--text)]">
                      {decision.data.title}
                    </h2>
                    <div className="num mt-1 text-[10.5px] text-[var(--text-3)]">
                      {decision.data.action} · {decision.data.target} · day{" "}
                      {decision.data.horizonDay}
                    </div>
                    <p className="mt-2 text-[12px] leading-relaxed text-[var(--text-2)]">
                      {decision.data.rationale}
                    </p>
                    <div className="mt-2 border-t border-[var(--line)] pt-2">
                      <KeyValue label="Expected delay saved" dense>
                        <Num value={decision.data.expectedDelaySavedHours} unit="h" tone="ok" />
                      </KeyValue>
                      <KeyValue label="Confidence" dense>
                        <Num value={decision.data.confidence} digits={2} />
                      </KeyValue>
                      <KeyValue label="Uncertainty" dense>
                        <Num value={decision.data.uncertainty} digits={2} tone="unc" />
                      </KeyValue>
                    </div>
                  </div>
                ) : (
                  <p className="p-3 text-[11.5px] text-[var(--text-3)]">
                    No decision artefact for this port in the current run.
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
