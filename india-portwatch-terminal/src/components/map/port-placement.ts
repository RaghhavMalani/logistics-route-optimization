import type { Map as MapLibreMap } from "maplibre-gl";
import harbourContext from "@/assets/geo/region-land-detail.generated.json";
import { destination } from "@/lib/maritime/geo";

export const GROVE_ZOOM = 8;
export const SCHEMATIC_ZOOM = 11;

export interface RegisteredPort {
  code: string;
  name: string;
  center: [number, number];
  shore?: { bearing: number; clearance: number; groves: number[][] };
}

export type PortMiniatureTarget = RegisteredPort &
  Required<Pick<RegisteredPort, "shore">>;

export function registeredPorts(
  ports: GeoJSON.FeatureCollection | undefined,
): RegisteredPort[] {
  return (ports?.features ?? []).flatMap(({ properties, geometry }) => {
    if (
      geometry.type !== "Point" ||
      typeof properties?.code !== "string" ||
      typeof properties.name !== "string"
    )
      return [];
    const shore =
      harbourContext.ports[
        properties.code as keyof typeof harbourContext.ports
      ];
    const [lon, lat] = geometry.coordinates;
    return [
      {
        code: properties.code,
        name: properties.name,
        center: [lon, lat],
        shore,
      },
    ];
  });
}

export function schematicScale(zoom: number) {
  return 68 * 2 ** (-0.66 * (zoom - SCHEMATIC_ZOOM));
}

export function schematicAnchor(port: PortMiniatureTarget, zoom: number) {
  return destination(
    port.center,
    port.shore.bearing,
    (port.shore.clearance + 44 * schematicScale(zoom)) / 1000,
  );
}

export function inView(
  map: MapLibreMap,
  coordinates: [number, number],
  margin = 0,
) {
  const { x, y } = map.project(coordinates);
  const canvas = map.getCanvas();
  return (
    x >= -margin &&
    x <= canvas.clientWidth + margin &&
    y >= -margin &&
    y <= canvas.clientHeight + margin
  );
}

export function portSeed(code: string) {
  return [...code].reduce(
    (value, letter) => value * 31 + letter.charCodeAt(0),
    0,
  );
}
