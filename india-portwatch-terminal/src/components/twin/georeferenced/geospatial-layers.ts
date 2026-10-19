import { API_BASE } from "@/services/api";

export interface GeospatialLayer {
  schemaVersion: "geospatial-layer/1";
  layerId: string;
  portCode: string;
  kind: "raster" | "vector";
  bounds: [number, number, number, number];
  horizontalCrs: "EPSG:4326";
  verticalDatum: string | null;
  acquisitionFrom: string | null;
  acquisitionThrough: string | null;
  firstAvailableAt: string | null;
  nativeResolutionM: number | null;
  resamplingMethod: string | null;
  noDataDefinition: string | null;
  sourceProduct: string | null;
  processingVersion: string | null;
  sourceHashes: string[];
  attribution: string | null;
  quality: string;
  displayResource: {
    url: string;
    valueKind: "display";
    expiresAt: string | null;
    format?: string;
  } | null;
  analyticalResource: {
    url: string;
    valueKind: string;
    expiresAt: string | null;
  } | null;
  assetIds: string[];
}
export interface LayerCatalogue {
  schemaVersion: "geospatial-layer-catalogue/1";
  portCode: string;
  layers: GeospatialLayer[];
}
export function layerCatalogueUrl(portCode: string): string {
  const configured = import.meta.env.VITE_PORTWATCH_GEOSPATIAL_LAYERS_URL as
    string | undefined;
  return configured
    ? configured.replace("{portCode}", encodeURIComponent(portCode))
    : `${API_BASE}/public/port-geometry/${encodeURIComponent(portCode)}/layers`;
}
export function resourceUrl(url: string, catalogueUrl: string): string {
  const resolved = new URL(url, new URL(catalogueUrl, window.location.href));
  if (
    resolved.username ||
    resolved.password ||
    !["http:", "https:"].includes(resolved.protocol)
  )
    throw new Error("Unsafe layer resource URL");
  if (
    resolved.protocol === "http:" &&
    !["127.0.0.1", "localhost", "[::1]"].includes(resolved.hostname)
  )
    throw new Error("External layers require HTTPS");
  return resolved.href;
}
export function parseLayers(
  value: unknown,
  portCode: string,
  assetIds: Set<string>,
): LayerCatalogue {
  const result = value as LayerCatalogue;
  if (
    !result ||
    result.schemaVersion !== "geospatial-layer-catalogue/1" ||
    result.portCode !== portCode ||
    !Array.isArray(result.layers)
  )
    throw new Error("Invalid layer catalogue");
  const ids = new Set<string>();
  for (const layer of result.layers) {
    if (
      !layer ||
      layer.schemaVersion !== "geospatial-layer/1" ||
      layer.portCode !== portCode ||
      typeof layer.layerId !== "string" ||
      ids.has(layer.layerId) ||
      !["raster", "vector"].includes(layer.kind) ||
      layer.horizontalCrs !== "EPSG:4326"
    )
      throw new Error("Invalid layer identity or CRS");
    ids.add(layer.layerId);
    const b = layer.bounds;
    if (
      !Array.isArray(b) ||
      b.length !== 4 ||
      !b.every(Number.isFinite) ||
      b[0] >= b[2] ||
      b[1] >= b[3] ||
      b[0] < -180 ||
      b[2] > 180 ||
      b[1] < -90 ||
      b[3] > 90
    )
      throw new Error("Invalid layer bounds");
    if (
      !Array.isArray(layer.assetIds) ||
      layer.assetIds.some((id) => !assetIds.has(id))
    )
      throw new Error("Unknown layer asset binding");
    if (
      layer.nativeResolutionM !== null &&
      (!Number.isFinite(layer.nativeResolutionM) ||
        layer.nativeResolutionM <= 0)
    )
      throw new Error("Invalid native resolution");
    if (
      !layer.displayResource ||
      layer.displayResource.valueKind !== "display" ||
      typeof layer.displayResource.url !== "string"
    )
      throw new Error("Layer needs a display resource");
    if (
      layer.displayResource.expiresAt !== null &&
      !Number.isFinite(Date.parse(layer.displayResource.expiresAt))
    )
      throw new Error("Invalid layer expiry");
    for (const key of [
      "acquisitionFrom",
      "acquisitionThrough",
      "firstAvailableAt",
    ] as const)
      if (layer[key] !== null && !Number.isFinite(Date.parse(layer[key])))
        throw new Error("Invalid layer date");
    if (
      layer.acquisitionFrom &&
      layer.acquisitionThrough &&
      Date.parse(layer.acquisitionFrom) > Date.parse(layer.acquisitionThrough)
    )
      throw new Error("Reversed acquisition interval");
  }
  return result;
}
export function layerExpired(layer: GeospatialLayer): boolean {
  return Boolean(
    layer.displayResource?.expiresAt &&
    Date.parse(layer.displayResource.expiresAt) <= Date.now(),
  );
}
