import { createFileRoute } from "@tanstack/react-router";

import { Page, PageBody, PageHeader } from "@/components/kit/layout";

export const Route = createFileRoute("/admin/intelligence")({ component: AdminIntelligence });

function AdminIntelligence() {
  return (
    <Page>
      <PageHeader title="Event Intelligence" />
      <PageBody>
        <div className="text-[12px] text-[var(--text-3)]">Under construction.</div>
      </PageBody>
    </Page>
  );
}
