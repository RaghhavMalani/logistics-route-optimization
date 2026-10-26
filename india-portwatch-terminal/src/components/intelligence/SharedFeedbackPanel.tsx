import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getBlob, getJson, postJson } from "@/services/api";
import type {
  FeedbackClaim,
  FeedbackConsumption,
  FeedbackEvidence,
  FeedbackInspection,
} from "@/services/sharedFeedback";
import type { DecisionProblem } from "@/types/decisions";
import type { CompanyFleet } from "@/types/portwatch-os";
import { Button } from "@/components/ui/button";
import { formatUtc } from "@/components/kit/primitives";

const number = (value: unknown, signed = false) =>
  typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("en-US", {
        maximumFractionDigits: 4,
        signDisplay: signed ? "exceptZero" : "auto",
      })
    : "Unavailable";
const clock = (value: string | null | undefined) =>
  value && Number.isFinite(Date.parse(value))
    ? `${formatUtc(value)} ${new Date(value).getUTCFullYear()}`
    : "Unavailable";

function period(claim: FeedbackClaim) {
  const reported = claim.target.reportedPeriod;
  return (
    claim.target.date ??
    (claim.target.from
      ? `${claim.target.from} through ${claim.target.through ?? "unknown end"}`
      : typeof reported === "string"
        ? reported
        : reported
          ? `${reported.from ?? "unknown start"} through ${reported.through ?? "unknown end"} (${reported.precision ?? "precision unavailable"})`
          : "Reporting period unknown")
  );
}

function OriginalResponse({
  digest,
  label = "Download retained original response",
}: {
  digest?: string;
  label?: string;
}) {
  const valid = !!digest && /^[a-f0-9]{64}$/.test(digest);
  const original = useMutation({
    mutationFn: async () => {
      if (!valid) throw new Error("Original hash is unavailable.");
      const blob = await getBlob(`/intelligence/feedback/evidence/${digest}`);
      const hash = Array.from(
        new Uint8Array(
          await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()),
        ),
      )
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");
      if (hash !== digest)
        throw new Error(
          "Retained original hash does not match; download withheld.",
        );
      return blob;
    },
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob),
        link = document.createElement("a");
      link.href = url;
      link.download = `${digest}.response`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
  });
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        className="h-auto min-h-8 max-w-full whitespace-normal text-left"
        disabled={!valid || original.isPending}
        onClick={() => original.mutate()}
      >
        {label}
      </Button>
      {original.isError ? (
        <p role="alert">Original unavailable: {original.error.message}</p>
      ) : null}
    </>
  );
}

function EvidenceSummary({ evidence }: { evidence: FeedbackEvidence }) {
  return (
    <li className="space-y-1 border-t border-[var(--line)] py-2">
      <p>
        {evidence.source ?? "Source unavailable"} ·{" "}
        {evidence.recordKind ?? evidence.sourceRole ?? "Retained evidence"}
      </p>
      <p>First available to PortWatch {clock(evidence.firstAvailableAt)}.</p>
      <p>
        Publisher{" "}
        {evidence.publicationPrecision === "DATE_ONLY"
          ? (evidence.publishedDate ?? "date unavailable")
          : clock(evidence.publishedAt)}{" "}
        · lineage {evidence.sourceLineageId ?? "unverified"}.
      </p>
      {evidence.responseSha256 ? (
        <OriginalResponse
          digest={evidence.responseSha256}
          label="Download decisive evidence original"
        />
      ) : (
        <p>Original hash unavailable; inspect the exclusion.</p>
      )}
    </li>
  );
}

