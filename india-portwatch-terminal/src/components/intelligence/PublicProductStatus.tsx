import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson } from "@/services/api";
import type { DataTruth as Truth } from "@/types/data-truth";
import { DataTruth } from "./DataTruth";
import { formatUtc } from "@/components/kit/primitives";
type Product = Truth & {
  productId: string;
  coverage: { retainedRows: number; scope: string };
  rows: Record<string, unknown>[];
  error?: string | null;
};
export function PublicProductStatus() {
  const { identityHeaders } = useAuth();
  const q = useQuery({
    queryKey: ["public-product-status"],
    queryFn: ({ signal }) =>
      getJson<{
        asOf: string;
        products: Product[];
        counts: Record<string, number>;
        denominator: number;
        scope: string;
      }>("/intelligence/products", identityHeaders, { signal }),
    staleTime: 60000,
    refetchInterval: 60000,
  });
  return (
    <section
      className="pw-evidence-section"
      aria-label="Provider-backed product coverage"
    >
      <h3>Provider-backed products</h3>
      <p className="pw-source-limit">
        Public context is separate from your fictional fleet and demo actions.
        Inspection reads retained evidence; it does not fetch providers.
      </p>
      {q.isPending ? (
        <p role="status">Reading retained provider receipts…</p>
      ) : null}
      {q.isError ? (
        <p role="alert">
          Provider coverage unavailable.{" "}
          {q.data ? "Previous results retained; not newly checked." : ""}
        </p>
      ) : null}
      {q.data ? (
        <>
          <p>
            {q.data.products.length} configured products ·{" "}
            {Object.entries(q.data.counts)
              .map(([state, count]) => `${count} ${state.toLowerCase()}`)
              .join(" · ")}
          </p>
          <p className="pw-meta">
            Projection {formatUtc(q.data.asOf)}; denominator is configured
            products, not ships or ports.
          </p>
          {q.data.products.map((product) => (
            <article key={product.productId} className="pw-product-row">
              <h4>
                {product.provider} · {product.product}
              </h4>
              <DataTruth value={product} details />
              <p className="pw-meta">
                {product.coverage.retainedRows} retained rows ·{" "}
                {product.coverage.scope}
              </p>
              {product.error ? (
                <p>
                  Last attempt failed ({product.error}); last successful receipt
                  preserved.
                </p>
              ) : null}
              <details>
                <summary>Inspect retained values</summary>
                <pre className="pw-json">
                  {JSON.stringify(product.rows, null, 2)}
                </pre>
              </details>
            </article>
          ))}
        </>
      ) : null}
    </section>
  );
}
