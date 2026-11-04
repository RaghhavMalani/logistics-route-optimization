import { createFileRoute } from "@tanstack/react-router";

import { AdvisoryScreen } from "@/components/advisory/AdvisoryScreen";

export const Route = createFileRoute("/port/advisories")({
  component: PortAdvisories,
});

/**
 * The issuing side of the advisory workflow.
 *
 * A controller reviews what the decision engine drafted, modifies it if the
 * recommendation does not survive contact with the day, and issues or rejects
 * it. Nothing reaches a vessel without passing through this screen.
 */
function PortAdvisories() {
  return (
    <div className="flex h-full min-h-0 flex-col [&_[data-testid=decision-approve]]:bg-[var(--action)] [&_[data-testid=advisory-action-issued]]:bg-[var(--action)] [&_[data-testid=decision-approve]]:text-white [&_[data-testid=advisory-action-issued]]:!text-white">
      <AdvisoryScreen
        title="Advisories"
        context="Review, modify and issue recommendations to vessels"
        side="issuer"
      />
    </div>
  );
}
