import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getJson, postJson } from "@/services/api";
import type { ArrivalWorkspace } from "@/services/arrivals";

const button =
  "rounded border border-[var(--line)] px-3 py-1.5 text-xs disabled:opacity-40";
const input =
  "w-full rounded border border-[var(--line)] bg-[var(--surface)] p-2 text-xs";
const headers = {
  operations:
    "operationRef,mmsi,vesselName,recipientOrganisation,plannedArrivalAt,baselineWaitHours,baselineSource,baselineRef,baselineEstimatedAt,baselineAvailableAt,routeRevision",
  outcomes:
    "operationRef,mmsi,arrivedAt,berthedAt,arrivalAvailableAt,allFastAvailableAt,availableAt,source,sourceRef,kind,berthRef",
};
type ImportResult = {
  status: string;
  count: number;
  rows: { row: number; operationRef: string }[];
};

export default function ArrivalCollection({
  state,
  live,
  busy,
  start,
}: {
  state: ArrivalWorkspace;
  live: boolean;
  busy: boolean;
  start: () => void;
}) {
  const q = state.collection;
  const queries = useQueryClient();
  const [kind, setKind] = useState<keyof typeof headers>("operations");
  const [csv, setCsv] = useState("");
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const changeCsv = (value: string) => {
    setCsv(value);
    setPreview(null);
    setMessage(null);
  };
  const run = async (commit: boolean) => {
    setImporting(true);
    setMessage(null);
    try {
      const result = await postJson<ImportResult>("/arrivals/import", {
        recordType: kind,
        csvText: csv,
        commit,
      });
      if (commit) {
        setPreview(null);
        setMessage(
          `Imported ${result.count} records. Originals are frozen in the ledger.`,
        );
        await queries.invalidateQueries({ queryKey: ["arrivals"] });
      } else setPreview(result);
    } catch (e) {
      setPreview(null);
      setMessage(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };
  const exportDataset = async () => {
    setImporting(true);
    setMessage(null);
    try {
      const dataset = await getJson("/arrivals/dataset");
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(dataset, null, 2)], {
          type: "application/json",
        }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = "jnpa-prospective-cohort.json";
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Export failed");
    } finally {
      setImporting(false);
    }
  };
  return (
    <div
      className="space-y-3 border border-[var(--line)] p-3"
      data-testid="arrival-collection"
    >
      <h3 className="font-medium">Prospective JNPA collection</h3>
      {q.cohort ? (
        <p className="text-xs">
          {q.cohort.status} · started{" "}
          {new Date(q.cohort.startedAt).toLocaleString()} · protocol{" "}
          {q.cohort.protocolHash.slice(0, 12)}
        </p>
      ) : (
        <p className="text-xs">
          Start the cohort before registering calls. Legacy and public berth
          records do not count toward this prospective dataset.
        </p>
      )}
      {q.cohort?.status !== "COLLECTING" && (
        <button className={button} disabled={!live || busy} onClick={start}>
          Start prospective cohort
        </button>
      )}
      {q.cohort && (
        <button
          className={button}
          disabled={importing}
          onClick={() => void exportDataset()}
        >
          Export cohort JSON
        </button>
      )}
      <p>
        {q.qualifyingCount} / 60 qualifying calls · {q.enrolledCount} enrolled ·{" "}
        {q.confirmedCount} confirmed
      </p>
      <p className="text-xs">
        {q.unresolvedCount} unresolved ({q.overdueCount} overdue) ·{" "}
        {q.missingEvidenceCount} missing evidence · {q.staleAisCount} stale AIS
        at issue · {q.duplicateCandidateCount} possible duplicate calls ·{" "}
        {q.excludedCount} exclusions
      </p>
      <p className="text-xs">
        AIS archive: {q.aisArchiveStatus}
        {q.latestAisObservedAt
          ? `; latest source time ${new Date(q.latestAisObservedAt).toLocaleString()}`
          : ""}
        . Refreshing AIS cannot repair an earlier frozen claim.
      </p>
      <p className="text-xs">
        {q.gateReason}. Required after purging: 24 fit, 10 calibration, 10
        holdout. Reaching these counts does not establish accuracy.
      </p>
      {q.partitions && (
        <p className="text-xs">
          Available split: {q.partitions.fit} fit · {q.partitions.calibration}{" "}
          calibration · {q.partitions.holdout} holdout · {q.partitions.purged}{" "}
          purged
        </p>
      )}
      {q.calls.some((c) => c.flags.length) && (
        <details>
          <summary className="cursor-pointer text-xs">
            Collection issues by call
          </summary>
          <ul className="space-y-1 pt-2 text-xs">
            {q.calls
              .filter((c) => c.flags.length)
              .map((c) => (
                <li key={c.operationId} className="break-words">
                  {c.operationRef}: {c.flags.join(", ")}
                </li>
              ))}
          </ul>
        </details>
      )}
      {state.publicEvidence && (
        <details data-testid="jnpa-public-evidence">
          <summary className="cursor-pointer text-xs">
            {state.publicEvidence.records.length} imported public berth records
            · awaiting verification
          </summary>
          <p className="py-2 text-xs">
            <a
              href={state.publicEvidence.source}
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              Official JNPA report
            </a>{" "}
            dated {state.publicEvidence.reportDate}; first seen{" "}
            {new Date(state.publicEvidence.retrievedAt).toLocaleString()}. MMSI,
            anchorage arrival, confirmed all-fast and scheduler estimates remain
            missing. These records contribute zero qualifying calls.
          </p>
          <ul className="space-y-1 text-xs">
            {state.publicEvidence.records.map((r) => (
              <li
                key={`${r.operationRef}:${r.berthRef}`}
                className="break-words"
              >
                {r.operationRef} · {r.vesselName} · {r.terminal}/{r.berthRef} ·
                reported berthed on {r.reportedBerthedOn}
              </li>
            ))}
          </ul>
        </details>
      )}
      <details>
        <summary className="cursor-pointer text-xs">
          Import operator / port-call CSV
        </summary>
        <div className="space-y-3 pt-3">
          <p className="text-xs">
            Timezone offsets are required. New claims freeze evidence when
            committed, before actual arrival. Outcome rows match both the
            registered call reference and MMSI. Public “berthed on” timestamps
            require verification as all-fast before importing outcomes.
          </p>
          <label className="grid gap-1 text-xs">
            CSV record type
            <select
              className={input}
              disabled={importing}
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as keyof typeof headers);
                setPreview(null);
                setMessage(null);
              }}
            >
              <option value="operations">
                Future arrivals and scheduler estimates
              </option>
              <option value="outcomes">Confirmed port-call outcomes</option>
            </select>
          </label>
          <a
            className="text-xs underline"
            download={`jnpa-${kind}-template.csv`}
            href={`data:text/csv;charset=utf-8,${encodeURIComponent(headers[kind] + "\n")}`}
          >
            Download CSV header template
          </a>
          <label className="grid gap-1 text-xs">
            CSV file
            <input
              type="file"
              accept=".csv,text/csv"
              disabled={importing || !live}
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                if (file.size > 250000) {
                  setMessage("CSV exceeds 250 KB");
                  setPreview(null);
                  return;
                }
                changeCsv(await file.text());
              }}
            />
          </label>
          <label className="grid gap-1 text-xs">
            CSV records
            <textarea
              className={`${input} font-mono`}
              rows={5}
              value={csv}
              disabled={importing}
              maxLength={250000}
              onChange={(e) => changeCsv(e.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              className={button}
              disabled={!live || importing || !csv.trim()}
              onClick={() => void run(false)}
            >
              Preview CSV
            </button>
            <button
              className={button}
              disabled={!live || importing || !preview}
              onClick={() => void run(true)}
            >
              Commit validated CSV
            </button>
          </div>
          {preview && (
            <p className="break-words text-xs" role="status">
              Preview: {preview.count} valid records. No writes kept.{" "}
              {preview.rows.map((r) => r.operationRef).join(", ")}
            </p>
          )}
          {message && (
            <p className="break-words text-xs" role="status">
              {message}
            </p>
          )}
        </div>
      </details>
    </div>
  );
}
