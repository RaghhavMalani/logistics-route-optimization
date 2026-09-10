import { Navigate, createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/company/")({
  component: () => <Navigate to="/company/overview" replace />,
});
