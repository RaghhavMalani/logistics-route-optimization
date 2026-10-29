import { Pill } from "@/components/kit/primitives";
import type {
  CargoOptionAssessment,
  FrozenEnvironment,
} from "@/services/current-inputs";

import { cargoHours, cargoTime } from "./cargo-presentation";

export function CargoAssessmentStatus({
  assessment,
}: {
  assessment: CargoOptionAssessment | undefined;
}) {
  if (!assessment) return <>Unavailable in saved record</>;
  return (
    <>
      <Pill
        className="max-w-full whitespace-normal"
        tone={
          assessment.status === "BLOCKED"
            ? "crit"
            : assessment.status === "UNKNOWN"
              ? "warn"
              : "info"
        }
      >
        {assessment.status === "COMPATIBLE_UNDER_ASSUMPTIONS"
          ? "Compatible under assumptions"
          : assessment.status === "BLOCKED"
            ? "Blocked"
            : "Unknown"}
      </Pill>
      <span className="block">
        {[...assessment.reasons, ...assessment.missing]
          .slice(0, 1)
          .join("; ") ||
          "Declared timing and compatibility checks fit under assumptions."}
      </span>
      {assessment.requiredConstraint.required ? (
        <strong className="block">
          Required connection:{" "}
          {assessment.requiredConstraint.passed === true
            ? "fits under assumptions"
            : assessment.requiredConstraint.passed === false
              ? "fails"
              : "insufficient basis"}
        </strong>
      ) : (
        <span className="block">Context only · passage ranking unchanged</span>
      )}
    </>
  );
}

