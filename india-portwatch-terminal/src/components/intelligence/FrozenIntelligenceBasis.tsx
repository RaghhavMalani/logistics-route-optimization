import { formatUtc } from "@/components/kit/primitives";
import { FrozenFeedback } from "./SharedFeedbackPanel";
import type { FeedbackConsumption } from "@/services/sharedFeedback";

export interface IntelligenceBasis {
  feedbackConsumption?: FeedbackConsumption;
  kind: "INTELLIGENCE_SCENARIO" | "NOTICE_RESTRICTION";
  portCode: string;
  evidenceId: string;
  plannedArrival: string;
  firstClearApproach?: string;
  restriction?: {
    sourceFamily?: string;
    requestedPassage: string;
    earliestScheduledAccess: string;
    calculatedWaitHours: number;
    totalScheduleShiftHours: number;
    condition: string;
    revisionId: string;
    plan: {
      postPassageHours: number;
      characteristics: {
        loaM: number;
        beamM: number;
        draughtM: number;
        airDraughtM: number;
      };
      direction: string;
      alternativeAccess: string;
    };
  };
  reportedFact: {
    title: string;
    fact: string;
    status: string;
    source: string;
    mechanism: string;
    relationship: string;
    availableAt: string;
    publishedAt?: string;
    observedAt?: string;
    validThrough?: string;
    responseSha256: string;
    pdfSha256?: string;
    pdfSource?: string;
    publishedDate?: string;
    providerCreatedAt?: string;
    providerModifiedAt?: string;
    publicationPrecision?: string;
    withdrawsAt?: string;
    unaffectedAlternative?: string;
    applicability?: { characteristicRule: string };
  };
  inferredExposure: {
    route: string;
    port: string;
    vessel: string;
    cargo: string;
    basis: string;
  };
  assumptions: {
    assumedHoldHours?: number;
    purpose: string;
    doesNotAssert: string;
  };
}

