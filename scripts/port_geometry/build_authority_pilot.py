"""Build the v2 JNPA release from retained source files, without network access."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.portwatch_os.geospatial.geometry import validate_catalogue

VERSION = "authority-20261019-v2"


def build(source_dir, reference_dir, output, public):
    original = ROOT / "data/port_geometry/INNSA/osm-20261017-v1/footprints.geojson"
    catalogue = json.loads(original.read_text())
    catalogue["geometryVersion"] = VERSION
    catalogue["displayBounds"] = json.loads((reference_dir/"receipt.json").read_text())["bounds"]
    for feature in catalogue["features"]: feature["properties"]["geometryVersion"] = VERSION
    output.mkdir(parents=True, exist_ok=True)
    originals = output / "originals"
    originals.mkdir(exist_ok=True)
    mapping = []
    source_index = {}
    for kind, filename, layer in (("berth", "jnpa-authority-berths.geojson", 6), ("terminal", "jnpa-authority-terminals.geojson", 5)):
        source = source_dir / filename
        if not source.exists():
            index = json.loads((source_dir/"index.json").read_text())
            source = source_dir/index[filename]
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        retained = originals / (digest + ".geojson")
        source_index[filename] = retained.name
        if retained.exists() and retained.read_bytes() != raw: raise ValueError("Original collision")
        if not retained.exists(): retained.write_bytes(raw)
        source_id = "jnpa-gis-" + str(layer)
        catalogue["sources"].append({"sourceId": source_id, "sourceProductId": "JNPA Port GIS layer " + str(layer),
            "sourceReceiptId": digest, "originalSha256": digest, "publisher": "Jawaharlal Nehru Port Authority",
            "url": "https://gis.jnpa.in/server/rest/services/JNPA/Port/MapServer/" + str(layer) + "/query?where=1%3D1&outFields=*&outSR=4326&f=geojson",
            "firstAvailableAt": "2026-10-19", "acquisitionFrom": None, "acquisitionThrough": None, "publicationDate": None,
            "horizontalCrs": "EPSG:4326", "originalServiceCrs": "EPSG:32643", "groundResolutionM": None, "verticalDatum": None,
            "permittedUse": "Anonymous public query; redistribution licence not specified by service", "attribution": "JNPA public GIS; positional accuracy and survey epoch unpublished"})
        for item in json.loads(raw)["features"]:
            props = item["properties"]
            parent = "jnpa-" + kind + "-" + str(props["OBJECTID"])
            polygons = [item["geometry"]["coordinates"]] if item["geometry"]["type"] == "Polygon" else item["geometry"]["coordinates"]
            for index, polygon in enumerate(polygons):
                if len(polygon) != 1: raise ValueError("Authority polygon holes require explicit support")
                fid = parent if len(polygons) == 1 else parent + "-part" + str(index)
                catalogue["features"].append({"type": "Feature", "id": fid, "geometry": {"type": "Polygon", "coordinates": polygon},
                    "properties": {"portCode": "INNSA", "terminalId": parent if kind == "terminal" else props.get("terminal"), "kind": kind,
                        "name": props["NAME"], "geometryVersion": VERSION, "sourceIds": [source_id], "sourceDate": None,
                        "sourceModifiedAt": None, "horizontalQuality": "Authority plan", "heightQuality": "Unknown", "heightM": None,
                        "heightDatum": None, "valueKind": "derived", "publishedLengthM": props.get("length"),
                        "dimensionSourceDate": None, "dimensionUse": "Undated GIS reference attribute; not navigation clearance"}})
                if kind == "berth": mapping.append({"featureId": fid, "operationalAssetId": None, "status": "reviewed-unmapped",
                    "reviewedBy": "Codex code/source identity audit", "reviewedAt": "2026-10-19", "reason": "Simulator B1..Bn are generated schematic assets; counts or array order cannot establish named berth identity."})
    catalogue["operationalMappings"] = mapping
    (originals/"index.json").write_text(json.dumps(source_index,indent=2)+"\n")
    catalogue["coverage"] = "OSM context plus 13 authority berth polygons and 10 authority terminals (multipart terminal pieces retain parent IDs)."
    catalogue["limitations"].append("Authority GIS has no published survey epoch, positional accuracy or explicit redistribution licence. No GIS depth/draught values are imported.")
    validate_catalogue(catalogue)
    data = (json.dumps(catalogue,indent=2,ensure_ascii=False)+"\n").encode()
    (output/"footprints.geojson").write_bytes(data)
    reference = output/"reference"; reference.mkdir(exist_ok=True)
    for name in ("stac-item.json", "receipt.json", "original-window.tif", "reference.png"):
        if (reference_dir/name).resolve() != (reference/name).resolve(): shutil.copyfile(reference_dir/name,reference/name)
    receipt=json.loads((reference/"receipt.json").read_text())
    layer={"schemaVersion":"geospatial-layer/1","layerId":"innsa-sentinel2-20260322","portCode":"INNSA","kind":"raster",
        "bounds":receipt["bounds"],"horizontalCrs":"EPSG:4326","verticalDatum":None,"acquisitionFrom":receipt["acquisitionAt"],
        "acquisitionThrough":receipt["acquisitionAt"],"firstAvailableAt":"2026-10-19","nativeResolutionM":10,"resamplingMethod":"nearest",
        "noDataDefinition":"Black pixels may be source no-data; no occupancy or depth inference.","sourceProduct":receipt["itemId"],
        "processingVersion":receipt["processingVersion"],"sourceHashes":[receipt["sourceSubsetSha256"],receipt["originalMetadataSha256"]],
        "attribution":"Contains modified Copernicus Sentinel data (2026), distributed via Element 84 Earth Search.","quality":"Imagery-derived",
        "displayResource":{"url":"/api/public/port-geometry/INNSA/reference-image","valueKind":"display","format":"image/png","expiresAt":None},
        "analyticalResource":None,"assetIds":[]}
    (output/"layers.json").write_text(json.dumps({"schemaVersion":"geospatial-layer-catalogue/1","portCode":"INNSA","layers":[layer]},indent=2)+"\n")
    (output/"operational-mappings.json").write_text(json.dumps(mapping,indent=2)+"\n")
    (output/"manifest.json").write_text(json.dumps({"schemaVersion":"port-geometry-manifest/1","portCode":"INNSA","geometryVersion":VERSION,
        "catalogueSha256":hashlib.sha256(data).hexdigest(),"baseCatalogueSha256":hashlib.sha256(original.read_bytes()).hexdigest(),
        "featureCount":len(catalogue["features"]),"accuracyStatus":"reference comparisons; absolute accuracy unverified","sourceReceiptHashes":[s["originalSha256"] for s in catalogue["sources"]]},indent=2)+"\n")
    public.mkdir(parents=True,exist_ok=True)
    (public/"catalogue.geojson").write_bytes(data)
    shutil.copyfile(reference/"reference.png",public/"reference.png")
    print("Built",len(catalogue["features"]),"features",len(mapping),"reviewed-unmapped berth identities")


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources",type=Path,required=True)
    p.add_argument("--reference",type=Path,required=True)
    args=p.parse_args()
    build(args.sources,args.reference,ROOT/"data/port_geometry/INNSA"/VERSION,ROOT/"india-portwatch-terminal/public/port-geometry/INNSA")
