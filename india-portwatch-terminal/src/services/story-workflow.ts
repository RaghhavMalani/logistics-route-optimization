import { postJson, getJson } from "./api";
import { fetchDecision } from "./decisions";
import {
  confirmDecisionOption,
  confirmPortIssue,
} from "./decision-confirmation";
import { fetchAdvisories, transitionAdvisory } from "./portwatch-os";
import type { StorySession } from "./story-session";
import type { DecisionProblem } from "@/types/decisions";
import type { FrozenEnvironment } from "./current-inputs";

function required(value: string | undefined) {
  if (!value) throw new Error("This chapter is missing its saved record.");
  return value;
}

export async function runStoryStep(
  story: StorySession,
  headers: Record<string, string>,
): Promise<StorySession> {
  switch (story.step) {
    case 0: {
      const result = await postJson<{
        problem?: DecisionProblem;
        missingInputs?: string;
      }>(
        "/demonstrations/select",
        { scenarioId: "S10", requestId: story.requestId, acknowledged: true },
        headers,
      );
      const problem = result.problem;
      if (!problem)
        throw new Error(
          result.missingInputs ?? "The S10 comparison could not be calculated.",
        );
      const option = problem.options.find(
        (row) => row.status === "FEASIBLE" && /10(?:\.0)? kn/i.test(row.label),
      );
      if (!option)
        throw new Error("The comparison did not return the 10 kn option.");
      const passage = (
        problem.evidence.currentEnvironment as FrozenEnvironment | undefined
      )?.passageComparison?.options;
      const before = passage?.[0]?.anchorageWaitHours;
      const after = passage?.find(
        (row) => row.optionId === option.optionId,
      )?.anchorageWaitHours;
      return {
        ...story,
        decisionId: problem.decisionId,
        optionId: option.optionId,
        wait:
          typeof before === "number" && typeof after === "number"
            ? { before, after }
            : undefined,
      };
    }
    case 1:
      await confirmDecisionOption(
        required(story.decisionId),
        required(story.optionId),
        headers,
      );
      return story;
    case 2: {
      const review = await postJson<DecisionProblem>(
        "/decisions/current-proposals/review",
        { decisionId: required(story.decisionId) },
        headers,
      );
      return { ...story, reviewId: review.decisionId };
    }
    case 3: {
      const [advisoryId] = await confirmPortIssue(
        required(story.reviewId),
        required(story.optionId),
        headers,
      );
      return { ...story, advisoryId };
    }
    case 4:
    case 5: {
      const id = required(story.advisoryId);
      const list = await fetchAdvisories(headers);
      const advisory = list.advisories.find((row) => row.advisoryId === id);
      if (!advisory)
        throw new Error("This vessel has not received the advisory yet.");
      const target = story.step === 4 ? "acknowledged" : "accepted";
      if (
        advisory.state !== target &&
        advisory.state !== "completed" &&
        !(target === "acknowledged" && advisory.state === "accepted")
      ) {
        await transitionAdvisory(headers, id, target);
      }
      return story;
    }
    case 6: {
      const id = required(story.reviewId);
      const problem = await fetchDecision(id);
      if (!problem.evidence.demoOutcome) {
        const result = await postJson<{
          outcome: { kind: string; eligibleForRealTarget: boolean };
        }>(
          `/decisions/problems/${encodeURIComponent(id)}/demo-outcome`,
          {},
          headers,
        );
        if (
          result.outcome.kind !== "SIMULATED_DEMO_OUTCOME" ||
          result.outcome.eligibleForRealTarget
        ) {
          throw new Error(
            "This story can only record a simulated demo outcome.",
          );
        }
      }
      return story;
    }
    default:
      return story;
  }
}
