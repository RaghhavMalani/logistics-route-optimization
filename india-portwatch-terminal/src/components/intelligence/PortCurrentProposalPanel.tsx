import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation } from "@tanstack/react-router";
import { useAuth, useWorkspace } from "@/auth/AuthProvider";
import { Panel, Button } from "@/components/kit/layout";
import { DecisionPanel } from "@/components/decision/DecisionPanel";
import { FrozenWeatherBasis } from "./FrozenWeatherBasis";
import {
  FrozenIntelligenceBasis,
  type IntelligenceBasis,
} from "./FrozenIntelligenceBasis";
import { useDecision } from "@/services/decisions";
import { useAdvisories } from "@/services/os-hooks";
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
  const { portCode } = useWorkspace();
  const client = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [compare, setCompare] = useState(true);
  const search = useLocation({ select: (location) => location.searchStr });
  const linkedProposal = new URLSearchParams(search).get("proposal");
  const [journeyId, setJourneyId] = useState<string | null>(null);
  const target = journeyId ?? linkedProposal;
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
  const proposal = target
    ? proposals.data?.proposals.find((row) => row.decisionId === target)
    : proposals.data?.proposals[0];
  const weather =
    proposal?.evidenceKind !== "intelligence" &&
    proposal?.evidenceKind !== "restriction"
      ? (proposal?.evidence as FrozenEnvironment | undefined)
      : undefined;
  const passage = weather?.passageComparison?.options;
  const baseline = passage?.[0];
  const choice = passage?.find(
    (option) => option.optionId === proposal?.optionId,
  );
  const decision = useDecision(proposal?.reviewDecisionId ?? null);
  const advisories = useAdvisories(identityHeaders, { portCode }, 8000);
  const linkedAdvisories = decision.data?.evidence.advisories;
  const vesselAccepted =
    !advisories.isError &&
    Array.isArray(linkedAdvisories) &&
    linkedAdvisories.length > 0 &&
    linkedAdvisories.every((id) =>
      advisories.data?.advisories.some(
        (row) =>
          row.advisoryId === id &&
          (row.state === "accepted" || row.state === "completed"),
      ),
    );
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
  if (session?.mode !== "demo") return null;
  if (!proposal)
    return target ? (
      <p role="status" className="p-3 text-sm">
        {proposals.isPending
          ? "Opening the linked proposal…"
          : "That proposal is unavailable in this Port workspace."}
      </p>
    ) : null;
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
      {baseline && choice ? (
        <section
          aria-label="Frozen passage at a glance"
          className="m-2 rounded border border-[var(--line-strong)] bg-[var(--panel-2)] p-3"
        >
          <p className="text-xs">
            Company-approved comparison · modeled values
          </p>
          <dl className="mt-2 flex flex-wrap gap-x-8 gap-y-2">
            <div>
              <dt className="text-xs">Declared speed</dt>
              <dd className="num text-lg font-semibold">
                {baseline.speedKn ?? "Unavailable"} →{" "}
                {choice.speedKn ?? "Unavailable"} kn
              </dd>
            </div>
            <div>
              <dt className="text-xs">Assumed anchorage wait</dt>
              <dd className="num text-lg font-semibold">
                {baseline.anchorageWaitHours?.toFixed(2) ?? "Unavailable"} →{" "}
                {choice.anchorageWaitHours?.toFixed(2) ?? "Unavailable"} h
              </dd>
            </div>
          </dl>
        </section>
      ) : null}
      <p className="px-2 py-2 text-[11px] text-[var(--text-2)]">
        Review the same frozen input and assumed arrival limits submitted by
        Company. Issue through the existing advisory register; Vessel must
        acknowledge and accept before the demo outcome.
      </p>
      {!decision.data ? (
        <>
          <Button
            variant="primary"
            disabled={review.isPending}
            onClick={() => review.mutate()}
          >
            {review.isPending
              ? "Opening Port review…"
              : proposal.evidenceKind === "restriction"
                ? "Review Company restriction proposal"
                : proposal.evidenceKind === "intelligence"
                  ? "Review Company intelligence proposal"
                  : "Review Company weather proposal"}
          </Button>
          <details className="m-2 text-xs" open={!passage}>
            <summary className="cursor-pointer font-medium">
              Frozen assumptions and source evidence
            </summary>
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
          </details>
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
            {result?.evidenceKind === "paradip_entry" ? (
              <p data-testid="current-demo-outcome">
                <strong>Simulated demo outcome</strong> · {result.note}
              </p>
            ) : result ? (
              <p data-testid="current-demo-outcome">
                <strong>Simulated demo outcome</strong> ·{" "}
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
                  disabled={!vesselAccepted || outcome.isPending}
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
