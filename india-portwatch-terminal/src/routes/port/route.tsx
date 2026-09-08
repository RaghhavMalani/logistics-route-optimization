import { Outlet, createFileRoute } from "@tanstack/react-router";

import { PORT_ACCESS, RoleGuard } from "@/auth/guards";
import { AppShell } from "@/components/app/AppShell";
import { WorkspaceNotFound } from "@/components/app/WorkspaceNotFound";

export const Route = createFileRoute("/port")({
  component: PortWorkspace,
  // Rendered into this layout's Outlet, so the guard and the shell are already
  // around it: an unknown child address keeps the rail rather than going blank.
  notFoundComponent: WorkspaceNotFound,
});

function PortWorkspace() {
  return (
    <RoleGuard allow={PORT_ACCESS}>
      <AppShell>
        <Outlet />
      </AppShell>
    </RoleGuard>
  );
}
