import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { statusTone, useFleetIntel, type VesselIntel } from "@/components/app/fleet-context";
import { Page, PageBody, PageHeader, Panel, SegmentedControl, Toolbar } from "@/components/kit/layout";
import {
  Delta,
  Dot,
  MiniBar,
  Num,
  Pill,
  formatUtc,
  riskLabel,
  riskTone,
} from "@/components/kit/primitives";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { DataTable, SearchInput, type Column } from "@/components/kit/table";

export const Route = createFileRoute("/vessel/fleet")({ component: FleetBoard });

type Filter = "all" | "reroute" | "risk" | "weather";

const FILTERS: Array<{ value: Filter; label: string }> = [
  { value: "all", label: "All" },
  { value: "reroute", label: "Reroute advised" },
  { value: "risk", label: "Wait risk" },
  { value: "weather", label: "Weather exposed" },
];

function formatEta(date: Date | null): string {
  if (!date) return "—";
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${String(date.getUTCDate()).padStart(2, "0")} ${months[date.getUTCMonth()]}`;
}

function FleetBoard() {
  const { intel, isLoading, error, refetch } = useFleetIntel();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    return intel.filter((row) => {
      if (filter === "reroute" && !row.vessel.reroute) return false;
      if (filter === "risk" && (row.vessel.intendedCongestionProbability ?? 0) < 0.5) return false;
      if (filter === "weather" && (row.weather?.impactScore ?? 0) < 0.15) return false;
      if (!term) return true;
      return (
        row.vessel.name.toLowerCase().includes(term) ||
        row.vessel.id.toLowerCase().includes(term) ||
        (row.vessel.intendedPortName ?? "").toLowerCase().includes(term) ||
        (row.vessel.intendedPortCode ?? "").toLowerCase().includes(term)
      );
    });
  }, [filter, intel, search]);

  if (isLoading || error) {
    return (
      <ScreenFallback
        title="Fleet"
        context={<span>Every declared call scored against the live forecast</span>}
        isLoading={isLoading}
        error={error}
        retry={refetch}
        label="Loading fleet"
      />
    );
  }

  const columns: Array<Column<VesselIntel>> = [
    {
      key: "vessel",
      header: "Vessel",
      width: 156,
      render: (row) => (
        <Link
          to="/vessel/$vesselId"
          params={{ vesselId: row.vessel.id }}
          className="flex items-center gap-1.5 font-medium text-[var(--text)] hover:text-[var(--info)]"
        >
          <Dot tone={statusTone(row.status)} />
          {row.vessel.name}
        </Link>
      ),
      sort: (row) => row.vessel.name,
    },
    {
      key: "id",
      header: "Vessel ID",
      width: 138,
      hint: "Optimizer identifier — the routing artefact carries no IMO number",
      render: (row) => <span className="num text-[var(--text-3)]">{row.vessel.id}</span>,
      sort: (row) => row.vessel.id,
    },
    {
      key: "position",
      header: "Position",
      width: 120,
      hint: "No AIS track in this artefact: routing is anchored at the declared call",
      render: () => <span className="num text-[var(--text-3)]">not tracked</span>,
    },
    {
      key: "destination",
      header: "Destination",
      width: 176,
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
      width: 104,
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
      key: "window",
      header: "Arrival window",
      align: "right",
      width: 124,
      hint: "Declared earliest and latest acceptable arrival, in horizon days",
      render: (row) =>
        row.arrivalWindow ? (
          <span className="num text-[var(--text-2)]">
            +{row.arrivalWindow.earliest} … +{row.arrivalWindow.latest}
          </span>
        ) : (
          <span className="num text-[var(--text-3)]">n/a</span>
        ),
      sort: (row) => row.arrivalWindow?.latest ?? null,
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
      key: "delta",
      header: "Δ wait if rerouted",
      align: "right",
      width: 138,
      hint: "Negative means the alternative call is alongside sooner",
      render: (row) => <Delta value={row.vessel.portWaitDeltaHours} unit="h" />,
      sort: (row) => row.vessel.portWaitDeltaHours,
    },
    {
      key: "congestion",
      header: "Destination congestion",
      align: "right",
      width: 168,
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
      key: "entry",
      header: "Port entry risk",
      align: "right",
      width: 126,
      hint: "P(congestion index > 50) at the scored arrival day",
      render: (row) => (
        <span className="flex items-center justify-end gap-2">
          <span className="w-9">
            <MiniBar
              value={row.vessel.intendedCongestionProbability}
              tone={(row.vessel.intendedCongestionProbability ?? 0) >= 0.5 ? "crit" : "info"}
            />
          </span>
          <Num value={row.vessel.intendedCongestionProbability} digits={2} />
        </span>
      ),
      sort: (row) => row.vessel.intendedCongestionProbability ?? null,
    },
    {
      key: "wx",
      header: "Weather exposure",
      align: "right",
      width: 142,
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
      key: "conf",
      header: "Confidence",
      align: "right",
      width: 106,
      render: (row) => <Num value={row.destination?.confidence} digits={0} scale={100} unit="%" />,
      sort: (row) => row.destination?.confidence ?? null,
    },
    {
      key: "action",
      header: "Recommended action",
      width: 250,
      render: (row) => <span className="text-[var(--text-2)]">{row.action}</span>,
      sort: (row) => row.action,
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Fleet"
        context={<span>Every declared call scored against the live forecast</span>}
        meta={
          <span className="num">
            origin {formatUtc(intel[0]?.vessel.originDate ?? null)}
          </span>
        }
      />

      <Toolbar>
        <SegmentedControl
          ariaLabel="Filter fleet"
          value={filter}
          options={FILTERS}
          onChange={setFilter}
        />
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Filter by vessel or destination"
          className="w-[280px]"
        />
        <span className="num ml-auto text-[11px] text-[var(--text-3)]">
          {rows.length} of {intel.length} vessels
        </span>
      </Toolbar>

      <PageBody padded={false} className="min-h-0">
        <Panel className="h-full rounded-none border-0">
          {rows.length === 0 ? (
            <EmptyState
              title="Nothing matches"
              detail="No vessel in the routing artefact matches this filter."
            />
          ) : (
            <DataTable
              rows={rows}
              columns={columns}
              rowKey={(row) => row.vessel.id}
              onRowClick={(row) =>
                void navigate({ to: "/vessel/$vesselId", params: { vesselId: row.vessel.id } })
              }
              initialSort="eta"
              initialDirection="asc"
              rowTone={(row) =>
                row.status === "reroute advised"
                  ? "var(--warn)"
                  : row.status === "monitor"
                    ? "var(--info)"
                    : null
              }
            />
          )}
        </Panel>
      </PageBody>
    </Page>
  );
}
