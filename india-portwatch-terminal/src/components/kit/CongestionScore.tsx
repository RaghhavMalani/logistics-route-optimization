import { Sparkline } from "@/components/kit/charts";
import { portPressureBand, portPressureBasis } from "@/lib/score-bands";
import type { HistoryPoint } from "@/types/portwatch";

function recentObservations(history: HistoryPoint[]) {
  const days = new Map<number, number>();
  for (const { date, value } of history) {
    if (date && value != null && Number.isFinite(value)) {
      const day = Date.parse(date.slice(0, 10));
      if (Number.isFinite(day)) days.set(day, value);
    }
  }
  const ordered = [...days].sort(([a], [b]) => a - b);
  const last = ordered.at(-1)?.[0] ?? 0;
  return ordered.filter(([day]) => day >= last - 6 * 86_400_000);
}

export function CongestionScore({
  value,
  history = [],
  compact = false,
}: {
  value: number | null | undefined;
  history?: HistoryPoint[];
  compact?: boolean;
}) {
  if (value == null || !Number.isFinite(value)) return <span>—</span>;
  const observations = recentObservations(history);
  const latest = observations.at(-1);
  const description = latest
    ? `Observed congestion, available observations from the seven days through ${new Date(latest[0]).toISOString().slice(0, 10)}`
    : undefined;
  return (
    <span
      title={portPressureBasis}
      className="inline-flex flex-wrap items-center justify-end gap-x-1.5"
    >
      <span className="num whitespace-nowrap">
        {value.toFixed(1)} / 100 pts
      </span>
      <span
        className={
          compact
            ? "text-xs text-[var(--text-3)]"
            : "whitespace-nowrap text-[var(--text-3)]"
        }
      >
        {portPressureBand(value)}
      </span>
      {observations.length > 1 && (
        <span
          title={description}
          aria-label={description}
          role="img"
          className="inline-block w-12"
        >
          <Sparkline
            data={observations.map(([, score]) => score)}
            height={14}
            fill={false}
          />
        </span>
      )}
    </span>
  );
}

export function CongestionForecastBand({
  low,
  high,
}: {
  low: number | null | undefined;
  high: number | null | undefined;
}) {
  if (
    low == null ||
    high == null ||
    !Number.isFinite(low) ||
    !Number.isFinite(high)
  )
    return <span>—</span>;
  const start = portPressureBand(low);
  const end = portPressureBand(high);
  return (
    <span
      title={portPressureBasis}
      className="inline-flex flex-wrap justify-end gap-x-1.5"
    >
      <span className="num whitespace-nowrap">
        {low.toFixed(0)}–{high.toFixed(0)} / 100 pts
      </span>
      <span className="whitespace-nowrap text-[var(--text-3)]">
        {start === end ? start : `${start}–${end}`}
      </span>
    </span>
  );
}
