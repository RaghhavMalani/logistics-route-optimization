import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getJson } from "@/services/api";
import type { CurrentEnvironment, CurrentHour } from "@/services/current-inputs";

export interface MiniatureWeather {
  lat: number;
  lon: number;
  hour: CurrentHour;
}

export function usePortWeather(code: string | null, lat?: number, lon?: number) {
  const query = useQuery({
    queryKey: ["miniature-port-weather", code],
    enabled: Boolean(code),
    queryFn: ({ signal }) => getJson<CurrentEnvironment>(
      `/intelligence/current?portCode=${encodeURIComponent(code ?? "")}&view=provider`,
      {}, { signal },
    ),
    staleTime: 60_000,
    refetchInterval: 60_000,
    retry: false,
  });
  const source = query.data?.sources.surface;
  const now = Date.now();
  const age = now - Date.parse(source?.availableAt ?? "");
  const stale = source?.status === "STALE" || (Number.isFinite(age) && age > 3_600_000);
  const hour = !stale && !query.isError && source?.status === "CURRENT" && age >= 0
    ? query.data?.hourly.find((row) => {
        const start = Date.parse(row.validAt);
        return start <= now && now < start + 3_600_000;
      })
    : undefined;
  const weather = useMemo(
    () => hour && lat != null && lon != null ? { hour, lat, lon } : null,
    [hour, lat, lon],
  );
  const label = weather
    ? "Current hourly forecast · Open-Meteo"
    : stale
      ? "Open-Meteo weather stale · effects off"
      : "Current Open-Meteo weather unavailable · effects off";
  return { weather, label };
}
