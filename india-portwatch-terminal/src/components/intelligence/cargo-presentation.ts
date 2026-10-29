import { formatUtc } from "@/components/kit/primitives";

export const cargoTime = (value: string | null | undefined) =>
  value ? formatUtc(value) : "Unavailable";

export const cargoHours = (value: number | null | undefined, signed = false) =>
  value != null && Number.isFinite(value)
    ? `${signed && value > 0 ? "+" : ""}${Number(value.toFixed(2))} h`
    : "Unavailable";
