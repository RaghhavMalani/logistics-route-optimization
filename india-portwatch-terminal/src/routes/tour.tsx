import { lazy, Suspense } from "react";
import { createFileRoute } from "@tanstack/react-router";
import tourCss from "@/components/tour/tour.css?url";
const TourPage = lazy(() => import("@/components/tour/TourPage"));
export const Route = createFileRoute("/tour")({
  component: () => (
    <Suspense fallback={null}>
      <TourPage />
    </Suspense>
  ),
  head: () => ({
    meta: [
      { title: "PortWatch X — Follow the miniature voyage" },
      {
        name: "description",
        content:
          "An illustrative voyage through PortWatch’s intelligence, shipping comparisons, port twin, cargo commitments and four role workspaces.",
      },
    ],
    links: [
      { rel: "stylesheet", href: tourCss },
      { rel: "stylesheet", href: "/fonts/miniature.css" },
      ...[
        "archivo-latin-variable.woff2",
        "ibm-plex-mono-latin-400.woff2",
        "ibm-plex-mono-latin-500.woff2",
      ].map((name) => ({
        rel: "preload",
        as: "font",
        type: "font/woff2",
        crossOrigin: "anonymous" as const,
        href: `/fonts/${name}`,
      })),
    ],
  }),
});
