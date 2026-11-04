import type { components } from "./openapi.generated";
import { prewarmChart } from "@/components/map/chart-engine";

/** Private boot packets are shared only by the authenticated browser session. */
const homes = {
  SHIPPING_COMPANY: ["company-home", "/company/overview"],
  PORT_AUTHORITY: ["port-home", "/port/overview"],
  VESSEL_OPERATOR: ["vessel-home", "/vessel/overview"],
  NATIONAL_ADMIN: ["admin-home", "/admin/radar"],
} as const;

type HomeRole = keyof typeof homes;
type Mode = "demo" | "production";
type Packet = components["schemas"]["ScreenPayload"];

type Entry = { token: string; until: number; packet: Promise<Packet | null> };
const entries = new Map<string, Entry>();
const BOOT_MS = 10_000;
let boot: { navigation: string; until: number } | undefined;
const screenPaths = new Set([
  "/health",
  "/public/sources",
  "/fleet",
  "/news",
  "/ports",
  "/ports/registry",
  "/weather",
  "/weather/current-map",
  "/world/clock",
  "/fabric/health",
  "/company/fleet",
  "/company/risk",
  "/company/decision-triage",
  "/demonstrations/scenarios",
  "/demonstrations/selection",
  "/handoffs",
]);

function active(role: string | undefined): role is HomeRole {
  return (
    typeof window !== "undefined" &&
    !!role &&
    Object.hasOwn(homes, role) &&
    window.location.pathname === homes[role as HomeRole][1]
  );
}

function acquire(
  base: string,
  role: HomeRole,
  token: string,
  mode: Mode,
  prefetch = false,
) {
  const key = JSON.stringify([base, token, role, mode]);
  const existing = entries.get(key);
  if (existing && existing.until > Date.now()) return existing.packet;
  const path = mode === "demo" ? "/demo/terminal" : "";
  const url =
    base +
    path +
    "/screens/" +
    homes[role][0] +
    (prefetch ? "?prefetch=true" : "");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6_000);
  const entry: Entry = {
    token,
    until: Infinity,
    packet: Promise.resolve(null),
  };
  entry.packet = fetch(url, {
    headers: { Authorization: "Bearer " + token, Accept: "application/json" },
    signal: controller.signal,
  })
    .then(async (response) =>
      response.ok ? ((await response.json()) as Packet) : null,
    )
    .catch(() => null)
    .then((packet) => {
      entry.until = Date.now() + BOOT_MS;
      return packet;
    })
    .finally(() => clearTimeout(timer));
  entries.set(key, entry);
  while (entries.size > 8) {
    const oldest = entries.keys().next().value;
    if (oldest !== undefined) entries.delete(oldest);
  }
  return entry.packet;
}

export function retainHomePackets(token: string | undefined) {
  if (!token) boot = undefined;
  for (const [key, entry] of entries)
    if (entry.token !== token) entries.delete(key);
}

export function invalidateHomePackets() {
  entries.clear();
}

export async function loadHomeSession(
  base: string,
  role: string,
  token: string,
  mode: Mode,
) {
  if (!active(role)) return null;
  prewarmChart();
  const packet = await acquire(base, role, token, mode);
  return packet?.session ?? null;
}

export function prefetchHome(base: string, role: string, token: string) {
  if (!Object.hasOwn(homes, role)) return;
  void acquire(base, role as HomeRole, token, "demo", true);
}

export async function projectHomeSection(
  base: string,
  path: string,
  role: string | undefined,
  token: string | undefined,
  mode: Mode,
) {
  if (!token || !active(role)) return undefined;
  const navigation =
    role + ":" + (window.history.state?.__TSR_key ?? window.location.pathname);
  const now = Date.now();
  if (boot?.navigation !== navigation)
    boot = { navigation, until: now + BOOT_MS };
  if (boot.until <= now) return undefined;
  const [endpoint, query] = path.split("?", 2);
  if (
    !screenPaths.has(endpoint) &&
    !/^\/model\/[^/]+\/(?:forecast|decision)$/.test(endpoint)
  )
    return undefined;
  const params = new URLSearchParams(query);
  params.sort();
  const key = endpoint + (params.size ? "?" + params.toString() : "");
  return (await acquire(base, role, token, mode))?.sections[key];
}
