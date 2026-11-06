import { API_BASE } from "./api";
import type { ApiResponse } from "./api-client";

type Handoffs = ApiResponse<"/api/handoffs", "get">;
type Sources = ApiResponse<"/api/public/sources", "get">;
type Listener = { items: (items: Handoffs["items"]) => void; sources: (sources: Sources) => void; state: (live: boolean) => void };
type Stream = { listeners: Set<Listener>; controller: AbortController; live: boolean; retry?: ReturnType<typeof setTimeout> };
const streams = new Map<string, Stream>();

/** One authenticated connection per workspace session, shared by cards and pulse. */
export function subscribeWorkspaceStream(token: string, mode: string | undefined, listener: Listener) {
  const key = `${mode}:${token}`;
  let stream = streams.get(key);
  if (!stream) {
    stream = { listeners: new Set(), controller: new AbortController(), live: false };
    streams.set(key, stream);
  }
  const current = stream;
  const first = current.listeners.size === 0;
  current.listeners.add(listener);
  listener.state(current.live);
  const state = (live: boolean) => {
    current.live = live;
    for (const item of current.listeners) item.state(live);
  };
  async function listen() {
    let reconnect = true;
    try {
      const prefix = mode === "demo" ? "/demo/terminal" : "";
      const response = await fetch(API_BASE + prefix + "/handoffs/stream", {
        headers: { Authorization: "Bearer " + token, Accept: "text/event-stream" },
        signal: current.controller.signal, cache: "no-store",
      });
      if ([401, 403, 404, 405].includes(response.status)) reconnect = false;
      if (!response.ok || !response.body || !response.headers.get("content-type")?.startsWith("text/event-stream")) return;
      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      let pending = "";
      try {
        while (!current.controller.signal.aborted) {
          const chunk = await reader.read();
          if (chunk.done) return;
          pending += chunk.value.replaceAll("\r\n", "\n");
          if (pending.length > 1_048_576) throw new Error("Oversized workspace event");
          let boundary = pending.indexOf("\n\n");
          while (boundary >= 0) {
            const frame = pending.slice(0, boundary);
            pending = pending.slice(boundary + 2);
            boundary = pending.indexOf("\n\n");
            const event = frame.split("\n").find((line) => line.startsWith("event:"))?.slice(6).trim();
            if (event !== "handoffs" && event !== "sources") continue;
            const data = frame.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
            const payload = JSON.parse(data);
            if (current.controller.signal.aborted) return;
            if (event === "handoffs" && Array.isArray(payload.items)) {
              for (const item of current.listeners) item.items(payload.items);
              state(true);
            } else if (event === "sources" && Array.isArray(payload.sources)) {
              for (const item of current.listeners) item.sources(payload);
              state(true);
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    } catch {
      // Retained queries provide polling fallback while SSE is disconnected.
    } finally {
      if (!current.controller.signal.aborted) {
        state(false);
        if (reconnect) current.retry = setTimeout(listen, 3000);
      }
    }
  }
  if (first) void listen();
  return () => {
    current.listeners.delete(listener);
    if (current.listeners.size === 0) {
      current.controller.abort();
      clearTimeout(current.retry);
      streams.delete(key);
    }
  };
}
