import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/port/")({
  beforeLoad: () => {
    throw redirect({ to: "/port/overview", replace: true });
  },
});
