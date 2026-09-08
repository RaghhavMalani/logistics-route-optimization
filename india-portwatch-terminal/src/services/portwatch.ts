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

/* --------------------------------------------------------------- system --- */

export const fetchHealth = () => getJson<Health>("/health");
export const fetchProvenance = () => getJson<Provenance>("/provenance");

/* ---------------------------------------------------------------- ports --- */

export const fetchPorts = () => getJson<PortSnapshot[]>("/ports");
export const fetchPort = (code: string) =>
  getJson<PortSnapshot>(`/ports/${encodeURIComponent(code)}`);
export const fetchPortRegistry = () =>
  getJson<PortRegistryEntry[]>("/ports/registry");

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

export const fetchScenarios = () =>
  getJson<ScenarioDefinition[]>("/scenarios");

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
