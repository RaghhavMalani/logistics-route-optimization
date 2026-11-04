import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { ApiError, getJson } from "@/services/api";

interface HomeHandoff {
  id: string;
  vesselName: string;
  portCode: string;
  state: string;
  nextActor: string | null;
  deepLink: string | null;
}

export function WorkspaceHandoffCard({ view }: { view: "vessel" | "company" }) {
  const { session, identityHeaders } = useAuth();
  const isVessel = view === "vessel";
  const query = useQuery({
    queryKey: [
      "workspace-handoffs",
      session?.demoId ?? session?.user.id,
      session?.user.role,
    ],
    enabled: Boolean(session),
    refetchInterval: 8000,
    retry: false,
    queryFn: async ({ signal }) => {
      try {
        return (
          await getJson<{ items: HomeHandoff[] }>(
            "/handoffs",
            identityHeaders,
            { signal },
          )
        ).items;
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
  const matches =
    query.data?.filter((item) =>
      isVessel
        ? item.nextActor === "VESSEL_OPERATOR" &&
          item.deepLink?.startsWith("/vessel/advisories?advisory=")
        : item.state === "ACCEPTED",
    ) ?? [];
  if (!isVessel && !matches.length) return null;
  return (
    <section
      aria-label={isVessel ? "Needs your action" : "Accepted handoffs"}
      className="pointer-events-auto max-h-40 shrink-0 overflow-auto rounded border border-[var(--line-strong)] bg-[var(--panel)] p-2 text-xs"
    >
      <h2 className="font-semibold">
        {isVessel ? "Needs your action" : "Accepted handoffs"}
        {matches.length ? ` · ${matches.length}` : ""}
      </h2>
      {query.isError ? (
        <button
          type="button"
          className="underline"
          onClick={() => void query.refetch()}
        >
          Handoffs unavailable · retry
        </button>
      ) : query.isPending ? (
        <p>Checking Port advisories…</p>
      ) : query.data === null ? (
        <a href="/vessel/advisories" className="underline">
          Open the advisory register
        </a>
      ) : matches.length === 0 ? (
        <p>No issued advisory needs your response.</p>
      ) : (
        matches.map((item) => (
          <div
            key={item.id}
            className="mt-2 border-t border-[var(--line)] pt-2"
          >
            <strong>{item.vesselName}</strong> · {item.portCode}
            <p>
              {item.state === "ACCEPTED"
                ? "Accepted by Vessel"
                : item.state === "ACKNOWLEDGED"
                  ? "Acknowledged · awaiting your response"
                  : "Issued by Port"}
            </p>
            {item.deepLink?.startsWith(`/${view}/advisories?advisory=`) ? (
              <a href={item.deepLink} className="font-semibold underline">
                Open advisory
              </a>
            ) : null}
          </div>
        ))
      )}
    </section>
  );
}
