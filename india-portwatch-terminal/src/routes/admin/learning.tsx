/**
 * The learning dashboard.
 *
 * This is the screen that decides whether anyone should believe the rest of the
 * product, so it is built around the awkward numbers rather than the flattering
 * ones. In order down the page:
 *
 *   1. What the ledger holds, and how much of it has actually resolved.
 *   2. Calibration — including the case where there is not enough evidence to
 *      state one, which is rendered as a sentence and not as a chart of zeros.
 *   3. Why PortWatch was wrong: the largest misses, each decomposed across the
 *      contributors that produced them. Attribution appears only where it was
 *      computed; where a prediction carried no per-contributor signals the panel
 *      says so instead of drawing a plausible bar chart.
 *   4. What changed as a result — reliability weights, with the before and after.
 *   5. Policies and their promotion state, including the rejected ones and why.
 *
 * A dashboard that only showed successes would be marketing.
 */

import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Button, Page, PageBody, PageHeader, Panel, Section } from "@/components/kit/layout";
import { Num, Pill } from "@/components/kit/primitives";
import { DataTable, type Column } from "@/components/kit/table";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { cn } from "@/lib/utils";
import { runOutcomePass } from "@/services/portwatch-os";
import {
  useLearningSummary,
  useMisses,
  usePolicies,
  useReliability,
} from "@/services/os-hooks";
import type {
  CalibrationBinView,
  MissReport,
  PolicyRecordView,
  ReliabilityWeight,
} from "@/types/portwatch-os";

export const Route = createFileRoute("/admin/learning")({ component: LearningDashboard });

