import { exposureBand } from "@/lib/score-bands";

export const exposureBasis =
  "Exposure is a 0–1 index based on event severity, source confidence and time decay, with route or port adjustments. The index can reach its ceiling and is not a probability.";

export function ExposureScore({ value }: { value: number }) {
  if (!Number.isFinite(value)) return <span>Exposure unavailable</span>;
  return (
    <span title={exposureBasis}>
      Exposure {value.toFixed(2)} / 1 index · {exposureBand(value)}
    </span>
  );
}
