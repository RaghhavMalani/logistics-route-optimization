import type { PortTwinState, TwinSimulation } from "@/types/portwatch-os";

export interface TwinFrame {
  state: PortTwinState;
  hour: number;
  progress: number;
  next: PortTwinState;
  yardFill: ReadonlyArray<number>;
}

export function createTwinPlayback(run: TwinSimulation) {
  const frames = run.timeline ?? [];
  if (!frames.length) return null;
  const initial = frames[0];
  // The scheduling engine keeps stored inventory and gate demand fixed. This
  // separate display projection maps half of quay lifts into yard inflow and
  // half of gate capacity into outflow, spread over the schematic blocks.
  const fill = [initial.yardBlocks.map((block) => block.occupied_teu)];
  for (let i = 1; i < frames.length; i++) {
    const previous = frames[i - 1];
    const current = frames[i];
    const dt = current.hour - previous.hour;
    const lifted = current.cranes.reduce(
      (sum, crane, index) =>
        sum +
        Math.max(
          0,
          crane.working_hours - (previous.cranes[index]?.working_hours ?? 0),
        ) *
          crane.moves_per_hour,
      0,
    );
    const gateMoves = current.gates.reduce(
      (sum, gate) => sum + gate.trucks_per_hour * dt,
      0,
    );
    const delta =
      ((lifted - gateMoves) * 0.5) / Math.max(1, current.yardBlocks.length);
    fill.push(
      current.yardBlocks.map((block, index) =>
        Math.max(0, Math.min(block.capacityTeu, fill[i - 1][index] + delta)),
      ),
    );
  }
  const yardFill = new Array<number>(initial.yardBlocks.length);
  let index = 0;
  return {
    duration: run.horizonHours,
    sample(hour: number): TwinFrame {
      while (index > 0 && frames[index].hour > hour) index--;
      while (index + 1 < frames.length && frames[index + 1].hour <= hour)
        index++;
      const state = frames[index];
      const next = frames[index + 1] ?? state;
      const progress =
        next === state ? 0 : (hour - state.hour) / (next.hour - state.hour);
      for (let block = 0; block < yardFill.length; block++) {
        const capacity = state.yardBlocks[block].capacityTeu;
        yardFill[block] = capacity
          ? (fill[index][block] +
              ((fill[index + 1]?.[block] ?? fill[index][block]) -
                fill[index][block]) *
                progress) /
            capacity
          : 0;
      }
      return { state, next, hour, progress, yardFill };
    },
  };
}

export type TwinPlayback = NonNullable<ReturnType<typeof createTwinPlayback>>;
