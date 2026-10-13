import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { Panel, Button } from "@/components/kit/layout";
import { DecisionPanel } from "@/components/decision/DecisionPanel";
import { FrozenWeatherBasis } from "./FrozenWeatherBasis";
import {
  FrozenIntelligenceBasis,
  type IntelligenceBasis,
} from "./FrozenIntelligenceBasis";
import { useDecision } from "@/services/decisions";
import { getJson, postJson } from "@/services/api";
import type { FrozenEnvironment } from "@/services/current-inputs";
import type { DecisionProblem } from "@/types/decisions";

interface Proposal {
  decisionId: string;
  optionId: string;
  subject: string;
  evidence: FrozenEnvironment | IntelligenceBasis;
  evidenceKind?: string;
  totalScheduleShiftHours?: number;
  reviewDecisionId?: string | null;
}
interface DemoOutcome {
  kind: string;
  baselineAssumedWaitHours: number;
  selectedAssumedWaitHours: number;
  note: string;
  evidenceKind?: string;
  totalScheduleShiftHours?: number;
}

export function PortCurrentProposalPanel() {
  const { session, identityHeaders } = useAuth();
  const client = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [compare, setCompare] = useState(true);
  const [journeyId, setJourneyId] = useState<string | null>(null);
  const proposals = useQuery({
    queryKey: ["current-proposals"],
    queryFn: ({ signal }) =>
      getJson<{ proposals: Proposal[] }>(
        "/decisions/current-proposals",
        identityHeaders,
        { signal },
      ),
    enabled: session?.mode === "demo",
    refetchInterval: 10000,
  });
  const proposal =
    proposals.data?.proposals.find((p) => p.decisionId === journeyId) ??
    proposals.data?.proposals[0];
  const decision = useDecision(proposal?.reviewDecisionId ?? null);
  const review = useMutation({
    mutationFn: () =>
      postJson<DecisionProblem>(
        "/decisions/current-proposals/review",
        { decisionId: proposal?.decisionId },
        identityHeaders,
      ),
    onSuccess: (problem) => {
      client.setQueryData(["decision", problem.decisionId], problem);
      void client.invalidateQueries({ queryKey: ["current-proposals"] });
      setSelected(proposal?.optionId ?? null);
    },
  });
  const outcome = useMutation({
    mutationFn: () =>
      postJson<{ outcome: DemoOutcome }>(
        `/decisions/problems/${decision.data?.decisionId}/demo-outcome`,
        {},
        identityHeaders,
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["decision"] });
      void client.invalidateQueries({ queryKey: ["advisories"] });
    },
  });
  const result =
    outcome.data?.outcome ??
    (decision.data?.evidence.demoOutcome as DemoOutcome | undefined);
  if (session?.mode !== "demo" || !proposal) return null;
  return (
    <Panel
      title={
        proposal.evidenceKind === "restriction"
          ? "Company authority-restriction proposal"
          : proposal.evidenceKind === "intelligence"
            ? "Company intelligence proposal"
            : "Company current-weather proposal"
      }
      note={proposal.subject}
      testId="current-proposal-review"
    >
      {(proposals.data?.proposals.length ?? 0) > 1 ? (
        <label className="block p-2 text-xs">
          Saved journey{" "}
          <select
            aria-label="Saved shipping journey"
            className="bg-[var(--panel-2)]"
            value={proposal.decisionId}
            onChange={(e) => {
              setJourneyId(e.target.value);
              setSelected(null);
            }}
          >
            {proposals.data?.proposals.map((p) => (
              <option key={p.decisionId} value={p.decisionId}>
                {p.subject} · {p.decisionId}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <p className="px-2 py-2 text-[11px] text-[var(--text-2)]">
        Review the same frozen input and assumed arrival limits submitted by
        Company. Issue through the existing advisory register; Vessel must
        acknowledge and accept before the demo outcome.
      </p>
      {!decision.data ? (
        <>
          {proposal.evidenceKind === "intelligence" ||
          proposal.evidenceKind === "restriction" ? (
            <FrozenIntelligenceBasis
              evidence={proposal.evidence as IntelligenceBasis}
            />
          ) : (
            <FrozenWeatherBasis
              evidence={proposal.evidence as FrozenEnvironment}
            />
          )}
          <Button disabled={review.isPending} onClick={() => review.mutate()}>
            {review.isPending
              ? "Opening Port review…"
              : proposal.evidenceKind === "restriction"
                ? "Review Company restriction proposal"
                : proposal.evidenceKind === "intelligence"
                  ? "Review Company intelligence proposal"
                  : "Review Company weather proposal"}
          </Button>
        </>
      ) : (
        <>
          <div className="flex h-[650px] min-h-0 flex-col">
            <DecisionPanel
              problem={decision.data}
              selectedOptionId={selected ?? proposal.optionId}
              compare={compare}
              onSelectOption={setSelected}
              onToggleCompare={setCompare}
              canHandoff
            />
          </div>
          <div className="border-t border-[var(--line)] p-2 text-[11px]">
            {result ? (
              <p data-testid="current-demo-outcome">
                <strong>{result.kind}</strong> ·{" "}
                {result.evidenceKind === "restriction"
                  ? "baseline planned lock wait"
                  : result.evidenceKind === "intelligence"
                    ? "baseline assumed schedule shift"
                    : "baseline assumed wait"}{" "}
                {result.baselineAssumedWaitHours.toFixed(1)} h → selected{" "}
                {result.selectedAssumedWaitHours.toFixed(1)} h.{" "}
                {result.evidenceKind === "restriction"
                  ? `Both options: total schedule shift ${result.totalScheduleShiftHours?.toFixed(2)} h. `
                  : ""}
                {result.note}
              </p>
            ) : (
              <>
                <Button
                  disabled={
                    decision.data.workflow !== "PROPOSED" || outcome.isPending
                  }
                  onClick={() => outcome.mutate()}
                >
                  Run frozen demo outcome
                </Button>
                <p className="mt-1">
                  Available after advisory issue and Vessel
                  acknowledgement/acceptance. This reproduces the frozen
                  assumptions; it does not measure an actual wait.
                </p>
              </>
            )}
          </div>
        </>
      )}
      {review.isError ? <p role="alert">{review.error.message}</p> : null}
      {outcome.isError ? <p role="alert">{outcome.error.message}</p> : null}
      {decision.isError ? <p role="alert">{decision.error.message}</p> : null}
    </Panel>
  );
}
