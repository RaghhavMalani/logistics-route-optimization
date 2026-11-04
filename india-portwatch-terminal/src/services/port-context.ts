import { z } from "zod";
import { getJson } from "./api";

export const contextMetricSchema = z
  .object({
    id: z.string(),
    value: z.number().nullish(),
    unit: z.string(),
    section: z.string(),
    precision: z.string(),
    asOf: z.string().optional(),
    dateScope: z
      .object({ date: z.string(), meaning: z.string() })
      .passthrough()
      .optional(),
    eligibility: z.string(),
    meaning: z.string(),
    pages: z.array(z.number()),
    oldestPossibleAgeHours: z.number().optional(),
  })
  .passthrough();
export const contextRuleSchema = z
  .object({
    id: z.string(),
    vesselId: z.string(),
    episodeId: z.string(),
    metricId: z.string(),
    portCode: z.string(),
    threshold: z.number(),
    declaredAt: z.string(),
    basis: z.string(),
  })
  .passthrough();
export const portContextSchema = z
  .object({
    sourceFamily: z.string(),
    policyVersion: z.string(),
    asOf: z.string(),
    status: z.string(),
    reason: z.string(),
    metrics: z.array(contextMetricSchema),
    reportDate: z.string().optional(),
    priorDayTrafficDate: z.string().optional(),
    publicationAt: z.string().nullish(),
    firstReceivedAt: z.string().optional(),
    availableAt: z.string().optional(),
    lastSuccessfulCheckAt: z.string().nullish(),
    originalSha256: z.string().optional(),
    originalStatus: z.string().optional(),
    snapshotId: z.string().optional(),
    revisionId: z.string().optional(),
    source: z.string().optional(),
    evidenceKind: z.string().optional(),
    scheduledSections: z.string().optional(),
    sourceUse: z.object({
      attribution: z.string(),
      scope: z.string(),
      policy: z.string(),
      fullDocumentDownload: z.boolean(),
    }),
  })
  .passthrough();
const responseSchema = z.object({
  refreshPending: z.boolean().optional(),
  context: portContextSchema,
  voyages: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      portCode: z.string(),
      episodeId: z.string().nullish(),
      rule: contextRuleSchema.nullish(),
    }),
  ),
});
export type PortContext = z.infer<typeof portContextSchema>;
export type PortContextRule = z.infer<typeof contextRuleSchema>;
export type PortContextSelection = {
  revisionId: string;
  ruleId: string;
  acknowledged: true;
};
export type FrozenPortContext = {
  evidenceKind?: string;
  sourceFamily?: string;
  originalSha256?: string | null;
  policyVersion?: string;
  revisionId: string;
  reportDate: string;
  metric: z.infer<typeof contextMetricSchema>;
  rule: PortContextRule;
  availableAt: string;
};
export async function getPortContext(
  headers: Record<string, string>,
  signal?: AbortSignal,
) {
  return responseSchema.parse(
    await getJson("/intelligence/port-context", headers, { signal }),
  );
}