function ClaimArchive({ claim }: { claim: FeedbackClaim }) {
  const digest =
    claim.responseSha256 ??
    (typeof claim.inputs[0]?.responseSha256 === "string"
      ? claim.inputs[0].responseSha256
      : undefined);
  const decisive =
    claim.newsInspection?.evidence ??
    claim.verification?.decisiveEvidence ??
    [];
  const publicPublisher = /^https?:\/\//i.test(claim.source)
    ? claim.source
    : null;
  const localArchiveOnly =
    claim.sourceQuality?.originalAccess === "LOCAL_RESEARCH_ARCHIVE";
  return (
    <details
      className="min-w-0 border-t border-[var(--line)] py-2 text-xs [overflow-wrap:anywhere]"
      data-testid="feedback-claim-evidence"
    >
      <summary className="cursor-pointer">
        Originals, revisions and matching methodology
      </summary>
      <p>
        Claim origin {clock(claim.originAt)} · application first availability{" "}
        {clock(claim.firstAvailableAt)}.
      </p>
      <p>
        Publisher publication{" "}
        {claim.publicationPrecision === "DATE_ONLY"
          ? (claim.publishedDate ?? "date unavailable")
          : clock(claim.publishedAt)}
        . Receipt is a separate clock.
      </p>
      <p>
        Source {claim.source} · version {claim.sourceVersion}.
      </p>
      {claim.sourceQuality ? (
        <p>
          {claim.sourceQuality.articleBodyRetained
            ? "Publisher document retained."
            : "Publisher article body is not retained; source-product scope is limited."}{" "}
          {claim.sourceQuality.timestampMeaning}.{" "}
          {claim.sourceQuality.closureInference}.
        </p>
      ) : null}
      {localArchiveOnly ? (
        <p>
          Publisher original retained for local research; public redistribution
          is not qualified.{" "}
          {publicPublisher ? (
            <a
              href={publicPublisher}
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              Inspect the publisher page
            </a>
          ) : null}{" "}
          {claim.sourceQuality?.redistributionPolicy}
        </p>
      ) : digest ? (
        <OriginalResponse digest={digest} />
      ) : (
        <p>Original source hash unavailable.</p>
      )}
      {claim.economicInspection?.matchedObservation?.responseSha256 ? (
        <OriginalResponse
          digest={claim.economicInspection.matchedObservation.responseSha256}
          label="Download scoring outcome original"
        />
      ) : null}
      {decisive.length ? (
        <ul aria-label="Decisive assessment evidence">
          {decisive.map((item, index) => (
            <EvidenceSummary
              key={item.id ?? `${item.responseSha256}-${index}`}
              evidence={item}
            />
          ))}
        </ul>
      ) : null}
      <details>
        <summary>Inspect full frozen record and audit precision</summary>
        <pre className="max-h-72 max-w-full overflow-y-auto whitespace-pre-wrap break-all">
          {JSON.stringify(claim, null, 2)}
        </pre>
      </details>
    </details>
  );
}

