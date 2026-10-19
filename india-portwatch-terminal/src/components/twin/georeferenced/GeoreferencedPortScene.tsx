import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import RemoteLayers, { type DisplayLayer } from "./RemoteLayers";
import { attachDisplayLayers } from "./display-meshes";
import { getJson } from "@/services/api";
import type { TwinSelection, TwinOverlay } from "../PortTwinScene";
import type { PortTwinState } from "@/types/portwatch-os";
import { operationalView } from "./operational-mapping";
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
  terminal: "#527466",
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
  "terminal",
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
  state?: PortTwinState,
  overlay: TwinOverlay = "utilisation",
): TwinSelection {
  const operational = operationalView(feature, catalogue, state, overlay);
  return {
    id: feature.id,
    kind: "geometry",
    label: feature.properties.name,
    fields: [
      ["Feature ID", feature.id],
      ["Geometry", feature.properties.kind],
      ["Terminal ID", feature.properties.terminalId ?? "Unknown"],
      ...(feature.properties.publishedLengthM != null
        ? [
            [
              "Undated GIS length reference",
              `${feature.properties.publishedLengthM} m; not operational clearance`,
            ] as [string, string],
          ]
        : []),
      ["Version", catalogue.geometryVersion],
      ["Footprint quality", feature.properties.horizontalQuality],
      [
        "Height",
        feature.properties.heightM === null
          ? "Unknown; footprints at display zero"
          : `${feature.properties.heightM} m · ${feature.properties.heightQuality}`,
      ],
      ["Acquisition date", feature.properties.sourceDate ?? "Unknown"],
      ["OSM edit date", feature.properties.sourceModifiedAt ?? "Unknown"],
      ["Sources", feature.properties.sourceIds.join(", ")],
      [
        "Operational mapping",
        operational
          ? "Reviewed ID mapping; simulated state"
          : "Unavailable — no supported identity; review required",
      ],
      ...(operational?.fields ?? []),
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
  state,
  overlay = "utilisation",
}: {
  portCode: string;
  selectedId: string | null;
  onSelect: (selection: TwinSelection | null) => void;
  onFallback: () => void;
  state?: PortTwinState;
  overlay?: TwinOverlay;
}) {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState(false);
  const [illustrativeHeights, setIllustrativeHeights] = useState(false);
  const [berthLabels, setBerthLabels] = useState(false);
  const [webglFailed, setWebglFailed] = useState(false);
  const [displayLayers, setDisplayLayers] = useState<DisplayLayer[]>([]);
  const [layerError, setLayerError] = useState<string | null>(null);
  const assetIds = useMemo(
    () => new Set(catalogue?.features.map((f) => f.id) ?? []),
    [catalogue],
  );
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
  const operationalState = useRef({ state, overlay });
  operationalState.current = { state, overlay };
  const live = useRef<{
    objects: THREE.Object3D[];
    scene: THREE.Scene;
    render: () => void;
  } | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    setCatalogue(null);
    setError(null);
    setWebglFailed(false);
    getJson<unknown>(
      `/public/port-geometry/${portCode}/geometry`,
      {},
      { signal: abort.signal },
    )
      .then((v) => setCatalogue(parseCatalogue(v, portCode)))
      .catch((e) => {
        if (!abort.signal.aborted)
          setError(
            "Geometry unavailable: " +
              (e instanceof Error ? e.message : "Unknown error"),
          );
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
    const d = catalogue?.displayBounds;
    const points =
      d && catalogue
        ? [
            [d[0], d[1]],
            [d[2], d[1]],
            [d[2], d[3]],
            [d[0], d[3]],
          ].map((p) => localPoint(p as [number, number], catalogue.origin))
        : local.flatMap((f) => f.points);
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
  }, [local, catalogue]);
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
    const labels: THREE.Sprite[] = [];
    const render = () => {
      camera.updateMatrixWorld();
      const occupied: Array<[number, number, number, number]> = [];
      const pixels =
        (container.clientHeight || 500) /
        (2 * Math.tan((camera.fov * Math.PI) / 360));
      const ordered = labels
        .slice()
        .sort(
          (a, b) =>
            Number(b.userData.featureId === selected.current) -
            Number(a.userData.featureId === selected.current),
        );
      for (const label of ordered) {
        const p = label.position.clone().project(camera);
        const x = ((p.x + 1) * (container.clientWidth || 800)) / 2;
        const y = ((1 - p.y) * (container.clientHeight || 500)) / 2;
        const w = label.scale.x * pixels,
          h = label.scale.y * pixels;
        const box: [number, number, number, number] = [
          x - w / 2,
          y - h / 2,
          x + w / 2,
          y + h / 2,
        ];
        label.visible =
          Boolean(label.userData.showLabel) &&
          p.z >= -1 &&
          p.z <= 1 &&
          !occupied.some(
            (b) =>
              box[0] < b[2] + 4 &&
              box[2] > b[0] - 4 &&
              box[1] < b[3] + 4 &&
              box[3] > b[1] - 4,
          );
        if (label.visible) occupied.push(box);
      }
      const start = performance.now();
      renderer.render(scene, camera);
      renderer.domElement.dataset.renderDurationMs = String(
        performance.now() - start,
      );
      renderer.domElement.dataset.drawCalls = String(
        renderer.info.render.calls,
      );
      renderer.domElement.dataset.triangles = String(
        renderer.info.render.triangles,
      );
    };
    const frame = (box?: THREE.Box3, top = false) => {
      const target = box ? box.getCenter(new THREE.Vector3()) : centre;
      const size = box
        ? Math.max(100, box.getSize(new THREE.Vector3()).length())
        : bounds.span;
      const distance = (size * 1.15) / Math.min(1, camera.aspect);
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
    const labelledTerminals = new Set<string>();
    for (const { feature, points } of local) {
      const index = ORDER.indexOf(feature.properties.kind);
      const elevation = index * 0.15; // Z-fighting offset; never a reported terrain elevation.
      let object: THREE.Object3D;
      if (feature.geometry.type === "Polygon") {
        const shape = new THREE.Shape(
          points.map(([e, n]) => new THREE.Vector2(e, n)),
        );
        const displayHeight =
          feature.properties.heightM ??
          (illustrativeHeights && feature.properties.kind === "building"
            ? 6
            : null);
        const geometry =
          displayHeight !== null && displayHeight > 0
            ? new THREE.ExtrudeGeometry(shape, {
                depth: displayHeight,
                bevelEnabled: false,
              })
            : new THREE.ShapeGeometry(shape);
        geometry.rotateX(-Math.PI / 2);
        object = new THREE.Mesh(
          geometry,
          new THREE.MeshBasicMaterial({
            color: COLOURS[feature.properties.kind],
            side: THREE.DoubleSide,
            transparent: ["boundary", "terminal", "berth"].includes(
              feature.properties.kind,
            ),
            opacity:
              feature.properties.kind === "boundary"
                ? 0.2
                : feature.properties.kind === "terminal"
                  ? 0.12
                  : feature.properties.kind === "berth"
                    ? 0.45
                    : 1,
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
      const labelKey =
        feature.properties.kind === "terminal"
          ? (feature.properties.terminalId ?? feature.id)
          : feature.id;
      if (
        (feature.properties.kind === "terminal" ||
          feature.properties.kind === "berth") &&
        !labelledTerminals.has(labelKey)
      ) {
        labelledTerminals.add(labelKey);
        const canvas = document.createElement("canvas");
        canvas.width = 512;
        canvas.height = 64;
        const context = canvas.getContext("2d");
        if (context) {
          context.fillStyle = "rgba(6,20,32,.8)";
          context.fillRect(0, 0, 512, 64);
          context.fillStyle = "#ffffff";
          context.font = "30px sans-serif";
          context.textAlign = "center";
          context.fillText(feature.properties.name, 256, 42, 500);
          const texture = new THREE.CanvasTexture(canvas);
          const label = new THREE.Sprite(
            new THREE.SpriteMaterial({
              map: texture,
              depthTest: false,
              depthWrite: false,
              sizeAttenuation: false,
            }),
          );
          const centre = new THREE.Box3()
            .setFromObject(object)
            .getCenter(new THREE.Vector3());
          label.position.copy(centre).add(new THREE.Vector3(0, 25, 0));
          label.scale.set(0.24, 0.035, 1);
          label.renderOrder = 10;
          label.userData.showLabel = feature.properties.kind === "terminal";
          label.userData.featureId = feature.id;
          labels.push(label);
          object.userData.label = label;
          scene.add(label);
        }
      }
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
        hit
          ? inspect(
              hit.object.userData.feature,
              catalogue,
              operationalState.current.state,
              operationalState.current.overlay,
            )
          : null,
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
    live.current = { objects, scene, render };
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
            : [mesh.material]) {
            if ("map" in m && m.map instanceof THREE.Texture) m.map.dispose();
            m.dispose();
          }
      });
      renderer.dispose();
      renderer.domElement.remove();
      live.current = null;
      action.current = null;
    };
  }, [catalogue, local, bounds, plan, webglFailed, illustrativeHeights]);
  useEffect(() => {
    const current = live.current;
    if (!current || !catalogue) return;
    return attachDisplayLayers(
      current.scene,
      catalogue.origin,
      displayLayers,
      current.render,
      setLayerError,
    );
  }, [displayLayers, catalogue, plan, webglFailed, illustrativeHeights]);
  useEffect(() => {
    for (const object of live.current?.objects ?? []) {
      const feature: GeographicFeature = object.userData.feature;
      object.visible = layers.has(feature.properties.kind);
      if (object.userData.label)
        object.userData.label.userData.showLabel =
          object.visible &&
          (feature.properties.kind === "terminal" ||
            berthLabels ||
            feature.id === selectedId);
      const material = (object as THREE.Mesh)
        .material as THREE.MeshBasicMaterial;
      const operational = catalogue
        ? operationalView(feature, catalogue, state, overlay)
        : null;
      material.color.set(
        feature.id === selectedId
          ? "#ffffff"
          : operational
            ? new THREE.Color().lerpColors(
                new THREE.Color("#3f8f6b"),
                new THREE.Color("#c2564a"),
                Math.max(0, Math.min(1, operational.pressure)),
              )
            : COLOURS[feature.properties.kind],
      );
    }
    live.current?.render();
  }, [
    layers,
    selectedId,
    catalogue,
    plan,
    webglFailed,
    state,
    overlay,
    illustrativeHeights,
    berthLabels,
  ]);
  useEffect(() => {
    const feature = catalogue?.features.find((f) => f.id === selectedId);
    if (feature && catalogue)
      handler.current(inspect(feature, catalogue, state, overlay));
  }, [state, overlay, catalogue, selectedId]);
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
          {displayLayers
            .filter((l) => l.descriptor.kind === "raster")
            .map((layer) => {
              const [w, s, e, n] = layer.descriptor.bounds;
              const [left, top] = localPoint([w, n], catalogue.origin);
              const [right, bottom] = localPoint([e, s], catalogue.origin);
              return (
                <image
                  key={layer.descriptor.layerId}
                  href={layer.url}
                  x={left}
                  y={-top}
                  width={right - left}
                  height={top - bottom}
                  preserveAspectRatio="none"
                  onError={() =>
                    setLayerError(
                      `Display image unavailable: ${layer.descriptor.layerId}`,
                    )
                  }
                />
              );
            })}
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
                fillOpacity={
                  feature.properties.kind === "boundary"
                    ? 0.1
                    : feature.properties.kind === "terminal"
                      ? 0.15
                      : feature.properties.kind === "berth"
                        ? 0.35
                        : 1
                }
                stroke={
                  selectedId === feature.id
                    ? "white"
                    : COLOURS[feature.properties.kind]
                }
                strokeWidth={selectedId === feature.id ? 12 : 3}
                onClick={() =>
                  onSelect(inspect(feature, catalogue, state, overlay))
                }
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
          JNPA · OSM context + authority geometry · horizontal accuracy
          unverified
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
          <label>
            <input
              type="checkbox"
              checked={illustrativeHeights}
              onChange={(e) => setIllustrativeHeights(e.target.checked)}
            />
            Illustrative building height: 6 m
          </label>
          <label>
            <input
              type="checkbox"
              checked={berthLabels}
              onChange={(e) => setBerthLabels(e.target.checked)}
            />
            Berth labels
          </label>
        </div>
        <RemoteLayers
          portCode={portCode}
          assetIds={assetIds}
          onChange={setDisplayLayers}
        />
        {layerError && (
          <div role="status">
            {layerError}. Geographic footprints remain available.
          </div>
        )}
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
