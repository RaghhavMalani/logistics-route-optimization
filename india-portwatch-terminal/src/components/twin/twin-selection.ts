import type { PortTwinState } from "@/types/portwatch-os";
import type { TwinSelection } from "./twin-presentation";

/** Resolve against the displayed simulation frame, including after a seek. */
export function twinSelection(
  state: PortTwinState,
  id: string,
): TwinSelection | null {
  const berth = state.berths.find((row) => row.berth_id === id);
  if (berth)
    return {
      kind: "berth",
      id: berth.berth_id,
      label: berth.name,
      fields: [
        ["Length", `${berth.length_m.toFixed(0)} m`],
        ["Depth", `${berth.depth_m.toFixed(1)} m`],
        ["Handles", berth.handles.join(", ")],
        ["Cranes able to serve", String(berth.crane_ids.length)],
        ["Occupied by", berth.occupied_by ?? "free"],
        [
          "Frees at",
          berth.free_at_hour == null
            ? "n/a"
            : `hour ${berth.free_at_hour.toFixed(1)}`,
        ],
        ["Occupied hours this run", berth.occupied_hours.toFixed(1)],
      ],
    };
  const crane = state.cranes.find((row) => row.crane_id === id);
  if (crane)
    return {
      kind: "crane",
      id: crane.crane_id,
      label: crane.name,
      fields: [
        ["Rate", `${crane.moves_per_hour.toFixed(1)} moves/h`],
        ["Reaches", crane.serves.join(", ")],
        ["Assigned to", crane.assigned_berth ?? "idle"],
        ["Working hours this run", crane.working_hours.toFixed(1)],
      ],
    };
  const block = state.yardBlocks.find((row) => row.block_id === id);
  if (block)
    return {
      kind: "yard",
      id: block.block_id,
      label: block.name,
      fields: [
        ["Ground slots", block.slots.toLocaleString()],
        ["Tiers", String(block.tiers)],
        ["Capacity", `${block.capacityTeu.toLocaleString()} TEU`],
        ["Occupied", `${block.occupied_teu.toFixed(0)} TEU`],
        ["Utilisation", `${(block.utilisation * 100).toFixed(0)}%`],
        ["Mean dwell", `${block.mean_dwell_hours.toFixed(1)} h`],
        ["Accepts", block.accepts.join(", ")],
        ["Reefer plugs", String(block.reefer_plugs)],
      ],
    };
  const shed = state.sheds.find((row) => row.shed_id === id);
  if (shed)
    return {
      kind: "shed",
      id: shed.shed_id,
      label: shed.name,
      fields: [
        ["Area", `${shed.area_m2.toLocaleString()} m²`],
        ["Stores", shed.stores.join(", ")],
        ["Utilisation", `${(shed.utilisation * 100).toFixed(0)}%`],
      ],
    };
  const gate = state.gates.find((row) => row.gate_id === id);
  if (gate)
    return {
      kind: "gate",
      id: gate.gate_id,
      label: gate.name,
      fields: [
        ["Lanes", String(gate.lanes)],
        ["Throughput", `${gate.trucks_per_hour.toFixed(0)} trucks/h`],
        ["Queue", `${gate.queue_trucks.toFixed(0)} trucks`],
      ],
    };
  const call = state.calls.find((row) => row.call_id === id);
  if (call)
    return {
      kind: "vessel",
      id: call.call_id,
      label: call.name,
      fields: [
        ["Class", call.vessel_class],
        ["LOA", `${call.loa_m.toFixed(0)} m`],
        ["Draught", `${call.draught_m.toFixed(1)} m`],
        ["Moves", call.moves.toLocaleString()],
        ["Waiting", `${call.wait_hours.toFixed(1)} h`],
        [
          "Latest departure",
          call.latest_departure_hour == null
            ? "no commitment"
            : `hour ${call.latest_departure_hour.toFixed(1)}`,
        ],
      ],
    };
  return null;
}
