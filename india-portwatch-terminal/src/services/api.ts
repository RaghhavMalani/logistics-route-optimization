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

export async function getJson<T>(path: string): Promise<T> {
  const url = endpoint(path);
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response), url);
  }
  return (await response.json()) as T;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const url = endpoint(path);
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response), url);
  }
  return (await response.json()) as T;
}

export { API_BASE };
