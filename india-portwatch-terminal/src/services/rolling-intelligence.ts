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
