import { z } from "zod";

/** Semantic role of a product's time coverage, separate from fetch freshness. */
export const SourceTemporalRoleSchema = z.enum([
  "CURRENT",
  "HISTORICAL",
  "FORECAST",
  "MIXED",
  "UNKNOWN",
]);
export type SourceTemporalRole = z.infer<typeof SourceTemporalRoleSchema>;

export const SourceValueKindSchema = z.enum([
  "OBSERVED",
  "FORECAST",
  "DERIVED",
  "ASSUMED",
  "SIMULATED",
  "UNKNOWN",
]);
export type SourceValueKind = z.infer<typeof SourceValueKindSchema>;

export const SourceOperationalUseSchema = z.enum([
  "CONTEXT_ONLY",
  "CALCULATION_INPUT",
  "SCENARIO_ASSUMPTION",
  "REVIEWED_OUTCOME",
  "UNKNOWN",
]);
export type SourceOperationalUse = z.infer<
  typeof SourceOperationalUseSchema
>;

const nullableDate = z.string().nullable();
const nullableNonNegative = z.number().finite().nonnegative().nullable();

/**
 * Additive presentation contract for source quality. Missing facts stay null
 * with an explanation; this shape does not infer quality from row counts.
 */
export const SourceQualitySchema = z
  .object({
    schemaVersion: z.literal(1),
    temporalRole: SourceTemporalRoleSchema,
    valueKinds: z.array(SourceValueKindSchema).min(1),
    operationalUse: SourceOperationalUseSchema,
    receipt: z.object({
      lastFetchedAt: nullableDate,
      lastCheckedAt: nullableDate,
      ageSeconds: nullableNonNegative,
      freshnessBudgetSeconds: nullableNonNegative,
      status: z.enum([
        "LIVE",
        "CACHED_LIVE",
        "STALE",
        "SYNTHETIC",
        "UNAVAILABLE",
      ]),
      fallback: z.string().nullable(),
    }),
    coverage: z.object({
      portCodes: z.array(z.string()).nullable(),
      variables: z.array(z.string()).nullable(),
      observedFrom: nullableDate,
      observedThrough: nullableDate,
      forecastOriginAt: nullableDate,
      targetFrom: nullableDate,
      targetThrough: nullableDate,
      datePrecision: z.enum(["INSTANT", "DATE_ONLY", "UNKNOWN"]),
    }),
    provenance: z.object({
      provider: z.string().nullable(),
      sourceProductId: z.string().nullable(),
      sourceReceiptId: z.string().nullable(),
      originalRef: z.string().nullable(),
      originalHash: z.string().nullable(),
      derivationVersion: z.string().nullable(),
    }),
    quality: z.object({
      rowCount: nullableNonNegative,
      confidence: z.number().finite().min(0).max(1).nullable(),
      completeness: z.number().finite().min(0).max(1).nullable(),
      missingFields: z.array(z.string()),
      issues: z.array(z.string()),
    }),
    unknownReasons: z.array(z.string()),
  })
  .passthrough();

export type SourceQualityDTO = z.infer<typeof SourceQualitySchema>;

export type SourceQualityParseResult =
  | { ok: true; value: SourceQualityDTO }
  | { ok: false; reason: string };

export function parseSourceQuality(value: unknown): SourceQualityParseResult {
  const parsed = SourceQualitySchema.safeParse(value);
  if (parsed.success) return { ok: true, value: parsed.data };
  const firstIssue = parsed.error.issues[0];
  return {
    ok: false,
    reason: firstIssue
      ? `${firstIssue.path.join(".") || "source quality"}: ${firstIssue.message}`
      : "Source quality metadata is malformed.",
  };
}
