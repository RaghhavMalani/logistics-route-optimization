import { createFileRoute } from "@tanstack/react-router";

import { Page, PageBody, PageHeader } from "@/components/kit/layout";

export const Route = createFileRoute("/vessel/ports")({ component: DestinationPorts });

function DestinationPorts() {
  return (
    <Page>
      <PageHeader title="Destination Ports" />
      <PageBody>
        <div className="text-[12px] text-[var(--text-3)]">Under construction.</div>
      </PageBody>
    </Page>
  );
}
