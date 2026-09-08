import { createFileRoute } from "@tanstack/react-router";

import { Page, PageBody, PageHeader } from "@/components/kit/layout";

export const Route = createFileRoute("/port/vessels")({ component: PortVessels });

function PortVessels() {
  return (
    <Page>
      <PageHeader title="Vessels" />
      <PageBody>
        <div className="text-[12px] text-[var(--text-3)]">Under construction.</div>
      </PageBody>
    </Page>
  );
}
