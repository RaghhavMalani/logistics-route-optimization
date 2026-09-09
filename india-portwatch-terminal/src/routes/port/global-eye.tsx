import { createFileRoute } from "@tanstack/react-router";

import { usePortContext } from "@/components/app/port-context";
import { GlobalEyeScreen } from "@/components/globaleye/GlobalEyeScreen";

export const Route = createFileRoute("/port/global-eye")({ component: PortGlobalEye });

function PortGlobalEye() {
  const { portCode } = usePortContext();
  return (
    <GlobalEyeScreen
      scope="port"
      title="Global Eye — Exposure here"
      portCode={portCode}
    />
  );
}
