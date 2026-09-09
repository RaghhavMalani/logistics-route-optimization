import { createFileRoute } from "@tanstack/react-router";

import { GlobalEyeScreen } from "@/components/globaleye/GlobalEyeScreen";

export const Route = createFileRoute("/company/global-eye")({ component: CompanyGlobalEye });

/**
 * Global Eye, scoped to one fleet.
 *
 * Same chain, one filter: vessel exposure is computed against this carrier's
 * voyages, so the "Vessels" tab answers "what impacts my fleet" rather than
 * "what is happening in the world".
 */
function CompanyGlobalEye() {
  return <GlobalEyeScreen scope="company" title="Global Eye — Fleet exposure" />;
}
