/**
 * Formatting shared by the trust surfaces: the age of a reading, the instant
 * it was taken, and the tone and label of a traffic mode. In its own module
 * so component files export only components.
 */

import type { Tone } from "@/components/kit/primitives";
import type { TrafficMode } from "@/types/portwatch-os";

export const TRAFFIC_TONE: Record<TrafficMode["mode"], Tone> = {
  LIVE_AIS: "ok",
  AIS_STALE: "warn",
  SIMULATED_TRAFFIC: "unc",
  UNAVAILABLE: "crit",
};

export const TRAFFIC_LABEL: Record<TrafficMode["mode"], string> = {
  LIVE_AIS: "Live AIS",
  AIS_STALE: "AIS stale",
  SIMULATED_TRAFFIC: "Simulated replay",
  UNAVAILABLE: "No traffic feed",
};

/** An age an operator reads at a glance: "4s", "6m", "2h", "13d". */
export function formatAge(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86_400)}d`;
}

/** "13 Sep 11:20Z" -- the instant, not a relative word. */
export function formatInstant(iso: string | null): string {
  if (!iso) return "—";
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) return "—";
  return `${new Date(parsed).toUTCString().slice(5, 22)}Z`;
}
