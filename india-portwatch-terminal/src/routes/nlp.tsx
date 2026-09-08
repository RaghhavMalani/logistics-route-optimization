import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  Chip,
  ErrorState,
  Loading,
  Metric,
  Panel,
  Value,
  formatUtc,
  riskTone,
} from "@/components/terminal/ui";
import { fetchNews } from "@/services/portwatch";

export const Route = createFileRoute("/nlp")({
  validateSearch: (search: Record<string, unknown>) => ({
    entity: typeof search.entity === "string" ? search.entity : "ALL",
  }),
  component: EventIntelligence,
});

/**
 * Event intelligence. Each row is a document -- a GDELT article or a GDACS
 * disaster alert -- with the ports it was attributed to and the lane exposure
 * that justified the attribution. Every headline links back to its source, so
 * nothing on this screen is an unverifiable claim.
 */
function EventIntelligence() {
  const { entity } = Route.useSearch();
  const navigate = useNavigate();

  const newsQuery = useQuery({
    queryKey: ["news"],
    queryFn: fetchNews,
    staleTime: 60_000,
  });

  if (newsQuery.isLoading) return <Loading label="LOADING EVENT STREAM" />;
  if (newsQuery.isError || !newsQuery.data) {
    return <ErrorState error={newsQuery.error} />;
  }

  const bundle = newsQuery.data;
  const filter = entity.toUpperCase();
  const events =
    filter === "ALL"
      ? bundle.events
      : bundle.events.filter(
          (event) =>
            event.chokepoint?.toUpperCase().includes(filter) ||
            event.entity.toUpperCase().includes(filter) ||
            event.title.toUpperCase().includes(filter) ||
            event.affectedPorts.some((code) => code.toUpperCase() === filter),
        );

  const chokepointCounts = new Map<string, number>();
  for (const event of bundle.events) {
    const key = event.chokepoint ?? "UNATTRIBUTED";
    chokepointCounts.set(key, (chokepointCounts.get(key) ?? 0) + 1);
  }

  // The model's news features are keyed to the observed panel, which trails the
  // event feed; the footnote below makes that lag explicit rather than letting
  // a flat risk column read as a bug.
  const featureDate = bundle.alerts.find((alert) => alert.ts)?.ts ?? null;

  const severeCount = bundle.events.filter((e) => e.severity === "severe").length;
  const meanSeverity = bundle.events.length
    ? bundle.events.reduce((sum, e) => sum + e.severityScore, 0) /
      bundle.events.length
    : 0;

  return (
    <div className="h-full grid grid-rows-[auto_1fr] gap-2 p-2 overflow-hidden">
      <div className="grid grid-cols-4 gap-2">
        <Metric
          label="ATTRIBUTED EVENTS"
          value={bundle.summary.totalEvents}
          tone="cyan"
          sub={bundle.summary.dataSource}
        />
        <Metric
          label="SEVERE EVENTS"
          value={severeCount}
          tone="red"
          sub="severity >= 0.75"
        />
        <Metric
          label="MEAN SEVERITY"
          value={meanSeverity.toFixed(2)}
          tone="amber"
          sub="0-1, decays with recency in the model"
        />
        <Metric
          label="PORT ALERTS"
          value={bundle.summary.totalAlerts}
          tone="purple"
          sub="raised by the decision engine"
        />
      </div>

      <div className="min-h-0 grid grid-cols-[1.5fr_1fr] gap-2">
        <Panel
          title="EVENT STREAM"
          right={
            <span className="flex items-center gap-1">
              {["ALL", "HORMUZ", "SUEZ", "BAB_EL_MANDEB", "MALACCA"].map((key) => (
                <button
                  key={key}
                  onClick={() => navigate({ to: "/nlp", search: { entity: key } })}
                  className={`px-1.5 py-[1px] border text-[9px] tracking-widest ${
                    filter === key
                      ? "border-[var(--color-cyan)] text-[var(--color-cyan)]"
                      : "border-[var(--color-line-strong)] text-[var(--color-muted-foreground)]"
                  }`}
                >
                  {key === "BAB_EL_MANDEB" ? "BAB" : key}
                </button>
              ))}
            </span>
          }
          bodyClassName="overflow-auto"
        >
          <div className="divide-y divide-[var(--color-line)]/30">
            {events.map((event) => (
              <div key={event.id} className="p-2.5">
                <div className="flex items-start gap-2">
                  <Chip tone={riskTone(event.severity)}>{event.tag}</Chip>
                  <a
                    href={event.url || undefined}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-[11px] leading-snug text-[var(--color-foreground)] hover:text-[var(--color-cyan)] hover:underline flex-1"
                  >
                    {event.title}
                  </a>
                  <span className="text-[9px] tabular-nums text-[var(--color-muted-foreground)] shrink-0">
                    {event.severityScore.toFixed(2)}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-2 text-[9px] text-[var(--color-muted-foreground)] flex-wrap">
                  <span>{event.source}</span>
                  <span>·</span>
                  <span>{formatUtc(event.timestamp)}</span>
                  {event.chokepointName && (
                    <>
                      <span>·</span>
                      <span className="text-[var(--color-cyan)]">
                        {event.chokepointName}
                      </span>
                    </>
                  )}
                </div>
                {event.exposure.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {event.exposure.slice(0, 6).map((port) => (
                      <button
                        key={port.portCode}
                        onClick={() =>
                          navigate({ to: "/port", search: { port: port.portCode } })
                        }
                        title={`Lane exposure ${port.exposure.toFixed(2)}`}
                        className="px-1.5 py-[1px] border border-[var(--color-line-strong)] text-[9px] tracking-widest text-[var(--color-muted-foreground)] hover:text-[var(--color-cyan)] hover:border-[var(--color-cyan)]/60"
                      >
                        {port.name}
                        <span className="ml-1 tabular-nums text-[var(--color-cyan)]">
                          {port.exposure.toFixed(2)}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {!events.length && (
              <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
                {bundle.summary.eventsAvailable
                  ? `No events matched "${filter}".`
                  : bundle.summary.dataSource}
              </div>
            )}
          </div>
        </Panel>

        <div className="min-h-0 grid grid-rows-[auto_auto_1fr] gap-2">
          <Panel title="ATTRIBUTION BY LANE">
            <div className="p-3 space-y-2">
              {Array.from(chokepointCounts.entries())
                .sort((a, b) => b[1] - a[1])
                .map(([key, count]) => (
                  <div key={key}>
                    <div className="flex justify-between text-[10px]">
                      <span
                        className={
                          key === "UNATTRIBUTED"
                            ? "text-[var(--color-muted-foreground)]"
                            : "text-[var(--color-foreground)]"
                        }
                      >
                        {key === "UNATTRIBUTED" ? "No lane attribution" : key}
                      </span>
                      <span className="tabular-nums">{count}</span>
                    </div>
                    <Bar
                      value={count / Math.max(bundle.events.length, 1)}
                      tone={key === "UNATTRIBUTED" ? "muted" : "cyan"}
                    />
                  </div>
                ))}
              <div className="text-[9px] leading-snug text-[var(--color-muted-foreground)] pt-1">
                A chokepoint event reaches a port in proportion to that port's
                measured lane exposure. An unattributed headline enters at a
                reduced national weight instead of hitting every berth equally.
              </div>
            </div>
          </Panel>

          <Panel title="PORT ALERTS · DECISION ENGINE">
            <div className="p-2 space-y-1">
              {bundle.alerts.map((alert) => (
                <button
                  key={alert.id}
                  onClick={() =>
                    navigate({ to: "/port", search: { port: alert.portCode } })
                  }
                  className="w-full text-left grid grid-cols-[58px_1fr] items-start gap-2 px-1 py-1 text-[10px] hover:bg-[var(--color-cyan)]/5"
                >
                  <Chip tone={riskTone(alert.severity)}>
                    {alert.severity.toUpperCase()}
                  </Chip>
                  <span className="leading-snug">
                    {alert.text}
                    <span className="block text-[9px] text-[var(--color-muted-foreground)]">
                      {alert.action} · priority{" "}
                      <Value value={alert.priority} digits={2} /> · confidence{" "}
                      <Value value={alert.confidence} digits={2} />
                    </span>
                  </span>
                </button>
              ))}
              {!bundle.alerts.length && (
                <div className="text-[10px] text-[var(--color-muted-foreground)]">
                  No port alerts were raised in this run.
                </div>
              )}
            </div>
          </Panel>

          <Panel
            title="PORT-LEVEL EVENT RISK"
            right={
              featureDate ? `aligned to ${formatUtc(featureDate)}` : undefined
            }
          >
            <div className="overflow-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="label-xs text-left border-b border-[var(--color-line)]">
                    <th className="py-1.5 px-2 font-normal">PORT</th>
                    <th className="py-1.5 px-2 font-normal text-right">MENTIONS</th>
                    <th className="py-1.5 px-2 font-normal text-right">GEO RISK</th>
                    <th className="py-1.5 px-2 font-normal text-right">TONE</th>
                    <th className="py-1.5 px-2 font-normal text-right">CONF</th>
                  </tr>
                </thead>
                <tbody>
                  {bundle.sentiment.map((row) => (
                    <tr
                      key={row.entity}
                      className="border-b border-[var(--color-line)]/30"
                    >
                      <td className="py-1 px-2">{row.entity}</td>
                      <td className="py-1 px-2 text-right tabular-nums">
                        {row.mentions}
                      </td>
                      <td className="py-1 px-2 text-right tabular-nums">
                        <Value value={row.riskScore} digits={3} />
                      </td>
                      <td className="py-1 px-2 text-right tabular-nums">
                        <Value value={row.sentiment} digits={3} />
                      </td>
                      <td className="py-1 px-2 text-right tabular-nums text-[var(--color-cyan)]">
                        <Value value={row.confidence} digits={2} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!bundle.sentiment.length && (
                <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
                  The news expert produced no port-level features in this run.
                </div>
              )}
            </div>
            <div className="px-2 py-1.5 text-[9px] leading-snug text-[var(--color-muted-foreground)] border-t border-[var(--color-line)]/50">
              These features are aligned to the observed port panel, which ends
              {featureDate ? ` ${formatUtc(featureDate)}` : ""} — the IMF
              PortWatch feed publishes with a lag. Events newer than that date
              appear in the stream and in the mention counts, but cannot yet
              influence the forecast. <span className="text-[var(--color-amber)]">
              Mentions</span> counts the current event stream;{" "}
              <span className="text-[var(--color-amber)]">geo risk</span> and{" "}
              <span className="text-[var(--color-amber)]">tone</span> are the
              model's features on the last observed day.
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
