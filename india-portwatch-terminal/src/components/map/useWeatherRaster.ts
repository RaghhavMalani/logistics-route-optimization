import { useEffect, useMemo, useRef, useState } from "react";
import type {
  WeatherFieldKey,
  WeatherTimeline,
} from "@/lib/maritime/weather-model";
import {
  buildCompositeRaster,
  buildWeatherRaster,
  type WeatherRaster,
} from "./weather-layers";

type Raster = WeatherRaster | null;
type Job = { run: () => void };

export function useWeatherRaster(
  timeline: WeatherTimeline,
  at: number | null,
  field: WeatherFieldKey | null,
) {
  const cache = useMemo(() => new Map<number, Raster>(), [timeline, field]);
  const worker = useRef<Worker | null>(null);
  const queue = useRef<{ running: boolean; pending?: Job }>({ running: false });
  const [, refresh] = useState(0);

  useEffect(
    () => () => {
      worker.current?.terminate();
      worker.current = null;
      queue.current = { running: false };
    },
    [],
  );

  useEffect(() => {
    if (at === null || cache.has(at)) return;
    const state = queue.current;
    let active = true;
    const job = {
      run() {
        if (!active) return;
        state.running = true;
        const finish = (raster: Raster) => {
          if (active) {
            if (cache.size >= 400) {
              const oldest = cache.keys().next().value;
              if (oldest !== undefined) cache.delete(oldest);
            }
            cache.set(at, raster);
            refresh((value) => value + 1);
          }
          const pending = state.pending;
          state.pending = undefined;
          state.running = false;
          pending?.run();
        };
        const frame = timeline.frameAt(at);
        const fallback = () => {
          window.setTimeout(() => {
            if (!active) {
              finish(null);
              return;
            }
            void (
              field
                ? buildWeatherRaster(frame, field)
                : buildCompositeRaster(frame)
            ).then(finish, () => finish(null));
          }, 0);
        };
        if (
          typeof OffscreenCanvas === "undefined" ||
          typeof Worker === "undefined"
        ) {
          fallback();
          return;
        }
        try {
          const renderer = (worker.current ??= new Worker(
            new URL("./weather-raster.worker.ts", import.meta.url),
            { type: "module" },
          ));
          const failed = () => {
            renderer.terminate();
            if (worker.current === renderer) worker.current = null;
            fallback();
          };
          renderer.onerror = failed;
          renderer.onmessage = ({
            data,
          }: MessageEvent<{ raster: Raster; failed?: boolean }>) => {
            if (data.failed) failed();
            else finish(data.raster);
          };
          renderer.postMessage({ frame, field });
        } catch {
          fallback();
        }
      },
    };
    if (state.running) state.pending = job;
    else job.run();
    return () => {
      active = false;
      if (state.pending === job) state.pending = undefined;
    };
  }, [at, cache, field, timeline]);

  return at === null ? null : (cache.get(at) ?? null);
}
