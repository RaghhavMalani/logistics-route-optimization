import * as THREE from "three";
import { createMiniatureBuilders } from "@/components/miniature/builders";
import { seededRandom } from "@/components/miniature/rng";
import {
  GROVE_ZOOM,
  inView,
  portSeed,
  type PortMiniatureTarget,
} from "./port-placement";
import { placeScene, portSceneLayer } from "./port-scene-layer";

export function createPortGroves(port: PortMiniatureTarget) {
  const scene = new THREE.Scene();
  const rng = seededRandom(portSeed(port.code) ^ 1049);
  const { M, unitBox, placeTrees } = createMiniatureBuilders(scene, rng);
  const seeds = port.shore.groves.flatMap(([east, north]) =>
    Array.from({ length: 7 }, () => ({
      x: east + (rng() - 0.5) * 410,
      z: -north + (rng() - 0.5) * 410,
      size: 0.7 + rng() * 0.55,
    })),
  );
  // Keep positions fixed; each level shares two instanced draws for all groves.
  const levels = [93, 40, 16, 8].map((scale) => {
    const group = new THREE.Group();
    placeTrees(
      group,
      seeds.map((tree) => ({ ...tree, size: tree.size * scale })),
    );
    scene.add(group);
    return group;
  });
  return portSceneLayer(
    "port-groves",
    scene,
    (map, model) => {
      const zoom = map.getZoom();
      if (zoom < GROVE_ZOOM || !inView(map, port.center, 140)) return false;
      const level = zoom < 9.5 ? 0 : zoom < 11.5 ? 1 : zoom < 13 ? 2 : 3;
      levels.forEach((group, index) => {
        group.visible = index === level;
      });
      placeScene(model, port.center, 1);
      return true;
    },
    [unitBox, ...Object.values(M)],
  );
}
