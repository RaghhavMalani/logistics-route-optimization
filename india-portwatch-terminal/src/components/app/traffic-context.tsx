/**
 * One fleet, one clock, shared by every screen.
 *
 * The traffic layer is the only thing in this application that changes sixty
 * times a second, so it deliberately does not live in React state. The clock is
 * a small subscribable store: the map subscribes and writes straight into the
 * GL source, while panels subscribe at two or three hertz and re-render. A
 * component that only needs the fleet's static particulars never re-renders at
 * all.
 *
 * The clock is anchored to the pipeline's forecast origin rather than the wall
 * clock. That keeps the opening picture identical across runs and machines --
 * which is what makes a screenshot reviewable -- and it keeps the traffic time
 * consistent with the observation time of the port state it sits on top of.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { createTrafficSource, type OwnedVesselSeed } from "@/lib/maritime/traffic-source";
import type { TrafficSource, VesselFix } from "@/lib/maritime/traffic-types";
import { useEnrichedPorts, useFleet, useHealth } from "@/services/hooks";

/* ----------------------------------------------------------------- clock -- */

export const REPLAY_RATES = [1, 10, 60, 240] as const;
export type ReplayRate = (typeof REPLAY_RATES)[number];

/** Forecast steps the timeline offers, in hours ahead of the traffic clock. */
export const FORECAST_STEPS = [0, 3, 6, 12, 24, 48, 72] as const;

interface ClockStore {
  at: number;
  epoch: number;
  playing: boolean;
  rate: ReplayRate;
  offsetHours: number;
  listeners: Set<() => void>;
}

export interface TrafficClock {
  /** Current replay instant, epoch ms. Read in a frame, never in a render. */
  now(): number;
  epoch(): number;
  offsetHours(): number;
  /** The instant the forecast timeline is pointing at. */
  forecastAt(): number;
  playing(): boolean;
  rate(): ReplayRate;
  subscribe(listener: () => void): () => void;
  setPlaying(next: boolean): void;
  setRate(next: ReplayRate): void;
  setOffsetHours(next: number): void;
  seek(at: number): void;
  reset(): void;
}

function createClock(epoch: number): { clock: TrafficClock; store: ClockStore } {
  const store: ClockStore = {
    at: epoch,
    epoch,
    playing: true,
    rate: 60,
    offsetHours: 0,
    listeners: new Set(),
  };
  const emit = () => {
    for (const listener of store.listeners) listener();
  };
  const clock: TrafficClock = {
    now: () => store.at,
    epoch: () => store.epoch,
    offsetHours: () => store.offsetHours,
    forecastAt: () => store.at + store.offsetHours * 3_600_000,
    playing: () => store.playing,
    rate: () => store.rate,
    subscribe: (listener) => {
      store.listeners.add(listener);
      return () => store.listeners.delete(listener);
    },
    setPlaying: (next) => {
      store.playing = next;
      emit();
    },
    setRate: (next) => {
      store.rate = next;
      emit();
    },
    setOffsetHours: (next) => {
      store.offsetHours = next;
      emit();
    },
    seek: (at) => {
      store.at = at;
      emit();
    },
    reset: () => {
      store.at = store.epoch;
      store.offsetHours = 0;
      emit();
    },
  };
  return { clock, store };
}

/* --------------------------------------------------------------- context -- */

export interface TrafficContextValue {
  source: TrafficSource;
  clock: TrafficClock;
  /** Every vessel resolved to an instant. Cached per instant. */
  fixesAt(at: number): VesselFix[];
  fixAt(id: string, at: number): VesselFix | null;
  /** True once the port artefacts the fleet is sized from have loaded. */
  ready: boolean;
}

const TrafficContext = createContext<TrafficContextValue | null>(null);

const FALLBACK_EPOCH = Date.UTC(2026, 7, 28, 6, 0, 0);

function resolveEpoch(origin: string | null | undefined): number {
  if (!origin) return FALLBACK_EPOCH;
  const parsed = Date.parse(origin);
  return Number.isNaN(parsed) ? FALLBACK_EPOCH : parsed;
}

