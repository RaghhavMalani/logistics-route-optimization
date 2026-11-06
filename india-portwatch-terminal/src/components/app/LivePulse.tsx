import { ageLabel, useSourceHealth } from "@/services/source-health";
import { useWorkspaceHandoffs } from "@/services/handoffs";

export function LivePulse() {
  useWorkspaceHandoffs();
  const health = useSourceHealth();
  return <nav aria-label="Live source freshness" data-testid="live-pulse"
    className="flex h-7 shrink-0 items-center gap-4 overflow-x-auto border-b border-[var(--line)] bg-[var(--panel)] px-3 font-mono text-[10px] text-[var(--text-2)]">
    <a href="/sources" className="shrink-0 uppercase tracking-wider">Sources</a>
    {!health.data ? <span>{health.isError ? "Unavailable · retained source health" : "Checking retained snapshots"}</span> : null}
    {health.data?.sources.map((source) => <a key={source.id} href="/sources" data-source={source.id} data-status={source.status}
      className={`flex shrink-0 items-center gap-1.5 ${source.status === "live" ? "" : "text-[var(--text-3)]"}`}
      title={`${source.name}: ${source.status}; ${source.lastError ?? source.detail}`}>
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${source.status === "live" ? "bg-emerald-700" : source.status === "stale" ? "bg-amber-600" : "bg-neutral-400"}`} />
      <span>{source.name}</span>
      <span>{source.dataAgeSeconds == null ? "—" : ageLabel(source.dataAgeSeconds)}</span>
      <span className="sr-only">{source.status}</span>
    </a>)}
  </nav>;
}
