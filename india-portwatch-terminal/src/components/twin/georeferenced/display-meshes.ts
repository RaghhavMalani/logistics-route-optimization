import * as THREE from "three";
import { localPoint, type Position } from "./catalogue";
import type { DisplayLayer } from "./RemoteLayers";

/** Display-only layers. This function never reads analyticalResource values. */
export function attachDisplayLayers(
  scene: THREE.Scene,
  origin: Position,
  layers: DisplayLayer[],
  render: () => void,
  onError: (message: string | null) => void,
) {
  const group = new THREE.Group();
  scene.add(group);
  const abort = new AbortController();
  let active = true;
  const textures: THREE.Texture[] = [];
  onError(null);
  const disposeObject = (object: THREE.Object3D) =>
    object.traverse((node) => {
      const o = node as THREE.Mesh;
      o.geometry?.dispose();
      if (o.material)
        for (const m of Array.isArray(o.material) ? o.material : [o.material])
          m.dispose();
    });
  for (const layer of layers) {
    if (layer.descriptor.kind === "raster") {
      const [west, south, east, north] = layer.descriptor.bounds;
      const geometry = new THREE.PlaneGeometry(1, 1, 24, 24);
      const positions = geometry.attributes.position;
      const uv = geometry.attributes.uv;
      for (let i = 0; i < positions.count; i++) {
        const [e, n] = localPoint(
          [
            west + (east - west) * uv.getX(i),
            south + (north - south) * uv.getY(i),
          ],
          origin,
        );
        positions.setXYZ(i, e, -1, -n);
      }
      positions.needsUpdate = true;
      geometry.computeBoundingSphere();
      const texture = new THREE.TextureLoader().load(
        layer.url,
        () => {
          if (active) render();
          else texture.dispose();
        },
        undefined,
        () => {
          if (active)
            onError(`Display image unavailable: ${layer.descriptor.layerId}`);
        },
      );
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.magFilter = THREE.NearestFilter;
      textures.push(texture);
      group.add(
        new THREE.Mesh(
          geometry,
          new THREE.MeshBasicMaterial({
            map: texture,
            side: THREE.DoubleSide,
            transparent: true,
            depthWrite: false,
          }),
        ),
      );
    } else {
      fetch(layer.url, { signal: abort.signal, credentials: "omit" })
        .then((r) => {
          if (!r.ok) throw new Error("Vector display unavailable");
          return r.json();
        })
        .then((value) => {
          if (!active) return;
          if (
            value.type !== "FeatureCollection" ||
            !Array.isArray(value.features) ||
            value.features.length > 10000
          )
            throw new Error("Unsupported vector display");
          const draft = new THREE.Group();
          try {
            let count = 0;
            for (const feature of value.features) {
              const geometry = feature.geometry;
              if (
                !geometry ||
                !["Polygon", "LineString"].includes(geometry.type)
              )
                throw new Error(
                  "Vector layer supports Polygon/LineString only",
                );
              if (
                geometry.type === "Polygon" &&
                geometry.coordinates.length !== 1
              )
                throw new Error("Vector holes need explicit preprocessing");
              const points: Position[] =
                geometry.type === "Polygon"
                  ? geometry.coordinates[0]
                  : geometry.coordinates;
              if (
                !Array.isArray(points) ||
                points.length < 2 ||
                (count += points.length) > 100000
              )
                throw new Error("Invalid vector geometry size");
              const vertices = points.map((p) => {
                if (
                  !Array.isArray(p) ||
                  p.length !== 2 ||
                  !p.every(Number.isFinite) ||
                  Math.abs(p[0]) > 180 ||
                  Math.abs(p[1]) > 90
                )
                  throw new Error("Invalid vector coordinate");
                const [e, n] = localPoint(p, origin);
                if (Math.hypot(e, n) > 50000)
                  throw new Error("Vector outside local frame");
                return new THREE.Vector3(e, 3, -n);
              });
              draft.add(
                new THREE.Line(
                  new THREE.BufferGeometry().setFromPoints(vertices),
                  new THREE.LineBasicMaterial({ color: "#e6cc73" }),
                ),
              );
            }
            group.add(draft);
            render();
          } catch (e) {
            disposeObject(draft);
            throw e;
          }
        })
        .catch((e) => {
          if (active && !abort.signal.aborted)
            onError(
              `${layer.descriptor.layerId}: ${e instanceof Error ? e.message : "Unavailable"}`,
            );
        });
    }
  }
  render();
  return () => {
    active = false;
    abort.abort();
    scene.remove(group);
    disposeObject(group);
    textures.forEach((t) => t.dispose());
  };
}