function ClaimResult({ claim }: { claim: FeedbackClaim }) {
  const economic = claim.economicInspection;
  const assessment =
    claim.newsInspection?.currentAssessment ?? claim.verification;
  const assessmentAt =
    assessment?.availableAt ??
    assessment?.assessedAt ??
    assessment?.createdAt ??
    claim.newsInspection?.assessmentHistory.find(
      (item) => item.id === assessment?.id,
    )?.assessedAt;
  const news =
    !!claim.newsInspection ||
    !!claim.newsIdentity ||
    ["ANNOUNCEMENT", "ACTUAL_EVENT", "CANCELLATION"].includes(
      claim.target.kind,
    );
  return (
    <section
      className="min-w-0 space-y-2 py-2 text-xs leading-relaxed [overflow-wrap:anywhere]"
      data-testid="feedback-claim-result"
      data-claim-id={claim.id}
    >
      <p className="font-medium text-[var(--text)]">{claim.wording}</p>
      {economic ? (
        <>
          <p role="status">
            <strong>{economic.status}</strong> · {economic.reason}
          </p>
          <dl
            className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] gap-x-3 gap-y-1"
            data-testid="economic-result"
          >
            <dt>Frozen persistence forecast</dt>
            <dd>
              {number(economic.predicted)} {claim.unit ?? "INR/USD"}
            </dd>
            <dt>Target observation date</dt>
            <dd>{economic.targetDate ?? "Unavailable"} · date only</dd>
            <dt>Input quote</dt>
            <dd>
              {number(economic.inputQuote?.value)} {claim.unit ?? "INR/USD"} ·{" "}
              {economic.inputQuote?.observationDate ?? "date unavailable"}
            </dd>
            <dt>Quote age at forecast issue</dt>
            <dd>
              {economic.inputQuote?.ageDays == null
                ? "Unavailable"
                : `${number(economic.inputQuote.ageDays)} calendar days`}
            </dd>
            <dt>Forecast issued</dt>
            <dd>{clock(economic.issuedAt)}</dd>
            <dt>Scoring observation</dt>
            <dd>
              {economic.matchedObservation
                ? `${number(economic.matchedObservation.value)} ${claim.unit ?? "INR/USD"} · ${economic.matchedObservation.observationDate ?? "date unavailable"}`
                : "Pending compatible later evidence"}
            </dd>
            <dt>Outcome first receipt</dt>
            <dd>{clock(economic.matchedObservation?.firstAvailableAt)}</dd>
            <dt>Qualified score available</dt>
            <dd>{clock(economic.assessmentAvailableAt)}</dd>
            <dt>Signed error: observed − predicted</dt>
            <dd>
              {number(economic.error, true)} {claim.unit ?? "INR/USD"}
            </dd>
            <dt>Absolute error</dt>
            <dd>
              {number(economic.absoluteError)} {claim.unit ?? "INR/USD"}
            </dd>
            <dt>Scoring vintage / revisions</dt>
            <dd>
              {economic.scoringVintage ?? "Scoring vintage unavailable"} ·{" "}
              {economic.revisionState ?? "Revision state unavailable"}
            </dd>
          </dl>
          <p>
            DEXINUS is INR per USD, the New York noon buying-rate series.
            Observation dates have no invented intraday measurement or release
            instant.
          </p>
          {economic.expectedRelease ? (
            <p>
              Expected release context:{" "}
              {typeof economic.expectedRelease === "string"
                ? economic.expectedRelease
                : String(
                    economic.expectedRelease.meaning ??
                      economic.expectedRelease.reason ??
                      "Inspect the retained release methodology below.",
                  )}{" "}
              {typeof economic.expectedRelease === "object" &&
              economic.expectedRelease.expectedAt
                ? `Derived expected check window ${clock(String(economic.expectedRelease.expectedAt))}. `
                : ""}
              Provider availability is not guaranteed.
            </p>
          ) : null}
          {(economic.exclusionReasons ?? []).map((reason, index) => (
            <p key={index}>Excluded: {reason}</p>
          ))}
          {(economic.exclusions ?? []).map((exclusion, index) => (
            <p key={index}>
              Excluded:{" "}
              {typeof exclusion === "string"
                ? exclusion
                : (exclusion.reason ?? "Inspect retained exclusion details.")}
            </p>
          ))}
          <p>
            Persistence is the frozen baseline. Its own error does not
            demonstrate improvement, and reference-rate accuracy does not
            establish shipping savings.
          </p>
        </>
      ) : news ? (
        <>
          <p role="status">
            <strong>{assessment?.verdict ?? "UNRESOLVED"}</strong> ·{" "}
            {assessment?.reason ??
              "Suitable authority/operator evidence is unavailable; unresolved does not mean false."}
          </p>
          <dl
            className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] gap-x-3 gap-y-1"
            data-testid="news-result"
          >
            <dt>Exact predicate</dt>
            <dd>{claim.target.predicate ?? claim.target.kind}</dd>
            <dt>Entity / geographic scope</dt>
            <dd>
              {claim.entity} · {claim.geography}
            </dd>
            <dt>Reported period</dt>
            <dd>{period(claim)}</dd>
            <dt>Reported value</dt>
            <dd>
              {typeof claim.value === "boolean"
                ? String(claim.value)
                : number(claim.value)}{" "}
              {claim.unit}
            </dd>
            <dt>Applicability</dt>
            <dd>{assessment?.applicability ?? "Not established"}</dd>
            <dt>Assessment available</dt>
            <dd>{clock(assessmentAt)}</dd>
            <dt>Current inspection as of</dt>
            <dd>{clock(claim.newsInspection?.asOf)}</dd>
          </dl>
          {assessment?.verificationMode ? (
            <p>Assessment basis: {assessment.verificationMode}.</p>
          ) : null}
          {assessment?.independentReportingConfirmations != null ? (
            <p>
              {assessment.independentReportingConfirmations} independent
              reporting confirmations. An authority's own notice is
              source-document verification, not independent confirmation of
              itself.
            </p>
          ) : null}
          {claim.target.kind === "ANNOUNCEMENT" ? (
            <p>
              Verifying an announcement does not prove the announced closure
              occurred. A later cancellation changes applicability without
              making the original announcement false.
            </p>
          ) : null}
          {(
            claim.newsInspection?.exclusionReasons ??
            assessment?.exclusionReasons ??
            assessment?.exclusions ??
            []
          ).map((reason, index) => (
            <p key={index}>Excluded: {reason}</p>
          ))}
          <p>
            Source verification remains separate from actual vessel execution
            and shipping-impact error.
          </p>
        </>
      ) : (
        <>
          <p>
            {claim.kind} · {claim.target.kind} · {period(claim)}
          </p>
          <p>
            Value{" "}
            {typeof claim.value === "boolean"
              ? String(claim.value)
              : number(claim.value)}{" "}
            {claim.unit} · {claim.geography}.
          </p>
          {claim.kind === "FORECAST" ? (
            <>
              <p>
                Stored numerical result: {claim.score?.status ?? "pending"}.{" "}
                {claim.target.series === "DEXINUS"
                  ? "Legacy economic scores remain for audit; current evidence qualification is unavailable."
                  : "Operational qualification requires matching actual execution and measurement records."}
              </p>
              <p>
                Stored outcome {number(claim.score?.observed)} {claim.unit};
                signed error (observed − predicted){" "}
                {number(claim.score?.error, true)} {claim.unit}. Simulation is
                not a real operational observation.
              </p>
            </>
          ) : (
            <p>
              This reported value or context is not a prospective numerical
              forecast and is not scored as one.
            </p>
          )}
        </>
      )}
      <ClaimArchive claim={claim} />
    </section>
  );
}

