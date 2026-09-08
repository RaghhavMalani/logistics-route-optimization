import { createFileRoute, redirect } from "@tanstack/react-router";

/** Legacy address from the single-workspace terminal; kept so old links resolve. */
export const Route = createFileRoute("/sar")({
  beforeLoad: () => {
    throw redirect({ to: "/admin/vessels", replace: true });
  },
});
