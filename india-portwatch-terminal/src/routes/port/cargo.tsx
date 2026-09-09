import { createFileRoute } from "@tanstack/react-router";

import { usePortContext } from "@/components/app/port-context";
import { CargoScreen } from "@/components/cargo/CargoScreen";

export const Route = createFileRoute("/port/cargo")({ component: PortCargo });

/**
 * Transshipment assignment for this facility.
 *
 * A port authority commits a plan, so this opens on the assignment rather than
 * on the opportunity list a carrier reads.
 */
function PortCargo() {
  const { portCode } = usePortContext();
  return <CargoScreen portCode={portCode} title="Cargo assignment" mode="plan" />;
}
