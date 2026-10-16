import { z } from "zod";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson } from "@/services/api";
import { formatUtc } from "@/components/kit/primitives";

const tasksSchema = z.object({
  tasks: z.array(
    z
      .object({
        id: z.string(),
        kind: z.literal("SOURCE_EXPOSURE_VERIFICATION_TASK"),
        status: z.string(),
        createdAt: z.string(),
        reason: z.string(),
        missingOperationalInputs: z.array(z.string()),
        calculatedDelayHours: z.null(),
        createsOperationalTarget: z.literal(false),
      })
      .passthrough(),
  ),
});

export function IntelligenceReviewTasks() {
  const { session, identityHeaders } = useAuth();
  const q = useQuery({
    queryKey: ["intelligence-review-tasks", identityHeaders],
    queryFn: async ({ signal }) => {
      const raw = await getJson<unknown>(
        "/intelligence/review-tasks",
        identityHeaders,
        { signal },
      );
      const parsed = tasksSchema.safeParse(raw);
      if (!parsed.success)
        throw new Error(
          "Review-task response is malformed; retained records are unavailable.",
        );
      return parsed.data;
    },
    enabled: session?.mode === "demo",
    staleTime: 15000,
  });
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
