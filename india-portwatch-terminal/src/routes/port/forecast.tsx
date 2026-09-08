import { createFileRoute } from "@tanstack/react-router";

import { Page, PageBody, PageHeader } from "@/components/kit/layout";

export const Route = createFileRoute("/port/forecast")({ component: PortForecast });

function PortForecast() {
  return (
    <Page>
      <PageHeader title="Forecast" />
      <PageBody>
        <div className="text-[12px] text-[var(--text-3)]">Under construction.</div>
      </PageBody>
    </Page>
  );
}
