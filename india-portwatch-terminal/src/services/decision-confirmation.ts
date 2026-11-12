import {
  fetchDecision,
  handoffDecision,
  transitionDecision,
} from "./decisions";
import { fetchAdvisories, transitionAdvisory } from "./portwatch-os";

type Headers = Record<string, string>;

/** The backend still owns scope, approval eligibility and every audited transition. */
export async function confirmDecisionOption(
  id: string,
  optionId: string,
  headers: Headers,
) {
  let decision = await fetchDecision(id);
  if (decision.options.find((option) => option.optionId === optionId)?.status !== "FEASIBLE")
    throw new Error("Select a feasible option to approve.");
  if (decision.workflow === "COMPUTED") {
    decision = await transitionDecision(id, { target: "REVIEWED", note: "reviewed in the terminal" }, headers);
  }
  if (decision.workflow === "REVIEWED") {
    decision = await transitionDecision(
      id,
      { target: "APPROVED", optionId, note: "chosen in the terminal" },
      headers,
    );
  }
  if (decision.humanChoice !== optionId)
    throw new Error("This decision has a different recorded choice.");
  return decision;
}

export async function confirmPortIssue(
  id: string,
  optionId: string,
  headers: Headers,
) {
  const decision = await confirmDecisionOption(id, optionId, headers);
  const saved = decision.evidence.advisories;
  const ids =
    Array.isArray(saved) && saved.length > 0
      ? saved.map(String)
      : (await handoffDecision(id, {}, headers)).advisories.map(
          (row) => row.advisoryId,
        );
  const list = await fetchAdvisories(headers);
  for (const advisoryId of ids) {
    let advisory = list.advisories.find((row) => row.advisoryId === advisoryId);
    if (!advisory)
      throw new Error(
        "The advisory draft could not be loaded. Retry to resume issuing.",
      );
    if (advisory.state === "draft")
      advisory = await transitionAdvisory(headers, advisoryId, "under_review");
    if (advisory.state === "under_review")
      advisory = await transitionAdvisory(headers, advisoryId, "issued");
    if (
      !["issued", "acknowledged", "accepted", "completed"].includes(
        advisory.state,
      )
    ) {
      throw new Error("This advisory can no longer be issued.");
    }
  }
  if (!ids.length)
    throw new Error("No advisory was created for this decision.");
  return ids;
}
