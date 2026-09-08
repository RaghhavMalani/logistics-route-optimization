import { createFileRoute } from "@tanstack/react-router";

import { Page, PageBody, PageHeader } from "@/components/kit/layout";

export const Route = createFileRoute("/port/weather")({ component: PortWeather });

function PortWeather() {
  return (
    <Page>
      <PageHeader title="Weather" />
      <PageBody>
        <div className="text-[12px] text-[var(--text-3)]">Under construction.</div>
      </PageBody>
    </Page>
  );
}