function ClaimInspection({ claim }: { claim: FeedbackClaim }) {
  return (
    <details className="border-t border-[var(--line)] py-2">
      <summary>
        {claim.entity} · {claim.target.kind} ·{" "}
        {claim.verification?.verdict ??
          claim.economicInspection?.status ??
          claim.score?.status ??
          "PENDING"}
      </summary>
      <ClaimResult claim={claim} />
    </details>
  );
}

export function FrozenFeedback({
  consumed,
}: {
  consumed?: FeedbackConsumption;
}) {
  if (!consumed) return null;
  return (
    <details
      className="min-w-0 border border-[var(--line)] p-2 text-xs [overflow-wrap:anywhere]"
      data-testid="frozen-feedback"
    >
      <summary>
        Frozen feedback · {consumed.reliabilityVersion.status} ·{" "}
        {consumed.inputs.length} consumed claims
      </summary>
      <p>{consumed.effect}</p>
      <p>
        Reliability version {consumed.reliabilityVersion.id}; weight{" "}
        {consumed.reliabilityVersion.consumedWeight}.
      </p>
      <p>
        Changed consumed verification or applied policy requires a linked
        successor and fresh review. Earlier approvals retain this version.
        Unrelated global counts and unused descriptive reliability do not
        invalidate it.
      </p>
      {consumed.inputs.map(({ claim, assessment }) => (
        <ClaimInspection
          key={claim.id}
          claim={{ ...claim, verification: assessment }}
        />
      ))}
    </details>
  );
}

