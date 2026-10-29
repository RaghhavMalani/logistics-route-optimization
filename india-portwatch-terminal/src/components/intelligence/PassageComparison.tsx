import { formatUtc } from "@/components/kit/primitives";
import { CargoCommitmentEvidence } from "./CargoCommitmentEvidence";
import type {
  FrozenEnvironment,
  PassageOptionComparison,
} from "@/services/current-inputs";

const hours = (value: number | null | undefined, signed = false) =>
  value == null || !Number.isFinite(value)
    ? "Unavailable"
    : `${signed && value > 0 ? "+" : ""}${value.toFixed(2)} h`;
const tonnes = (value: number | null | undefined, signed = false) =>
  value == null || !Number.isFinite(value)
    ? "Unavailable"
    : `${signed && value > 0 ? "+" : ""}${value.toFixed(3)} t`;
const money = (
  value: { amount: number; currency: string } | null | undefined,
  signed = false,
) =>
  value
    ? `${signed && value.amount > 0 ? "+" : ""}${value.amount.toFixed(2)} ${value.currency}`
    : "Unavailable";

function OptionEvidence({ option }: { option: PassageOptionComparison }) {
  return (
    <details className="border-t border-[var(--line)] py-1">
      <summary>
        {option.label} · inspect fuel, component costs and forecast hours
      </summary>
      {option.reason ? <p>{option.reason}</p> : null}
      {option.speedChangeAt ? (
        <p>
          Speed choice from {formatUtc(option.speedChangeAt)}; future sailing{" "}
          {hours(option.futureSailingHours)}. The elapsed segment (
          {hours(option.commonElapsedSailingHours)}) is unchanged.
        </p>
      ) : null}
      {option.requestedWindowWaitHours != null ||
      option.forecastGateWaitHours != null ? (
        <p>
          Operator requested-window wait{" "}
          {hours(option.requestedWindowWaitHours)}; subsequent hourly forecast
          gate wait {hours(option.forecastGateWaitHours)}. Both contribute to
          the displayed total anchorage wait.
        </p>
      ) : null}
      {option.fuel ? (
        <>
          <p>
            Modeled fuel {tonnes(option.fuel.totalTonnes)} ·{" "}
            {option.fuel.available
              ? "declared modes complete"
              : "incomplete; unknown modes are not zero"}
            . {option.fuel.meaning}
          </p>
          <p>Consumption relation: {option.fuel.formula}</p>
          <p>
            Operator source: {option.fuel.consumption.source ?? "unavailable"}.
            Load: {option.fuel.consumption.loadCondition ?? "unavailable"}.
            Declared {formatUtc(option.fuel.consumption.declaredAt)}.
          </p>
          <ul className="list-disc pl-4">
            {Object.entries(option.fuel.modes).map(([key, mode]) => (
              <li key={key}>
                {key}: {tonnes(mode.tonnes)} over {hours(mode.hours)}.{" "}
                {mode.basis ?? mode.unknownBecause}
                {mode.propulsionTonnes != null || mode.auxiliaryTonnes != null
                  ? ` Propulsion ${tonnes(mode.propulsionTonnes)}; auxiliary ${tonnes(mode.auxiliaryTonnes)}.`
                  : ""}
                {mode.segments?.map((segment) => (
                  <p key={segment.index}>
                    Sailing segment {segment.index + 1}: {hours(segment.hours)}{" "}
                    at {segment.speedKn ?? "unavailable"} kn ·{" "}
                    {tonnes(segment.tonnes)}.{" "}
                    {segment.basis ?? segment.unknownBecause}
                  </p>
                ))}
              </li>
            ))}
          </ul>
          {option.fuel.missingInputs.length ? (
            <p>
              Missing consumption inputs: {option.fuel.missingInputs.join("; ")}
            </p>
          ) : null}
          {option.fuel.assumptions.map((text, index) => (
            <p key={index}>{text}</p>
          ))}
        </>
      ) : (
        <p>
          Fuel unavailable; no supported consumption calculation retained for
          this option.
        </p>
      )}
      {option.finance ? (
        <>
          <p>
            {option.finance.complete
              ? "Complete modeled cost"
              : "PARTIAL modeled cost — not total voyage cost"}
            :{" "}
            {money(
              option.finance.complete
                ? option.finance.total
                : option.finance.partialTotal,
            )}
            . Operator assumptions; no measured saving or cheapest-plan claim.
          </p>
          <div
            className="max-w-full overflow-x-auto"
            role="region"
            tabIndex={0}
            aria-label={`${option.label} component costs, scroll horizontally for all measures`}
          >
            <table className="w-full text-left">
              <caption className="text-left">
                Modeled variable components and unavailable costs
              </caption>
              <thead>
                <tr>
                  <th scope="col">Component</th>
                  <th scope="col">State</th>
                  <th scope="col">Quantity</th>
                  <th scope="col">Amount</th>
                  <th scope="col">Basis / missing input</th>
                </tr>
              </thead>
              <tbody>
                {option.finance.components.map((component) => (
                  <tr
                    key={component.key}
                    className="border-t border-[var(--line)] align-top"
                  >
                    <th scope="row" className="font-normal">
                      {component.label}
                    </th>
                    <td>{component.state}</td>
                    <td>
                      {component.quantity
                        ? `${component.quantity.value.toFixed(3)} ${component.quantity.unit}`
                        : component.state === "ZERO"
                          ? "0 · not incurred"
                          : "Unavailable"}
                    </td>
                    <td>
                      {component.state === "ZERO"
                        ? "0 · not incurred"
                        : money(component.money)}
                    </td>
                    <td>
                      {component.reason || component.basis}
                      {component.isAssumption ? " · USER ASSUMPTION" : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {option.finance.notes.map((note, index) => (
            <p key={index}>{note}</p>
          ))}
        </>
      ) : (
        <p>Cost unavailable; no priced evaluation retained.</p>
      )}
      {option.delta ? (
        <div className="space-y-1">
          <p>
            Signed differences: option minus baseline. Fuel{" "}
            {tonnes(option.delta.fuelTonnes.value, true)}.{" "}
            {option.delta.fuelTonnes.unknownBecause}
          </p>
          {option.delta.components.map((component) => (
            <p key={component.key}>
              {component.label}:{" "}
              {component.available
                ? money(component.money, true)
                : "Unavailable"}
              . {component.basis ?? component.unknownBecause}
            </p>
          ))}
          <p>{option.delta.meaning}</p>
        </div>
      ) : null}
      <details>
        <summary>Hourly gust and visibility consumed for this option</summary>
        {(option.consumedForecasts ?? []).length ? (
          option.consumedForecasts?.map((row) => (
            <p key={row.validAt}>
              {formatUtc(row.validAt)} · gust{" "}
              {row.wind_gusts_10m ?? "unavailable"} kn · visibility{" "}
              {row.visibility ?? "unavailable"} m
            </p>
          ))
        ) : (
          <p>No usable approach forecast hours retained for this option.</p>
        )}
      </details>
    </details>
  );
}

/** Renders server-frozen consequences; never recomputes shipping physics in the browser. */
export function PassageComparison({
  evidence,
}: {
  evidence: FrozenEnvironment;
}) {
  const comparison = evidence.passageComparison;
  if (!comparison) return null;
  const plan = evidence.passagePlan;
  return (
    <div className="min-w-0 space-y-2" data-testid="frozen-passage-comparison">
      <strong className="text-[var(--text)]">
        Declared passage → conditional approach comparison
      </strong>
      <p>
        {comparison.distanceNm.toFixed(3)} nm · {comparison.distanceBasis}.
        Reference {formatUtc(comparison.referenceAt)}. Requested approach{" "}
        {formatUtc(comparison.requestedApproachAt)}.
      </p>
      {comparison.calculationAt ? (
        <p>
          Calculation at {formatUtc(comparison.calculationAt)}. Common elapsed
          sailing {hours(comparison.commonElapsedSailingHours)} /{" "}
          {comparison.commonElapsedDistanceNm?.toFixed(3) ?? "unavailable"} nm;
          remaining distance then{" "}
          {comparison.remainingDistanceAtCalculationNm?.toFixed(3) ??
            "unavailable"}{" "}
          nm. {comparison.projectionBasis}
        </p>
      ) : null}
      <p>
        {plan?.referenceLabel} · {comparison.geometryBasis}. Declared inputs are
        operator assumptions. Forecast source facts remain separately dated
        above.
      </p>
      <div
        className="max-w-full overflow-x-auto"
        role="region"
        tabIndex={0}
        aria-label="Passage schedule comparison, scroll horizontally for all measures"
      >
        <table
          className="w-full whitespace-nowrap text-left"
          data-testid="passage-schedule-table"
        >
          <caption className="text-left">
            Frozen option timelines · UTC · signed shifts against current plan
          </caption>
          <thead>
            <tr>
              <th scope="col">Plan / status</th>
              <th scope="col">Speed</th>
              <th scope="col">Departure / reference</th>
              <th scope="col">Sailing</th>
              <th scope="col">Departure hold</th>
              <th scope="col">Approach arrival</th>
              <th scope="col">Anchorage wait</th>
              <th scope="col">Conditional clear approach</th>
              <th scope="col">Total elapsed</th>
              <th scope="col">Schedule shift</th>
              <th scope="col">Declared approach deadline</th>
            </tr>
          </thead>
          <tbody>
            {comparison.options.map((option) => (
              <tr
                key={option.optionId}
                className="border-t border-[var(--line)] align-top"
                data-passage-option={option.optionId}
              >
                <th
                  scope="row"
                  className="max-w-60 whitespace-normal font-normal"
                >
                  {option.label}
                  <br />
                  {option.status}
                  {option.reason ? (
                    <p className="max-w-60 whitespace-normal">
                      {option.reason}
                    </p>
                  ) : null}
                </th>
                <td>
                  {option.speedKn == null
                    ? "Unavailable"
                    : `${option.speedKn.toFixed(3)} kn`}
                </td>
                <td>
                  {formatUtc(option.departureAt ?? comparison.referenceAt)}
                </td>
                <td>{hours(option.sailingHours)}</td>
                <td>{hours(option.departureHoldHours)}</td>
                <td>{formatUtc(option.arrivalAt)}</td>
                <td>{hours(option.anchorageWaitHours)}</td>
                <td>{formatUtc(option.approachClearAt)}</td>
                <td>{hours(option.totalElapsedHours)}</td>
                <td>{hours(option.scheduleShiftHours, true)}</td>
                <td>
                  {option.deadlineAt ? (
                    <>
                      {formatUtc(option.deadlineAt)}
                      <br />
                      {option.deadlineMet == null
                        ? "Not evaluated"
                        : option.deadlineMet
                          ? "Within declared deadline"
                          : "MISSES DECLARED DEADLINE"}
                    </>
                  ) : (
                    "Not declared"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        Clear approach is conditional on these port-hour forecasts and assumed
        limits. It establishes neither faster delivery, whole-route safety,
        berth access nor an official clearance. Lower modeled fuel does not
        excuse a deadline miss.
      </p>
      {comparison.limitations.map((text, index) => (
        <p key={index}>{text}</p>
      ))}
      {comparison.options.map((option) => (
        <OptionEvidence key={option.optionId} option={option} />
      ))}
      <CargoCommitmentEvidence evidence={evidence} />
      <details>
        <summary>
          Inspect frozen passage declaration, consumption and rate provenance
        </summary>
        <p>
          Baseline arrival {formatUtc(comparison.baselineArrivalAt)}. Input
          declaration {formatUtc(plan?.declaredAt)}. No live metadata is
          substituted into this frozen record.
        </p>
        {comparison.inputVersion ? (
          <p className="break-all">
            Frozen input version {comparison.inputVersion}
          </p>
        ) : null}
        <pre className="max-w-full whitespace-pre-wrap break-words">
          {JSON.stringify(
            plan ?? { unavailable: "Original passage declaration unavailable" },
            null,
            2,
          )}
        </pre>
      </details>
    </div>
  );
}
