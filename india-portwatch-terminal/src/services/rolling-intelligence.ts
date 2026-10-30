import { z } from "zod";
import { getJson } from "./api";

const passageSchema = z
  .object({
    id: z.string(),
    areaId: z.string(),
    sourceFamily: z.string(),
    passageAt: z.string(),
    postPassageHours: z.number().finite(),
  })
  .passthrough();
export const noticeSchema = z
  .object({
    noticeId: z.string(),
    providerNoticeId: z.string().optional(),
    noticeRef: z.string(),
    source: z.string(),
    sourceFamily: z.string(),
    title: z.string().optional(),
    areaId: z.string().nullish(),
    sourceStatus: z.string(),
    status: z.string().optional(),
    extractionStatus: z.string().optional(),
    calculationSupported: z.boolean().optional(),
    revisionId: z.string().optional(),
    availableAt: z.string().nullish(),
    checkedAt: z.string(),
    reason: z.string().nullish(),
    providerCreatedAt: z.string().nullish(),
    providerModifiedAt: z.string().nullish(),
    publicationPrecision: z.string().nullish(),
    extractionMode: z.string().optional(),
    sourceFirstReceivedAt: z.string().nullish(),
    extractedAt: z.string().nullish(),
    restriction: z.string().nullish(),
    unaffectedAlternative: z.string().nullish(),
    confirmation: z.string().nullish(),
    originalWording: z.string().optional(),
    responseSha256: z.string().optional(),
    coordinates: z
      .object({
        lat: z.number().finite().min(-90).max(90),
        lon: z.number().finite().min(-180).max(180),
        basis: z.string(),
      })
      .nullish(),
    windows: z.array(
      z.object({
        start: z.string(),
        end: z.string(),
        localDate: z.string(),
        localStart: z.string(),
        localEnd: z.string(),
        timeZone: z.string(),
        timeZoneBasis: z.string(),
      }),
    ),
  })
  .passthrough();
export const exposureSchema = z
  .object({
    noticeId: z.string(),
    title: z.string(),
    vesselId: z.string(),
    vesselName: z.string(),
    assetId: z.string().nullish(),
    assetName: z.string().nullish(),
    status: z.string(),
    sourceStatus: z.string(),
    sourceValidity: z.string().optional(),
    reason: z.string(),
    missingInputs: z.array(z.string()),
    calculable: z.boolean(),
    calculationReason: z.string(),
    passageAt: z.string().nullish(),
    priority: z.object({
      rank: z.number(),
      score: z.number(),
      label: z.string(),
      reason: z.string(),
      hoursToDeclaredPassage: z.number().nullish(),
    }),
  })
  .passthrough();
export const rollingSchema = z
  .object({
    sourceStatus: z.string(),
    checkedAt: z.string(),
    meaning: z.string(),
    notices: z.array(noticeSchema),
    voyages: z.array(
      z
        .object({
          id: z.string(),
          name: z.string(),
          portCode: z.string(),
          cargo: z.string(),
          operationalEpisode: z
            .object({ id: z.string(), voyageLegId: z.string() })
            .nullish(),
          declaredPassage: passageSchema.nullish(),
          declaredPassages: z.record(passageSchema).nullish(),
        })
        .passthrough(),
    ),
    exposureQueue: z.array(exposureSchema),
    sourceRegistry: z.unknown().optional(),
  })
  .passthrough();
export type NavigationNotice = z.infer<typeof noticeSchema>;
export type VoyageExposure = z.infer<typeof exposureSchema>;

export async function getRollingIntelligence(
  headers: Record<string, string>,
  signal?: AbortSignal,
) {
  const raw = await getJson<unknown>(
    "/intelligence/navigation-restrictions",
    headers,
    { signal, timeoutMs: 60000 },
  );
  const result = rollingSchema.safeParse(raw);
  if (!result.success)
    throw new Error(
      "The notice catalogue response is incomplete or malformed; numerical actions are unavailable.",
    );
  return result.data;
}

export function reviewSelection() {
  if (typeof window === "undefined") return {};
  const prefix = "#intelligence-review?";
  if (!window.location.hash.startsWith(prefix)) return {};
  const params = new URLSearchParams(window.location.hash.slice(prefix.length));
  return {
    noticeId: params.get("noticeId") ?? "",
    vesselId: params.get("vesselId") ?? "",
  };
}

export function reviewHash(noticeId: string, vesselId: string) {
  return `intelligence-review?${new URLSearchParams({ noticeId, vesselId })}`;
}

export const FLEET_TRIAGE_CATEGORIES = [
  "CURRENT_CONDITIONAL_FAILURE",
  "REASSESSMENT",
  "COMPANY_ACTION",
  "WAITING_OTHER_ROLE",
  "INCOMPLETE_ASSESSMENT",
  "MONITORED",
] as const;
export type FleetTriageCategory = (typeof FLEET_TRIAGE_CATEGORIES)[number];

const triageReasonSchema = z.object({
  code: z.string(),
  text: z.string(),
  basis: z.string(),
  evidenceId: z.string().nullish(),
  decisionId: z.string().nullish(),
  optionId: z.string().nullish(),
});
const comparisonLinkSchema = z
  .object({
    decisionId: z.string(),
    optionId: z.string().nullish(),
    basis: z.string().optional(),
    workflow: z.string().optional(),
  })
  .passthrough();
