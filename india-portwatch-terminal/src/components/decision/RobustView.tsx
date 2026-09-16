/**
 * The robust recommendation, in the operator's terms.
 *
 * The engine evaluated every option under four stress horizons for the
 * claim's duration and decided by minimax regret. What the operator needs
 * is not the arithmetic but its consequence: keep the plan, wait, or act;
 * why, in one sentence; how sure the product is about the duration (never
 * very); when the choice closes; when the next observation lands; and the
 * regret each option carries under each horizon so the sentence can be
 * checked. Nothing here computes. Every figure is the engine's.
 */

import { Pill, type Tone } from "@/components/kit/primitives";
import { cn } from "@/lib/utils";
import type {
  DecisionProblem,
  RecommendationKind,
  RobustAssessment,
} from "@/types/decisions";

const KIND_LABEL: Record<RecommendationKind, string> = {
  ACT: "Act",
  KEEP_CURRENT_PLAN: "Keep current plan",
  WAIT_FOR_MORE_INFORMATION: "Wait for more information",
};

const KIND_TONE: Record<RecommendationKind, Tone> = {
  ACT: "warn",
  KEEP_CURRENT_PLAN: "ok",
  WAIT_FOR_MORE_INFORMATION: "info",
};

const REVERSIBILITY_LABEL: Record<string, string> = {
  OPEN: "keeps every option open",
  HIGH: "highly reversible",
  UNTIL_BRANCH: "reversible until the branch point",
  PARTIAL: "partly reversible",
  IRREVERSIBLE: "irreversible",
};

export function kindLabel(kind: RecommendationKind | undefined): string {
  return kind ? KIND_LABEL[kind] : "Recommendation";
}

function hours(value: number | null | undefined): string {
  if (value == null) return "—";
  const h = Math.floor(value);
  const m = Math.round((value - h) * 60);
  return m ? `${h}h ${m.toString().padStart(2, "0")}m` : `${h}h`;
}

function optionLabel(
  problem: DecisionProblem,
  optionId: string | null | undefined,
): string {
  if (!optionId) return "—";
  return (
    problem.options.find((o) => o.optionId === optionId)?.label ?? optionId
  );
}

/** The header block: the verdict, the why, and the four facts an operator acts on. */
export function RobustHeadline({ problem }: { problem: DecisionProblem }) {
  const rec = problem.recommendation;
  if (!rec) return null;
  const rob = rec.robustness;
  const kind = rec.kind ?? "ACT";
  const contender = rob?.provisionalOptionId ?? rob?.contenderId ?? null;
  const contenderSummary = contender ? rob?.summary[contender] : undefined;
  const baseSummary = problem.baselineOptionId
    ? rob?.summary[problem.baselineOptionId]
    : undefined;
  const info = rob?.information ?? {};
  return (
    <div
      className="border-b border-[var(--line)] px-2 py-1.5"
      data-testid="robust-headline"
      data-kind={kind}
    >
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
          Recommendation
        </span>
        <Pill tone={KIND_TONE[kind]} solid>
          {kindLabel(kind)}
        </Pill>
        {rec.policy ? (
          <span
            className="ml-auto text-[10px] text-[var(--text-3)]"
            title="the policy that produced this recommendation"
          >
            {rec.policy}
          </span>
        ) : null}
      </div>
      <p className="mt-0.5 text-[11px] font-medium leading-snug text-[var(--text)]">
        {kind === "ACT"
          ? optionLabel(problem, rec.optionId)
          : kind === "WAIT_FOR_MORE_INFORMATION"
            ? `Do nothing yet${contender ? `; ${optionLabel(problem, contender).toLowerCase()} stays available` : ""}`
            : "Continue the current plan"}
      </p>
      {rob?.applicable ? (
        <dl className="mt-1 grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-[2px] text-[10px] leading-snug">
          <dt className="text-[var(--text-3)]">Why</dt>
          <dd className="text-[var(--text-2)]" data-testid="robust-why">
            {contenderSummary?.breakEven?.statement
              ? `${optionLabel(problem, contender)} ${contenderSummary.breakEven.statement}.`
              : rec.why}
          </dd>
          <dt className="text-[var(--text-3)]">Duration confidence</dt>
          <dd className="text-[var(--text-2)]">
            <span className="text-[var(--warn)]">
              {rob.durationConfidence.label}
            </span>
            <span className="text-[var(--text-3)]">
              {" "}
              · {rob.durationConfidence.basis}
            </span>
          </dd>
          <dt className="text-[var(--text-3)]">Decision window</dt>
          <dd className="num text-[var(--text-2)]">
            {problem.decisionWindowHours != null
              ? hours(problem.decisionWindowHours)
              : "open"}
            {info.branchPointInHours != null
              ? ` · branch point in ${hours(info.branchPointInHours)}`
              : ""}
          </dd>
          <dt className="text-[var(--text-3)]">Next useful observation</dt>
          <dd className="text-[var(--text-2)]">
            {info.reevaluateInHours != null
              ? `re-evaluate in ${hours(info.reevaluateInHours)} — ${info.nextObservationBasis ?? "event register refresh"}`
              : info.nextObservationHours != null
                ? `event register refreshes within ${hours(info.nextObservationHours)}${
                    problem.decisionWindowHours != null &&
                    info.nextObservationHours <= problem.decisionWindowHours
                      ? ", before the decision closes"
                      : ""
                  }`
                : "not stated"}
          </dd>
          <dt className="text-[var(--text-3)]">Robustness</dt>
          <dd className="text-[var(--text-2)]" data-testid="robust-wins">
            {baseSummary
              ? `Current plan wins ${baseSummary.wins}/${baseSummary.scenarios} stress horizons`
              : "—"}
            {contenderSummary
              ? `; ${optionLabel(problem, contender).toLowerCase()} wins ${contenderSummary.wins}/${contenderSummary.scenarios}, worst-case regret ${contenderSummary.worstCaseRegret.toFixed(0)} h`
              : ""}
          </dd>
        </dl>
      ) : rob && !rob.applicable ? (
        <p className="mt-0.5 text-[10px] leading-snug text-[var(--text-3)]">
          {rob.why}
        </p>
      ) : (
        <p className="mt-0.5 text-[10px] leading-snug text-[var(--text-3)]">
          {rec.statement}
        </p>
      )}
    </div>
  );
}

