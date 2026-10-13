import { useCurrentMapWeather } from "@/services/current-inputs";
import { Pill, formatUtc } from "@/components/kit/primitives";

export function CurrentWeatherStatus() {
  const weather = useCurrentMapWeather();
  const rows = weather.data ?? [];
  const receipt = rows[0]?.availableAt;
  return (
    <span
      className="flex items-center gap-1.5"
      data-testid="current-weather-status"
      title={`Independent public forecast receipts; first port available ${formatUtc(receipt)}. Provider issue time unavailable. Activity data has its own age.`}
    >
      <span className="eyebrow text-[10px]">Weather</span>
      <Pill tone={rows.length ? "info" : "warn"}>
        {rows.length
          ? `current ${rows.length} ports`
          : weather.isPending
            ? "checking"
            : "refresh pending"}
      </Pill>
    </span>
  );
}
