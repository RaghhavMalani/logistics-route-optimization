import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/vessel/")({
  beforeLoad: () => {
    throw redirect({ to: "/vessel/overview", replace: true });
  },
});
