import { createFileRoute, redirect } from "@tanstack/react-router";

/** Legacy address from the single-workspace terminal; kept so old links resolve. */
export const Route = createFileRoute("/nlp")({
  beforeLoad: () => {
    throw redirect({ to: "/admin/intelligence", replace: true });
  },
});