export function TrafficProvider({ children }: { children: ReactNode }) {
  const { ports, query: portsQuery } = useEnrichedPorts();
  const health = useHealth();
  const fleet = useFleet();

  const epoch = resolveEpoch(health.data?.forecastOrigin ?? ports[0]?.observedAt);

  const clockRef = useRef<{ clock: TrafficClock; store: ClockStore } | null>(null);
  if (!clockRef.current) clockRef.current = createClock(epoch);

  // The epoch only becomes known once /health answers; re-anchor once.
  const anchored = useRef(false);
  useEffect(() => {
    const state = clockRef.current;
    if (!state || anchored.current || !health.data) return;
    anchored.current = true;
    state.store.epoch = epoch;
    state.store.at = epoch;
    state.clock.seek(epoch);
  }, [epoch, health.data]);

  const owned: OwnedVesselSeed[] = useMemo(() => {
    const rows = fleet.data ?? [];
    return rows
      .filter((row) => row.intendedPortCode)
      .map((row) => {
        const originDate = row.originDate ? Date.parse(row.originDate) : NaN;
        const day = row.intendedArrivalDay ?? row.bestArrivalDay;
        return {
          id: row.id,
          name: row.name,
          destinationId: row.intendedPortCode as string,
          etaMs:
            Number.isNaN(originDate) || day == null
              ? null
              : originDate + day * 86_400_000,
        } satisfies OwnedVesselSeed;
      });
  }, [fleet.data]);

  const source = useMemo(
    () =>
      createTrafficSource({
        ports,
        epoch,
        owned,
        // Enough long-haul traffic to read as a network at national zoom without
        // starving the software renderer the browser suite runs on.
        oceanFleet: 250,
      }),
    [epoch, owned, ports],
  );

  /* The animation loop. One rAF for the whole application. */
  useEffect(() => {
    const state = clockRef.current;
    if (!state) return undefined;
    let frame = 0;
    let last = performance.now();

    const tick = (time: number) => {
      const delta = time - last;
      last = time;
      if (state.store.playing) {
        state.store.at += delta * state.store.rate;
        for (const listener of state.store.listeners) listener();
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  /* One fix computation per instant, shared by every subscriber in that frame. */
  const cache = useRef<{ at: number; fixes: VesselFix[] } | null>(null);
  useEffect(() => {
    cache.current = null;
  }, [source]);

  const fixesAt = useCallback(
    (at: number) => {
      if (cache.current && cache.current.at === at) return cache.current.fixes;
      const fixes = source.fixes(at);
      cache.current = { at, fixes };
      return fixes;
    },
    [source],
  );

  const fixAt = useCallback((id: string, at: number) => source.fix(id, at), [source]);

  const value = useMemo<TrafficContextValue>(
    () => ({
      source,
      clock: clockRef.current!.clock,
      fixesAt,
      fixAt,
      ready: portsQuery.isSuccess,
    }),
    [fixAt, fixesAt, portsQuery.isSuccess, source],
  );

  return <TrafficContext.Provider value={value}>{children}</TrafficContext.Provider>;
}

export function useTraffic(): TrafficContextValue {
  const value = useContext(TrafficContext);
  if (!value) throw new Error("useTraffic must be used inside a TrafficProvider");
  return value;
}

/**
 * Subscribe to the clock at a bounded rate.
 *
 * Panels want a readable number, not sixty of them a second. Returning the
 * instant as state means the caller re-renders at `hz`, which is the whole
 * point of separating this from the map's own subscription.
 */
export function useTrafficTick(hz = 2): number {
  const { clock } = useTraffic();
  const [at, setAt] = useState(() => clock.now());
  useEffect(() => {
    const interval = 1000 / hz;
    let last = 0;
    return clock.subscribe(() => {
      const time = performance.now();
      if (time - last < interval) return;
      last = time;
      setAt(clock.now());
    });
  }, [clock, hz]);
  return at;
}

/** The clock's control state, for the transport bar. Re-renders on change. */
export function useClockState(): {
  playing: boolean;
  rate: ReplayRate;
  offsetHours: number;
  at: number;
  epoch: number;
} {
  const { clock } = useTraffic();
  const [state, setState] = useState(() => ({
    playing: clock.playing(),
    rate: clock.rate(),
    offsetHours: clock.offsetHours(),
    at: clock.now(),
    epoch: clock.epoch(),
  }));
  useEffect(() => {
    let last = 0;
    return clock.subscribe(() => {
      const time = performance.now();
      const next = {
        playing: clock.playing(),
        rate: clock.rate(),
        offsetHours: clock.offsetHours(),
        at: clock.now(),
        epoch: clock.epoch(),
      };
      // Control changes must land immediately; the clock reading can wait.
      setState((prev) => {
        if (
          prev.playing !== next.playing ||
          prev.rate !== next.rate ||
          prev.offsetHours !== next.offsetHours ||
          prev.epoch !== next.epoch
        ) {
          last = time;
          return next;
        }
        if (time - last < 500) return prev;
        last = time;
        return next;
      });
    });
  }, [clock]);
  return state;
}

/** Every fix at the current tick. For tables and lists, not for the map. */
export function useFixes(hz = 2): VesselFix[] {
  const { fixesAt } = useTraffic();
  const at = useTrafficTick(hz);
  return useMemo(() => fixesAt(at), [at, fixesAt]);
}
