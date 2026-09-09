import { createFileRoute } from "@tanstack/react-router";

import { usePortContext } from "@/components/app/port-context";
import { PortTwinScreen } from "@/components/twin/PortTwinScreen";
import { ScreenFallback } from "@/components/kit/states";

export const Route = createFileRoute("/port/twin")({ component: PortTwin });

function PortTwin() {
  const { portCode, query } = usePortContext();
  if (query.isLoading || query.isError) {
    return (
      <ScreenFallback
        title="Port Digital Twin"
        context={<span>Berths, yard, cranes and the queue in space</span>}
        isLoading={query.isLoading}
        error={query.error}
        retry={() => void query.refetch()}
        label="Resolving the facility"
      />
    );
  }
  return <PortTwinScreen portCode={portCode} />;
}
