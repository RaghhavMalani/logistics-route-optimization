import { useSourceHealth, ageLabel } from "@/services/source-health";
import { formatUtc } from "@/components/kit/primitives";
import type { WeatherTimeline } from "@/lib/maritime/weather-model";
import { forecastReceiptLabel } from "@/lib/forecast-freshness";

export function useWorkspaceWeatherStatus(timeline: WeatherTimeline) {
  const weather = useSourceHealth().data?.sources.find(
    (source) => source.id === "open-meteo-surface",
  );
  const now = Date.now();
  const current =
    timeline.available &&
    timeline.to >= now &&
    timeline.from <= now &&
    weather?.status === "live";
  const observedAt = new Date(timeline.observedAt);
  const latest =
    current && weather?.checkedAt
      ? forecastReceiptLabel(weather, true, now)
      : timeline.available && Number.isFinite(timeline.observedAt)
        ? `Latest available · ${formatUtc(observedAt.toISOString())} (${ageLabel(Math.max(0, (now - timeline.observedAt) / 1000))})`
        : "Weather unavailable";
  return { current, latest, expired: timeline.to < now };
}