type Filter = "ALL" | "ECONOMIC_FORECAST" | "NEWS";
export function SharedFeedbackPanel({
  onDecision,
  vesselId: controlledVesselId,
  onVesselChange,
}: {
  onDecision?: (problem: DecisionProblem) => void;
  vesselId?: string;
  onVesselChange?: (vesselId: string) => void;
}) {
  const { identityHeaders, session } = useAuth();
  const client = useQueryClient();
  const [open, setOpen] = useState(false),
    [localVesselId, setLocalVesselId] = useState("");
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [filter, setFilter] = useState<Filter>("ALL"),
    [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [asOfInput, setAsOfInput] = useState(""),
    [asOf, setAsOf] = useState<string | null>(null),
    [timeError, setTimeError] = useState<string | null>(null);
  const canPropose = !!onDecision && session?.user.role === "SHIPPING_COMPANY";
  const parameters = new URLSearchParams({
    kind: filter,
    offset: String(offset),
    limit: "25",
  });
  if (asOf) parameters.set("asOf", asOf);
  const query = useQuery({
    queryKey: ["shared-feedback", identityHeaders, filter, offset, asOf],
    queryFn: ({ signal }) =>
      getJson<FeedbackInspection>(
        `/intelligence/feedback?${parameters}`,
        identityHeaders,
        { signal },
      ),
    enabled: session?.mode === "demo" && open,
    staleTime: 30000,
    refetchInterval: asOf ? false : 60000,
  });
  useEffect(() => {
    if (!selectedId && query.data?.claims[0])
      setSelectedId(query.data.claims[0].id);
  }, [query.data, selectedId]);
  const inspectionAt = query.data?.dataset?.asOf ?? asOf;
  const selected = useQuery({
    queryKey: [
      "shared-feedback-selected",
      identityHeaders,
      selectedId,
      inspectionAt,
    ],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({
        claimId: selectedId!,
        kind: "ALL",
        limit: "1",
      });
      if (inspectionAt) params.set("asOf", inspectionAt);
      return getJson<FeedbackInspection>(
        `/intelligence/feedback?${params}`,
        identityHeaders,
        { signal },
      );
    },
    enabled: session?.mode === "demo" && open && !!selectedId,
    staleTime: 30000,
  });
  const activeClaim = selected.data
    ? selected.data.claims[0]
    : query.data?.claims.find((claim) => claim.id === selectedId);
  const fleet = useQuery<CompanyFleet>({
    queryKey: ["company", "fleet", null],
    queryFn: () => getJson("/company/fleet", identityHeaders),
    enabled: canPropose && open,
    staleTime: 30000,
  });
  const vesselId =
    controlledVesselId ||
    localVesselId ||
    fleet.data?.vessels[0]?.vessel_id ||
    "";
  const impacts = useQuery({
    queryKey: ["feedback-impacts", identityHeaders],
    queryFn: ({ signal }) =>
      getJson<FeedbackInspection>(
        "/intelligence/feedback/impacts",
        identityHeaders,
        { signal },
      ),
    enabled: session?.mode === "demo" && open,
    staleTime: 30000,
  });
  const create = useMutation({
    mutationFn: (claimId: string) =>
      postJson<{ id: string; status: string }>(
        "/intelligence/review-tasks",
        { claimId, vesselId, requestId },
        identityHeaders,
      ),
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: ["intelligence-review-tasks"],
      });
      setRequestId(crypto.randomUUID());
    },
  });
  const audit = useMutation({
    mutationFn: () => {
      const params = new URLSearchParams({ kind: filter });
      if (inspectionAt) params.set("asOf", inspectionAt);
      return getBlob(`/intelligence/feedback/audit?${params}`);
    },
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob),
        link = document.createElement("a");
      link.href = url;
      link.download = "portwatch-feedback-audit.json";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
  });
  if (session?.mode !== "demo") return null;
  const dataset = query.data?.dataset,
    economics = query.data?.economicSummary,
    news = query.data?.newsAggregation;
  return (
    <details
      className="my-2 min-w-0 border border-[var(--line)] p-3 text-xs leading-relaxed [overflow-wrap:anywhere]"
      data-testid="shared-feedback"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer">
        News, economics and operational feedback · COLLECTING
      </summary>
      <p>
        Source verification, numerical forecast error and real operational
        consequences are evaluated separately. No collecting correction changes
        hourly approach, waiting, fuel or cost.
      </p>
      <div className="my-2 flex flex-wrap items-end gap-2">
        <label className="min-w-0">
          Inspect{" "}
          <select
            aria-label="Feedback claim category"
            className="block max-w-full bg-[var(--panel-2)]"
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value as Filter);
              setOffset(0);
            }}
          >
            <option value="ALL">All retained claims</option>
            <option value="ECONOMIC_FORECAST">DEXINUS forecasts</option>
            <option value="NEWS">News and authority claims</option>
          </select>
        </label>
        <label className="min-w-0 flex-1">
          As of UTC (optional ISO 8601)
          <input
            aria-label="Feedback as-of UTC"
            className="block w-full min-w-0 border border-[var(--line)] bg-[var(--panel-2)] p-1"
            value={asOfInput}
            placeholder="2026-10-25T06:00:00Z"
            onChange={(event) => setAsOfInput(event.target.value)}
          />
        </label>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            if (!asOfInput.trim()) {
              setAsOf(null);
              setOffset(0);
              setTimeError(null);
              return;
            }
            if (
              !/(?:Z|[+-]\d{2}:\d{2})$/.test(asOfInput.trim()) ||
              !Number.isFinite(Date.parse(asOfInput))
            ) {
              setTimeError(
                "Enter a valid timestamp with Z or an explicit UTC offset.",
              );
              return;
            }
            setAsOf(new Date(asOfInput).toISOString());
            setOffset(0);
            setTimeError(null);
          }}
        >
          Apply as-of
        </Button>
      </div>
      {timeError ? <p role="alert">{timeError}</p> : null}
      {query.isPending ? (
        <p>Loading retained claims…</p>
      ) : query.isError ? (
        <p role="alert">Feedback unavailable: {query.error.message}</p>
      ) : (
        <>
          <p data-testid="feedback-dataset-scope">
            As of {clock(dataset?.asOf ?? query.data.newsAggregation?.asOf)} ·{" "}
            {dataset
              ? `${dataset.totalClaims} retained claims in the full as-of dataset; ${dataset.filteredClaims} in this filter. Showing ${dataset.returnedClaims} from offset ${dataset.offset}.`
              : "Legacy response: displayed claims are a limited inspection page; aggregate scope is not supplied."}
          </p>
          {economics ? (
            <section
              className="my-2 border-t border-[var(--line)] py-2"
              aria-label="Economic feedback summary"
              data-testid="economic-feedback-summary"
            >
              <p>
                <strong>DEXINUS forecast accuracy · COLLECTING</strong>
              </p>
              <p>
                {economics.retainedObservations} retained observations ·{" "}
                {economics.independentForecastTargets} independent forecast
                targets · {economics.forecastVintages} vintages.
              </p>
              <p>
                {economics.eligibleMatches} eligible matches ·{" "}
                {economics.unresolvedTargets} unresolved targets ·{" "}
                {economics.excludedTargets} excluded targets.
                {economics.historyOnlyObservationDates != null
                  ? ` History/context only: ${economics.historyOnlyObservationDates} observation dates, not prospective forecast targets.`
                  : economics.retrospectiveObservations != null
                    ? ` Retrospectively collected history: ${economics.retrospectiveObservations} observations.`
                    : " History-only count is unavailable."}
              </p>
              {economics.independentObservationDates != null ? (
                <p>
                  {economics.independentObservationDates} independent
                  observation dates; retained observation vintages are not
                  independent sample counts.
                </p>
              ) : null}
              {economics.collector ? (
                <p>
                  DEXINUS last source check{" "}
                  {clock(economics.collector.lastCheck?.checkedAt)} ·{" "}
                  {economics.collector.lastCheck?.status ?? "No recorded check"}
                  . Last successful receipt{" "}
                  {clock(economics.collector.lastSuccessfulReceiptAt)}. Latest
                  observation date{" "}
                  {economics.collector.latestObservationDate ?? "Unavailable"};
                  age{" "}
                  {economics.collector.observationAgeCalendarDays == null
                    ? "Unavailable"
                    : `${number(economics.collector.observationAgeCalendarDays)} calendar days`}
                  .
                </p>
              ) : null}
              {(economics.metrics ?? []).map((metric, index) => (
                <p key={index}>
                  {Array.isArray(metric.context)
                    ? metric.context.join(" · ")
                    : metric.context}
                  : {metric.independentTargets} comparable independent targets,{" "}
                  {metric.targetFrom ?? "unknown start"} through{" "}
                  {metric.targetThrough ?? "unknown end"}; bias{" "}
                  {number(metric.bias, true)} / MAE{" "}
                  {number(metric.meanAbsoluteError)} {metric.unit}. Error is
                  observed − predicted; {metric.status}.
                </p>
              ))}
            </section>
          ) : null}
          {news ? (
            <p data-testid="news-feedback-summary">
              News: {news.summary.eventCount} event families ·{" "}
              {news.summary.independentTargets} exact targets ·{" "}
              {news.summary.resolvedIndependentTargets} resolved /{" "}
              {news.summary.pendingIndependentTargets} pending ·{" "}
              {news.summary.excludedTargetCount} excluded target groups ·{" "}
              {news.summary.reportCount} documents ·{" "}
              {news.summary.revisionCount} revisions ·{" "}
              {news.summary.ambiguousClaimCount} ambiguous-period claims.
              Excluded groups can include ambiguous identities; these counts can
              overlap. Syndicated documents do not multiply independent
              confirmations.
            </p>
          ) : (
            <p>
              {query.data.newsIndependentEvents} news event families ·{" "}
              {query.data.newsSourceReports} reports.
            </p>
          )}
          <div className="my-2 flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={offset === 0 || query.isFetching}
              onClick={() => setOffset(Math.max(0, offset - 25))}
            >
              Previous claims
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!dataset?.hasMore || query.isFetching}
              onClick={() => setOffset(offset + 25)}
            >
              Next claims
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-auto min-h-8 whitespace-normal"
              disabled={audit.isPending}
              onClick={() => audit.mutate()}
            >
              Download full filtered audit
            </Button>
          </div>
          {audit.isError ? (
            <p role="alert">Audit unavailable: {audit.error.message}</p>
          ) : null}
          {query.data.claims.length ? (
            <label className="my-2 block min-w-0">
              Retained claim on this page
              <select
                aria-label="Selected feedback claim"
                className="mt-1 block w-full min-w-0 max-w-full bg-[var(--panel-2)]"
                value={
                  query.data.claims.some((item) => item.id === selectedId)
                    ? selectedId!
                    : ""
                }
                onChange={(event) => {
                  setSelectedId(event.target.value);
                  setRequestId(crypto.randomUUID());
                  create.reset();
                }}
              >
                <option value="" disabled>
                  {selectedId
                    ? "Selected claim retained outside this page/filter"
                    : "Select a retained claim"}
                </option>
                {query.data.claims.map((claim) => (
                  <option key={claim.id} value={claim.id}>
                    {claim.entity} · {claim.target.date ?? claim.target.kind} ·{" "}
                    {claim.wording}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <p>
              No claims in this page/filter at the requested time. No outcome is
              invented.
            </p>
          )}
          {selected.isError ? (
            <p role="alert">
              Selected claim unavailable: {selected.error.message}
            </p>
          ) : activeClaim ? (
            <>
              {!query.data.claims.some(
                (claim) => claim.id === activeClaim.id,
              ) ? (
                <p>
                  The selected claim is retained outside this page/filter.
                  Choose a claim from the page list to change the inspection.
                </p>
              ) : null}
              <ClaimResult claim={activeClaim} />
              {canPropose &&
              (activeClaim.sourceQuality ||
                activeClaim.newsIdentity ||
                activeClaim.newsInspection) ? (
                <div className="my-2 space-y-2 border-t border-[var(--line)] py-2">
                  <label className="block min-w-0">
                    Owned voyage for verification
                    <select
                      aria-label="Feedback voyage"
                      className="block w-full max-w-full bg-[var(--panel-2)]"
                      value={vesselId}
                      onChange={(event) => {
                        setLocalVesselId(event.target.value);
                        onVesselChange?.(event.target.value);
                        setRequestId(crypto.randomUUID());
                        create.reset();
                      }}
                    >
                      {(fleet.data?.vessels ?? []).map((vessel) => (
                        <option key={vessel.vessel_id} value={vessel.vessel_id}>
                          {vessel.name} · {vessel.vessel_id}
                        </option>
                      ))}
                    </select>
                  </label>
                  {fleet.isError ? (
                    <p role="alert">
                      Owned voyages unavailable; verification cannot be
                      requested.
                    </p>
                  ) : null}
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-auto min-h-8 max-w-full whitespace-normal text-left"
                    disabled={
                      !fleet.data?.vessels.some(
                        (vessel) => vessel.vessel_id === vesselId,
                      ) || create.isPending
                    }
                    onClick={() => create.mutate(activeClaim.id)}
                  >
                    Request verification of this report
                  </Button>
                  <p>
                    This creates a current visitor-owned review task, separately
                    from the archive's as-of view, not a vessel hold, speed
                    change or real operational target.
                  </p>
                </div>
              ) : null}
            </>
          ) : selected.isPending && selectedId ? (
            <p>Loading the selected retained claim…</p>
          ) : selectedId ? (
            <p>
              The selected claim was not available at this as-of time. Later
              evidence is hidden.
            </p>
          ) : null}
          <details className="border-t border-[var(--line)] py-2">
            <summary>
              Collector clocks, independent counts and full methodology
            </summary>
            <p>{query.data.note}</p>
            <p>
              Collector {query.data.collector?.status ?? "COLLECTING"} · last
              run/check {clock(query.data.collector?.ranAt)}. A check does not
              establish a new observation or first receipt.
            </p>
            {(query.data.collector?.failures ?? []).map((failure, index) => (
              <p key={index}>
                {failure.source}: {failure.reason}. Retained originals remain
                inspectable.
              </p>
            ))}
            <p>
              Consumed neutral reliability weight{" "}
              {query.data.reliability.consumedWeight}. Chronological validation
              and explicit scoped adoption remain required. No mixed-unit global
              accuracy or percentage-error score is inferred.
            </p>
            <pre className="max-h-72 max-w-full overflow-y-auto whitespace-pre-wrap break-all">
              {JSON.stringify(
                {
                  dataset,
                  economicSummary: economics,
                  newsAggregation: news,
                  collector: query.data.collector,
                  reliability: query.data.reliability,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </>
      )}
      {create.isError ? <p role="alert">{create.error.message}</p> : null}
      {create.isSuccess ? (
        <p role="status">
          Verification requested · {create.data.status}. This visitor's review
          queue retains the frozen source and voyage context; no numerical
          consequence or execution is inferred.
        </p>
      ) : null}
      <details className="border-t border-[var(--line)] py-2">
        <summary>
          Visitor operational hypotheses · separate from source accuracy
        </summary>
        <p>
          Only suitable actual records matching the call, executed action,
          forecast cutoff and measurement basis resolve real operational
          targets. Approval, context review, FX accuracy and simulation add zero
          real targets by themselves.
        </p>
        {impacts.isError ? (
          <p role="alert">
            Operational targets unavailable: {impacts.error.message}
          </p>
        ) : (
          impacts.data?.claims.map((claim) => (
            <ClaimInspection key={claim.id} claim={claim} />
          ))
        )}
      </details>
    </details>
  );
}
