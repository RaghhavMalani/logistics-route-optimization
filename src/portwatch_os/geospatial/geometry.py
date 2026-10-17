"""Port-local WGS84 tangent plane and strict interchange validation.

WGS84 geodetic -> ECEF -> local ENU. Three.js uses (east, up, -north).
Elevations are ellipsoid heights only when actually supplied as such. Rendering
an unknown elevation at zero is a display convention, never an observation.
"""
import math

SCHEMA_VERSION = "port-geometry/1"
QUALITY = {"Surveyed", "Authority plan", "Imagery-derived", "Illustrative", "Unknown"}
KINDS = {"boundary", "coastline", "water", "breakwater", "berth", "yard", "building", "gate", "road", "rail"}


def coordinate(lon, lat, height=0):
    values = (lon, lat, height)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError("Coordinates must be finite numbers")
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise ValueError("Invalid longitude/latitude")
    return values


def _ecef(lon, lat, height):
    coordinate(lon, lat, height)
    lon, lat = math.radians(lon), math.radians(lat)
    a, e2 = 6378137.0, 6.6943799901413165e-3
    n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    return ((n + height) * math.cos(lat) * math.cos(lon),
            (n + height) * math.cos(lat) * math.sin(lon),
            (n * (1 - e2) + height) * math.sin(lat))


def to_local(position, origin, crs="EPSG:4326"):
    if crs != "EPSG:4326":
        raise ValueError("Only EPSG:4326 interchange is supported; reproject explicitly")
    if len(position) not in (2, 3) or len(origin) not in (2, 3):
        raise ValueError("Expected longitude, latitude and optional ellipsoid height")
    p = _ecef(*position) if len(position) == 3 else _ecef(*position, 0)
    o = _ecef(*origin) if len(origin) == 3 else _ecef(*origin, 0)
    dx, dy, dz = (p[i] - o[i] for i in range(3))
    lon, lat = map(math.radians, origin[:2])
    return (-math.sin(lon) * dx + math.cos(lon) * dy,
            -math.sin(lat) * math.cos(lon) * dx - math.sin(lat) * math.sin(lon) * dy + math.cos(lat) * dz,
            math.cos(lat) * math.cos(lon) * dx + math.cos(lat) * math.sin(lon) * dy + math.sin(lat) * dz)


def to_three(enu):
    east, north, up = enu
    return east, up, -north


def validate_catalogue(catalogue):
    if catalogue.get("schemaVersion") != SCHEMA_VERSION or catalogue.get("horizontalCrs") != "EPSG:4326":
        raise ValueError("Unsupported schema or CRS")
    coordinate(*catalogue["origin"])
    if catalogue.get("type") != "FeatureCollection" or not catalogue.get("portCode"):
        raise ValueError("Expected a port FeatureCollection")
    source_ids = {s["sourceId"] for s in catalogue["sources"]}
    if len(source_ids) != len(catalogue["sources"]):
        raise ValueError("Duplicate source IDs")
    ids = set()
    for feature in catalogue["features"]:
        fid = feature["id"]
        props, geom = feature["properties"], feature["geometry"]
        if fid in ids or not isinstance(fid, str) or not fid:
            raise ValueError("Feature IDs must be unique nonempty strings")
        ids.add(fid)
        if props["portCode"] != catalogue["portCode"] or props["geometryVersion"] != catalogue["geometryVersion"]:
            raise ValueError("Feature port/version mismatch")
        if props["kind"] not in KINDS or props["horizontalQuality"] not in QUALITY or props["heightQuality"] not in QUALITY:
            raise ValueError("Unsupported kind or quality")
        if not props["sourceIds"] or not set(props["sourceIds"]) <= source_ids:
            raise ValueError("Missing source reference")
        for field in ("terminalId", "sourceDate", "heightM", "heightDatum", "valueKind"):
            if field not in props:
                raise ValueError("Missing feature metadata: " + field)
        if props["heightM"] is not None and (not math.isfinite(props["heightM"]) or props["heightM"] < 0):
            raise ValueError("Invalid height")
        shape, coords = geom["type"], geom["coordinates"]
        if shape == "Polygon":
            if len(coords) != 1 or len(coords[0]) < 4 or coords[0][0] != coords[0][-1]:
                raise ValueError("Polygon needs one closed exterior ring; holes require explicit support")
            points = coords[0]
        elif shape == "LineString" and len(coords) >= 2:
            points = coords
        elif shape == "Point":
            points = [coords]
        else:
            raise ValueError("Unsupported or empty geometry")
        for point in points:
            if len(point) != 2:
                raise ValueError("Footprints require 2D longitude/latitude")
            coordinate(*point)
            if math.hypot(*to_local(point, catalogue["origin"])[:2]) > 50000:
                raise ValueError("Feature outside 50 km local-frame limit")
    mapped = set()
    for mapping in catalogue["operationalMappings"]:
        if mapping["featureId"] not in ids or mapping["featureId"] in mapped:
            raise ValueError("Missing or duplicate mapping feature")
        mapped.add(mapping["featureId"])
        if mapping.get("operationalAssetId") is not None:
            if mapping.get("status") != "reviewed" or not mapping.get("reviewedBy") or not mapping.get("reviewedAt"):
                raise ValueError("Operational mappings require review")
    return catalogue


def accuracy_report(checks):
    """Independent hold-out points only; no claimed accuracy from fit points."""
    if not checks:
        return {"status": "unverified", "count": 0, "medianM": None, "p95M": None, "maximumM": None}
    if any(c.get("role") != "check" or not c.get("referenceSourceId") for c in checks):
        raise ValueError("Accuracy requires independent check points and reference IDs")
    errors = sorted(math.dist(c["modelEN"], c["referenceEN"]) for c in checks)
    if not all(math.isfinite(e) for e in errors):
        raise ValueError("Nonfinite check points")
    def quantile(q):
        index = (len(errors) - 1) * q
        lo, hi = math.floor(index), math.ceil(index)
        return errors[lo] + (errors[hi] - errors[lo]) * (index - lo)
    return {"status": "measured", "count": len(errors), "medianM": quantile(.5), "p95M": quantile(.95), "maximumM": errors[-1]}
