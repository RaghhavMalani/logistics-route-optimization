import * as THREE from "three";
import { MercatorCoordinate, type CustomLayerInterface } from "maplibre-gl";
import { createMiniatureBuilders } from "@/components/miniature/builders";
import { createMiniatureLighting } from "@/components/miniature/lighting";
import { seededRandom } from "@/components/miniature/rng";
import type { PortMiniatureTarget } from "./usePortMiniature";

export const PORT_MINIATURE_LAYER = "port-miniature";

export function createPortMiniature(
  port: PortMiniatureTarget,
): CustomLayerInterface {
  const scene = new THREE.Scene();
  const seed = [...port.code].reduce(
    (value, letter) => value * 31 + letter.charCodeAt(0),
    0,
  );
  const { M, unitBox, box, makeQuayCrane, rnd } = createMiniatureBuilders(
    scene,
    seededRandom(seed),
  );
  const origin = MercatorCoordinate.fromLngLat(port.center);
  const metresPerUnit = 28;
  const scale = origin.meterInMercatorCoordinateUnits() * metresPerUnit;
  const model = new THREE.Matrix4()
    .makeTranslation(origin.x, origin.y, origin.z)
    .scale(new THREE.Vector3(scale, -scale, scale))
    .multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2));

  box(scene, 52, 1.5, 65, M.land, 12, 0, 0);
  box(scene, 12, 1.75, 65, M.pave, -13, 0.1, 0);
  box(scene, 0.8, 0.6, 64, M.ink, -19, 0.85, 0, false);
  box(scene, 3, 0.25, 63, M.road, -4, 0.87, 0, false);
  for (const z of [-20, 0, 20]) {
    const crane = makeQuayCrane(z);
    crane.g.position.x = -14;
    crane.g.position.y = 0.98;
    crane.g.scale.setScalar(0.57);
  }

  const yardColors = [M.white, M.road, M.pave, M.rail];
  for (const x of [7, 16, 25]) {
    for (const z of [-22, -11, 0, 11, 22]) {
      const tiers = rnd() > 0.42 ? 2 : 1;
      for (let tier = 0; tier < tiers; tier++) {
        const material = yardColors[Math.floor(rnd() * yardColors.length)];
        box(scene, 6.3, 1.65, 7.2, material, x, 1.6 + tier * 1.65, z);
      }
    }
  }
  box(scene, 9, 3.2, 16, M.white, 35, 2.3, 12);
  box(scene, 9.5, 0.6, 17, M.rail, 35, 4.1, 12);

  // The tour's parts are static on the chart. Batch their shared boxes by ink.
  const batches = new Map<THREE.Material, THREE.Matrix4[]>();
  scene.updateMatrixWorld(true);
  scene.traverse((object) => {
    if (!(object instanceof THREE.Mesh) || Array.isArray(object.material))
      return;
    const matrices = batches.get(object.material) ?? [];
    matrices.push(object.matrixWorld.clone());
    batches.set(object.material, matrices);
  });
  scene.clear();
  for (const [material, matrices] of batches) {
    const mesh = new THREE.InstancedMesh(unitBox, material, matrices.length);
    matrices.forEach((matrix, index) => mesh.setMatrixAt(index, matrix));
    mesh.computeBoundingSphere();
    scene.add(mesh);
  }

  const lighting = createMiniatureLighting(scene, true);
  lighting.follow(new THREE.Vector3(), 45);
  lighting.sun.castShadow = false;

  const camera = new THREE.Camera();
  let renderer: THREE.WebGLRenderer | undefined;
  return {
    id: PORT_MINIATURE_LAYER,
    type: "custom",
    renderingMode: "3d",
    onAdd(map, context) {
      renderer = new THREE.WebGLRenderer({ canvas: map.getCanvas(), context });
      renderer.autoClear = false;
      renderer.toneMapping = THREE.NoToneMapping;
    },
    render(_context, frame) {
      if (!renderer) return;
      camera.projectionMatrix
        .fromArray(frame.defaultProjectionData.mainMatrix)
        .multiply(model);
      camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
      renderer.resetState();
      renderer.render(scene, camera);
    },
    onRemove() {
      lighting.dispose();
      unitBox.dispose();
      for (const material of new Set([...Object.values(M), ...batches.keys()]))
        material.dispose();
      renderer?.dispose();
      scene.clear();
    },
  };
}
