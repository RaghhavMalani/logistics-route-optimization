import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { getJson } from "./api";

const number = z.number().finite().nullable();
const model = z
  .object({
    model: z.string(),
    n: z.number(),
    mae: z.number(),
    rmse: z.number(),
    signed_bias: number.optional(),
    coverage_80pct: number.optional(),
    interval_width: number.optional(),
    horizon_day: z.number().optional(),
    mae_change_vs_full_gbm: number.optional(),
  })
  .passthrough();
const exploreSchema = z.object({
  asOf: z.string(),
  readOnly: z.literal(true),
  eventStatus: z.string(),
  eventReason: z.string().nullable(),
  limits: z.string(),
  sources: z.array(
    z.object({
      name: z.string(),
      url: z.string(),
      status: z.string(),
      collectedAt: z.string().nullable(),
      observedAt: z.string().nullable(),
    }),
  ),
  simulation: z.object({
    meaning: z.string(),
    defaultSpeedKn: z.number(),
    defaultDailyCostUsd: z.number(),
    speedRangeKn: z.array(z.number()),
  }),
  events: z.array(
    z.object({
      eventId: z.string(),
      title: z.string(),
      categoryLabel: z.string(),
      region: z.string().nullable(),
      firstSeen: z.string(),
      lastSeen: z.string(),
      severity: z.number(),
      confidence: z.number(),
      confidenceMeaning: z.string(),
      status: z.string(),
      sources: z.array(
        z.object({
          url: z.string().nullable(),
          outlet: z.string().nullable().optional(),
          publishedAt: z.string().nullable().optional(),
        }),
      ),
      ports: z.array(
        z.object({
          portCode: z.string(),
          portName: z.string(),
          exposure: z.number(),
        }),
      ),
      lanes: z.array(
        z.object({
          laneCode: z.string(),
          laneName: z.string(),
          detourNm: number,
          alternative: z.string().nullable(),
          indiaPorts: z.array(z.string()),
        }),
      ),
    }),
  ),
  ports: z.array(
    z.object({
      code: z.string(),
      name: z.string(),
      observedAt: z.string().nullable(),
      congestionIndex: number,
      delayMeaning: z.string(),
      forecastTarget: z.string(),
      forecasts: z.array(
        z.object({
          day: z.number(),
          targetDate: z.string(),
          originDate: z.string(),
          q10: number,
          q50: number,
          q90: number,
          delayHoursP50: number,
          source: z.string().nullable(),
          status: z.string(),
        }),
      ),
    }),
  ),
});
const researchSchema = z.object({
  available: z.boolean(),
  reason: z.string().optional(),
  releaseId: z.string().optional(),
  generatedAt: z.string().optional(),
  evaluationProtocol: z.string().optional(),
  unit: z.string().optional(),
  target: z.string().optional(),
  datasetMeaning: z.string().optional(),
  models: z.array(model).default([]),
  horizons: z.array(model).default([]),
  ablations: z.array(model).default([]),
  series: z
    .array(
      z.object({
        model: z.string(),
        target_date: z.string(),
        horizon_day: z.number(),
        observed: z.number(),
        predicted: z.number(),
        low: number,
        high: number,
        samples: z.number(),
      }),
    )
    .default([]),
  partitions: z
    .object({
      weightFitThrough: z.string(),
      calibrationFrom: z.string(),
      calibrationThrough: z.string(),
      holdoutFrom: z.string(),
      holdoutThrough: z.string(),
    })
    .optional(),
  reproducibility: z
    .object({
      datasetRows: z.number(),
      datasetSha256: z.string(),
      forecastCodeSha256: z.string(),
      codeRevision: z.string().nullable(),
      dependencies: z.record(z.string().nullable()),
      configuration: z.record(z.unknown()),
    })
    .optional(),
  calibration: z
    .object({
      models: z.record(
        z.array(
          z.object({
            nominal: z.number(),
            empirical: z.number(),
            error: z.number(),
            meanWidth: z.number(),
          }),
        ),
      ),
    })
    .optional(),
  limits: z.array(z.string()).default([]),
  downloads: z.array(
    z.object({ name: z.string(), sha256: z.string(), bytes: z.number() }),
  ),
  weather: z.object({
    available: z.boolean().default(true),
    version: z.string(),
    total: number,
    resolved: number,
    pending: number,
    method: z.string(),
    note: z.string(),
    scores: z.array(
      z.object({
        portCode: z.string(),
        variable: z.string(),
        provider: z.string(),
        horizonDays: z.number(),
        unit: z.string(),
        samples: z.number(),
        rawMae: z.number(),
        correctedMae: z.number(),
        rawBias: z.number(),
        correctedBias: z.number(),
      }),
    ),
  }),
  operational: z.object({
    available: z.boolean().default(true),
    reason: z.string().optional(),
    meaning: z.string(),
    ports: z.array(
      z.object({
        portCode: z.string(),
        frozen: z.number(),
        matchedArrivals: z.number(),
        complete: z.number(),
        ambiguous: z.number(),
        pending: z.number(),
        lastSuccessfulCollectionAt: z.string().nullable(),
        collectionFailed: z.boolean(),
      }),
    ),
  }),
  simulationMeaning: z.string(),
});
export type PublicExplore = z.infer<typeof exploreSchema>;
export type PublicResearch = z.infer<typeof researchSchema>;
const publicCallsSchema = z.object({
  available: z.boolean(),
  asOf: z.string(),
  meaning: z.string(),
  ports: z.array(
    z.object({
      portCode: z.string(),
      frozen: z.number(),
      matched: z.number(),
      waitingOutcomes: z.number(),
      pending: z.number(),
      ambiguous: z.number(),
      excludedRecords: z.number(),
      lastSuccessfulCollectionAt: z.string().nullable(),
      lastRunStartedAt: z.string().nullable(),
      collectionDelayMinutes: number,
      expectedCollectionAt: z.string().nullable(),
      freshness: z.string(),
      collectionFailed: z.boolean(),
      parserIssues: z.array(
        z.object({
          code: z.string(),
          page: z.number().nullable(),
          candidates: z.array(z.string()),
          reportDate: z.string().nullable(),
          url: z.string().startsWith("/api/public/port-calls/"),
        }),
      ),
    }),
  ),
  cases: z.array(
    z.object({
      caseId: z.string(),
      archivedPublication: z.boolean().optional(),
      publishedAt: z.string().optional(),
      portCode: z.string(),
      vesselName: z.string(),
      berthRef: z.string(),
      identity: z.object({
        loaMetres: z.number(),
        beamMetres: number,
        mmsi: z.null(),
        basis: z.string(),
      }),
      publishedEtaBaselineErrorMinutes: z.number(),
      reportedWaitingHours: z.number(),
      uncertainty: z.string(),
      meaning: z.string(),
      timezoneNote: z.string(),
      review: z.object({
        status: z.literal("PASSED"),
        reviewedAt: z.string(),
        preparedAt: z.string(),
      }),
      auditUrl: z.string().startsWith("/api/public/port-calls/"),
      events: z.array(
        z.object({
          event: z.enum(["frozenEta", "reportedArrival", "reportedBerth"]),
          at: z.string(),
          rawClock: z.string(),
          availableAt: z.string(),
          firstSeenAt: z.string(),
          reportDate: z.string(),
          page: z.number(),
          sha256: z.string(),
          url: z.string().startsWith("/api/public/port-calls/"),
          sourceUrl: z.string().url(),
          parserVersion: z.string(),
          parsedAt: z.string(),
        }),
      ),
    }),
  ),
});
export type PublicCalls = z.infer<typeof publicCallsSchema>;
export const publicEvidenceUrl = (path: string) =>
  `${(import.meta.env.VITE_PORTWATCH_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "/api"}${path.slice(4)}`;
export function usePublicCalls() {
  return useQuery({
    queryKey: ["public-port-calls"],
    queryFn: async ({ signal }) =>
      publicCallsSchema.parse(
        await getJson<unknown>("/public/port-calls", {}, { signal }),
      ),
    staleTime: 60_000,
    retry: 1,
  });
}
export const resultUrl = (name: string, releaseId?: string) =>
  `${(import.meta.env.VITE_PORTWATCH_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "/api"}/public/research/download/${encodeURIComponent(name)}${releaseId ? `?releaseId=${encodeURIComponent(releaseId)}` : ""}`;
export function usePublicExplore() {
  return useQuery({
    queryKey: ["public-explore"],
    queryFn: async ({ signal }) =>
      exploreSchema.parse(
        await getJson<unknown>("/public/explore", {}, { signal }),
      ),
    staleTime: 60_000,
    retry: 1,
  });
}
export function usePublicResearch() {
  return useQuery({
    queryKey: ["public-research"],
    queryFn: async ({ signal }) =>
      researchSchema.parse(
        await getJson<unknown>("/public/research", {}, { signal }),
      ),
    staleTime: 60_000,
    retry: 1,
  });
}
