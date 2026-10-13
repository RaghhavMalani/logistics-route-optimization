import { createFileRoute } from "@tanstack/react-router";
import { PublicResearch } from "@/components/public/PublicResearch";

export const Route = createFileRoute("/research")({
  component: PublicResearch,
  head: () => ({
    meta: [
      { title: "PortWatch — Research results" },
      {
        name: "description",
        content:
          "Chronological shipping-intelligence benchmarks, calibration, ablations and reproducible public research results.",
      },
    ],
  }),
});
