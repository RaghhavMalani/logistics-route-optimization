/**
 * A cargo decision: a consignment that misses its booked connection, and
 * every way of moving it that the cargo model's rules allow.
 *
 * Same object, same panel as a vessel's routing and a port's berth plan.
 * The options are checked by capacity, plugs, dangerous-goods, deadweight
 * and connection-window rules; a failed rule rejects the option with the
 * rule named. Arrival at the far port is not measured -- no onward transit
 * schedule is held -- and the panel says so rather than inventing one.
 */

import { useAuth, useWorkspace } from "@/auth/AuthProvider";
import { Panel } from "@/components/kit/layout";
import { Pill } from "@/components/kit/primitives";
import { useCreateDecision, useDecision } from "@/services/decisions";

import { DecisionPanel } from "./DecisionPanel";

export function CargoDecisionPanel({
  portCode,
  decisionId,
  onDecision,
  selectedOptionId,
  onSelectOption,
}: {
  portCode: string;
  decisionId: string | null;
  onDecision: (decisionId: string | null) => void;
  selectedOptionId: string | null;
  onSelectOption: (optionId: string | null) => void;
}) {
  const { identityHeaders } = useAuth();
  const { role } = useWorkspace();
  const create = useCreateDecision(identityHeaders);
  const decision = useDecision(decisionId);
  const problem = decision.data;

  return (
    <Panel
      title="Cargo decision"
      note={
        problem ? (
          <Pill tone="warn">Action required</Pill>
        ) : (
          <span className="text-[10.5px]">a missed connection</span>
        )
      }
      testId="cargo-decision"
    >
      {!problem ? (
        <div className="px-2 py-2">
          <p className="text-[10.5px] leading-relaxed text-[var(--text-2)]">
            Find the first consignment at this port whose booked sailing it
            cannot make, and compute every alternative: another vessel, the next
            sailing, a nearer yard zone -- each checked by the cargo model's own
            feasibility rules.
          </p>
          <button
            type="button"
            data-testid="cargo-decide"
            disabled={create.isPending}
            onClick={() =>
              create.mutate(
                { domain: "cargo", portCode, mode: "DEMO" },
                {
                  onSuccess: (created) => {
                    onDecision(created.decisionId);
                    onSelectOption(
                      created.recommendation?.optionId ??
                        created.baselineOptionId,
                    );
                  },
                },
              )
            }
            className="mt-2 rounded bg-[var(--accent)] px-2 py-1 text-[10px] font-medium text-[var(--surface)] disabled:opacity-50"
          >
            {create.isPending
              ? "Checking every connection…"
              : "What should we do?"}
          </button>
          {create.isError ? (
            <p className="mt-1 text-[10.5px] text-[var(--crit)]">
              {(create.error as Error).message}
            </p>
          ) : null}
        </div>
      ) : (
        <div className="flex max-h-[640px] min-h-0 flex-col">
          <DecisionPanel
            problem={problem}
            selectedOptionId={selectedOptionId}
            compare={false}
            onSelectOption={onSelectOption}
            onToggleCompare={() => undefined}
            onClose={() => {
              onDecision(null);
              onSelectOption(null);
            }}
            canHandoff={role === "PORT_AUTHORITY" || role === "NATIONAL_ADMIN"}
          />
        </div>
      )}
    </Panel>
  );
}
