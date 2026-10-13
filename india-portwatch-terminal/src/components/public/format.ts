export function utc(value?: string | null) {
  if (!value) return "Unavailable";
  // Benchmark daily partition boundaries are UTC calendar dates serialized by
  // pandas without an offset. Other source clocks retain their explicit zone.
  const timestamp =
    /^\d{4}-\d{2}-\d{2}T/.test(value) && !/(Z|[+-]\d{2}:?\d{2})$/.test(value)
      ? value + "Z"
      : value;
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime())
    ? "Unavailable"
    : date.toLocaleString("en-GB", {
        timeZone: "UTC",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }) + " UTC";
}
export const fmt = (value?: number | null, digits = 1) =>
  value == null
    ? "Unavailable"
    : value.toLocaleString("en-GB", { maximumFractionDigits: digits });
