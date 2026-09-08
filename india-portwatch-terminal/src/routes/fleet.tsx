import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  Chip,
  Delta,
  ErrorState,
  Loading,
  Metric,
  Panel,
  Value,
  formatUtc,
  riskTone,
} from "@/components/terminal/ui";
import { fetchFleet, fetchPorts } from "@/services/portwatch";

export const Route = createFileRoute("/fleet")({ component: FleetBoard });

/**
 * Fleet board. Each row is the route optimizer's comparison of the intended
 * call against the best alternative, with the ETA, risk and port-wait
 * differences that justify the recommendation. A reroute is only advised when
 * the measured saving clears the diversion cost.
 */
function FleetBoard() {
  const navigate = useNavigate();

  const fleetQuery = useQuery({
    queryKey: ["fleet"],
    queryFn: fetchFleet,
    staleTime: 60_000,
  });
  const portsQuery = useQuery({
    queryKey: ["ports"],
    queryFn: fetchPorts,
    staleTime: 60_000,
  });

  if (fleetQuery.isLoading) return <Loading label="LOADING ROUTE RECOMMENDATIONS" />;
  if (fleetQuery.isError || !fleetQuery.data) {
    return <ErrorState error={fleetQuery.error} />;
  }

  const fleet = fleetQuery.data;
  const ports = portsQuery.data ?? [];
  const portName = (code: string | null) =>
    ports.find((port) => port.code === code)?.short ?? code ?? "n/a";

  const reroutes = fleet.filter((row) => row.reroute).length;
  const savings = fleet
    .map((row) => row.etaDeltaHours)
    .filter((value): value is number => value != null && value < 0);
  const bestSaving = savings.length ? Math.min(...savings) : null;

  return (
    <div className="h-full grid grid-rows-[auto_auto_1fr] gap-2 p-2 overflow-hidden">
      <div className="grid grid-cols-4 gap-2">
        <Metric
          label="VESSELS SCORED"
          value={fleet.length}
          tone="cyan"
          sub="against the live forecast"
        />
        <Metric
          label="REROUTES ADVISED"
          value={reroutes}
          tone={reroutes ? "amber" : "mint"}
          sub="only when the saving clears diversion cost"
        />
        <Metric
          label="BEST ETA SAVING"
          value={bestSaving == null ? "none" : `${bestSaving.toFixed(1)}h`}
          tone="mint"
          sub="negative = alongside sooner"
        />
        <Metric
          label="FORECAST ORIGIN"
          value={formatUtc(fleet[0]?.originDate ?? null)}
          tone="cyan"
          sub={fleet[0]?.source ?? "route optimizer"}
        />
      </div>

      <Panel title="ROUTE RECOMMENDATIONS">
        <div className="overflow-auto">
          <table className="w-full text-[10px]">
            <thead>
              <tr className="label-xs text-left border-b border-[var(--color-line)]">
                <th className="py-1.5 px-2 font-normal">VESSEL</th>
                <th className="py-1.5 px-2 font-normal">INTENDED</th>
                <th className="py-1.5 px-2 font-normal">RECOMMENDED</th>
                <th className="py-1.5 px-2 font-normal text-right">BEST DAY</th>
                <th className="py-1.5 px-2 font-normal text-right">Δ ETA</th>
                <th className="py-1.5 px-2 font-normal text-right">Δ PORT WAIT</th>
                <th className="py-1.5 px-2 font-normal text-right">Δ RISK</th>
                <th className="py-1.5 px-2 font-normal text-right">BUFFER</th>
                <th className="py-1.5 px-2 font-normal text-right">DIVERSION</th>
                <th className="py-1.5 px-2 font-normal">CALL</th>
              </tr>
            </thead>
            <tbody>
              {fleet.map((row) => (
                <tr key={row.id} className="border-b border-[var(--color-line)]/30">
                  <td className="py-1.5 px-2 text-[var(--color-foreground)]">
                    {row.name}
                  </td>
                  <td className="py-1.5 px-2">
                    <button
                      onClick={() =>
                        row.intendedPortCode &&
                        navigate({
                          to: "/port",
                          search: { port: row.intendedPortCode },
                        })
                      }
                      className="hover:text-[var(--color-cyan)] hover:underline"
                    >
                      {portName(row.intendedPortCode)}
                    </button>
                  </td>
                  <td className="py-1.5 px-2">
                    <button
                      onClick={() =>
                        row.recommendedPortCode &&
                        navigate({
                          to: "/port",
                          search: { port: row.recommendedPortCode },
                        })
                      }
                      className={
                        row.reroute
                          ? "text-[var(--color-amber)] hover:underline"
                          : "hover:text-[var(--color-cyan)] hover:underline"
                      }
                    >
                      {portName(row.recommendedPortCode)}
                    </button>
                  </td>
                  <td className="py-1.5 px-2 text-right tabular-nums">
                    <Value value={row.bestArrivalDay} digits={0} />
                  </td>
                  <td className="py-1.5 px-2 text-right">
                    <Delta value={row.etaDeltaHours} digits={1} unit="h" />
                  </td>
                  <td className="py-1.5 px-2 text-right">
                    <Delta value={row.portWaitDeltaHours} digits={1} unit="h" />
                  </td>
                  <td className="py-1.5 px-2 text-right">
                    <Delta value={row.riskDelta} digits={3} />
                  </td>
                  <td className="py-1.5 px-2 text-right tabular-nums">
                    <Value value={row.bufferHours} digits={0} unit="h" />
                  </td>
                  <td className="py-1.5 px-2 text-right tabular-nums text-[var(--color-muted-foreground)]">
                    <Value value={row.diversionKm} digits={0} unit=" km" />
                  </td>
                  <td className="py-1.5 px-2">
                    <Chip tone={row.reroute ? "amber" : "mint"}>
                      {row.reroute ? "REROUTE" : "KEEP"}
                    </Chip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!fleet.length && (
            <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
              No route recommendations were produced in this run.
            </div>
          )}
        </div>
      </Panel>

      <Panel title="OPTIMIZER REASONING" bodyClassName="overflow-auto">
        <div className="p-2 space-y-2">
          {fleet.map((row) => (
            <div
              key={row.id}
              className="border-b border-[var(--color-line)]/30 pb-2 last:border-0"
            >
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-[var(--color-foreground)]">
                  {row.name}
                </span>
                <Chip tone={riskTone(row.reroute ? "high" : "normal")}>
                  {row.reroute ? "REROUTE ADVISED" : "KEEP INTENDED CALL"}
                </Chip>
              </div>
              <div className="mt-1 text-[10px] leading-relaxed text-[var(--color-muted-foreground)]">
                {row.recommendation}
              </div>
            </div>
          ))}
          {!fleet.length && (
            <div className="text-[10px] text-[var(--color-muted-foreground)]">
              Run the pipeline to populate the fleet board.
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}
