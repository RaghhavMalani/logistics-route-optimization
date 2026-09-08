import { createFileRoute } from "@tanstack/react-router";

import { Page, PageBody, PageHeader } from "@/components/kit/layout";

export const Route = createFileRoute("/vessel/$vesselId")({ component: VesselDetail });

function VesselDetail() {
  return (
    <Page>
      <PageHeader title="Vessel" />
      <PageBody>
        <div className="text-[12px] text-[var(--text-3)]">Under construction.</div>
      </PageBody>
    </Page>
  );
}
