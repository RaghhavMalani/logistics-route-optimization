"""Public static geography and reviewed layer configuration; no simulation state."""
import hashlib
import json
import os
from pathlib import Path

from .geometry import validate_catalogue
from .layers import GeospatialLayer

ROOT = Path(__file__).resolve().parents[3]
VERSION = "authority-20261019-v2"


def is_public_geometry_request(method, path):
    """Exact public-data routes only; never exempt operational twin routes."""
    import re
    prefix=r"/api/public/port-geometry/[A-Za-z0-9]{4,5}"
    if method == "GET":
        return re.fullmatch(prefix+r"(?:/geometry|/layers|/reference-image)?",path) is not None
    return method == "POST" and re.fullmatch(prefix+r"/validate-layer",path) is not None


def port_directory(port_code):
    code = {"JNPT": "INNSA"}.get(port_code.upper(), port_code.upper())
    if code != "INNSA":
        raise FileNotFoundError("No reviewed geometry release for this port")
    return ROOT / "data" / "port_geometry" / code / VERSION


def geometry(port_code):
    directory = port_directory(port_code)
    data = (directory / "footprints.geojson").read_bytes()
    manifest = json.loads((directory / "manifest.json").read_text())
    if hashlib.sha256(data).hexdigest() != manifest["catalogueSha256"]:
        raise ValueError("Geometry catalogue integrity check failed")
    return validate_catalogue(json.loads(data))


def validate_layer(payload, port_code, known_ids=None):
    if not isinstance(payload, dict):
        raise ValueError("Expected one geospatial-layer/1 descriptor")
    try:
        layer = GeospatialLayer(**payload).to_dict()
    except (TypeError, KeyError) as exc:
        raise ValueError("Invalid descriptor fields: " + str(exc)) from exc
    if layer["portCode"] != port_code:
        raise ValueError("Layer portCode does not match requested port")
    if known_ids is not None and not set(layer["assetIds"]) <= set(known_ids):
        raise ValueError("Layer contains unknown geographic asset IDs")
    return layer


def layers(port_code):
    catalogue = geometry(port_code)
    code = catalogue["portCode"]
    # Integration-owner configuration only. Request inputs never become paths/URLs.
    configured = os.environ.get("PORTWATCH_GEOSPATIAL_LAYERS_FILE")
    path = Path(configured) if configured else port_directory(code) / "layers.json"
    if not path.exists():
        return {"schemaVersion": "geospatial-layer-catalogue/1", "portCode": code, "layers": [], "status": "unavailable", "reason": "No layer catalogue configured"}
    envelope = json.loads(path.read_text())
    if envelope.get("schemaVersion") != "geospatial-layer-catalogue/1" or envelope.get("portCode") != code or not isinstance(envelope.get("layers"), list):
        raise ValueError("Unsupported layer catalogue")
    known = [f["id"] for f in catalogue["features"]]
    result = [validate_layer(p, code, known) for p in envelope["layers"]]
    if len({p["layerId"] for p in result}) != len(result):
        raise ValueError("Duplicate layer IDs")
    return {"schemaVersion": "geospatial-layer-catalogue/1", "portCode": code, "layers": result, "status": "available"}


def manifest(port_code):
    catalogue = geometry(port_code)
    code = catalogue["portCode"]
    prefix = "/api/public/port-geometry/" + code
    return {"schemaVersion": "port-twin-geospatial-api/1", "portCode": code,
        "geometryVersion": catalogue["geometryVersion"], "horizontalCrs": "EPSG:4326",
        "bounds": [72.925, 18.9, 72.995, 18.985], "origin": catalogue["origin"],
        "axisMapping": {"x": "east", "y": "up", "z": "south"},
        "featureCount": len(catalogue["features"]),
        "geometryUrl": prefix + "/geometry", "layersUrl": prefix + "/layers",
        "validateLayerUrl": prefix + "/validate-layer", "layerSchemaVersion": "geospatial-layer/1",
        "deliveryMode": "pull-reviewed-catalogue", "accuracyStatus": "unverified",
        "operationalMappingStatus": "unmapped", "credentials": "Keep GEE credentials on provider backend"}
