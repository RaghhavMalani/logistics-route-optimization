import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { useAuth } from "@/auth/AuthProvider";
import { getBlob, getJson, postJson } from "@/services/api";
import { Button } from "@/components/ui/button";
import { formatUtc } from "@/components/kit/primitives";
import { useIntelligenceReviewTasks } from "@/services/intelligence-review-tasks";

const selectorSchema = z.object({
  product: z.string(),
  portCode: z.string(),
  snapshotId: z.string().optional(),
  receiptId: z.string().optional(),
  recordId: z.string(),
});
const feedSchema = z.object({
  contractVersion: z.string(),
  asOf: z.string(),
  products: z.array(
    z.object({
      id: z.string(),
      product: z.string(),
      portCode: z.string(),
      name: z.string(),
      status: z.string(),
      semanticClass: z.string(),
      sourceUrl: z.string(),
      sha256: z.string().nullable(),
      originalHashVerified: z.boolean(),
      clocks: z.object({
        reportDate: z.string().nullable(),
        observedAt: z.string().nullable(),
        publishedAt: z.string().nullable(),
        firstAvailableAt: z.string().nullable(),
        checkedAt: z.string().nullable(),
        observationAgeHours: z.number().nullable(),
        reportAgeDays: z.number().nullable().optional(),
        parsedAt: z.string().nullable().optional(),
      }),
      records: z.array(
        z.object({
          selector: selectorSchema,
          title: z.string(),
          semanticClass: z.string(),
          record: z.record(z.unknown()),
        }),
      ),
      limitations: z.array(z.string()),
      collection: z.object({
        lastSuccessfulCollectionAt: z.string().nullable(),
        lastCheckAt: z.string().nullable(),
        errors: z.array(z.string()),
      }),
      location: z
        .object({ lat: z.number(), lon: z.number(), basis: z.string() })
        .nullable()
        .optional(),
    }),
  ),
  voyages: z.array(
    z.object({ id: z.string(), name: z.string(), portCode: z.string() }),
  ),
  oceansQualification: z.object({
    status: z.string(),
    enabled: z.literal(false),
    unverified: z.array(z.string()),
    access: z.object({ requiredAction: z.string() }),
    terms: z.object({ url: z.string() }),
  }),
});

