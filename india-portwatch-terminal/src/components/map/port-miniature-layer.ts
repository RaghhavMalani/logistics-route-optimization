import * as THREE from "three";
import { createPortSceneWeather } from "@/components/miniature/port-scene-weather";
import type { MiniatureWeather } from "@/components/miniature/use-port-weather";
import { createMiniatureBuilders } from "@/components/miniature/builders";
import { seededRandom } from "@/components/miniature/rng";
import {
  SCHEMATIC_ZOOM,
  inView,
  portSeed,
  schematicAnchor,
  schematicScale,
  type PortMiniatureTarget,
} from "./port-placement";
import { placeScene, portSceneLayer } from "./port-scene-layer";

/** Batch the tour's shared boxes by material. The two groups are independent LODs. */
function batchBoxes(group: THREE.Group, unitBox: THREE.BoxGeometry) {
  const batches = new Map<THREE.Material, THREE.Matrix4[]>();
  group.updateMatrixWorld(true);
  group.traverse((part) => {
    if (!(part instanceof THREE.Mesh) || Array.isArray(part.material)) return;
    const matrices = batches.get(part.material) ?? [];
    matrices.push(part.matrixWorld.clone());
    batches.set(part.material, matrices);
  });
  group.clear();
  for (const [material, matrices] of batches) {
    const mesh = new THREE.InstancedMesh(unitBox, material, matrices.length);
    matrices.forEach((matrix, index) => mesh.setMatrixAt(index, matrix));
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.computeBoundingSphere();
    group.add(mesh);
  }
}

export function createPortMiniature(
  port: PortMiniatureTarget,
  weather: () => MiniatureWeather | null,
) {
  const scene = new THREE.Scene();
  const core = new THREE.Group();
  const detail = new THREE.Group();
  const {
    M,
    unitBox,
    box,
    makeQuayCrane,
    makeGantry,
    placeTrees,
    dummy,
    boxCol,
    rnd,
  } = createMiniatureBuilders(scene, seededRandom(portSeed(port.code)));

  box(core, 52, 1.2, 58, M.pave, 9, 0, 0);
  box(core, 9, 1.6, 58, M.land, -15, 0, 0);
  box(core, 0.8, 0.65, 58, M.rail, -19.5, 0.48, 0);
  box(core, 2.8, 0.2, 56, M.road, -4, 0.68, 0, false);
  for (const z of [-18, 18, 0]) {
    const { g } = makeQuayCrane(z);
    g.position.set(-16, 0.78, z);
    g.scale.setScalar(0.56);
    (z ? core : detail).add(g);
  }
  const { g: gantry } = makeGantry(12, 8, 4);
  gantry.position.set(17, 0.66, 12);
  gantry.scale.setScalar(0.62);
  detail.add(gantry);
  box(core, 7.5, 3.5, 13, M.white, 29, 2.32, -13);
  box(core, 7.9, 0.65, 13.4, M.rail, 29, 4.32, -13);
  batchBoxes(core, unitBox);
  batchBoxes(detail, unitBox);
  scene.add(core, detail);

  // The tour's container dimensions and ink colours, batched in one draw.
  const stacks = new THREE.InstancedMesh(unitBox, M.white, 320);
  stacks.count = 0;
  for (const x of [4, 13, 22]) {
    for (const z of [-20, -10, 0, 10, 20]) {
      for (let row = 0; row < 4; row++) {
        const tiers = 1 + Math.floor(rnd() * 3);
        for (let tier = 0; tier < tiers; tier++) {
          const index = stacks.count++;
          dummy.position.set(x, 1.27 + tier * 1.36, z - 2.25 + row * 1.5);
          dummy.scale.set(3.05, 1.28, 1.3);
          dummy.updateMatrix();
          stacks.setMatrixAt(index, dummy.matrix);
          stacks.setColorAt(index, new THREE.Color(boxCol()));
        }
      }
    }
  }
  stacks.castShadow = true;
  stacks.receiveShadow = true;
  stacks.computeBoundingSphere();
  core.add(stacks);
  placeTrees(
    core,
    [-24, -16, -7, 6, 15, 23].map((z) => ({
      x: 34 + rnd() * 3,
      z,
      size: 0.52 + rnd() * 0.22,
    })),
  );

  const rotation = new THREE.Matrix4().makeRotationY(
    ((90 - port.shore.bearing) * Math.PI) / 180,
  );
  const center = new THREE.Vector3(9, 0.7, 0);
  const cranePositions = [-18, 18].map(
    (z) => new THREE.Vector3(-16 + 6 * 0.56, 0.78 + 30.5 * 0.56, z),
  );
  const effects = createPortSceneWeather(
    scene,
    center,
    52,
    58,
    90 + port.shore.bearing,
    cranePositions,
  );
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let previousZoom = -1;
  let anchor = port.center;
  return portSceneLayer(
    "port-miniature",
    scene,
    (map, model) => {
      const zoom = map.getZoom();
      if (zoom < SCHEMATIC_ZOOM || !inView(map, port.center, 28)) return false;
      if (zoom !== previousZoom) {
        previousZoom = zoom;
        anchor = schematicAnchor(port, zoom);
        placeScene(model, anchor, schematicScale(zoom)).multiply(rotation);
      }
      detail.visible = zoom >= 12.15;
      return inView(map, anchor, 75);
    },
    [unitBox, ...Object.values(M)],
    (_map, light) => {
      const { direction, night, animate } = effects.draw(
        weather(),
        Date.now(),
        !motion.matches,
      );
      light.follow(center, 45, direction);
      light.sun.castShadow = Boolean(direction && !night);
      light.sun.intensity = night ? 0.12 : 3.6;
      light.hemi.intensity = night ? 0.72 : 3.3;
      return animate;
    },
    effects.dispose,
  );
}