export const fleetTriageSchema = z
  .object({
    policyVersion: z.string(),
    asOf: z.string(),
    counts: z.record(z.number().int().nonnegative()),
    coverage: z
      .object({
        ownedVoyages: z.number().int().nonnegative(),
        currentCalls: z.number().int().nonnegative(),
        assessedCurrentPlans: z.number().int().nonnegative(),
        retainedComparisons: z.number().int().nonnegative(),
        legacyComparisons: z.number().int().nonnegative(),
        snapshotConsistent: z.boolean(),
      })
      .passthrough(),
    rows: z.array(
      z.object({
        id: z.string(),
        vessel: z.object({ id: z.string(), name: z.string() }),
        destinationPort: z.string().nullish(),
        episode: z
          .object({ id: z.string(), voyageLegId: z.string().nullish() })
          .nullish(),
        currentPlan: z.object({
          basis: z.enum([
            "APPROVED",
            "BASELINE_NOT_APPROVED",
            "MISSING",
            "AMBIGUOUS",
          ]),
          decisionId: z.string().nullish(),
          optionId: z.string().nullish(),
          approvalStatus: z.string().nullish(),
        }),
        recommendation: comparisonLinkSchema.nullish(),
        workflow: z.object({
          stage: z.string(),
          nextRole: z.string().nullish(),
          companyDecisionId: z.string().nullish(),
          portDecisionId: z.string().nullish(),
          advisoryIds: z.array(z.string()),
        }),
        primaryCategory: z.enum(FLEET_TRIAGE_CATEGORIES),
        reasons: z.array(triageReasonSchema),
        freshness: z.object({
          status: z.string(),
          reasons: z.array(triageReasonSchema),
        }),
        deadline: z
          .object({
            at: z.string(),
            kind: z.string(),
            hoursRemaining: z.number().finite(),
            basis: z.string(),
          })
          .nullish(),
        cargo: z
          .object({
            mustMeet: z.boolean(),
            status: z.string(),
            timingStatus: z.string().nullish(),
            slackHours: z.number().finite().nullish(),
            cutoffAt: z.string().nullish(),
            unit: z.literal("hours"),
            basis: z.string(),
          })
          .nullish(),
        navigation: z.object({
          kind: z.enum(["SAVED_COMPARISON", "CURRENT_INPUTS"]),
          vesselId: z.string(),
          decisionId: z.string().nullish(),
          optionId: z.string().nullish(),
          episodeId: z.string().nullish(),
        }),
        candidateComparisons: z.array(comparisonLinkSchema),
        missingCoverage: z.array(z.string()),
        asOf: z.string(),
      }),
    ),
    sourceLeads: z.array(exposureSchema).optional(),
    sourceLeadCoverage: z
      .object({
        status: z.string(),
        checkedAt: z.string().nullish(),
        reason: z.string(),
      })
      .optional(),
  })
  .passthrough();

export type FleetDecisionTriage = z.infer<typeof fleetTriageSchema>;
export type FleetDecisionRow = FleetDecisionTriage["rows"][number];

/** A retained-state projection. It never calls the provider-refresh listing. */
export async function getFleetDecisionTriage(
  headers: Record<string, string>,
  signal?: AbortSignal,
) {
  const raw = await getJson<unknown>("/company/decision-triage", headers, {
    signal,
    timeoutMs: 30000,
  });
  const parsed = fleetTriageSchema.safeParse(raw);
  if (!parsed.success)
    throw new Error(
      "Fleet review projection is incomplete or malformed; current plan status is unavailable.",
    );
  return parsed.data;
}

export interface FleetReviewSelection {
  kind: "SAVED_COMPARISON" | "CURRENT_INPUTS";
  vesselId: string;
  decisionId: string;
  optionId: string;
  episodeId: string;
}

export function fleetReviewSelection(
  hash: string,
): FleetReviewSelection | null {
  const saved = hash.startsWith("#fleet-review?");
  const inputs = hash.startsWith("#current-inputs?");
  if (!saved && !inputs) return null;
  const params = new URLSearchParams(hash.slice(hash.indexOf("?") + 1));
  return {
    kind: saved ? "SAVED_COMPARISON" : "CURRENT_INPUTS",
    vesselId: params.get("vesselId") ?? "",
    decisionId: params.get("decisionId") ?? "",
    optionId: params.get("optionId") ?? "",
    episodeId: params.get("episodeId") ?? "",
  };
}

export function fleetReviewHash(selection: {
  kind: "SAVED_COMPARISON" | "CURRENT_INPUTS";
  vesselId: string;
  decisionId?: string | null;
  optionId?: string | null;
  episodeId?: string | null;
}) {
  const params = new URLSearchParams({ vesselId: selection.vesselId });
  for (const field of ["decisionId", "optionId", "episodeId"] as const) {
    if (selection[field]) params.set(field, selection[field]);
  }
  return `${selection.kind === "SAVED_COMPARISON" ? "fleet-review" : "current-inputs"}?${params}`;
}
