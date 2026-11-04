import { Navigate, createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/company/")({
  head: () => ({ meta: [{ title: "PortWatch X — Fleet Command" }] }),
  component: () => <Navigate to="/company/overview" replace />,
});
