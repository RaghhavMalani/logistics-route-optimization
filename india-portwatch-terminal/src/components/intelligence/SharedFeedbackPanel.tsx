import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getBlob, getJson, postJson } from "@/services/api";
import type {
  FeedbackClaim,
  FeedbackConsumption,
  FeedbackInspection,
} from "@/services/sharedFeedback";
import type { DecisionProblem } from "@/types/decisions";
import { Button } from "@/components/ui/button";
import { formatUtc } from "@/components/kit/primitives";

function ClaimInspection({ claim }: { claim: FeedbackClaim }) {
  const observed =
    typeof claim.inputs[0]?.observedAt === "string"
      ? claim.inputs[0].observedAt
      : null;
  const baselineAge =
    claim.baselineAgeDays ??
    (observed
      ? Math.floor(
          (Date.parse(claim.originAt) - Date.parse(observed)) / 86400000,
        )
      : null);
  const baselineStatus =
    claim.baselineStatus ??
    (baselineAge != null && baselineAge > 7
      ? "STALE"
      : "Inspect retained observation age");
  const digest =
    claim.responseSha256 ??
    (typeof claim.inputs[0]?.responseSha256 === "string"
      ? claim.inputs[0].responseSha256
      : null);
  const original = useMutation({
    mutationFn: () => getBlob(`/intelligence/feedback/evidence/${digest}`),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${digest}.response`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
  });
  return (
    <details className="border-t border-[var(--line)] py-2">
      <summary>
        {claim.entity} · {claim.target.kind} ·{" "}
        {claim.verification?.verdict ?? claim.score?.status ?? "PENDING"}
      </summary>
      <p>
        Original claim ({claim.kind}): {claim.wording}
      </p>
      <p>
        Value {String(claim.value ?? "unavailable")} {claim.unit} · scope{" "}
        {claim.geography}
      </p>
      {claim.target.series === "DEXINUS" && (
        <p>
          Baseline quote observed{" "}
          {String(claim.inputs[0]?.observedAt ?? "unavailable")} ·{" "}
          {baselineStatus}
          {baselineAge != null ? ` ${baselineAge} days at forecast origin` : ""}
          . This is a retained reference rate, not a current executable FX
          quote.
        </p>
      )}
      <p>
        Origin {formatUtc(claim.originAt)} · first available{" "}
        {formatUtc(claim.firstAvailableAt)}
      </p>
      <p>
        Target{" "}
        {claim.target.date ??
          claim.target.at ??
          (claim.target.from
            ? `${claim.target.from} to ${claim.target.through}`
            : (claim.target.reportedPeriod ?? "Target period unavailable"))}
      </p>
      <p>
        Later outcome:{" "}
        {claim.score?.observed ?? "Pending suitable real evidence"} · error
        (observed − predicted): {claim.score?.error ?? "unavailable"}
      </p>
      {claim.verification && (
        <p>
          {claim.verification.reason}. Applicability:{" "}
          {claim.verification.applicability}.
        </p>
      )}
      <p>
        Correction status: COLLECTING. No learned change to hourly weather,
        arrival, delay, fuel or cost.
      </p>
      <p className="break-all">
        Source {claim.source} · version {claim.sourceVersion} · claim {claim.id}
      </p>
      {claim.sourceQuality && (
        <p>
          Headline source product retained; publisher article body unavailable.{" "}
          {claim.sourceQuality.timestampMeaning}.{" "}
          {claim.sourceQuality.closureInference}.
        </p>
      )}
      {digest && (
        <Button
          size="sm"
          variant="outline"
          disabled={original.isPending}
          onClick={() => original.mutate()}
        >
          Download retained original response
        </Button>
      )}
      {original.isError && (
        <p role="alert">Original unavailable: {original.error.message}</p>
      )}
      <details>
        <summary>Inspect frozen inputs, source vintages and outcomes</summary>
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all">
          {JSON.stringify(claim, null, 2)}
        </pre>
      </details>
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
      className="border border-[var(--line)] p-2 text-[11px]"
      data-testid="frozen-feedback"
    >
      <summary>
        Frozen feedback · {consumed.reliabilityVersion.status} ·{" "}
        {consumed.inputs.length} consumed claims
      </summary>
      <p>{consumed.effect}</p>
      <p className="break-all">
        Reliability version {consumed.reliabilityVersion.id} · weight{" "}
        {consumed.reliabilityVersion.consumedWeight}
      </p>
      <p>
        Changed consumed verification or applied policy requires a linked
        successor and fresh review. Earlier approvals remain attached to this
        version. Unrelated pending reports and global descriptive counts do not
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

export function SharedFeedbackPanel({
  onDecision,
}: {
  onDecision?: (problem: DecisionProblem) => void;
}) {
  const { identityHeaders, session } = useAuth();
  const [vesselId, setVesselId] = useState("PWD-001");
  const [hold, setHold] = useState(6);
  const canPropose = !!onDecision && session?.user.role === "SHIPPING_COMPANY";
  const query = useQuery({
    queryKey: ["shared-feedback", identityHeaders],
    queryFn: ({ signal }) =>
      getJson<FeedbackInspection>("/intelligence/feedback", identityHeaders, {
        signal,
      }),
    enabled: session?.mode === "demo",
    staleTime: 30000,
    refetchInterval: 60000,
  });
  const impacts = useQuery({
    queryKey: ["feedback-impacts", identityHeaders],
    queryFn: ({ signal }) =>
      getJson<FeedbackInspection>(
        "/intelligence/feedback/impacts",
        identityHeaders,
        { signal },
      ),
    enabled: session?.mode === "demo",
    staleTime: 30000,
  });
  const create = useMutation({
    mutationFn: (claimId: string) =>
      postJson<DecisionProblem>(
        "/intelligence/feedback/comparison",
        { claimId, vesselId, assumedHoldHours: hold },
        identityHeaders,
      ),
    onSuccess: (problem) => onDecision?.(problem),
  });
  if (session?.mode !== "demo") return null;
  return (
    <details
      className="my-2 border border-[var(--line)] p-3 text-[11px]"
      data-testid="shared-feedback"
    >
      <summary>News, economics and operational feedback · COLLECTING</summary>
      {query.isPending ? (
        <p>Loading retained claims…</p>
      ) : query.isError ? (
        <p role="alert">Feedback unavailable: {query.error.message}</p>
      ) : (
        <>
          <p>{query.data.note}</p>
          <p>
            {query.data.newsIndependentEvents} news events ·{" "}
            {query.data.newsSourceReports} target reports. Syndicated sources
            never multiply independent target counts.
          </p>
          <p>
            An announcement is separate from actual closure. A cancellation
            changes applicability; it does not automatically falsify a past
            report.
          </p>
          <p>
            DEXINUS is INR per USD, a New York noon buying rate. Daily values
            are released weekly with possible holiday delays and revisions.
            Quotes are observations; only frozen future forecasts are scored.
          </p>
          <p>
            Collector: {query.data.collector?.status ?? "COLLECTING"} · last run{" "}
            {formatUtc(query.data.collector?.ranAt ?? null)}
          </p>
          {query.data.collector?.failures.map((f) => (
            <p role="status" key={f.source}>
              {f.source} unavailable: {f.reason}. Retained evidence remains
              inspectable.
            </p>
          ))}
          {query.data.claims.length === 0 && (
            <p>
              No retained case yet. Collection is pending; no example outcome
              has been invented.
            </p>
          )}
          {query.data.claims.map((claim) => (
            <div key={claim.id}>
              <ClaimInspection claim={claim} />
              {canPropose && claim.sourceQuality && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={create.isPending}
                  onClick={() => create.mutate(claim.id)}
                >
                  Use news as Company review context
                </Button>
              )}
            </div>
          ))}
          {canPropose && (
            <div className="flex flex-wrap gap-3 my-2">
              <label>
                Visitor vessel ID{" "}
                <input
                  aria-label="Feedback vessel ID"
                  className="bg-[var(--surface)] border border-[var(--line)] w-24"
                  value={vesselId}
                  onChange={(e) => setVesselId(e.target.value)}
                />
              </label>
              <label>
                Assumed review hold (h){" "}
                <input
                  aria-label="Feedback review hold hours"
                  className="bg-[var(--surface)] border border-[var(--line)] w-16"
                  type="number"
                  min={1}
                  max={24}
                  value={hold}
                  onChange={(e) => setHold(Number(e.target.value))}
                />
              </label>
            </div>
          )}
          <p>
            Notice exposure uses the declared passage in the existing
            restriction panel below. FX remains reference-rate inspection;
            currency amounts and settlement dates are unavailable. It does not
            justify a vessel hold or establish realized savings.
          </p>
          {query.data.reliability.slices.map((slice) => (
            <p key={slice.context.join("|")}>
              {slice.context.join(" · ")}: {slice.independentTargets}{" "}
              independent targets · bias {slice.bias} · MAE{" "}
              {slice.meanAbsoluteError} · {slice.status}
            </p>
          ))}
          <p className="break-all">
            Consumed neutral reliability version {query.data.reliability.id};
            chronological validation is required before applying a correction.
          </p>
        </>
      )}
      {create.isError && <p role="alert">{create.error.message}</p>}
      <details>
        <summary>
          Visitor operational hypotheses · separate from source accuracy
        </summary>
        <p>
          Only selected options with matching executed-action, call and
          measurement basis in suitable actual records can be evaluated.
          Approval is not execution. Simulated outcomes do not resolve these
          targets.
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
