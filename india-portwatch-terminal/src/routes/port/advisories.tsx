import { createFileRoute } from "@tanstack/react-router";

import { AdvisoryScreen } from "@/components/advisory/AdvisoryScreen";

export const Route = createFileRoute("/port/advisories")({ component: PortAdvisories });

/**
 * The issuing side of the advisory workflow.
 *
 * A controller reviews what the decision engine drafted, modifies it if the
 * recommendation does not survive contact with the day, and issues or rejects
 * it. Nothing reaches a vessel without passing through this screen.
 */
function PortAdvisories() {
  return (
    <AdvisoryScreen
      title="Advisories"
      context="Review, modify and issue recommendations to vessels"
      side="issuer"
    />
  );
}
