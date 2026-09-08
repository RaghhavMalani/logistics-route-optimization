import { Outlet, createFileRoute } from "@tanstack/react-router";

import { RoleGuard, VESSEL_ACCESS } from "@/auth/guards";
import { AppShell } from "@/components/app/AppShell";

export const Route = createFileRoute("/vessel")({ component: VesselWorkspace });

function VesselWorkspace() {
  return (
    <RoleGuard allow={VESSEL_ACCESS}>
      <AppShell>
        <Outlet />
      </AppShell>
    </RoleGuard>
  );
}
