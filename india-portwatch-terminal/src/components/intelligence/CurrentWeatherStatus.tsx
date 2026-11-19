import { useCurrentMapWeather } from "@/services/current-inputs";
import { Pill, formatUtc } from "@/components/kit/primitives";
import { useSourceHealth, ageLabel } from "@/services/source-health";
import { forecastReceiptLabel } from "@/lib/forecast-freshness";

export function CurrentWeatherStatus() {
  const weather = useCurrentMapWeather();
  const rows = weather.data ?? [];
  const receipt = rows[0]?.availableAt;
  const health = useSourceHealth();
  const source = health.data?.sources.find(
    (item) => item.id === "open-meteo-surface",
  );
  const current = source?.status === "live" && rows.length > 0;
  return (
    <span
      className="flex items-center gap-1.5"
      data-testid="current-weather-status"
      title={`First available ${formatUtc(receipt)}. ~ estimates issue time from the last value change in the Best Match forecast. Activity has its own age.`}
    >
      <span className="eyebrow text-[10px]">Weather</span>
      <Pill tone={current ? "info" : "neutral"}>
        {current
          ? forecastReceiptLabel(source, true)
          : weather.isPending
            ? "checking"
            : source?.availableAt
              ? `Latest available · ${formatUtc(source.availableAt)} (${ageLabel(source.dataAgeSeconds)} old)`
              : "unavailable"}
      </Pill>
    </span>
  );
}
