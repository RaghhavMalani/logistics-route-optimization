import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson } from "@/services/api";
import { formatUtc } from "@/components/kit/primitives";
import type { WeatherInspection } from "@/services/intelligence";

interface Evidence {
  responseSha256: string;
  location?: { lat: number; lon: number };
  requestLocation?: { lat: number; lon: number };
  availableAt?: string;
  statistic: string;
  completeHours: number;
  representativeness?: string;
  measurementWindow?: { from: string; through: string; definition: string };
}
type Case = WeatherInspection & {
  statistic: string;
  rawError: number | null;
  forecastEvidence: Evidence | null;
  outcomeEvidence: Evidence | null;
};
interface Verification {
  independentTargets: number;
  independentResolvedTargets: number;
  reconciliation: {
    status: string;
    checkedAt?: string;
    nextEligibleAt?: string;
    conservativeLagDays?: number;
  };
  originalFiveDayCase: Case | null;
  retainedFiveDayCase: Case | null;
  latestMatchedCase?: Case | null;
  matchedContextCounts?: {
    forecastSnapshots: number;
    independentTargets: number;
    targetMeaning: string;
  };
  currentCandidate: {
    status: string;
    sampleCount: number;
    reason: string;
    partitions?: Record<string, number | string>;
    evaluationRawMae: number | null;
    evaluationCorrectedMae: number | null;
  };
  subsequentRecommendation: {
    status?: string;
    reason: string;
    forecastId?: string;
    targetDate?: string;
    variable?: string;
    rawValue?: number;
    consumedValue?: number;
    unit?: string;
    correctionConsumed?: boolean;
    correctionId?: string | null;
    recommendation?: string;
    rawRecommendation?: string;
    hourlyApproachEffect?: string;
    threshold?: number;
    thresholdDirection?: string;
    thresholdBasis?: string;
  };
}
export function WeatherVerificationPanel({
  portCode = "INNSA",
  variable = "wind_gust",
}: {
  portCode?: string;
  variable?: string;
}) {
  const { identityHeaders } = useAuth();
  const [source, setSource] = useState<string | null>(null);
  const [showRetained, setShowRetained] = useState(false);
  const [location, setLocation] = useState(portCode);
  const q = useQuery({
    queryKey: ["weather-verification", location, variable, identityHeaders],
    queryFn: ({ signal }) =>
      getJson<Verification>(
        `/weather/verification?portCode=${encodeURIComponent(location)}&variable=${variable}`,
        identityHeaders,
        { signal },
      ),
    staleTime: 30000,
  });
  const raw = useQuery({
    queryKey: ["weather-original", source, identityHeaders],
    queryFn: ({ signal }) =>
      getJson(`/weather/evidence/${source}`, identityHeaders, { signal }),
    enabled: !!source,
  });
  if (q.isPending)
    return <p className="text-xs">Reading original five-day archive…</p>;
  if (q.isError)
    return (
      <p role="alert" className="text-xs">
        Verification archive unavailable: {q.error.message}
      </p>
    );
  const data = q.data;
  const c = showRetained ? data.retainedFiveDayCase : data.originalFiveDayCase;
  const next = data.subsequentRecommendation;
  const matched = data.latestMatchedCase;
  return (
    <section
      className="border border-[var(--line)] p-2 my-2 text-[11px]"
      data-testid="weather-verification-chain"
    >
      <strong>
        Original five-day forecast → outcome → error → correction → subsequent
        watch
      </strong>
      <label className="block">
        Archive location{" "}
        <select
          aria-label="Weather verification location"
          className="bg-[var(--panel-2)]"
          value={location}
          onChange={(e) => {
            setLocation(e.target.value);
            setSource(null);
            setShowRetained(false);
          }}
        >
          {[
            "INIXY",
            "INMUN",
            "INNSA",
            "INBOM",
            "INMRM",
            "INNML",
            "INCOK",
            "INTUT",
            "INMAA",
            "INENR",
            "INVTZ",
            "INPRT",
            "INCCU",
          ].map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
      </label>
      {data.originalFiveDayCase &&
      !data.originalFiveDayCase.forecastEvidence ? (
        <p>
          The earliest historical claim has no preserved provider response or
          location/aggregation annotation. It remains in the ledger and cannot
          enter automatic verification or correction fitting without that
          provenance.
          {data.retainedFiveDayCase ? (
            <button
              className="underline ml-2"
              onClick={() => {
                setShowRetained(!showRetained);
                setSource(null);
              }}
            >
              {showRetained
                ? "Show earliest historical claim"
                : "Inspect earliest five-day claim with retained response"}
            </button>
          ) : null}
        </p>
      ) : null}
      {showRetained ? (
        <p>
          Showing the earliest complete retained-response claim; the earlier
          historical claim is preserved separately.
        </p>
      ) : null}
      <p>
        {data.independentResolvedTargets} independent resolved targets /{" "}
        {data.independentTargets} independent archived targets. Repeated
        receipts do not add targets.
      </p>
      <p>
        Automatic reconciliation: {data.reconciliation.status} · checked{" "}
        {formatUtc(data.reconciliation.checkedAt ?? null)} · earliest eligible{" "}
        {formatUtc(data.reconciliation.nextEligibleAt ?? null)}.
      </p>
      <p>
        ERA5 is gridded reanalysis, distinct from station measurements. Six-day
        eligibility is conservative; only a complete 24-hour returned outcome
        can match.
      </p>
      {matched ? (
        <details
          className="my-2 border border-[var(--line)] p-2"
          data-testid="weather-latest-matched-case"
        >
          <summary>Inspect a matched forecast and later ERA5 outcome</summary>
          <p>
            {matched.portCode} · {matched.variable.replaceAll("_", " ")} · +
            {matched.horizonDays}d · UTC target {matched.targetDate} ·{" "}
            {matched.statistic}. Original forecast {matched.original.toFixed(2)}{" "}
            {matched.unit} → later ERA5 {matched.observed?.toFixed(2)}{" "}
            {matched.unit} → error (forecast − outcome){" "}
            {matched.rawError?.toFixed(2)} {matched.unit}.
          </p>
          <p>
            Forecast first received {formatUtc(matched.issuedAt)}; outcome first
            received {formatUtc(matched.observedAt)}. The outcome is gridded
            reanalysis, not a station measurement. Provider publication time is
            unknown.
          </p>
          <p>
            {data.matchedContextCounts?.independentTargets ?? "—"} independent
            matched targets for this location and variable across{" "}
            {data.matchedContextCounts?.forecastSnapshots ?? "—"} forecast
            snapshots. Repeated snapshots share a target. This case is separate
            from the five-day example below.
          </p>
          <p>
            Original correction status: {matched.correction.status}. Current +5d
            candidate: {data.currentCandidate.status}.
            {next.correctionConsumed
              ? " A separately validated correction is identified in the subsequent watch below."
              : " No learned correction is consumed by the subsequent watch."}
            Daily results do not alter hourly gust or visibility decisions.
          </p>
          <p>
            Requested forecast location:{" "}
            {matched.forecastEvidence?.requestLocation?.lat},{" "}
            {matched.forecastEvidence?.requestLocation?.lon}; outcome grid:{" "}
            {matched.outcomeEvidence?.location?.lat},{" "}
            {matched.outcomeEvidence?.location?.lon}.
            {matched.outcomeEvidence?.representativeness}
          </p>
          {matched.outcomeEvidence?.measurementWindow ? (
            <p>
              Outcome aggregation:{" "}
              {formatUtc(matched.outcomeEvidence.measurementWindow.from)} →{" "}
              {formatUtc(matched.outcomeEvidence.measurementWindow.through)}.{" "}
              {matched.outcomeEvidence.measurementWindow.definition}
            </p>
          ) : null}
          {[
            ["forecast", matched.forecastEvidence],
            ["ERA5 outcome", matched.outcomeEvidence],
          ].map(([label, evidence]) =>
            evidence && typeof evidence !== "string" ? (
              <button
                key={evidence.responseSha256}
                className="underline mr-3"
                onClick={() => setSource(evidence.responseSha256)}
              >
                Inspect matched {label as string} source response
              </button>
            ) : null,
          )}
        </details>
      ) : null}
      {c ? (
        <>
          <p>
            Original {c.provider} · {c.portCode} · +{c.horizonDays}d · receipt{" "}
            {formatUtc(c.issuedAt)} → UTC target {c.targetDate}.{" "}
            {c.variable.replaceAll("_", " ")}:{" "}
            <strong>
              {c.original.toFixed(2)} {c.unit}
            </strong>
            .
          </p>
          <p>
            Outcome:{" "}
            {c.observed == null
              ? "Awaiting an eligible later outcome; a newer forecast cannot verify this claim."
              : `${c.observed.toFixed(2)} ${c.unit} · ${c.observationSource} · first available ${formatUtc(c.observedAt)}`}
          </p>
          <p>
            Error (forecast − outcome): {c.rawError?.toFixed(2) ?? "Pending"}{" "}
            {c.unit}. Original correction: {c.correction.status}.
          </p>
          <p>
            Forecast location:{" "}
            {c.forecastEvidence?.requestLocation
              ? `${c.forecastEvidence.requestLocation.lat}, ${c.forecastEvidence.requestLocation.lon}`
              : "Original location annotation unavailable"}
            ; {c.forecastEvidence?.statistic ?? "daily aggregate"};{" "}
            {c.forecastEvidence?.completeHours ?? "unknown"} hours.
          </p>
          {c.forecastEvidence?.measurementWindow ? (
            <p>
              Measurement window:{" "}
              {formatUtc(c.forecastEvidence.measurementWindow.from)} →{" "}
              {formatUtc(c.forecastEvidence.measurementWindow.through)}.{" "}
              {c.forecastEvidence.measurementWindow.definition}
            </p>
          ) : null}
          {c.outcomeEvidence ? (
            <p>
              Outcome grid: {c.outcomeEvidence.location?.lat},{" "}
              {c.outcomeEvidence.location?.lon}.{" "}
              {c.outcomeEvidence.representativeness}
            </p>
          ) : null}
          {[c.forecastEvidence, c.outcomeEvidence]
            .filter((e): e is Evidence => !!e)
            .map((e, i) => (
              <button
                key={e.responseSha256}
                className="underline mr-3"
                onClick={() => setSource(e.responseSha256)}
              >
                Inspect {i === 0 ? "forecast" : "outcome"} source response
              </button>
            ))}
        </>
      ) : (
        <p>No original +5 day claim for this location and variable.</p>
      )}
      <p>
        Current correction candidate:{" "}
        <strong>{data.currentCandidate.status}</strong> ·{" "}
        {data.currentCandidate.sampleCount} independent outcomes.{" "}
        {data.currentCandidate.reason}
      </p>
      {data.currentCandidate.partitions ? (
        <p>
          Partitions: {JSON.stringify(data.currentCandidate.partitions)}.
          Subsequent evaluation MAE:{" "}
          {data.currentCandidate.evaluationRawMae ?? "unavailable"} →{" "}
          {data.currentCandidate.evaluationCorrectedMae ?? "unavailable"}.
        </p>
      ) : null}
      <p>
        Subsequent daily watch: {next.forecastId ?? "Unavailable"} ·{" "}
        {next.targetDate} · raw {next.rawValue ?? "—"} → consumed{" "}
        {next.consumedValue ?? "—"} {next.unit}. Correction{" "}
        {next.correctionConsumed
          ? `consumed (${next.correctionId})`
          : "not consumed"}
        ; {next.rawRecommendation} → {next.recommendation}. {next.reason}
      </p>
      {next.threshold != null ? (
        <p>
          Research watch assumption: review {next.thresholdDirection}{" "}
          {next.threshold} {next.unit}; {next.thresholdBasis}.
        </p>
      ) : null}
      <p>
        {next.hourlyApproachEffect ??
          "Daily results never modify the hourly approach gate."}
      </p>
      {source ? (
        <details open className="max-h-48 overflow-auto">
          <summary>Preserved source response · {source}</summary>
          {raw.isError ? (
            <p>Source response unavailable.</p>
          ) : (
            <pre className="whitespace-pre-wrap break-all">
              {JSON.stringify(raw.data, null, 2)}
            </pre>
          )}
        </details>
      ) : null}
    </section>
  );
}
