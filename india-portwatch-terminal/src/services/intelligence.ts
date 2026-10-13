import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { getJson, postJson } from "./api";

const location = z.object({
  lat: z.number().finite(),
  lon: z.number().finite(),
});
const correction = z
  .object({
    status: z.string(),
    sampleCount: z.number(),
    bias: z.number(),
    reason: z.string(),
    validationRawMae: z.number().nullable(),
    validationCorrectedMae: z.number().nullable(),
  })
  .passthrough();
const forecast = z
  .object({
    id: z.string(),
    portCode: z.string(),
    variable: z.string(),
    provider: z.string(),
    issuedAt: z.string(),
    validAt: z.string(),
    targetDate: z.string(),
    horizonDays: z.number(),
    unit: z.string(),
    original: z.number(),
    corrected: z.number(),
    low: z.number().nullable(),
    high: z.number().nullable(),
    observed: z.number().nullable(),
    observedAt: z.string().nullable(),
    observationSource: z.string().nullable(),
    status: z.enum(["open", "resolved"]),
    correction,
  })
  .passthrough();
const camera = z
  .object({
    id: z.string(),
    portCode: z.string(),
    name: z.string(),
    lat: z.number(),
    lon: z.number(),
    coverage: z.string(),
    viewpoint: z.string(),
    mediaUrl: z.string().url().nullable(),
    feedType: z.enum(["image", "mjpeg", "mp4", "webm", "hls"]),
    access: z.enum(["public", "port_authority"]),
    source: z.string(),
    rightsBasis: z.string(),
    enabled: z.boolean(),
    poseBasis: z.string(),
    health: z.string(),
    lastFrameAt: z.string().nullable(),
    healthNote: z.string(),
  })
  .passthrough();
export const intelligenceSchema = z.object({
  asOf: z.string(),
  clockMode: z.string(),
  selectedPort: z.string().nullable(),
  ports: z.array(
    z.object({ code: z.string(), name: z.string(), location }).passthrough(),
  ),
  news: z.object({
    status: z.string(),
    reason: z.string().nullable(),
    events: z.array(
      z
        .object({
          eventId: z.string(),
          title: z.string(),
          categoryLabel: z.string(),
          coordinates: location.nullable(),
          severity: z.number(),
          confidence: z.number(),
          firstSeen: z.string(),
          lastSeen: z.string(),
          sources: z.array(
            z
              .object({
                outlet: z.string(),
                url: z.string().nullable().optional(),
              })
              .passthrough(),
          ),
        })
        .passthrough(),
    ),
    impacts: z.array(
      z
        .object({
          eventId: z.string(),
          lanes: z.array(
            z
              .object({ laneName: z.string(), laneCode: z.string() })
              .passthrough(),
          ),
          ports: z.array(
            z
              .object({ portCode: z.string(), name: z.string().optional() })
              .passthrough(),
          ),
          actions: z.array(z.object({ label: z.string() }).passthrough()),
        })
        .passthrough(),
    ),
  }),
  economics: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      unit: z.string(),
      source: z.string().url(),
      shippingConnection: z.string(),
      status: z.string(),
      value: z.number().nullable(),
      changePct: z.number().nullable(),
      observedAt: z.string().nullable(),
      ageHours: z.number().nullable(),
    }),
  ),
  cameras: z.array(camera),
  cameraEvidence: z.array(
    z
      .object({
        id: z.string(),
        cameraId: z.string(),
        portCode: z.string(),
        observedAt: z.string(),
        coverage: z.string(),
        summary: z.string(),
        confidence: z.number(),
        method: z.string(),
        operationalUse: z.string(),
        source: z.string(),
      })
      .passthrough(),
  ),
  weatherFeedback: z
    .object({
      total: z.number(),
      resolved: z.number(),
      pending: z.number(),
      method: z.string(),
      note: z.string(),
      forecasts: z.array(forecast),
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
        }),
      ),
    })
    .passthrough(),
  integration: z.object({
    name: z.string(),
    repository: z.string().url(),
    revision: z.string(),
    codeLicence: z.string(),
    implemented: z.array(z.string()),
    pending: z.array(z.string()),
  }),
});
export type IntelligenceContext = z.infer<typeof intelligenceSchema>;
export type PortCamera = z.infer<typeof camera>;
export type WeatherInspection = z.infer<typeof forecast>;

export function useIntelligence(
  port: string | null,
  headers: Record<string, string>,
  variable = "wind_speed",
  clockKey = "unknown",
) {
  return useQuery({
    queryKey: ["intelligence", port, headers, variable, clockKey],
    queryFn: async ({ signal }) => {
      const body = await getJson<unknown>(
        `/intelligence/context?weatherVariable=${encodeURIComponent(variable)}${port ? `&portCode=${encodeURIComponent(port)}` : ""}`,
        headers,
        { signal },
      );
      const parsed = intelligenceSchema.safeParse(body);
      if (!parsed.success)
        throw new Error(
          `Intelligence response does not match the API contract: ${parsed.error.issues[0]?.path.join(".")}`,
        );
      return parsed.data;
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useRegisterCamera(headers: Record<string, string>) {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      postJson("/intelligence/cameras", body, headers),
    onSuccess: () =>
      void queries.invalidateQueries({ queryKey: ["intelligence"] }),
  });
}
