import { Outlet, createFileRoute } from "@tanstack/react-router";

import { ADMIN_ACCESS, RoleGuard } from "@/auth/guards";
import { AppShell } from "@/components/app/AppShell";
import { WorkspaceNotFound } from "@/components/app/WorkspaceNotFound";

export const Route = createFileRoute("/admin")({
  component: AdminWorkspace,
  // Rendered into this layout's Outlet, so the guard and the shell are already
  // around it: an unknown child address keeps the rail rather than going blank.
  notFoundComponent: WorkspaceNotFound,
});

function AdminWorkspace() {
  return (
    <RoleGuard allow={ADMIN_ACCESS}>
      <AppShell>
        <Outlet />
      </AppShell>
    </RoleGuard>
  );
}
