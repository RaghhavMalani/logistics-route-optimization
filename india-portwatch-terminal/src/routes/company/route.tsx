import { Outlet, createFileRoute } from "@tanstack/react-router";

import { COMPANY_ACCESS, RoleGuard } from "@/auth/guards";
import { AppShell } from "@/components/app/AppShell";
import { WorkspaceNotFound } from "@/components/app/WorkspaceNotFound";

export const Route = createFileRoute("/company")({
  component: CompanyWorkspace,
  // Rendered into this layout's Outlet, so the guard and the shell are already
  // around it: an unknown child address keeps the rail rather than going blank.
  notFoundComponent: WorkspaceNotFound,
});

function CompanyWorkspace() {
  return (
    <RoleGuard allow={COMPANY_ACCESS}>
      <AppShell>
        <Outlet />
      </AppShell>
    </RoleGuard>
  );
}