/** The Robust tab: the regret table by horizon, the picks, the gate, the break-evens. */
export function RobustView({
  problem,
  selectedOptionId,
  onSelect,
}: {
  problem: DecisionProblem;
  selectedOptionId: string | null;
  onSelect: (optionId: string) => void;
}) {
  const rec = problem.recommendation;
  const rob: RobustAssessment | null | undefined = rec?.robustness;
  if (!rec) {
    return (
      <p className="px-2 py-2 text-[10px] text-[var(--text-3)]">
        No feasible option survived; there is nothing to stress.
      </p>
    );
  }
  if (!rob || !rob.applicable) {
    return (
      <div
        className="px-2 py-2 text-[10px] leading-snug text-[var(--text-3)]"
        data-testid="robust-view"
      >
        <p>
          {rob?.why ??
            "The recommendation was not assessed across stress horizons."}
        </p>
        <p className="mt-1">
          Expected-value pick:{" "}
          <span className="text-[var(--text-2)]">
            {optionLabel(
              problem,
              rec.rankingBasis?.expectedBest ?? rec.optionId,
            )}
          </span>
        </p>
      </div>
    );
  }
  const labels = rob.scenarios.map((s) => s.label);
  const ids = Object.keys(rob.table);
  const ordered = [
    ...ids.filter((id) => id === problem.baselineOptionId),
    ...ids.filter((id) => id !== problem.baselineOptionId),
  ];
  return (
    <div className="flex flex-col gap-2 px-2 py-1.5" data-testid="robust-view">
      <div>
        <p className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
          Regret by stress horizon · hours against the best option under that
          horizon
        </p>
        <div className="mt-1 overflow-x-auto">
          <table className="w-full text-[10px]">
            <thead>
              <tr className="text-[var(--text-3)]">
                <th className="text-left font-normal">Option</th>
                {rob.scenarios.map((s) => (
                  <th
                    key={s.label}
                    className="num text-right font-normal"
                    title={`${s.description}${s.closureFromNowHours != null ? ` (${s.closureFromNowHours.toFixed(0)} h from now)` : ""}`}
                  >
                    {s.label.toLowerCase()}
                    {s.closureFromNowHours != null ? (
                      <span className="block text-[10px] text-[var(--text-3)]/80">
                        {s.closureFromNowHours.toFixed(0)} h
                      </span>
                    ) : (
                      <span className="block text-[10px] text-[var(--text-3)]/80">
                        open
                      </span>
                    )}
                  </th>
                ))}
                <th
                  className="num text-right font-normal"
                  title="the largest regret across the horizons"
                >
                  worst
                </th>
                <th
                  className="num text-right font-normal"
                  title="horizons where the option is within tolerance of the best"
                >
                  wins
                </th>
              </tr>
            </thead>
            <tbody>
              {ordered.map((id) => {
                const summary = rob.summary[id];
                const rows = rob.table[id];
                const isRec = id === rec.optionId;
                return (
                  <tr
                    key={id}
                    data-testid="robust-row"
                    data-option={id}
                    onClick={() => onSelect(id)}
                    className={cn(
                      "cursor-pointer border-t border-[var(--line)]",
                      id === selectedOptionId ? "bg-[var(--surface-2)]" : "",
                    )}
                  >
                    <td className="max-w-[140px] truncate py-[3px] pr-1 text-[var(--text-2)]">
                      {optionLabel(problem, id)}
                      {isRec ? (
                        <span className="ml-1 text-[10px] uppercase text-[var(--ok)]">
                          rec
                        </span>
                      ) : null}
                    </td>
                    {labels.map((label) => {
                      const cell = rows?.[label];
                      return (
                        <td
                          key={label}
                          className={cn(
                            "num py-[3px] text-right",
                            cell && cell.regret <= rob.tolerance.hours
                              ? "text-[var(--ok)]"
                              : "text-[var(--text-2)]",
                          )}
                          title={
                            cell
                              ? `delay ${cell.delay.toFixed(1)} h — ${cell.how}`
                              : "not modelled"
                          }
                        >
                          {cell ? cell.regret.toFixed(0) : "—"}
                        </td>
                      );
                    })}
                    <td className="num py-[3px] text-right text-[var(--text)]">
                      {summary ? summary.worstCaseRegret.toFixed(0) : "—"}
                    </td>
                    <td className="num py-[3px] text-right text-[var(--text)]">
                      {summary ? `${summary.wins}/${summary.scenarios}` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-1 text-[10px] leading-snug text-[var(--text-3)]">
          Queue model {rob.queueModel.name.toLowerCase()} (drain{" "}
          {rob.queueModel.drainFraction} × closure) — {rob.queueModel.basis}.
          Tolerance {rob.tolerance.hours} h: {rob.tolerance.basis}.
        </p>
      </div>

      <div className="flex flex-wrap gap-1" data-testid="robust-picks">
        {(
          [
            ["Expected best", rob.picks.EXPECTED_BEST],
            ["Robust best", rob.picks.ROBUST_BEST],
            ["Lowest worst-case regret", rob.picks.LOWEST_WORST_CASE_REGRET],
          ] as Array<[string, string | null]>
        ).map(([name, id]) => (
          <button
            key={name}
            type="button"
            onClick={() => id && onSelect(id)}
            className={cn(
              "rounded border border-[var(--line)] px-1.5 py-[2px] text-[10px]",
              id && id === selectedOptionId ? "bg-[var(--surface-2)]" : "",
            )}
            title={
              name === "Expected best"
                ? "the BALANCED expected-value ranking's pick"
                : name === "Robust best"
                  ? "wins the most stress horizons; ties to the lower worst case, then the plan"
                  : "the minimax pick: smallest worst-case regret across the horizons"
            }
          >
            <span className="text-[var(--text-3)]">{name} · </span>
            <span className="text-[var(--text)]">
              {optionLabel(problem, id)}
            </span>
          </button>
        ))}
      </div>

      {ordered
        .filter(
          (id) => id !== problem.baselineOptionId && rob.summary[id]?.breakEven,
        )
        .map((id) => {
          const summary = rob.summary[id];
          const be = summary.breakEven!;
          return (
            <p
              key={id}
              className="text-[10px] leading-snug text-[var(--text-2)]"
              data-testid="break-even"
            >
              <span className="text-[var(--text)]">
                {optionLabel(problem, id)}
              </span>{" "}
              {be.available
                ? be.statement
                : `break-even unavailable: ${be.reason}`}
              {be.available && be.winningShare != null
                ? ` (${Math.round(be.winningShare * 100)}% of closure lengths up to ${be.gridSpanHours?.toFixed(0)} h)`
                : ""}
              <span className="text-[var(--text-3)]">
                {" "}
                ·{" "}
                {REVERSIBILITY_LABEL[summary.reversibility.class] ??
                  summary.reversibility.class}
                {summary.reversibility.closesInHours != null
                  ? `, closes in ${hours(summary.reversibility.closesInHours)}`
                  : ""}
              </span>
            </p>
          );
        })}

      {rob.checks.length ? (
        <div>
          <p className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
            Intervention gate ·{" "}
            {optionLabel(
              problem,
              rob.provisionalOptionId ?? rob.contenderId ?? rec.optionId,
            )}
          </p>
          <ul className="mt-0.5 flex flex-col gap-[2px]">
            {rob.checks.map((check) => (
              <li
                key={check.name}
                data-testid="gate-check"
                data-passed={check.passed}
                className="flex flex-col"
              >
                <span className="flex items-center gap-1.5 text-[10.5px]">
                  <span
                    className={cn(
                      "num w-1.5",
                      check.passed
                        ? "text-[var(--ok)]"
                        : check.blocking
                          ? "text-[var(--crit)]"
                          : "text-[var(--warn)]",
                    )}
                  >
                    {check.passed ? "✓" : check.blocking ? "✕" : "!"}
                  </span>
                  <span className="text-[var(--text)]">
                    {check.name.replace(/_/g, " ")}
                  </span>
                  {!check.blocking ? (
                    <span className="text-[10px] uppercase text-[var(--text-3)]">
                      advisory
                    </span>
                  ) : null}
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

      {Object.keys(rob.notModelled).length ? (
        <p className="text-[10px] leading-snug text-[var(--text-3)]">
          Not in the table:{" "}
          {Object.entries(rob.notModelled)
            .map(([id, why]) => `${optionLabel(problem, id)} (${why})`)
            .join("; ")}
          .
        </p>
      ) : null}
    </div>
  );
}
