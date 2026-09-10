import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { SelectControl } from "@/components/kit/layout";
import { ScreenFallback } from "@/components/kit/states";
import { PortTwinScreen } from "@/components/twin/PortTwinScreen";
import { usePorts } from "@/services/hooks";

export const Route = createFileRoute("/admin/twins")({ component: AdminTwins });

/** National command reaching any port's twin, with a facility selector. */
function AdminTwins() {
  const ports = usePorts();
  const [portCode, setPortCode] = useState("INMAA");

  if (ports.isLoading || ports.isError) {
    return (
      <ScreenFallback
        title="Port Twins"
        context={<span>3D digital twins by facility</span>}
        isLoading={ports.isLoading}
        error={ports.error}
        retry={() => void ports.refetch()}
        label="Loading the port registry"
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-[var(--line)] bg-[var(--panel)] px-4 py-1.5">
        <span className="eyebrow text-[9px]">Facility</span>
        <SelectControl
          ariaLabel="Select the port to inspect"
          className="w-[240px]"
          value={portCode}
          onChange={setPortCode}
          options={(ports.data ?? []).map((port) => ({
            value: port.code,
            label: port.name,
          }))}
        />
      </div>
      <div className="min-h-0 flex-1">
        <PortTwinScreen key={portCode} portCode={portCode} />
      </div>
    </div>
  );
}
