import * as T from "three";
import { COLORS } from "./palette";
/** Retuned for physically based r186; PCFSoftShadowMap was removed in r186. */
export function createMiniatureLighting(scene: T.Scene, mobile: boolean) {
  const hemi = new T.HemisphereLight(COLORS.skyLight, COLORS.groundLight, 3.3);
  const sun = new T.DirectionalLight(COLORS.sunWarm, 3.6);
  sun.castShadow = true;
  sun.shadow.mapSize.setScalar(mobile ? 1024 : 2048);
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.6;
  scene.add(hemi, sun, sun.target);
  const direction = new T.Vector3(-0.42, 0.86, 0.32).normalize();
  return {
    sun,
    hemi,
    follow(target: T.Vector3, size: number, heading = direction) {
      const distance = Math.max(600, size * 1.85);
      sun.position.copy(target).addScaledVector(heading, distance);
      sun.target.position.copy(target);
      const c = sun.shadow.camera,
        reach = size * 1.25;
      c.left = -reach;
      c.right = reach;
      c.top = reach;
      c.bottom = -reach;
      c.near = Math.max(10, distance - reach * 1.2);
      c.far = distance + reach * 1.6;
      c.updateProjectionMatrix();
    },
    dispose() {
      sun.shadow.dispose();
    },
  };
}
