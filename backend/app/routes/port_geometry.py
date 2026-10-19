"""Public, read-only static geography and dry-run GEE descriptor validation."""
from typing import Any, Dict
from fastapi import APIRouter, HTTPException

router = APIRouter()


def _geospatial_read(operation, port_code):
    try:
        return operation(port_code)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=503, detail="Geospatial release unavailable: " + str(exc)) from exc


@router.get("/public/port-geometry/{port_code}")
def geographic_manifest(port_code: str):
    from src.portwatch_os.geospatial.catalogue_service import manifest
    return _geospatial_read(manifest, port_code)


@router.get("/public/port-geometry/{port_code}/geometry")
def geographic_geometry(port_code: str):
    from src.portwatch_os.geospatial.catalogue_service import geometry
    return _geospatial_read(geometry, port_code)


@router.get("/public/port-geometry/{port_code}/layers")
def geographic_layers(port_code: str):
    from src.portwatch_os.geospatial.catalogue_service import layers
    return _geospatial_read(layers, port_code)


@router.get("/public/port-geometry/{port_code}/reference-image")
def geographic_reference_image(port_code: str):
    import hashlib
    import json
    from fastapi.responses import FileResponse
    from src.portwatch_os.geospatial.catalogue_service import port_directory
    directory = _geospatial_read(port_directory, port_code)
    path = directory / "reference" / "reference.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Reference image unavailable")
    receipt=json.loads((directory/"reference"/"receipt.json").read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=receipt["displaySha256"]:
        raise HTTPException(status_code=503,detail="Reference image integrity check failed")
    return FileResponse(path, media_type="image/png")


@router.post("/public/port-geometry/{port_code}/validate-layer")
def geographic_validate_layer(port_code: str, payload: Dict[str, Any]):
    from src.portwatch_os.geospatial.catalogue_service import geometry, validate_layer
    catalogue = _geospatial_read(geometry, port_code)
    try:
        layer = validate_layer(payload, catalogue["portCode"], [f["id"] for f in catalogue["features"]])
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"valid": True, "persisted": False, "layer": layer,
            "nextStep": "Publish in the reviewed layer catalogue; this endpoint validates without writing."}
