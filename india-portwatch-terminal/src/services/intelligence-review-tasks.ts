import { z } from "zod";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson } from "@/services/api";

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
        vesselId: z.string(),
        taskQuestion: z.string().optional(),
        source: z
          .object({
            operationalEvidence: z
              .object({ portCode: z.string() })
              .passthrough()
              .optional(),
          })
          .passthrough()
          .optional(),
        dispositions: z
          .array(
            z
              .object({
                id: z.string(),
                type: z.literal("CONTEXT_REVIEWED"),
                reviewedAt: z.string(),
                actor: z.string(),
                role: z.string(),
                sourceClaimStatus: z.string(),
                actualExecutionStatus: z.string(),
                realResolvedTargetsAdded: z.literal(0),
                evidence: z
                  .object({
                    sha256: z.string(),
                    firstAvailableAt: z.string(),
                    portCode: z.string(),
                  })
                  .passthrough(),
              })
              .passthrough(),
          )
          .optional(),
      })
      .passthrough(),
  ),
});

export function useIntelligenceReviewTasks() {
  const { session, identityHeaders } = useAuth();
  return useQuery({
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
}
