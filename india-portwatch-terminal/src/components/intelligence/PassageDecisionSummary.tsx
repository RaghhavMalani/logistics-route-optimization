import type { ReactNode } from "react";

import { formatUtc, Pill } from "@/components/kit/primitives";
import type {
  FrozenEnvironment,
  PassageOptionComparison,
} from "@/services/current-inputs";
import type { DecisionProblem } from "@/types/decisions";
import { CargoAssessmentStatus } from "./CargoCommitmentEvidence";
import { cargoHours, cargoTime } from "./cargo-presentation";

const finite = (value: number | null | undefined): value is number =>
  value != null && Number.isFinite(value);

function passageHours(value: number | null | undefined, signed = false) {
  return finite(value)
    ? `${signed && value > 0 ? "+" : ""}${Number(value.toFixed(2))} h`
    : "Unavailable";
}

function fuel(option: PassageOptionComparison) {
  return option.fuel?.available && finite(option.fuel.totalTonnes)
    ? `${option.fuel.totalTonnes.toFixed(2)} t · modeled`
    : "Unavailable";
}

function cost(option: PassageOptionComparison) {
  const financial = option.finance;
  const value = financial?.complete ? financial.total : financial?.partialTotal;
  return value && finite(value.amount)
    ? `${financial?.complete ? "Modeled" : "Partial"} ${value.currency} ${value.amount.toLocaleString("en-US", { maximumFractionDigits: 2 })}`
    : "Unavailable";
}

/** A display of retained fields, not a new ranking or a rewritten ledger statement. */
function passageRecommendationText(problem: DecisionProblem) {
  const evidence = problem.evidence.currentEnvironment as
    FrozenEnvironment | undefined;
  const option = evidence?.passageComparison?.options.find(
    (row) => row.optionId === problem.recommendation?.optionId,
  );
  if (!option || option.status !== "FEASIBLE") {
    return "Insufficient basis: no feasible passage recommendation is available.";
  }
  if (problem.recommendation?.kind === "WAIT_FOR_MORE_INFORMATION") {
    return `Wait for more information. Retained provisional plan: ${option.label}.`;
  }
  const keep =
    problem.recommendation?.kind === "KEEP_CURRENT_PLAN" ||
    option.optionId === problem.baselineOptionId;
  return `${keep ? "KEEP CURRENT PLAN" : `Recommended: ${option.label}`}.`;
}

export function PassageRecommendation({
  problem,
}: {
  problem: DecisionProblem;
}) {
  return <>{passageRecommendationText(problem)}</>;
}

