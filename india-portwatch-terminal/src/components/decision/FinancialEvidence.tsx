/**
 * Where the money came from -- and where there is none.
 *
 * Each component of an option's cost is one of three things: KNOWN, with the
 * rate and its source type; ZERO, with the reason it is zero; UNKNOWN, with
 * the reason it could not be priced. The three are rendered differently
 * because they mean different things, and a total is shown only when every
 * component is known. Anything built on an operator's assumption carries the
 * ASSUMPTION label on the figure itself, not in a footnote.
 */

import { useState } from "react";

import { Pill, type Tone } from "@/components/kit/primitives";
import type { ScenarioAssumptions } from "@/services/decisions";
import type {
  DecisionOption,
  DecisionRecommendation,
  FinancialEvaluation,
} from "@/types/decisions";

const STATE_TONE: Record<"KNOWN" | "ZERO" | "UNKNOWN", Tone> = {
  KNOWN: "ok",
  ZERO: "neutral",
  UNKNOWN: "warn",
};

export function money(
  value: { amount: number; currency: string } | null | undefined,
): string {
  if (!value) return "unknown";
  return `${value.currency} ${Math.round(value.amount).toLocaleString("en-IN")}`;
}

/**
 * The gaps an operator may fill for a scenario. Each is a figure the engine
 * refused to invent: a charter rate, a bunker price, a burn, a tonnage.
 * Which ones are offered follows from which components came back unknown.
 */
const ASSUMABLE: Array<{
  id: string;
  kind: "rate" | "vessel";
  primitive: string;
  label: string;
  unit: string;
  currency?: string;
  forComponent: string;
  /** The engine's own reason for the gap; a field is offered only when this is why. */
  gap: RegExp;
}> = [
  {
    id: "charter",
    kind: "rate",
    primitive: "charter_day",
    label: "Charter",
    unit: "USD/day",
    currency: "USD",
    forComponent: "delay",
    gap: /charter rate/i,
  },
  {
    id: "bunker",
    kind: "rate",
    primitive: "bunker_price_t",
    label: "Bunker",
    unit: "USD/t",
    currency: "USD",
    forComponent: "fuel",
    gap: /bunker price/i,
  },
  {
    id: "burn",
    kind: "rate",
    primitive: "fuel_burn_t_day",
    label: "Burn",
    unit: "t/day",
    currency: "USD",
    forComponent: "fuel",
    gap: /fuel burn/i,
  },
  {
    id: "grt",
    kind: "vessel",
    primitive: "grt",
    label: "Gross tonnage",
    unit: "GT",
    forComponent: "port",
    gap: /gross tonnage/i,
  },
];

export function FinancialEvidence({
  option,
  baseline,
  recommendation,
  onRecompute,
  recomputing = false,
}: {
  option: DecisionOption;
  baseline: DecisionOption | null;
  recommendation: DecisionRecommendation | null;
  /** Re-run this decision priced with the assumptions given; absent, no form is offered. */
  onRecompute?: (assumptions: ScenarioAssumptions) => void;
  recomputing?: boolean;
}) {
  const financial: FinancialEvaluation | null =
    option.evaluation?.financial ?? null;
  if (!financial) {
    return (
      <p className="px-2 py-2 text-[10px] italic text-[var(--text-3)]">
        This option was not priced: it was rejected before evaluation.
      </p>
    );
  }
  const avoidable = recommendation?.expectedAvoidableCost;
  const isRecommended = recommendation?.optionId === option.optionId;

  return (
    <div
      data-testid="financial-evidence"
      className="flex flex-col gap-1.5 px-2 py-1.5"
    >
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] font-medium text-[var(--text)]">
          {financial.total
            ? `Total ${money(financial.total)}`
            : "Total unknown"}
        </span>
        {financial.label ? (
          <Pill tone={financial.label === "ASSUMPTION" ? "unc" : "info"}>
            {financial.label}
          </Pill>
        ) : null}
        {!financial.complete ? (
          <span className="num text-[10px] text-[var(--text-3)]">
            {financial.unknown.length} unknown · partial{" "}
            {money(financial.partialTotal)}
          </span>
        ) : null}
      </div>

      <ul className="flex flex-col gap-[3px]">
        {financial.components.map((component) => (
          <li
            key={component.key}
            data-testid="cost-component"
            data-state={component.state}
            className="flex flex-col gap-[1px]"
          >
            <div className="flex items-center gap-1.5">
              <Pill tone={STATE_TONE[component.state]}>{component.state}</Pill>
              <span className="min-w-0 flex-1 truncate text-[10px] text-[var(--text)]">
                {component.label}
              </span>
              <span className="num shrink-0 text-[10px] text-[var(--text-2)]">
                {component.state === "KNOWN"
                  ? money(component.money)
                  : component.state === "ZERO"
                    ? "0"
                    : "—"}
              </span>
            </div>
            <p className="pl-1 text-[10px] leading-snug text-[var(--text-3)]">
              {component.state === "KNOWN"
                ? `${component.sourceType}${component.isAssumption ? " (assumption)" : ""} · ${component.basis}`
                : component.reason}
            </p>
          </li>
        ))}
      </ul>

      {isRecommended && avoidable ? (
        <div className="rounded border border-[var(--line)] bg-[var(--surface-2)]/60 px-1.5 py-1">
          <p className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
            Cost of doing nothing vs this option
          </p>
          {avoidable.available ? (
            <div className="num mt-0.5 flex items-center gap-2 text-[10px]">
              <span>
                {money(
                  avoidable.costOfDoingNothing as {
                    amount: number;
                    currency: string;
                  },
                )}
              </span>
              <span className="text-[var(--text-3)]">vs</span>
              <span>
                {money(
                  avoidable.optionCost as { amount: number; currency: string },
                )}
              </span>
              <span className="ml-auto text-[var(--ok)]">
                avoidable{" "}
                {money(
                  avoidable.expectedAvoidableCost as {
                    amount: number;
                    currency: string;
                  },
                )}
              </span>
              {avoidable.label ? (
                <Pill tone="unc">{String(avoidable.label)}</Pill>
              ) : null}
            </div>
          ) : (
            <p className="mt-0.5 text-[10.5px] leading-snug text-[var(--text-2)]">
              Not computable:{" "}
              {String(avoidable.reason ?? "one side is unpriced")}.
              {baseline
                ? " Unknown components are shown above as unknown, never as zero."
                : ""}
            </p>
          )}
        </div>
      ) : null}
      {financial.notes.length ? (
        <p className="text-[10px] leading-snug text-[var(--text-3)]">
          {financial.notes.join(" · ")}
        </p>
      ) : null}
      {onRecompute ? (
        <AssumptionForm
          financial={financial}
          onRecompute={onRecompute}
          busy={recomputing}
        />
      ) : null}
    </div>
  );
}

