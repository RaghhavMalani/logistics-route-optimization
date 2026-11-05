import { useEffect, useRef, useState } from "react";
import type { CustomLayerInterface, Map as MapLibreMap } from "maplibre-gl";
import {
  GROVE_ZOOM,
  SCHEMATIC_ZOOM,
  inView,
  schematicAnchor,
  type PortMiniatureTarget,
  type RegisteredPort,
} from "./port-placement";

const SCHEMATIC_ID = "port-miniature";
const GROVE_ID = "port-groves";

function closestVisible(
  map: MapLibreMap,
  ports: RegisteredPort[],
): PortMiniatureTarget | null {
  const center = map.project(map.getCenter());
  let target: PortMiniatureTarget | null = null;
  let distance = Infinity;
  for (const port of ports) {
    if (!port.shore || !inView(map, port.center)) continue;
    const point = map.project(port.center);
    const next = (point.x - center.x) ** 2 + (point.y - center.y) ** 2;
    if (next < distance) {
      target = { ...port, shore: port.shore };
      distance = next;
    }
  }
  return target;
}

export function usePortMiniature(
  map: MapLibreMap | null,
  ports: RegisteredPort[],
  enabled: boolean,
) {
  const [active, setActive] = useState<PortMiniatureTarget | null>(null);
  const latest = useRef(ports);
  const refresh = useRef<(() => void) | null>(null);
  latest.current = ports;

  useEffect(() => {
    if (!map || !enabled) return;
    setActive(null);
    let disposed = false;
    const slots = new Map<string, PortMiniatureTarget>();
    const remove = (id: string) => {
      slots.delete(id);
      if (map.getLayer(id)) map.removeLayer(id);
      if (!disposed && id === SCHEMATIC_ID) setActive(null);
    };
    const sync = (
      id: string,
      target: PortMiniatureTarget | null,
      factory: () => Promise<
        (port: PortMiniatureTarget) => CustomLayerInterface
      >,
    ) => {
      if (slots.get(id)?.code === target?.code) return;
      remove(id);
      if (!target) return;
      slots.set(id, target);
      void factory()
        .then((createLayer) => {
          if (
            disposed ||
            slots.get(id) !== target ||
            document.hidden ||
            !map.getLayer("port-mark")
          ) {
            if (!disposed && slots.get(id) === target) slots.delete(id);
            return;
          }
          const zoom = map.getZoom();
          if (
            !inView(map, target.center) ||
            zoom < (id === GROVE_ID ? GROVE_ZOOM : SCHEMATIC_ZOOM)
          ) {
            slots.delete(id);
            return;
          }
          map.addLayer(createLayer(target), "port-mark");
          if (id === SCHEMATIC_ID) setActive(target);
        })
        .catch((error: unknown) => {
          if (disposed || slots.get(id) !== target) return;
          slots.delete(id);
          console.warn("[port landscape]", error);
        });
    };
    const update = () => {
      if (document.hidden || !map.getLayer("port-mark")) return;
      const zoom = map.getZoom();
      const port =
        zoom >= GROVE_ZOOM ? closestVisible(map, latest.current) : null;
      sync(GROVE_ID, port?.shore.groves.length ? port : null, () =>
        import("./port-grove-layer").then(
          ({ createPortGroves }) => createPortGroves,
        ),
      );
      const schematic =
        port &&
        zoom >= SCHEMATIC_ZOOM &&
        inView(map, schematicAnchor(port, zoom), 32)
          ? port
          : null;
      sync(SCHEMATIC_ID, schematic, () =>
        import("./port-miniature-layer").then(
          ({ createPortMiniature }) => createPortMiniature,
        ),
      );
    };
    const styleLoaded = () => {
      slots.clear();
      setActive(null);
      update();
    };
    // Wait for the camera to settle before constructing a new port scene.
    refresh.current = update;
    map.on("moveend", update);
    map.on("resize", update);
    map.on("style.load", styleLoaded);
    document.addEventListener("visibilitychange", update);
    update();
    return () => {
      disposed = true;
      refresh.current = null;
      map.off("moveend", update);
      map.off("resize", update);
      map.off("style.load", styleLoaded);
      document.removeEventListener("visibilitychange", update);
      remove(SCHEMATIC_ID);
      remove(GROVE_ID);
    };
  }, [enabled, map]);

  useEffect(() => refresh.current?.(), [ports]);
  return enabled ? active : null;
}
