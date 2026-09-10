import { createFileRoute } from "@tanstack/react-router";

import { AdvisoryScreen } from "@/components/advisory/AdvisoryScreen";

export const Route = createFileRoute("/company/advisories")({ component: CompanyAdvisories });

/**
 * Advisories addressed to this carrier.
 *
 * The recipient side of the workflow: accept, request review, or decline. A
 * draft a port controller is still working on is not visible here, and the
 * screen says so where the list is empty.
 */
function CompanyAdvisories() {
  return (
    <AdvisoryScreen
      title="Advisories"
      context="Recommendations issued to this fleet by port authorities"
      side="recipient"
    />
  );
}
