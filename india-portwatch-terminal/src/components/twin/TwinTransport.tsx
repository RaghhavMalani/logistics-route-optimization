import { Pause, Play } from "lucide-react";
import { TWIN_RATES, type useTwinClock } from "./use-twin-clock";

function elapsed(hour: number) {
  const minute = Math.floor(hour * 60 + 0.001);
  return `+${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}

export function TwinTransport({
  transport,
  duration,
  enabled,
  onPlay,
  onSeek,
  compact = false,
}: {
  transport: ReturnType<typeof useTwinClock>;
  duration: number;
  enabled: boolean;
  onPlay: () => void;
  onSeek: (hour: number) => void;
  compact?: boolean;
}) {
  const { position, playing, rate, setRate } = transport;
  return (
    <section
      aria-label="Modelled simulation timeline"
      className={
        compact
          ? "min-w-[260px] flex-1 px-2 py-1"
          : "shrink-0 border-t border-[var(--line)] bg-[var(--panel)] px-3 py-2"
      }
    >
      <div className="flex items-center gap-2.5">
        <button
          type="button"
          aria-label={playing ? "Pause simulation" : "Play simulation"}
          disabled={!enabled}
          onClick={onPlay}
          className="grid size-8 shrink-0 place-items-center rounded border border-[var(--line)] text-[var(--signal-ink)] hover:bg-[var(--panel-3)] disabled:opacity-40"
        >
          {playing ? <Pause size={15} /> : <Play size={15} />}
        </button>
        <div
          className="flex shrink-0 items-center gap-0.5"
          aria-label="Simulation speed"
        >
          {TWIN_RATES.map((speed) => (
            <button
              key={speed}
              type="button"
              disabled={!enabled}
              aria-pressed={speed === rate}
              onClick={() => setRate(speed)}
              className="num rounded px-1.5 py-1 text-[11px] text-[var(--text-2)] aria-pressed:bg-[var(--panel-3)] aria-pressed:font-semibold aria-pressed:text-[var(--signal-ink)] disabled:opacity-40"
            >
              ×{speed}
            </button>
          ))}
        </div>
        <label className="flex min-w-0 flex-1 items-center gap-2">
          <span className="sr-only">Modelled hour</span>
          <input
            type="range"
            min={0}
            max={duration}
            step={0.05}
            disabled={!enabled}
            value={Math.min(duration, position)}
            aria-valuetext={elapsed(position)}
            onChange={(event) => onSeek(event.currentTarget.valueAsNumber)}
            className="min-w-0 flex-1 accent-[var(--signal-deep)]"
          />
          <output
            data-testid="twin-simulation-hour"
            className="num shrink-0 text-xs"
          >
            {elapsed(position)}
          </output>
        </label>
      </div>
      <p
        className={
          compact ? "sr-only" : "mt-0.5 text-[10px] text-[var(--text-3)]"
        }
      >
        Modelled time · ×1 advances one simulated minute per second.
      </p>
    </section>
  );
}
