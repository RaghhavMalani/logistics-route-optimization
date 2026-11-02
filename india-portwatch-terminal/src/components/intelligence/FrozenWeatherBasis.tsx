import { formatUtc } from "@/components/kit/primitives";
import type { FrozenEnvironment } from "@/services/current-inputs";
import { PassageComparison } from "./PassageComparison";

export function FrozenWeatherBasis({
  evidence,
}: {
  evidence: FrozenEnvironment;
}) {
  const first = evidence.consumedForecasts[0];
  return (
    <div
      className="pw-structured-evidence min-w-0 space-y-1 border-b border-[var(--line)] [overflow-wrap:anywhere]"
      data-testid="frozen-weather-basis"
    >
      <strong className="text-[var(--text)]">
        {evidence.evidenceKind === "SOFTWARE_LIFECYCLE_FIXTURE"
          ? "Frozen SOFTWARE forecast fixture"
          : "Frozen current-weather basis"}{" "}
        · {evidence.portCode}
      </strong>
      <p>
        Available {formatUtc(evidence.availableAt)}.{" "}
        {evidence.evidenceKind === "SOFTWARE_LIFECYCLE_FIXTURE"
          ? "Illustrative voyage and hourly source assumptions; not a provider forecast, measurement or actual port event."
          : "Provider issue time unavailable; forecast, not a station observation."}
      </p>
      <p>
        Consumed hour {formatUtc(first?.validAt)}: gust{" "}
        {first?.wind_gusts_10m ?? "unavailable"} kn; visibility{" "}
        {first?.visibility ?? "unavailable"} m.
      </p>
      <p>
        Assumed approach limits: gust ≤ {evidence.assumptions.maxGustKn} kn;
        visibility ≥ {evidence.assumptions.minVisibilityM} m; two clear hourly
        forecasts. {evidence.assumptions.scope}
      </p>
      {evidence.passageComparison ? (
        <PassageComparison evidence={evidence} />
      ) : (
        <>
          <p>
            Requested arrival {formatUtc(evidence.plannedArrival)} → clear
            approach {formatUtc(evidence.firstClearApproach)}.
          </p>
          <div
            className="overflow-x-auto"
            role="region"
            tabIndex={0}
            aria-label="Frozen arrival-window schedule, scroll horizontally for all measures"
          >
            <table className="w-full text-left">
              <caption className="text-left">
                Frozen option comparison · UTC
              </caption>
              <thead>
                <tr>
                  <th>Option</th>
                  <th>Requested arrival</th>
                  <th>Clear approach</th>
                  <th>Assumed anchorage wait</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Continue plan</td>
                  <td>{formatUtc(evidence.plannedArrival)}</td>
                  <td>{formatUtc(evidence.firstClearApproach)}</td>
                  <td>{evidence.forecastGateWaitHours.toFixed(1)} h</td>
                </tr>
                <tr>
                  <td>Later arrival window</td>
                  <td>{formatUtc(evidence.firstClearApproach)}</td>
                  <td>{formatUtc(evidence.firstClearApproach)}</td>
                  <td>0 h</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p>
            Overall approach timing is unchanged. Later arrival reduces assumed
            anchorage waiting; faster delivery and measured savings are not
            established. Fuel, cost, berth availability and calibrated
            uncertainty remain unavailable.
          </p>
        </>
      )}
      <p>
        Calculation: hourly gust and visibility, requested arrival and operator
        limits. GDACS hazards, wave overlays and activity are contextual layers;
        they do not change this gate calculation.
      </p>
      <details>
        <summary>Forecast hours used to find the approach window</summary>
        {evidence.consumedForecasts.map((row) => (
          <p key={row.validAt}>
            {formatUtc(row.validAt)} · gust{" "}
            {row.wind_gusts_10m ?? "unavailable"} kn · visibility{" "}
            {row.visibility ?? "unavailable"} m
          </p>
        ))}
      </details>
      {!evidence.passageComparison ? (
        <p>
          Without weather gate: {evidence.noWeatherGateWaitHours} h wait.
          Forecast gate: {evidence.forecastGateWaitHours.toFixed(1)} h assumed
          anchorage wait.
        </p>
      ) : null}
      {evidence.activityContext ? (
        <details data-testid="frozen-activity-context">
          <summary>
            Frozen activity context · no effect on this calculation
          </summary>
          <p>
            {evidence.activityContext.provider ?? "Provider unavailable"} ·{" "}
            {evidence.activityContext.sourceProductId ?? "Product unavailable"}.
            Observation period{" "}
            {evidence.activityContext.observedFrom ??
              evidence.activityContext.observationDate ??
              "unavailable"}
            {evidence.activityContext.observedThrough &&
            evidence.activityContext.observedThrough !==
              evidence.activityContext.observedFrom
              ? ` through ${evidence.activityContext.observedThrough}`
              : ""}
            ; precision {evidence.activityContext.datePrecision ?? "unknown"}.
            Daily dates are not measurement or publication instants.
          </p>
          <p>
            First application receipt{" "}
            {evidence.activityContext.firstAvailableAt
              ? formatUtc(evidence.activityContext.firstAvailableAt)
              : "unavailable"}
            . {evidence.activityContext.unknownReason}
          </p>
          <p className="break-all text-[var(--text-3)]">
            Projection {evidence.activityContext.projectionVersion} · source
            version {evidence.activityContext.sourceVersion ?? "unavailable"} ·
            receipt {evidence.activityContext.sourceReceiptId ?? "unavailable"}{" "}
            · original {evidence.activityContext.originalRef ?? "unavailable"} ·
            hash {evidence.activityContext.originalHash ?? "unavailable"}
          </p>
        </details>
      ) : (
        <p data-testid="frozen-activity-legacy">
          {evidence.activityObservation ??
            "Activity context was not retained in this frozen comparison."}
        </p>
      )}
      <p className="break-all text-[var(--text-3)]">
        Evidence {evidence.evidenceId} · snapshot {evidence.snapshotId}
      </p>
      <p>{evidence.meaning}</p>
      {evidence.portContextBindings?.map((binding) => (
        <details
          key={binding.revisionId}
          className="border-t border-[var(--line)] pt-2"
          data-testid="frozen-port-context"
        >
          <summary className="cursor-pointer font-medium">
            Reviewed port context · {binding.reportDate} ·{" "}
            {binding.metric.value ?? "unavailable"} {binding.metric.unit}
          </summary>
          <p>
            {binding.evidenceKind === "SOFTWARE_LIFECYCLE_FIXTURE"
              ? "SOFTWARE source fixture"
              : "Official public report context"}{" "}
            · {binding.rule.portCode} · {binding.metric.id.replaceAll("_", " ")}
            .
          </p>
          <p>
            Company operator criterion: reported rows ≥ {binding.rule.threshold}
            . {binding.rule.basis}.
          </p>
          <p>
            {binding.metric.asOf
              ? `Section snapshot ${formatUtc(binding.metric.asOf)}; timezone assumed Asia/Kolkata.`
              : `Section date ${binding.metric.dateScope?.date ?? "unknown"}; no observation/publication instant is invented.`}{" "}
            Context available {formatUtc(binding.availableAt)}.
          </p>
          <p>
            {binding.metric.meaning} This reviewed context changes no numerical
            weather, passage, cargo or cost calculation.
          </p>
          <p className="break-all">
            Revision {binding.revisionId} · original SHA-256{" "}
            {binding.originalSha256 ??
              "software fixture; no authority original"}{" "}
            · policy {binding.policyVersion ?? "retained in the source binding"}
            .
          </p>
        </details>
      ))}
    </div>
  );
}
