/**
 * A port decision beside the 3D twin.
 *
 * Three ships arrive within ninety minutes: the port authority can keep the
 * incumbent rule, reassign berths, stagger the arrivals, size the gangs or
 * move one call up the queue. Each option is the twin run forward under
 * that policy, and the scene shows the selected one -- the berth plan the
 * option produced is written onto the state the renderer projects, so a
 * different option is a visibly different quay, not a different number.
 */

import { useState } from "react";

import { useAuth, useWorkspace } from "@/auth/AuthProvider";
import { Panel } from "@/components/kit/layout";
import { Pill } from "@/components/kit/primitives";
import { useCreateDecision, useDecision } from "@/services/decisions";
import type { DecisionOption, DecisionProblem } from "@/types/decisions";
import type { PortTwinState } from "@/types/portwatch-os";

import { DecisionPanel } from "./DecisionPanel";

/**
 * The twin's state with an option's berth plan applied.
 *
 * Only what the plan decides changes: which call sits at which berth, and
 * which cranes it holds. Everything else -- yard, sheds, gates -- is the
 * observed state, so the difference between two options on screen is
 * exactly the difference the engine computed.
 */
export function applyPortPlan(
  state: PortTwinState,
  option: DecisionOption | null,
): PortTwinState {
  if (!option?.evaluation) return state;
  const assignments =
    (option.evaluation.derived.assignments as Array<{
      callId: string;
      name: string;
      berthId: string | null;
      berthedHour: number | null;
      craneIds: string[];
      state: string;
      waitHours: number;
      imposedDelayHours: number;
    }>) ?? [];
  const byBerth = new Map<string, (typeof assignments)[number]>();
  for (const row of assignments) {
    if (
      row.berthId &&
      (row.state === "alongside" || row.state === "departed") &&
      !byBerth.has(row.berthId)
    ) {
      byBerth.set(row.berthId, row);
    }
  }
  const byCall = new Map(assignments.map((row) => [row.callId, row]));
  return {
    ...state,
    berths: state.berths.map((berth) => {
      const plan = byBerth.get(berth.berth_id);
      return plan
        ? {
            ...berth,
            occupied_by: plan.callId,
            free_at_hour: null,
            occupied_hours: berth.occupied_hours,
          }
        : {
            ...berth,
            occupied_by: berth.occupied_by?.startsWith("seed-")
              ? berth.occupied_by
              : null,
          };
    }),
    cranes: state.cranes.map((crane) => {
      const holder = assignments.find(
        (row) => row.craneIds.includes(crane.crane_id) && row.berthId,
      );
      return { ...crane, assigned_berth: holder?.berthId ?? null };
    }),
    calls: state.calls.map((call) => {
      const plan = byCall.get(call.call_id);
      return plan
        ? {
            ...call,
            berth_id: plan.berthId,
            berthed_hour: plan.berthedHour,
            assigned_cranes: plan.craneIds,
            wait_hours: plan.waitHours,
            imposed_delay_hours: plan.imposedDelayHours,
            state:
              (plan.state as PortTwinState["calls"][number]["state"]) ??
              call.state,
          }
        : call;
    }),
  };
}

export function PortDecisionPanel({
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
  const [bunch, setBunch] = useState(3);
  const problem: DecisionProblem | undefined = decision.data;

  return (
    <Panel
      title="Port decision"
      note={
        problem ? (
          <Pill tone="warn">Action required</Pill>
        ) : (
          <span className="text-[10.5px]">what should we do?</span>
        )
      }
      testId="port-decision"
    >
      {!problem ? (
        <div className="px-2 py-2">
          <p className="text-[10.5px] leading-relaxed text-[var(--text-2)]">
            Bunch the next arrivals within ninety minutes and let the engine
            compute every berth, crane and slot option through this twin --
            first come, first served as the baseline.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <label className="flex items-center gap-1 text-[10px] text-[var(--text-3)]">
              arrivals
              <input
                type="number"
                min={2}
                max={6}
                value={bunch}
                onChange={(e) => setBunch(Number(e.target.value))}
                className="num w-12 rounded border border-[var(--line)] bg-transparent px-1 text-[10px] text-[var(--text)]"
                data-testid="port-bunch"
              />
            </label>
            <button
              type="button"
              data-testid="port-decide"
              disabled={create.isPending}
              onClick={() =>
                create.mutate(
                  {
                    domain: "port",
                    portCode,
                    bunchArrivals: bunch,
                    mode: "DEMO",
                  },
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
              className="rounded bg-[var(--accent)] px-2 py-1 text-[10px] font-medium text-[var(--surface)] disabled:opacity-50"
            >
              {create.isPending
                ? "Simulating every option…"
                : "What should we do?"}
            </button>
          </div>
          {create.isError ? (
            <p className="mt-1 text-[10.5px] text-[var(--crit)]">
              {(create.error as Error).message}
            </p>
          ) : null}
          <p className="mt-2 text-[10px] leading-snug text-[var(--text-3)]">
            The bunching is a scenario assumption on a clone of the observed
            twin, recorded as one. The observed twin is never edited.
          </p>
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
