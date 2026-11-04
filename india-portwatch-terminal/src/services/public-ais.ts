import { useQuery } from "@tanstack/react-query";
import { getJson } from "./api";
import type { ObservedTracks } from "@/types/portwatch-os";
export type PublicAis = ObservedTracks & {
  origin: string;
  freshness: string;
  replayOf: string | null;
  meaning: string;
};
export function usePublicAis(enabled: boolean) {
  return useQuery({
    queryKey: ["public-ais-observations"],
    queryFn: ({ signal }) =>
      getJson<PublicAis>("/intelligence/ais-observations", {}, { signal }),
    enabled,
    staleTime: 4000,
    refetchInterval: enabled ? 5000 : false,
    retry: false,
  });
}
