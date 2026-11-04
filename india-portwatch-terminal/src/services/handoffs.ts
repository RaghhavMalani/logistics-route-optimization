import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { API_BASE, ApiError, getJson } from "@/services/api";

export interface HomeHandoff {
  id: string;
  vesselName: string;
  portCode: string;
  state: string;
  summary?: string;
  nextActor: string | null;
  deepLink: string | null;
  advisoryId?: string;
}

async function readEvents(
  response: Response,
  onItems: (items: HomeHandoff[]) => void,
) {
  const reader = response
    .body!.pipeThrough(new TextDecoderStream())
    .getReader();
  let pending = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) return;
      pending += value.replaceAll("\r\n", "\n");
      let boundary = pending.indexOf("\n\n");
      while (boundary >= 0) {
        const frame = pending.slice(0, boundary);
        pending = pending.slice(boundary + 2);
        boundary = pending.indexOf("\n\n");
        if (!frame.startsWith("event: handoffs\n")) continue;
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        const payload = JSON.parse(data) as { items: HomeHandoff[] };
        if (Array.isArray(payload.items)) onItems(payload.items);
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export function useWorkspaceHandoffs(enabled = true) {
  const { session, identityHeaders } = useAuth();
  const client = useQueryClient();
  const [live, setLive] = useState(false);
  const key = useMemo(
    () => [
      "workspace-handoffs",
      session?.demoId ?? session?.user.id,
      session?.user.role,
    ],
    [session?.demoId, session?.user.id, session?.user.role],
  );
  const query = useQuery({
    queryKey: key,
    enabled: enabled && Boolean(session),
    staleTime: 10_000,
    refetchInterval: live ? false : 10_000,
    refetchOnWindowFocus: !live,
    retry: false,
    queryFn: async ({ signal }) => {
      try {
        const result = await getJson<{ items: HomeHandoff[] }>(
          "/handoffs",
          identityHeaders,
          { signal, bypassScreen: live },
        );
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
    const controller = new AbortController();
    let retry: ReturnType<typeof setTimeout> | undefined;
    const prefix = mode === "demo" ? "/demo/terminal" : "";
    async function listen() {
      let reconnect = true;
      try {
        const response = await fetch(API_BASE + prefix + "/handoffs/stream", {
          headers: {
            Authorization: "Bearer " + token,
            Accept: "text/event-stream",
          },
          signal: controller.signal,
          cache: "no-store",
        });
        if ([401, 403, 404, 405].includes(response.status)) reconnect = false;
        if (
          !response.ok ||
          !response.body ||
          !response.headers.get("content-type")?.startsWith("text/event-stream")
        )
          return;
        await readEvents(response, (items) => {
          if (controller.signal.aborted) return;
          client.setQueryData(key, items);
          setLive(true);
        });
      } catch {
        // Existing query polling continues when streaming is unavailable.
      } finally {
        if (!controller.signal.aborted) {
          setLive(false);
          if (reconnect) retry = setTimeout(listen, 3000);
        }
      }
    }
    void listen();
    return () => {
      controller.abort();
      clearTimeout(retry);
    };
  }, [enabled, token, mode, ready, client, key]);

  return query;
}
