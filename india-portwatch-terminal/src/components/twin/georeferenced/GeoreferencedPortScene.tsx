import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { TwinSelection } from "../PortTwinScene";
import {
  localPoint,
  parseCatalogue,
  ring,
  type Catalogue,
  type GeographicFeature,
  type GeometryKind,
} from "./catalogue";

const COLOURS: Record<GeometryKind, string> = {
  boundary: "#25483d",
  coastline: "#65c5d0",
  water: "#123949",
  breakwater: "#81939a",
  berth: "#dbb65e",
  yard: "#6c8667",
  building: "#a4b0bc",
  gate: "#d5a057",
  road: "#6c737b",
  rail: "#bd8570",
};
const ORDER: GeometryKind[] = [
  "boundary",
  "water",
  "coastline",
  "breakwater",
  "road",
  "rail",
  "yard",
  "berth",
  "building",
  "gate",
];
function inspect(
  feature: GeographicFeature,
  catalogue: Catalogue,
): TwinSelection {
  return {
    id: feature.id,
    kind: "geometry",
    label: feature.properties.name,
    fields: [
      ["Feature ID", feature.id],
      ["Geometry", feature.properties.kind],
      ["Version", catalogue.geometryVersion],
      ["Footprint quality", feature.properties.horizontalQuality],
      ["Height", "Unknown; footprints at display zero"],
      ["Acquisition date", feature.properties.sourceDate ?? "Unknown"],
      ["OSM edit date", feature.properties.sourceModifiedAt ?? "Unknown"],
      ["Sources", feature.properties.sourceIds.join(", ")],
      ["Operational mapping", "Unavailable — review required"],
      ["Attribution", catalogue.sources.map((s) => s.attribution).join("; ")],
    ],
  };
}

