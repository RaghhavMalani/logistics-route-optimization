/**
 * The 3D port digital twin.
 *
 * **This geometry is schematic.** Berth, yard, shed and crane positions are
 * generated from published berth counts and the port's coastline orientation,
 * not from a surveyed plan. Nothing here is dimensionally authoritative, and the
 * banner saying so is not dismissible. What *is* real is what the scene is
 * coloured by: berth occupancy, yard utilisation, crane workload and queue
 * pressure all come from the same `PortState` the simulator and the RL
 * environment run on.
 *
 * That shared state is the whole reason this is worth building. A 3D port that
 * rendered its own idea of the terminal would be an illustration; one that
 * projects the object a policy is evaluated against is an inspector.
 *
 * Three.js directly rather than react-three-fiber: the scene is a few hundred
 * boxes that change colour, the interaction is one raycast on click, and a
 * reconciler between React and the scene graph would cost more than it saved.
 * The module is lazy-loaded so the 1.1 MB of Three stays out of the entry
 * bundle for the eleven screens that do not use it.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import type { PortTwinState, TwinMetrics } from "@/types/portwatch-os";

/** What the operator is colouring the scene by. */
export type TwinOverlay =
  | "utilisation"
  | "dwell"
  | "workload"
  | "queue"
  | "storage";

export const OVERLAYS: Array<{ key: TwinOverlay; label: string; hint: string }> = [
  { key: "utilisation", label: "Utilisation", hint: "Berth occupancy and yard fill" },
  { key: "dwell", label: "Dwell", hint: "How long cargo has been sitting in each block" },
  { key: "workload", label: "Crane workload", hint: "Working hours accrued per crane" },
  { key: "queue", label: "Queue", hint: "Vessels waiting, and how long" },
  { key: "storage", label: "Storage pressure", hint: "Yard and shed capacity headroom" },
];

export interface TwinSelection {
  kind: "berth" | "yard" | "shed" | "crane" | "vessel" | "gate";
  id: string;
  label: string;
  fields: Array<[string, string]>;
}

/* ------------------------------------------------------------------ ramp -- */

/** Green through amber to red. The same status vocabulary as the rest of the UI. */
function pressureColour(value: number): THREE.Color {
  const v = Math.max(0, Math.min(1, value));
  if (v < 0.5) {
    return new THREE.Color().lerpColors(
      new THREE.Color("#3f8f6b"),
      new THREE.Color("#c9a13a"),
      v / 0.5,
    );
  }
  return new THREE.Color().lerpColors(
    new THREE.Color("#c9a13a"),
    new THREE.Color("#c2564a"),
    (v - 0.5) / 0.5,
  );
}

const WATER = new THREE.Color("#0a2733");
const QUAY = new THREE.Color("#3d4750");
const IDLE = new THREE.Color("#2f3d47");

/* ---------------------------------------------------------------- scene --- */

interface Pickable {
  mesh: THREE.Object3D;
  selection: TwinSelection;
}

