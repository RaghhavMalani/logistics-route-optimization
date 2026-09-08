import { Outlet, createFileRoute } from "@tanstack/react-router";

import { PORT_ACCESS, RoleGuard } from "@/auth/guards";
import { AppShell } from "@/components/app/AppShell";

export const Route = createFileRoute("/port")({ component: PortWorkspace });

function PortWorkspace() {
  return (
    <RoleGuard allow={PORT_ACCESS}>
      <AppShell>
        <Outlet />
      </AppShell>
    </RoleGuard>
  );
}
