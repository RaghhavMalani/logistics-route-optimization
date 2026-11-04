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
import type { HomeHandoff } from "@/components/advisory/WorkspaceHandoffCard";

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

const handoffLabels: Record<string, string> = {
  COMPANY_PROPOSED: "Awaiting Port review",
  PORT_REVIEWING: "Port review in progress",
  ISSUED_TO_VESSEL: "Issued to Vessel",
  ACKNOWLEDGED: "Acknowledged by Vessel",
  ACCEPTED: "Accepted by Vessel",
  OUTCOME_RECORDED: "Outcome completed",
  COMPLETED: "Advisory completed",
  QUERIED: "Vessel requested review",
  DECLINED: "Declined by Vessel",
  REJECTED: "Rejected by Port",
  WITHDRAWN: "Advisory withdrawn",
  EXPIRED: "Advisory expired",
};

export function PortCurrentProposalPanel({
  handoffs,
}: {
  handoffs: HomeHandoff[];
}) {
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
      void client.invalidateQueries({ queryKey: ["workspace-handoffs"] });
      setSelected(proposal?.optionId ?? null);
    },
  });
  const outcome = useMutation({
    mutationFn: (decisionId: string) =>
      postJson<{ outcome: DemoOutcome }>(
        `/decisions/problems/${decisionId}/demo-outcome`,
        {},
        identityHeaders,
      ),
    onSuccess: ({ outcome }, decisionId) => {
      client.setQueryData<DecisionProblem>(
        ["decision", decisionId],
        (problem) =>
          problem
            ? {
                ...problem,
                evidence: { ...problem.evidence, demoOutcome: outcome },
              }
            : problem,
      );
      void client.invalidateQueries({ queryKey: ["decision", decisionId] });
      void client.invalidateQueries({ queryKey: ["advisories"] });
      void client.invalidateQueries({ queryKey: ["workspace-handoffs"] });
    },
  });
  const result = decision.data?.evidence.demoOutcome as DemoOutcome | undefined;
  if (session?.mode !== "demo") return null;
  if (!proposal)
    return target ? (
      <p role="status" className="p-3 text-sm">
        {proposals.isPending
          ? "Opening the linked proposal…"
          : "That proposal is unavailable in this Port workspace."}
      </p>
    ) : null;
  const handoff = handoffs.find(
    (item) =>
      item.deepLink ===
      "/port/advisories?proposal=" + encodeURIComponent(proposal.decisionId),
  );
  const handoffStatus = result
    ? "Outcome completed"
    : handoff
      ? handoffLabels[handoff.state]
      : undefined;
  const closedWindowStatus =
    handoff?.advisoryId || result ? handoffStatus : undefined;
  return (
    <Panel
      title={
        proposal.evidenceKind === "restriction"
          ? "Company authority-restriction proposal"
          : proposal.evidenceKind === "intelligence"
            ? "Company intelligence proposal"
            : "Company current-weather proposal"
      }
      note={
        handoffStatus
          ? `${proposal.subject} · ${handoffStatus}`
          : proposal.subject
      }
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
              closedWindowStatus={closedWindowStatus}
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
                  onClick={() => outcome.mutate(decision.data.decisionId)}
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
