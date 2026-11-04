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
        const result = await getJson<{ items: HomeHandoff[] }>(
          "/handoffs",
          identityHeaders,
          { signal },
        );
        return result.items;
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
}
