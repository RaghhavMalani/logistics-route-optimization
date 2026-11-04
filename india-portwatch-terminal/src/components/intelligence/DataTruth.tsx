import type { DataTruth as Truth } from "@/types/data-truth";
import { formatUtc } from "@/components/kit/primitives";
const names: Record<Truth["origin"], string> = {
  OFFICIAL_REPORT: "Official report",
  REPORTED_EVENT: "Reported event",
  TRANSPONDER_OBSERVATION: "Transponder observation",
  PROVIDER_FORECAST: "Provider forecast",
  REANALYSIS: "Reanalysis",
  DERIVED_METRIC: "Derived metric",
  OPERATOR_DECLARATION: "Operator declaration",
  SIMULATION: "Simulation / fixture",
  REFERENCE: "Reference geography",
  UNKNOWN: "Origin unknown",
};
export function DataTruth({
  value,
  details = false,
}: {
  value: Truth;
  details?: boolean;
}) {
  return (
    <div
      className="pw-truth"
      data-origin={value.origin}
      data-freshness={value.freshness}
    >
      <p>
        <span>{names[value.origin] ?? names.UNKNOWN}</span>
        <span> · {value.freshness.toLowerCase().replaceAll("_", " ")}</span>
        {value.execution ? (
          <span> · {value.execution.toLowerCase().replaceAll("_", " ")}</span>
        ) : null}
      </p>
      {details ? (
        <details>
          <summary>Provenance and limits</summary>
          <dl>
            <dt>Provider / product</dt>
            <dd>
              {value.provider ?? "Unknown"} · {value.product ?? "Unknown"}
            </dd>
            <dt>Publication</dt>
            <dd>
              {value.publishedAt
                ? formatUtc(value.publishedAt)
                : "Unknown; receipt is not publication"}
            </dd>
            <dt>First availability</dt>
            <dd>{formatUtc(value.firstAvailableAt)}</dd>
            <dt>Last successful check</dt>
            <dd>{formatUtc(value.lastSuccessfulCheckAt)}</dd>
            <dt>Precision / units</dt>
            <dd>
              {value.timePrecision ?? "Unknown"} · {value.unit ?? "Unknown"}
            </dd>
            <dt>Coverage</dt>
            <dd>{value.geography ?? "Unknown"}</dd>
            <dt>Original SHA-256</dt>
            <dd className="break-all">{value.sha256 ?? "Unknown"}</dd>
          </dl>
          {value.source ? (
            <a href={value.source} target="_blank" rel="noreferrer">
              Provider product
            </a>
          ) : null}
          <p>{value.limit}</p>
        </details>
      ) : null}
    </div>
  );
}
