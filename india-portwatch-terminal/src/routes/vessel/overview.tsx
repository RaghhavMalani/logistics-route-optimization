import { createFileRoute } from "@tanstack/react-router";

import { Page, PageBody, PageHeader } from "@/components/kit/layout";

export const Route = createFileRoute("/vessel/overview")({ component: VesselOverview });

function VesselOverview() {
  return (
    <Page>
      <PageHeader title="Fleet Overview" />
      <PageBody>
        <div className="text-[12px] text-[var(--text-3)]">Under construction.</div>
      </PageBody>
    </Page>
  );
}
