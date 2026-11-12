import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export const TWIN_RATES = [1, 10, 60] as const;
type TwinRate = (typeof TWIN_RATES)[number];

export interface TwinClock {
  read: () => number;
  subscribe: (listener: () => void) => () => void;
}

export function useTwinClock(duration: number, enabled: boolean) {
  const hour = useRef(0);
  const listeners = useRef(new Set<() => void>());
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState<TwinRate>(60);
  const clock = useMemo<TwinClock>(
    () => ({
      read: () => hour.current,
      subscribe(listener) {
        listeners.current.add(listener);
        return () => listeners.current.delete(listener);
      },
    }),
    [],
  );

  const update = useCallback((next: number) => {
    if (hour.current === next) return;
    hour.current = next;
    for (const listener of listeners.current) listener();
  }, []);
  const seek = useCallback(
    (next: number) => {
      const clamped = Math.max(0, Math.min(duration, next));
      update(clamped);
      setPosition(clamped);
    },
    [duration, update],
  );
  const pause = useCallback(() => {
    setPlaying(false);
    setPosition(hour.current);
  }, []);
  const play = useCallback(() => {
    if (!enabled) return;
    if (hour.current >= duration) seek(0);
    setPlaying(true);
  }, [duration, enabled, seek]);

  const toggle = playing ? pause : play;

  useEffect(() => {
    if (!enabled || !playing) return;
    let frame = 0;
    let last: number | undefined;
    let labelAt = 0;
    const tick = (now: number) => {
      const delta = last === undefined ? 0 : Math.min(100, now - last);
      last = now;
      const next = Math.min(duration, hour.current + (delta * rate) / 60_000);
      update(next);
      if (next >= duration) {
        pause();
        return;
      }
      if (now - labelAt > 95) {
        setPosition(next);
        labelAt = now;
      }
      frame = requestAnimationFrame(tick);
    };
    const visibility = () => {
      cancelAnimationFrame(frame);
      last = undefined;
      if (!document.hidden) frame = requestAnimationFrame(tick);
    };
    document.addEventListener("visibilitychange", visibility);
    visibility();
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [duration, enabled, pause, playing, rate, update]);

  return {
    clock,
    position,
    playing: enabled && playing,
    pause,
    play,
    seek,
    toggle,
    rate,
    setRate,
  };
}
