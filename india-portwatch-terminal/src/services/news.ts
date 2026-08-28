import { getJson } from "./api";
import type { NewsEvent } from "@/types/portwatch";

interface AlertEvent {
  id: string;
  portCode: string;
  severity: string;
  text: string;
  ts: string;
  dataSource?: string;
}

interface EntitySentiment {
  entity: string;
  mentions: number;
  sentiment: number;
}

interface NewsBundle {
  events: NewsEvent[];
  alerts: AlertEvent[];
  sentiment: EntitySentiment[];
  summary?: {
    totalEvents?: number;
    totalAlerts?: number;
    negativeEvents?: number;
    averageConfidence?: number;
    dataSource?: string;
  };
}

export async function fetchNewsBundle(): Promise<NewsBundle> {
  return getJson<NewsBundle>("/news", () => ({
    events: [],
    alerts: [],
    sentiment: [],
  }));
}

export async function fetchNewsEvents(): Promise<NewsEvent[]> {
  return (await fetchNewsBundle()).events;
}

export async function fetchAlertEvents(): Promise<AlertEvent[]> {
  return (await fetchNewsBundle()).alerts;
}

export async function fetchNewsEventsForEntity(
  entity: string,
): Promise<NewsEvent[]> {
  const bundle = await getJson<{ events: NewsEvent[] }>(
    `/news/entity/${encodeURIComponent(entity)}`,
    () => ({
      events: [],
    }),
  );

  return bundle.events;
}
