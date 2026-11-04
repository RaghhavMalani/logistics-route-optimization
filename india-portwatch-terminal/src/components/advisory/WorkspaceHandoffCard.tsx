import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { ApiError, getJson } from "@/services/api";

export interface HomeHandoff {
  id: string;
  vesselName: string;
  portCode: string;
  state: string;
  nextActor: string | null;
  deepLink: string | null;
  advisoryId?: string;
}

const companyStages: Record<string, string> = {
  COMPANY_PROPOSED: "Waiting on Port",
  PORT_REVIEWING: "Waiting on Port",
  ISSUED_TO_VESSEL: "Issued to Vessel",
  ACKNOWLEDGED: "Issued to Vessel · receipt acknowledged",
  ACCEPTED: "Accepted by Vessel",
  OUTCOME_RECORDED: "Outcome completed",
  COMPLETED: "Outcome completed",
};

export function useWorkspaceHandoffs(enabled = true) {
  const { session, identityHeaders } = useAuth();
  return useQuery({
    queryKey: [
      "workspace-handoffs",
      session?.demoId ?? session?.user.id,
      session?.user.role,
    ],
    enabled: enabled && Boolean(session),
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
}

export function WorkspaceHandoffCard({ view }: { view: "vessel" | "company" }) {
  const { session } = useAuth();
  const isVessel = view === "vessel";
  const demoCompany = !isVessel && session?.mode === "demo";
  const title = isVessel
    ? "Needs your action"
    : demoCompany
      ? "Fleet handoffs"
      : "Accepted handoffs";
  const query = useWorkspaceHandoffs();
  const matches =
    query.data?.filter((item) =>
      isVessel
        ? item.nextActor === "VESSEL_OPERATOR" &&
          item.deepLink?.startsWith("/vessel/advisories?advisory=")
        : demoCompany
          ? item.state in companyStages
          : item.state === "ACCEPTED",
    ) ?? [];
  if (!isVessel && !demoCompany && !matches.length) return null;
  return (
    <section
      aria-label={title}
      className="pointer-events-auto max-h-40 shrink-0 overflow-auto rounded border border-[var(--line-strong)] bg-[var(--panel)] p-2 text-xs"
    >
      <h2 className="font-semibold">
        {title}
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
        <p>Checking handoffs…</p>
      ) : query.data === null && isVessel ? (
        <a href="/vessel/advisories" className="underline">
          Open the advisory register
        </a>
      ) : matches.length === 0 ? (
        <p>
          {isVessel
            ? "No issued advisory needs your response."
            : "No fleet handoffs yet."}
        </p>
      ) : (
        matches.map((item) => (
          <div
            key={item.id}
            className="mt-2 border-t border-[var(--line)] pt-2"
          >
            <strong>{item.vesselName}</strong> · {item.portCode}
            <p>
              {isVessel
                ? item.state === "ACKNOWLEDGED"
                  ? "Acknowledged · awaiting your response"
                  : "Issued by Port"
                : companyStages[item.state]}
            </p>
            {item.deepLink?.startsWith(`/${view}/advisories?advisory=`) ||
            (!isVessel &&
              item.deepLink?.startsWith(
                "/company/global-eye#fleet-review?",
              )) ? (
              <a href={item.deepLink} className="font-semibold underline">
                {item.deepLink.includes("#fleet-review?")
                  ? "Open Company comparison"
                  : "Open advisory"}
              </a>
            ) : null}
          </div>
        ))
      )}
    </section>
  );
}