export function PortTwinScene({
  state,
  overlay,
  metrics,
  onSelect,
  selectedId,
  className,
}: {
  state: PortTwinState;
  overlay: TwinOverlay;
  /** Metrics at the chosen horizon, where they differ from the state's own. */
  metrics?: TwinMetrics | null;
  onSelect?: (selection: TwinSelection | null) => void;
  selectedId?: string | null;
  className?: string;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    pickables: Pickable[];
    dispose: () => void;
  } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const handlers = useRef({ onSelect });
  handlers.current = { onSelect };

  // The scene is rebuilt when the *shape* of the port changes -- a different
  // port, or a different berth count -- and only recoloured when the numbers
  // change. Rebuilding on every overlay switch would drop a frame for nothing.
  const shapeKey = useMemo(
    () =>
      [
        state.portCode,
        state.berths.length,
        state.yardBlocks.length,
        state.sheds.length,
        state.cranes.length,
      ].join("|"),
    [state],
  );

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return undefined;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch (error) {
      setFailed(
        error instanceof Error ? error.message : "WebGL is unavailable in this browser",
      );
      return undefined;
    }

    const width = mount.clientWidth || 800;
    const height = mount.clientHeight || 500;
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.setSize(width, height);
    renderer.setClearColor(new THREE.Color("#061420"));
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x061420, 2200, 5200);

    const [extentX, extentY] = state.extentM;
    const camera = new THREE.PerspectiveCamera(42, width / height, 10, 12000);
    // Looking down the quay from seaward and above: the angle a controller
    // recognises from a terminal plan, not a video-game chase camera.
    camera.position.set(extentX * 0.62, extentY * 1.35, -extentY * 1.15);
    camera.lookAt(extentX * 0.45, 0, extentY * 0.4);

    scene.add(new THREE.AmbientLight(0xb8d4e4, 0.62));
    const sun = new THREE.DirectionalLight(0xffffff, 0.85);
    sun.position.set(extentX * 0.4, 1600, -900);
    scene.add(sun);
    const fill = new THREE.DirectionalLight(0x6fa8c4, 0.35);
    fill.position.set(-extentX * 0.3, 700, extentY);
    scene.add(fill);

    const pickables: Pickable[] = [];
    const disposables: Array<THREE.BufferGeometry | THREE.Material> = [];

    const track = <T extends THREE.BufferGeometry | THREE.Material>(item: T): T => {
      disposables.push(item);
      return item;
    };

    /* -- water and quay ------------------------------------------------- */
    const water = new THREE.Mesh(
      track(new THREE.PlaneGeometry(extentX * 2.4, extentY * 2.4)),
      track(new THREE.MeshStandardMaterial({ color: WATER, roughness: 0.35, metalness: 0.1 })),
    );
    water.rotation.x = -Math.PI / 2;
    water.position.set(extentX * 0.4, -1.5, extentY * 0.2);
    scene.add(water);

    const apron = new THREE.Mesh(
      track(new THREE.BoxGeometry(extentX, 6, extentY * 0.95)),
      track(new THREE.MeshStandardMaterial({ color: QUAY, roughness: 0.9 })),
    );
    apron.position.set(extentX / 2 - 100, 3, extentY * 0.45);
    scene.add(apron);

    /* -- berths --------------------------------------------------------- */
    for (const berth of state.berths) {
      const mesh = new THREE.Mesh(
        track(new THREE.BoxGeometry(berth.length_m * 0.86, 10, 46)),
        track(new THREE.MeshStandardMaterial({ color: IDLE, roughness: 0.8 })),
      );
      mesh.position.set(berth.x, 9, 24);
      mesh.userData.kind = "berth";
      mesh.userData.id = berth.berth_id;
      scene.add(mesh);
      pickables.push({
        mesh,
        selection: {
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
              berth.free_at_hour == null ? "n/a" : `hour ${berth.free_at_hour.toFixed(1)}`,
            ],
            ["Occupied hours this run", berth.occupied_hours.toFixed(1)],
          ],
        },
      });

      // A hull alongside, so an occupied berth reads as occupied at a glance.
      if (berth.occupied_by) {
        const hull = new THREE.Mesh(
          track(new THREE.BoxGeometry(berth.length_m * 0.8, 34, 44)),
          track(new THREE.MeshStandardMaterial({ color: 0x4a6a80, roughness: 0.7 })),
        );
        hull.position.set(berth.x, 18, -32);
        scene.add(hull);
        const house = new THREE.Mesh(
          track(new THREE.BoxGeometry(38, 26, 34)),
          track(new THREE.MeshStandardMaterial({ color: 0x93aec0, roughness: 0.6 })),
        );
        house.position.set(berth.x + berth.length_m * 0.28, 46, -32);
        scene.add(house);
      }
    }

    /* -- cranes --------------------------------------------------------- */
    for (const crane of state.cranes) {
      const group = new THREE.Group();
      const legMaterial = track(
        new THREE.MeshStandardMaterial({ color: 0x8d9aa6, roughness: 0.6 }),
      );
      for (const dx of [-16, 16]) {
        for (const dz of [-14, 14]) {
          const leg = new THREE.Mesh(track(new THREE.BoxGeometry(5, 78, 5)), legMaterial);
          leg.position.set(dx, 39, dz);
          group.add(leg);
        }
      }
      const boom = new THREE.Mesh(
        track(new THREE.BoxGeometry(9, 5, 132)),
        legMaterial,
      );
      boom.position.set(0, 80, -34);
      group.add(boom);
      const gantry = new THREE.Mesh(
        track(new THREE.BoxGeometry(40, 9, 34)),
        track(new THREE.MeshStandardMaterial({ color: 0x6f7c88, roughness: 0.7 })),
      );
      gantry.position.set(0, 84, 0);
      group.add(gantry);

      group.position.set(crane.x, 6, 8);
      group.userData.kind = "crane";
      group.userData.id = crane.crane_id;
      scene.add(group);
      pickables.push({
        mesh: group,
        selection: {
          kind: "crane",
          id: crane.crane_id,
          label: crane.name,
          fields: [
            ["Rate", `${crane.moves_per_hour.toFixed(1)} moves/h`],
            ["Reaches", crane.serves.join(", ")],
            ["Assigned to", crane.assigned_berth ?? "idle"],
            ["Working hours this run", crane.working_hours.toFixed(1)],
          ],
        },
      });
    }

    /* -- yard blocks ---------------------------------------------------- */
    for (const block of state.yardBlocks) {
      const height = 8 + block.utilisation * 34;
      const mesh = new THREE.Mesh(
        track(new THREE.BoxGeometry(block.width_m, height, block.depth_m)),
        track(new THREE.MeshStandardMaterial({ color: IDLE, roughness: 0.85 })),
      );
      mesh.position.set(block.x, 6 + height / 2, block.y);
      mesh.userData.kind = "yard";
      mesh.userData.id = block.block_id;
      scene.add(mesh);
      pickables.push({
        mesh,
        selection: {
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
        },
      });
    }

    /* -- sheds ---------------------------------------------------------- */
    for (const shed of state.sheds) {
      const mesh = new THREE.Mesh(
        track(new THREE.BoxGeometry(shed.width_m, 46, shed.depth_m)),
        track(new THREE.MeshStandardMaterial({ color: 0x4c5b66, roughness: 0.9 })),
      );
      mesh.position.set(shed.x, 29, shed.y);
      mesh.userData.kind = "shed";
      mesh.userData.id = shed.shed_id;
      scene.add(mesh);

      const roof = new THREE.Mesh(
        track(new THREE.ConeGeometry(shed.width_m * 0.62, 22, 4)),
        track(new THREE.MeshStandardMaterial({ color: 0x5d6d79, roughness: 0.85 })),
      );
      roof.rotation.y = Math.PI / 4;
      roof.position.set(shed.x, 63, shed.y);
      scene.add(roof);

      pickables.push({
        mesh,
        selection: {
          kind: "shed",
          id: shed.shed_id,
          label: shed.name,
          fields: [
            ["Area", `${shed.area_m2.toLocaleString()} m²`],
            ["Stores", shed.stores.join(", ")],
            ["Utilisation", `${(shed.utilisation * 100).toFixed(0)}%`],
          ],
        },
      });
    }

    /* -- gates and internal vehicles ------------------------------------ */
    for (const gate of state.gates) {
      const mesh = new THREE.Mesh(
        track(new THREE.BoxGeometry(gate.lanes * 16, 22, 40)),
        track(new THREE.MeshStandardMaterial({ color: 0x55636e, roughness: 0.9 })),
      );
      mesh.position.set(gate.x, 17, gate.y);
      scene.add(mesh);
      pickables.push({
        mesh,
        selection: {
          kind: "gate",
          id: gate.gate_id,
          label: gate.name,
          fields: [
            ["Lanes", String(gate.lanes)],
            ["Throughput", `${gate.trucks_per_hour.toFixed(0)} trucks/h`],
            ["Queue", `${gate.queue_trucks.toFixed(0)} trucks`],
          ],
        },
      });
    }

    const vehicleMaterial = track(
      new THREE.MeshStandardMaterial({ color: 0xd0a55c, roughness: 0.7 }),
    );
    const vehicleGeometry = track(new THREE.BoxGeometry(18, 9, 9));
    for (const vehicle of state.vehicles) {
      const mesh = new THREE.Mesh(vehicleGeometry, vehicleMaterial);
      mesh.position.set(vehicle.x, 11, vehicle.y);
      scene.add(mesh);
    }

    /* -- vessels at anchor ---------------------------------------------- */
    const waiting = state.calls.filter((c) => c.state === "waiting");
    waiting.forEach((call, index) => {
      const hull = new THREE.Mesh(
        track(new THREE.BoxGeometry(call.loa_m * 0.72, 26, 38)),
        track(new THREE.MeshStandardMaterial({ color: 0x7a5f52, roughness: 0.8 })),
      );
      // Ranked seaward in the order they will be served, so the anchorage
      // reads as a queue rather than as scatter.
      hull.position.set(
        200 + (index % 4) * 460,
        13,
        -300 - Math.floor(index / 4) * 190,
      );
      scene.add(hull);
      pickables.push({
        mesh: hull,
        selection: {
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
        },
      });
    });

    /* -- interaction ---------------------------------------------------- */
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();

    const onClick = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(
        pickables.map((p) => p.mesh),
        true,
      );
      if (!hits.length) {
        handlers.current.onSelect?.(null);
        return;
      }
      // The hit may be a child of a picked group (a crane leg), so walk up.
      let node: THREE.Object3D | null = hits[0].object;
      while (node) {
        const match = pickables.find((p) => p.mesh === node);
        if (match) {
          handlers.current.onSelect?.(match.selection);
          return;
        }
        node = node.parent;
      }
      handlers.current.onSelect?.(null);
    };
    renderer.domElement.addEventListener("click", onClick);

    // Orbit by drag, zoom by wheel. Hand-rolled rather than OrbitControls: the
    // camera is constrained to a hemisphere above the quay, which the stock
    // controls do not do without fighting them.
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    const target = new THREE.Vector3(extentX * 0.45, 0, extentY * 0.4);
    const spherical = new THREE.Spherical().setFromVector3(
      camera.position.clone().sub(target),
    );

    const applyCamera = () => {
      spherical.phi = Math.max(0.18, Math.min(Math.PI / 2 - 0.06, spherical.phi));
      spherical.radius = Math.max(extentX * 0.35, Math.min(extentX * 2.6, spherical.radius));
      camera.position.copy(target).add(new THREE.Vector3().setFromSpherical(spherical));
      camera.lookAt(target);
    };

    const onDown = (event: MouseEvent) => {
      dragging = true;
      lastX = event.clientX;
      lastY = event.clientY;
    };
    const onUp = () => {
      dragging = false;
    };
    const onMove = (event: MouseEvent) => {
      if (!dragging) return;
      spherical.theta -= (event.clientX - lastX) * 0.005;
      spherical.phi -= (event.clientY - lastY) * 0.005;
      lastX = event.clientX;
      lastY = event.clientY;
      applyCamera();
    };
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      spherical.radius *= 1 + Math.sign(event.deltaY) * 0.08;
      applyCamera();
    };

    renderer.domElement.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("mousemove", onMove);
    renderer.domElement.addEventListener("wheel", onWheel, { passive: false });

    const resize = () => {
      const w = mount.clientWidth || width;
      const h = mount.clientHeight || height;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(mount);

    let raf = 0;
    const render = () => {
      raf = requestAnimationFrame(render);
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(render);

    const dispose = () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      renderer.domElement.removeEventListener("click", onClick);
      renderer.domElement.removeEventListener("mousedown", onDown);
      renderer.domElement.removeEventListener("wheel", onWheel);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("mousemove", onMove);
      for (const item of disposables) item.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) {
        mount.removeChild(renderer.domElement);
      }
    };

    sceneRef.current = { renderer, scene, camera, pickables, dispose };
    return dispose;
    // Rebuild only when the port's shape changes; recolouring is a separate
    // effect so switching overlay never tears the GL context down.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shapeKey]);

  /* -- recolour on overlay or data change ------------------------------ */
  useEffect(() => {
    const current = sceneRef.current;
    if (!current) return;

    const berthById = new Map(state.berths.map((b) => [b.berth_id, b]));
    const blockById = new Map(state.yardBlocks.map((b) => [b.block_id, b]));
    const craneById = new Map(state.cranes.map((c) => [c.crane_id, c]));
    const shedById = new Map(state.sheds.map((s) => [s.shed_id, s]));
    const callById = new Map(state.calls.map((c) => [c.call_id, c]));

    const maxCraneHours = Math.max(
      1,
      ...state.cranes.map((c) => c.working_hours),
    );
    const maxWait = Math.max(1, ...state.calls.map((c) => c.wait_hours));
    const maxDwell = Math.max(1, ...state.yardBlocks.map((b) => b.mean_dwell_hours));

    for (const { mesh, selection } of current.pickables) {
      let value: number | null = null;

      if (selection.kind === "berth") {
        const berth = berthById.get(selection.id);
        if (berth) {
          value =
            overlay === "queue"
              ? berth.occupied_by
                ? 0.85
                : 0.15
              : berth.occupied_by
                ? 0.8
                : 0.12;
        }
      } else if (selection.kind === "yard") {
        const block = blockById.get(selection.id);
        if (block) {
          value =
            overlay === "dwell"
              ? block.mean_dwell_hours / maxDwell
              : overlay === "storage"
                ? Math.min(1, block.utilisation / 0.95)
                : block.utilisation;
        }
      } else if (selection.kind === "crane") {
        const crane = craneById.get(selection.id);
        if (crane) {
          value =
            overlay === "workload"
              ? crane.working_hours / maxCraneHours
              : crane.assigned_berth
                ? 0.75
                : 0.15;
        }
      } else if (selection.kind === "shed") {
        const shed = shedById.get(selection.id);
        if (shed) value = overlay === "storage" ? shed.utilisation : shed.utilisation * 0.6;
      } else if (selection.kind === "vessel") {
        const call = callById.get(selection.id);
        if (call) value = Math.min(1, call.wait_hours / maxWait);
      }

      const colour =
        value == null ? IDLE.clone() : pressureColour(value);
      const emphasised = selectedId === selection.id;

      mesh.traverse((child) => {
        if (!(child instanceof THREE.Mesh)) return;
        const material = child.material;
        if (!(material instanceof THREE.MeshStandardMaterial)) return;
        material.color.copy(colour);
        material.emissive.set(emphasised ? 0x2b6f9e : 0x000000);
        material.emissiveIntensity = emphasised ? 0.6 : 0;
        material.needsUpdate = true;
      });
    }
  }, [overlay, selectedId, state]);

  if (failed) {
    return (
      <div className="grid h-full w-full place-items-center bg-[#061420] p-6 text-center">
        <div className="max-w-[380px]">
          <div className="mb-1 text-[12px] font-medium text-[var(--crit)]">
            3D renderer unavailable
          </div>
          <p className="text-[11.5px] leading-relaxed text-[var(--text-3)]">
            {failed}. The twin's metrics and overlays on this screen are unaffected —
            only the spatial view is missing.
          </p>
        </div>
      </div>
    );
  }

  return <div ref={mountRef} className={className} data-testid="port-twin-scene" />;
}

export default PortTwinScene;
