import { formatUtc } from "@/components/kit/primitives";
import type { ExposureSegment } from "@/lib/maritime/weather-field";
import { worstExposure } from "@/lib/maritime/weather-field";
import type { WeatherTimeline } from "@/lib/maritime/weather-model";
import { useWorkspaceWeatherStatus } from "./use-workspace-weather-status";

function remaining(eta: number | null | undefined, at: number) {
  if (eta == null || !Number.isFinite(eta)) return "Unavailable";
  if (eta < at) return "ETA passed";
  const hours = Math.ceil((eta - at) / 3_600_000);
  const days = Math.floor(hours / 24);
  return days ? `${days} d ${hours % 24} h` : `${hours} h`;
}

export function BridgePassage({
  name,
  origin,
  destination,
  eta,
  at,
  recommendedSpeed,
  exposure,
  timeline,
}: {
  name: string;
  origin?: string | null;
  destination?: string | null;
  eta?: number | null;
  at: number;
  recommendedSpeed?: number;
  exposure: ExposureSegment[];
  timeline: WeatherTimeline;
}) {
  const worst = worstExposure(exposure);
  const weatherStatus = useWorkspaceWeatherStatus(timeline);
  const maxSpeed = Math.max(20, Math.ceil((recommendedSpeed ?? 0) / 5) * 5);
  return (
    <section
      aria-label="Passage at a glance"
      className="pointer-events-auto shrink-0 rounded border border-[var(--line-strong)] bg-[var(--panel)] p-2.5"
    >
      <h2 className="text-sm font-semibold">Passage · {name}</h2>
      <p className="mt-0.5 text-xs">
        {origin ?? "Unavailable"} → {destination ?? "Unavailable"}
      </p>
      <div className="my-2 flex items-start justify-between gap-2 border-y border-[var(--line)] py-2">
        <div>
          <p className="eyebrow">Modelled ETA countdown</p>
          <output
            data-testid="bridge-eta-countdown"
            className="num block text-2xl font-semibold leading-tight"
          >
            {remaining(eta, at)}
          </output>
          {eta != null && Number.isFinite(eta) ? (
            <p className="text-[11px] text-[var(--text-3)]">
              {formatUtc(new Date(eta).toISOString())}
            </p>
          ) : null}
        </div>
        {recommendedSpeed != null ? (
          <div
            className="flex shrink-0 flex-col items-center"
            data-testid="bridge-speed-dial"
          >
            <div
              aria-hidden="true"
              className="grid size-14 place-items-center rounded-full"
              style={{
                background: `conic-gradient(from 225deg, var(--signal) ${(recommendedSpeed / maxSpeed) * 270}deg, var(--line-strong) 0 270deg, transparent 0)`,
              }}
            >
              <span className="num grid size-11 place-items-center rounded-full bg-[var(--panel)] text-xs font-semibold">
                {recommendedSpeed} kn
              </span>
            </div>
            <p className="text-center text-[10px] leading-tight text-[var(--text-3)]">
              Accepted advisory
              <br />
              <span className="sr-only">{recommendedSpeed} knots · </span>0–
              {maxSpeed} kn scale
            </p>
          </div>
        ) : (
          <p className="max-w-[7rem] text-right text-[11px] text-[var(--text-3)]">
            No speed from an accepted advisory
          </p>
        )}
      </div>
      <h3 className="eyebrow">Route weather · forecast</h3>
      {!weatherStatus.current ? (
        <p className="mt-0.5 text-[11px] text-[var(--text-3)]">
          {weatherStatus.latest}
        </p>
      ) : null}
      {worst ? (
        <>
          <p className="mt-0.5 text-[11px] text-[var(--text-3)]">
            {timeline.stripLabel ? `${timeline.stripLabel} · ` : ""}
            {weatherStatus.current
              ? `${formatUtc(new Date(timeline.from).toISOString())} · `
              : ""}
            Peak {worst.label} at +{Math.round(worst.leadHours)} h
          </p>
          <ol
            aria-label="Weather along the passage"
            tabIndex={0}
            className="mt-1 flex gap-1 overflow-x-auto pb-1"
          >
            {exposure.map((segment, index) => (
              <li
                key={index}
                className="min-w-max rounded border border-[var(--line)] px-1.5 py-1 text-[10px]"
                style={{
                  borderTopColor: `var(--${segment.level === "severe" ? "crit" : segment.level === "watch" ? "warn" : "info"})`,
                }}
              >
                <p className="num">+{Math.round(segment.leadHours)} h</p>
                <p>{segment.label}</p>
                {segment.windKn != null ? (
                  <p>{Math.round(segment.windKn)} kn wind</p>
                ) : null}
              </li>
            ))}
          </ol>
        </>
      ) : (
        <p className="text-xs text-[var(--text-3)]">
          No forecast coverage for this passage
        </p>
      )}
    </section>
  );
}
