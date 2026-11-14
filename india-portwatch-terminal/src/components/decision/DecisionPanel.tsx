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

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/auth/AuthProvider";
import { Chip, PanelTabs } from "@/components/command/panels";
import { formatUtc, Pill, type Tone } from "@/components/kit/primitives";
import { optionStyles } from "@/lib/maritime/decision-layers";
import { cn } from "@/lib/utils";
import {
  type ScenarioAssumptions,
  useDecisionWorkflow,
} from "@/services/decisions";
import {
  confirmDecisionOption,
  confirmPortIssue,
} from "@/services/decision-confirmation";
import { invalidateHomePackets } from "@/services/home-screen";
import type {
  CriticVerdict,
  DecisionOption,
  DecisionProblem,
  Measure,
} from "@/types/decisions";

import { DecisionTimeline } from "./DecisionTimeline";
import {
  scrollToWorkflowStep,
  WorkflowRail,
} from "@/components/miniature/WorkflowRail";
import { CommercialReview } from "./CommercialReview";
import { RiskTab } from "@/components/cargo-risk/RiskTab";
import { DecisionTradeoff } from "@/components/cargo-risk/DecisionTradeoff";
import { FinancialEvidence } from "./FinancialEvidence";
import { ParetoChart } from "./ParetoChart";
import { RobustHeadline, RobustView, kindLabel } from "./RobustView";
import { FrozenWeatherBasis } from "@/components/intelligence/FrozenWeatherBasis";
import {
  PassageDecisionSummary,
  PassageRecommendation,
} from "@/components/intelligence/PassageDecisionSummary";
import {
  FrozenIntelligenceBasis,
  type IntelligenceBasis,
} from "@/components/intelligence/FrozenIntelligenceBasis";
import type { FrozenEnvironment } from "@/services/current-inputs";

type Tab =
  | "options"
  | "robust"
  | "frontier"
  | "timeline"
  | "money"
  | "why"
  | "workflow"
  | "business"
  | "cargo-risk";

const VERDICT_TONE: Record<CriticVerdict, Tone> = {
  PASS: "ok",
  PASS_WITH_WARNINGS: "warn",
  REJECT: "crit",
};

