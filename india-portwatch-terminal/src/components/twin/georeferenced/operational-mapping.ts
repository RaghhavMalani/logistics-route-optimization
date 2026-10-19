import type { PortTwinState } from "@/types/portwatch-os";
import type { TwinOverlay } from "../PortTwinScene";
import type { Catalogue, GeographicFeature } from "./catalogue";

export function operationalView(
  feature: GeographicFeature,
  catalogue: Catalogue,
  state: PortTwinState | undefined,
  overlay: TwinOverlay,
) {
  const mapping = catalogue.operationalMappings.find(
    (m) => m.featureId === feature.id,
  );
  if (
    !mapping?.operationalAssetId ||
    mapping.status !== "reviewed" ||
    !mapping.reviewedBy ||
    !mapping.reviewedAt ||
    !state ||
    ![catalogue.portCode, "JNPT"].includes(state.portCode)
  )
    return null;
  const id = mapping.operationalAssetId;
  const berth = state.berths.find((b) => b.berth_id === id);
  if (feature.properties.kind === "berth" && berth)
    return {
      pressure: berth.occupied_by ? 0.8 : 0.12,
      fields: [
        ["State kind", "Simulated operational state"],
        ["Simulation horizon", `Simulation hour ${state.hour}`],
        ["Operational ID", id],
        ["Occupied by", berth.occupied_by ?? "Free in simulation"],
        ["Occupied hours", berth.occupied_hours.toFixed(1)],
      ] as Array<[string, string]>,
    };
  const yard = state.yardBlocks.find((b) => b.block_id === id);
  if (feature.properties.kind === "yard" && yard)
    return {
      pressure:
        overlay === "dwell"
          ? yard.mean_dwell_hours /
            Math.max(1, ...state.yardBlocks.map((b) => b.mean_dwell_hours))
          : overlay === "storage"
            ? Math.min(1, yard.utilisation / 0.95)
            : yard.utilisation,
      fields: [
        ["State kind", "Simulated operational state"],
        ["Simulation horizon", `Simulation hour ${state.hour}`],
        ["Operational ID", id],
        ["Utilisation", `${(yard.utilisation * 100).toFixed(0)}%`],
        ["Mean dwell", `${yard.mean_dwell_hours.toFixed(1)} h`],
      ] as Array<[string, string]>,
    };
  const shed = state.sheds.find((b) => b.shed_id === id);
  if (feature.properties.kind === "building" && shed)
    return {
      pressure: shed.utilisation,
      fields: [
        ["State kind", "Simulated operational state"],
        ["Simulation horizon", `Simulation hour ${state.hour}`],
        ["Operational ID", id],
        ["Utilisation", `${(shed.utilisation * 100).toFixed(0)}%`],
      ] as Array<[string, string]>,
    };
  return null;
}
