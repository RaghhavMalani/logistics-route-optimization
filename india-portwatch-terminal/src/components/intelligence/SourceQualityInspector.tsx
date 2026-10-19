import type { ProvenanceSource } from "@/types/portwatch";
import {
  KeyValue,
  Pill,
  formatAge,
  formatUtc,
} from "@/components/kit/primitives";
import { Panel } from "@/components/kit/layout";
import { canonicalizePortCodes } from "@/types/source-quality";
import type { PortRegistryEntry } from "@/types/portwatch";

function known(value: string | number | null | undefined): string {
  return value == null || value === "" ? "Unknown" : String(value);
}

function date(value: string | null | undefined, precision?: string): string {
  if (value == null) return "Unknown";
  if (precision === "DATE_ONLY" || /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return `${value} (date only)`;
  }
  const formatted = formatUtc(value);
  return formatted === "—" ? "Unknown" : formatted;
}

/** Read-only evidence view. Legacy provenance fields remain useful, while
 * fields absent from the receipt stay explicitly unknown. */
export function SourceQualityInspector({
  source,
  portRegistry,
  onClose,
}: {
  source: ProvenanceSource | null;
  portRegistry?: readonly PortRegistryEntry[] | null;
  onClose?: () => void;
}) {
  if (!source) {
    return (
      <Panel
        title="Source evidence"
        className="shrink-0 rounded-none border-x-0 border-t-0"
      >
        <p className="px-3 py-3 text-[11px] text-[var(--text-3)]">
          Select a source to inspect its receipt and coverage evidence.
        </p>
      </Panel>
    );
  }

  const quality = source.sourceQuality;
  const receipt = quality?.receipt;
  const coverage = quality?.coverage;
  const provenance = quality?.provenance;
  const issues = quality?.quality;
  const unknowns = quality?.unknownReasons ?? [];
  const completeness = issues?.completeness;
  const portCodes = coverage?.portCodes;
  const portResolution =
    portCodes != null && portRegistry != null
      ? canonicalizePortCodes(portCodes, portRegistry)
      : null;
  const portCoverageLabel =
    portCodes == null
      ? "Ports unknown"
      : portCodes.length === 0
        ? "No ports reported"
        : portResolution == null
          ? `Registry unavailable · ${portCodes.join(", ")}`
          : [
              ...portResolution.canonical,
              ...portResolution.unresolved.map((code) => `Unresolved: ${code}`),
            ].join(", ") || "No registry matches";
  const variableCoverageLabel =
    coverage?.variables == null
      ? "variables unknown"
      : coverage.variables.length === 0
        ? "No variables reported"
        : coverage.variables.join(", ");

  return (
    <Panel
      title="Source evidence"
      actions={
        source && onClose ? (
          <button
            type="button"
            aria-label="Close source evidence inspector"
            onClick={onClose}
            className="rounded border border-[var(--line)] px-1.5 py-0.5 text-[10px] text-[var(--text-2)] hover:text-[var(--text)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--info)]"
          >
            Close
          </button>
        ) : undefined
      }
      note={
        <Pill tone={source.status === "STALE" ? "warn" : "info"}>
          {source.status.replace("_", " ")}
        </Pill>
      }
      className="h-full min-h-0 rounded-none border-x-0 border-t-0"
      scroll
      testId="source-quality-inspector"
    >
      <div className="px-3 py-2">
        <h3 className="mb-1 text-[12px] font-medium text-[var(--text)]">
          {source.source}
        </h3>
        <p className="mb-2 text-[10.5px] text-[var(--text-3)]">
          {source.provider || "Provider not supplied"}
        </p>
        {source.sourceQualityError ? (
          <p
            role="alert"
            className="mb-2 border-l-2 border-[var(--crit)] pl-2 text-[10.5px] text-[var(--crit)]"
          >
            Quality metadata rejected: {source.sourceQualityError}. Raw legacy
            provenance remains available below.
          </p>
        ) : !quality ? (
          <p className="mb-2 text-[10.5px] text-[var(--text-3)]">
            The service did not provide normalized quality metadata. Missing
            fields are shown as unknown.
          </p>
        ) : null}

        <KeyValue label="Temporal role" dense>
          {quality?.temporalRole ?? "Unknown"}
        </KeyValue>
        <KeyValue label="Value kind" dense>
          {quality?.valueKinds.join(", ") || "Unknown"}
        </KeyValue>
        <KeyValue label="Operational use" dense>
          {quality?.operationalUse ?? "Unknown"}
        </KeyValue>
        <KeyValue label="Last fetched" dense>
          <span className="num">
            {date(receipt?.lastFetchedAt ?? source.fetched_at)}
          </span>
        </KeyValue>
        <KeyValue label="Last checked" dense>
          <span className="num">{date(receipt?.lastCheckedAt)}</span>
        </KeyValue>
        <KeyValue label="Source observation through" dense>
          <span className="num">
            {date(
              coverage?.observedThrough ?? source.observed_at,
              coverage?.datePrecision,
            )}
          </span>
        </KeyValue>
        <KeyValue label="Observation start" dense>
          <span className="num">
            {date(coverage?.observedFrom, coverage?.datePrecision)}
          </span>
        </KeyValue>
        <KeyValue label="Forecast origin" dense>
          <span className="num">
            {date(coverage?.forecastOriginAt, coverage?.datePrecision)}
          </span>
        </KeyValue>
        <KeyValue label="Date precision" dense>
          {coverage?.datePrecision ?? "Unknown"}
        </KeyValue>
        <KeyValue label="Forecast target range" dense>
          <span className="num">
            {coverage?.targetFrom || coverage?.targetThrough
              ? `${date(coverage.targetFrom, coverage.datePrecision)} – ${date(coverage.targetThrough, coverage.datePrecision)}`
              : "Unknown"}
          </span>
        </KeyValue>
        <KeyValue label="Coverage" dense>
          {portCoverageLabel} · {variableCoverageLabel}
        </KeyValue>
        <KeyValue label="Observation age / budget" dense>
          <span className="num">
            {coverage?.observationAgeSeconds != null
              ? formatAge(coverage.observationAgeSeconds / 3600)
              : source.ageHours != null
                ? formatAge(source.ageHours)
                : "Unknown"}
            {coverage?.observationFreshnessBudgetSeconds != null
              ? ` / ${formatAge(coverage.observationFreshnessBudgetSeconds / 3600)}`
              : source.freshness_budget_hours != null
                ? ` / ${formatAge(source.freshness_budget_hours)}`
                : " / budget unknown"}
          </span>
        </KeyValue>
        <KeyValue label="Rows / completeness" dense>
          <span className="num">
            {known(issues?.rowCount ?? source.rows)} /{" "}
            {completeness == null
              ? "unknown"
              : `${(completeness * 100).toFixed(0)}%`}
          </span>
        </KeyValue>
        <KeyValue label="Receipt / product ID" dense>
          {known(provenance?.sourceReceiptId)} /{" "}
          {known(provenance?.sourceProductId)}
        </KeyValue>
        <KeyValue label="Original evidence" dense>
          {known(provenance?.originalRef)} · hash{" "}
          {known(provenance?.originalHash)}
        </KeyValue>

        {issues?.issues.length ? (
          <div className="mt-2 border-t border-[var(--line)] pt-2">
            <p className="text-[10px] uppercase tracking-wide text-[var(--warn)]">
              Quality issues
            </p>
            <ul className="mt-1 list-disc pl-4 text-[10.5px] text-[var(--text-2)]">
              {issues.issues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {unknowns.length ? (
          <div className="mt-2 border-t border-[var(--line)] pt-2">
            <p className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
              Why fields are unknown
            </p>
            <ul className="mt-1 list-disc pl-4 text-[10.5px] text-[var(--text-3)]">
              {unknowns.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </Panel>
  );
}
