import { createFileRoute } from "@tanstack/react-router";

import { GlobalEyeScreen } from "@/components/globaleye/GlobalEyeScreen";

export const Route = createFileRoute("/admin/global-eye")({ component: AdminGlobalEye });

function AdminGlobalEye() {
  return <GlobalEyeScreen scope="national" title="Global Eye" />;
}
