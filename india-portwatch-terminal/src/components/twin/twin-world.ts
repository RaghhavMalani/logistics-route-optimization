import * as T from "three";
import { createMiniatureBuilders } from "@/components/miniature/builders";
import { createMiniatureLighting } from "@/components/miniature/lighting";
import { BOXCOLS, COLORS } from "@/components/miniature/palette";
import { seededRandom } from "@/components/miniature/rng";
import type { PortTwinState, TwinCall } from "@/types/portwatch-os";
import type { TwinFrame } from "./twin-playback";
import { twinCallPickId } from "./twin-selection";
import { TWIN_RAMP, type TwinOverlay } from "./twin-presentation";

type Part = { matrix: T.Matrix4; color: T.Color; material: T.Material };
type Tint = T.ColorRepresentation;

export function createTwinWorld(base: PortTwinState) {
  const scene = new T.Scene();
  scene.background = new T.Color(COLORS.modelSea);
  const templates = new T.Scene();
  const { unitBox, makeShip, makeQuayCrane, makeGantry, buildTracks, M } =
    createMiniatureBuilders(templates, seededRandom(1234));

  const instancedMaterial = new T.MeshStandardMaterial({
    color: 0xffffff,
    roughness: 0.92,
  });
  const transform = new T.Object3D();
  const matrix = new T.Matrix4();
  const color = new T.Color();
  const batches: T.InstancedMesh[] = [];
  const entities = new Map<T.InstancedMesh, string[]>();
  const templateResources = new Set<T.Material>();
  const templateInstances: T.InstancedMesh[] = [];

  function batch(name: string, capacity: number) {
    const mesh = new T.InstancedMesh(
      unitBox,
      instancedMaterial,
      Math.max(1, capacity),
    );
    mesh.name = name;
    mesh.count = 0;
    mesh.frustumCulled = false;
    mesh.instanceMatrix.setUsage(T.DynamicDrawUsage);
    const ids: string[] = [];
    entities.set(mesh, ids);
    batches.push(mesh);
    scene.add(mesh);
    return {
      reset() {
        mesh.count = 0;
      },
      push(at: T.Matrix4, tint: Tint, id = "") {
        const index = mesh.count++;
        mesh.setMatrixAt(index, at);
        mesh.setColorAt(index, color.set(tint));
        ids[index] = id;
      },
      commit() {
        mesh.boundingSphere = null;
        mesh.instanceMatrix.needsUpdate = true;
        if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      },
    };
  }

  function extract(root: T.Object3D) {
    root.updateMatrixWorld(true);
    const parts: Part[] = [];
    root.traverse((object) => {
      if (!(object instanceof T.Mesh)) return;
      const material = object.material as T.MeshStandardMaterial;
      templateResources.add(material);
      if (object instanceof T.InstancedMesh) {
        templateInstances.push(object);
        for (let index = 0; index < object.count; index++) {
          object.getMatrixAt(index, matrix);
          object.getColorAt(index, color);
          parts.push({
            matrix: object.matrixWorld.clone().multiply(matrix),
            color: color.clone(),
            material,
          });
        }
      } else {
        parts.push({
          matrix: object.matrixWorld.clone(),
          color: material.color.clone(),
          material,
        });
      }
    });
    return parts;
  }

  type Batch = ReturnType<typeof batch>;
  function pose(
    x: number,
    y: number,
    z: number,
    sx: number,
    sy: number,
    sz: number,
    heading = 0,
  ) {
    transform.position.set(x, y, z);
    transform.scale.set(sx, sy, sz);
    transform.rotation.y = heading;
    transform.updateMatrix();
    return transform.matrix;
  }
  function box(
    target: Batch,
    x: number,
    y: number,
    z: number,
    sx: number,
    sy: number,
    sz: number,
    tint: Tint,
    id = "",
  ) {
    target.push(pose(x, y, z, sx, sy, sz), tint, id);
  }
  function model(
    target: Batch,
    parts: Part[],
    at: T.Matrix4,
    id = "",
    hullTint?: Tint,
  ) {
    for (const part of parts) {
      matrix.multiplyMatrices(at, part.matrix);
      target.push(
        matrix,
        hullTint && part.material === M.signal ? hullTint : part.color,
        id,
      );
    }
  }

  const quayStart = Math.min(
    0,
    ...base.berths.map((b) => b.x - b.length_m * 0.6),
  );
  const quayEnd = Math.max(
    quayStart + 600,
    ...base.berths.map((b) => b.x + b.length_m * 0.65),
    ...base.yardBlocks.map((b) => b.x + b.width_m * 0.65),
    ...base.sheds.map((s) => s.x + s.width_m * 0.6),
    ...base.gates.map((g) => g.x + 100),
  );
  const span = quayEnd - quayStart;
  const inland = Math.max(760, ...base.gates.map((gate) => gate.y + 125));
  const mid = (quayStart + quayEnd) / 2;
  const lighting = createMiniatureLighting(scene, true);
  lighting.sun.castShadow = false;
  lighting.sun.intensity = 2.6;
  lighting.follow(new T.Vector3(mid, 0, inland / 3), span);

  const ground = batch("Quay and landside", 20 + base.berths.length * 4);
  box(
    ground,
    mid,
    -9,
    inland / 2,
    span,
    18,
    inland,
    COLORS.land,
    "facility-quay",
  );
  box(ground, mid, 1, 76, span, 4, 152, COLORS.pave, "facility-quay");
  box(ground, mid, 0, -4, span, 13, 10, COLORS.modelInk);
  box(ground, mid, 8, 9, span, 3, 5, COLORS.modelWhite);
  box(ground, mid, 1, 178, span - 20, 3, 26, COLORS.road);
  box(ground, mid, 1, inland - 92, span - 24, 3, 32, COLORS.road);
  for (const berth of base.berths) {
    box(
      ground,
      berth.x,
      4,
      67,
      berth.length_m,
      2,
      2,
      COLORS.controlLine,
      berth.berth_id,
    );
    box(
      ground,
      berth.x - berth.length_m / 2,
      6,
      18,
      8,
      7,
      8,
      COLORS.modelInk,
      berth.berth_id,
    );
    box(
      ground,
      berth.x + berth.length_m / 2,
      6,
      18,
      8,
      7,
      8,
      COLORS.modelInk,
      berth.berth_id,
    );
  }
  ground.commit();

  const ship = makeShip(36, 8, 0.56);
  ship.position.set(0, 0, 0);
  const hullParts = extract(ship);
  const crane = makeQuayCrane(0);
  const craneFixed = extract(crane.g).slice(0, crane.g.children.length - 1);
  const craneMotion = extract(crane.trolley);
  const gantry = makeGantry(16, 9, 2.8);
  const rtgParts = extract(gantry.g);
  templates.clear();
  buildTracks();
  const tracks = batch("Rail", 20);
  model(
    tracks,
    extract(templates),
    pose(mid - span / 2, 1, inland - 32, span / 550, 3, 1.2),
    "facility-rail",
  );
  tracks.commit();

  const pad = batch(
    "Facility pads",
    base.berths.length +
      base.yardBlocks.length +
      base.sheds.length +
      base.cranes.length +
      base.gates.length,
  );
  const cranes = batch(
    "Quay cranes",
    base.cranes.length * (craneFixed.length + craneMotion.length),
  );
  const gantries = batch("Yard RTGs", base.yardBlocks.length * rtgParts.length);
  const containers = batch("Yard containers", base.yardBlocks.length * 60);
  const hulls = batch(
    "Hull models",
    (base.calls.length + base.berths.length) * hullParts.length,
  );
  const buildings = batch(
    "Sheds and gate",
    base.sheds.length * 3 + base.gates.length * 6,
  );
  const trucks = batch(
    "Road vehicles",
    (base.vehicles.length + base.gates.length * 8) * 3,
  );

  const ramp = TWIN_RAMP.map((hex) => new T.Color(hex));
  const fillColor = new T.Color();
  function pressure(value: number | null) {
    if (value === null) return COLORS.pave;
    const fraction = T.MathUtils.clamp(value, 0, 1);
    return fraction < 0.5
      ? fillColor.lerpColors(ramp[0], ramp[1], fraction * 2)
      : fillColor.lerpColors(ramp[1], ramp[2], fraction * 2 - 1);
  }
  function truck(x: number, z: number, id: string) {
    box(trucks, x, 8, z, 21, 4, 9, COLORS.modelInk, id);
    box(trucks, x + 8, 13, z, 8, 9, 9, COLORS.signal, id);
    box(trucks, x - 4, 14, z, 13, 10, 8, COLORS.modelWhite, id);
  }

  const queuePads = batch("Anchorage pads", base.calls.length);
  const outline = batch("Selection outline", 16);
  const active = [
    pad,
    queuePads,
    cranes,
    gantries,
    containers,
    hulls,
    buildings,
    trucks,
    outline,
  ];
  function drawOutline(
    x: number,
    y: number,
    z: number,
    w: number,
    d: number,
    heading = 0,
  ) {
    const cos = Math.cos(heading);
    const sin = Math.sin(heading);
    for (const side of [-1, 1]) {
      const short = (side * d) / 2;
      const long = (side * w) / 2;
      outline.push(
        pose(x + short * sin, y, z + short * cos, w, 3, 6, heading),
        COLORS.signal,
      );
      outline.push(
        pose(x + long * cos, y, z - long * sin, 6, 3, d, heading),
        COLORS.signal,
      );
    }
  }
  const anchorOrder = new Map(
    base.calls
      .map((call, row) => ({ eta: call.effectiveEta, row }))
      .sort((a, b) => a.eta - b.eta)
      .map(({ row }, rank) => [row, rank]),
  );
  const craneSwing = new T.Matrix4();
  const movingCrane = new T.Matrix4();
  const smooth = (value: number) => {
    const t = T.MathUtils.clamp(value, 0, 1);
    return t * t * (3 - 2 * t);
  };
  function shipAt(
    call: TwinCall,
    row: number,
    x: number,
    z: number,
    heading: number,
    selected: string | null,
  ) {
    const id = twinCallPickId(call, row);
    model(
      hulls,
      hullParts,
      pose(
        x,
        -1,
        z,
        call.loa_m / 38,
        call.loa_m / 46,
        call.loa_m / 46,
        heading,
      ),
      id,
      COLORS.shipContainer,
    );
    if (id === selected || call.call_id === selected)
      drawOutline(x, 1, z, call.loa_m + 20, call.loa_m * 0.25 + 18, heading);
  }
  function draw(
    state: PortTwinState,
    overlay: TwinOverlay,
    selectedId: string | null,
    frame?: TwinFrame,
    view?: { unitsPerPixel: number; x: number; z: number },
  ) {
    for (const item of active) item.reset();
    const calls = new Map<string, number>();
    // The engine resolves duplicate demo IDs to the first record.
    for (const [row, call] of state.calls.entries()) {
      if (!calls.has(call.call_id)) calls.set(call.call_id, row);
    }
    let lowDetailBlocks = 0;
    const craneHours = Math.max(1, ...state.cranes.map((c) => c.working_hours));
    const dwellHours = Math.max(
      1,
      ...state.yardBlocks.map((b) => b.mean_dwell_hours),
    );
    for (const berth of state.berths) {
      const tint = pressure(
        overlay === "utilisation" ? (berth.occupied_by ? 0.85 : 0.15) : null,
      );
      if (berth.berth_id === selectedId)
        drawOutline(berth.x, 7, 29, berth.length_m * 0.94, 41);
      box(
        pad,
        berth.x,
        4,
        29,
        berth.length_m * 0.92,
        3,
        37,
        tint,
        berth.berth_id,
      );
      if (!berth.occupied_by) continue;
      const row = calls.get(berth.occupied_by);
      const call = row === undefined ? undefined : state.calls[row];
      if (frame && call) continue;
      const length = call?.loa_m ?? berth.length_m * 0.8;
      if (call) {
        shipAt(call, row!, berth.x, -37, 0, selectedId);
        continue;
      }
      model(
        hulls,
        hullParts,
        pose(berth.x, -1, -37, length / 38, length / 46, length / 46),
        berth.berth_id,
        COLORS.shipContainer,
      );
    }
    let waiting = 0;
    const longestWait = Math.max(
      1,
      ...state.calls
        .filter((call) => call.state === "waiting")
        .map((call) => call.wait_hours),
    );
    const berths = new Map(
      state.berths.map((berth) => [berth.berth_id, berth]),
    );
    for (const [row, call] of state.calls.entries()) {
      if (!frame && call.state !== "waiting") continue;
      const index = frame ? (anchorOrder.get(row) ?? 0) % 15 : waiting++;
      const x = quayStart + span * (0.16 + (index % 5) * 0.17);
      const z = -250 - Math.floor(index / 5) * 135;
      if (!frame || call.state === "waiting") {
        if (overlay === "queue")
          box(
            queuePads,
            x,
            -11,
            z,
            call.loa_m + 26,
            2,
            call.loa_m * 0.28 + 22,
            pressure(call.wait_hours / longestWait),
            twinCallPickId(call, row),
          );
        shipAt(call, row, x, z, 0.12, selectedId);
      } else if (
        call.state === "approaching" &&
        call.effectiveEta - frame.hour <= 2
      ) {
        const approach = smooth((frame.hour - call.effectiveEta + 2) / 2);
        shipAt(
          call,
          row,
          x - (1 - approach) * 220,
          z - (1 - approach) * 420,
          -0.72,
          selectedId,
        );
      } else {
        const berth = call.berth_id ? berths.get(call.berth_id) : undefined;
        if (!berth) continue;
        if (call.state === "alongside" && call.berthed_hour !== null) {
          const docking = smooth((frame.hour - call.berthed_hour) / 0.75);
          shipAt(
            call,
            row,
            T.MathUtils.lerp(x, berth.x, docking),
            T.MathUtils.lerp(z, -37, docking),
            (1 - docking) * -0.55,
            selectedId,
          );
        } else if (
          call.state === "departed" &&
          call.departed_hour !== null &&
          frame.hour - call.departed_hour < 1.6
        ) {
          const leaving = smooth((frame.hour - call.departed_hour) / 1.6);
          shipAt(
            call,
            row,
            berth.x + 320 * leaving,
            -37 - 740 * leaving,
            leaving * 0.93,
            selectedId,
          );
        }
      }
    }
    for (const [index, item] of state.cranes.entries()) {
      box(
        pad,
        item.x,
        4,
        98,
        38,
        2,
        37,
        pressure(
          overlay === "workload" ? item.working_hours / craneHours : null,
        ),
        item.crane_id,
      );
      const berth = item.assigned_berth
        ? berths.get(item.assigned_berth)
        : undefined;
      const x = berth ? berth.x + (index % 2 === 0 ? -39 : 39) : item.x;
      if (item.crane_id === selectedId) drawOutline(x, 5, 43, 56, 65);
      const at = pose(x, 3, 6, 4, 4, 4, -Math.PI / 2);
      model(cranes, craneFixed, at, item.crane_id);
      const working = T.MathUtils.lerp(
        item.working_hours,
        frame?.next.cranes[index]?.working_hours ?? item.working_hours,
        frame?.progress ?? 0,
      );
      const swing = berth ? Math.sin(working * Math.PI * 3) : 0;
      craneSwing.makeTranslation(-8 + swing * 12, -Math.abs(swing) * 4, 0);
      model(
        cranes,
        craneMotion,
        movingCrane.multiplyMatrices(at, craneSwing),
        item.crane_id,
      );
    }
    for (const [index, block] of state.yardBlocks.entries()) {
      const value =
        overlay === "dwell"
          ? block.mean_dwell_hours / dwellHours
          : overlay === "storage"
            ? Math.min(1, block.utilisation / 0.95)
            : overlay === "utilisation"
              ? block.utilisation
              : null;
      box(
        pad,
        block.x,
        2,
        block.y,
        block.width_m,
        3,
        block.depth_m,
        pressure(value),
        block.block_id,
      );
      if (block.block_id === selectedId)
        drawOutline(
          block.x,
          5,
          block.y,
          block.width_m + 10,
          block.depth_m + 10,
        );
      const near =
        !view ||
        (block.width_m / view.unitsPerPixel >= 30 &&
          Math.hypot(block.x - view.x, block.y - view.z) <
            Math.hypot(mid - view.x, inland * 0.31 - view.z) + span * 0.24);
      if (!near) lowDetailBlocks++;
      const columns = near ? 5 : 3;
      const rows = near ? 4 : 2;
      const slots = columns * rows;
      const capacity = slots * 3;
      const count = Math.min(
        capacity,
        Math.round(capacity * (frame?.yardFill[index] ?? block.utilisation)),
      );
      for (let stack = 0; stack < count; stack++) {
        const slot = stack % slots;
        const tier = Math.floor(stack / slots);
        box(
          containers,
          block.x +
            (((slot % columns) - (columns - 1) / 2) * block.width_m) /
              (columns + 0.7),
          10 + tier * 12,
          block.y +
            ((Math.floor(slot / columns) - (rows - 1) / 2) * block.depth_m) /
              (rows + 0.7),
          block.width_m / (columns + 1.6),
          11,
          block.depth_m / (rows + 2.4),
          BOXCOLS[(index * 3 + slot + tier) % BOXCOLS.length],
          block.block_id,
        );
      }
      model(
        gantries,
        rtgParts,
        pose(
          block.x - block.width_m * 0.23,
          3,
          block.y,
          4,
          4,
          block.depth_m / 17,
        ),
        block.block_id,
      );
    }
    for (const shed of state.sheds) {
      if (shed.shed_id === selectedId)
        drawOutline(shed.x, 5, shed.y, shed.width_m + 25, shed.depth_m + 22);
      box(
        pad,
        shed.x,
        3,
        shed.y,
        shed.width_m + 24,
        3,
        shed.depth_m + 22,
        pressure(overlay === "storage" ? shed.utilisation : null),
        shed.shed_id,
      );
      box(
        buildings,
        shed.x,
        19,
        shed.y,
        shed.width_m,
        30,
        shed.depth_m,
        COLORS.modelWhite,
        shed.shed_id,
      );
      box(
        buildings,
        shed.x,
        37,
        shed.y,
        shed.width_m + 12,
        9,
        shed.depth_m + 10,
        COLORS.glass,
        shed.shed_id,
      );
      box(
        buildings,
        shed.x,
        9,
        shed.y - shed.depth_m / 2,
        shed.width_m * 0.56,
        11,
        5,
        COLORS.rail,
        shed.shed_id,
      );
    }
    for (const gate of state.gates) {
      const width = gate.lanes * 16;
      if (gate.gate_id === selectedId)
        drawOutline(gate.x, 5, gate.y, width + 25, 65);
      box(pad, gate.x, 2, gate.y, width + 24, 3, 60, COLORS.road, gate.gate_id);
      box(
        buildings,
        gate.x,
        28,
        gate.y,
        width,
        8,
        28,
        COLORS.modelInk,
        gate.gate_id,
      );
      for (const side of [-1, 1])
        box(
          buildings,
          gate.x + side * width * 0.45,
          13,
          gate.y,
          11,
          24,
          21,
          COLORS.modelWhite,
          gate.gate_id,
        );
    }
    for (const vehicle of state.vehicles) {
      if (vehicle.vehicle_id === selectedId)
        drawOutline(vehicle.x, 4, vehicle.y, 35, 22);
      truck(vehicle.x, vehicle.y, vehicle.vehicle_id);
    }
    if (selectedId === "facility-quay") drawOutline(mid, 6, 76, span, 152);
    if (selectedId === "facility-rail")
      drawOutline(mid, 5, inland - 197, span * 0.95, 48);
    if (frame) {
      for (const gate of state.gates) {
        for (let i = 0; i < 8; i++) {
          const phase = ((frame.hour * gate.trucks_per_hour) / 70 + i / 8) % 1;
          const x = gate.x + Math.sin(phase * Math.PI * 2) * span * 0.2;
          const z = 160 + (gate.y - 160) * (1 - Math.abs(2 * phase - 1));
          truck(x, z, gate.gate_id);
        }
      }
    }
    for (const item of active) item.commit();
    return lowDetailBlocks;
  }

  const pick = (raycaster: T.Raycaster) => {
    for (const hit of raycaster.intersectObjects(batches, false)) {
      const id =
        hit.instanceId === undefined
          ? undefined
          : entities.get(hit.object as T.InstancedMesh)?.[hit.instanceId];
      if (id) return id;
    }
    return null;
  };
  return {
    scene,
    draw,
    pick,
    mid,
    span,
    inland,
    dispose() {
      for (const mesh of [...batches, ...templateInstances]) mesh.dispose();
      for (const material of new Set([
        ...Object.values(M),
        ...templateResources,
        instancedMaterial,
      ]))
        material.dispose();
      lighting.dispose();
      unitBox.dispose();
      scene.clear();
    },
  };
}
