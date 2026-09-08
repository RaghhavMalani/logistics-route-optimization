import { Outlet, createFileRoute } from "@tanstack/react-router";

import { ADMIN_ACCESS, RoleGuard } from "@/auth/guards";
import { AppShell } from "@/components/app/AppShell";

export const Route = createFileRoute("/admin")({ component: AdminWorkspace });

function AdminWorkspace() {
  return (
    <RoleGuard allow={ADMIN_ACCESS}>
      <AppShell>
        <Outlet />
      </AppShell>
    </RoleGuard>
  );
}
