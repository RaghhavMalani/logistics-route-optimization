/**
 * Query hooks.
 *
 * One hook per artefact, with the cache policy that artefact deserves: the
 * health probe is polled because it is how a screen learns the twin went stale,
 * everything else is fetched once per view and revalidated on demand. Pages do
 * not call `useQuery` directly, so refresh behaviour is decided here rather
 * than eleven times over.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import {
  fetchBenchmark,
  fetchChain,
  fetchDecision,
  fetchFeedAdapters,
  fetchFleet,
  fetchForecast,
  fetchHealth,
  fetchNews,
  fetchPipeline,
  fetchPort,
  fetchPortRegistry,
  fetchPorts,
  fetchProvenance,
  fetchRegime,
  fetchScenarios,
  fetchVessels,
  fetchWeather,
  fetchWeatherIntelligence,
} from "./portwatch";
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
  VesselBundle,
  WeatherIntelligence,
  WeatherSignal,
} from "@/types/portwatch";

const ARTEFACT = { staleTime: 60_000, gcTime: 600_000 } as const;

export const useHealth = (): UseQueryResult<Health> =>
  useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    staleTime: 20_000,
    refetchInterval: 60_000,
  });

export const useProvenance = (): UseQueryResult<Provenance> =>
  useQuery({ queryKey: ["provenance"], queryFn: fetchProvenance, ...ARTEFACT });

export const usePorts = (): UseQueryResult<PortSnapshot[]> =>
  useQuery({ queryKey: ["ports"], queryFn: fetchPorts, ...ARTEFACT });

export const usePort = (code: string | null | undefined): UseQueryResult<PortSnapshot> =>
  useQuery({
    queryKey: ["port", code],
    queryFn: () => fetchPort(code as string),
    enabled: Boolean(code),
    ...ARTEFACT,
  });

export const usePortRegistry = (): UseQueryResult<PortRegistryEntry[]> =>
  useQuery({ queryKey: ["port-registry"], queryFn: fetchPortRegistry, ...ARTEFACT });

export const useWeather = (): UseQueryResult<WeatherSignal[]> =>
  useQuery({ queryKey: ["weather"], queryFn: fetchWeather, ...ARTEFACT });

export const useWeatherIntelligence = (): UseQueryResult<WeatherIntelligence> =>
  useQuery({
    queryKey: ["weather-intelligence"],
    queryFn: fetchWeatherIntelligence,
    ...ARTEFACT,
  });

export const useNews = (): UseQueryResult<NewsBundle> =>
  useQuery({ queryKey: ["news"], queryFn: fetchNews, ...ARTEFACT });

export const useVessels = (): UseQueryResult<VesselBundle> =>
  useQuery({ queryKey: ["vessels"], queryFn: fetchVessels, ...ARTEFACT });

export const useFeedAdapters = (): UseQueryResult<FeedAdapter[]> =>
  useQuery({ queryKey: ["feed-adapters"], queryFn: fetchFeedAdapters, ...ARTEFACT });

export const useFleet = (): UseQueryResult<FleetRow[]> =>
  useQuery({ queryKey: ["fleet"], queryFn: fetchFleet, ...ARTEFACT });

export const usePipeline = (): UseQueryResult<PipelineNode[]> =>
  useQuery({ queryKey: ["pipeline"], queryFn: fetchPipeline, ...ARTEFACT });

export const useBenchmark = (): UseQueryResult<Benchmark> =>
  useQuery({ queryKey: ["benchmark"], queryFn: fetchBenchmark, ...ARTEFACT });

export const useForecast = (code: string | null | undefined): UseQueryResult<ForecastPoint[]> =>
  useQuery({
    queryKey: ["forecast", code],
    queryFn: () => fetchForecast(code as string),
    enabled: Boolean(code),
    ...ARTEFACT,
  });

export const useRegime = (code: string | null | undefined): UseQueryResult<RegimeState> =>
  useQuery({
    queryKey: ["regime", code],
    queryFn: () => fetchRegime(code as string),
    enabled: Boolean(code),
    ...ARTEFACT,
  });

export const useDecision = (code: string | null | undefined): UseQueryResult<Decision> =>
  useQuery({
    queryKey: ["decision", code],
    queryFn: () => fetchDecision(code as string),
    enabled: Boolean(code),
    ...ARTEFACT,
  });

export const useChain = (code: string | null | undefined): UseQueryResult<IntelligenceChain> =>
  useQuery({
    queryKey: ["chain", code],
    queryFn: () => fetchChain(code as string),
    enabled: Boolean(code),
    ...ARTEFACT,
  });

export const useScenarios = (): UseQueryResult<ScenarioDefinition[]> =>
  useQuery({ queryKey: ["scenarios"], queryFn: fetchScenarios, ...ARTEFACT });
