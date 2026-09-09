import { Outlet, createFileRoute } from "@tanstack/react-router";

import { VESSEL_ACCESS, RoleGuard } from "@/auth/guards";
import { AppShell } from "@/components/app/AppShell";
import { WorkspaceNotFound } from "@/components/app/WorkspaceNotFound";

export const Route = createFileRoute("/vessel")({
  component: VesselWorkspace,
  // Rendered into this layout's Outlet, so the guard and the shell are already
  // around it: an unknown child address keeps the rail rather than going blank.
  notFoundComponent: WorkspaceNotFound,
});

function VesselWorkspace() {
  return (
    <RoleGuard allow={VESSEL_ACCESS}>
      <AppShell>
        <Outlet />
      </AppShell>
    </RoleGuard>
  );
}