export function FrozenIntelligenceBasis({
  evidence,
}: {
  evidence: IntelligenceBasis;
}) {
  const fact = evidence.reportedFact;
  const restriction = evidence.restriction;
  const bridge = restriction?.sourceFamily === "NAVCEN_MSI";
  if (evidence.kind === "NOTICE_RESTRICTION" && restriction)
    return (
      <section
        className="space-y-2 border-b border-[var(--line)] p-2 text-[11px]"
        data-testid="frozen-restriction-basis"
      >
        <strong>Frozen authority restriction · {fact.title}</strong>
        <FrozenFeedback consumed={evidence.feedbackConsumption} />
        <p>Published fact: {fact.fact}</p>
        <p>
          {bridge
            ? `Publication instant unverified; provider metadata ${fact.providerModifiedAt ?? "unavailable"}`
            : `Published ${fact.publishedDate} (date precision)`}{" "}
          · first receipt {formatUtc(fact.availableAt)} · scheduled withdrawal{" "}
          {formatUtc(fact.withdrawsAt ?? null)}.
        </p>
        <a
          className="underline"
          href={fact.pdfSource ?? fact.source}
          target="_blank"
          rel="noreferrer"
        >
          Authority original
        </a>
        <p>
          Affected declared voyage: {evidence.inferredExposure.vessel} ·{" "}
          {evidence.inferredExposure.route}. Cargo:{" "}
          {evidence.inferredExposure.cargo}. {evidence.inferredExposure.basis}
        </p>
        <p>
          Declared characteristics: length{" "}
          {restriction.plan.characteristics.loaM} m · beam{" "}
          {restriction.plan.characteristics.beamM} m · draught{" "}
          {restriction.plan.characteristics.draughtM} m · air draught{" "}
          {restriction.plan.characteristics.airDraughtM} m.{" "}
          {fact.applicability?.characteristicRule}
        </p>
        <p>{fact.unaffectedAlternative}</p>
        <div
          className="overflow-x-auto"
          role="region"
          aria-label="Restriction timing comparison; scroll horizontally for all columns"
          tabIndex={0}
        >
          <table className="w-full min-w-[680px] text-left [&_td]:whitespace-nowrap [&_td]:px-2 [&_td]:py-1 [&_th]:px-2 [&_th]:py-1">
            <caption className="text-left">
              Conditional scheduled comparison · times UTC
            </caption>
            <thead>
              <tr>
                <th>Option</th>
                <th>Requested passage</th>
                <th>Requested destination arrival</th>
                <th>
                  {bridge
                    ? "Published restriction ends"
                    : "First published operational tide"}
                </th>
                <th>{bridge ? "Planned bridge wait" : "Planned lock wait"}</th>
                <th>Total schedule shift</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Current request</td>
                <td>{formatUtc(restriction.requestedPassage)}</td>
                <td>{formatUtc(evidence.plannedArrival)}</td>
                <td>{formatUtc(restriction.earliestScheduledAccess)}</td>
                <td>{restriction.calculatedWaitHours.toFixed(2)} h</td>
                <td>{restriction.totalScheduleShiftHours.toFixed(2)} h</td>
              </tr>
              <tr>
                <td>Revised request</td>
                <td>{formatUtc(restriction.earliestScheduledAccess)}</td>
                <td>{formatUtc(evidence.firstClearApproach ?? null)}</td>
                <td>{formatUtc(restriction.earliestScheduledAccess)}</td>
                <td>0 h</td>
                <td>{restriction.totalScheduleShiftHours.toFixed(2)} h</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-[var(--text-3)]">
          Scroll the timing table horizontally to inspect every column.
        </p>
        <p>
          Both options reach the same conditional destination arrival{" "}
          {formatUtc(evidence.firstClearApproach ?? null)}. Fixed onward
          duration {restriction.plan.postPassageHours} h is operator-assumed.
          Revised timing relocates planned waiting; it does not imply faster
          delivery.
        </p>
        <p>
          {restriction.condition} Actual earliest permitted access is
          unavailable. Alternate access, berth, fuel, cost, clearance and safety
          benefits are unavailable.
        </p>
        <p className="break-all text-[var(--text-3)]">
          Evidence {evidence.evidenceId} · notice revision{" "}
          {restriction.revisionId} · original{" "}
          {fact.pdfSha256 ?? fact.responseSha256}
        </p>
      </section>
    );
  return (
    <section
      className="space-y-1 border-b border-[var(--line)] p-2 text-[11px]"
      data-testid="frozen-intelligence-basis"
    >
      <strong>Frozen intelligence comparison · {evidence.portCode}</strong>
      <FrozenFeedback consumed={evidence.feedbackConsumption} />
      <p>
        Reported evidence · {fact.status}: {fact.fact}
      </p>
      <p>
        Source observation/publication{" "}
        {formatUtc(fact.observedAt ?? fact.publishedAt ?? null)} · first receipt{" "}
        {formatUtc(fact.availableAt)}
        {fact.validThrough
          ? ` · valid through ${formatUtc(fact.validThrough)}`
          : ""}
        .
      </p>
      <a
        className="underline"
        href={fact.source}
        target="_blank"
        rel="noreferrer"
      >
        Source report
      </a>
      <p>Transmission mechanism: {fact.mechanism}</p>
      <p>
        Inferred exposure: {evidence.inferredExposure.vessel} · route{" "}
        {evidence.inferredExposure.route} · port{" "}
        {evidence.inferredExposure.port} · cargo{" "}
        {evidence.inferredExposure.cargo}. {evidence.inferredExposure.basis}
      </p>
      <p>
        Operator demo assumption: {evidence.assumptions.assumedHoldHours} h
        review hold to {evidence.assumptions.purpose.toLowerCase()}. Continue
        plan at {formatUtc(evidence.plannedArrival)}, or request arrival{" "}
        {evidence.assumptions.assumedHoldHours} h later.
      </p>
      <p>
        {evidence.assumptions.doesNotAssert}. Event-caused delay, fuel, cost,
        berth availability and calibrated uncertainty remain unavailable. The
        faster schedule alone does not establish which action is operationally
        preferable.
      </p>
      <p className="break-all text-[var(--text-3)]">
        Evidence {evidence.evidenceId} · response {fact.responseSha256}
      </p>
    </section>
  );
}
