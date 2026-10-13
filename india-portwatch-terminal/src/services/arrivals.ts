import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { getJson, postJson } from "./api";

const prediction = z
  .object({
    status: z.string(),
    value: z.number().nullable(),
    low: z.number().nullable(),
    high: z.number().nullable(),
    modelVersion: z.string(),
    intervalNominal: z.number().nullable(),
    missing: z.array(z.string()),
  })
  .passthrough();
const event = z.object({
  kind: z.string(),
  actor: z.string(),
  recordedAt: z.string(),
  body: z.record(z.string(), z.unknown()),
});
const operation = z.object({
  operationId: z.string(),
  operationRef: z.string(),
  mmsi: z.string(),
  vesselName: z.string(),
  recipientOrganisation: z.string(),
  plannedArrivalAt: z.string(),
  issuedAt: z.string(),
  baselineWaitHours: z.number(),
  baselineSource: z.string(),
  baselineRef: z.string().nullable().optional(),
  baselineEstimatedAt: z.string().nullable().optional(),
  baselineAvailableAt: z.string().nullable().optional(),
  cohortId: z.string().nullable().optional(),
  disposition: z
    .object({ reason: z.string(), source: z.string() })
    .passthrough()
    .nullable(),
  routeRevision: z.string().nullable().optional(),
  decisionId: z.string(),
  predictionId: z.string().nullable(),
  recommendation: z.string(),
  prediction,
  missingEvidence: z.array(z.string()),
  approved: z.boolean(),
  events: z.array(event),
  evidence: z.object({
    weather: z.array(
      z.object({
        id: z.string(),
        variable: z.string(),
        original: z.number(),
        consumed: z.number(),
        unit: z.string(),
        issuedAt: z.string(),
        validAt: z.string(),
        recordedAt: z.string(),
        availableAt: z.string(),
        source: z.string(),
      }),
    ),
    tracks: z.array(
      z.object({
        id: z.string(),
        mmsi: z.string(),
        observedAt: z.string(),
        availableAt: z.string(),
        recordedAt: z.string(),
        lat: z.number(),
        lon: z.number(),
        source: z.string(),
        rawRef: z.string(),
      }),
    ),
    matchRationale: z.string(),
    camera: z.object({ status: z.string(), reason: z.string() }),
  }),
  advisoryId: z.string().nullable(),
  advisory: z
    .object({
      id: z.string(),
      state: z.string(),
      audit: z.array(
        z
          .object({ at: z.string(), actor: z.string(), to_state: z.string() })
          .passthrough(),
      ),
    })
    .nullable(),
  actualAction: z
    .object({
      actualAction: z.string(),
      actionState: z.string(),
      occurredAt: z.string(),
      availableAt: z.string(),
      source: z.string(),
    })
    .nullable(),
  outcome: z
    .object({
      waitHours: z.number(),
      arrivedAt: z.string(),
      berthedAt: z.string(),
      availableAt: z.string(),
      recordedAt: z.string(),
      source: z.string(),
      berthRef: z.string(),
      sourceRef: z.string().nullable().optional(),
      arrivalAvailableAt: z.string().nullable().optional(),
      allFastAvailableAt: z.string().nullable().optional(),
    })
    .nullable(),
  errorHours: z.number().nullable(),
  withinInterval: z.boolean().nullable(),
});
const benchmark = z
  .object({
    status: z.string(),
    modelVersion: z.string(),
    datasetHash: z.string(),
    fitCount: z.number(),
    calibrationCount: z.number(),
    holdoutCount: z.number(),
    fitThrough: z.string(),
    calibrationFrom: z.string(),
    calibrationThrough: z.string(),
    holdoutFrom: z.string(),
    holdoutThrough: z.string(),
    gbmMaeHours: z.number(),
    baselineMaeHours: z.number(),
    historicalMedianMaeHours: z.number(),
    intervalCoverage: z.number(),
    promotion: z.string(),
    limitations: z.string(),
    metrics: z
      .record(
        z.string(),
        z.object({
          maeHours: z.number(),
          signedBiasHours: z.number(),
          intervalCoverage: z.number(),
        }),
      )
      .optional(),
    incrementalValue: z
      .object({
        weatherAndAisMaeReductionHours: z.number(),
        weatherGivenAisMaeReductionHours: z.number(),
        aisGivenWeatherMaeReductionHours: z.number(),
        interpretation: z.string(),
      })
      .optional(),
  })
  .passthrough();
const workspace = z.object({
  portCode: z.string(),
  asOf: z.string(),
  operations: z.array(operation),
  measuredCount: z.number(),
  evaluationEligibleCount: z.number(),
  reason: z.string(),
  target: z.string(),
  cameraStatus: z.string(),
  benchmark: benchmark.nullable(),
  collection: z.object({
    cohort: z
      .object({
        cohortId: z.string(),
        startedAt: z.string(),
        status: z.string(),
        protocolHash: z.string(),
      })
      .nullable(),
    enrolledCount: z.number(),
    confirmedCount: z.number(),
    qualifyingCount: z.number(),
    unresolvedCount: z.number(),
    overdueCount: z.number(),
    missingEvidenceCount: z.number(),
    staleAisCount: z.number(),
    duplicateCandidateCount: z.number(),
    excludedCount: z.number(),
    evaluationReady: z.boolean(),
    gateReason: z.string(),
    aisArchiveStatus: z.string(),
    latestAisObservedAt: z.string().nullable(),
    partitions: z
      .object({
        fit: z.number(),
        calibration: z.number(),
        holdout: z.number(),
        purged: z.number(),
      })
      .nullable(),
    calls: z.array(
      z.object({
        operationId: z.string(),
        operationRef: z.string(),
        flags: z.array(z.string()),
        qualifying: z.boolean(),
      }),
    ),
  }),
  publicEvidence: z
    .object({
      reportDate: z.string(),
      retrievedAt: z.string(),
      source: z.string(),
      records: z.array(
        z.object({
          operationRef: z.string(),
          vesselName: z.string(),
          terminal: z.string(),
          berthRef: z.string(),
          reportedBerthedOn: z.string(),
          status: z.string(),
        }),
      ),
    })
    .nullable(),
});
export type ArrivalOperation = z.infer<typeof operation>;
export type ArrivalWorkspace = z.infer<typeof workspace>;

export function useArrivals(
  portCode: string,
  clockKey: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["arrivals", portCode, clockKey],
    enabled,
    queryFn: async ({ signal }) =>
      workspace.parse(
        await getJson(
          `/arrivals/workspace?portCode=${encodeURIComponent(portCode)}`,
          {},
          { signal },
        ),
      ),
    staleTime: 15_000,
  });
}
export const arrivalWrite = (path: string, body: unknown = {}) =>
  postJson(`/arrivals/${path}`, body);
