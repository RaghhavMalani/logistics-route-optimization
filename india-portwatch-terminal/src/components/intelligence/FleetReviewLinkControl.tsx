import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { getJson } from "@/services/api";
import {
  fleetReviewHash,
  fleetReviewSelection,
  getFleetDecisionTriage,
} from "@/services/rolling-intelligence";
import type { DecisionProblem } from "@/types/decisions";

/** Exact retained-case navigation; it never creates/re-ranks a comparison. */
export function FleetReviewLinkControl({
  enabled,
  onDecision,
  onInputs,
  onLeave,
}: {
  enabled: boolean;
  onDecision: (problem: DecisionProblem, optionId: string) => void;
  onInputs: (vesselId: string) => void;
  onLeave: () => void;
}) {
  const { session, identityHeaders } = useAuth();
  const [hash, setHash] = useState("");
  const applied = useRef("");
  const lastRead = useRef("");
  useEffect(() => {
    const read = () => {
      const next = window.location.hash;
      setHash(next);
      if (
        next !== lastRead.current &&
        (fleetReviewSelection(next) || applied.current)
      ) {
        // A failing new link must never leave the previous case looking like
        // the requested result. The exact case opens only after validation.
        applied.current = "";
        onLeave();
      }
      lastRead.current = next;
    };
    read();
    window.addEventListener("hashchange", read);
    window.addEventListener("popstate", read);
    return () => {
      window.removeEventListener("hashchange", read);
      window.removeEventListener("popstate", read);
    };
  }, [onLeave]);
  const selection = fleetReviewSelection(hash);
  const visitor = session?.demoId ?? session?.issuedAt ?? "no-session";
  const q = useQuery({
    queryKey: ["fleet-review-link", visitor, hash],
    enabled: enabled && selection != null,
    retry: false,
    staleTime: 0,
    gcTime: 0,
    queryFn: async ({ signal }) => {
      if (!selection?.vesselId)
        throw new Error("This fleet link does not identify an owned voyage.");
      if (selection.kind === "SAVED_COMPARISON" && !selection.decisionId)
        throw new Error(
          "This fleet link does not identify an exact saved comparison.",
        );
      const [projection, problem] = await Promise.all([
        getFleetDecisionTriage(identityHeaders, signal),
        selection.kind === "SAVED_COMPARISON"
          ? getJson<DecisionProblem>(
              `/decisions/problems/${encodeURIComponent(selection.decisionId)}`,
              identityHeaders,
              { signal },
            )
          : Promise.resolve(null),
      ]);
      const row = projection.rows.find(
        (candidate) => candidate.vessel.id === selection.vesselId,
      );
      if (!row)
        throw new Error(
          "This voyage is not in the current visitor's Company fleet. No other comparison was opened.",
        );
      if (selection.episodeId && row.episode?.id !== selection.episodeId) {
        throw new Error(
          "This link belongs to a historical or different call. Review current inputs explicitly; no replacement comparison was opened.",
        );
      }
      if (selection.kind === "CURRENT_INPUTS")
        return { vesselId: selection.vesselId, problem: null, optionId: null };
      if (
        !problem ||
        problem.subject.id !== selection.vesselId ||
        problem.actor.role !== "SHIPPING_COMPANY"
      ) {
        throw new Error(
          "The exact saved Company comparison does not belong to this linked voyage.",
        );
      }
      const evidence = (problem.evidence.currentEnvironment ??
        problem.evidence.intelligenceBasis) as
        { operationalEpisode?: { id?: string } } | undefined;
      if (
        !row.episode?.id ||
        evidence?.operationalEpisode?.id !== row.episode.id
      ) {
        throw new Error(
          "This saved record lacks the applicable current-call identity or belongs to a previous call. It remains historical; no current plan was substituted.",
        );
      }
      const linked =
        row.currentPlan.decisionId === problem.decisionId ||
        row.candidateComparisons.some(
          (candidate) => candidate.decisionId === problem.decisionId,
        );
      if (!linked)
        throw new Error(
          "This comparison is not an identified current plan or linked candidate for this call. No newer case was substituted.",
        );
      if (
        !selection.optionId ||
        !problem.options.some(
          (option) => option.optionId === selection.optionId,
        )
      ) {
        throw new Error(
          "This fleet link does not identify an exact retained option. No recommendation or highlighted alternative was substituted.",
        );
      }
      return {
        vesselId: selection.vesselId,
        problem,
        optionId: selection.optionId,
      };
    },
  });
  useEffect(() => {
    if (
      !enabled ||
      !q.data ||
      q.isFetching ||
      q.isError ||
      applied.current === hash
    )
      return;
    applied.current = hash;
    if (q.data.problem && q.data.optionId)
      onDecision(q.data.problem, q.data.optionId);
    else onInputs(q.data.vesselId);
  }, [enabled, hash, q.data, q.isFetching, q.isError, onDecision, onInputs]);
  if (!enabled || !selection) return null;
  if (q.isPending || q.isError || (q.isFetching && applied.current !== hash)) {
    return (
      <section
        className="pointer-events-auto absolute inset-x-3 top-3 z-50 mx-auto max-w-xl space-y-2 rounded border border-[var(--line-strong)] bg-[var(--panel)] p-3 text-xs [overflow-wrap:anywhere]"
        aria-label="Fleet review link status"
      >
        <p role={q.isError ? "alert" : "status"}>
          {q.isError
            ? q.error.message
            : "Loading the exact retained voyage comparison and current-call basis…"}
        </p>
        <div className="flex flex-wrap gap-2">
          <a className="underline" href="/company/overview#fleet-queue">
            Return to fleet review queue
          </a>
          {q.isError && selection.vesselId ? (
            <a
              className="underline"
              href={`#${fleetReviewHash({ kind: "CURRENT_INPUTS", vesselId: selection.vesselId })}`}
            >
              Review current inputs for this voyage
            </a>
          ) : null}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              window.location.hash = "";
              onLeave();
            }}
          >
            Close link message
          </Button>
        </div>
      </section>
    );
  }
  return null;
}
