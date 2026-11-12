import { useRouterState } from "@tanstack/react-router";

export function useWorkspaceTarget(key: "port" | "hull" | "scenario") {
  const search = useRouterState({ select: (state) => state.location.searchStr });
  return new URLSearchParams(search).get(key);
}
