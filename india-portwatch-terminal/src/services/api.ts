/**
 * HTTP layer for the terminal.
 *
 * There is deliberately no local fallback data. If the backend cannot serve an
 * artefact the request fails and the screen says so -- a terminal that silently
 * swaps in demo numbers when the pipeline is down is worse than one that goes
 * dark, because the operator cannot tell the difference.
 */

const API_BASE =
  (import.meta.env.VITE_PORTWATCH_API_BASE as string | undefined)?.replace(
    /\/$/,
    "",
  ) ?? "/api";

let accessToken: string | undefined;
let sessionMode: "demo" | "production" = "production";
export const getSessionMode = () => sessionMode;
export function setAccessToken(
  token?: string,
  mode: "demo" | "production" = "production",
): void {
  accessToken = token;
  sessionMode = mode;
}

export interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

async function request(
  url: string,
  init: RequestInit,
  options: RequestOptions,
): Promise<Response> {
  const controller = new AbortController();
  const abort = () => controller.abort(options.signal?.reason);
  options.signal?.addEventListener("abort", abort, { once: true });
  if (options.signal?.aborted) abort();
  const timer = setTimeout(
    () => controller.abort(new Error("Request timed out")),
    options.timeoutMs ?? 20_000,
  );
  try {
    // Consume the body inside this scope so cancellation also bounds JSON reads.
    const response = await fetch(url, {
      ...init,
      headers: {
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...init.headers,
      },
      signal: controller.signal,
    });
    const body = await response.arrayBuffer();
    if (
      response.status === 401 &&
      sessionMode === "demo" &&
      typeof window !== "undefined"
    ) {
      window.dispatchEvent(new Event("portwatch:demo-expired"));
    }
    return new Response(
      [204, 205, 304].includes(response.status) ? null : body,
      {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
      },
    );
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string, url: string) {
    super(`${url} failed with ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function endpoint(path: string): string {
  if (
    sessionMode === "demo" &&
    !path.startsWith("/demo/") &&
    !path.startsWith("/public/") &&
    !path.startsWith("/auth/")
  ) {
    // The server adapter mounts an explicit set of original contracts against
    // visitor-owned resources. It never authenticates operational routes.
    return `${API_BASE}/demo/terminal${path.startsWith("/") ? path : `/${path}`}`;
  }
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

async function readDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      return String((body as { detail: unknown }).detail);
    }
    return JSON.stringify(body).slice(0, 300);
  } catch {
    return response.statusText || "no response body";
  }
}

/**
 * `headers` carries the caller identity where an endpoint needs one -- the
 * advisory routes, which the backend turns into an acting principal. It is
 * optional because most of this API is read-only and anonymous.
 */
export async function getJson<T>(
  path: string,
  headers: Record<string, string> = {},
  options: RequestOptions = {},
): Promise<T> {
  const url = endpoint(path);
  const response = await request(
    url,
    {
      headers: { Accept: "application/json", ...headers },
    },
    options,
  );
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response), url);
  }
  return (await response.json()) as T;
}

export async function postJson<T>(
  path: string,
  body: unknown,
  headers: Record<string, string> = {},
  options: RequestOptions = {},
): Promise<T> {
  const url = endpoint(path);
  const response = await request(
    url,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...headers,
      },
      body: JSON.stringify(body),
    },
    options,
  );
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response), url);
  }
  return (await response.json()) as T;
}

export { API_BASE };

export async function getBlob(path: string): Promise<Blob> {
  const url = endpoint(path);
  const response = await request(
    url,
    { headers: { Accept: "application/pdf" } },
    {},
  );
  if (!response.ok)
    throw new ApiError(response.status, await readDetail(response), url);
  return response.blob();
}
