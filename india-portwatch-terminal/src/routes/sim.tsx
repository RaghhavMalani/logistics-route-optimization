import { createFileRoute, redirect } from "@tanstack/react-router";

/** Legacy address from the single-workspace terminal; kept so old links resolve. */
export const Route = createFileRoute("/sim")({
  beforeLoad: () => {
    throw redirect({ to: "/admin/scenarios", replace: true });
  },
});