/**
 * Price the scenario with figures the operator supplies. Nothing here is a
 * default: an empty field stays unknown, and every figure entered comes
 * back on the option labelled ASSUMPTION with the operator's name on it.
 */
function AssumptionForm({
  financial,
  onRecompute,
  busy,
}: {
  financial: FinancialEvaluation;
  onRecompute: (assumptions: ScenarioAssumptions) => void;
  busy: boolean;
}) {
  // Only the gaps a figure would close. A delay unknown because the ETA is
  // unknown is not fixed by a charter rate, and the form must not imply it is.
  const reasons = new Map(
    financial.components
      .filter((c) => c.state === "UNKNOWN")
      .map((c) => [c.key, c.reason] as const),
  );
  const offered = ASSUMABLE.filter((a) => {
    const reason = reasons.get(a.forComponent);
    return reason !== undefined && a.gap.test(reason);
  });
  const [values, setValues] = useState<Record<string, string>>({});
  if (!offered.length) return null;
  const entered = offered.filter(
    (a) => values[a.id] !== undefined && values[a.id].trim() !== "",
  );
  const valid = entered.every((a) => Number(values[a.id]) > 0);

  return (
    <form
      data-testid="assumption-form"
      className="rounded border border-dashed border-[var(--line-strong)] px-1.5 py-1"
      onSubmit={(event) => {
        event.preventDefault();
        if (!entered.length || !valid) return;
        const rates: ScenarioAssumptions["rates"] = [];
        const vessel: Record<string, number> = {};
        for (const a of entered) {
          const value = Number(values[a.id]);
          if (a.kind === "rate") {
            rates.push({
              primitive: a.primitive,
              value,
              currency: a.currency ?? "USD",
            });
          } else {
            vessel[a.primitive] = value;
          }
        }
        onRecompute({ rates, vessel });
      }}
    >
      <p className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
        Price this scenario with your own figures
      </p>
      <p className="mt-0.5 text-[10px] leading-snug text-[var(--text-3)]">
        Each figure is an assumption, labelled as one on every number it
        touches. Leave a field empty and that component stays unknown.
      </p>
      <div className="mt-1 grid grid-cols-2 gap-x-2 gap-y-1">
        {offered.map((a) => (
          <label
            key={a.id}
            className="flex min-w-0 flex-col gap-[1px] text-[10px] text-[var(--text-2)]"
          >
            <span>
              {a.label}{" "}
              <span className="num text-[var(--text-3)]">{a.unit}</span>
            </span>
            <input
              type="number"
              min={0}
              step="any"
              inputMode="decimal"
              data-testid={`assume-${a.id}`}
              value={values[a.id] ?? ""}
              onChange={(event) =>
                setValues((prev) => ({ ...prev, [a.id]: event.target.value }))
              }
              placeholder="unknown"
              className="num w-full rounded border border-[var(--line)] bg-[var(--surface)] px-1 py-0.5 text-[10px] text-[var(--text)] placeholder:italic placeholder:text-[var(--text-3)]"
            />
          </label>
        ))}
      </div>
      <div className="mt-1 flex items-center gap-1.5">
        <button
          type="submit"
          data-testid="assume-submit"
          disabled={busy || !entered.length || !valid}
          className="rounded bg-[var(--accent)] px-1.5 py-0.5 text-[10.5px] font-medium text-[var(--surface)] disabled:opacity-50"
        >
          {busy ? "Re-pricing…" : "Re-price with these assumptions"}
        </button>
        <span className="text-[10px] text-[var(--text-3)]">
          {entered.length
            ? `${entered.length} labelled ASSUMPTION`
            : "nothing assumed yet"}
        </span>
      </div>
    </form>
  );
}
