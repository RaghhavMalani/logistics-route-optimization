import { createFileRoute, redirect } from "@tanstack/react-router";

/** Legacy address from the single-workspace terminal; kept so old links resolve. */
export const Route = createFileRoute("/fleet")({
  beforeLoad: () => {
    throw redirect({ to: "/vessel/fleet", replace: true });
  },
});