/** Real static footprints only. Simulator geometry is intentionally not projected by array index. */
export default function GeoreferencedPortScene({
  portCode,
  selectedId,
  onSelect,
  onFallback,
}: {
  portCode: string;
  selectedId: string | null;
  onSelect: (selection: TwinSelection | null) => void;
  onFallback: () => void;
}) {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState(false);
  const [webglFailed, setWebglFailed] = useState(false);
  const [layers, setLayers] = useState<Set<GeometryKind>>(() => new Set(ORDER));
  const mount = useRef<HTMLDivElement>(null);
  const action = useRef<{
    reset: () => void;
    plan: () => void;
    fit: () => void;
  } | null>(null);
  const handler = useRef(onSelect);
  handler.current = onSelect;
  const selected = useRef(selectedId);
  selected.current = selectedId;
  const live = useRef<{ objects: THREE.Object3D[]; render: () => void } | null>(
    null,
  );
  useEffect(() => {
    const abort = new AbortController();
    setCatalogue(null);
    setError(null);
    setWebglFailed(false);
    fetch(`/port-geometry/${portCode}/osm-20261017-v1.geojson`, {
      signal: abort.signal,
    })
      .then((r) => {
        if (!r.ok) throw new Error(`Geometry unavailable (${r.status})`);
        return r.json();
      })
      .then((v) => setCatalogue(parseCatalogue(v, portCode)))
      .catch((e) => {
        if (!abort.signal.aborted)
          setError(e instanceof Error ? e.message : "Geometry unavailable");
      });
    return () => abort.abort();
  }, [portCode]);
  const local = useMemo(
    () =>
      catalogue?.features.map((feature) => ({
        feature,
        points: ring(feature).map((p) => localPoint(p, catalogue.origin)),
      })) ?? [],
    [catalogue],
  );
  const bounds = useMemo(() => {
    const points = local.flatMap((f) => f.points);
    let minX = Infinity,
      minY = Infinity,
      maxX = -Infinity,
      maxY = -Infinity;
    for (const [x, y] of points) {
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    }
    return {
      minX,
      minY,
      maxX,
      maxY,
      span: Math.max(maxX - minX, maxY - minY, 100),
    };
  }, [local]);
  useEffect(() => {
    if (!catalogue || !mount.current || plan || webglFailed) return;
    const container = mount.current;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      setWebglFailed(true);
      return;
    }
    renderer.setClearColor("#061420");
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    container.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 1, 100000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.maxPolarAngle = Math.PI / 2 - 0.01;
    controls.minDistance = 25;
    controls.maxDistance = bounds.span * 5;
    const centre = new THREE.Vector3(
      (bounds.minX + bounds.maxX) / 2,
      0,
      -(bounds.minY + bounds.maxY) / 2,
    );
    const render = () => renderer.render(scene, camera);
    const frame = (box?: THREE.Box3, top = false) => {
      const target = box ? box.getCenter(new THREE.Vector3()) : centre;
      const size = box
        ? Math.max(100, box.getSize(new THREE.Vector3()).length())
        : bounds.span;
      const distance = (size * 1.4) / Math.min(1, camera.aspect);
      controls.target.copy(target);
      camera.position
        .copy(target)
        .add(
          new THREE.Vector3(
            0,
            distance * (top ? 1 : 0.85),
            distance * (top ? 0.001 : 0.8),
          ),
        );
      controls.update();
      render();
    };
    const objects: THREE.Object3D[] = [];
    for (const { feature, points } of local) {
      const index = ORDER.indexOf(feature.properties.kind);
      const elevation = index * 0.15; // Z-fighting offset; never a reported terrain elevation.
      let object: THREE.Object3D;
      if (feature.geometry.type === "Polygon") {
        const shape = new THREE.Shape(
          points.map(([e, n]) => new THREE.Vector2(e, n)),
        );
        const geometry = new THREE.ShapeGeometry(shape);
        geometry.rotateX(-Math.PI / 2);
        object = new THREE.Mesh(
          geometry,
          new THREE.MeshBasicMaterial({
            color: COLOURS[feature.properties.kind],
            side: THREE.DoubleSide,
            transparent: feature.properties.kind === "boundary",
            opacity: feature.properties.kind === "boundary" ? 0.45 : 1,
          }),
        );
      } else {
        object = new THREE.Line(
          new THREE.BufferGeometry().setFromPoints(
            points.map(([e, n]) => new THREE.Vector3(e, 0, -n)),
          ),
          new THREE.LineBasicMaterial({
            color: COLOURS[feature.properties.kind],
          }),
        );
      }
      object.position.y = elevation;
      object.userData.feature = feature;
      scene.add(object);
      objects.push(object);
    }
    // A fixed 500 metre reference remains in the world as the camera rotates.
    const scale = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(bounds.minX, 2, -bounds.minY - 100),
        new THREE.Vector3(bounds.minX + 500, 2, -bounds.minY - 100),
      ]),
      new THREE.LineBasicMaterial({ color: "#ffffff" }),
    );
    scene.add(scale);
    const north = new THREE.ArrowHelper(
      new THREE.Vector3(0, 0, -1),
      new THREE.Vector3(bounds.minX, 2, -bounds.minY - 200),
      300,
      0xffffff,
      70,
      30,
    );
    scene.add(north);
    const resize = () => {
      const w = container.clientWidth || 800,
        h = container.clientHeight || 500;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      render();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();
    frame();
    controls.addEventListener("change", render);
    const ray = new THREE.Raycaster();
    ray.params.Line = { threshold: 8 };
    let down: [number, number] = [0, 0];
    const pointerDown = (e: PointerEvent) => {
      down = [e.clientX, e.clientY];
    };
    const click = (e: MouseEvent) => {
      if (Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
      const rect = renderer.domElement.getBoundingClientRect();
      ray.setFromCamera(
        new THREE.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          (-(e.clientY - rect.top) / rect.height) * 2 + 1,
        ),
        camera,
      );
      const hit = ray.intersectObjects(
        objects.filter((o) => o.visible),
        false,
      )[0];
      handler.current(
        hit ? inspect(hit.object.userData.feature, catalogue) : null,
      );
    };
    const contextLost = (e: Event) => {
      e.preventDefault();
      setWebglFailed(true);
    };
    renderer.domElement.addEventListener("pointerdown", pointerDown);
    renderer.domElement.addEventListener("click", click);
    renderer.domElement.addEventListener("webglcontextlost", contextLost);
    action.current = {
      reset: () => frame(),
      plan: () => frame(undefined, true),
      fit: () => {
        const o = objects.find(
          (o) => o.userData.feature.id === selected.current,
        );
        if (o) frame(new THREE.Box3().setFromObject(o));
      },
    };
    live.current = { objects, render };
    return () => {
      observer.disconnect();
      controls.removeEventListener("change", render);
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", pointerDown);
      renderer.domElement.removeEventListener("click", click);
      renderer.domElement.removeEventListener("webglcontextlost", contextLost);
      scene.traverse((o) => {
        const mesh = o as THREE.Mesh;
        mesh.geometry?.dispose();
        if (mesh.material)
          for (const m of Array.isArray(mesh.material)
            ? mesh.material
            : [mesh.material])
            m.dispose();
      });
      renderer.dispose();
      renderer.domElement.remove();
      live.current = null;
      action.current = null;
    };
  }, [catalogue, local, bounds, plan, webglFailed]);
  useEffect(() => {
    for (const object of live.current?.objects ?? []) {
      const feature: GeographicFeature = object.userData.feature;
      object.visible = layers.has(feature.properties.kind);
      const material = (object as THREE.Mesh)
        .material as THREE.MeshBasicMaterial;
      material.color.set(
        feature.id === selectedId
          ? "#ffffff"
          : COLOURS[feature.properties.kind],
      );
    }
    live.current?.render();
  }, [layers, selectedId, catalogue, plan, webglFailed]);
  const flat = plan || webglFailed;
  if (error)
    return (
      <div role="status" className="p-6 text-sm">
        {error}.{" "}
        <button type="button" className="underline" onClick={onFallback}>
          Open schematic reference
        </button>
      </div>
    );
  if (!catalogue)
    return (
      <div role="status" className="p-6 text-sm">
        Loading retained geographic footprints…
      </div>
    );
  return (
    <div
      className="relative h-full w-full bg-[#061420]"
      data-testid="georeferenced-port-scene"
    >
      {flat ? (
        <svg
          role="img"
          aria-label="JNPA geographic footprints, north up, unverified positional accuracy"
          className="h-full w-full"
          viewBox={`${bounds.minX - 100} ${-bounds.maxY - 100} ${bounds.maxX - bounds.minX + 200} ${bounds.maxY - bounds.minY + 200}`}
        >
          {local
            .filter(({ feature }) => layers.has(feature.properties.kind))
            .map(({ feature, points }) => (
              <path
                key={feature.id}
                d={`M ${points.map(([x, y]) => `${x},${-y}`).join(" L ")}${feature.geometry.type === "Polygon" ? " Z" : ""}`}
                fill={
                  feature.geometry.type === "Polygon"
                    ? COLOURS[feature.properties.kind]
                    : "none"
                }
                fillOpacity={feature.properties.kind === "boundary" ? 0.35 : 1}
                stroke={
                  selectedId === feature.id
                    ? "white"
                    : COLOURS[feature.properties.kind]
                }
                strokeWidth={selectedId === feature.id ? 12 : 3}
                onClick={() => onSelect(inspect(feature, catalogue))}
              >
                <title>{feature.properties.name}</title>
              </path>
            ))}
          <path
            d={`M ${bounds.minX} ${-bounds.minY + 50} h 500`}
            stroke="white"
            strokeWidth="8"
          />
          <text
            x={bounds.minX}
            y={-bounds.minY + 90}
            fill="white"
            fontSize="50"
          >
            500 m · N ↑
          </text>
        </svg>
      ) : (
        <div
          ref={mount}
          className="h-full w-full"
          aria-label="Orbit by drag, pan by right drag, zoom by wheel"
        />
      )}
      <div className="absolute left-2 top-2 max-w-[75%] rounded bg-[var(--panel)]/95 p-2 text-[10px]">
        <div>
          JNPA · retained OSM geography · horizontal accuracy unverified
        </div>
        <div>
          Heights unknown · static footprints · no mapped operational
          observations
        </div>
        <div>
          White world line: 500 m · arrow: north ·{" "}
          {catalogue.features.length.toLocaleString()} features
        </div>
        <div className="mt-1 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => {
              setPlan(false);
              action.current?.reset();
            }}
          >
            Reset / oblique
          </button>
          <button type="button" onClick={() => action.current?.plan()}>
            Top view
          </button>
          <button
            type="button"
            disabled={!selectedId || flat}
            onClick={() => action.current?.fit()}
          >
            Fit selection
          </button>
          <button
            type="button"
            aria-pressed={plan}
            onClick={() => setPlan((v) => !v)}
          >
            2D plan
          </button>
          <button type="button" onClick={onFallback}>
            Schematic reference
          </button>
        </div>
        <div className="mt-1 flex flex-wrap gap-2">
          {ORDER.map((kind) => (
            <label key={kind}>
              <input
                type="checkbox"
                checked={layers.has(kind)}
                onChange={() =>
                  setLayers((old) => {
                    const next = new Set(old);
                    if (next.has(kind)) next.delete(kind);
                    else next.add(kind);
                    return next;
                  })
                }
              />
              {kind}
            </label>
          ))}
        </div>
        {webglFailed && (
          <div role="status">
            WebGL unavailable; showing retained 2D geography.
          </div>
        )}
      </div>
      <div className="absolute bottom-2 right-2 rounded bg-[var(--panel)]/95 p-1 text-[9px]">
        <a
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noreferrer"
        >
          © OpenStreetMap contributors · ODbL
        </a>
      </div>
    </div>
  );
}
