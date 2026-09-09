import { createFileRoute } from "@tanstack/react-router";

import { PortSwitcher, usePortContext } from "@/components/app/port-context";
import { QuantileChart, SeriesChart } from "@/components/kit/charts";
import { Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import {
  KeyValue,
  MiniBar,
  Num,
  Pill,
  ProvenanceTag,
  formatUtc,
  riskTone,
} from "@/components/kit/primitives";
import { ScreenFallback } from "@/components/kit/states";
import { DataTable, type Column } from "@/components/kit/table";
import { useForecast, useRegime } from "@/services/hooks";
import type { ForecastPoint } from "@/types/portwatch";

export const Route = createFileRoute("/port/forecast")({ component: PortForecast });

function PortForecast() {
  const { port, query } = usePortContext();
  const forecast = useForecast(port?.code);
  const regime = useRegime(port?.code);

  if (query.isLoading || forecast.isLoading || forecast.isError || !port) {
    return (
      <ScreenFallback
        title="Forecast"
        isLoading={query.isLoading || forecast.isLoading}
        error={forecast.error ?? (port ? null : new Error("No port selected."))}
        retry={() => void forecast.refetch()}
        label="Loading forecast"
      />
    );
  }

  const rows = forecast.data ?? [];
  const first = rows[0] ?? null;
  const peak = rows.reduce<ForecastPoint | null>(
    (best, row) => (!best || row.congestionIndex > best.congestionIndex ? row : best),
    null,
  );
  const widest = rows.reduce<ForecastPoint | null>(
    (best, row) => (!best || row.intervalWidth > best.intervalWidth ? row : best),
    null,
  );
  const meanConfidence = rows.length
    ? rows.reduce((sum, row) => sum + row.confidence, 0) / rows.length
    : null;

  const columns: Array<Column<ForecastPoint>> = [
    {
      key: "day",
      header: "Day",
      width: 62,
      render: (row) => <span className="num text-[var(--text-2)]">+{row.day}</span>,
      sort: (row) => row.day,
    },
    {
      key: "date",
      header: "Date",
      width: 82,
      render: (row) => <span className="num">{row.dateLabel}</span>,
      sort: (row) => row.targetDate,
    },
    {
      key: "q10",
      header: "q10",
      align: "right",
      width: 70,
      render: (row) => <Num value={row.q10} />,
      sort: (row) => row.q10,
    },
    {
      key: "q50",
      header: "q50",
      align: "right",
      width: 70,
      render: (row) => <Num value={row.q50} className="text-[var(--text)]" />,
      sort: (row) => row.q50,
    },
    {
      key: "q90",
      header: "q90",
      align: "right",
      width: 70,
      render: (row) => <Num value={row.q90} />,
      sort: (row) => row.q90,
    },
    {
      key: "band",
      header: "Band width",
      align: "right",
      width: 100,
      hint: "q90 − q10 after conformal calibration",
      render: (row) => <Num value={row.intervalWidth} />,
      sort: (row) => row.intervalWidth,
    },
    {
      key: "wait",
      header: "Wait",
      align: "right",
      width: 78,
      render: (row) => <Num value={row.delayHoursP50} unit="h" />,
      sort: (row) => row.delayHoursP50,
    },
    {
      key: "wx",
      header: "P(weather)",
      align: "right",
      width: 96,
      render: (row) => <Num value={row.weatherProbability} digits={2} />,
      sort: (row) => row.weatherProbability,
    },
    {
      key: "conf",
      header: "Confidence",
      align: "right",
      width: 108,
      render: (row) => (
        <span className="flex items-center justify-end gap-2">
          <span className="w-10">
            <MiniBar value={row.confidence} tone={row.confidence >= 0.6 ? "ok" : "warn"} />
          </span>
          <Num value={row.confidence} digits={0} scale={100} unit="%" />
        </span>
      ),
      sort: (row) => row.confidence,
    },
    {
      key: "disagree",
      header: "Disagreement",
      align: "right",
      width: 116,
      hint: "Spread between ensemble members on this horizon",
      render: (row) => <Num value={row.modelDisagreement} digits={2} tone="unc" />,
      sort: (row) => row.modelDisagreement,
    },
    {
      key: "sev",
      header: "Severity",
      align: "right",
      width: 90,
      render: (row) => <Pill tone={riskTone(row.severity)}>{row.severity}</Pill>,
      sort: (row) => row.congestionIndex,
    },
  ];

  const state = regime.data;

  return (
    <Page>
      <PageHeader
        title="Forecast"
        context={
          <>
            <span>{port.name}</span>
            <span className="num">{port.code}</span>
            <span className="num">{first?.source ?? port.model ?? "no model"}</span>
          </>
        }
        meta={
          <>
            <span className="num">origin {formatUtc(first?.originDate ?? port.forecastOrigin)}</span>
            <ProvenanceTag status={first?.dataStatus ?? port.dataStatus} ageHours={first?.dataAgeHours} />
          </>
        }
        actions={<PortSwitcher />}
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "Day-1 median",
            value: first?.q50.toFixed(1) ?? "n/a",
            tone: (first?.q50 ?? 0) >= 50 ? "warn" : "ok",
            note: first ? `band ${first.q10.toFixed(0)}–${first.q90.toFixed(0)}` : "no rows",
          },
          {
            label: "Horizon peak",
            value: peak?.congestionIndex.toFixed(1) ?? "n/a",
            tone: (peak?.congestionIndex ?? 0) >= 65 ? "crit" : "warn",
            note: peak ? `day ${peak.day} · ${peak.dateLabel}` : "no rows",
          },
          {
            label: "Widest band",
            value: widest?.intervalWidth.toFixed(1) ?? "n/a",
            tone: "unc",
            note: widest ? `day ${widest.day} — least certain horizon` : "no rows",
          },
          {
            label: "Mean confidence",
            value: meanConfidence != null ? `${(meanConfidence * 100).toFixed(0)}%` : "n/a",
            note: "decays with horizon by construction",
          },
          {
            label: "Conformal offset",
            value: first?.conformalOffset?.toFixed(2) ?? "n/a",
            note: "per-horizon calibration applied to the band",
          },
          {
            label: "Regime",
            value: state?.state ?? port.regime,
            tone: riskTone(port.risk),
            note: `transition risk 24h ${state?.transitionRisk24h?.toFixed(3) ?? port.transitionRisk24h?.toFixed(3) ?? "n/a"}`,
          },
        ]}
      />

      <PageBody className="grid grid-cols-1 gap-3 xl:grid-cols-[1fr_330px]">
        <div className="flex min-w-0 flex-col gap-3">
          <Panel
            title="Ten-day quantile forecast"
            note={
              first?.conformalOffset != null
                ? `conformal ±${first.conformalOffset.toFixed(2)}`
                : undefined
            }
          >
            <div className="p-3">
              <QuantileChart
                height={230}
                threshold={50}
                thresholdLabel="congestion threshold 50"
                yLabel="congestion index"
                points={rows.map((row) => ({
                  label: row.dateLabel,
                  q10: row.q10,
                  q50: row.q50,
                  q90: row.q90,
                }))}
              />
              <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11.5px] leading-snug text-[var(--text-3)]">
                The shaded ribbon is the 80% interval after per-horizon conformal
                calibration; the line inside it is the median. A day is only actionable
                where the band sits clear of the threshold.
              </p>
            </div>
          </Panel>

          <Panel title="Per-horizon detail" className="min-h-[300px]">
            <DataTable
              rows={rows}
              columns={columns}
              rowKey={(row) => String(row.day)}
              initialSort="day"
              initialDirection="asc"
              emptyLabel="No forecast rows for this port"
              rowTone={(row) =>
                row.congestionIndex >= 65
                  ? "var(--crit)"
                  : row.congestionIndex >= 50
                    ? "var(--warn)"
                    : null
              }
            />
          </Panel>
        </div>

        <div className="flex min-w-0 flex-col gap-3">
          <Panel title="Regime" note={state ? `conf ${(state.confidence * 100).toFixed(0)}%` : undefined}>
            {state ? (
              <div className="p-3">
                <div className="mb-2.5 flex items-center justify-between">
                  <span className="text-[15px] font-medium text-[var(--text)]">{state.state}</span>
                  <ProvenanceTag status={state.dataStatus} ageHours={state.dataAgeHours} />
                </div>
                {(
                  [
                    ["p(normal)", state.probabilities.normal, "ok"],
                    ["p(congested)", state.probabilities.congested, "warn"],
                    ["p(severe)", state.probabilities.severe, "crit"],
                  ] as const
                ).map(([label, value, tone]) => (
                  <div key={label} className="mb-2">
                    <div className="mb-1 flex justify-between text-[11.5px]">
                      <span className="text-[var(--text-3)]">{label}</span>
                      <Num value={value} digits={3} />
                    </div>
                    <MiniBar value={value} tone={tone} />
                  </div>
                ))}
                <div className="mt-3 border-t border-[var(--line)] pt-2">
                  <KeyValue label="Days in state" dense>
                    <Num value={state.daysInState} />
                  </KeyValue>
                  <KeyValue label="Expected remaining" dense>
                    <Num value={state.expectedRemainingDays} unit="d" />
                  </KeyValue>
                  <KeyValue label="Transition risk 24h" dense>
                    <Num value={state.transitionRisk24h} digits={3} />
                  </KeyValue>
                </div>
                <p className="mt-2 text-[11px] leading-snug text-[var(--text-3)]">
                  Source: {state.source}
                </p>
              </div>
            ) : (
              <p className="p-3 text-[11.5px] text-[var(--text-3)]">
                No regime state for this port in the current run.
              </p>
            )}
          </Panel>

          <Panel title="Uncertainty across the horizon">
            <div className="p-3">
              <SeriesChart
                height={140}
                yUnit="band width and disagreement"
                series={[
                  {
                    name: "80% band width",
                    tone: "info",
                    area: true,
                    points: rows.map((row) => ({
                      label: row.dateLabel,
                      value: row.intervalWidth,
                    })),
                  },
                  {
                    name: "Model disagreement ×100",
                    tone: "unc",
                    dashed: true,
                    points: rows.map((row) => ({
                      label: row.dateLabel,
                      value: row.modelDisagreement == null ? null : row.modelDisagreement * 100,
                    })),
                  },
                ]}
              />
              <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11.5px] leading-snug text-[var(--text-3)]">
                Where the two rise together the members disagree and the interval widens
                to admit it. Where the band widens alone, the model is uncertain but the
                members still agree.
              </p>
            </div>
          </Panel>

          <Panel title="Ensemble weights on day 1">
            <div className="px-3 py-2">
              <KeyValue label="Deep model (TFT) weight" dense>
                <Num value={first?.tftWeight} digits={2} />
              </KeyValue>
              <KeyValue label="GBM weight" dense>
                <Num value={first?.gbmWeight} digits={2} />
              </KeyValue>
              <KeyValue label="Source" dense>
                <span className="num text-[11px]">{first?.source ?? "n/a"}</span>
              </KeyValue>
            </div>
          </Panel>
        </div>
      </PageBody>
    </Page>
  );
}