const WORKFLOW = [
  { key: "COMPUTED", label: "Computed" },
  { key: "REVIEWED", label: "Reviewed" },
  { key: "APPROVED", label: "Approved" },
  { key: "PROPOSED", label: "Proposed" },
  { key: "ISSUED", label: "Issued" },
  { key: "ACCEPTED", label: "Accepted" },
  { key: "OBSERVED", label: "Observed" },
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

function decisionLead(problem: DecisionProblem, closed?: string) {
  const subject = problem.subject.label;
  if (problem.workflow === "OBSERVED")
    return `The outcome for ${subject} is recorded.`;
  if (problem.workflow === "DECLINED")
    return `The proposed change for ${subject} was declined.`;
  if (closed) return `${subject} · ${closed}`;

  const risk = problem.evidence.closureModel as
    { hoursToRisk?: number | null; alreadyEntered?: boolean } | undefined;
  const event = (problem.evidence.event as { label?: string } | undefined)
    ?.label;
  const hours = risk?.hoursToRisk;
  const context =
    event && risk?.alreadyEntered
      ? `${subject} is already in the modelled area affected by ${event}`
      : event && hours != null && Number.isFinite(hours) && hours >= 0
        ? `${subject} reaches the modelled area affected by ${event} in ${Math.ceil(hours)} h`
        : `${subject} has a plan to review`;
  const deadline = problem.decisionDeadline
    ? ` by ${formatUtc(problem.decisionDeadline)}`
    : "";
  const recommendation = problem.recommendation;
  if (recommendation?.kind === "WAIT_FOR_MORE_INFORMATION") {
    return `${context}. Review the missing evidence${deadline} before changing the plan.`;
  }
  const choice = problem.options.find(
    (option) => option.optionId === recommendation?.optionId,
  );
  const current = problem.options.find((option) => option.isBaseline);
  if (!choice || choice.status !== "FEASIBLE") {
    return `${context}. Review the available options${deadline}.`;
  }
  if (choice.isBaseline || recommendation?.kind === "KEEP_CURRENT_PLAN") {
    return `${context}. Review whether to keep the current plan${deadline}.`;
  }
  const eta = choice.evaluation?.objectives.eta;
  const currentEta = current?.evaluation?.objectives.eta;
  const change =
    eta?.available &&
    currentEta?.available &&
    eta.unit === "h" &&
    currentEta.unit === "h" &&
    eta.value != null &&
    currentEta.value != null
      ? Math.round(eta.value - currentEta.value)
      : null;
  const timing = change ? ` (${change > 0 ? "+" : ""}${change} h)` : "";
  return `${context}. Decide${deadline} between ${choice.label}${timing} and the current plan.`;
}

export function DecisionPanel({
  problem,
  selectedOptionId,
  compare,
  onSelectOption,
  onToggleCompare,
  onClose,
  onEditCurrentInputs,
  onNewComparison,
  canHandoff = false,
  issueOnApprove = false,
  issueComplete = false,
  onRecompute,
  recomputing = false,
  compact = false,
  closedWindowStatus,
}: {
  problem: DecisionProblem;
  selectedOptionId: string | null;
  compare: boolean;
  onSelectOption: (optionId: string) => void;
  onToggleCompare: (compare: boolean) => void;
  onClose?: () => void;
  /** Open the existing input editor without a floating control over the inspector. */
  onEditCurrentInputs?: () => void;
  onNewComparison?: (problem: DecisionProblem) => void;
  /** Whether the signed-in actor may hand an approved option into the advisory boundary. */
  canHandoff?: boolean;
  issueOnApprove?: boolean;
  issueComplete?: boolean;
  /** Re-run the decision priced with scenario assumptions; absent, the Money tab offers no form. */
  onRecompute?: (assumptions: ScenarioAssumptions) => void;
  recomputing?: boolean;
  /** Fewer tabs, for a replay or a twin sidebar. */
  compact?: boolean;
  closedWindowStatus?: string;
}) {
  const { identityHeaders, session } = useAuth();
  const workflow = useDecisionWorkflow(identityHeaders);
  const client = useQueryClient();
  const confirm = useMutation({
    mutationFn: async ({
      optionId,
      issue,
    }: {
      optionId: string;
      issue: boolean;
    }) => {
      if (issue) {
        await confirmPortIssue(problem.decisionId, optionId, identityHeaders);
      } else {
        const approved = await confirmDecisionOption(
          problem.decisionId,
          optionId,
          identityHeaders,
        );
        client.setQueryData(["decision", approved.decisionId], approved);
      }
    },
    onSettled: () => {
      invalidateHomePackets();
      return Promise.all(
        [
          ["decision", problem.decisionId],
          ["decisions"],
          ["advisories"],
          ["current-proposals"],
          ["workspace-handoffs"],
        ].map((queryKey) => client.invalidateQueries({ queryKey })),
      );
    },
  });
  const singleApproval =
    issueOnApprove || session?.user.role === "SHIPPING_COMPANY";
  const [tab, setTab] = useState<Tab>(issueOnApprove ? "workflow" : "options");
  const [workflowTarget, setWorkflowTarget] = useState<{
    key: string;
    showControls: boolean;
  } | null>(null);
  const currentStage =
    WORKFLOW.find((step) => step.key === problem.workflow)?.key ??
    problem.workflowHistory
      .filter((entry) => WORKFLOW.some((step) => step.key === entry.state))
      .at(-1)?.state;
  useEffect(() => {
    document
      .querySelector<HTMLElement>(
        `[data-testid="decision-panel"][data-decision="${CSS.escape(problem.decisionId)}"]`,
      )
      ?.focus({ preventScroll: true });
  }, [problem.decisionId]);
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
  const currentWeather = problem.evidence?.currentEnvironment as
    FrozenEnvironment | undefined;
  const passageResult = Boolean(currentWeather?.passageComparison);
  const comparisonScroll = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!passageResult || tab !== "options") return;
    const scroller = comparisonScroll.current;
    const firstMeasure = scroller?.querySelector(
      "table[data-testid='passage-core-comparison'] tbody tr",
    );
    if (!scroller || !firstMeasure) return;
    const clipped =
      firstMeasure.getBoundingClientRect().bottom -
      scroller.getBoundingClientRect().bottom;
    if (clipped > 0) scroller.scrollTop += Math.ceil(clipped) + 4;
  }, [passageResult, problem.decisionId, tab]);
  const intelligence = problem.evidence?.intelligenceBasis as
    IntelligenceBasis | undefined;
  const passageUnavailable = problem.evidence.passagePlanningUnavailable as
    { reason: string; fallback: string; meaning: string } | undefined;
  const columns = currentWeather
    ? [
        { key: "eta", label: "Clear approach shift" },
        { key: "port_wait", label: "Assumed wait" },
        { key: "weather", label: "Wave" },
        ...(currentWeather.passageComparison
          ? [{ key: "fuel", label: "Modeled fuel" }]
          : []),
        { key: "cost", label: "Cost" },
      ]
    : intelligence?.kind === "NOTICE_RESTRICTION"
      ? [
          { key: "eta", label: "Total schedule shift" },
          { key: "port_wait", label: "Planned access wait" },
          { key: "fuel", label: "Fuel" },
          { key: "cost", label: "Cost" },
        ]
      : (COLUMNS[problem.domain] ?? COLUMNS.VESSEL_ROUTING);
  const isReplay = Boolean(problem.evidence?.replay);
  const [rootRef, width] = usePanelWidth();
  const stacked = width < STACK_BELOW;

  return (
    <div
      ref={rootRef}
      data-testid="decision-panel"
      tabIndex={-1}
      role="region"
      aria-label="Decision comparison"
      data-decision={problem.decisionId}
      data-passage={Boolean(currentWeather?.passageComparison)}
      data-layout={stacked ? "stacked" : "table"}
      className="pw-decision-panel flex min-h-0 flex-1 flex-col"
    >
      {/* ------------------------------------------------------- header -- */}
      <div className="pw-decision-header border-b border-[var(--line)] px-2 py-1.5">
        <p
          data-testid="decision-lead"
          className="mb-1 text-xs font-semibold leading-snug [overflow-wrap:anywhere]"
        >
          {decisionLead(problem, closedWindowStatus)}
        </p>
        <div className="flex items-center gap-1.5">
          <Pill
            tone={
              closedWindowStatus
                ? "info"
                : problem.decisionWindowHours != null &&
                    problem.decisionWindowHours < 3
                  ? "crit"
                  : "warn"
            }
            solid
          >
            {closedWindowStatus ?? "Action required"}
          </Pill>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close decision"
              className="ml-auto text-[10px] text-[var(--text-3)] hover:text-[var(--text)]"
            >
              ✕
            </button>
          ) : null}
        </div>
        {currentWeather?.passageComparison ? (
          <p className="mt-0.5 text-[10px] text-[var(--text-2)]">
            Declared passage · conditional port approach
          </p>
        ) : null}
        <div className="mt-1 flex items-center gap-3 text-[10.5px] text-[var(--text-3)]">
          {!closedWindowStatus ? (
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
          ) : null}
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
          {currentWeather?.passageComparison
            ? "Current plan and alternatives use frozen declarations and forecast hours."
            : problem.doNothingStatement}
        </p>
      </div>

      <div className="pw-decision-rail">
        <WorkflowRail
          label="Decision progress"
          steps={WORKFLOW}
          current={currentStage}
          onStep={(key) => {
            setTab("workflow");
            setWorkflowTarget({ key, showControls: key === currentStage });
          }}
        />
      </div>

      {currentWeather?.passageComparison ? (
        <p className="pw-mixed-basis">
          {currentWeather.evidenceKind === "SOFTWARE_LIFECYCLE_FIXTURE"
            ? "Software forecast fixture"
            : "Provider forecast"}{" "}
          + declared voyage · modeled approach, demo review
        </p>
      ) : problem.evidence.currentEnvironment ? (
        <p className="px-2 py-1 text-xs">
          {currentWeather?.passageComparison ? (
            <>
              Proposed arrival plan; Port review is advisory. Navigation remains
              the operator's decision.
            </>
          ) : (
            <>
              Forecast approach comparison: both options reach the same clear
              approach time. Later arrival reduces assumed anchorage waiting.
              The closure-duration stress model does not apply; calibrated
              uncertainty is unavailable.
            </>
          )}
        </p>
      ) : intelligence?.kind === "NOTICE_RESTRICTION" ? (
        <p className="p-2 text-xs">
          Published authority restriction and declared voyage timing. Both
          options use the same published access boundary and conditional
          destination arrival. Revising the request relocates planned waiting;
          actual access and operational benefits remain unavailable.
        </p>
      ) : intelligence?.kind === "PARADIP_ENTRY_RESTRICTION" ? (
        <p className="p-2 text-xs">
          The only eligible option is referral for human review. Entry,
          pilotage, and the schedule effect remain unknown.
        </p>
      ) : intelligence ? (
        <p className="p-2 text-xs">
          Reported evidence and an explicit review-hold assumption. Only the
          assumed schedule shift is quantified; operational benefit is
          unavailable.
        </p>
      ) : (
        <RobustHeadline problem={problem} />
      )}
      {passageUnavailable ? (
        <p
          role="status"
          className="border-b border-[var(--line)] px-2 py-2 text-xs"
        >
          Passage planning unavailable: {passageUnavailable.reason}. Fallback:
          arrival-window comparison only. {passageUnavailable.meaning}
        </p>
      ) : null}

      {onEditCurrentInputs ? (
        <button
          type="button"
          data-current-inputs-trigger
          onClick={onEditCurrentInputs}
          className="mx-2 mb-1 min-h-8 rounded border border-[var(--line-strong)] px-2 py-1 text-left text-xs text-[var(--text)] hover:bg-[var(--surface-2)]"
        >
          Edit inputs / saved comparisons
        </button>
      ) : null}
      <div
        className={
          currentWeather?.passageComparison
            ? "[&_[role=tablist]]:flex-wrap [&_[role=tab]]:flex-auto"
            : undefined
        }
      >
        <PanelTabs
          value={tab}
          onChange={setTab}
          tabs={
            compact
              ? [
                  {
                    value: "options",
                    label: "Options",
                    count: feasible.length,
                  },
                  { value: "robust", label: "Robust" },
                  { value: "frontier", label: "Frontier" },
                  { value: "why", label: "Why" },
                ]
              : [
                  {
                    value: "options",
                    label: "Options",
                    count: feasible.length,
                  },
                  { value: "robust", label: "Robust" },
                  { value: "frontier", label: "Frontier" },
                  { value: "timeline", label: "Timeline" },
                  { value: "money", label: "Money" },
                  ...(onNewComparison &&
                  currentWeather?.passageComparison &&
                  session?.user.role === "SHIPPING_COMPANY"
                    ? [{ value: "business" as const, label: "Business" }]
                    : []),
                  ...(session?.mode === "demo" &&
                  session.user.role === "SHIPPING_COMPANY"
                    ? [{ value: "cargo-risk" as const, label: "Cargo risk" }]
                    : []),
                  { value: "why", label: "Why" },
                  { value: "workflow", label: "Decide" },
                ]
          }
        />
      </div>

      <div
        ref={comparisonScroll}
        key={tab}
        className="min-h-0 flex-1 overflow-y-auto"
      >
        {tab === "cargo-risk" &&
        session?.mode === "demo" &&
        session.user.role === "SHIPPING_COMPANY" ? (
          <RiskTab key={problem.decisionId} problemId={problem.decisionId} />
        ) : null}
        {tab === "business" && onNewComparison ? (
          <CommercialReview
            key={problem.decisionId}
            problem={problem}
            onSuccessor={onNewComparison}
          />
        ) : null}
        {currentWeather &&
        !currentWeather.passageComparison &&
        tab === "options" ? (
          <FrozenWeatherBasis evidence={currentWeather} />
        ) : null}
        {intelligence ? (
          <FrozenIntelligenceBasis evidence={intelligence} />
        ) : null}
        {tab === "options" ? (
          currentWeather?.passageComparison ? (
            <>
              <div className="border-b border-[var(--line)] px-2 py-1">
                <Chip
                  active={compare}
                  onClick={() => onToggleCompare(!compare)}
                  title="Draw every feasible option on the water at once"
                >
                  Compare on map
                </Chip>
              </div>
              <PassageDecisionSummary
                problem={problem}
                evidence={currentWeather}
                selectedOptionId={selectedOptionId}
                onSelectOption={onSelectOption}
              />
              <details className="min-w-0 border-t border-[var(--line)] px-2 py-2 text-xs [overflow-wrap:anywhere]">
                <summary className="cursor-pointer font-medium">
                  Full passage schedule and evidence
                </summary>
                <FrozenWeatherBasis evidence={currentWeather} />
              </details>
              {notOffered.length ? (
                <details className="border-t border-[var(--line)] px-2 py-2 text-xs [overflow-wrap:anywhere]">
                  <summary>Other action availability</summary>
                  {notOffered.map((action) => (
                    <p key={action.kind}>
                      {action.label}: {action.availability.status} ·{" "}
                      {action.availability.reason}
                    </p>
                  ))}
                </details>
              ) : null}
            </>
          ) : (
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
                    {intelligence?.kind === "PARADIP_ENTRY_RESTRICTION"
                      ? "Manual review required"
                      : "no feasible option survived"}
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
                      <span className="text-[var(--text-2)]">{row.label}</span>{" "}
                      ·{" "}
                      {row.availability.status.toLowerCase().replace("_", " ")}{" "}
                      — {row.availability.reason}
                    </p>
                  ))}
                </div>
              ) : null}
            </div>
          )
        ) : null}

        {tab === "robust" ? (
          currentWeather?.passageComparison ? (
            <div
              className="space-y-2 p-2 text-xs"
              data-testid="passage-policy-explanation"
            >
              <p>
                <PassageRecommendation problem={problem} />
              </p>
              <p>
                Closure-duration stress horizons are not used for this declared
                hourly approach comparison. Partial monetary components do not
                establish a total cost or cheapest plan.
              </p>
              <p>
                Hourly gust and visibility at the port, the declared passage and
                operator limits determine conditional approach timing. Daily
                corrections, regional hazards and activity layers do not enter
                this calculation. Calibrated uncertainty remains unavailable.
              </p>
              <details>
                <summary>Original recommendation and ranking basis</summary>
                <p className="whitespace-pre-wrap break-words">
                  {problem.recommendation?.statement ??
                    "No original recommendation retained."}
                </p>
                <p>{problem.recommendation?.why}</p>
                <pre className="whitespace-pre-wrap break-words">
                  {JSON.stringify(
                    problem.recommendation?.rankingBasis ?? {},
                    null,
                    2,
                  )}
                </pre>
              </details>
            </div>
          ) : problem.evidence.currentEnvironment ? (
            <p className="p-2 text-xs">
              This comparison uses hourly gust and visibility with explicit
              operator limits. Both options reach the same forecast-clear
              approach. Closure-duration stress horizons are not used. Fuel,
              cost, berth availability and calibrated uncertainty are
              unavailable.
            </p>
          ) : intelligence?.kind === "NOTICE_RESTRICTION" ? (
            <p className="p-2 text-xs">
              This calculation uses the authority's published access schedule,
              declared passage and fixed onward travel assumption. Both options
              have the same total schedule shift. Actual reopening, slot,
              clearance, berth, fuel, cost and safety effects are unavailable;
              no closure-duration stress model is applied.
            </p>
          ) : intelligence ? (
            <p className="p-2 text-xs">
              The closure-duration stress model does not apply to this
              review-hold scenario. Event-caused delay, cost, fuel, berth and
              calibrated safety effects remain unavailable.
            </p>
          ) : (
            <RobustView
              problem={problem}
              selectedOptionId={selectedOptionId}
              onSelect={onSelectOption}
            />
          )
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
          <>
            <p className="px-2 pt-2 text-xs">{problem.headline}</p>
            {currentWeather?.passageComparison ? (
              <div className="space-y-2 p-2 text-xs [overflow-wrap:anywhere]">
                <p>
                  <PassageRecommendation problem={problem} />
                </p>
                <p>
                  Anchorage waiting includes requested-window waiting and the
                  subsequent hourly forecast gate. Sailing and permitted
                  departure holding are separate. Lower modeled fuel cannot
                  excuse a hard deadline miss.
                </p>
                {currentWeather.passageComparison.limitations.map(
                  (text, index) => (
                    <p key={index}>{text}</p>
                  ),
                )}
              </div>
            ) : null}
            <CriticView problem={problem} option={selected ?? baseline} />
            {currentWeather ? (
              <details className="min-w-0 border-t border-[var(--line)] px-2 py-2 text-xs [overflow-wrap:anywhere]">
                <summary className="cursor-pointer font-medium">
                  Frozen weather and passage evidence
                </summary>
                <FrozenWeatherBasis evidence={currentWeather} />
                <p>Original headline: {problem.headline}</p>
                <p>
                  Original current-plan statement: {problem.doNothingStatement}
                </p>
                <p>
                  Original recommendation:{" "}
                  {problem.recommendation?.statement ?? "Unavailable"}
                </p>
                <pre className="whitespace-pre-wrap break-words">
                  {JSON.stringify(currentWeather, null, 2)}
                </pre>
              </details>
            ) : null}
          </>
        ) : null}

        {tab === "workflow" ? (
          <>
            {session?.user.role === "SHIPPING_COMPANY" ? (
              <DecisionTradeoff
                key={problem.decisionId}
                problemId={problem.decisionId}
              />
            ) : null}
            <WorkflowView
              problem={problem}
              target={workflowTarget}
              selected={selected}
              canHandoff={canHandoff && session?.user.canApprove !== false}
              canApprove={session?.user.canApprove !== false}
              singleApproval={singleApproval}
              issueOnApprove={issueOnApprove}
              issueComplete={issueComplete}
              onConfirm={(optionId, issue) =>
                confirm.mutate({ optionId, issue })
              }
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
                  reviewBefore:
                    singleApproval && problem.workflow === "COMPUTED",
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
                confirm.isPending ||
                workflow.transition.isPending ||
                workflow.handoff.isPending ||
                workflow.outcome.isPending
              }
              error={
                confirm.error?.message ??
                (workflow.transition.error as Error | null)?.message ??
                (workflow.handoff.error as Error | null)?.message ??
                (workflow.outcome.error as Error | null)?.message ??
                null
              }
              handoffResult={workflow.handoff.data ?? null}
            />
          </>
        ) : null}
      </div>
      {tab === "options" &&
      (currentWeather?.passageComparison ||
        intelligence?.kind === "PARADIP_ENTRY_RESTRICTION") ? (
        <div className="pw-next-action shrink-0">
          <button
            type="button"
            onClick={() => setTab("workflow")}
            className="w-full rounded border px-3 py-2"
          >
            Continue to Decide
          </button>
        </div>
      ) : null}
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
  target,
  selected,
  canHandoff,
  canApprove,
  singleApproval,
  issueOnApprove,
  issueComplete,
  onConfirm,
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
  target: { key: string; showControls: boolean } | null;
  selected: DecisionOption | null;
  canHandoff: boolean;
  canApprove: boolean;
  singleApproval: boolean;
  issueOnApprove: boolean;
  issueComplete: boolean;
  onConfirm: (optionId: string, issue: boolean) => void;
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
  const workflowIntro = useRef<HTMLParagraphElement>(null);
  const workflowLog = useRef<HTMLOListElement>(null);
  useEffect(() => {
    if (!target) return;
    scrollToWorkflowStep(
      target.showControls
        ? workflowIntro.current
        : workflowLog.current?.querySelector(
            `[data-workflow-stage="${target.key}"]`,
          ),
    );
  }, [target]);
  const chosen =
    problem.options.find((o) => o.optionId === problem.humanChoice) ?? null;
  const execution = problem.evidence?.execution as
    { by?: string; mechanism?: string } | undefined;
  const actorMayHandoff =
    canHandoff &&
    !issueOnApprove &&
    problem.workflow === "APPROVED" &&
    chosen &&
    !chosen.isBaseline;

  const ready =
    problem.workflow === "COMPUTED" || problem.workflow === "REVIEWED";
  const resumeIssue =
    issueOnApprove &&
    !issueComplete &&
    chosen &&
    !chosen.isBaseline &&
    (problem.workflow === "APPROVED" || problem.workflow === "PROPOSED");
  const option = resumeIssue ? chosen : selected;
  const issue = issueOnApprove && Boolean(option && !option.isBaseline);

  return (
    <div
      className="flex flex-col gap-2 px-2 py-1.5"
      data-testid="decision-workflow"
    >
      <p
        ref={workflowIntro}
        className="text-[10px] leading-snug text-[var(--text-3)]"
      >
        Decision ≠ execution. A named person reviews and approves;{" "}
        {execution?.mechanism === "ISSUE_ADVISORY"
          ? `the approved option reaches the ${problem.domain === "CARGO_CONNECTION" ? "booking party" : "vessel"} as an advisory to ${execution.by}, never as a command.`
          : "the approved option is carried out by its actor and the outcome is recorded here."}
      </p>

      {problem.workflow === "COMPUTED" && (!singleApproval || !canApprove) ? (
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
      {(singleApproval && canApprove && (ready || resumeIssue)) ||
      (!singleApproval && problem.workflow === "REVIEWED") ? (
        <div className="flex gap-1">
          <button
            type="button"
            disabled={
              busy || !canApprove || !option || option.status !== "FEASIBLE"
            }
            onClick={() =>
              singleApproval && option
                ? onConfirm(option.optionId, issue)
                : onApprove()
            }
            data-testid="decision-approve"
            className="flex-1 rounded bg-[var(--action)] px-2 py-1 text-[10px] font-medium text-[var(--on-signal)] hover:bg-[var(--signal-ink)] disabled:opacity-50"
          >
            {issue
              ? "Approve and issue to vessel"
              : `Approve ${option ? (option.isBaseline ? "current plan" : option.label) : "— select an option"}`}
          </button>
          {ready ? (
            <button
              type="button"
              disabled={busy}
              onClick={onDecline}
              data-testid="decision-decline"
              className="rounded border border-[var(--line)] px-2 py-1 text-[10px] text-[var(--text-2)] hover:bg-[var(--surface-2)]"
            >
              Decline
            </button>
          ) : null}
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
      {(problem.evidence?.currentEnvironment ||
        problem.evidence?.intelligenceBasis) &&
      problem.workflow === "APPROVED" &&
      problem.actor.role === "SHIPPING_COMPANY" ? (
        <p className="text-[11px] text-[var(--text-2)]">
          Company proposal submitted to your demo Port desk. Switch to Port
          Authority → Advisories to review the same frozen evidence, issue the
          advisory and await Vessel response.
        </p>
      ) : null}
      {!problem.evidence?.currentEnvironment &&
      !problem.evidence?.intelligenceBasis &&
      ["APPROVED", "ACCEPTED", "DECLINED"].includes(problem.workflow) ? (
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
      <ol ref={workflowLog} className="pw-decision-workflow-log">
        {WORKFLOW.map(({ key, label }) => {
          const history = problem.workflowHistory.filter(
            (entry) => entry.state === key,
          );
          return (
            <li key={key} data-workflow-stage={key}>
              <h3>{label}</h3>
              {history.length ? (
                <ul>
                  {history.map((step, index) => (
                    <li key={index}>
                      {step.at.slice(0, 16).replace("T", " ")} · {step.actor}
                      {step.optionId ? ` · ${step.optionId}` : ""}
                      {step.note ? ` · ${step.note}` : ""}
                    </li>
                  ))}
                </ul>
              ) : (
                <p>Pending</p>
              )}
            </li>
          );
        })}
        {problem.workflowHistory
          .filter((entry) => !WORKFLOW.some((step) => step.key === entry.state))
          .map((step, index) => (
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
