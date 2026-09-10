import { createFileRoute } from "@tanstack/react-router";

import { AdvisoryScreen } from "@/components/advisory/AdvisoryScreen";

export const Route = createFileRoute("/vessel/advisories")({ component: VesselAdvisories });

/**
 * Advisories addressed to this vessel.
 *
 * A recommendation, never an instruction. Declining is a normal answer and
 * costs nothing; PortWatch does not control vessel navigation.
 */
function VesselAdvisories() {
  return (
    <AdvisoryScreen
      title="Advisories"
      context="Recommendations from port authorities — advisory, not instruction"
      side="recipient"
    />
  );
}
