import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson, postJson } from "@/services/api";
import { Button } from "@/components/ui/button";
import { formatUtc } from "@/components/kit/primitives";
import type { DecisionProblem } from "@/types/decisions";
import { OperationalNoticePanel } from "./OperationalNoticePanel";

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
export function ShippingIntelligencePanel({
  onDecision,
}: {
  onDecision?: (problem: DecisionProblem) => void;
}) {
  const { identityHeaders, session } = useAuth();
  const [selected, setSelected] = useState("");
  const [vesselId, setVesselId] = useState("");
  const [hold, setHold] = useState(6);
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
      postJson<DecisionProblem>(
        "/intelligence/shipping-comparison",
        { signalId: selected, vesselId, assumedHoldHours: hold },
        identityHeaders,
      ),
    onSuccess: (problem) => onDecision?.(problem),
  });
  if (session?.mode !== "demo") return null;
  return (
    <section
      className="mt-3 border border-[var(--line)] p-3 text-[11px]"
      data-testid="shipping-intelligence"
    >
      <OperationalNoticePanel onDecision={onDecision} />
      <h3 className="text-xs">
        Reported intelligence → shipping exposure → action comparison
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
            <Button
              size="sm"
              variant="outline"
              disabled={refresh.isPending}
              onClick={() => refresh.mutate(p.decisionId)}
            >
              Refresh to linked intelligence comparison
            </Button>
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
              {s.comparisonAvailable &&
              onDecision &&
              session.user.role === "SHIPPING_COMPANY" ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setSelected(s.id!);
                    setVesselId(s.exposure.vessels[0].id);
                  }}
                >
                  Select for shipping comparison
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
          <legend>Explicit operator scenario · {chosen.title}</legend>
          <label className="block">
            Affected voyage{" "}
            <select
              aria-label="Intelligence voyage"
              value={vesselId}
              onChange={(e) => setVesselId(e.target.value)}
              className="bg-[var(--panel-2)]"
            >
              {chosen.exposure.vessels.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            Assumed review hold (h){" "}
            <input
              aria-label="Assumed intelligence review hold"
              type="number"
              min={1}
              max={24}
              value={hold}
              onChange={(e) => setHold(Number(e.target.value))}
              className="w-16 bg-[var(--panel-2)]"
            />
          </label>
          <p>
            This bounded hold is an operator demo assumption for further
            verification. The source does not establish event-caused delay, a
            closure, safer passage or savings. Compare continuing the plan with
            requesting a later arrival.
          </p>
          <Button
            size="sm"
            disabled={create.isPending || !vesselId || hold < 1 || hold > 24}
            onClick={() => create.mutate()}
          >
            {create.isPending
              ? "Freezing comparison…"
              : "Compare shipping actions"}
          </Button>
        </fieldset>
      ) : null}
      {create.isError ? <p role="alert">{create.error.message}</p> : null}
    </section>
  );
}
