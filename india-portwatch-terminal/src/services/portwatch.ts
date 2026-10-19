/**
 * Typed endpoints for every screen in the terminal.
 *
 * One module, one contract. There is no parallel set of local "service" files
 * shadowing these with static demo objects any more -- if a value appears on
 * screen, it came through one of these calls.
 */

import { getJson, postJson } from "./api";
import type {
  Benchmark,
  Decision,
  FeedAdapter,
  FleetRow,
  ForecastPoint,
  Health,
  IntelligenceChain,
  NewsBundle,
  PipelineNode,
  PortRegistryEntry,
  PortSnapshot,
  Provenance,
  RegimeState,
  ScenarioDefinition,
  ScenarioResult,
  VesselBundle,
  WeatherIntelligence,
  WeatherSignal,
} from "@/types/portwatch";
import {
  PortRegistryQualityResponseSchema,
  parseSourceQuality,
} from "@/types/source-quality";

/* --------------------------------------------------------------- system --- */

export const fetchHealth = () => getJson<Health>("/health");
export async function fetchProvenance(): Promise<Provenance> {
  const provenance = await getJson<Provenance>("/provenance");
  const sources = Object.fromEntries(
    Object.entries(provenance.sources ?? {}).map(([key, source]) => {
      if (source.sourceQuality == null) return [key, source];
      const parsed = parseSourceQuality(source.sourceQuality);
      return [
        key,
        parsed.ok
          ? { ...source, sourceQuality: parsed.value, sourceQualityError: null }
          : {
              ...source,
              sourceQuality: null,
              sourceQualityError: parsed.reason,
            },
      ];
    }),
  );
  return { ...provenance, sources };
}

/* ---------------------------------------------------------------- ports --- */

export const fetchPorts = () => getJson<PortSnapshot[]>("/ports");
export const fetchPort = (code: string) =>
  getJson<PortSnapshot>(`/ports/${encodeURIComponent(code)}`);
export async function fetchPortRegistry(): Promise<PortRegistryEntry[]> {
  const response = await getJson<unknown>("/ports/registry");
  const parsed = PortRegistryQualityResponseSchema.safeParse(response);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    throw new Error(
      `Port registry response rejected: ${issue?.path.join(".") || "response"}: ${issue?.message ?? "invalid response"}`,
    );
  }
  return parsed.data;
}

/* ---------------------------------------------------------------- model --- */

export const fetchPipeline = () => getJson<PipelineNode[]>("/model/pipeline");
export const fetchBenchmark = () => getJson<Benchmark>("/model/benchmark");
export const fetchModelPorts = () => getJson<string[]>("/model/ports");
export const fetchForecast = (code: string) =>
  getJson<ForecastPoint[]>(`/model/${encodeURIComponent(code)}/forecast`);
export const fetchRegime = (code: string) =>
  getJson<RegimeState>(`/model/${encodeURIComponent(code)}/regime`);
export const fetchDecision = (code: string) =>
  getJson<Decision>(`/model/${encodeURIComponent(code)}/decision`);
export const fetchChain = (code: string) =>
  getJson<IntelligenceChain>(`/model/${encodeURIComponent(code)}/chain`);

/* -------------------------------------------------------------- weather --- */

export const fetchWeather = () => getJson<WeatherSignal[]>("/weather");
export const fetchWeatherForPort = (code: string) =>
  getJson<WeatherSignal>(`/weather/${encodeURIComponent(code)}`);
export const fetchWeatherIntelligence = () =>
  getJson<WeatherIntelligence>("/weather/intelligence");

/* ----------------------------------------------------------------- news --- */

export const fetchNews = () => getJson<NewsBundle>("/news");
export const fetchNewsForEntity = (entity: string) =>
  getJson<Pick<NewsBundle, "events" | "alerts" | "sentiment">>(
    `/news/entity/${encodeURIComponent(entity)}`,
  );

/* -------------------------------------------------------------- vessels --- */

export const fetchVessels = () => getJson<VesselBundle>("/sar/vessels");
export const fetchFeedAdapters = () =>
  getJson<FeedAdapter[]>("/sar/feed-adapters");
export const fetchFleet = () => getJson<FleetRow[]>("/fleet");

/* ------------------------------------------------------------ scenarios --- */

export const fetchScenarios = () => getJson<ScenarioDefinition[]>("/scenarios");

export const runScenario = (
  scenarioKey: string,
  intensity: number,
  runId: number,
) =>
  postJson<ScenarioResult>("/scenarios/simulate", {
    scenarioKey,
    intensity,
    runId,
  });

/* ------------------------------------------------------------ composite --- */

export interface RadarOverview {
  health: Health;
  ports: PortSnapshot[];
  vessels: VesselBundle;
  weather: WeatherSignal[];
  news: NewsBundle;
}

/**
 * The national radar's single fetch. Everything on that screen comes from these
 * five calls; a failure in any of them surfaces rather than being swallowed.
 */
export async function fetchRadarOverview(): Promise<RadarOverview> {
  const [health, ports, vessels, weather, news] = await Promise.all([
    fetchHealth(),
    fetchPorts(),
    fetchVessels(),
    fetchWeather().catch(() => [] as WeatherSignal[]),
    fetchNews().catch(
      () =>
        ({
          events: [],
          alerts: [],
          sentiment: [],
          summary: {
            totalEvents: 0,
            totalAlerts: 0,
            severeEvents: 0,
            eventsAvailable: false,
            dataSource: "event feed unavailable in this run",
          },
        }) as NewsBundle,
    ),
  ]);
  return { health, ports, vessels, weather, news };
}
