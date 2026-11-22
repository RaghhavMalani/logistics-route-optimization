import { formatUtc } from "@/components/kit/primitives";
import { ageLabel } from "@/services/source-health";

export interface ForecastClocks {
  checkedAt?: string | null;
  forecastIssuedAt?: string | null;
  forecastIssueBasis?: string | null;
  checkPolicySeconds?: number | null;
  modelUpdateSeconds?: number;
  issueMarginSeconds?: number;
}

export function forecastIsCurrent(
  source: ForecastClocks & { status: string },
  now: number,
) {
  const checkedAge = now - Date.parse(source.checkedAt ?? "");
  const issuedAge = now - Date.parse(source.forecastIssuedAt ?? "");
  return (
    source.status === "CURRENT" &&
    checkedAge >= 0 &&
    checkedAge <= (source.checkPolicySeconds ?? 5400) * 1000 &&
    issuedAge >= 0 &&
    issuedAge <=
      ((source.modelUpdateSeconds ?? 21600) +
        (source.issueMarginSeconds ?? 7200)) *
        1000
  );
}

export function forecastReceiptLabel(
  source: ForecastClocks,
  current: boolean,
  now = Date.now(),
) {
  const checkedAt = Date.parse(source.checkedAt ?? "");
  const estimate =
    source.forecastIssueBasis === "VALUES_LAST_CHANGED" ? "~" : "";
  const checked = Number.isFinite(checkedAt)
    ? ageLabel(Math.max(0, (now - checkedAt) / 1000))
    : "unknown";
  return `Checked ${checked} ago · forecast issued ${estimate}${formatUtc(source.forecastIssuedAt)} (${current ? "latest available" : "stale"})`;
}