function LearningDashboard() {
  const summary = useLearningSummary();
  const reliability = useReliability();
  const misses = useMisses(8);
  const policies = usePolicies();
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState<string | null>(null);

  const pass = useMutation({
    mutationFn: runOutcomePass,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["learning"] });
    },
  });

  if (summary.isLoading || summary.isError) {
    return (
      <ScreenFallback
        title="Learning"
        context={<span>What PortWatch said, what happened, and what changed</span>}
        isLoading={summary.isLoading}
        error={summary.error}
        retry={() => void summary.refetch()}
        label="Reading the outcome ledger"
      />
    );
  }

  const counts = summary.data?.counts ?? {};
  const predictions = counts.predictions ?? {};
  const resolved = predictions.resolved ?? 0;
  const open = predictions.open ?? 0;
  const events = summary.data?.events;
  const decisions = summary.data?.decisions;
  const overall = summary.data?.overall.continuous ?? null;

  return (
    <Page>
      <PageHeader
        title="Learning"
        context={<span>What PortWatch said, what happened, and what changed</span>}
        meta={
          <>
            <span className="num">{resolved} resolved</span>
            <span className="num">{open} open</span>
            <span className="num">{summary.data?.reliabilityRows ?? 0} weights</span>
          </>
        }
        actions={
          <Button
            variant="default"
            disabled={pass.isPending}
            onClick={() => pass.mutate()}
          >
            {pass.isPending ? "Running…" : "Run outcome pass"}
          </Button>
        }
      />

      <PageBody>
        {resolved === 0 ? (
          <div className="mb-3">
            <EmptyState
              title="The ledger holds no resolved claims yet"
              detail={
                open
                  ? `${open} claims are open. Each is about an instant that has not arrived, or an observation that has not landed. Calibration, reliability and attribution stay unavailable until they resolve — reporting them as perfect would be worse than reporting nothing.`
                  : "No prediction has been recorded. Run the pipeline to write claims into the ledger, then run the outcome pass once observations arrive."
              }
            />
          </div>
        ) : null}

        <div className="grid gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          {/* ------------------------------------------------- left column -- */}
          <div className="space-y-3">
            <Panel title="Forecast accuracy" note={`${resolved} resolved claims`}>
              {overall ? (
                <Section title="Overall">
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-4">
                    {(
                      [
                        ["Mean abs. error", overall.meanAbsoluteError, ""],
                        ["RMSE", overall.rootMeanSquareError, ""],
                        ["Bias", overall.bias, ""],
                        [
                          "Interval coverage",
                          overall.intervalCoverage,
                          overall.nominalCoverage != null
                            ? `nominal ${(overall.nominalCoverage * 100).toFixed(0)}%`
                            : "",
                        ],
                      ] as Array<[string, number | null, string]>
                    ).map(([label, value, hint]) => (
                      <div key={label}>
                        <div className="text-[9px] uppercase tracking-[0.06em] text-[var(--text-3)]">
                          {label}
                        </div>
                        <div className="num text-[17px] leading-none text-[var(--text)]">
                          {value == null ? "n/a" : value.toFixed(3)}
                        </div>
                        {hint ? (
                          <div className="num text-[9px] text-[var(--text-3)]">{hint}</div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                  {overall.coverageError != null ? (
                    <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-3)]">
                      The bands cover{" "}
                      {(overall.intervalCoverage! * 100).toFixed(0)}% of observations
                      against a nominal{" "}
                      {(overall.nominalCoverage! * 100).toFixed(0)}%, a coverage error of{" "}
                      {(overall.coverageError * 100).toFixed(1)} points.{" "}
                      {Math.abs(overall.coverageError) < 0.05
                        ? "The intervals are well calibrated."
                        : overall.coverageError > 0
                          ? "The intervals are wider than they need to be."
                          : "The intervals are too narrow and understate the uncertainty."}
                    </p>
                  ) : null}
                </Section>
              ) : (
                <Section title="Unavailable">
                  <p className="text-[10.5px] leading-relaxed text-[var(--text-3)]">
                    No continuous claim has resolved, so there is no error to report.
                  </p>
                </Section>
              )}
            </Panel>

            <Panel
              title="Why was PortWatch wrong?"
              note={
                misses.data
                  ? `${misses.data.attributionAvailable} of ${misses.data.misses.length} decomposed`
                  : "…"
              }
              testId="learning-misses"
            >
              {!misses.data || misses.data.misses.length === 0 ? (
                <Section title="Nothing to show">
                  <p className="text-[10.5px] leading-relaxed text-[var(--text-3)]">
                    No resolved claim has an error to attribute yet.
                  </p>
                </Section>
              ) : (
                <>
                  {misses.data.misses.map((miss) => (
                    <MissRow
                      key={miss.predictionId}
                      miss={miss}
                      expanded={expanded === miss.predictionId}
                      onToggle={() =>
                        setExpanded(
                          expanded === miss.predictionId ? null : miss.predictionId,
                        )
                      }
                    />
                  ))}
                  <Section title="Method">
                    <p className="text-[10px] leading-relaxed text-[var(--text-3)]">
                      {misses.data.method}
                    </p>
                  </Section>
                </>
              )}
            </Panel>

            <Panel
              title="Reliability"
              note={
                reliability.data
                  ? `${reliability.data.changedCount} weights moved`
                  : "…"
              }
              testId="learning-reliability"
              scroll
              className="max-h-[420px]"
            >
              {!reliability.data || reliability.data.weights.length === 0 ? (
                <Section title="Not yet fitted">
                  <p className="text-[10.5px] leading-relaxed text-[var(--text-3)]">
                    Reliability is fitted from resolved claims only. Nothing has resolved,
                    so every contributor is still at its neutral weight of 1.00.
                  </p>
                </Section>
              ) : (
                <DataTable<ReliabilityWeight>
                  rows={reliability.data.weights}
                  rowKey={(row) => `${row.contributor}|${row.context}`}
                  initialSort="samples"
                  columns={reliabilityColumns}
                />
              )}
            </Panel>
          </div>

          {/* ------------------------------------------------ right column -- */}
          <div className="space-y-3">
            <Panel title="Event calibration" testId="learning-calibration">
              {events?.available && events.overall ? (
                <>
                  <Section title="Scores">
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                      {(
                        [
                          ["Brier", events.overall.brier],
                          ["Log loss", events.overall.logLoss],
                          ["Base rate", events.overall.baseRate],
                          ["Brier skill", events.overall.brierSkill],
                        ] as Array<[string, number | null]>
                      ).map(([label, value]) => (
                        <div key={label}>
                          <div className="text-[9px] uppercase tracking-[0.06em] text-[var(--text-3)]">
                            {label}
                          </div>
                          <div className="num text-[15px] leading-none text-[var(--text)]">
                            {value == null ? "n/a" : value.toFixed(3)}
                          </div>
                        </div>
                      ))}
                    </div>
                    <p className="mt-1.5 text-[9.5px] leading-relaxed text-[var(--text-3)]">
                      Brier skill compares against always predicting the base rate. A
                      value at or below zero means the claims carry no information the
                      climatology did not.
                    </p>
                  </Section>
                  {events.overall.calibration ? (
                    <Section title="Calibration curve">
                      <CalibrationBars bins={events.overall.calibration.bins} />
                      <p className="mt-1.5 text-[9.5px] leading-relaxed text-[var(--text-3)]">
                        Expected calibration error{" "}
                        {events.overall.calibration.expectedCalibrationError?.toFixed(3) ??
                          "n/a"}
                        {events.overall.calibration.overForecast != null
                          ? `; the system ${
                              events.overall.calibration.overForecast > 0
                                ? "over-forecasts"
                                : "under-forecasts"
                            } by ${Math.abs(
                              events.overall.calibration.overForecast * 100,
                            ).toFixed(1)} points on average.`
                          : "."}
                      </p>
                    </Section>
                  ) : null}
                </>
              ) : (
                <Section title="Unavailable">
                  <p className="text-[10.5px] leading-relaxed text-[var(--text-3)]">
                    {events?.note ??
                      "No event claim has reached its horizon yet, so Global Eye's probabilities cannot be scored."}
                  </p>
                </Section>
              )}
            </Panel>

            <Panel title="Decisions" testId="learning-decisions">
              {decisions?.available ? (
                <Section title="Take-up">
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                    {(
                      [
                        ["Recorded", decisions.count ?? 0],
                        ["Resolved", decisions.resolved ?? 0],
                        [
                          "Take-up rate",
                          decisions.takeUpRate == null
                            ? null
                            : Number((decisions.takeUpRate * 100).toFixed(1)),
                        ],
                        ["Mean reward", decisions.meanReward ?? null],
                      ] as Array<[string, number | null]>
                    ).map(([label, value]) => (
                      <div key={label}>
                        <div className="text-[9px] uppercase tracking-[0.06em] text-[var(--text-3)]">
                          {label}
                        </div>
                        <div className="num text-[15px] leading-none text-[var(--text)]">
                          {value == null ? "n/a" : value}
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="mt-1.5 text-[9.5px] leading-relaxed text-[var(--text-3)]">
                    Take-up is how the product finds out whether operators trust it. A
                    recommendation nobody accepts has no operational value however good
                    its simulated reward looks.
                  </p>
                </Section>
              ) : (
                <Section title="Unavailable">
                  <p className="text-[10.5px] leading-relaxed text-[var(--text-3)]">
                    No recommendation has been recorded in the decision ledger yet.
                  </p>
                </Section>
              )}
            </Panel>

            <Panel
              title="Policies"
              note={
                policies.data
                  ? `${policies.data.states.approved} approved`
                  : "…"
              }
              testId="learning-policies"
            >
              {!policies.data || policies.data.policies.length === 0 ? (
                <Section title="No candidate">
                  <p className="text-[10.5px] leading-relaxed text-[var(--text-3)]">
                    No learned policy has been trained and submitted. Operational
                    recommendations use the hand-written optimiser.
                  </p>
                </Section>
              ) : (
                <>
                  {policies.data.policies.map((policy) => (
                    <PolicyCard key={policy.policyId} policy={policy} />
                  ))}
                  <Section title="Promotion">
                    <p className="text-[10px] leading-relaxed text-[var(--text-3)]">
                      {policies.data.note}
                    </p>
                  </Section>
                </>
              )}
            </Panel>
          </div>
        </div>
      </PageBody>
    </Page>
  );
}

/* ---------------------------------------------------------------- misses -- */

function MissRow({
  miss,
  expanded,
  onToggle,
}: {
  miss: MissReport;
  expanded: boolean;
  onToggle: () => void;
}) {
  const attribution = miss.attribution;
  const worst = attribution.shares[0];

  return (
    <div className="border-b border-[var(--line)]/60 last:border-0">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start gap-2 px-2 py-1.5 text-left hover:bg-[var(--panel-2)]"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="num text-[10.5px] text-[var(--text-2)]">{miss.subject}</span>
            <span className="truncate text-[10.5px] text-[var(--text-3)]">
              {miss.target}
            </span>
            <span className="num ml-auto shrink-0 text-[9.5px] text-[var(--text-3)]">
              {miss.validAt.slice(0, 10)}
            </span>
          </div>
          <div className="mt-[3px] flex flex-wrap items-baseline gap-x-3 text-[10.5px]">
            <span className="text-[var(--text-3)]">
              predicted{" "}
              <span className="num text-[var(--text)]">
                {miss.predicted?.toFixed(2) ?? "n/a"}
              </span>
            </span>
            <span className="text-[var(--text-3)]">
              observed{" "}
              <span className="num text-[var(--text)]">
                {miss.observed?.toFixed(2) ?? "n/a"}
              </span>
            </span>
            <span
              className={cn(
                "num",
                (miss.error ?? 0) > 0 ? "text-[var(--warn)]" : "text-[var(--info)]",
              )}
            >
              {miss.error == null ? "" : `${miss.error > 0 ? "+" : ""}${miss.error.toFixed(2)}`}
            </span>
          </div>
          {attribution.available && worst ? (
            <div className="mt-[3px] text-[9.5px] text-[var(--text-3)]">
              Dominated by{" "}
              <span className="text-[var(--text-2)]">{attribution.dominant}</span>, which
              accounted for {((worst.share ?? 0) * 100).toFixed(0)}% of the miss.
            </div>
          ) : (
            <div className="mt-[3px] text-[9.5px] text-[var(--unc)]">
              Attribution unavailable for this prediction.
            </div>
          )}
        </div>
      </button>

      {expanded ? (
        <div className="space-y-2 border-t border-[var(--line)]/60 bg-[var(--panel-2)]/40 px-3 py-2">
          {attribution.available ? (
            <section>
              <h4 className="eyebrow text-[8.5px]">Contribution to the error</h4>
              <div className="mt-1 space-y-1">
                {attribution.shares.map((share) => (
                  <div key={share.contributor}>
                    <div className="flex items-baseline gap-2 text-[10px]">
                      <span className="min-w-0 flex-1 truncate text-[var(--text-2)]">
                        {share.contributor}
                      </span>
                      <span className="num text-[var(--text-3)]">
                        w {share.weight.toFixed(2)}
                      </span>
                      <span
                        className={cn(
                          "num w-[54px] text-right",
                          share.contribution > 0
                            ? "text-[var(--warn)]"
                            : "text-[var(--info)]",
                        )}
                      >
                        {share.contribution > 0 ? "+" : ""}
                        {share.contribution.toFixed(2)}
                      </span>
                    </div>
                    <div className="mt-[2px] h-[4px] overflow-hidden rounded-[1px] bg-[var(--panel-3)]">
                      <div
                        className="h-full"
                        style={{
                          width: `${Math.min(100, (share.share ?? 0) * 100)}%`,
                          background:
                            share.contribution > 0 ? "var(--warn)" : "var(--info)",
                        }}
                      />
                    </div>
                  </div>
                ))}
                {attribution.residual != null && Math.abs(attribution.residual) > 1e-6 ? (
                  <p className="text-[9.5px] leading-snug text-[var(--text-3)]">
                    Residual {attribution.residual.toFixed(3)} — error the contributors do
                    not account for, reported rather than smeared across them.
                  </p>
                ) : null}
              </div>
            </section>
          ) : (
            <p className="text-[10px] leading-relaxed text-[var(--unc)]">
              {attribution.reason}
            </p>
          )}

          {miss.reliabilityChanges.length ? (
            <section>
              <h4 className="eyebrow text-[8.5px]">What changed as a result</h4>
              <ul className="mt-1 space-y-0.5">
                {miss.reliabilityChanges.map((change, index) => (
                  <li
                    key={`${change.contributor}-${index}`}
                    className="flex items-baseline gap-2 text-[9.5px]"
                  >
                    <span className="min-w-0 flex-1 truncate text-[var(--text-2)]">
                      {change.contributor}
                    </span>
                    <span className="num text-[var(--text-3)]">
                      {change.from.toFixed(2)} → {change.to.toFixed(2)}
                    </span>
                    <span
                      className={cn(
                        "num w-[46px] text-right",
                        change.delta < 0 ? "text-[var(--crit)]" : "text-[var(--ok)]",
                      )}
                    >
                      {change.delta > 0 ? "+" : ""}
                      {change.delta.toFixed(3)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section>
            <h4 className="eyebrow text-[8.5px]">Context</h4>
            <div className="mt-1 flex flex-wrap gap-1">
              {Object.entries(miss.context)
                .filter(([, value]) => value != null && value !== "")
                .map(([key, value]) => (
                  <Pill key={key} tone="neutral">
                    {key}: {String(value)}
                  </Pill>
                ))}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}

/* ----------------------------------------------------------- calibration -- */

function CalibrationBars({ bins }: { bins: CalibrationBinView[] }) {
  const populated = bins.filter((bin) => bin.count > 0);
  if (!populated.length) {
    return (
      <p className="text-[10px] text-[var(--text-3)]">
        No bin carries an observation yet.
      </p>
    );
  }
  return (
    <div className="space-y-1">
      {populated.map((bin) => (
        <div key={`${bin.lower}`}>
          <div className="flex items-baseline gap-2 text-[9.5px]">
            <span className="num w-[62px] shrink-0 text-[var(--text-3)]">
              {(bin.lower * 100).toFixed(0)}–{(bin.upper * 100).toFixed(0)}%
            </span>
            <span className="num text-[var(--text-2)]">
              said {((bin.meanPredicted ?? 0) * 100).toFixed(0)}%
            </span>
            <span className="num text-[var(--text)]">
              happened {((bin.observedRate ?? 0) * 100).toFixed(0)}%
            </span>
            <span className="num ml-auto text-[var(--text-3)]">n={bin.count}</span>
          </div>
          <div className="relative mt-[2px] h-[5px] rounded-[1px] bg-[var(--panel-3)]">
            <div
              className="absolute inset-y-0 rounded-[1px] bg-[var(--info)]/50"
              style={{ width: `${(bin.meanPredicted ?? 0) * 100}%` }}
            />
            <div
              className="absolute inset-y-0 w-[2px] rounded-[1px] bg-[var(--text)]"
              style={{ left: `${(bin.observedRate ?? 0) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------- policies -- */

const POLICY_TONE: Record<string, "ok" | "info" | "unc" | "crit" | "neutral"> = {
  approved: "ok",
  evaluating: "info",
  candidate: "unc",
  rejected: "crit",
  retired: "neutral",
};

function PolicyCard({ policy }: { policy: PolicyRecordView }) {
  const checks = Object.entries(policy.safetyChecks);
  const failed = checks.filter(([, ok]) => !ok);

  return (
    <Section title={policy.name} right={<Pill tone={POLICY_TONE[policy.state] ?? "neutral"}>{policy.state}</Pill>}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[9.5px] text-[var(--text-3)]">
        <span className="num">v{policy.version}</span>
        <span className="num">{policy.family}</span>
        {policy.environment ? <span className="truncate">{policy.environment}</span> : null}
        {policy.approvedBy ? (
          <span>approved by {policy.approvedBy}</span>
        ) : null}
      </div>

      {checks.length ? (
        <ul className="mt-1.5 space-y-0.5">
          {checks.map(([name, ok]) => (
            <li key={name} className="flex items-baseline gap-1.5 text-[9.5px]">
              <span
                className={cn(
                  "num shrink-0",
                  ok ? "text-[var(--ok)]" : "text-[var(--crit)]",
                )}
              >
                {ok ? "PASS" : "FAIL"}
              </span>
              <span className="text-[var(--text-3)]">{name.replace(/_/g, " ")}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {policy.rejectionReason ? (
        <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--crit)]">
          {policy.rejectionReason}
        </p>
      ) : null}

      {failed.length && !policy.rejectionReason ? (
        <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--unc)]">
          {failed.length} promotion check(s) have not passed, so this policy is not
          eligible for approval.
        </p>
      ) : null}
    </Section>
  );
}

/* ---------------------------------------------------------------- columns -- */

const reliabilityColumns: Array<Column<ReliabilityWeight>> = [
  {
    key: "contributor",
    header: "Contributor",
    sort: (row) => row.contributor,
    render: (row) => (
      <span className="truncate text-[11px] text-[var(--text)]">{row.contributor}</span>
    ),
  },
  {
    key: "context",
    header: "Context",
    sort: (row) => row.context,
    render: (row) => (
      <span className="num truncate text-[10px] text-[var(--text-3)]">{row.context}</span>
    ),
  },
  {
    key: "samples",
    header: "n",
    align: "right",
    width: 46,
    sort: (row) => row.samples,
    render: (row) => <span className="num">{row.samples}</span>,
  },
  {
    key: "mae",
    header: "MAE",
    align: "right",
    width: 62,
    sort: (row) => row.meanAbsoluteError ?? 0,
    render: (row) => (
      <span className="num">{row.meanAbsoluteError?.toFixed(3) ?? "n/a"}</span>
    ),
  },
  {
    key: "bias",
    header: "Bias",
    align: "right",
    width: 62,
    hint: "Signed mean error. A consistent bias is the correctable kind.",
    sort: (row) => row.bias ?? 0,
    render: (row) => (
      <span
        className={cn(
          "num",
          (row.bias ?? 0) > 0.5
            ? "text-[var(--warn)]"
            : (row.bias ?? 0) < -0.5
              ? "text-[var(--info)]"
              : "",
        )}
      >
        {row.bias?.toFixed(3) ?? "n/a"}
      </span>
    ),
  },
  {
    key: "weight",
    header: "Weight",
    align: "right",
    width: 78,
    sort: (row) => row.weight,
    render: (row) => (
      <span className="num text-[var(--text)]">
        {row.previousWeight != null ? (
          <span className="mr-1 text-[9.5px] text-[var(--text-3)]">
            {row.previousWeight.toFixed(2)} →
          </span>
        ) : null}
        {row.weight.toFixed(2)}
      </span>
    ),
  },
];
