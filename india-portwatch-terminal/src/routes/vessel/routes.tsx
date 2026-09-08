import { createFileRoute } from "@tanstack/react-router";

import { Page, PageBody, PageHeader } from "@/components/kit/layout";

export const Route = createFileRoute("/vessel/routes")({ component: RouteIntelligence });

function RouteIntelligence() {
  return (
    <Page>
      <PageHeader title="Route Intelligence" />
      <PageBody>
        <div className="text-[12px] text-[var(--text-3)]">Under construction.</div>
      </PageBody>
    </Page>
  );
}
