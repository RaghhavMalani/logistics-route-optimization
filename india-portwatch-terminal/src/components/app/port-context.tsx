/**
 * Which port the port workspace is looking at.
 *
 * A port operator is scoped to one facility by their session and cannot switch;
 * an admin inspecting the same screens can. That distinction is enforced here
 * rather than in each of the seven port screens.
 */

import { useAuth, useWorkspace } from "@/auth/AuthProvider";
import { SelectControl } from "@/components/kit/layout";
import { usePorts } from "@/services/hooks";
import type { PortSnapshot } from "@/types/portwatch";

export function usePortContext() {
  const { portCode } = useWorkspace();
  const { session, setPortCode } = useAuth();
  const query = usePorts();
  const ports = query.data ?? [];
  const port: PortSnapshot | null =
    ports.find((entry) => entry.code === portCode) ?? ports[0] ?? null;

  return {
    query,
    ports,
    port,
    portCode: port?.code ?? portCode,
    locked: session?.user.role === "PORT_OPERATOR",
    setPortCode,
  };
}

export function PortSwitcher({ className }: { className?: string }) {
  const { ports, portCode, locked, setPortCode } = usePortContext();

  if (locked) {
    return (
      <span className="text-[11px] text-[var(--text-3)]">
        Facility scope · <span className="num text-[var(--text-2)]">{portCode}</span>
      </span>
    );
  }

  return (
    <SelectControl
      ariaLabel="Select port"
      className={className ?? "w-[190px]"}
      value={portCode}
      onChange={setPortCode}
      options={ports.map((port) => ({ value: port.code, label: port.name }))}
    />
  );
}
