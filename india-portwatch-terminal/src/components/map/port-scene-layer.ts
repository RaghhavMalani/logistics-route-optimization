import * as THREE from "three";
import {
  MercatorCoordinate,
  type CustomLayerInterface,
  type Map as MapLibreMap,
} from "maplibre-gl";
import { createMiniatureLighting } from "@/components/miniature/lighting";

const renderers = new WeakMap<
  HTMLCanvasElement,
  { renderer: THREE.WebGLRenderer; uses: number }
>();

/** Share one Three renderer across the two static scenes on MapLibre's canvas. */
export function portSceneLayer(
  id: string,
  scene: THREE.Scene,
  drawAt: (map: MapLibreMap, model: THREE.Matrix4) => boolean,
  resources: Iterable<THREE.BufferGeometry | THREE.Material>,
  weather?: (map: MapLibreMap, lighting: ReturnType<typeof createMiniatureLighting>) => boolean,
  disposeWeather?: () => void,
): CustomLayerInterface {
  const camera = new THREE.Camera();
  const model = new THREE.Matrix4();
  const lighting = createMiniatureLighting(scene, true);
  lighting.sun.castShadow = false;
  lighting.follow(new THREE.Vector3(), 45);
  let canvas: HTMLCanvasElement;
  let entry: { renderer: THREE.WebGLRenderer; uses: number } | undefined;
  let map: MapLibreMap;
  return {
    id,
    type: "custom",
    renderingMode: "3d",
    onAdd(instance, context) {
      map = instance;
      canvas = map.getCanvas();
      entry = renderers.get(canvas);
      if (!entry) {
        const renderer = new THREE.WebGLRenderer({ canvas, context });
        renderer.autoClear = false;
        renderer.toneMapping = THREE.NeutralToneMapping;
        renderers.set(canvas, (entry = { renderer, uses: 0 }));
      }
      entry.uses++;
    },
    render(_context, frame) {
      if (!entry || document.hidden || !drawAt(map, model)) return;
      camera.projectionMatrix
        .fromArray(frame.defaultProjectionData.mainMatrix)
        .multiply(model);
      camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
      const animate = weather?.(map, lighting);
      entry.renderer.resetState();
      entry.renderer.shadowMap.enabled = lighting.sun.castShadow;
      entry.renderer.render(scene, camera);
      if (animate) map.triggerRepaint();
    },
    onRemove() {
      disposeWeather?.();
      lighting.dispose();
      const disposable = new Set(resources);
      scene.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        disposable.add(object.geometry);
        for (const material of Array.isArray(object.material)
          ? object.material
          : [object.material])
          disposable.add(material);
        if (object instanceof THREE.InstancedMesh) object.dispose();
      });
      for (const resource of disposable) resource.dispose();
      scene.clear();
      if (entry && --entry.uses === 0) {
        entry.renderer.dispose();
        renderers.delete(canvas);
      }
      entry = undefined;
    },
  };
}

const axes = new THREE.Matrix4().makeRotationX(Math.PI / 2);
const stretch = new THREE.Vector3();

export function placeScene(
  matrix: THREE.Matrix4,
  anchor: [number, number],
  metresPerUnit: number,
) {
  const origin = MercatorCoordinate.fromLngLat(anchor);
  const scale = origin.meterInMercatorCoordinateUnits() * metresPerUnit;
  return matrix
    .makeTranslation(origin.x, origin.y, origin.z)
    .scale(stretch.set(scale, -scale, scale))
    .multiply(axes);
}
