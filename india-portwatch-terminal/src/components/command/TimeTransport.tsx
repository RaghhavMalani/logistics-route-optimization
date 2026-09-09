/**
 * The time control: one bar, two clocks.
 *
 * TRAFFIC is the replay clock -- where the fleet is right now, and how fast the
 * replay is running. WEATHER is an offset from the forecast series, and moving
 * it moves the composite sheet, the wind, the storm cells and the predicted
 * fleet positions together. Keeping both on one bar is the point: a digital twin
 * with two independent time cursors is a lie waiting to happen.
 *
 * Each clock has its own transport, because they are not the same kind of time.
 * The replay runs at a multiple of real time; the forecast cursor sweeps a fixed
 * series and loops. Tying the forecast to the replay rate would make a 240x
 * traffic replay skip the whole forecast in a frame.
 *
 * The strip under the scrubber is the national mean weather impact across the
 * forecast series, so an operator can see where the weather is going before
 * dragging to it.
 */

import { FastForward, Pause, Play, RotateCcw } from "lucide-react";

import {
  FORECAST_STEPS,
  REPLAY_RATES,
  useClockState,
  useTraffic,
  type ReplayRate,
} from "@/components/app/traffic-context";
import type { WeatherTimeline } from "@/lib/maritime/weather-model";
import { cn } from "@/lib/utils";

function clockLabel(ms: number): string {
  const date = new Date(ms);
  const day = String(date.getUTCDate()).padStart(2, "0");
  const month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][
    date.getUTCMonth()
  ];
  return `${day} ${month} ${String(date.getUTCHours()).padStart(2, "0")}:${String(
    date.getUTCMinutes(),
  ).padStart(2, "0")}Z`;
}

function offsetLabel(hours: number): string {
  if (hours < 0.5) return "NOW";
  return `+${Math.round(hours)}H`;
}

