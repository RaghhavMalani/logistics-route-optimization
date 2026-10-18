import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson, postJson } from "@/services/api";
import { Button } from "@/components/ui/button";
import { formatUtc } from "@/components/kit/primitives";
import type { DecisionProblem } from "@/types/decisions";
import { OperationalNoticePanel } from "./OperationalNoticePanel";
import { SharedFeedbackPanel } from "./SharedFeedbackPanel";
import { NavigationRestrictionPanel } from "./NavigationRestrictionPanel";
import { IntelligenceReviewTasks } from "./IntelligenceReviewTasks";
import { OperationalEvidencePanel } from "./OperationalEvidencePanel";

interface Signal {
  id?: string;
  title: string;
  category: string;
  status: string;
  fact?: string;
  mechanism?: string;
  relationship?: string;
  source?: string;
  observedAt?: string;
  publishedAt?: string;
  availableAt?: string;
  validThrough?: string;
  reason?: string;
  comparisonAvailable: boolean;
  responseSha256?: string;
  parentResponseSha256?: string;
  exposure: {
    ports: string[];
    routes: string[];
    vessels: { id: string; name: string }[];
    cargo: { vesselId: string; description: string }[];
  };
}
function hasRestrictionBasis(problem: DecisionProblem) {
  const basis = problem.evidence.intelligenceBasis;
  return (
    typeof basis === "object" &&
    basis !== null &&
    "kind" in basis &&
    basis.kind === "NOTICE_RESTRICTION"
  );
}
export function ShippingIntelligencePanel({
  onDecision,
}: {
  onDecision?: (problem: DecisionProblem) => void;
}) {
  const { identityHeaders, session } = useAuth();
  const client = useQueryClient();
  const [selected, setSelected] = useState("");
  const [vesselId, setVesselId] = useState("");
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [digest, setDigest] = useState<string | null>(null);
  const raw = useQuery({
    queryKey: ["shipping-evidence", digest, identityHeaders],
    queryFn: ({ signal }) =>
      getJson(`/intelligence/shipping-evidence/${digest}`, identityHeaders, {
        signal,
      }),
    enabled: !!digest,
  });
  const q = useQuery({
    queryKey: ["shipping-signals", identityHeaders],
    queryFn: ({ signal }) =>
      getJson<{ signals: Signal[]; note: string }>(
        "/intelligence/shipping-signals",
        identityHeaders,
        { signal, timeoutMs: 60000 },
      ),
    enabled: session?.mode === "demo",
    staleTime: 60000,
  });
  const chosen = q.data?.signals.find((s) => s.id === selected);
  const saved = useQuery({
    queryKey: ["saved-intelligence-comparisons", identityHeaders],
    queryFn: ({ signal }) =>
      getJson<{ problems: DecisionProblem[] }>(
        "/decisions/problems?limit=50",
        identityHeaders,
        { signal },
      ),
    enabled: session?.mode === "demo" && !!onDecision,
    staleTime: 10000,
  });
  const resume = useMutation({
    mutationFn: (id: string) =>
      getJson<DecisionProblem>(`/decisions/problems/${id}`, identityHeaders),
    onSuccess: (problem) => onDecision?.(problem),
  });
  const refresh = useMutation({
    mutationFn: (id: string) =>
      postJson<DecisionProblem>(
        `/decisions/problems/${id}/refresh`,
        {},
        identityHeaders,
      ),
    onSuccess: (problem) => onDecision?.(problem),
  });
  const create = useMutation({
    mutationFn: () =>
      postJson<{ id: string; status: string }>(
        "/intelligence/review-tasks",
        { signalId: selected, vesselId, requestId },
        identityHeaders,
      ),
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: ["intelligence-review-tasks"],
      });
      setRequestId(crypto.randomUUID());
    },
  });
  if (session?.mode !== "demo") return null;
  return (
    <section
      className="mt-3 border border-[var(--line)] p-3 text-[11px]"
      data-testid="shipping-intelligence"
    >
      <SharedFeedbackPanel onDecision={onDecision} />
      <OperationalEvidencePanel />
      <NavigationRestrictionPanel onDecision={onDecision} />
      <OperationalNoticePanel onDecision={onDecision} />
      <h3 className="text-xs">
        Reported intelligence → possible exposure → verification
      </h3>
      {(saved.data?.problems ?? [])
        .filter(
          (p) =>
            p.evidence.intelligenceBasis && p.actor.role === "SHIPPING_COMPANY",
        )
        .map((p) => (
          <div
            key={p.decisionId}
            className="border-b border-[var(--line)] py-2"
          >
            <span>
              Saved intelligence: {p.subject.label} · {p.workflow} ·{" "}
              {formatUtc(p.createdAt)}
            </span>{" "}
            <Button
              size="sm"
              variant="outline"
              disabled={resume.isPending}
              onClick={() => resume.mutate(p.decisionId)}
            >
              Resume saved intelligence comparison
            </Button>{" "}
            {hasRestrictionBasis(p) ? (
              <Button
                size="sm"
                variant="outline"
                disabled={refresh.isPending}
                onClick={() => refresh.mutate(p.decisionId)}
              >
                Refresh to linked intelligence comparison
              </Button>
            ) : null}
          </div>
        ))}
      {resume.isError || refresh.isError ? (
        <p role="alert">{resume.error?.message ?? refresh.error?.message}</p>
      ) : null}
      {(saved.data?.problems ?? []).some(
        (p) => p.evidence.intelligenceBasis,
      ) ? (
        <p>
          Refresh refreezes the scenario against the current voyage. The
          source's original receipt and validity stay visible; prior approvals
          and advisories are preserved.
        </p>
      ) : null}
      {q.isPending ? (
        <p>Checking source receipts and visitor fleet exposure…</p>
      ) : q.isError ? (
        <p role="alert">Sources unavailable: {q.error.message}</p>
      ) : (
        <>
          <p className="my-2">{q.data.note}</p>
          {q.data.signals.map((s, i) => (
            <details
              key={s.id ?? `${s.category}-${i}`}
              className="border-t border-[var(--line)] py-2"
            >
              <summary>
                {s.category} · {s.title} · {s.status}
              </summary>
              <p>Reported fact: {s.fact ?? s.reason ?? "Unavailable"}</p>
              <p>
                Observed/published{" "}
                {formatUtc(s.observedAt ?? s.publishedAt ?? null)} · first
                receipt {formatUtc(s.availableAt ?? null)}
                {s.validThrough
                  ? ` · valid through ${formatUtc(s.validThrough)}`
                  : ""}
                .
              </p>
              {s.source ? (
                <a
                  href={s.source}
                  target="_blank"
                  rel="noreferrer"
                  className="underline"
                >
                  Provider source
                </a>
              ) : null}
              {(s.parentResponseSha256 ?? s.responseSha256) ? (
                <button
                  className="underline ml-3"
                  onClick={() =>
                    setDigest(s.parentResponseSha256 ?? s.responseSha256!)
                  }
                >
                  Inspect retained source response
                </button>
              ) : null}
              <p>Transmission: {s.mechanism ?? "No supported mechanism"}</p>
              <p>{s.relationship}</p>
              <p>
                Inferred exposure: ports {s.exposure.ports.join(", ") || "none"}
                ; routes {s.exposure.routes.join(", ") || "none"}; vessels{" "}
                {s.exposure.vessels.map((v) => v.name).join(", ") || "none"};
                cargo{" "}
                {s.exposure.cargo.map((c) => c.description).join(", ") ||
                  "unavailable"}
                .
              </p>
              {s.category === "news" &&
              s.id &&
              s.exposure.vessels.length > 0 &&
              onDecision &&
              session.user.role === "SHIPPING_COMPANY" ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setSelected(s.id!);
                    setVesselId(s.exposure.vessels[0].id);
                    setRequestId(crypto.randomUUID());
                  }}
                >
                  Select report for verification
                </Button>
              ) : null}
            </details>
          ))}
        </>
      )}
      {digest ? (
        <details open className="max-h-48 overflow-auto">
          <summary>Retained source response · {digest}</summary>
          {raw.isError ? (
            <p role="alert">Source response unavailable.</p>
          ) : (
            <pre className="whitespace-pre-wrap break-all">
              {JSON.stringify(raw.data, null, 2)}
            </pre>
          )}
        </details>
      ) : null}
      {chosen ? (
        <fieldset className="border border-[var(--line)] p-2 space-y-2">
          <legend>Request source/exposure verification · {chosen.title}</legend>
          <label className="block">
            Affected voyage{" "}
            <select
              aria-label="Intelligence voyage"
              value={vesselId}
              onChange={(e) => {
                setVesselId(e.target.value);
                setRequestId(crypto.randomUUID());
              }}
              className="bg-[var(--panel-2)]"
            >
              {chosen.exposure.vessels.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </label>
          <p>
            Ask for independent source and passage confirmation. Broad lane or
            destination membership is a review lead. No delay, closure, arrival
            change or savings is calculated from this report.
          </p>
          <Button
            size="sm"
            disabled={create.isPending || !vesselId}
            onClick={() => create.mutate()}
          >
            {create.isPending
              ? "Recording review request…"
              : "Request source and exposure verification"}
          </Button>
        </fieldset>
      ) : null}
      {create.isError ? <p role="alert">{create.error.message}</p> : null}
      {create.isSuccess ? (
        <p role="status">
          Verification requested · {create.data.status}. No operational target
          or vessel hold was created.
        </p>
      ) : null}
      <IntelligenceReviewTasks />
    </section>
  );
}