export function PassageDecisionSummary({
  problem,
  evidence,
  selectedOptionId,
  onSelectOption,
  onContinue,
}: {
  problem: DecisionProblem;
  evidence: FrozenEnvironment;
  selectedOptionId: string | null;
  onSelectOption: (optionId: string) => void;
  onContinue: () => void;
}) {
  const comparison = evidence.passageComparison;
  if (!comparison) return null;
  const baselineId =
    problem.baselineOptionId ??
    problem.options.find((row) => row.isBaseline)?.optionId;
  const baseline = comparison.options.find(
    (row) => row.optionId === baselineId,
  );
  const selected = comparison.options.find(
    (row) => row.optionId === selectedOptionId,
  );
  // The inspected alternative is derived from the shared selection; no second
  // choice state can drift from the map, timeline, or approved advisory option.
  const alternative =
    (selected && selected.optionId !== baselineId ? selected : undefined) ??
    comparison.options.find(
      (row) =>
        row.optionId === problem.recommendation?.optionId &&
        row.optionId !== baselineId,
    ) ??
    comparison.options.find((row) => row.optionId !== baselineId);
  const plans = [baseline, alternative];
  const cargo = evidence.cargoComparison;
  const cargoFor = (option: PassageOptionComparison) =>
    cargo?.options.find((row) => row.optionId === option.optionId);
  const sameClear =
    baseline?.approachClearAt &&
    alternative?.approachClearAt &&
    baseline.approachClearAt === alternative.approachClearAt;
  const rows: Array<{
    label: string;
    render: (option: PassageOptionComparison) => ReactNode;
  }> = [
    {
      label: "Conditional clear approach",
      render: (option) => formatUtc(option.approachClearAt),
    },
    {
      label: "Anchorage waiting",
      render: (option) => passageHours(option.anchorageWaitHours),
    },
    {
      label: "Schedule vs current",
      render: (option) => passageHours(option.scheduleShiftHours, true),
    },
    { label: "Modeled fuel", render: fuel },
    {
      label: "Declared deadline",
      render: (option) =>
        option.deadlineAt ? (
          <>
            <span className="block">{formatUtc(option.deadlineAt)}</span>
            <strong
              className={
                option.deadlineMet === false ? "text-[var(--crit)]" : ""
              }
            >
              {option.deadlineMet == null
                ? "Not evaluated"
                : option.deadlineMet
                  ? "Within deadline"
                  : "MISSES DECLARED DEADLINE"}
            </strong>
          </>
        ) : (
          "Not declared"
        ),
    },
    { label: "Component costs", render: cost },
    {
      label: "Speed",
      render: (option) =>
        finite(option.speedKn)
          ? `${Number(option.speedKn.toFixed(2))} kn`
          : "Unavailable",
    },
    {
      label: "Departure / reference",
      render: (option) =>
        formatUtc(option.departureAt ?? comparison.referenceAt),
    },
    {
      label: "Physical approach arrival",
      render: (option) => formatUtc(option.arrivalAt),
    },
  ];
  if (evidence.cargoCommitment && cargo) {
    rows.splice(
      1,
      0,
      {
        label: "Cargo connection",
        render: (option) => (
          <CargoAssessmentStatus assessment={cargoFor(option)} />
        ),
      },
      {
        label: "Conditional cargo ready",
        render: (option) => cargoTime(cargoFor(option)?.readinessAt),
      },
      {
        label: "Loading cutoff",
        render: (option) => cargoTime(cargoFor(option)?.cutoffAt),
      },
      {
        label: "Cutoff slack",
        render: (option) => cargoHours(cargoFor(option)?.slackHours, true),
      },
    );
  }

  return (
    <section
      data-testid="passage-decision-summary"
      data-selected-option={selectedOptionId ?? ""}
      className="min-w-0 space-y-2 px-2 py-2 text-xs leading-relaxed text-[var(--text-2)] [overflow-wrap:anywhere]"
      aria-label="Declared passage decision summary"
    >
      <p role="status" className="font-medium text-[var(--text)]">
        {passageRecommendationText(problem)}
      </p>
      <div
        className="grid grid-cols-2 gap-1"
        aria-label="Choose the plan for review"
      >
        {comparison.options.map((option) => {
          const action = problem.options.find(
            (row) => row.optionId === option.optionId,
          );
          const isBaseline = option.optionId === baselineId;
          const feasible =
            option.status === "FEASIBLE" && action?.status === "FEASIBLE";
          return (
            <button
              key={option.optionId}
              type="button"
              aria-label={
                isBaseline ? "Select current plan" : `Select ${option.label}`
              }
              aria-pressed={option.optionId === selectedOptionId}
              data-option={option.optionId}
              data-testid="passage-select-option"
              disabled={!feasible}
              onClick={() => onSelectOption(option.optionId)}
              className="min-h-9 rounded border border-[var(--line-strong)] px-2 py-1 text-left aria-pressed:border-[var(--info)] aria-pressed:bg-[var(--info-dim)] hover:bg-[var(--surface-2)] disabled:cursor-not-allowed disabled:opacity-75"
            >
              {isBaseline ? "Select current plan" : `Select ${option.label}`}
              {option.optionId === selectedOptionId ? " · selected" : ""}
              {option.optionId === problem.recommendation?.optionId
                ? " · recommended"
                : ""}
              {!feasible ? " · unavailable for approval" : ""}
              {!feasible ? (
                <span className="block text-[var(--crit)]">
                  {option.status}:{" "}
                  {option.reason ??
                    action?.rejectedBy
                      .map((reason) => reason.detail)
                      .join("; ") ??
                    "Inspect the retained constraints."}
                </span>
              ) : null}
              {option.deadlineMet === false ? (
                <strong className="block text-[var(--crit)]">
                  MISSES DECLARED DEADLINE
                </strong>
              ) : null}
            </button>
          );
        })}
      </div>
      {sameClear ? (
        <p className="text-[var(--text)]">
          Same conditional clear-approach time. No earlier delivery is
          established.
          {cargo
            ? " With the same downstream assumptions, cargo readiness and cutoff slack are also unchanged."
            : ""}
        </p>
      ) : null}
      {evidence.cargoCommitment ? (
        <p data-testid="cargo-commitment-summary">
          Fictional cargo {evidence.cargoCommitment.shipment.shipmentId} →{" "}
          {evidence.cargoCommitment.bookedConnection.name}.{" "}
          {evidence.cargoCommitment.mustMeet
            ? "Declared must-meet connection."
            : "Context only; passage ranking unchanged."}{" "}
          Full stage arithmetic, capacities and later-sailing proposals are in
          Full passage schedule and evidence. No booking or final delivery is
          established.
        </p>
      ) : null}
      <table
        className="w-full table-fixed border-collapse text-left"
        data-testid="passage-core-comparison"
      >
        <caption className="sr-only">
          Current plan and alternative · frozen conditional results · UTC
        </caption>
        <thead>
          <tr className="align-top">
            <th scope="col" className="w-[32%] py-1 pr-1 font-normal">
              Measure
            </th>
            {plans.map((option, index) => (
              <th
                scope="col"
                key={index}
                className="w-[34%] px-1 py-1 font-medium text-[var(--text)]"
              >
                <span className="block">
                  {index === 0
                    ? "Current plan"
                    : selectedOptionId === option?.optionId
                      ? "Selected alternative"
                      : "Alternative"}
                </span>
                <span className="block font-normal">
                  {option?.label ?? "Unavailable in saved record"}
                </span>
                {option ? (
                  <>
                    <Pill
                      className="block max-w-full whitespace-normal"
                      tone={option.status === "FEASIBLE" ? "ok" : "crit"}
                    >
                      {option.status}
                    </Pill>
                    {option.reason ? (
                      <p className="font-normal text-[var(--crit)]">
                        {option.reason}
                      </p>
                    ) : null}
                  </>
                ) : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ label, render }) => (
            <tr key={label} className="border-t border-[var(--line)] align-top">
              <th scope="row" className="py-1.5 pr-1 font-normal">
                {label}
              </th>
              {plans.map((option, index) => (
                <td key={index} className="px-1 py-1.5">
                  {option ? render(option) : "Unavailable"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        onClick={onContinue}
        className="min-h-9 w-full rounded border border-[var(--line-strong)] px-2 py-1 font-medium text-[var(--text)] hover:bg-[var(--surface-2)]"
      >
        Continue to Decide
      </button>
      <p>
        Operator-declared passage. {comparison.geometryBasis}. Port-approach
        weather only; clearance, berth confirmation and whole-route safety are
        not established.
      </p>
      <p>
        Fuel is modeled, not measured. Component costs are partial or
        unavailable; unknown inputs are not zero. No complete voyage saving is
        established.
      </p>
    </section>
  );
}