/** Shows the retained cargo arithmetic only; no forecast or schedule is filled from live state. */
export function CargoCommitmentEvidence({
  evidence,
}: {
  evidence: FrozenEnvironment;
}) {
  const declaration = evidence.cargoCommitment;
  const comparison = evidence.cargoComparison;
  if (!declaration || !comparison) return null;
  return (
    <details
      className="space-y-2 border-t border-[var(--line)] py-2"
      data-testid="frozen-cargo-comparison"
    >
      <summary>
        Cargo connection · stages, constraints and frozen evidence
      </summary>
      <p>
        Fictional shipment {declaration.shipment.shipmentId} ·{" "}
        {declaration.shipment.teu ?? "unknown"} TEU ·{" "}
        {declaration.shipment.cargoClass} ·{" "}
        {declaration.shipment.weightT ?? "unknown"} t · onward destination{" "}
        {declaration.shipment.destinationPort}. Bound voyage{" "}
        {declaration.voyageId} at {declaration.portCode}.
      </p>
      <p>
        {declaration.mustMeet
          ? "Explicit must-meet booked connection."
          : "Optional context; no change to passage ranking or approval eligibility."}{" "}
        Booked onward vessel {declaration.bookedConnection.name} (
        {declaration.bookedConnection.vesselId}). Latest departure{" "}
        {cargoTime(declaration.shipment.latestDepartureAt)}.
      </p>
      <p>
        Conditional clear approach +{" "}
        {cargoHours(declaration.transfer.approachToStartHours)} declared
        access/prerequisite interval → cargo-model start.{" "}
        {declaration.transfer.basis}
      </p>
      <p>
        The cargo model counts discharge, transfer overhead, yard moves when
        applicable and loading once. The start is before those handling stages.
        Handling is schematic and{" "}
        {declaration.transfer.acceptedSchematicHandling
          ? "explicitly accepted"
          : "not accepted"}{" "}
        for this scenario. Clear approach establishes no berth, all-fast,
        discharge completion or customs release.
      </p>
      <p>
        Relative simulation hour zero: {cargoTime(comparison.referenceAt)}.
        Aware timestamps convert through UTC; each option retains its own start
        and completion.
      </p>
      {comparison.options.map((assessment) => {
        const option = evidence.passageComparison?.options.find(
          (row) => row.optionId === assessment.optionId,
        );
        return (
          <section
            key={assessment.optionId}
            className="space-y-1 border-t border-[var(--line)] py-2"
            data-cargo-option={assessment.optionId}
          >
            <strong>{option?.label ?? assessment.optionId}</strong>
            <CargoAssessmentStatus assessment={assessment} />
            <dl className="grid grid-cols-2 gap-x-2 gap-y-1">
              <dt>Discharge / transfer start</dt>
              <dd>{cargoTime(assessment.startAt)}</dd>
              <dt>Total handling</dt>
              <dd>{cargoHours(assessment.handlingHours)}</dd>
              <dt>Conditional loading completion</dt>
              <dd>{cargoTime(assessment.readinessAt)}</dd>
              <dt>Declared loading cutoff</dt>
              <dd>{cargoTime(assessment.cutoffAt)}</dd>
              <dt>Signed cutoff slack</dt>
              <dd>{cargoHours(assessment.slackHours, true)}</dd>
              <dt>Booked onward departure</dt>
              <dd>{cargoTime(assessment.departureAt)}</dd>
              <dt>Timing under assumptions</dt>
              <dd>{assessment.timingStatus}</dd>
            </dl>
            {assessment.stages ? (
              <dl
                className="grid grid-cols-2 gap-x-2 gap-y-1"
                aria-label="Handling stages counted once"
              >
                <dt>Discharge</dt>
                <dd>{cargoHours(assessment.stages.dischargeHours)}</dd>
                <dt>Transfer overhead</dt>
                <dd>{cargoHours(assessment.stages.transferOverheadHours)}</dd>
                <dt>Yard moves</dt>
                <dd>{cargoHours(assessment.stages.yardMovesHours)}</dd>
                <dt>Loading</dt>
                <dd>{cargoHours(assessment.stages.loadHours)}</dd>
                <dt>Handling sum</dt>
                <dd>{cargoHours(assessment.stages.totalHandlingHours)}</dd>
              </dl>
            ) : null}
            {assessment.alternatives.length ? (
              <details>
                <summary>
                  Supported cargo-engine alternatives · proposals only
                </summary>
                <p>
                  These alternatives use the existing cargo decision engine and
                  this option's frozen cargo start. Declared later departures
                  and compatibility remain conditional. Nothing is booked,
                  reserved or executed by accepting the navigation advisory.
                </p>
                {assessment.alternatives.map((alternative) => (
                  <div
                    key={alternative.optionId}
                    className="border-t border-[var(--line)] py-1"
                  >
                    <strong>{alternative.label}</strong>
                    <p>
                      Onward vessel {alternative.vesselId}; conditional loading
                      completion {cargoTime(alternative.readinessAt)}; cutoff{" "}
                      {cargoTime(alternative.cutoffAt)}; slack{" "}
                      {cargoHours(alternative.slackHours, true)}.
                    </p>
                    <p>
                      Departure {cargoTime(alternative.departureAt)};{" "}
                      {cargoHours(alternative.departureShiftHours, true)} versus
                      booked sailing. {alternative.limitation}
                    </p>
                    <p>
                      Proposal only · not reserved · separate Company review
                      required.
                    </p>
                  </div>
                ))}
              </details>
            ) : (
              <p>
                {assessment.alternativesUnavailableBecause ??
                  "No supported later sailing retained for this assessment."}
              </p>
            )}
            <details>
              <summary>
                Inspect complete stage arithmetic and rule results
              </summary>
              <pre className="max-w-full whitespace-pre-wrap break-words">
                {JSON.stringify(assessment, null, 2)}
              </pre>
            </details>
          </section>
        );
      })}
      <p>
        Cargo costs remain partial or unavailable. No storage charge is inferred
        for time sailing or waiting at anchorage. Final delivery ETA and actual
        service improvement remain unavailable.
      </p>
      <p className="break-all">
        Adapter version {comparison.version} · frozen cargo input hash{" "}
        {comparison.inputVersion}. Passage evidence {evidence.evidenceId}.
      </p>
      <details>
        <summary>
          Inspect cargo declaration, capacity and source assumptions
        </summary>
        <pre className="max-w-full whitespace-pre-wrap break-words">
          {JSON.stringify(declaration, null, 2)}
        </pre>
      </details>
    </details>
  );
}
