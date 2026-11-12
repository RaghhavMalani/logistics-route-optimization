export const exposureBasis =
  "Exposure is a 0–1 index based on event severity, source confidence and time decay, with route or port adjustments. The index can reach its ceiling and is not a probability.";

export function ExposureScore({ value }: { value: number }) {
  const band = value >= 0.55 ? "High" : value >= 0.3 ? "Medium" : "Low";
  return (
    <span title={exposureBasis}>
      Exposure {value.toFixed(2)} / 1 index · {band}
    </span>
  );
}
