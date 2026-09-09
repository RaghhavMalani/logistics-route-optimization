import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowLeft, ArrowUpRight } from "lucide-react";
import { useMemo, useState } from "react";

import { statusTone, useFleetIntel } from "@/components/app/fleet-context";
import { ColumnChart, QuantileChart } from "@/components/kit/charts";
import { Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import {
  Delta,
  KeyValue,
  MiniBar,
  Num,
  Pill,
  ProvenanceTag,
  formatUtc,
  riskLabel,
  riskTone,
  severityTone,
} from "@/components/kit/primitives";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { ContextMap } from "@/components/command/ContextMap";
import { selectionGeometry } from "@/components/command/selection-geometry";
import { useRouteExposure } from "@/components/command/VesselInspector";
import { useWorkspaceMap } from "@/components/command/useWorkspaceMap";
import { useFixes } from "@/components/app/traffic-context";
import { useForecast } from "@/services/hooks";

export const Route = createFileRoute("/vessel/$vesselId")({ component: VesselDetail });

function formatEta(date: Date | null): string {
  if (!date) return "—";
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${String(date.getUTCDate()).padStart(2, "0")} ${months[date.getUTCMonth()]}`;
}

function VesselDetail() {
  const { vesselId } = Route.useParams();
  const { intel, isLoading, error, refetch, ports, weather, events } = useFleetIntel();

  const row = intel.find((entry) => entry.vessel.id === vesselId) ?? null;
  const destinationForecast = useForecast(row?.vessel.intendedPortCode ?? null);
  const alternativeForecast = useForecast(
    row?.vessel.reroute ? (row.vessel.recommendedPortCode ?? null) : null,
  );

  /**
   * The vessel's own position, from the traffic source.
   *
   * The routing artefact carries a declared call and an arrival window, never a
   * track. The replay engine turns that into a position by placing the vessel on
   * the water-only passage so it arrives when the artefact says it will -- which
   * is why the map and the fleet board agree instead of contradicting each other.
   */
  const fixes = useFixes(1);
  const fix = useMemo(
    () => fixes.find((entry) => entry.id === `own:${vesselId}`) ?? null,
    [fixes, vesselId],
  );

  const workspace = useWorkspaceMap({ layerOverrides: { corridors: false } });
  const exposure = useRouteExposure(fix, workspace.timeline);
  const geometry = useMemo(
    () =>
      selectionGeometry(fix, exposure, {
        alternativeTo: row?.vessel.reroute ? row.vessel.recommendedPortCode : null,
      }),
    [exposure, fix, row],
  );

  const centre = useMemo<[number, number]>(() => {
    const a = row?.destination?.location;
    const b = row?.alternative?.location;
    if (a && b && row?.vessel.reroute) {
      return [(a.lon + b.lon) / 2, (a.lat + b.lat) / 2];
    }
    if (a) return [a.lon, a.lat];
    return [79.5, 15.5];
  }, [row]);

  if (isLoading || error) {
    return (
      <ScreenFallback
        title="Vessel"
        isLoading={isLoading}
        error={error}
        retry={refetch}
        label="Loading vessel"
      />
    );
  }
  if (!row) {
    return (
      <Page>
        <PageHeader title="Vessel" />
        <PageBody>
          <EmptyState
            title="Not in the roster"
            detail={`No vessel with id ${vesselId} appears in the routing artefact for this run.`}
            action={
              <Link
                to="/vessel/fleet"
                className="inline-flex items-center gap-1 rounded-[2px] border border-[var(--line-strong)] px-2.5 py-[5px] text-[11.5px] text-[var(--text-2)] hover:text-[var(--text)]"
              >
                <ArrowLeft size={11} /> Back to fleet
              </Link>
            }
          />
        </PageBody>
      </Page>
    );
  }

  const { vessel, destination, alternative } = row;
  const forecastRows = destinationForecast.data ?? [];
  const window = row.arrivalWindow;
  const scoredDay = vessel.intendedArrivalDay ?? vessel.bestArrivalDay ?? null;

  return (
    <Page>
      <PageHeader
        title={vessel.name}
        context={
          <>
            <span className="num">{vessel.id}</span>
            <Pill tone={statusTone(row.status)}>{row.status}</Pill>
            <span className="truncate">
              {vessel.intendedPortName ?? vessel.intendedPortCode ?? "n/a"}
              {vessel.reroute ? (
                <>
                  {" → "}
                  <span className="text-[var(--warn)]">
                    {vessel.recommendedPortName ?? vessel.recommendedPortCode}
                  </span>
                </>
              ) : null}
            </span>
          </>
        }
        meta={
          <>
            <span className="num">origin {formatUtc(vessel.originDate)}</span>
            {destination ? (
              <ProvenanceTag
                status={destination.dataStatus}
                ageHours={destination.dataAgeHours}
                detail={`Destination state observed ${formatUtc(destination.observedAt)}`}
              />
            ) : null}
          </>
        }
        actions={
          <Link
            to="/vessel/fleet"
            className="inline-flex items-center gap-1 rounded-[2px] border border-[var(--line-strong)] px-2 py-[4px] text-[11px] text-[var(--text-2)] hover:text-[var(--text)]"
          >
            <ArrowLeft size={11} /> Fleet
          </Link>
        }
      />

      <StatStrip
        items={[
          {
            label: "Current ETA",
            value: formatEta(row.etaDate),
            note: scoredDay != null ? `horizon day +${scoredDay}` : "no scored day",
          },
          {
            label: "Recommended ETA",
            value: formatEta(row.recommendedEtaDate),
            tone: vessel.reroute ? "warn" : "ok",
            note: vessel.reroute
              ? `at ${vessel.recommendedPortName ?? vessel.recommendedPortCode}`
              : "unchanged — same port, same day",
          },
          {
            label: "Predicted berth wait",
            value: vessel.intendedWaitHours?.toFixed(1) ?? "n/a",
            unit: "h",
            tone: (vessel.intendedWaitHours ?? 0) >= 8 ? "warn" : "info",
            note: `buffer advised ${vessel.bufferHours?.toFixed(0) ?? "n/a"}h`,
          },
          {
            label: "Port entry risk",
            value: vessel.intendedCongestionProbability?.toFixed(2) ?? "n/a",
            tone: (vessel.intendedCongestionProbability ?? 0) >= 0.5 ? "crit" : "info",
            note: "P(congestion > 50) on the scored day",
          },
          {
            label: "Weather exposure",
            value: row.weather?.impactScore?.toFixed(3) ?? "n/a",
            tone: (row.weather?.impactScore ?? 0) >= 0.35 ? "warn" : "ok",
            note: row.weather?.weatherRegime ?? "no marine feed at destination",
          },
          {
            label: "Model confidence",
            value: destination ? `${(destination.confidence * 100).toFixed(0)}%` : "n/a",
            note: `disagreement ${destination?.modelDisagreement?.toFixed(2) ?? "n/a"}`,
          },
        ]}
      />

      <PageBody padded={false} className="flex min-h-0 overflow-hidden">
        <div className="relative min-w-0 flex-1 border-r border-[var(--line)]">
          <ContextMap
            workspace={workspace}
            extraData={geometry}
            view={{ center: fix ? [fix.lon, fix.lat] : centre, zoom: 5.4 }}
            note="Own position is SIMULATED by the replay engine and placed so the vessel arrives when the routing artefact says it will. Passage geometry is non-navigational."
          />
        </div>

        <aside className="flex w-[420px] shrink-0 flex-col overflow-y-auto 2xl:w-[480px]">
          <Panel title="Operational recommendation" className="shrink-0 rounded-none border-x-0 border-t-0">
            <div className="p-3">
              <div className="mb-2 flex items-center gap-2">
                <Pill tone={statusTone(row.status)} solid>
                  {row.status}
                </Pill>
                <span className="num text-[11px] text-[var(--text-3)]">{vessel.source}</span>
              </div>
              <h2 className="text-[15px] font-medium leading-snug text-[var(--text)]">
                {row.action}
              </h2>
              <p className="mt-2 text-[12px] leading-relaxed text-[var(--text-2)]">{row.why}</p>
              <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11.5px] leading-relaxed text-[var(--text-3)]">
                {vessel.recommendation}
              </p>
            </div>
          </Panel>

          <Panel
            title="Declared call versus alternative"
            note={vessel.reroute ? "reroute advised" : "no advantage"}
            className="shrink-0 rounded-none border-x-0 border-t-0"
          >
            <table className="data-grid">
              <thead>
                <tr>
                  {["", "Declared", "Alternative", "Δ"].map((header, index) => (
                    <th
                      key={header || index}
                      className={`border-b border-[var(--line)] bg-[var(--panel-2)] px-2.5 py-[6px] text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-3)] ${
                        index === 0 ? "text-left" : "text-right"
                      }`}
                    >
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    [
                      "Port",
                      vessel.intendedPortName ?? vessel.intendedPortCode ?? "n/a",
                      vessel.recommendedPortName ?? vessel.recommendedPortCode ?? "n/a",
                      null,
                    ],
                    [
                      "Arrival day",
                      vessel.intendedArrivalDay != null ? `+${vessel.intendedArrivalDay}` : "n/a",
                      vessel.bestArrivalDay != null ? `+${vessel.bestArrivalDay}` : "n/a",
                      null,
                    ],
                    [
                      "Berth wait",
                      vessel.intendedWaitHours?.toFixed(1) ?? "n/a",
                      vessel.alternativeWaitHours?.toFixed(1) ?? "n/a",
                      vessel.portWaitDeltaHours,
                    ],
                    [
                      "P(congestion)",
                      vessel.intendedCongestionProbability?.toFixed(2) ?? "n/a",
                      vessel.alternativeCongestionProbability?.toFixed(2) ?? "n/a",
                      vessel.intendedCongestionProbability != null &&
                      vessel.alternativeCongestionProbability != null
                        ? vessel.alternativeCongestionProbability -
                          vessel.intendedCongestionProbability
                        : null,
                    ],
                    [
                      "Optimizer cost",
                      vessel.intendedCost?.toFixed(2) ?? "n/a",
                      vessel.alternativeCost?.toFixed(2) ?? "n/a",
                      vessel.intendedCost != null && vessel.alternativeCost != null
                        ? vessel.alternativeCost - vessel.intendedCost
                        : null,
                    ],
                    [
                      "Congestion index",
                      destination?.congestionIndex?.toFixed(1) ?? "n/a",
                      alternative?.congestionIndex?.toFixed(1) ?? "n/a",
                      destination && alternative
                        ? alternative.congestionIndex - destination.congestionIndex
                        : null,
                    ],
                  ] as Array<[string, string, string, number | null]>
                ).map(([label, left, right, delta]) => (
                  <tr key={label} className="border-b border-[var(--line)]/45 last:border-0">
                    <td className="px-2.5 py-[5px] text-[11.5px] text-[var(--text-3)]">{label}</td>
                    <td className="num px-2.5 py-[5px] text-right text-[12px] text-[var(--text)]">
                      {left}
                    </td>
                    <td className="num px-2.5 py-[5px] text-right text-[12px] text-[var(--text-2)]">
                      {right}
                    </td>
                    <td className="px-2.5 py-[5px] text-right text-[12px]">
                      {delta == null ? (
                        <span className="text-[var(--text-3)]">—</span>
                      ) : (
                        <Delta value={delta} digits={2} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="border-t border-[var(--line)] px-3 py-2">
              <KeyValue label="Extra steaming" dense>
                <Num value={vessel.extraSteamingHours} unit="h" />
              </KeyValue>
              <KeyValue label="Diversion" dense>
                <Num value={vessel.diversionKm} digits={0} unit=" km" />
              </KeyValue>
              <KeyValue label="Net ETA change" dense>
                <Delta value={vessel.etaDeltaHours} unit="h" />
              </KeyValue>
              <KeyValue label="Entry-risk change" dense>
                <Delta value={vessel.riskDelta} digits={3} />
              </KeyValue>
            </div>
          </Panel>

          <Panel
            title="Arrival window"
            note={window ? `declared +${window.earliest} … +${window.latest}` : undefined}
            className="shrink-0 rounded-none border-x-0 border-t-0"
          >
            <div className="p-3">
              {forecastRows.length ? (
                <>
                  <ColumnChart
                    height={110}
                    points={forecastRows.map((point) => {
                      const inWindow =
                        window == null ||
                        (point.day >= window.earliest && point.day <= window.latest);
                      return {
                        label: point.dateLabel,
                        value: point.delayHoursP50,
                        tone: !inWindow
                          ? "neutral"
                          : point.day === scoredDay
                            ? "ok"
                            : "info",
                      };
                    })}
                  />
                  <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11.5px] leading-snug text-[var(--text-3)]">
                    Predicted berth wait per horizon day at{" "}
                    {vessel.intendedPortName ?? "the destination"}. Grey columns fall outside
                    the declared window; the green column is the day the optimizer scored.
                  </p>
                </>
              ) : (
                <p className="py-5 text-center text-[11.5px] text-[var(--text-3)]">
                  No forecast rows for the destination port.
                </p>
              )}
            </div>
          </Panel>

          <Panel title="Destination state" className="shrink-0 rounded-none border-x-0 border-t-0">
            {destination ? (
              <div className="px-3 py-2">
                <KeyValue label="Regime" dense>
                  <Pill tone={riskTone(destination.risk)}>{destination.regime}</Pill>
                </KeyValue>
                <KeyValue label="Risk band" dense>
                  <span className="text-[11.5px]">{riskLabel(destination.risk)}</span>
                </KeyValue>
                <KeyValue label="Observed congestion" dense>
                  <Num value={destination.observedCongestionIndex} />
                </KeyValue>
                <KeyValue label="Day-1 forecast" dense>
                  <Num value={destination.congestionIndex} />
                </KeyValue>
                <KeyValue label="80% band" dense>
                  <span className="num text-[11.5px]">
                    {destination.forecastQ10?.toFixed(0) ?? "—"}–
                    {destination.forecastQ90?.toFixed(0) ?? "—"}
                  </span>
                </KeyValue>
                <KeyValue label="Anchorage waiting" dense>
                  <Num value={destination.anchorageCount} />
                </KeyValue>
                <KeyValue label="Transition risk 24h" dense>
                  <Num value={destination.transitionRisk24h} digits={3} />
                </KeyValue>
                <div className="mt-2 border-t border-[var(--line)] pt-2">
                  <Link
                    to="/vessel/ports"
                    className="inline-flex items-center gap-1 text-[11.5px] text-[var(--info)] hover:underline"
                  >
                    Compare destination ports <ArrowUpRight size={11} />
                  </Link>
                </div>
              </div>
            ) : (
              <p className="p-3 text-[11.5px] text-[var(--text-3)]">
                No port snapshot for the declared call in this run.
              </p>
            )}
          </Panel>

          {alternativeForecast.data?.length ? (
            <Panel
              title="Alternative port forecast"
              note={vessel.recommendedPortName ?? undefined}
              className="shrink-0 rounded-none border-x-0 border-t-0"
            >
              <div className="p-3">
                <QuantileChart
                  height={130}
                  threshold={50}
                  points={alternativeForecast.data.map((point) => ({
                    label: point.dateLabel,
                    q10: point.q10,
                    q50: point.q50,
                    q90: point.q90,
                  }))}
                />
              </div>
            </Panel>
          ) : null}

          <Panel
            title="Exposure on this lane"
            note={`${row.exposure.length}`}
            className="min-h-0 flex-1 rounded-none border-x-0 border-b-0"
            scroll
          >
            {row.exposure.length === 0 ? (
              <p className="px-3 py-3 text-[11.5px] leading-snug text-[var(--text-3)]">
                No event in the current feed reports a measured exposure to{" "}
                {vessel.intendedPortName ?? "the destination"}. That is an absence of a
                measured path, not a guarantee of clear water.
              </p>
            ) : (
              <ul>
                {row.exposure.slice(0, 10).map((entry) => (
                  <li
                    key={entry.event.id}
                    className="border-b border-[var(--line)]/50 px-3 py-2 last:border-0"
                  >
                    <div className="flex items-center gap-2">
                      <Pill tone={severityTone(entry.event.severity)}>
                        {entry.event.severity}
                      </Pill>
                      {entry.event.chokepointName ? (
                        <span className="text-[10.5px] text-[var(--text-3)]">
                          {entry.event.chokepointName}
                        </span>
                      ) : null}
                      <span className="num ml-auto text-[10px] text-[var(--text-3)]">
                        exposure {entry.exposure?.toFixed(2) ?? "n/a"}
                      </span>
                    </div>
                    <p className="mt-1 text-[11.5px] leading-snug text-[var(--text-2)]">
                      {entry.event.title}
                    </p>
                    <div className="mt-1">
                      <MiniBar
                        value={entry.exposure}
                        tone={(entry.exposure ?? 0) >= 0.4 ? "warn" : "info"}
                      />
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
