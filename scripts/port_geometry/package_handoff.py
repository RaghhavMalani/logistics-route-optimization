"""Build a minimal, checksummed API handoff; excludes private/runtime state.

Run from repository root: python -m scripts.port_geometry.package_handoff OUTPUT.zip
The archive is for integration review, not a grant of source redistribution rights.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from src.portwatch_os.geospatial.catalogue_service import ROOT, geometry, layers, port_directory


def package(output):
    if os.environ.get("PORTWATCH_GEOSPATIAL_LAYERS_FILE"):
        raise ValueError("Unset PORTWATCH_GEOSPATIAL_LAYERS_FILE to package the retained release")
    catalogue = geometry("INNSA")
    layers("INNSA")  # Validate descriptors and asset bindings before packaging.
    release = port_directory("INNSA")
    image = release / "reference/reference.png"
    receipt = json.loads((release / "reference/receipt.json").read_text())
    if hashlib.sha256(image.read_bytes()).hexdigest() != receipt["displaySha256"]:
        raise ValueError("Reference image integrity check failed")
    # Explicit allowlist: no recursive repository copy, secrets or private state.
    names = [
        "backend/geospatial_preview.py", "backend/app/routes/port_geometry.py",
        "src/portwatch_os/geospatial/catalogue_service.py",
        "src/portwatch_os/geospatial/geometry.py", "src/portwatch_os/geospatial/layers.py",
        "docs/port_geometry/GEE_HANDOFF.md", "docs/port_geometry/ACCURACY_AND_ACCEPTANCE.md",
    ]
    names += [str((release / name).relative_to(ROOT)) for name in (
        "footprints.geojson", "manifest.json", "operational-mappings.json", "layers.json",
        "reference/reference.png", "reference/receipt.json")]
    files = {name: (ROOT / name).read_bytes() for name in names}
    files["requirements.txt"] = b"fastapi>=0.115,<1\nuvicorn>=0.30,<1\n"
    files["START_HERE.txt"] = (
        "Review source reuse permissions before public hosting.\n"
        "Create a Python 3.10+ virtual environment; pip install -r requirements.txt\n"
        "Set PORTWATCH_GEOSPATIAL_CORS_ORIGINS to the approved frontend origin.\n"
        "Run: python -m uvicorn backend.geospatial_preview:app --host 0.0.0.0 --port 8001\n"
        "GET /api/public/port-geometry/INNSA on your chosen host.\n"
        "Use an HTTPS reverse proxy/hosting service for remote integration.\n"
        "No host, GEE credentials, operational mappings or accuracy certification are supplied.\n"
        "See docs/port_geometry/GEE_HANDOFF.md for the payload and configuration.\n"
    ).encode()
    files["SHA256SUMS.json"] = (json.dumps({name: hashlib.sha256(data).hexdigest()
        for name, data in sorted(files.items())}, indent=2) + "\n").encode()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids overwriting an earlier handoff.
    with ZipFile(output, "x", ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    return {"archive": str(output.resolve()), "featureCount": len(catalogue["features"]),
            "fileCount": len(files), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(package(parser.parse_args().output), indent=2))