export function OperationalEvidencePanel() {
  const { session, identityHeaders, role } = useAuth();
  const client = useQueryClient();
  const [productId, setProductId] = useState("");
  const [recordId, setRecordId] = useState("");
  const [vesselId, setVesselId] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [reviewConfirmed, setReviewConfirmed] = useState(false);
  const [taskId, setTaskId] = useState("");
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [reviewId, setReviewId] = useState(() => crypto.randomUUID());
  const tasks = useIntelligenceReviewTasks();
  const q = useQuery({
    queryKey: ["operational-evidence", identityHeaders],
    queryFn: async ({ signal }) => {
      const parsed = feedSchema.safeParse(
        await getJson<unknown>(
          "/intelligence/operational-evidence",
          identityHeaders,
          { signal, timeoutMs: 60000 },
        ),
      );
      if (!parsed.success)
        throw new Error(
          "Port-evidence response is malformed; no review action is available.",
        );
      return parsed.data;
    },
    enabled: session?.mode === "demo",
    staleTime: 60000,
    retry: 1,
  });
  const product =
    q.data?.products.find((p) => p.id === productId) ?? q.data?.products[0];
  const record =
    product?.records.find((r) => r.selector.recordId === recordId) ??
    product?.records[0];
  const voyage =
    q.data?.voyages.find((v) => v.id === vesselId) ?? q.data?.voyages[0];
  const matchingTasks =
    tasks.data?.tasks.filter(
      (t) =>
        t.taskQuestion ===
          "INSPECT_PUBLISHED_PORT_CONTEXT_FOR_DECLARED_VOYAGE" &&
        t.vesselId === voyage?.id &&
        t.source?.operationalEvidence?.portCode === product?.portCode,
    ) ?? [];
  const task = matchingTasks.find((t) => t.id === taskId) ?? matchingTasks[0];
  const canReview = role === "SHIPPING_COMPANY" || role === "PORT_AUTHORITY";
  const available =
    !!product &&
    ["CURRENT", "STALE"].includes(product.status) &&
    product.originalHashVerified &&
    !!record;
  const create = useMutation({
    mutationFn: () =>
      postJson<{ id: string }>(
        "/intelligence/review-tasks",
        {
          vesselId: voyage?.id,
          requestId,
          operationalEvidence: record?.selector,
          portContextConfirmed: confirmed,
        },
        identityHeaders,
      ),
    onSuccess: (saved) => {
      setTaskId(saved.id);
      setRequestId(crypto.randomUUID());
      void client.invalidateQueries({
        queryKey: ["intelligence-review-tasks"],
      });
    },
  });
  const review = useMutation({
    mutationFn: () =>
      postJson(
        `/intelligence/review-tasks/${task?.id}/dispositions`,
        {
          requestId: reviewId,
          operationalEvidence: record?.selector,
          dispositionType: "CONTEXT_REVIEWED",
          contextConfirmed: reviewConfirmed,
        },
        identityHeaders,
      ),
    onSuccess: () => {
      setReviewId(crypto.randomUUID());
      setReviewConfirmed(false);
      void client.invalidateQueries({
        queryKey: ["intelligence-review-tasks"],
      });
    },
  });
  const original = useMutation({
    mutationFn: async () => {
      if (!record) throw new Error("Select a retained record first.");
      const params = new URLSearchParams(
        Object.entries(record.selector).filter(
          (entry): entry is [string, string] => typeof entry[1] === "string",
        ),
      );
      const blob = await getBlob(
        "/intelligence/operational-evidence/original?" + params.toString(),
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${product?.portCode}-${product?.sha256}.${product?.product === "PUBLIC_PORT_PDF" ? "pdf" : "json"}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
  });
  function changeSelection() {
    setConfirmed(false);
    setReviewConfirmed(false);
    setTaskId("");
    setRequestId(crypto.randomUUID());
    setReviewId(crypto.randomUUID());
    create.reset();
    review.reset();
    original.reset();
  }
  if (session?.mode !== "demo") return null;
  return (
    <section
      className="mt-3 border border-[var(--line)] p-3 text-[11px] space-y-2"
      data-testid="operational-evidence-panel"
    >
      <h3 className="text-xs">
        Indian port evidence → voyage context → attributed review
      </h3>
      <p>
        Published expected arrivals, reported positions and aggregate activity
        are separate evidence products. A context review records what the
        operator inspected; it does not confirm this demo vessel's actual
        arrival.
      </p>
      {q.isPending ? (
        <p>Checking retained official port reports and aggregate activity…</p>
      ) : null}
      {q.isError ? (
        <p role="alert">Operational evidence unavailable: {q.error.message}</p>
      ) : null}
      <Button
        size="sm"
        variant="outline"
        onClick={() => void q.refetch()}
        disabled={q.isFetching}
      >
        Check retained evidence
      </Button>
      {product ? (
        <>
          <label className="block">
            Evidence product{" "}
            <select
              className="block max-w-full w-full bg-[var(--panel)] border border-[var(--line)] p-1"
              value={product.id}
              onChange={(e) => {
                setProductId(e.target.value);
                setRecordId("");
                changeSelection();
              }}
            >
              {q.data?.products.map((p) => (
                <option value={p.id} key={p.id}>
                  {p.portCode} · {p.name} · {p.status}
                </option>
              ))}
            </select>
          </label>
          <p>
            {product.semanticClass} · <strong>{product.status}</strong> ·{" "}
            {product.records.length} retained rows
          </p>
          {product.status === "STALE" ? (
            <p>
              Retained stale context can be inspected and reviewed with its
              original age. It cannot support a current operational calculation.
            </p>
          ) : null}
          <p>
            Report date: {product.clocks.reportDate ?? "unknown"}. Observation
            time:{" "}
            {product.clocks.observedAt
              ? formatUtc(product.clocks.observedAt)
              : "not established"}
            . Publication time:{" "}
            {product.clocks.publishedAt
              ? formatUtc(product.clocks.publishedAt)
              : "not established"}
            .
          </p>
          <p>
            Original first receipt:{" "}
            {product.clocks.firstAvailableAt
              ? formatUtc(product.clocks.firstAvailableAt)
              : "unavailable"}
            . Checked:{" "}
            {product.clocks.checkedAt
              ? formatUtc(product.clocks.checkedAt)
              : "not checked"}
            . Observation age:{" "}
            {product.clocks.observationAgeHours == null
              ? "unknown"
              : `${product.clocks.observationAgeHours.toFixed(1)} h`}
            ; a recent check does not refresh the observation.
          </p>
          <p>
            Printed report age:{" "}
            {product.clocks.reportAgeDays == null
              ? "unknown"
              : `${product.clocks.reportAgeDays} days`}
            . Extraction available:{" "}
            {product.clocks.parsedAt
              ? formatUtc(product.clocks.parsedAt)
              : "see exact record availability"}
            .
          </p>
          <a
            className="underline break-all"
            href={product.sourceUrl}
            target="_blank"
            rel="noreferrer"
          >
            Publisher source
          </a>
          <p className="break-all">
            Original SHA-256: {product.sha256 ?? "unavailable"} ·{" "}
            {product.originalHashVerified ? "verified" : "unverified"}
          </p>
          {product.collection.errors.map((error, i) => (
            <p role="status" key={i}>
              Collection failure: {error}
            </p>
          ))}
          <ul className="list-disc pl-4">
            {product.limitations.map((limit, i) => (
              <li key={i}>{limit}</li>
            ))}
          </ul>
          {product.location ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                window.dispatchEvent(
                  new CustomEvent("portwatch:focus-constraint", {
                    detail: {
                      id: product.id,
                      name: product.portCode + " port context",
                      ...product.location,
                      period: product.location?.basis,
                    },
                  }),
                )
              }
            >
              Focus port on original map
            </Button>
          ) : null}
          <label className="block">
            Publisher record{" "}
            <select
              className="block max-w-full w-full bg-[var(--panel)] border border-[var(--line)] p-1"
              value={record?.selector.recordId ?? ""}
              onChange={(e) => {
                setRecordId(e.target.value);
                changeSelection();
              }}
            >
              {product.records.map((r) => (
                <option key={r.selector.recordId} value={r.selector.recordId}>
                  {r.title}
                </option>
              ))}
            </select>
          </label>
          {record ? (
            <details>
              <summary>Inspect exact publisher fields and selector</summary>
              <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-all">
                {JSON.stringify(record, null, 2)}
              </pre>
            </details>
          ) : null}
          <Button
            size="sm"
            variant="outline"
            disabled={
              !product.originalHashVerified || !record || original.isPending
            }
            onClick={() => original.mutate()}
          >
            Download retained original
          </Button>
          <label className="block">
            Visitor voyage{" "}
            <select
              className="block max-w-full w-full bg-[var(--panel)] border border-[var(--line)] p-1"
              value={voyage?.id ?? ""}
              onChange={(e) => {
                setVesselId(e.target.value);
                changeSelection();
              }}
            >
              {q.data?.voyages.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} · declared destination {v.portCode}
                </option>
              ))}
            </select>
          </label>
          <p>
            {product.portCode === voyage?.portCode
              ? "This is the selected voyage's destination-port context."
              : `${product.portCode} differs from this voyage's declared destination ${voyage?.portCode ?? "unknown"}. Selecting candidate-port context does not change its route.`}{" "}
            No real-vessel identity is associated.
          </p>
          {role === "SHIPPING_COMPANY" ? (
            <>
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                I select this physical port as context to inspect for this
                voyage, without asserting route membership or a real-vessel
                association.
              </label>
              <Button
                size="sm"
                disabled={
                  !available || !voyage || !confirmed || create.isPending
                }
                onClick={() => create.mutate()}
              >
                Request port-context inspection
              </Button>
            </>
          ) : null}
          {task ? (
            <div className="border-t border-[var(--line)] pt-2 space-y-2">
              <label className="block">
                Retained inspection task{" "}
                <select
                  className="block max-w-full w-full bg-[var(--panel)] border border-[var(--line)] p-1"
                  value={task.id}
                  onChange={(e) => {
                    setTaskId(e.target.value);
                    setReviewId(crypto.randomUUID());
                    setReviewConfirmed(false);
                    review.reset();
                  }}
                >
                  {matchingTasks.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.status} · {formatUtc(t.createdAt)}
                    </option>
                  ))}
                </select>
              </label>
              <p>
                {task.status}. Original request, operational episode and earlier
                evidence remain frozen. The selected receipt will be retained
                with this new review.
              </p>
              {canReview ? (
                <>
                  <label className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      checked={reviewConfirmed}
                      onChange={(e) => setReviewConfirmed(e.target.checked)}
                    />
                    I inspected these publisher fields as port context. This
                    does not verify a news claim, actual execution, delay or
                    all-fast.
                  </label>
                  <Button
                    size="sm"
                    disabled={
                      !available || !reviewConfirmed || review.isPending
                    }
                    onClick={() => review.mutate()}
                  >
                    Record attributed context review
                  </Button>
                </>
              ) : null}
              {review.isSuccess ? (
                <p role="status">
                  Context review retained. Source accuracy and actual execution
                  remain unresolved.
                </p>
              ) : null}
            </div>
          ) : null}
          <p>
            Delay, waiting, fuel, cost and safety benefits: unavailable. No
            numerical advisory is created from this context.
          </p>
        </>
      ) : null}
      {[create.error, review.error, original.error, tasks.error].map(
        (error, i) =>
          error ? (
            <p role="alert" key={i}>
              {error.message}
            </p>
          ) : null,
      )}
      {q.data?.oceansQualification ? (
        <details>
          <summary>Singapore OCEANS-X API qualification · inactive</summary>
          <p>{q.data.oceansQualification.status}</p>
          <p>{q.data.oceansQualification.access.requiredAction}</p>
          <ul className="list-disc pl-4">
            {q.data.oceansQualification.unverified.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <a
            className="underline"
            href={q.data.oceansQualification.terms.url}
            target="_blank"
            rel="noreferrer"
          >
            API dataset terms
          </a>
        </details>
      ) : null}
    </section>
  );
}
