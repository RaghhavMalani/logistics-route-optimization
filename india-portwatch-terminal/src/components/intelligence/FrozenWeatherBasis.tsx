import { formatUtc } from "@/components/kit/primitives";
import type { FrozenEnvironment } from "@/services/current-inputs";

export function FrozenWeatherBasis({
  evidence,
}: {
  evidence: FrozenEnvironment;
}) {
  const first = evidence.consumedForecasts[0];
  return (
    <div
      className="space-y-1 border-b border-[var(--line)] px-2 py-2 text-[10.5px] text-[var(--text-2)]"
      data-testid="frozen-weather-basis"
    >
      <strong className="text-[var(--text)]">
        Frozen current-weather basis · {evidence.portCode}
      </strong>
      <p>
        Available {formatUtc(evidence.availableAt)}. Provider issue time
        unavailable; forecast, not a station observation.
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
      <p>
        Requested arrival {formatUtc(evidence.plannedArrival)} → clear approach{" "}
        {formatUtc(evidence.firstClearApproach)}.
      </p>
      <div className="overflow-x-auto">
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
        established. Fuel, cost, berth availability and calibrated uncertainty
        remain unavailable.
      </p>
      <p>
        Calculation: hourly gust and visibility, requested arrival and operator
        limits. GDACS hazards, wave overlays and stale activity are contextual
        layers; they do not change this gate calculation.
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
      <p>
        Without weather gate: {evidence.noWeatherGateWaitHours} h wait. Forecast
        gate: {evidence.forecastGateWaitHours.toFixed(1)} h assumed anchorage
        wait. October 2 activity input retains its age.
      </p>
      <p className="break-all text-[var(--text-3)]">
        Evidence {evidence.evidenceId} · snapshot {evidence.snapshotId}
      </p>
      <p>{evidence.meaning}</p>
    </div>
  );
}
