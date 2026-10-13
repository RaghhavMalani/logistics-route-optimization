import { useEffect, useState } from "react";
import { useLocation } from "@tanstack/react-router";
import { publicEvidenceUrl, usePublicCalls } from "@/services/public-research";
import { fmt, utc } from "./format";

const labels = {
  frozenEta: "Published ETA",
  reportedArrival: "Reported arrival",
  reportedBerth: "Reported berth",
};
function eventTime(value: string, zone: string) {
  return new Date(value).toLocaleString("en-GB", {
    timeZone: zone,
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function PublicPortCases() {
  const query = usePublicCalls();
  const [selectedEvent, setSelectedEvent] = useState("frozenEta");
  const [zone, setZone] = useState("Asia/Kolkata");
  const [selectedPort, setPort] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const linkedCaseId = useLocation({
    select: (location) =>
      location.hash.match(/^case-([a-f0-9]{64})$/)?.[1] ?? null,
  });
  const data = query.data;
  const linkedCase = data?.cases.find((c) => c.caseId === linkedCaseId);
  const port = selectedPort ?? linkedCase?.portCode ?? "INPRT";
  const cases = data?.cases.filter((c) => c.portCode === port) ?? [];
  const call =
    cases.find((c) => c.caseId === caseId) ??
    cases.find((c) => c.caseId === linkedCaseId) ??
    cases[0];
  const event =
    call?.events.find((e) => e.event === selectedEvent) ?? call?.events[0];
  const displayedCaseId = call?.caseId;
  useEffect(() => {
    if (linkedCaseId && displayedCaseId === linkedCaseId) {
      document.getElementById(`case-${linkedCaseId}`)?.scrollIntoView();
    }
  }, [linkedCaseId, displayedCaseId]);
  return (
    <section id="public-port-cases" className="public-case-study">
      <div className="public-section-title">
        <div>
          <p className="public-eyebrow">Prospective public evidence</p>
          <h2>A port call, from ETA to berth</h2>
        </div>
        <label>
          Public call port
          <select
            aria-label="Public call port"
            value={port}
            onChange={(e) => setPort(e.target.value)}
          >
            <option value="INPRT">Paradip · INPRT</option>
            <option value="INMAA">Chennai · INMAA</option>
          </select>
        </label>
      </div>
      {query.isPending ? (
        <p role="status">Loading the public call evidence.</p>
      ) : query.isError ? (
        <p role="alert">
          Public case evidence could not be loaded.{" "}
          <button type="button" onClick={() => void query.refetch()}>
            Retry case evidence
          </button>
        </p>
      ) : !data?.available ? (
        <p role="status">{data?.meaning}</p>
      ) : (
        <>
          {!data.ports.length && (
            <p role="status" className="public-note">
              Current collection status and freshness are unavailable. The
              archived, reviewed case remains independently available.
            </p>
          )}
          <div className="public-table-wrap public-freshness">
            <table>
              <caption>Collection freshness · three-hour schedule</caption>
              <thead>
                <tr>
                  <th scope="col">Port</th>
                  <th scope="col">Frozen ETAs</th>
                  <th scope="col">Matched arrivals</th>
                  <th scope="col">Complete</th>
                  <th scope="col">Latest successful check</th>
                  <th scope="col">Collection start delay</th>
                </tr>
              </thead>
              <tbody>
                {data.ports.map((p) => (
                  <tr key={p.portCode}>
                    <th scope="row">{p.portCode}</th>
                    <td>{p.frozen}</td>
                    <td>{p.matched}</td>
                    <td>{p.waitingOutcomes}</td>
                    <td>
                      {utc(p.lastSuccessfulCollectionAt)}
                      <small>
                        {p.freshness.toLowerCase()}
                        {p.collectionFailed ? " · latest run failed" : ""}
                      </small>
                    </td>
                    <td>
                      {p.collectionDelayMinutes == null
                        ? "Unavailable"
                        : `${fmt(p.collectionDelayMinutes, 0)} min after due time`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="public-note">
            Delay is measured at collection start against the preceding
            successful check plus three hours. It describes data freshness, not
            vessel delay.
          </p>
          {call && event ? (
            <article id={`case-${call.caseId}`} className="public-call">
              <div className="public-section-title">
                <div>
                  <span className="public-badge">
                    Visually reviewed public case
                  </span>
                  <h3>{call.vesselName}</h3>
                  <p>
                    {call.portCode} · {fmt(call.identity.loaMetres)} m LOA ×{" "}
                    {fmt(call.identity.beamMetres, 2)} m beam · berth{" "}
                    {call.berthRef}
                  </p>
                </div>
                <label>
                  Clock display
                  <select
                    aria-label="Case clock display"
                    value={zone}
                    onChange={(e) => setZone(e.target.value)}
                  >
                    <option value="Asia/Kolkata">IST (assumed)</option>
                    <option value="UTC">UTC</option>
                  </select>
                </label>
              </div>
              {cases.length > 1 && (
                <label>
                  Reviewed vessel
                  <select
                    value={call.caseId}
                    onChange={(e) => setCaseId(e.target.value)}
                  >
                    {cases.map((c) => (
                      <option key={c.caseId} value={c.caseId}>
                        {c.vesselName}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <div className="public-call-results">
                <div>
                  <span>Published ETA baseline error</span>
                  <strong>
                    {fmt(call.publishedEtaBaselineErrorMinutes, 0)} min
                  </strong>
                  <small>
                    {call.publishedEtaBaselineErrorMinutes < 0
                      ? "Reported arrival earlier than the frozen published ETA"
                      : "Reported arrival later than the frozen published ETA"}
                  </small>
                </div>
                <div>
                  <span>Reported arrival-to-berth waiting</span>
                  <strong>{fmt(call.reportedWaitingHours)} h</strong>
                  <small>Public berth time; all-fast remains unconfirmed</small>
                </div>
              </div>
              <ol
                className="public-call-timeline"
                aria-label="ETA to arrival to berth evidence timeline"
              >
                {call.events.map((e, i) => (
                  <li key={e.event}>
                    <button
                      type="button"
                      aria-pressed={event.event === e.event}
                      aria-label={`Inspect ${labels[e.event].toLowerCase()}`}
                      onClick={() => setSelectedEvent(e.event)}
                    >
                      <small>0{i + 1}</small>
                      <strong>{labels[e.event]}</strong>
                      <time dateTime={e.at}>{eventTime(e.at, zone)}</time>
                      <span>{zone === "UTC" ? "UTC" : "IST, assumed"}</span>
                    </button>
                  </li>
                ))}
              </ol>
              <div className="public-event-evidence" aria-live="polite">
                <div>
                  <h4>{labels[event.event]} evidence</h4>
                  <dl>
                    <dt>Raw publisher clock</dt>
                    <dd className="public-raw-clock">{event.rawClock}</dd>
                    <dt>Original first collected</dt>
                    <dd>{utc(event.firstSeenAt)}</dd>
                    <dt>Field became available</dt>
                    <dd>{utc(event.availableAt)}</dd>
                    <dt>Report / cited page</dt>
                    <dd>
                      {event.reportDate} · page {event.page}
                    </dd>
                  </dl>
                </div>
                <div className="public-evidence-actions">
                  <a
                    href={publicEvidenceUrl(event.url)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open archived {labels[event.event].toLowerCase()} PDF ↗
                  </a>
                  <a href={event.sourceUrl} target="_blank" rel="noreferrer">
                    Publisher report (may change) ↗
                  </a>
                  <details>
                    <summary>Hash and parser provenance</summary>
                    <p>
                      SHA-256 <code>{event.sha256}</code>
                    </p>
                    <p>
                      {event.parserVersion} · parsed {utc(event.parsedAt)}
                    </p>
                  </details>
                </div>
              </div>
              <div className="public-case-limits">
                <h4>Identity and uncertainty</h4>
                <p>
                  {call.identity.basis} {call.uncertainty}
                </p>
                {call.archivedPublication && (
                  <p className="public-note">
                    Archived public study published {utc(call.publishedAt)}. Its
                    frozen evidence is independent of this host’s current
                    collection counts.
                  </p>
                )}
                <p>{call.timezoneNote}</p>
                <p>{call.meaning}</p>
                <a href={publicEvidenceUrl(call.auditUrl)}>
                  Download public case audit ↓
                </a>
                {" · "}
                <a href={`/research#case-${call.caseId}`}>
                  Link to this case ↗
                </a>
                <small>
                  Visual review passed {utc(call.review.reviewedAt)}. One case
                  does not establish forecast accuracy or savings.
                </small>
              </div>
            </article>
          ) : (
            <p className="public-note">
              No complete, visually reviewed public case is available for this
              port at the displayed time. Pending and incomplete calls remain in
              collection.
            </p>
          )}
          {data.ports
            .filter((p) => p.parserIssues.length)
            .map((p) => (
              <details className="public-parser-note" key={p.portCode}>
                <summary>{p.portCode}: date and layout exclusions</summary>
                <p>
                  Conflicting publisher dates remain excluded; a parser revision
                  cannot backdate evidence availability or a frozen ETA.
                </p>
                <ul>
                  {p.parserIssues.map((issue, i) => (
                    <li key={`${issue.url}-${i}`}>
                      <a
                        href={publicEvidenceUrl(issue.url)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {issue.reportDate} · page {issue.page}
                      </a>
                      {" · "}
                      {issue.code.replaceAll("_", " ").toLowerCase()}
                      {issue.candidates.length > 0 &&
                        `: ${issue.candidates.join(" / ")}`}
                    </li>
                  ))}
                </ul>
              </details>
            ))}
        </>
      )}
    </section>
  );
}
