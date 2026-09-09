/**
 * Which traffic source this deployment is running.
 *
 * The decision is made once, here, from configuration -- never from whether the
 * data "looks real". A deployment with an AIS contract sets
 * `VITE_AIS_PROVIDER` and implements the adapter behind it; every deployment
 * without one falls through to the replay engine, which says so.
 *
 * The seam matters more than either branch. Screens consume `TrafficSource`,
 * so wiring a real provider later changes this file and nothing that draws.
 */

import type { PortSnapshot } from "@/types/portwatch";
import { createReplaySource, type OwnedVesselSeed } from "./replay";
import type { TrafficSource, TrafficSourceInfo } from "./traffic-types";

export interface TrafficConfig {
  ports: PortSnapshot[];
  epoch: number;
  owned?: OwnedVesselSeed[];
  oceanFleet?: number;
}

/** No provider configured, and nothing to draw. */
function unavailableSource(epoch: number): TrafficSource {
  const info: TrafficSourceInfo = {
    kind: "UNAVAILABLE",
    label: "No traffic feed",
    provider: "—",
    detail:
      "An AIS provider is configured but did not answer. No vessel positions are " +
      "shown; the map is not falling back to generated traffic.",
    epoch,
    observed: false,
  };
  return {
    info,
    roster: () => [],
    fixes: () => [],
    fix: () => null,
    route: () => null,
  };
}

/**
 * The provider name this build was configured with, if any.
 *
 * Read through `import.meta.env` so it is fixed at build time: a running
 * terminal cannot be talked into claiming a live feed it does not have.
 */
export function configuredProvider(): string | null {
  const value = (import.meta.env.VITE_AIS_PROVIDER as string | undefined)?.trim();
  return value && value.length > 0 ? value : null;
}

export function createTrafficSource(config: TrafficConfig): TrafficSource {
  const provider = configuredProvider();

  if (provider) {
    // No adapter ships with this build. Rather than quietly serving simulated
    // positions under a live provider's name, the source reports unavailable --
    // an operator who configured a feed must be able to tell it is not working.
    return unavailableSource(config.epoch);
  }

  return createReplaySource({
    ports: config.ports,
    epoch: config.epoch,
    owned: config.owned,
    oceanFleet: config.oceanFleet,
  });
}

export type { OwnedVesselSeed };
