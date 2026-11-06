import { useQuery, useQueryClient } from "@tanstack/react-query";

import { getApi } from "@/services/api-client";

export function useSourceHealth() {
  const client = useQueryClient();
  return useQuery({
    queryKey: ["public", "source-health"],
    queryFn: ({ signal }) =>
      getApi("/api/public/sources", undefined, { signal }),
    staleTime: 60_000,
    refetchInterval: () => client.getQueryData(["source-stream-live"]) ? false : 30_000,
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
