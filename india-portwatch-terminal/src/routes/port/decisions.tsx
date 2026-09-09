import { Link, createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { PortSwitcher, usePortContext } from "@/components/app/port-context";
import { BarRanking } from "@/components/kit/charts";
import { Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import {
  KeyValue,
  MiniBar,
  Num,
  Pill,
  formatUtc,
  severityTone,
  type Tone,
} from "@/components/kit/primitives";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { useDecision, useFleet, useForecast, useNews } from "@/services/hooks";
import { cn } from "@/lib/utils";
import type { Decision, FleetRow } from "@/types/portwatch";

export const Route = createFileRoute("/port/decisions")({ component: PortDecisions });

/** One row of the action queue, whatever produced it. */
interface QueueItem {
  id: string;
  rank: number;
  severity: string;
  tone: Tone;
  title: string;
  action: string;
  horizon: string;
  priority: number | null;
  confidence: number | null;
  detail: string;
  origin: "decision" | "schedule" | "alert";
  congestionProbability?: number | null;
}

/**
 * Readable form of an action code, without inventing wording.
 *
 * The decision layer writes a title for the lead action but not for each
 * scheduled follow-up, so those rows carry their own code. Case it for reading
 * and keep the code itself on the row beneath, rather than paraphrasing an
 * instruction the pipeline did not write.
 */
const ACRONYMS = new Set(["ETA", "AIS", "TFT", "HSMM"]);

function humaniseAction(code: string): string {
  const words = code.split("_").filter(Boolean);
  return words
    .map((word, index) => {
      if (ACRONYMS.has(word)) return word;
      const lower = word.toLowerCase();
      return index === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower;
    })
    .join(" ");
}

function buildQueue(
  decision: Decision | undefined,
  alerts: Array<{ id: string; severity: string; text: string; action: string; priority: number | null; confidence: number | null }>,
): QueueItem[] {
  const items: QueueItem[] = [];

  if (decision) {
    items.push({
      id: decision.id,
      rank: 0,
      severity: decision.severity,
      tone: severityTone(decision.severity),
      title: decision.title,
      action: decision.action,
      horizon: `day ${decision.horizonDay}${decision.targetDate ? ` · ${decision.targetDate.slice(0, 10)}` : ""}`,
      priority: decision.priorityScore,
      confidence: decision.confidence,
      detail: decision.rationale,
      origin: "decision",
      congestionProbability: decision.congestionProbability,
    });

    for (const step of decision.schedule ?? []) {
      if (step.horizonDay === decision.horizonDay) continue;
      items.push({
        id: `${decision.id}-d${step.horizonDay}`,
        rank: 0,
        severity: step.priority >= 0.6 ? "high" : step.priority >= 0.35 ? "medium" : "watch",
        tone: step.priority >= 0.6 ? "warn" : step.priority >= 0.35 ? "info" : "neutral",
        title: humaniseAction(step.action),
        action: step.action,
        horizon: `day ${step.horizonDay}${step.targetDate ? ` · ${step.targetDate.slice(0, 10)}` : ""}`,
        priority: step.priority,
        confidence: null,
        detail: `Scheduled follow-up issued by the decision cascade for horizon day ${step.horizonDay}.`,
        origin: "schedule",
        congestionProbability: step.congestionProbability,
      });
    }
  }

  for (const alert of alerts) {
    if (decision && alert.action === decision.action) continue;
    items.push({
      id: alert.id,
      rank: 0,
      severity: alert.severity,
      tone: severityTone(alert.severity),
      title: alert.text,
      action: alert.action,
      horizon: "current run",
      priority: alert.priority,
      confidence: alert.confidence,
      detail: alert.text,
      origin: "alert",
    });
  }

  return items
    .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0))
    .map((item, index) => ({ ...item, rank: index + 1 }));
}

