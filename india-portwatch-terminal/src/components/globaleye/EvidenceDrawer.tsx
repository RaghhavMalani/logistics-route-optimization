/**
 * Evidence Mode: why the product thinks what it says.
 *
 * Every line here is one step the World State Engine actually ran, with the
 * quantity that arrived, the quantity that left, the rule that converted them
 * and the catalogue the relationship came from. It is rendered from the trace,
 * not from a parallel explanation -- an explanation generated separately from
 * the computation is a second implementation, and the moment they disagree the
 * one on screen is the one a port authority would quote back.
 *
 * Declines are shown in the same list as successes. "This lane has no
 * alternative routing, so no detour time exists" is frequently the most
 * important line in the trace, and hiding refusals would leave an operator
 * believing the model considered something it could not.
 */

import { Pill } from "@/components/kit/primitives";
import { cn } from "@/lib/utils";
import type { AttentionItem, CascadeStep, WorldQuantity } from "@/types/portwatch-os";

function quantityText(quantity: WorldQuantity): string {
  const { value, unit, unitLabel } = quantity;
  if (unit === "ratio") return `${(value * 100).toFixed(1)}%`;
  if (unit === "risk") return `risk ${value.toFixed(2)}`;
  if (unit === "inr") return `INR ${value.toLocaleString()}`;
  if (unit === "vessels") return `${value.toFixed(0)} vessels`;
  return `${value.toFixed(1)} ${unitLabel}`;
}

/** A rule name as a person would read it. */
function ruleLabel(rule: string): string {
  return rule.replace(/_/g, " ");
}

export function EvidenceDrawer({
  item,
  steps,
  narrative,
  onClose,
}: {
  item: AttentionItem | null;
  steps: CascadeStep[];
  narrative: string[];
  onClose: () => void;
}) {
  if (!item) return null;

  return (
    <div
      className="pointer-events-auto flex min-h-0 flex-col"
      data-testid="evidence-drawer"
    >
      <div className="border-b border-[var(--line)] px-2 py-2">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="text-[11.5px] font-medium leading-snug text-[var(--text)]">
              {item.headline}
            </p>
            <p className="mt-1 text-[10px] leading-relaxed text-[var(--text-2)]">
              {item.reason}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 text-[10px] text-[var(--text-3)] hover:text-[var(--text)]"
            aria-label="Close evidence"
          >
            ✕
          </button>
        </div>
      </div>

      {/* ------------------------------------------------------- outcomes -- */}
      <div className="border-b border-[var(--line)] px-2 py-2">
        <Row label="If nothing changes">{item.doNothingOutcome}</Row>
        <Row label="Baseline">{item.baselineOutcome}</Row>
        {item.recommendedAction ? (
          <Row label="Best action">
            {item.recommendedAction.summary}
            {item.recommendedAction.tradeoff ? (
              <span className="block text-[var(--text-3)]">
                {item.recommendedAction.tradeoff}
              </span>
            ) : null}
          </Row>
        ) : null}
        <Row label="Operational effect">
          {item.expectedOperationalEffect.available
            ? item.expectedOperationalEffect.statement
            : <span className="italic text-[var(--text-3)]">
                {item.expectedOperationalEffect.unavailableBecause}
              </span>}
        </Row>
        <Row label="Financial effect">
          {item.expectedFinancialEffect.available
            ? item.expectedFinancialEffect.statement
            : <span className="italic text-[var(--text-3)]">
                {item.expectedFinancialEffect.unavailableBecause}
              </span>}
        </Row>
      </div>

      {/* ------------------------------------------------------ ranking -- */}
      <div className="border-b border-[var(--line)] px-2 py-2">
        <p className="mb-1 text-[9px] uppercase tracking-wide text-[var(--text-3)]">
          Why this rank
        </p>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[9.5px] text-[var(--text-2)]">
          {Object.entries(item.priorityBasis).map(([term, value]) => (
            <span key={term} className="num">
              {term.replace(/([A-Z])/g, " $1").toLowerCase()}{" "}
              <span className="text-[var(--text)]">{value.toFixed(2)}</span>
            </span>
          ))}
          <span className="num ml-auto">
            priority <span className="text-[var(--text)]">{item.priority.toFixed(3)}</span>
          </span>
        </div>
      </div>

      {/* --------------------------------------------------------- trace -- */}
      <div className="min-h-0 flex-1 overflow-auto">
        <p className="px-2 pb-1 pt-2 text-[9px] uppercase tracking-wide text-[var(--text-3)]">
          Computation trail
        </p>
        {steps.length === 0 ? (
          <p className="px-2 pb-2 text-[10px] text-[var(--text-3)]">
            No propagation step reached this subject.
          </p>
        ) : (
          <ol className="px-2 pb-2">
            {steps.map((step, index) => (
              <li
                key={`${step.from}-${step.to}-${index}`}
                data-testid="evidence-step"
                className={cn(
                  "border-l pl-2 py-1.5",
                  step.declined
                    ? "border-[var(--warn)]"
                    : "border-[var(--line)]",
                )}
              >
                <div className="flex items-center gap-1.5">
                  <span className="num text-[9px] text-[var(--text-3)]">
                    {step.depth}
                  </span>
                  <span className="truncate text-[10px] text-[var(--text)]">
                    {ruleLabel(step.rule)}
                  </span>
                  {step.declined ? (
                    <Pill tone="warn">declined</Pill>
                  ) : null}
                </div>

                {step.declined ? (
                  <p className="mt-0.5 text-[9.5px] leading-relaxed text-[var(--text-2)]">
                    {step.declined}
                  </p>
                ) : (
                  <p className="num mt-0.5 text-[9.5px] text-[var(--text-2)]">
                    {quantityText(step.incoming)}
                    {" → "}
                    {step.outgoing.map((q) => quantityText(q)).join(", ")}
                  </p>
                )}

                <p className="mt-0.5 truncate text-[9px] text-[var(--text-3)]">
                  {step.from.split(":")[1] ?? step.from} → {step.to.split(":")[1] ?? step.to}
                  {step.source ? ` · ${step.source}` : ""}
                </p>
              </li>
            ))}
          </ol>
        )}

        {narrative.length ? (
          <>
            <p className="px-2 pb-1 pt-1 text-[9px] uppercase tracking-wide text-[var(--text-3)]">
              Chain
            </p>
            <ul className="px-2 pb-3">
              {narrative.map((line) => (
                <li key={line} className="num text-[9.5px] leading-relaxed text-[var(--text-2)]">
                  {line}
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-1.5 last:mb-0">
      <p className="text-[9px] uppercase tracking-wide text-[var(--text-3)]">{label}</p>
      <p className="text-[10px] leading-relaxed text-[var(--text)]">{children}</p>
    </div>
  );
}
