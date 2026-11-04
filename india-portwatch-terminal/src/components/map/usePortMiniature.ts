import { useEffect, useRef, useState } from "react";
import { LngLat, type Map as MapLibreMap } from "maplibre-gl";

const LAYER_ID = "port-miniature";
const DETAIL_ZOOM = 11;

export interface PortMiniatureTarget {
  code: string;
  name: string;
  center: [number, number];
}

export function registeredPorts(
  ports: GeoJSON.FeatureCollection | undefined,
): PortMiniatureTarget[] {
  return (ports?.features ?? []).flatMap(({ properties, geometry }) => {
    if (
      geometry.type !== "Point" ||
      typeof properties?.code !== "string" ||
      typeof properties.name !== "string"
    )
      return [];
    const [lon, lat] = geometry.coordinates;
    return [
      { code: properties.code, name: properties.name, center: [lon, lat] },
    ];
  });
}

export function usePortMiniature(
  map: MapLibreMap | null,
  ports: PortMiniatureTarget[],
  enabled: boolean,
) {
  const [active, setActive] = useState<PortMiniatureTarget | null>(null);
  const latest = useRef(ports);
  const updateRef = useRef<(() => void) | null>(null);
  latest.current = ports;

  useEffect(() => {
    if (!map || !enabled) return;
    setActive(null);
    let removed = false;
    let requested: PortMiniatureTarget | null = null;
    let visible: PortMiniatureTarget | null = null;
    const removeLayer = () => {
      if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID);
      visible = null;
      if (!removed) setActive(null);
    };
    const update = () => {
      const zoom = map.getZoom();
      let target: PortMiniatureTarget | null = null;
      if (zoom >= DETAIL_ZOOM) {
        const center = map.getCenter();
        let distance = Math.max(1500, 9000 / 2 ** (zoom - DETAIL_ZOOM));
        for (const port of latest.current) {
          const next = center.distanceTo(LngLat.convert(port.center));
          if (next < distance) {
            target = port;
            distance = next;
          }
        }
      }
      if (
        target?.code === requested?.code &&
        (!target || requested !== visible || map.getLayer(LAYER_ID))
      )
        return;
      requested = target;
      removeLayer();
      if (!target) return;
      void import("./port-miniature-layer")
        .then(({ createPortMiniature }) => {
          if (removed || requested !== target || map.getZoom() < DETAIL_ZOOM)
            return;
          map.addLayer(createPortMiniature(target), "port-mark");
          visible = target;
          setActive(target);
        })
        .catch((error: unknown) => {
          if (removed || requested !== target) return;
          requested = null;
          console.warn("[port miniature]", error);
        });
    };
    updateRef.current = update;
    map.on("moveend", update);
    map.on("style.load", update);
    update();
    return () => {
      removed = true;
      updateRef.current = null;
      map.off("moveend", update);
      map.off("style.load", update);
      removeLayer();
    };
  }, [enabled, map]);

  useEffect(() => updateRef.current?.(), [ports]);

  return enabled ? active : null;
}
