import { useAuth } from "@/auth/AuthProvider";
import { formatUtc } from "@/components/kit/primitives";
import { useIntelligenceReviewTasks } from "@/services/intelligence-review-tasks";

export function IntelligenceReviewTasks() {
  const { session } = useAuth();
  const q = useIntelligenceReviewTasks();
  if (session?.mode !== "demo") return null;
  return (
    <details
      className="border border-[var(--line)] p-2 my-2"
      data-testid="intelligence-review-tasks"
    >
      <summary>
        Visitor verification tasks · {q.data?.tasks.length ?? "checking"}
      </summary>
      <p>
        Source accuracy and passage exposure need separate verification. These
        records do not approve an action, change an arrival or prove execution.
      </p>
      <button
        type="button"
        className="my-2 rounded border border-[var(--line)] px-2 py-1 text-xs"
        disabled={q.isFetching}
        onClick={() => void q.refetch()}
      >
        Check consumed source state
      </button>
      <p>
        These current task checks use the wall clock, separately from the
        feedback archive's as-of view.
      </p>
      {q.isError ? <p role="alert">{q.error.message}</p> : null}
      {q.data?.tasks.length === 0 ? (
        <p>No task requested in this visitor world.</p>
      ) : null}
      {q.data?.tasks.slice(0, 30).map((task) => (
        <details className="border-t border-[var(--line)] py-2" key={task.id}>
          <summary>
            {task.status} · {formatUtc(task.createdAt)}
          </summary>
          <p>{task.reason}</p>
          {task.sourceReview ? (
            <div
              className="my-2 min-w-0 border border-[var(--line)] p-2 text-xs [overflow-wrap:anywhere]"
              data-testid="task-source-review"
            >
              <p
                role={
                  task.sourceReview.requiresFreshReview ? "status" : undefined
                }
              >
                <strong>
                  {task.sourceReview.status === "REVIEW_REQUIRED"
                    ? "Consumed source changed — fresh review required"
                    : "Consumed source unchanged"}
                </strong>
              </p>
              <p>{task.sourceReview.reason}</p>
              <p>
                Checked as of {formatUtc(task.sourceReview.asOf)}. Changed
                dependencies:{" "}
                {task.sourceReview.changedFields.join(", ") || "none"}.
              </p>
              {task.sourceReview.currentAssessment ? (
                <p>
                  Current source assessment{" "}
                  {task.sourceReview.currentAssessment.verdict}; applicability{" "}
                  {task.sourceReview.currentAssessment.applicability}.{" "}
                  {task.sourceReview.currentAssessment.reason}
                </p>
              ) : null}
              <p>
                Original task status and frozen evidence remain {task.status}.
                This source review adds zero real operational targets and does
                not approve an action.
              </p>
            </div>
          ) : null}
          {task.dispositions?.map((review) => (
            <div
              className="border border-[var(--line)] p-2 my-2"
              key={review.id}
            >
              <p>
                Context inspected by {review.actor} ({review.role}) ·{" "}
                {formatUtc(review.reviewedAt)}
              </p>
              <p>
                Physical port {review.evidence.portCode}; source first available{" "}
                {formatUtc(review.evidence.firstAvailableAt)}.
              </p>
              <p className="break-all">
                Retained original: {review.evidence.sha256}
              </p>
              <p>
                Source claim: {review.sourceClaimStatus}. Actual execution:{" "}
                {review.actualExecutionStatus}. Real resolved targets added:{" "}
                {review.realResolvedTargetsAdded}.
              </p>
            </div>
          ))}
          <p>
            Missing inputs:{" "}
            {task.missingOperationalInputs.join(", ") ||
              "independent verification"}
            . Calculated delay: unavailable.
          </p>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all">
            {JSON.stringify(task, null, 2)}
          </pre>
        </details>
      ))}
    </details>
  );
}
