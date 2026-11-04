import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { formatUtc } from "@/components/kit/primitives";
import { getJson, postJson } from "@/services/api";
import {
  getPortContext,
  type FrozenPortContext,
  type PortContextSelection,
} from "@/services/port-context";
import { fleetReviewHash } from "@/services/rolling-intelligence";

const METRIC_LABELS: Record<string, string> = {
  WORKING_LISTED_ROWS: "Working-list rows",
  ANCHORAGE_LISTED_ROWS: "Anchorage rows",
  ANCHORAGE_READY_ROWS: "Ready at anchorage",
  ANCHORAGE_NOT_READY_ROWS: "Not ready at anchorage",
};

export function PortOperationalContext({
  vesselId,
  onVesselChange,
}: {
  vesselId: string;
  onVesselChange: (id: string) => void;
}) {
  const { session, identityHeaders } = useAuth();
  const client = useQueryClient();
  const q = useQuery({
    queryKey: ["port-context", identityHeaders],
    queryFn: ({ signal }) => getPortContext(identityHeaders, signal),
    enabled: session?.mode === "demo",
    retry: false,
    staleTime: 30000,
    refetchInterval: (query) =>
      query.state.data?.refreshPending ? 2_000 : false,
  });
  const [metric, setMetric] = useState("WORKING_LISTED_ROWS"),
    [threshold, setThreshold] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  const changed = () => {
    void client.invalidateQueries({ queryKey: ["port-context"] });
    void client.invalidateQueries({ queryKey: ["company"] });
    window.dispatchEvent(new Event("portwatch:workflow-changed"));
  };
  const refresh = useMutation({
    mutationFn: () =>
      postJson(
        "/intelligence/port-context/refresh",
        { portCode: "INPRT" },
        identityHeaders,
      ),
    onSuccess: changed,
  });
  const refreshing = refresh.isPending || q.data?.refreshPending;
  const rule = useMutation({
    mutationFn: () =>
      postJson(
        "/intelligence/port-context/rule",
        {
          vesselId,
          metricId: metric,
          threshold: Number(threshold),
          acknowledged: confirmed,
          declareDestination: confirmed,
        },
        identityHeaders,
      ),
    onSuccess: changed,
  });
  const audit = useMutation({
    mutationFn: () =>
      getJson(
        `/intelligence/port-context/audit?${new URLSearchParams({ vesselId, ...(q.data?.context.asOf ? { asOf: q.data.context.asOf } : {}) })}`,
        identityHeaders,
      ),
    onSuccess: (data) => {
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "paradip-context-audit.json";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
  });
  const context = q.data?.context;
  const voyage = q.data?.voyages.find((v) => v.id === vesselId);
  if (session?.mode !== "demo") return null;
  return (
    <details
      open
      className="pw-evidence-section my-1 [overflow-wrap:anywhere]"
      data-testid="port-operational-context"
    >
      <summary className="cursor-pointer font-semibold">
        {context?.evidenceKind === "SOFTWARE_LIFECYCLE_FIXTURE"
          ? "Software lifecycle fixture · port context"
          : "Official Indian port context · inspect section freshness"}
      </summary>
      {q.isPending ? (
        <p role="status">Reading retained Paradip product…</p>
      ) : null}
      {q.isError ? (
        <p role="alert">
          Context read unavailable: {q.error.message}.{" "}
          {context
            ? "Previous result is retained, not newly verified."
            : "No current-source conclusion is available."}
          <Button size="sm" variant="outline" onClick={() => void q.refetch()}>
            Retry retained port context
          </Button>
        </p>
      ) : null}
      {context ? (
        <>
          <div className="pw-source-heading">
            <div>
              <h3>Paradip daily port context</h3>
              <p>
                {context.evidenceKind === "SOFTWARE_LIFECYCLE_FIXTURE"
                  ? "Software fixture · not authority observations"
                  : "Paradip Port Authority · INPRT"}
              </p>
            </div>
            <span
              className="pw-source-status"
              data-current={context.status === "CURRENT_ELIGIBLE"}
            >
              {context.status}
            </span>
          </div>
          <p className="mb-3 text-[var(--text-2)]">{context.reason}</p>
          <div className="pw-source-clocks">
            <div>
              <span>Product date · date only</span>
              <strong>{context.reportDate ?? "Unavailable"}</strong>
            </div>
            <div>
              <span>Working-section snapshot</span>
              <time>
                {formatUtc(
                  context.metrics.find((m) => m.id === "WORKING_LISTED_ROWS")
                    ?.asOf ?? null,
                )}
              </time>
            </div>
            <div>
              <span>Original first receipt</span>
              <time>{formatUtc(context.firstReceivedAt ?? null)}</time>
            </div>
            <div>
              <span>Last successful check</span>
              <time>{formatUtc(context.lastSuccessfulCheckAt ?? null)}</time>
            </div>
          </div>
          <div
            className="pw-source-metrics"
            aria-label="Reported rows, not active ships or capacity"
          >
            {context.metrics.map((m) => (
              <section
                key={m.id}
                className="pw-source-metric"
                data-metric={m.id}
              >
                <h4>{METRIC_LABELS[m.id] ?? m.id.replaceAll("_", " ")}</h4>
                <div className="pw-source-value">
                  {m.value ?? "Unavailable"}
                </div>
                <p className="pw-source-unit">{m.unit}</p>
                <p>{m.eligibility}</p>
                {!m.asOf ? (
                  <p>{m.dateScope?.date ?? "Unknown date"} · date only</p>
                ) : null}
              </section>
            ))}
          </div>
          <p className="pw-source-limit">
            Listed rows, including repeated or completed entries, are not active
            ships or available berths. Anchorage counts do not predict an
            individual wait.
          </p>
          <details className="pw-source-detail">
            <summary>Original, interpretation and display scope</summary>
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 py-2">
              <dt>Prior-day traffic</dt>
              <dd>{context.priorDayTrafficDate ?? "Unavailable"}</dd>
              <dt>Publication</dt>
              <dd>Unknown; no midnight release assumed</dd>
              <dt>Context available</dt>
              <dd>{formatUtc(context.availableAt ?? null)}</dd>
            </dl>
            {context.metrics.map((m) => (
              <section
                key={m.id}
                className="border-t border-[var(--line)] py-2"
              >
                <strong>
                  {m.id.replaceAll("_", " ")}: {m.value ?? "Unavailable"}{" "}
                  {m.unit}
                </strong>
                <p>
                  {m.section} · page {m.pages.join(", ")}. {m.meaning}
                </p>
                <p>
                  {m.asOf
                    ? `Snapshot ${formatUtc(m.asOf)} · timezone assumed Asia/Kolkata`
                    : `As-of ${m.dateScope?.date ?? "unknown"}, date only; the working-section clock does not apply.`}
                </p>
              </section>
            ))}
            <p>
              Destination association is context. A fictional owned hull is not
              matched to a real report ship. No individual waiting forecast,
              live AIS, closure, berth reservation, clearance or numerical
              benefit follows.
            </p>
            <p>
              Snapshot {context.snapshotId ?? "Unavailable"}; revision{" "}
              {context.revisionId ?? "Unavailable"}; SHA-256{" "}
              {context.originalSha256 ?? "Unavailable"}. Original{" "}
              {context.originalStatus ?? "Unavailable"}.
            </p>
            <p>
              {context.sourceUse.scope} Full-document redistribution is not
              enabled.
            </p>
            <p>{context.scheduledSections}</p>
          </details>
          <div className="pw-source-actions">
            {context.source ? (
              <a
                className="underline"
                href={context.source}
                target="_blank"
                rel="noreferrer"
              >
                Issuer report
              </a>
            ) : null}
            <Button
              size="sm"
              variant="outline"
              disabled={audit.isPending}
              onClick={() => audit.mutate()}
            >
              Download port context audit
            </Button>
            {session.user.role !== "VESSEL_OPERATOR" ? (
              <Button
                size="sm"
                variant="outline"
                disabled={refreshing}
                onClick={() => refresh.mutate()}
              >
                {refreshing
                  ? "Collecting approved report…"
                  : "Refresh official Paradip report"}
              </Button>
            ) : null}
          </div>
          {session.user.role === "SHIPPING_COMPANY" ? (
            <details>
              <summary>
                Declare an operator review criterion for this owned call
              </summary>
              <div className="mt-2 space-y-2">
                <label className="block">
                  Owned voyage{" "}
                  <select
                    aria-label="Port context voyage"
                    className="max-w-full bg-[var(--panel-2)]"
                    value={vesselId}
                    onChange={(e) => {
                      onVesselChange(e.target.value);
                      setConfirmed(false);
                    }}
                  >
                    <option value="">Select an owned voyage</option>
                    {q.data?.voyages.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name} · {v.portCode}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  Reported metric{" "}
                  <select
                    aria-label="Port context metric"
                    className="max-w-full bg-[var(--panel-2)]"
                    value={metric}
                    onChange={(e) => {
                      setMetric(e.target.value);
                      setConfirmed(false);
                    }}
                  >
                    {context.metrics.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.id} · {m.eligibility}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  Review when reported rows are at least{" "}
                  <input
                    aria-label="Operator review row threshold"
                    className="w-24 bg-[var(--panel-2)]"
                    type="number"
                    min="1"
                    max="1000"
                    value={threshold}
                    onChange={(e) => {
                      setThreshold(e.target.value);
                      setConfirmed(false);
                    }}
                  />
                </label>
                <label className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />
                  I explicitly declare INPRT as this fictional voyage's
                  destination and this threshold as my review rule. It is not an
                  authority forecast or hours of delay.
                </label>
                <Button
                  size="sm"
                  disabled={
                    !confirmed ||
                    !voyage ||
                    !threshold ||
                    !Number.isInteger(Number(threshold)) ||
                    Number(threshold) < 1 ||
                    Number(threshold) > 1000 ||
                    rule.isPending
                  }
                  onClick={() => rule.mutate()}
                >
                  Declare INPRT context review
                </Button>
                {voyage?.rule ? (
                  <p>
                    Saved rule {voyage.rule.metricId} ≥ {voyage.rule.threshold}.{" "}
                    <a
                      className="underline"
                      href={`/company/global-eye#${fleetReviewHash({ kind: "CURRENT_INPUTS", vesselId, episodeId: voyage.episodeId })}`}
                    >
                      Review current inputs for this port-context call
                    </a>
                    . Current eligible source acknowledgement is explicit in the
                    editor.
                  </p>
                ) : null}
              </div>
            </details>
          ) : null}
        </>
      ) : null}
      {refresh.isError || rule.isError || audit.isError ? (
        <p role="alert">
          {refresh.error?.message ??
            rule.error?.message ??
            audit.error?.message}
        </p>
      ) : null}
    </details>
  );
}

export function PortContextChoices({
  vesselId,
  previous,
  value,
  onChange,
}: {
  vesselId: string;
  previous?: FrozenPortContext[];
  value: PortContextSelection[];
  onChange: (value: PortContextSelection[]) => void;
}) {
  const { session, identityHeaders } = useAuth();
  const q = useQuery({
    queryKey: ["port-context", identityHeaders],
    queryFn: ({ signal }) => getPortContext(identityHeaders, signal),
    enabled: session?.mode === "demo",
    retry: false,
    staleTime: 30000,
    refetchInterval: (query) =>
      query.state.data?.refreshPending ? 2_000 : false,
  });
  useEffect(() => onChange([]), [vesselId, onChange]);
  const context = q.data?.context;
  const rule = q.data?.voyages.find((v) => v.id === vesselId)?.rule;
  const metric = context?.metrics.find((m) => m.id === rule?.metricId);
  if (!rule && !previous?.length) return null;
  const eligible =
    !!rule &&
    !!context?.revisionId &&
    context.status === "CURRENT_ELIGIBLE" &&
    metric?.eligibility === "CURRENT_ELIGIBLE";
  return (
    <fieldset
      className="space-y-2 border border-[var(--line)] p-3"
      data-testid="port-context-choices"
    >
      <legend>Daily port context · explicit operator review</legend>
      {previous?.map((old) => (
        <p key={old.revisionId}>
          Consumed {old.reportDate} · {old.metric.id} = {old.metric.value} ·
          revision {old.revisionId}. Earlier approvals remain inspectable.
        </p>
      ))}
      <p>
        Retained {context?.reportDate ?? "unavailable"} ·{" "}
        {metric?.id ?? "no rule"} = {metric?.value ?? "unavailable"} ·{" "}
        {metric?.eligibility ?? "unavailable"}. This review changes no numeric
        weather, passage, cargo or cost calculation.
      </p>
      <label className="flex gap-2">
        <input
          type="checkbox"
          disabled={!eligible}
          checked={!!value.length}
          onChange={(e) =>
            onChange(
              e.target.checked && rule && context?.revisionId
                ? [
                    {
                      ruleId: rule.id,
                      revisionId: context.revisionId,
                      acknowledged: true,
                    },
                  ]
                : [],
            )
          }
        />
        I reviewed this exact product/metric and operator criterion as
        destination context, with its time and source limits.
      </label>
      {!eligible ? (
        <p>
          Active consumption is blocked until this metric and owned-call
          criterion qualify. A saved binding cannot be silently discarded.
        </p>
      ) : null}
    </fieldset>
  );
}
