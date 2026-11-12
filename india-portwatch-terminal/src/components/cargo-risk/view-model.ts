import type { CargoLoss, CargoTone } from "./types";

export const money = (value: number, currency: string) =>
  new Intl.NumberFormat("en", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);

export const percent = (value: number) =>
  new Intl.NumberFormat("en", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);

export function tone(loss: CargoLoss): CargoTone {
  if (
    (loss.onTime?.estimate ?? 1) < 0.5 ||
    (loss.spoilage?.estimate ?? 0) >= 0.5
  )
    return "crit";
  if (
    (loss.onTime?.estimate ?? 1) < 0.9 ||
    (loss.spoilage?.estimate ?? 0) >= 0.1
  )
    return "warn";
  return loss.onTime ? "ok" : "unknown";
}
