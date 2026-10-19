# GEE teammate handoff

The working local manifest URL is:

`http://127.0.0.1:8001/api/public/port-geometry/INNSA`

This is a **local development URL**, not a remotely hosted endpoint. For a remote
teammate replace the origin with the deployed backend origin after the integration
owner merges/deploys this branch. Existing production does not yet have these
routes. Do not send localhost as though another computer can access it.

Until hosting is decided, share this placeholder:

`https://<PORTWATCH_BACKEND_HOST>/api/public/port-geometry/INNSA`

Copyable message to your teammate:

> My geometry API contract is ready. Which backend/domain should host
> `https://<PORTWATCH_BACKEND_HOST>/api/public/port-geometry/INNSA`? Also send me
> the HTTPS URL where your backend will serve `layers.json` and the exported
> PNG/GeoJSON resources, and confirm the PortWatch frontend origin allowed by
> your CORS settings. I will configure my layer loader to pull that catalogue.

His catalogue placeholder is
`https://<GEE_PROVIDER_HOST>/port-layers/{portCode}/layers.json`.

## API contract

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/public/port-geometry/INNSA` | Handshake: bounds, CRS, local origin, version and links |
| GET | `/api/public/port-geometry/INNSA/geometry` | Stable geographic feature IDs and GeoJSON geometry |
| GET | `/api/public/port-geometry/INNSA/layers` | `geospatial-layer-catalogue/1` display layers |
| GET | `/api/public/port-geometry/INNSA/reference-image` | Retained dated Sentinel-2 PNG example |
| POST | `/api/public/port-geometry/INNSA/validate-layer` | Validate one descriptor; returns `persisted: false` |
| GET | `/docs` | OpenAPI explorer on the standalone development service |

The public routes contain static geographic evidence only, never visitor/session
or operational state. No GEE credentials are required by these routes. Validation
is a dry run; it is deliberately not an unauthenticated upload endpoint.

Run from this branch's worktree with the project Python environment:

```sh
python -m uvicorn backend.geospatial_preview:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/api/public/port-geometry/INNSA
```

The full application mounts the same routes through its existing port-twin router.
Backend packaging must retain `data/port_geometry/INNSA/authority-20261019-v2`
alongside the Python source; the original v1 sources remain necessary for rebuilds.
The standalone service avoids starting collectors, simulator state or private
accounts. Its optional CORS allowlist is `PORTWATCH_GEOSPATIAL_CORS_ORIGINS`.

## How his GEE output reaches the scene

1. Fetch the manifest. Use `bounds` as `[west, south, east, north]` in EPSG:4326.
2. Export a north-up PNG with exactly that geographic footprint. Keep the real
   source acquisition date, native resolution, processing and attribution.
3. Retain the export and receipt. Host the PNG and `layers.json` on an approved
   HTTPS backend/static host with CORS for the PortWatch frontend.
4. POST each descriptor to `validate-layer` to catch schema/identity mistakes.
5. Set the frontend's `VITE_PORTWATCH_GEOSPATIAL_LAYERS_URL` to his catalogue URL.
   A `{portCode}` placeholder is supported. Rebuild the frontend after changing
   this Vite setting. Alternatively the integration owner can set the backend's
   `PORTWATCH_GEOSPATIAL_LAYERS_FILE` to a reviewed local catalogue file and use
   the default `/layers` route.
6. Open JNPA → Geographic preview. The layer control shows acquisition date,
   native resolution, attribution and expiry. Failure/expiry leaves static
   geography usable. Refresh layers obtains renewed signed URLs.

Example envelope (send the inner descriptor, not the envelope, to the validator):

```json
{
  "schemaVersion": "geospatial-layer-catalogue/1",
  "portCode": "INNSA",
  "layers": [{
    "schemaVersion": "geospatial-layer/1",
    "layerId": "innsa-gee-example",
    "portCode": "INNSA",
    "kind": "raster",
    "bounds": [72.925, 18.9, 72.995, 18.985],
    "horizontalCrs": "EPSG:4326",
    "verticalDatum": null,
    "acquisitionFrom": null,
    "acquisitionThrough": null,
    "firstAvailableAt": null,
    "nativeResolutionM": null,
    "resamplingMethod": null,
    "noDataDefinition": null,
    "sourceProduct": null,
    "processingVersion": "your-export-v1",
    "sourceHashes": [],
    "attribution": null,
    "quality": "Unknown",
    "displayResource": {
      "url": "https://YOUR_HOST/innsa/display.png",
      "valueKind": "display",
      "format": "image/png",
      "expiresAt": null
    },
    "analyticalResource": null,
    "assetIds": []
  }]
}
```

Replace placeholders and unknown metadata with actual values when known; never
invent acquisition dates or higher resolution. A whole-port image can use empty
`assetIds`. Asset-linked products use IDs returned by `/geometry`.

Raster display supports PNG/JPEG through the browser image loader. Vector display
supports GeoJSON FeatureCollections with 2D EPSG:4326 Polygon/LineString geometry;
holes, multipolygons, points and raw GeoTIFF/XYZ tile endpoints need preprocessing
or another renderer adapter. The renderer never treats RGB as analytical values.
SVG fallback shows raster layers with a local planar approximation; metric
assessment must use the native reference coordinates, not screenshot pixels.

See `scripts/port_geometry/gee_export_example.py` for a teammate-side example
using authorized GEE access. It reads this manifest, selects a dated Sentinel-2
image and writes retained PNG/metadata/catalogue files. It has not been executed
against a GEE account here. Service-account credentials stay with his backend.
The example follows the official [thumbnail export API](https://developers.google.com/earth-engine/apidocs/ee-image-getthumburl)
and [harmonized Sentinel-2 dataset](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED).

## Geometry status your teammate must retain

Release `authority-20261019-v2` contains OSM context, 13 authority berth polygons,
and 10 authority terminals (multipart terminals have stable part IDs). Source
epochs/accuracy differ and authority GIS redistribution terms are unspecified.
The retained Sentinel-2 example is from March 22, 2026 at 10 m native resolution.
It does not support a 5 m survey-accuracy claim or current occupancy.

The operational mapping audit explicitly leaves all real berths unmapped:
simulator `B1..Bn` IDs are schematic and do not prove physical identity. A future
reviewed mapping can enable simulated overlays without changing geographic IDs.
GEE integration does not need those operational mappings to display imagery.
