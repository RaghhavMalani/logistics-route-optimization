import { getApi, type ApiResponse } from "./api-client";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { ApiError } from "@/services/api";
import { subscribeWorkspaceStream } from "./workspace-stream";
import { invalidateHomePackets } from "./home-screen";

type HandoffPayload = ApiResponse<"/api/handoffs", "get">;
export type HomeHandoff = HandoffPayload["items"][number];

export function useWorkspaceHandoffs(enabled = true) {
  const { session, identityHeaders } = useAuth();
  const client = useQueryClient();
  const [live, setLive] = useState(false);
  const key = useMemo(() => ["workspace-handoffs", session?.demoId ?? session?.user.id, session?.user.role],
    [session?.demoId, session?.user.id, session?.user.role]);
  const query = useQuery({
    queryKey: key,
    enabled: enabled && Boolean(session),
    staleTime: 10_000,
    refetchInterval: live ? false : 10_000,
    refetchOnWindowFocus: !live,
    retry: false,
    queryFn: async ({ signal }) => {
      try {
        const result = await getApi("/api/handoffs", identityHeaders, { signal, bypassScreen: live });
        return result.items;
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
  const token = session?.accessToken;
  const mode = session?.mode;
  const ready = !query.isPending;
  useEffect(() => {
    setLive(false);
    if (!enabled || !token || !ready) return;
    return subscribeWorkspaceStream(token, mode, {
      items: (items) => client.setQueryData(key, items),
      sources: (sources) => {
        const sourceKey = ["public", "source-health"];
        type Sources = ApiResponse<"/api/public/sources", "get">;
        const previous = client.getQueryData<Sources>(sourceKey);
        client.setQueryData(["source-stream-live"], true);
        const signature = (value: Sources | undefined) => JSON.stringify(value?.sources.map((row) =>
          [row.id, row.status, row.observedAt, row.availableAt, row.lastSuccess]));
        client.setQueryData(sourceKey, sources);
        if (previous && signature(previous) !== signature(sources)) {
          invalidateHomePackets();
          void client.invalidateQueries({ queryKey: ["current-map-weather"] });
          void client.invalidateQueries({ queryKey: ["health"] });
        }
      },
      state: (connected) => {
        setLive(connected);
        if (!connected) client.setQueryData(["source-stream-live"], false);
      },
    });
  }, [enabled, token, mode, ready, client, key]);
  return query;
}
