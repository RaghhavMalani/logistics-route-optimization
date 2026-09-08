import { createFileRoute } from "@tanstack/react-router";

import { Page, PageBody, PageHeader } from "@/components/kit/layout";

export const Route = createFileRoute("/admin/scenarios")({ component: AdminScenarios });

function AdminScenarios() {
  return (
    <Page>
      <PageHeader title="Scenario Room" />
      <PageBody>
        <div className="text-[12px] text-[var(--text-3)]">Under construction.</div>
      </PageBody>
    </Page>
  );
}
