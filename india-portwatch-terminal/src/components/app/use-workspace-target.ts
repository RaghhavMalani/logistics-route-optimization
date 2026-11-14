import { useRouterState } from "@tanstack/react-router";

export function useWorkspaceTarget(
  key: "port" | "hull" | "scenario" | "command",
) {
  const search = useRouterState({
    select: (state) => state.location.searchStr,
  });
  return new URLSearchParams(search).get(key);
}

let pendingS10Command: string | null = null;

export function requestS10Command(command: string) {
  pendingS10Command = command;
}

export function consumeS10Command(command: string) {
  if (command !== pendingS10Command) return false;
  pendingS10Command = null;
  return true;
}