function PortDecisions() {
  const { port, query } = usePortContext();
  const decision = useDecision(port?.code);
  const news = useNews();
  const fleet = useFleet();
  const forecast = useForecast(port?.code);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (query.isLoading || decision.isLoading || query.isError || !port) {
    return (
      <ScreenFallback
        title="Decisions"
        isLoading={query.isLoading || decision.isLoading}
        error={query.error ?? (port ? null : new Error("No port selected."))}
        retry={() => void query.refetch()}
        label="Loading action queue"
      />
    );
  }

  const alerts = (news.data?.alerts ?? []).filter((alert) => alert.portCode === port.code);
  const queue = buildQueue(decision.data, alerts);
  const active = queue.find((item) => item.id === selectedId) ?? queue[0] ?? null;
  const primary = decision.data;

  const affected: FleetRow[] = (fleet.data ?? []).filter(
    (vessel) =>
      vessel.intendedPortCode === port.code || vessel.recommendedPortCode === port.code,
  );

  const horizonRow =
    primary && forecast.data
      ? (forecast.data.find((row) => row.day === primary.horizonDay) ?? null)
      : null;

  return (
    <Page>
      <PageHeader
        title="Decisions"
        context={
          <>
            <span>{port.name}</span>
            <span className="num">{port.code}</span>
            <span>Operational action queue</span>
          </>
        }
        meta={
          <>
            <span className="num">origin {formatUtc(primary?.originDate ?? null)}</span>
            <span className="num">{primary?.source ?? "no decision artefact"}</span>
          </>
        }
        actions={<PortSwitcher />}
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "Queued actions",
            value: queue.length,
            tone: queue.length ? "warn" : "ok",
            note: `${alerts.length} from the alert feed`,
          },
          {
            label: "Lead action",
            value: primary?.action ?? "none",
            tone: severityTone(primary?.severity),
            note: primary ? `target ${primary.target}` : "no decision issued",
          },
          {
            label: "Expected delay saved",
            value: primary?.expectedDelaySavedHours?.toFixed(1) ?? "n/a",
            unit: "h",
            tone: "ok",
            note: "if the action is taken at its target horizon",
          },
          {
            label: "Decision confidence",
            value: primary ? `${(primary.confidence * 100).toFixed(0)}%` : "n/a",
            note: `uncertainty ${primary?.uncertainty?.toFixed(2) ?? "n/a"}`,
          },
          {
            label: "P(congestion)",
            value: primary?.congestionProbability?.toFixed(3) ?? "n/a",
            tone: (primary?.congestionProbability ?? 0) >= 0.5 ? "warn" : "info",
            note: `entry risk ${primary?.portEntryRisk ?? "n/a"}`,
          },
        ]}
      />

      <PageBody padded={false} className="flex min-h-0 overflow-hidden">
        <div className="min-w-0 flex-1 overflow-y-auto border-r border-[var(--line)]">
          {queue.length === 0 ? (
            <EmptyState
              title="No action issued"
              detail={`The decision cascade produced no bounded action for ${port.name} against the current forecast. Standard monitoring applies.`}
            />
          ) : (
            <ul>
              {queue.map((item) => {
                const selected = active?.id === item.id;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(item.id)}
                      className={cn(
                        "flex w-full items-start gap-3 border-b border-[var(--line)] px-4 py-3 text-left transition-colors",
                        selected ? "bg-[var(--panel-2)]" : "hover:bg-[var(--panel)]",
                      )}
                    >
                      <span
                        className="mt-[3px] block h-[30px] w-[3px] shrink-0"
                        style={{
                          background: selected
                            ? "var(--info)"
                            : `color-mix(in srgb, var(--${item.tone === "neutral" ? "text-3" : item.tone}) 55%, transparent)`,
                        }}
                      />
                      <span className="num mt-[2px] w-6 shrink-0 text-[11px] text-[var(--text-3)]">
                        {String(item.rank).padStart(2, "0")}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-2">
                          <Pill tone={item.tone}>{item.severity}</Pill>
                          <span className="text-[13px] font-medium text-[var(--text)]">
                            {item.title}
                          </span>
                        </span>
                        <span className="num mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10.5px] text-[var(--text-3)]">
                          <span>{item.action}</span>
                          <span>{item.horizon}</span>
                          <span>priority {item.priority?.toFixed(2) ?? "n/a"}</span>
                          {item.confidence != null ? (
                            <span>confidence {item.confidence.toFixed(2)}</span>
                          ) : null}
                          <span className="uppercase tracking-[0.08em] opacity-70">
                            {item.origin}
                          </span>
                        </span>
                      </span>
                      <span className="w-16 shrink-0 pt-1">
                        <MiniBar value={item.priority} tone={item.tone} />
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <aside className="flex w-[420px] shrink-0 flex-col overflow-y-auto 2xl:w-[480px]">
          {active && primary ? (
            <>
              <Panel
                title="Selected action"
                note={active.origin}
                className="shrink-0 rounded-none border-x-0 border-t-0"
              >
                <div className="p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <Pill tone={active.tone} solid>
                      {active.severity}
                    </Pill>
                    <span className="num text-[11px] text-[var(--text-3)]">{active.horizon}</span>
                  </div>
                  <h2 className="text-[15px] font-medium leading-snug text-[var(--text)]">
                    {active.title}
                  </h2>
                  <p className="mt-2 text-[12px] leading-relaxed text-[var(--text-2)]">
                    {active.detail}
                  </p>
                </div>
              </Panel>

              <Panel title="Expected impact" className="shrink-0 rounded-none border-x-0 border-t-0">
                <div className="px-3 py-2">
                  <KeyValue label="Expected delay saved" dense>
                    <Num value={primary.expectedDelaySavedHours} unit="h" tone="ok" />
                  </KeyValue>
                  <KeyValue label="Congestion probability" dense>
                    <Num value={active.congestionProbability ?? primary.congestionProbability} digits={3} />
                  </KeyValue>
                  <KeyValue label="Decision confidence" dense>
                    <Num value={primary.confidence} digits={2} />
                  </KeyValue>
                  <KeyValue label="Uncertainty" dense>
                    <Num value={primary.uncertainty} digits={2} tone="unc" />
                  </KeyValue>
                  <KeyValue label="Priority score" dense>
                    <Num value={primary.priorityScore} digits={2} />
                  </KeyValue>
                  {horizonRow ? (
                    <KeyValue label="Forecast on target day" dense>
                      <span className="num">
                        {horizonRow.q50.toFixed(1)}
                        <span className="ml-1 text-[10px] text-[var(--text-3)]">
                          {horizonRow.q10.toFixed(0)}–{horizonRow.q90.toFixed(0)}
                        </span>
                      </span>
                    </KeyValue>
                  ) : null}
                  <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11.5px] leading-snug text-[var(--text-2)]">
                    {primary.expectedImpact}
                  </p>
                </div>
              </Panel>

              <Panel title="Why" className="shrink-0 rounded-none border-x-0 border-t-0">
                <div className="p-3">
                  <BarRanking
                    items={primary.topDrivers.map((driver) => ({
                      label: driver.factor.replace(/_/g, " "),
                      value: driver.contribution,
                      tone: "warn" as const,
                    }))}
                  />
                  <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11.5px] leading-snug text-[var(--text-3)]">
                    Ranked driver contributions from the decision cascade, largest first.
                  </p>
                </div>
              </Panel>

              <Panel title="Fallback" className="shrink-0 rounded-none border-x-0 border-t-0">
                <p className="px-3 py-2.5 text-[12px] leading-relaxed text-[var(--text-2)]">
                  {primary.alternativeAction}
                </p>
              </Panel>

              <Panel
                title="Affected vessels"
                note={`${affected.length}`}
                className="min-h-0 flex-1 rounded-none border-x-0 border-b-0"
                scroll
              >
                {affected.length === 0 ? (
                  <p className="px-3 py-3 text-[11.5px] leading-snug text-[var(--text-3)]">
                    No vessel in the routing roster declares {port.short} as an intended or
                    alternative call, so this action has no named vessel to serve. It still
                    applies to aggregate arrivals measured at the port.
                  </p>
                ) : (
                  <ul>
                    {affected.map((vessel) => (
                      <li
                        key={vessel.id}
                        className="border-b border-[var(--line)]/50 px-3 py-2 last:border-0"
                      >
                        <div className="flex items-baseline justify-between gap-2">
                          <Link
                            to="/vessel/$vesselId"
                            params={{ vesselId: vessel.id }}
                            className="text-[12px] font-medium text-[var(--text)] hover:text-[var(--info)]"
                          >
                            {vessel.name}
                          </Link>
                          <Pill tone={vessel.reroute ? "warn" : "ok"}>
                            {vessel.reroute ? "reroute advised" : "keep call"}
                          </Pill>
                        </div>
                        <div className="num mt-0.5 flex gap-3 text-[10.5px] text-[var(--text-3)]">
                          <span>day +{vessel.bestArrivalDay ?? "n/a"}</span>
                          <span>buffer {vessel.bufferHours ?? "n/a"}h</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </>
          ) : (
            <Panel title="Selected action" className="min-h-0 flex-1 rounded-none border-x-0 border-t-0 border-b-0">
              <EmptyState
                title="Nothing queued"
                detail="Select an action from the queue to see its expected impact, drivers and fallback."
              />
            </Panel>
          )}
        </aside>
      </PageBody>
    </Page>
  );
}
