import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  Chip,
  ErrorState,
  Loading,
  Metric,
  MetricRow,
  Panel,
  ProvenanceChip,
  Value,
  formatUtc,
} from "@/components/terminal/ui";
import {
  fetchFeedAdapters,
  fetchPorts,
  fetchVessels,
} from "@/services/portwatch";

export const Route = createFileRoute("/sar")({
  validateSearch: (search: Record<string, unknown>) => ({
    port: typeof search.port === "string" ? search.port : "INMAA",
  }),
  component: VesselActivityScreen,
});

/**
 * Vessel activity. This deployment has no per-vessel AIS licence and no SAR
 * scene ingestion, so the screen does not draw individual ships. It shows what
 * is actually measured -- daily satellite-AIS port-call aggregates from IMF
 * PortWatch and the queue buildup derived from each port's own baseline -- and
 * reports the unwired feeds as unavailable rather than filling them in.
 */
function VesselActivityScreen() {
  const { port: portCode } = Route.useSearch();
  const navigate = useNavigate();

  const vesselsQuery = useQuery({
    queryKey: ["vessels"],
    queryFn: fetchVessels,
    staleTime: 60_000,
  });
  const adaptersQuery = useQuery({
    queryKey: ["feed-adapters"],
    queryFn: fetchFeedAdapters,
    staleTime: 120_000,
  });
  const portsQuery = useQuery({
    queryKey: ["ports"],
    queryFn: fetchPorts,
    staleTime: 60_000,
  });

  if (vesselsQuery.isLoading) return <Loading label="LOADING VESSEL ACTIVITY" />;
  if (vesselsQuery.isError || !vesselsQuery.data) {
    return <ErrorState error={vesselsQuery.error} />;
  }

  const bundle = vesselsQuery.data;
  const adapters = adaptersQuery.data ?? [];
  const ports = portsQuery.data ?? [];
  const ranked = [...bundle.vessels].sort(
    (a, b) => b.queuePressure - a.queuePressure,
  );
  const selected =
    ranked.find((row) => row.portCode === portCode) ?? ranked[0] ?? null;
  const selectedPort = ports.find((p) => p.code === selected?.portCode);

  const totalCalls = bundle.vessels.reduce(
    (sum, row) => sum + (row.dailyPortCalls ?? 0),
    0,
  );
  const totalQueue = bundle.vessels.reduce(
    (sum, row) => sum + (row.queueBuildup ?? 0),
    0,
  );

  return (
    <div className="h-full grid grid-rows-[auto_1fr] gap-2 p-2 overflow-hidden">
      <div className="grid grid-cols-4 gap-2">
        <Metric
          label="DAILY PORT CALLS"
          value={totalCalls.toFixed(0)}
          tone="cyan"
          sub={`across ${bundle.vessels.length} ports`}
        />
        <Metric
          label="QUEUE BUILDUP"
          value={totalQueue.toFixed(1)}
          tone="amber"
          sub="calls above each port's own baseline"
        />
        <Metric
          label="HIGHEST QUEUE PRESSURE"
          value={ranked[0]?.queuePressure.toFixed(2) ?? "n/a"}
          tone="red"
          sub={ranked[0]?.name ?? "no data"}
        />
        <Metric
          label="OBSERVED"
          value={formatUtc(bundle.observedAt)}
          tone="mint"
          sub="latest satellite-AIS day"
        />
      </div>

      <div className="min-h-0 grid grid-cols-[1.2fr_1fr] gap-2">
        <Panel title="PORT ACTIVITY · MEASURED DAILY AGGREGATES">
          <div className="overflow-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="label-xs text-left border-b border-[var(--color-line)]">
                  <th className="py-1.5 px-2 font-normal">PORT</th>
                  <th className="py-1.5 px-2 font-normal text-right">CALLS/DAY</th>
                  <th className="py-1.5 px-2 font-normal text-right">QUEUE BUILDUP</th>
                  <th className="py-1.5 px-2 font-normal">QUEUE PRESSURE</th>
                  <th className="py-1.5 px-2 font-normal text-right">CONF</th>
                  <th className="py-1.5 px-2 font-normal">OBSERVED</th>
                </tr>
              </thead>
              <tbody>
                {ranked.map((row) => (
                  <tr
                    key={row.portCode}
                    onClick={() =>
                      navigate({ to: "/sar", search: { port: row.portCode } })
                    }
                    className={`border-b border-[var(--color-line)]/30 cursor-pointer ${
                      row.portCode === selected?.portCode
                        ? "bg-[var(--color-cyan)]/6"
                        : "hover:bg-[var(--color-cyan)]/4"
                    }`}
                  >
                    <td className="py-1 px-2 truncate">{row.name}</td>
                    <td className="py-1 px-2 text-right tabular-nums">
                      {row.dailyPortCalls.toFixed(1)}
                    </td>
                    <td className="py-1 px-2 text-right tabular-nums text-[var(--color-amber)]">
                      {row.queueBuildup.toFixed(1)}
                    </td>
                    <td className="py-1 px-2 w-[130px]">
                      <div className="flex items-center gap-2">
                        <Bar
                          value={row.queuePressure}
                          tone={
                            row.queuePressure >= 0.7
                              ? "red"
                              : row.queuePressure >= 0.5
                                ? "amber"
                                : "cyan"
                          }
                        />
                        <span className="tabular-nums text-[9px] w-8 text-right">
                          {row.queuePressure.toFixed(2)}
                        </span>
                      </div>
                    </td>
                    <td className="py-1 px-2 text-right tabular-nums text-[var(--color-cyan)]">
                      <Value value={row.confidence} digits={2} />
                    </td>
                    <td className="py-1 px-2 text-[var(--color-muted-foreground)]">
                      {formatUtc(row.observedAt)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <div className="min-h-0 grid grid-rows-[auto_auto_1fr] gap-2">
          {selected && (
            <Panel title={`${selected.name.toUpperCase()} · ACTIVITY DETAIL`}>
              <div className="p-3">
                <MetricRow label="Daily port calls (7d mean)">
                  <span className="tabular-nums">
                    {selected.dailyPortCalls.toFixed(2)}
                  </span>
                </MetricRow>
                <MetricRow label="Calls above baseline">
                  <span className="tabular-nums text-[var(--color-amber)]">
                    {selected.queueBuildup.toFixed(2)}
                  </span>
                </MetricRow>
                <MetricRow label="Queue pressure (0-1)">
                  <span className="tabular-nums">
                    {selected.queuePressure.toFixed(3)}
                  </span>
                </MetricRow>
                <MetricRow label="Feed confidence">
                  <Value value={selected.confidence} digits={2} tone="cyan" />
                </MetricRow>
                {selectedPort && (
                  <>
                    <MetricRow label="Observed congestion">
                      <Value
                        value={selectedPort.observedCongestionIndex}
                        digits={1}
                      />
                    </MetricRow>
                    <MetricRow label="Day-1 forecast">
                      <span className="tabular-nums">
                        {selectedPort.congestionIndex.toFixed(1)}
                      </span>
                    </MetricRow>
                  </>
                )}
                <div className="mt-2 text-[9px] leading-snug text-[var(--color-muted-foreground)]">
                  {selected.basis}
                </div>
              </div>
            </Panel>
          )}

          <Panel title="FEED ADAPTERS">
            <div className="p-2 space-y-2">
              {adapters.map((adapter) => (
                <div
                  key={adapter.key}
                  className="border-b border-[var(--color-line)]/30 pb-2 last:border-0"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] text-[var(--color-foreground)] truncate">
                      {adapter.name}
                    </span>
                    <ProvenanceChip
                      status={adapter.status}
                      ageHours={adapter.ageHours}
                      detail={adapter.detail}
                    />
                  </div>
                  <div className="text-[9px] text-[var(--color-muted-foreground)] leading-snug">
                    {adapter.provider} · {adapter.granularity}
                    {adapter.observedAt && ` · ${formatUtc(adapter.observedAt)}`}
                  </div>
                  <div className="text-[9px] leading-snug text-[var(--color-muted-foreground)] mt-0.5">
                    {adapter.detail}
                  </div>
                </div>
              ))}
              {!adapters.length && (
                <div className="text-[10px] text-[var(--color-muted-foreground)]">
                  No feed adapters reported.
                </div>
              )}
            </div>
          </Panel>

          <Panel title="WHAT THIS SCREEN IS NOT">
            <div className="p-3 text-[10px] leading-relaxed text-[var(--color-muted-foreground)] space-y-2">
              <p>
                <Chip tone="amber">SCOPE</Chip> This deployment measures
                <span className="text-[var(--color-foreground)]">
                  {" "}
                  daily port-call aggregates
                </span>
                , not individual vessel tracks. Every number above is an
                aggregate over a port-day.
              </p>
              <p>
                Per-vessel AIS positions require a commercial feed, and
                Sentinel-1 SAR detection requires scene ingestion and a detector
                — neither is wired here, so neither is drawn. The adapters panel
                reports both as unavailable rather than showing placeholder
                contacts.
              </p>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
