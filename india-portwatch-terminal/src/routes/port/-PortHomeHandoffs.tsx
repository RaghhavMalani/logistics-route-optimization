import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson } from "@/services/api";
import { useWorkspaceHandoffs } from "@/services/handoffs";

interface Handoff {
  id: string;
  state?: string;
  vesselName: string;
  summary: string;
  portCode: string;
  nextActor: string | null;
  deepLink: string | null;
}

export function PortHomeHandoffs({ portCode }: { portCode: string }) {
  const { session, identityHeaders } = useAuth();
  const feed = useWorkspaceHandoffs();
  const useLegacy = feed.data === null && session?.mode === "demo";
  const fallback = useQuery<Handoff[]>({
    queryKey: [
      "port-home-handoffs",
      session?.demoId ?? session?.user.id,
      portCode,
    ],
    enabled: useLegacy,
    refetchInterval: 8000,
    retry: false,
    queryFn: async ({ signal }) => {
      const result = await getJson<{
        proposals: {
          decisionId: string;
          subject: string;
          evidence: { portCode?: string };
        }[];
      }>("/decisions/current-proposals", identityHeaders, { signal });
      return result.proposals
        .filter((row) => row.evidence.portCode === portCode)
        .map((row) => ({
          id: row.decisionId,
          vesselName: row.subject,
          portCode,
          summary: "Company proposal awaiting review in the Port register.",
          nextActor: "PORT_AUTHORITY",
          deepLink:
            "/port/advisories?proposal=" + encodeURIComponent(row.decisionId),
        }));
    },
  });
  const queue = useLegacy ? fallback : feed;
  const needs =
    queue.data?.filter(
      (row) =>
        row.portCode === portCode &&
        row.nextActor === "PORT_AUTHORITY" &&
        row.deepLink?.startsWith("/port/advisories?proposal="),
    ) ?? [];
  return (
    <section
      aria-label="Needs your action"
      className="pointer-events-auto max-h-44 shrink-0 overflow-auto rounded border border-[var(--line-strong)] bg-[var(--panel)] p-2 text-xs"
    >
      <h2 className="font-semibold">
        Needs your action{needs.length ? ` · ${needs.length}` : ""}
      </h2>
      {queue.isError ? (
        <button
          type="button"
          className="underline"
          onClick={() => void queue.refetch()}
        >
          Handoffs unavailable · retry
        </button>
      ) : queue.isPending ? (
        <p>Checking Company proposals…</p>
      ) : needs.length === 0 ? (
        <p>No Company proposals need Port action.</p>
      ) : (
        needs.map((row) => (
          <div key={row.id} className="mt-2 border-t border-[var(--line)] pt-2">
            <strong>{row.vesselName}</strong>
            {row.state === "ACCEPTED" ? (
              <span className="ml-2 font-semibold">Accepted by Vessel</span>
            ) : null}
            <p className="text-[var(--text-2)]">{row.summary}</p>
            <a
              href={row.deepLink ?? undefined}
              className="mt-1 inline-block font-semibold underline"
            >
              {row.state === "ACCEPTED"
                ? "Review accepted proposal"
                : "Review proposal"}
            </a>
          </div>
        ))
      )}
    </section>
  );
}
