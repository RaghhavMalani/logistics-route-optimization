export const portPressureBasis =
  "Port pressure index · 0–100 points. 50 is this port’s own historical baseline for vessel calls.";

export function portPressureBand(value: number) {
  if (value < 40) return "Quiet";
  if (value <= 60) return "Normal";
  if (value <= 75) return "Busy";
  return "Severe";
}

export function exposureBand(value: number) {
  if (value < 0.3) return "Low";
  if (value < 0.55) return "Medium";
  return "High";
}