export function TimeTransport({
  timeline,
  weatherAt,
  className,
}: {
  timeline: WeatherTimeline;
  weatherAt: number;
  className?: string;
}) {
  const { clock } = useTraffic();
  const state = useClockState();

  const maxHours = state.maxOffsetHours;
  const peak = Math.max(0.001, ...timeline.meanImpact);
  // Which bar in the impact strip the cursor is currently over, so the strip
  // reads as a position indicator rather than as decoration.
  const activeBar = timeline.meanImpact.length
    ? Math.round((state.offsetHours / Math.max(1, maxHours)) * (timeline.meanImpact.length - 1))
    : -1;

  return (
    <div
      className={cn(
        "pointer-events-auto flex items-center gap-3 rounded-[3px] border border-[var(--line-strong)]",
        "bg-[var(--panel)]/95 px-2.5 py-1.5 backdrop-blur-[3px] shadow-[0_10px_30px_rgba(0,0,0,0.45)]",
        className,
      )}
      data-testid="time-transport"
    >
      {/* ------------------------------------------------------- traffic -- */}
      <div className="flex shrink-0 items-center gap-1.5">
        <button
          type="button"
          aria-label={state.playing ? "Pause replay" : "Play replay"}
          onClick={() => clock.setPlaying(!state.playing)}
          className="grid h-[22px] w-[22px] place-items-center rounded-[2px] border border-[var(--line-strong)] bg-[var(--panel-2)] text-[var(--text-2)] hover:text-[var(--text)]"
        >
          {state.playing ? <Pause size={11} /> : <Play size={11} />}
        </button>
        <button
          type="button"
          aria-label="Reset both clocks to the forecast origin"
          title="Reset both clocks to the forecast origin"
          onClick={() => clock.reset()}
          className="grid h-[22px] w-[22px] place-items-center rounded-[2px] border border-[var(--line-strong)] bg-[var(--panel-2)] text-[var(--text-3)] hover:text-[var(--text)]"
        >
          <RotateCcw size={11} />
        </button>
      </div>

      <div className="shrink-0 leading-none">
        <div className="eyebrow text-[8.5px]">Traffic</div>
        <div className="num mt-[3px] text-[11.5px] text-[var(--text)]">{clockLabel(state.at)}</div>
      </div>

      <div className="flex shrink-0 overflow-hidden rounded-[2px] border border-[var(--line-strong)]">
        {REPLAY_RATES.map((rate: ReplayRate) => (
          <button
            key={rate}
            type="button"
            aria-pressed={state.rate === rate}
            onClick={() => clock.setRate(rate)}
            className={cn(
              "num px-1.5 py-[2px] text-[10px] transition-colors",
              state.rate === rate
                ? "bg-[var(--panel-4)] text-[var(--text)]"
                : "text-[var(--text-3)] hover:bg-[var(--panel-3)] hover:text-[var(--text-2)]",
            )}
          >
            ×{rate}
          </button>
        ))}
      </div>

      <span className="h-6 w-px shrink-0 bg-[var(--line)]" />

      {/* ------------------------------------------------------- weather -- */}
      <button
        type="button"
        aria-label={
          state.weatherPlaying ? "Pause the forecast animation" : "Play the forecast forward"
        }
        title={
          state.weatherPlaying
            ? "Pause the forecast animation"
            : "Sweep the forecast forward and loop"
        }
        aria-pressed={state.weatherPlaying}
        data-testid="weather-play"
        onClick={() => clock.setWeatherPlaying(!state.weatherPlaying)}
        className={cn(
          "grid h-[22px] w-[22px] shrink-0 place-items-center rounded-[2px] border transition-colors",
          state.weatherPlaying
            ? "border-[var(--info)] bg-[var(--info)]/15 text-[var(--info)]"
            : "border-[var(--line-strong)] bg-[var(--panel-2)] text-[var(--text-2)] hover:text-[var(--text)]",
        )}
      >
        {state.weatherPlaying ? <Pause size={11} /> : <FastForward size={11} />}
      </button>

      <div className="shrink-0 leading-none">
        <div className="eyebrow text-[8.5px]">Weather</div>
        <div className="num mt-[3px] text-[11.5px] text-[var(--text)]">
          <span data-testid="weather-offset">{offsetLabel(state.offsetHours)}</span>
          <span className="ml-1.5 text-[10px] text-[var(--text-3)]">{clockLabel(weatherAt)}</span>
        </div>
      </div>

      <div className="relative min-w-[190px] flex-1">
        {/* The forecast's own shape, so the scrubber is worth dragging. */}
        <div className="flex h-[16px] items-end gap-[1px]" aria-hidden>
          {timeline.meanImpact.map((value, index) => (
            <span
              key={index}
              className={cn(
                "flex-1 rounded-[1px] transition-colors",
                index === activeBar ? "bg-[var(--info)]" : "bg-[var(--info)]/35",
              )}
              style={{ height: `${Math.max(8, (value / peak) * 100)}%` }}
            />
          ))}
        </div>
        <input
          type="range"
          min={0}
          max={maxHours}
          step={0.5}
          value={state.offsetHours}
          aria-label="Forecast lead time in hours"
          data-testid="weather-scrubber"
          onChange={(event) => {
            // Dragging is an explicit choice about where to look, so it takes
            // the cursor off autoplay rather than fighting it.
            clock.setWeatherPlaying(false);
            clock.setOffsetHours(Number(event.target.value));
          }}
          className="pw-scrub mt-1 w-full"
        />
        <div className="mt-[1px] flex justify-between">
          {FORECAST_STEPS.filter((step) => step <= maxHours).map((step) => (
            <button
              key={step}
              type="button"
              onClick={() => {
                clock.setWeatherPlaying(false);
                clock.setOffsetHours(step);
              }}
              className={cn(
                "num text-[9px] transition-colors",
                Math.abs(state.offsetHours - step) < 0.5
                  ? "text-[var(--info)]"
                  : "text-[var(--text-3)] hover:text-[var(--text-2)]",
              )}
            >
              {step === 0 ? "NOW" : `+${step}h`}
            </button>
          ))}
        </div>
      </div>

      {!timeline.available ? (
        <span className="shrink-0 text-[9.5px] text-[var(--crit)]">Forecast unavailable</span>
      ) : null}
    </div>
  );
}
