import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { CargoScreen } from "@/components/cargo/CargoScreen";
import { SelectControl } from "@/components/kit/layout";
import { usePorts } from "@/services/hooks";

export const Route = createFileRoute("/company/cargo")({ component: CompanyCargo });

/**
 * Transshipment opportunities for this fleet.
 *
 * A carrier evaluates connections rather than committing a plan, so the screen
 * opens on opportunities: capacity is not reserved on the operator's behalf by
 * looking at it.
 */
function CompanyCargo() {
  const ports = usePorts();
  const [portCode, setPortCode] = useState("INMAA");

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-[var(--line)] bg-[var(--panel)] px-4 py-1.5">
        <span className="eyebrow text-[9px]">Port</span>
        <SelectControl
          ariaLabel="Select the port to look for connections at"
          className="w-[220px]"
          value={portCode}
          onChange={setPortCode}
          options={(ports.data ?? []).map((port) => ({
            value: port.code,
            label: port.name,
          }))}
        />
      </div>
      <div className="min-h-0 flex-1">
        <CargoScreen portCode={portCode} title="Cargo connections" mode="opportunities" />
      </div>
    </div>
  );
}
