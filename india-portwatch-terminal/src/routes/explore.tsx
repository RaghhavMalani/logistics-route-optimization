import { createFileRoute } from "@tanstack/react-router";
import { PublicWorkspace } from "@/components/public/PublicWorkspace";
export const Route = createFileRoute("/explore")({
  component: PublicWorkspace,
  head: () => ({
    meta: [
      { title: "Explore shipping intelligence | PortWatch" },
      {
        name: "description",
        content:
          "Trace public global events to exposed ports, forecast uncertainty and shipping route scenarios.",
      },
    ],
  }),
});
