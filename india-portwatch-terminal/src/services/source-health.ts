import { useQuery } from "@tanstack/react-query";

import { getApi, type ApiResponse } from "@/services/api-client";

type SourceStatus = ApiResponse<"/api/public/sources", "get">["sources"][number]["status"];

export const sourceStatusLabel: Record<SourceStatus, string> = {
  live: "Current",
  expected_lag: "Within expected publication lag",
  stale: "Stale",
  unavailable: "Unavailable",
};

export const expectedLagTone = "rounded bg-amber-100 px-1 text-amber-900";

export function useSourceHealth() {
  const streaming = useQuery({
    queryKey: ["source-stream-live"],
    queryFn: async () => false,
    enabled: false,
    initialData: false,
  });
  return useQuery({
    queryKey: ["public", "source-health"],
    queryFn: ({ signal }) =>
      getApi("/api/public/sources", undefined, { signal }),
    staleTime: 60_000,
    refetchOnWindowFocus: true,
    refetchInterval: streaming.data ? false : 30_000,
    retry: false,
  });
}

export function ageLabel(seconds: number | null | undefined) {
  if (seconds == null) return "Unmeasured";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} h`;
  return `${(seconds / 86400).toFixed(1)} days`;
}

export function successLabel(rate: number | null | undefined, attempts = 0) {
  return rate == null
    ? "Unmeasured"
    : `${Math.round(rate * 100)}% of ${attempts}`;
}
