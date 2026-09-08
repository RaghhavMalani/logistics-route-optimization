/**
 * The vessel operator's view of the routing artefact.
 *
 * One join, done once: each scored vessel against its destination port's
 * forecast, that port's marine conditions, and the events with a measured
 * exposure to it. Every field here traces to an artefact — where the optimizer
 * produced no value the field is null and the screen renders `n/a`.
 *
 * Two things this deliberately does not have, because the artefacts do not:
 * an IMO number, and a position. The optimizer scores a *declared call* and an
 * arrival window; it does not track vessels.
 */

import { useMemo } from "react";

import { useFleet, useNews, usePorts, useWeather } from "@/services/hooks";
import type {
  FleetRow,
  NewsEvent,
  PortSnapshot,
  WeatherSignal,
} from "@/types/portwatch";

export type VesselStatus = "reroute advised" | "hold to plan" | "monitor";

export interface VesselIntel {
  vessel: FleetRow;
  destination: PortSnapshot | null;
  alternative: PortSnapshot | null;
  weather: WeatherSignal | null;
  /** Events whose measured exposure touches the destination port. */
  exposure: Array<{ event: NewsEvent; exposure: number | null }>;
  /** Calendar date of the intended arrival, from origin + horizon day. */
  etaDate: Date | null;
  recommendedEtaDate: Date | null;
  arrivalWindow: { earliest: number; latest: number } | null;
  status: VesselStatus;
  /** The single instruction, and the sentence that justifies it. */
  action: string;
  why: string;
  /** 0–1 composite used only for ranking rows, never displayed as a metric. */
  attention: number;
}

function addDays(iso: string | null | undefined, days: number | null | undefined): Date | null {
  if (!iso || days == null) return null;
  const base = new Date(iso);
  if (Number.isNaN(base.getTime())) return null;
  return new Date(base.getTime() + days * 86_400_000);
}

/**
 * The instruction shown to a vessel operator.
 *
 * It restates what the optimizer and the decision layer already decided; it
 * does not add a new rule. `reroute` is the optimizer's own flag, the buffer is
 * its own recommendation, and the congestion probability is the forecast's.
 */
function resolveAction(
  vessel: FleetRow,
  destination: PortSnapshot | null,
): { status: VesselStatus; action: string; why: string } {
  if (vessel.reroute && vessel.recommendedPortCode !== vessel.intendedPortCode) {
    const saved = vessel.portWaitDeltaHours;
    return {
      status: "reroute advised",
      action: `Consider ${vessel.recommendedPortName ?? vessel.recommendedPortCode ?? "the alternative call"}`,
      why:
        saved != null && saved < 0
          ? `Expected berth wait falls by ${Math.abs(saved).toFixed(1)}h against ${vessel.extraSteamingHours?.toFixed(1) ?? "extra"}h of steaming and ${vessel.diversionKm?.toFixed(0) ?? "a"} km of diversion.`
          : "The alternative call scores lower on the optimizer's cost even after the diversion penalty.",
    };
  }

  const probability = vessel.intendedCongestionProbability ?? 0;
  const regimeSevere = destination?.risk === "severe";
  if (probability >= 0.5 || regimeSevere) {
    return {
      status: "monitor",
      action: `Hold the call, carry a ${vessel.bufferHours?.toFixed(0) ?? "recommended"}h ETA buffer`,
      why: `${destination?.name ?? "The destination"} sits in ${destination?.regime ?? "an elevated"} regime with P(congestion) ${probability.toFixed(2)} on the scored day; the diversion does not pay for itself.`,
    };
  }

  return {
    status: "hold to plan",
    action: `Maintain the declared call, ${vessel.bufferHours?.toFixed(0) ?? "no"}h buffer`,
    why: `No alternative in the candidate set beats ${destination?.name ?? "the intended port"} once the diversion penalty is applied.`,
  };
}

export function useFleetIntel() {
  const fleet = useFleet();
  const ports = usePorts();
  const weather = useWeather();
  const news = useNews();

  const intel = useMemo<VesselIntel[]>(() => {
    const portByCode = new Map((ports.data ?? []).map((port) => [port.code, port]));
    const weatherByCode = new Map((weather.data ?? []).map((signal) => [signal.portCode, signal]));
    const events = news.data?.events ?? [];

    return (fleet.data ?? []).map((vessel) => {
      const destination = vessel.intendedPortCode
        ? (portByCode.get(vessel.intendedPortCode) ?? null)
        : null;
      const alternative = vessel.recommendedPortCode
        ? (portByCode.get(vessel.recommendedPortCode) ?? null)
        : null;

      const exposure = events
        .map((event) => {
          const match = event.exposure?.find(
            (entry) => entry.portCode === vessel.intendedPortCode,
          );
          const affected =
            vessel.intendedPortCode != null &&
            event.affectedPorts?.includes(vessel.intendedPortCode);
          if (!match && !affected) return null;
          return { event, exposure: match?.exposure ?? null };
        })
        .filter((row): row is { event: NewsEvent; exposure: number | null } => row !== null)
        .sort((a, b) => (b.exposure ?? 0) - (a.exposure ?? 0));

      const { status, action, why } = resolveAction(vessel, destination);

      const attention =
        (vessel.reroute ? 0.45 : 0) +
        (vessel.intendedCongestionProbability ?? 0) * 0.35 +
        (destination?.risk === "severe" ? 0.2 : destination?.risk === "congested" ? 0.1 : 0);

      return {
        vessel,
        destination,
        alternative,
        weather: vessel.intendedPortCode
          ? (weatherByCode.get(vessel.intendedPortCode) ?? null)
          : null,
        exposure,
        etaDate: addDays(vessel.originDate, vessel.intendedArrivalDay ?? vessel.bestArrivalDay),
        recommendedEtaDate: addDays(vessel.originDate, vessel.bestArrivalDay),
        arrivalWindow:
          vessel.earliestDay != null && vessel.latestDay != null
            ? { earliest: vessel.earliestDay, latest: vessel.latestDay }
            : null,
        status,
        action,
        why,
        attention,
      };
    });
  }, [fleet.data, news.data, ports.data, weather.data]);

  return {
    intel,
    ranked: useMemo(() => [...intel].sort((a, b) => b.attention - a.attention), [intel]),
    isLoading: fleet.isLoading || ports.isLoading,
    error: fleet.error ?? ports.error,
    refetch: () => {
      void fleet.refetch();
      void ports.refetch();
    },
    ports: ports.data ?? [],
    weather: weather.data ?? [],
    events: news.data?.events ?? [],
    alerts: news.data?.alerts ?? [],
    originDate: fleet.data?.[0]?.originDate ?? null,
  };
}

export function statusTone(status: VesselStatus): "warn" | "ok" | "info" {
  if (status === "reroute advised") return "warn";
  if (status === "monitor") return "info";
  return "ok";
}
