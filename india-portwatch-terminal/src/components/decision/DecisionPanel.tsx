/**
 * ACTION REQUIRED: the decision panel.
 *
 * The primary interaction of the product is no longer "what is the risk?"
 * but "what should I do?", and this panel is where the engine's answer
 * lands. It shows the subject, the window before the choice closes, what
 * happens if nothing is done, three to five feasible alternatives with their
 * measured consequences, the ones that were impossible and why, the frontier
 * they trade off on, the money where a defensible basis exists, the Critic's
 * verdict with the evidence it read, and the workflow a human moves the
 * decision through.
 *
 * Nothing here computes. Every figure is a `Measure` the engine produced,
 * and an unavailable one is rendered as unavailable with its reason. Selecting
 * an option drives the world: the map switches to that option's branch, the
 * port ring resizes to that option's yard pressure, the timeline re-reads.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/auth/AuthProvider";
import { Chip, PanelTabs } from "@/components/command/panels";
import { Pill, type Tone } from "@/components/kit/primitives";
import { optionStyles } from "@/lib/maritime/decision-layers";
import { cn } from "@/lib/utils";
import {
  type ScenarioAssumptions,
  useDecisionWorkflow,
} from "@/services/decisions";
import type {
  CriticVerdict,
  DecisionOption,
  DecisionProblem,
  Measure,
} from "@/types/decisions";

import { DecisionTimeline } from "./DecisionTimeline";
import { FinancialEvidence } from "./FinancialEvidence";
import { ParetoChart } from "./ParetoChart";
import { RobustHeadline, RobustView, kindLabel } from "./RobustView";

type Tab =
  "options" | "robust" | "frontier" | "timeline" | "money" | "why" | "workflow";

const VERDICT_TONE: Record<CriticVerdict, Tone> = {
  PASS: "ok",
  PASS_WITH_WARNINGS: "warn",
  REJECT: "crit",
};

const WORKFLOW: Array<{ state: string; label: string }> = [
  { state: "COMPUTED", label: "Computed" },
  { state: "REVIEWED", label: "Reviewed" },
  { state: "APPROVED", label: "Approved" },
  { state: "PROPOSED", label: "Proposed" },
  { state: "ISSUED", label: "Issued" },
  { state: "ACCEPTED", label: "Accepted" },
  { state: "OBSERVED", label: "Observed" },
];

/** The columns shown per domain, in order. */
const COLUMNS: Record<string, Array<{ key: string; label: string }>> = {
  VESSEL_ROUTING: [
    { key: "eta", label: "ETA" },
    { key: "risk", label: "Risk" },
    { key: "weather", label: "Weather" },
    { key: "fuel", label: "Fuel" },
    { key: "cost", label: "Cost" },
  ],
  PORT_BERTHING: [
    { key: "port_wait", label: "Wait" },
    { key: "turnaround", label: "Turnaround" },
    { key: "missed_departures", label: "Missed" },
    { key: "crane_utilisation", label: "Cranes" },
    { key: "cost", label: "Cost" },
  ],
  CARGO_CONNECTION: [
    { key: "sailing", label: "Sails" },
    { key: "slack", label: "Slack" },
    { key: "dwell", label: "Dwell" },
    { key: "handling", label: "Handling" },
    { key: "cost", label: "Cost" },
  ],
};

export function formatMeasure(measure: Measure | undefined): string {
  if (!measure) return "—";
  if (!measure.available || measure.value == null) return "unavailable";
  const v = measure.value;
  switch (measure.unit) {
    case "hours":
      return `${v >= 0 ? "+" : ""}${v.toFixed(v < 10 ? 1 : 0)} h`;
    case "risk":
      return v <= 0.001
        ? "none"
        : v < 0.34
          ? `low ${v.toFixed(2)}`
          : v < 0.67
            ? `moderate ${v.toFixed(2)}`
            : `high ${v.toFixed(2)}`;
    case "index":
      return `×${v.toFixed(2)}`;
    case "m":
      return `${v.toFixed(1)} m`;
    case "ratio":
      return `${(v * 100).toFixed(0)}%`;
    case "money":
      return `${(measure.attrs?.currency as string) ?? ""} ${Math.round(v).toLocaleString("en-IN")}`;
    case "count":
      return v.toFixed(0);
    case "nm":
      return `${Math.round(v).toLocaleString()} nm`;
    case "teu":
      return `${v.toFixed(0)} TEU`;
    default:
      return `${v.toFixed(2)} ${measure.unit}`;
  }
}

