export type GeometryKind =
  | "boundary"
  | "terminal"
  | "coastline"
  | "water"
  | "breakwater"
  | "berth"
  | "yard"
  | "building"
  | "gate"
  | "road"
  | "rail";
export type Position = [number, number];
export interface GeographicFeature {
  type: "Feature";
  id: string;
  geometry:
    | { type: "Polygon"; coordinates: Position[][] }
    | { type: "LineString"; coordinates: Position[] };
  properties: {
    portCode: string;
    terminalId: string | null;
    kind: GeometryKind;
    name: string;
    geometryVersion: string;
    sourceIds: string[];
    sourceDate: string | null;
    sourceModifiedAt: string | null;
    horizontalQuality: string;
    heightQuality: string;
    heightM: number | null;
    heightDatum: string | null;
    valueKind: string;
    publishedLengthM?: number | null;
  };
}
export interface Catalogue {
  type: "FeatureCollection";
  schemaVersion: "port-geometry/1";
  portCode: string;
  geometryVersion: string;
  horizontalCrs: "EPSG:4326";
  origin: Position;
  displayBounds?: [number, number, number, number];
  features: GeographicFeature[];
  sources: {
    sourceId: string;
    attribution: string;
    firstAvailableAt: string;
    originalSha256: string;
  }[];
  operationalMappings: {
    featureId: string;
    operationalAssetId: string | null;
    status: string;
    reviewedBy?: string;
    reviewedAt?: string;
  }[];
  limitations: string[];
}
function ecef([lon, lat]: Position): [number, number, number] {
  const l = (lon * Math.PI) / 180,
    p = (lat * Math.PI) / 180;
  const e2 = 6.6943799901413165e-3;
  const n = 6378137 / Math.sqrt(1 - e2 * Math.sin(p) ** 2);
  return [
    n * Math.cos(p) * Math.cos(l),
    n * Math.cos(p) * Math.sin(l),
    n * (1 - e2) * Math.sin(p),
  ];
}
/** WGS84 ECEF -> ENU; flattened footprint at unknown elevation, in metres. */
export function localPoint(
  point: Position,
  origin: Position,
): [number, number] {
  const a = ecef(point),
    b = ecef(origin),
    [x, y, z] = a.map((v, i) => v - b[i]);
  const l = (origin[0] * Math.PI) / 180,
    p = (origin[1] * Math.PI) / 180;
  return [
    -Math.sin(l) * x + Math.cos(l) * y,
    -Math.sin(p) * Math.cos(l) * x -
      Math.sin(p) * Math.sin(l) * y +
      Math.cos(p) * z,
  ];
}
export function ring(feature: GeographicFeature): Position[] {
  return feature.geometry.type === "Polygon"
    ? feature.geometry.coordinates[0]
    : feature.geometry.coordinates;
}
export function parseCatalogue(value: unknown, portCode: string): Catalogue {
  const c = value as Catalogue;
  const validPoint = (p: Position) =>
    Array.isArray(p) &&
    p.length === 2 &&
    p.every(Number.isFinite) &&
    Math.abs(p[0]) <= 180 &&
    Math.abs(p[1]) <= 90;
  if (
    !c ||
    c.type !== "FeatureCollection" ||
    c.schemaVersion !== "port-geometry/1" ||
    c.portCode !== portCode ||
    c.horizontalCrs !== "EPSG:4326" ||
    !validPoint(c.origin) ||
    !Array.isArray(c.features) ||
    !c.features.length ||
    !Array.isArray(c.sources) ||
    !Array.isArray(c.operationalMappings)
  )
    throw new Error("Unsupported geometry catalogue");
  const ids = new Set<string>();
  if (
    c.displayBounds &&
    (c.displayBounds.length !== 4 ||
      !c.displayBounds.every(Number.isFinite) ||
      !validPoint([c.displayBounds[0], c.displayBounds[1]]) ||
      !validPoint([c.displayBounds[2], c.displayBounds[3]]) ||
      c.displayBounds[0] >= c.displayBounds[2] ||
      c.displayBounds[1] >= c.displayBounds[3])
  )
    throw new Error("Invalid display bounds");
  for (const f of c.features) {
    if (
      !f ||
      typeof f.id !== "string" ||
      ids.has(f.id) ||
      !f.properties ||
      ![
        "boundary",
        "terminal",
        "coastline",
        "water",
        "breakwater",
        "berth",
        "yard",
        "building",
        "gate",
        "road",
        "rail",
      ].includes(f.properties.kind) ||
      ![
        "Surveyed",
        "Authority plan",
        "Imagery-derived",
        "Illustrative",
        "Unknown",
      ].includes(f.properties.horizontalQuality) ||
      f.properties.portCode !== portCode ||
      f.properties.geometryVersion !== c.geometryVersion ||
      (f.properties.heightM !== null &&
        (!Number.isFinite(f.properties.heightM) ||
          f.properties.heightM < 0 ||
          f.properties.heightM > 1000)) ||
      !["Polygon", "LineString"].includes(f.geometry?.type)
    )
      throw new Error("Invalid geometry feature");
    ids.add(f.id);
    const points = ring(f);
    if (
      !Array.isArray(points) ||
      points.length < (f.geometry.type === "Polygon" ? 4 : 2) ||
      !points.every(validPoint)
    )
      throw new Error("Invalid feature coordinates");
    if (
      f.geometry.type === "Polygon" &&
      JSON.stringify(points[0]) !== JSON.stringify(points[points.length - 1])
    )
      throw new Error("Unclosed polygon");
    if (f.geometry.type === "Polygon" && f.geometry.coordinates.length !== 1)
      throw new Error("Polygon holes require explicit support");
    if (points.some((p) => Math.hypot(...localPoint(p, c.origin)) > 50000))
      throw new Error("Geometry outside local frame");
    if (
      !Array.isArray(f.properties.sourceIds) ||
      !f.properties.sourceIds.length ||
      f.properties.sourceIds.some(
        (id) => !c.sources.some((s) => s.sourceId === id),
      )
    )
      throw new Error("Missing source reference");
  }
  const mapped = new Set<string>();
  for (const m of c.operationalMappings) {
    if (
      !ids.has(m.featureId) ||
      mapped.has(m.featureId) ||
      (m.operationalAssetId &&
        (m.status !== "reviewed" || !m.reviewedBy || !m.reviewedAt))
    )
      throw new Error("Unreviewed operational mapping");
    mapped.add(m.featureId);
  }
  return c;
}
