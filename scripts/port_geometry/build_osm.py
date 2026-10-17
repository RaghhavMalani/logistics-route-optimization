#!/usr/bin/env python3
"""Reproducibly import a retained OSM API XML extract (no network required)."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.portwatch_os.geospatial.geometry import to_local, validate_catalogue


def build(raw, port, version, origin, received, url):
    root = ET.fromstring(raw)
    nodes = {n.attrib["id"]: [float(n.attrib["lon"]), float(n.attrib["lat"])] for n in root.findall("node")}
    features = []
    skipped = []
    for way in root.findall("way"):
        tags = {t.attrib["k"]: t.attrib["v"] for t in way.findall("tag")}
        kind = None
        if tags.get("man_made") == "pier": kind = "berth"
        elif tags.get("man_made") == "breakwater": kind = "breakwater"
        elif tags.get("natural") == "coastline": kind = "coastline"
        elif tags.get("natural") == "water": kind = "water"
        elif tags.get("building") and tags["building"] != "no": kind = "building"
        elif tags.get("landuse") in ("depot", "container_terminal"): kind = "yard"
        elif tags.get("industrial") == "port": kind = "boundary"
        elif tags.get("highway") in ("primary", "secondary", "tertiary", "service", "unclassified", "residential"): kind = "road"
        elif tags.get("railway") == "rail": kind = "rail"
        if not kind: continue
        refs = [n.attrib["ref"] for n in way.findall("nd")]
        if len(refs) < 2 or any(ref not in nodes for ref in refs):
            skipped.append({"id": way.attrib["id"], "reason": "incomplete way"})
            continue
        points = [nodes[ref] for ref in refs]
        polygon = refs[0] == refs[-1] and kind not in ("coastline", "road", "rail") and tags.get("area") != "no"
        fid = "osm-way-" + way.attrib["id"]
        features.append({"type": "Feature", "id": fid,
            "geometry": {"type": "Polygon" if polygon else "LineString", "coordinates": [points] if polygon else points},
            "properties": {"portCode": port, "terminalId": None, "kind": kind,
                "name": tags.get("name", kind.title() + " · OSM " + way.attrib["id"]),
                "geometryVersion": version, "sourceIds": ["osm-extract"],
                "sourceDate": None, "sourceModifiedAt": way.attrib.get("timestamp"),
                "horizontalQuality": "Unknown", "heightQuality": "Unknown",
                "heightM": None, "heightDatum": None, "valueKind": "derived",
                "osmVersion": way.attrib.get("version"), "sourceTags": tags}})
    digest = hashlib.sha256(raw).hexdigest()
    catalogue = {"type": "FeatureCollection", "schemaVersion": "port-geometry/1", "portCode": port,
        "geometryVersion": version, "horizontalCrs": "EPSG:4326", "verticalDatum": None,
        "origin": origin, "sceneAxes": {"x": "east", "y": "up", "z": "south"},
        "coverage": "OSM ways intersecting requested bounds; relations are not reconstructed. Not a complete port inventory.",
        "sources": [{"sourceId": "osm-extract", "sourceProductId": "OpenStreetMap API 0.6 map",
            "sourceReceiptId": digest, "url": url, "publisher": "OpenStreetMap contributors",
            "acquisitionFrom": None, "acquisitionThrough": None, "publicationDate": None,
            "firstAvailableAt": received, "originalSha256": digest, "horizontalCrs": "EPSG:4326",
            "groundResolutionM": None, "verticalDatum": None, "permittedUse": "ODbL 1.0",
            "attribution": "© OpenStreetMap contributors", "licenceUrl": "https://www.openstreetmap.org/copyright"}],
        "features": features, "operationalMappings": [], "skipped": skipped,
        "limitations": ["OSM edit timestamps are not imagery acquisition dates.", "Horizontal accuracy is unmeasured; elevations and heights are unknown.",
            "Pier tags do not establish berth names, dimensions, restrictions or operational identity.",
            "No occupancy, bathymetry, clearance or navigation authorization can be inferred."]}
    return validate_catalogue(catalogue)


def plan_svg(catalogue):
    """Local metric inspection drawing. Not a registration/accuracy proof."""
    rows = []
    all_points = []
    for feature in catalogue["features"]:
        geom = feature["geometry"]
        points = geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"]
        local = [(to_local(p, catalogue["origin"])[0], -to_local(p, catalogue["origin"])[1]) for p in points]
        all_points.extend(local)
        coords = " ".join("%.3f,%.3f" % p for p in local)
        colour = {"berth": "#f6c45b", "coastline": "#70bbd0", "building": "#aebcc7", "boundary": "#527466"}.get(feature["properties"]["kind"], "#748d9d")
        rows.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="3"/>' % (coords, colour))
    xs, ys = zip(*all_points)
    x, y = min(xs)-100, min(ys)-100
    w, h = max(xs)-x+100, max(ys)-y+100
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="%f %f %f %f"><rect x="%f" y="%f" width="%f" height="%f" fill="#061420"/>%s</svg>' % (x,y,w,h,x,y,w,h,"".join(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("--port", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--origin", nargs=2, type=float, required=True)
    parser.add_argument("--received", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-output", type=Path)
    args = parser.parse_args()
    raw = args.original.read_bytes()
    catalogue = build(raw, args.port, args.version, args.origin, args.received, args.url)
    if not catalogue["features"]:
        raise ValueError("No supported source geometry in extract")
    manifest_path = args.output / "manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text())["originalSha256"] != hashlib.sha256(raw).hexdigest():
        raise ValueError("Source changed: choose a new geometry version/output directory")
    args.output.mkdir(parents=True, exist_ok=True)
    originals = args.output / "originals"
    originals.mkdir(exist_ok=True)
    original = originals / (hashlib.sha256(raw).hexdigest() + ".osm")
    if original.exists() and original.read_bytes() != raw:
        raise ValueError("Immutable original collision")
    if not original.exists(): original.write_bytes(raw)
    data = (json.dumps(catalogue, indent=2, ensure_ascii=False) + "\n").encode()
    (args.output / "footprints.geojson").write_bytes(data)
    (args.output / "plan.svg").write_text(plan_svg(catalogue))
    manifest = {"schemaVersion": "port-geometry-manifest/1", "portCode": args.port,
        "geometryVersion": args.version, "original": str(original.relative_to(args.output)),
        "originalSha256": hashlib.sha256(raw).hexdigest(), "catalogueSha256": hashlib.sha256(data).hexdigest(),
        "featureCount": len(catalogue["features"]), "transform": "WGS84 ECEF -> ENU -> Three(east, up, -north)",
        "accuracyStatus": "unverified", "registrationStatus": "independent reference required"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if args.public_output:
        args.public_output.parent.mkdir(parents=True, exist_ok=True)
        args.public_output.write_bytes(data)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__": main()