/** A live countdown to the instant the decision closes. */
export function useCountdown(deadline: string | null): string | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!deadline) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [deadline]);
  if (!deadline) return null;
  const remaining = Math.max(0, (Date.parse(deadline) - now) / 1000);
  const h = Math.floor(remaining / 3600);
  const m = Math.floor((remaining % 3600) / 60);
  const s = Math.floor(remaining % 60);
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

export function DecisionPanel({
  problem,
  selectedOptionId,
  compare,
  onSelectOption,
  onToggleCompare,
  onClose,
  canHandoff = false,
  onRecompute,
  recomputing = false,
  compact = false,
}: {
  problem: DecisionProblem;
  selectedOptionId: string | null;
  compare: boolean;
  onSelectOption: (optionId: string) => void;
  onToggleCompare: (compare: boolean) => void;
  onClose?: () => void;
  /** Whether the signed-in actor may hand an approved option into the advisory boundary. */
  canHandoff?: boolean;
  /** Re-run the decision priced with scenario assumptions; absent, the Money tab offers no form. */
  onRecompute?: (assumptions: ScenarioAssumptions) => void;
  recomputing?: boolean;
  /** Fewer tabs, for a replay or a twin sidebar. */
  compact?: boolean;
}) {
  const { identityHeaders } = useAuth();
  const workflow = useDecisionWorkflow(identityHeaders);
  const [tab, setTab] = useState<Tab>("options");
  // The first two objectives every feasible option is measured on, in the
  // engine's frontier order: a chart over an axis half the options lack
  // would open on an apology.
  const [axes, setAxes] = useState<[string, string]>(() => {
    const preferred =
      (problem.evidence?.frontierObjectives as string[] | undefined) ?? [];
    const feasibleOptions = problem.options.filter(
      (o) => o.status === "FEASIBLE" && o.evaluation,
    );
    const measured = (key: string) =>
      feasibleOptions.length > 0 &&
      feasibleOptions.every((o) => o.evaluation?.objectives[key]?.available);
    const candidates = [
      ...preferred,
      ...problem.objectives
        .map((o) => o.key)
        .filter((k) => !preferred.includes(k)),
    ].filter(measured);
    if (candidates.length >= 2) return [candidates[0], candidates[1]];
    return preferred.length >= 2
      ? [preferred[0], preferred[1]]
      : ["eta", "risk"];
  });
  const styles = useMemo(() => optionStyles(problem), [problem]);
  const countdown = useCountdown(problem.decisionDeadline);
  const baseline = problem.options.find((o) => o.isBaseline) ?? null;
  const selected =
    problem.options.find((o) => o.optionId === selectedOptionId) ?? null;
  const feasible = problem.options.filter((o) => o.status === "FEASIBLE");
  const rejected = problem.options.filter((o) => o.status !== "FEASIBLE");
  const notOffered = problem.availableActions.filter(
    (a) => a.availability.status !== "AVAILABLE",
  );
  const recommendation = problem.recommendation;
  const columns = COLUMNS[problem.domain] ?? COLUMNS.VESSEL_ROUTING;
  const isReplay = Boolean(problem.evidence?.replay);
  const [rootRef, width] = usePanelWidth();
  const stacked = width < STACK_BELOW;

  return (
    <div
      ref={rootRef}
      data-testid="decision-panel"
      data-decision={problem.decisionId}
      data-layout={stacked ? "stacked" : "table"}
      className="flex min-h-0 flex-1 flex-col"
    >
      {/* ------------------------------------------------------- header -- */}
      <div className="border-b border-[var(--line)] px-2 py-1.5">
        <div className="flex items-center gap-1.5">
          <Pill
            tone={
              problem.decisionWindowHours != null &&
              problem.decisionWindowHours < 3
                ? "crit"
                : "warn"
            }
            solid
          >
            Action required
          </Pill>
          <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-[var(--text)]">
            {problem.subject.label}
          </span>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close decision"
              className="text-[10px] text-[var(--text-3)] hover:text-[var(--text)]"
            >
              ✕
            </button>
          ) : null}
        </div>
        <p className="mt-0.5 truncate text-[10px] text-[var(--text-2)]">
          {problem.headline.split(" · ").slice(1).join(" · ") ||
            problem.headline}
        </p>
        <div className="mt-1 flex items-center gap-3 text-[10.5px] text-[var(--text-3)]">
          <span>
            Decision window{" "}
            <span
              className="num text-[var(--text)]"
              data-testid="decision-countdown"
            >
              {/* A replay's deadline is historical: the window is stated from its clock, not counted down from ours. */}
              {isReplay
                ? problem.decisionWindowHours != null
                  ? `${problem.decisionWindowHours.toFixed(1)} h from the replay clock`
                  : "open"
                : (countdown ??
                  (problem.decisionWindowHours != null
                    ? `${problem.decisionWindowHours.toFixed(1)} h`
                    : "open"))}
            </span>
          </span>
          {isReplay ? <Pill tone="info">Replay</Pill> : null}
          <span className="num ml-auto">
            {problem.counts.feasible} feasible · {problem.counts.rejected}{" "}
            rejected
          </span>
        </div>
        <p
          className="mt-1 text-[10px] leading-snug text-[var(--text-2)]"
          data-testid="do-nothing"
        >
          {problem.doNothingStatement}
        </p>
      </div>

      <RobustHeadline problem={problem} />

      <PanelTabs
        value={tab}
        onChange={setTab}
        tabs={
          compact
            ? [
                { value: "options", label: "Options", count: feasible.length },
                { value: "robust", label: "Robust" },
                { value: "frontier", label: "Frontier" },
                { value: "why", label: "Why" },
              ]
            : [
                { value: "options", label: "Options", count: feasible.length },
                { value: "robust", label: "Robust" },
                { value: "frontier", label: "Frontier" },
                { value: "timeline", label: "Timeline" },
                { value: "money", label: "Money" },
                { value: "why", label: "Why" },
                { value: "workflow", label: "Decide" },
              ]
        }
      />

      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === "options" ? (
          <div className="flex flex-col">
            <div className="flex items-center gap-1 border-b border-[var(--line)] px-2 py-1">
              <Chip
                active={compare}
                onClick={() => onToggleCompare(!compare)}
                title="Draw every feasible option on the water at once"
              >
                Compare
              </Chip>
              {recommendation ? (
                <span className="ml-auto truncate text-[10.5px] text-[var(--text-3)]">
                  {recommendation.kind && recommendation.kind !== "ACT"
                    ? kindLabel(recommendation.kind)
                    : "Recommended"}
                  :{" "}
                  <span className="text-[var(--text-2)]">
                    {
                      problem.options.find(
                        (o) => o.optionId === recommendation.optionId,
                      )?.label
                    }
                  </span>
                </span>
              ) : (
                <span className="ml-auto text-[10.5px] italic text-[var(--text-3)]">
                  no feasible option survived
                </span>
              )}
            </div>
            {stacked ? null : (
              <div className="grid grid-cols-[18px_minmax(0,1fr)_repeat(5,44px)] items-center gap-x-1 border-b border-[var(--line)] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[var(--text-3)]">
                <span />
                <span>Option</span>
                {columns.map((c) => (
                  <span key={c.key} className="truncate text-right">
                    {c.label}
                  </span>
                ))}
              </div>
            )}
            {[
              ...(baseline ? [baseline] : []),
              ...feasible.filter((o) => !o.isBaseline),
            ].map((option) => (
              <OptionRow
                key={option.optionId}
                option={option}
                letter={styles.get(option.optionId)!.letter}
                colour={styles.get(option.optionId)!.colour}
                columns={columns}
                selected={option.optionId === selectedOptionId}
                recommended={recommendation?.optionId === option.optionId}
                dominatedBy={
                  problem.frontier?.dominated[option.optionId] ?? null
                }
                stacked={stacked}
                onSelect={() => onSelectOption(option.optionId)}
              />
            ))}
            {rejected.length ? (
              <div className="border-t border-[var(--line)]">
                <p className="px-2 pt-1.5 text-[10px] uppercase tracking-wide text-[var(--text-3)]">
                  Rejected · impossible, not merely worse
                </p>
                {rejected.map((option) => (
                  <div
                    key={option.optionId}
                    data-testid="rejected-option"
                    className="px-2 py-1"
                  >
                    <div className="flex items-center gap-1.5">
                      <Pill tone="crit">Rejected</Pill>
                      <span className="min-w-0 flex-1 truncate text-[10px] text-[var(--text-2)]">
                        {option.label}
                      </span>
                    </div>
                    {option.rejectedBy.map((c) => (
                      <p
                        key={c.key}
                        className="pl-1 text-[10px] leading-snug text-[var(--text-3)]"
                      >
                        {c.label}: {c.detail}
                      </p>
                    ))}
                    {!option.rejectedBy.length &&
                    option.critic?.blocking?.length ? (
                      <p className="pl-1 text-[10px] leading-snug text-[var(--text-3)]">
                        Critic: {option.critic.blocking[0].detail}
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
            {notOffered.length ? (
              <div className="border-t border-[var(--line)] px-2 py-1.5">
                <p className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
                  Not offered
                </p>
                {notOffered.map((row) => (
                  <p
                    key={row.kind}
                    data-testid="not-offered"
                    className="text-[10px] leading-snug text-[var(--text-3)]"
                  >
                    <span className="text-[var(--text-2)]">{row.label}</span> ·{" "}
                    {row.availability.status.toLowerCase().replace("_", " ")} —{" "}
                    {row.availability.reason}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {tab === "robust" ? (
          <RobustView
            problem={problem}
            selectedOptionId={selectedOptionId}
            onSelect={onSelectOption}
          />
        ) : null}

        {tab === "frontier" ? (
          <div className="px-2 py-1.5">
            <ParetoChart
              problem={problem}
              x={axes[0]}
              y={axes[1]}
              onAxes={(x, y) => setAxes([x, y])}
              selectedOptionId={selectedOptionId}
              onSelect={onSelectOption}
            />
            {problem.frontier?.picks ? (
              <div className="mt-1 flex flex-wrap gap-1">
                {Object.entries(problem.frontier.picks).map(
                  ([label, optionId]) => (
                    <Chip
                      key={label}
                      active={optionId === selectedOptionId}
                      onClick={() => onSelectOption(optionId)}
                      color={styles.get(optionId)?.colour}
                    >
                      {label.replace(/_/g, " ").toLowerCase()} ·{" "}
                      {styles.get(optionId)?.letter}
                    </Chip>
                  ),
                )}
              </div>
            ) : null}
            {recommendation?.rankingBasis?.weights ? (
              <p className="mt-1.5 text-[10px] leading-snug text-[var(--text-3)]">
                Balanced ranking weights:{" "}
                {Object.entries(recommendation.rankingBasis.weights)
                  .map(([k, w]) => `${k} ${(w * 100).toFixed(0)}%`)
                  .join(" · ")}
                {recommendation.rankingBasis.objectivesDropped &&
                Object.keys(recommendation.rankingBasis.objectivesDropped)
                  .length
                  ? ` · dropped: ${Object.keys(recommendation.rankingBasis.objectivesDropped).join(", ")} (not measured for every option)`
                  : ""}
              </p>
            ) : null}
          </div>
        ) : null}

        {tab === "timeline" ? (
          <DecisionTimeline
            problem={problem}
            selectedOptionId={selectedOptionId}
            compare={compare}
            onSelect={onSelectOption}
          />
        ) : null}

        {tab === "money" ? (
          selected ? (
            <FinancialEvidence
              option={selected}
              baseline={baseline}
              recommendation={recommendation}
              onRecompute={onRecompute}
              recomputing={recomputing}
            />
          ) : (
            <p className="px-2 py-2 text-[10px] text-[var(--text-3)]">
              Select an option to see its cost basis.
            </p>
          )
        ) : null}

        {tab === "why" ? (
          <CriticView problem={problem} option={selected ?? baseline} />
        ) : null}

        {tab === "workflow" ? (
          <WorkflowView
            problem={problem}
            selected={selected}
            canHandoff={canHandoff}
            onReview={() =>
              workflow.transition.mutate({
                decisionId: problem.decisionId,
                target: "REVIEWED",
                note: "reviewed in the terminal",
              })
            }
            onApprove={() =>
              selected &&
              workflow.transition.mutate({
                decisionId: problem.decisionId,
                target: "APPROVED",
                optionId: selected.optionId,
                note: "chosen in the terminal",
              })
            }
            onDecline={() =>
              workflow.transition.mutate({
                decisionId: problem.decisionId,
                target: "DECLINED",
                note: "declined in the terminal",
              })
            }
            onHandoff={() =>
              workflow.handoff.mutate({ decisionId: problem.decisionId })
            }
            onOutcome={(actualAction, observed) =>
              workflow.outcome.mutate({
                decisionId: problem.decisionId,
                actualAction,
                observed,
              })
            }
            busy={
              workflow.transition.isPending ||
              workflow.handoff.isPending ||
              workflow.outcome.isPending
            }
            error={
              (workflow.transition.error as Error | null)?.message ??
              (workflow.handoff.error as Error | null)?.message ??
              (workflow.outcome.error as Error | null)?.message ??
              null
            }
            handoffResult={workflow.handoff.data ?? null}
          />
        ) : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ rows -- */

/** How wide the panel is; the option table stacks below STACK_BELOW px. */
const STACK_BELOW = 372;

function usePanelWidth(): [(node: HTMLDivElement | null) => void, number] {
  const [width, setWidth] = useState(STACK_BELOW);
  const observer = useRef<ResizeObserver | null>(null);
  const ref = useCallback((node: HTMLDivElement | null) => {
    observer.current?.disconnect();
    if (!node) return;
    const measure = () => {
      const next = node.clientWidth;
      if (next > 0) setWidth(next);
    };
    measure();
    if (typeof ResizeObserver !== "undefined") {
      observer.current = new ResizeObserver(measure);
      observer.current.observe(node);
    }
  }, []);
  useEffect(() => () => observer.current?.disconnect(), []);
  return [ref, width];
}

function OptionRow({
  option,
  letter,
  colour,
  columns,
  selected,
  recommended,
  dominatedBy,
  stacked,
  onSelect,
}: {
  option: DecisionOption;
  letter: string;
  colour: string;
  columns: Array<{ key: string; label: string }>;
  selected: boolean;
  recommended: boolean;
  dominatedBy: string | null;
  stacked: boolean;
  onSelect: () => void;
}) {
  const objectives = option.evaluation?.objectives ?? {};
  const confidence = option.evaluation?.weakestConfidence;
  const flags = (
    <span className="flex min-w-0 flex-wrap items-center gap-x-1 gap-y-0.5 overflow-hidden text-[10px] text-[var(--text-3)]">
      {recommended ? <Pill tone="ok">Recommended</Pill> : null}
      {dominatedBy ? (
        <span title={`dominated by ${dominatedBy}`}>dominated</span>
      ) : null}
      {option.critic?.verdict === "PASS_WITH_WARNINGS" ? (
        <span title={option.critic.warnings.map((w) => w.detail).join("\n")}>
          {option.critic.warnings.length} warn
        </span>
      ) : null}
      {confidence != null ? (
        <span className="num">conf {confidence.toFixed(2)}</span>
      ) : null}
    </span>
  );
  const cells = columns.map((c) => {
    const measure = objectives[c.key];
    const text = formatMeasure(measure);
    const title = measure
      ? measure.available
        ? `${measure.basis} · confidence ${measure.confidence ?? "—"}`
        : (measure.unknownBecause ?? "")
      : "";
    const unavailable = text === "unavailable";
    return {
      key: c.key,
      label: c.label,
      text: unavailable ? "n/a" : text,
      unavailable,
      title,
    };
  });

  if (stacked) {
    // A narrow panel: the label gets the whole line, the measures a second
    // one as labelled chips, so nothing is cut to seven characters.
    return (
      <button
        type="button"
        data-testid="decision-option"
        data-option={option.optionId}
        data-selected={selected}
        onClick={onSelect}
        className={cn(
          "flex w-full flex-col gap-0.5 border-b border-[var(--line)] px-2 py-1.5 text-left transition-colors hover:bg-[var(--surface-2)]",
          selected && "bg-[var(--surface-2)]",
        )}
        style={selected ? { boxShadow: `inset 3px 0 0 ${colour}` } : undefined}
      >
        <span className="flex items-center gap-1.5">
          <span
            className="num w-[14px] shrink-0 text-[10px] font-semibold"
            style={{ color: colour }}
          >
            {option.isBaseline ? "·" : letter}
          </span>
          <span className="min-w-0 flex-1 truncate text-[10.5px] text-[var(--text)]">
            {option.isBaseline ? "Continue current plan" : option.label}
          </span>
        </span>
        <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 pl-[20px]">
          {cells.map((cell) => (
            <span
              key={cell.key}
              className="num flex items-baseline gap-0.5 text-[10.5px]"
              title={cell.title}
            >
              <span className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
                {cell.label}
              </span>
              <span
                className={
                  cell.unavailable
                    ? "italic text-[var(--text-3)]"
                    : "text-[var(--text-2)]"
                }
              >
                {cell.text}
              </span>
            </span>
          ))}
        </span>
        <span className="pl-[20px]">{flags}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      data-testid="decision-option"
      data-option={option.optionId}
      data-selected={selected}
      onClick={onSelect}
      className={cn(
        "grid w-full grid-cols-[18px_minmax(0,1fr)_repeat(5,44px)] items-center gap-x-1 border-b border-[var(--line)] px-2 py-1.5 text-left transition-colors hover:bg-[var(--surface-2)]",
        selected && "bg-[var(--surface-2)]",
      )}
      style={selected ? { boxShadow: `inset 3px 0 0 ${colour}` } : undefined}
    >
      <span className="num text-[10px] font-semibold" style={{ color: colour }}>
        {option.isBaseline ? "·" : letter}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[10.5px] text-[var(--text)]">
          {option.isBaseline ? "Continue current plan" : option.label}
        </span>
        {flags}
      </span>
      {cells.map((cell) => (
        <span
          key={cell.key}
          className={cn(
            "num truncate text-right text-[10px]",
            cell.unavailable
              ? "italic text-[var(--text-3)]"
              : "text-[var(--text-2)]",
          )}
          title={cell.title}
        >
          {cell.text}
        </span>
      ))}
    </button>
  );
}

/* ---------------------------------------------------------------- critic -- */

function CriticView({
  problem,
  option,
}: {
  problem: DecisionProblem;
  option: DecisionOption | null;
}) {
  const recommendation = problem.recommendation;
  return (
    <div className="flex flex-col gap-2 px-2 py-1.5" data-testid="critic-view">
      {recommendation ? (
        <div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
              Recommendation
            </span>
            {recommendation.critic ? (
              <Pill tone={VERDICT_TONE[recommendation.critic.verdict]}>
                {recommendation.critic.verdict.replace(/_/g, " ")}
              </Pill>
            ) : null}
          </div>
          <p className="mt-0.5 text-[10px] leading-snug text-[var(--text)]">
            {recommendation.statement}
          </p>
          {recommendation.critic?.reasons.length ? (
            <ul className="mt-0.5">
              {recommendation.critic.reasons.map((r) => (
                <li
                  key={r}
                  className="text-[10px] leading-snug text-[var(--text-3)]"
                >
                  · {r}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {option?.critic ? (
        <div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
              Critic · {option.isBaseline ? "current plan" : option.label}
            </span>
            <Pill tone={VERDICT_TONE[option.critic.verdict]}>
              {option.critic.verdict.replace(/_/g, " ")}
            </Pill>
          </div>
          <ul className="mt-1 flex flex-col gap-[3px]">
            {option.critic.checks.map((check) => (
              <li
                key={check.name}
                data-testid="critic-check"
                data-passed={check.passed}
                className="flex flex-col"
              >
                <span className="flex items-center gap-1.5 text-[10.5px]">
                  <span
                    className={cn(
                      "num w-1.5",
                      check.passed
                        ? "text-[var(--ok)]"
                        : check.severity === "blocking"
                          ? "text-[var(--crit)]"
                          : "text-[var(--warn)]",
                    )}
                  >
                    {check.passed
                      ? "✓"
                      : check.severity === "blocking"
                        ? "✕"
                        : "!"}
                  </span>
                  <span className="text-[var(--text)]">
                    {check.name.replace(/_/g, " ")}
                  </span>
                </span>
                <span className="pl-3 text-[10px] leading-snug text-[var(--text-3)]">
                  {check.detail}
                  <span className="text-[var(--text-3)]/80">
                    {" "}
                    — {check.basis}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {option?.evaluation?.notes.length ? (
        <p className="text-[10px] leading-snug text-[var(--text-3)]">
          {option.evaluation.notes.join(" · ")}
        </p>
      ) : null}
      {problem.notes.length ? (
        <p className="text-[10px] leading-snug text-[var(--text-3)]">
          {problem.notes.join(" · ")}
        </p>
      ) : null}
      <p className="text-[10px] leading-snug text-[var(--text-3)]">
        World {problem.worldStateId} ·{" "}
        {String(problem.worldRevision?.mode ?? "")} · queried {problem.at}
      </p>
    </div>
  );
}

/* -------------------------------------------------------------- workflow -- */

function WorkflowView({
  problem,
  selected,
  canHandoff,
  onReview,
  onApprove,
  onDecline,
  onHandoff,
  onOutcome,
  busy,
  error,
  handoffResult,
}: {
  problem: DecisionProblem;
  selected: DecisionOption | null;
  canHandoff: boolean;
  onReview: () => void;
  onApprove: () => void;
  onDecline: () => void;
  onHandoff: () => void;
  onOutcome: (actualAction: string, observed: Record<string, number>) => void;
  busy: boolean;
  error: string | null;
  handoffResult: {
    advisories: Array<{ advisoryId: string; state: string; kind: string }>;
  } | null;
}) {
  const [observedEta, setObservedEta] = useState("");
  const [incident, setIncident] = useState(false);
  const current = WORKFLOW.findIndex((w) => w.state === problem.workflow);
  const chosen =
    problem.options.find((o) => o.optionId === problem.humanChoice) ?? null;
  const execution = problem.evidence?.execution as
    { by?: string; mechanism?: string } | undefined;
  const actorMayHandoff =
    canHandoff &&
    problem.workflow === "APPROVED" &&
    chosen &&
    !chosen.isBaseline;

  return (
    <div
      className="flex flex-col gap-2 px-2 py-1.5"
      data-testid="decision-workflow"
    >
      <ol className="flex items-center gap-0.5">
        {WORKFLOW.map((step, index) => (
          <li key={step.state} className="flex items-center gap-0.5">
            <span
              data-state={step.state}
              data-reached={index <= current}
              className={cn(
                "num rounded px-1 py-[1px] text-[10px] uppercase tracking-wide",
                index === current
                  ? "bg-[var(--accent)] text-[var(--surface)]"
                  : index < current
                    ? "text-[var(--text-2)]"
                    : "text-[var(--text-3)]",
              )}
            >
              {step.label}
            </span>
            {index < WORKFLOW.length - 1 ? (
              <span className="text-[10px] text-[var(--text-3)]">›</span>
            ) : null}
          </li>
        ))}
      </ol>
      <p className="text-[10px] leading-snug text-[var(--text-3)]">
        Decision ≠ execution. A named person reviews and approves;{" "}
        {execution?.mechanism === "ISSUE_ADVISORY"
          ? `the approved option reaches the ${problem.domain === "CARGO_CONNECTION" ? "booking party" : "vessel"} as an advisory to ${execution.by}, never as a command.`
          : "the approved option is carried out by its actor and the outcome is recorded here."}
      </p>

      {problem.workflow === "COMPUTED" ? (
        <button
          type="button"
          disabled={busy}
          onClick={onReview}
          data-testid="decision-review"
          className="rounded border border-[var(--line-strong)] px-2 py-1 text-[10px] text-[var(--text)] hover:bg-[var(--surface-2)] disabled:opacity-50"
        >
          Mark reviewed
        </button>
      ) : null}
      {problem.workflow === "REVIEWED" ? (
        <div className="flex gap-1">
          <button
            type="button"
            disabled={busy || !selected || selected.status !== "FEASIBLE"}
            onClick={onApprove}
            data-testid="decision-approve"
            className="flex-1 rounded bg-[var(--accent)] px-2 py-1 text-[10px] font-medium text-[var(--surface)] disabled:opacity-50"
          >
            Approve{" "}
            {selected
              ? selected.isBaseline
                ? "current plan"
                : selected.label
              : "— select an option"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onDecline}
            data-testid="decision-decline"
            className="rounded border border-[var(--line)] px-2 py-1 text-[10px] text-[var(--text-2)] hover:bg-[var(--surface-2)]"
          >
            Decline
          </button>
        </div>
      ) : null}
      {problem.workflow === "APPROVED" ? (
        <div className="flex flex-col gap-1">
          <p className="text-[10px] text-[var(--text)]">
            Approved:{" "}
            <span className="text-[var(--text-2)]">{chosen?.label}</span>
            {problem.recommendation &&
            chosen &&
            chosen.optionId !== problem.recommendation.optionId ? (
              <span className="text-[var(--text-3)]">
                {" "}
                (differs from the recommendation; recorded as such)
              </span>
            ) : null}
          </p>
          {actorMayHandoff ? (
            <button
              type="button"
              disabled={busy}
              onClick={onHandoff}
              data-testid="decision-handoff"
              className="rounded bg-[var(--accent)] px-2 py-1 text-[10px] font-medium text-[var(--surface)] disabled:opacity-50"
            >
              Hand into the advisory boundary (DRAFT)
            </button>
          ) : null}
          {chosen?.isBaseline ? (
            <p className="text-[10px] text-[var(--text-3)]">
              Continuing the current plan needs no advisory.
            </p>
          ) : null}
        </div>
      ) : null}
      {handoffResult?.advisories?.length ? (
        <ul
          data-testid="handoff-advisories"
          className="rounded border border-[var(--line)] px-1.5 py-1"
        >
          {handoffResult.advisories.map((a) => (
            <li
              key={a.advisoryId}
              className="num text-[10.5px] text-[var(--text-2)]"
            >
              {a.advisoryId} · {a.kind} · <Pill tone="neutral">{a.state}</Pill>
            </li>
          ))}
        </ul>
      ) : null}
      {["APPROVED", "ACCEPTED", "DECLINED"].includes(problem.workflow) ? (
        <form
          className="flex flex-col gap-1 rounded border border-[var(--line)] px-1.5 py-1"
          onSubmit={(event) => {
            event.preventDefault();
            const eta = Number(observedEta);
            const observed: Record<string, number> = {
              incident: incident ? 1 : 0,
            };
            if (Number.isFinite(eta) && observedEta.trim() !== "")
              observed.eta = eta;
            onOutcome(chosen?.action ?? "", observed);
          }}
        >
          <p className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
            Record the observed outcome
          </p>
          <label className="flex items-center gap-1 text-[10.5px] text-[var(--text-2)]">
            Observed arrival shift (h)
            <input
              value={observedEta}
              onChange={(e) => setObservedEta(e.target.value)}
              className="num w-16 rounded border border-[var(--line)] bg-transparent px-1 text-[10px] text-[var(--text)]"
              data-testid="outcome-eta"
            />
          </label>
          <label className="flex items-center gap-1 text-[10.5px] text-[var(--text-2)]">
            <input
              type="checkbox"
              checked={incident}
              onChange={(e) => setIncident(e.target.checked)}
            />{" "}
            incident at the strait
          </label>
          <button
            type="submit"
            disabled={busy}
            data-testid="outcome-submit"
            className="rounded border border-[var(--line-strong)] px-2 py-1 text-[10px] text-[var(--text)] hover:bg-[var(--surface-2)] disabled:opacity-50"
          >
            Record outcome
          </button>
        </form>
      ) : null}
      {problem.workflow === "OBSERVED" ? (
        <p className="text-[10px] text-[var(--ok)]">
          Outcome recorded; the learning pass scores this decision from the
          ledger.
        </p>
      ) : null}
      {error ? (
        <p className="text-[10.5px] text-[var(--crit)]">{error}</p>
      ) : null}
      <ol className="flex flex-col gap-[2px]">
        {problem.workflowHistory.map((step, index) => (
          <li
            key={`${step.state}-${index}`}
            className="num text-[10px] text-[var(--text-3)]"
          >
            {step.at.slice(0, 16).replace("T", " ")} · {step.state} ·{" "}
            {step.actor}
            {step.optionId ? ` · ${step.optionId}` : ""}
            {step.note ? ` · ${step.note}` : ""}
          </li>
        ))}
      </ol>
    </div>
  );
}
