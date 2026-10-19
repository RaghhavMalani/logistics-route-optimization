# Port geometry and GEE integration

Current release: `authority-20261019-v2`, on
`feat/ananya-georeferenced-port-twins`.

- [GEE API URLs, payload and copyable teammate message](GEE_HANDOFF.md)
- [Current accuracy report and acceptance matrix](ACCURACY_AND_ACCEPTANCE.md)
- [Current verification results and screenshots](VALIDATION_V2.md)
- [Second-port feasibility](SECOND_PORT_FEASIBILITY.md)
- [Machine-readable evidence](evidence/source-inventory.json)

The current scene loads public API geometry, real authority terminal/berth labels,
and provider-neutral dated raster/vector display layers. It preserves the original
simulator and schematic reference. Reviewed operational-ID mappings are supported;
the real release explicitly remains unmapped because schematic IDs do not prove
physical identity. Unknown heights stay unknown. An optional, labelled 6 m building
extrusion illustrates volumes without changing source height metadata.

The local handoff manifest is
`http://127.0.0.1:8001/api/public/port-geometry/INNSA`.
The remote placeholder is
`https://<PORTWATCH_BACKEND_HOST>/api/public/port-geometry/INNSA`.
No remotely hosted URL is claimed until the host is agreed and the branch deployed.

Rebuild the current release offline from retained sources:

```sh
python scripts/port_geometry/build_authority_pilot.py \
  --sources data/port_geometry/INNSA/authority-20261019-v2/originals \
  --reference data/port_geometry/INNSA/authority-20261019-v2/reference
python scripts/port_geometry/reference_checks.py \
  --release data/port_geometry/INNSA/authority-20261019-v2 \
  --output docs/port_geometry/evidence
python -m unittest discover -s tests -p 'test_port_geometry_*.py' -v
```

`prepare_reference.py` can reproduce the display from the retained native image
window using optional dependencies in `scripts/port_geometry/requirements.txt`.
The image was rebuilt offline with the same display SHA-256. The optional
`gee_export_example.py` shows teammate-side export; it requires his authorized
GEE project and has not been run against a GEE account here.

**Full accuracy acceptance is still not met.** The source investigation found
semantic/date/dimension mismatches. The report retains those discrepancies and
unknown absolute errors; it does not turn a 10 m image or unreviewed point match
into a 5 m survey claim. See the current acceptance matrix for the precise
external evidence and identity decisions still needed.

---

## Historical v1 implementation record — October 17, 2026

The following describes the first release and is retained as a comparison record.
The current implementation and source coverage are described above.

Branch: `feat/ananya-georeferenced-port-twins`. Shared base:
`c854e60b4404c0763818f49a780bc2764c668450` from
`origin/feat/portwatch-restored-intelligence`, fetched October 17, 2026.

The attached briefs define Ananya's geometry assignment. Their shared feedback,
learning, authentication and deployment work belongs to other owners and is not
part of this change. No production configuration or simulation state was added.

## What is implemented

JNPA/INNSA has an opt-in geographic preview in the existing twin screen. Admin →
Port Twins → select JNPA → Geographic preview. The original schematic is the
default and remains available. Static source-backed footprints can be orbited,
panned (right drag), zoomed, framed, selected and inspected for provenance.
Layer controls and a north-up SVG plan also work without WebGL. Missing/corrupt
assets offer the schematic reference. Changing horizon does not rebuild geographic
geometry or change geographic selection. The simulator and decision comparison
remain in the original screen. Geographic occupancy is unavailable because no
real-to-simulator mapping has been reviewed; no array-order mapping is inferred.

3,226 retained OSM ways cover boundaries, piers, coastlines, water, breakwaters,
yards, buildings, roads and rail where those tags exist. Coverage is an extract,
not a complete inventory of the port. Surrounding urban features are retained
as context. Relations (including multipolygon areas), gates, equipment and
terminal names that lack reviewed source identity are not reconstructed.

All footprints have **Unknown** horizontal quality; heights, terrain and vertical
datum are unknown. Planar rendering uses display zero with small drawing-order
offsets, not measured elevations. No cranes, container stacks, cameras, draughts,
bathymetry or operational observations are invented.

## Source inventory and pilot comparison

| Source | Publisher / date | Use and limits |
| --- | --- | --- |
| [JNPA land-use plan](https://www.jnport.gov.in/uploads/content_manager/Report_on_land_Use_Plan_for_JNPA___August_2022__23_2022_10_06_17_04_09.pdf) | JNPA; title identifies August 2022 | Candidate authority reference for terminal identities. Not downloaded, digitized or registered in this pilot; permission and positional accuracy unknown. |
| [Chennai master plan](https://www.chennaiport.gov.in/api/static/default/inner_content/mp2022.pdf) | Chennai Port Authority; acquisition/publication dates not verified | Candidate second-port reference. Planned works must be distinguished from existing features. Not downloaded or registered. |
| [Retained OSM extract](https://api.openstreetmap.org/api/0.6/map?bbox=72.925,18.90,72.995,18.985) | OpenStreetMap contributors; first receipt October 17, 2026 (date precision) | ODbL 1.0. WGS84 coordinates, resolution/vertical datum/acquisition dates unknown. Edit timestamps are not image dates. |

JNPA remains the provisional pilot because it matches the existing advisory
workflow and the primary OSM API returned usable geometry. Chennai also has
authority references; there is no evidence yet that either port supports the
accuracy goal. The Overpass endpoints failed (HTTP 406/500); the primary OSM
endpoint succeeded. These failures do not imply an absence of mapped features.

Original XML is hash-addressed under `data/port_geometry/INNSA/osm-20261017-v1/originals`.
The manifest records SHA-256 of original and derived catalogue. Each feature
keeps its OSM way ID/version, source tags, source reference and modification time.
The catalogue source entry records publisher, URL, receipt, acquisition unknowns,
CRS, resolution unknown, licence and attribution. Originals are never rewritten
by the importer. No original source snapshot is fetched during a rebuild.

## Reproduce and validate

From the repository root, using Python 3.10 or newer:

```sh
python scripts/port_geometry/build_osm.py \
  data/port_geometry/INNSA/osm-20261017-v1/originals/7325ea85c8214158d09302fe76c1bebad428b2cdc64ea1f03d8326ee30600a20.osm \
  --port INNSA --version osm-20261017-v1 --origin 72.95 18.95 \
  --received 2026-10-17 \
  --url 'https://api.openstreetmap.org/api/0.6/map?bbox=72.925,18.90,72.995,18.985' \
  --output data/port_geometry/INNSA/osm-20261017-v1 \
  --public-output india-portwatch-terminal/public/port-geometry/INNSA/osm-20261017-v1.geojson
python -m unittest discover -s tests -p 'test_port_geometry_*.py' -v
cd india-portwatch-terminal
npm ci
npm run typecheck
npm run build
npx playwright test qa/tests/georeferenced.spec.ts --project=laptop-1366
```

The SVG plan is a metric inspection drawing of the imported coordinates. It is
**not** the required independent imagery registration proof. Inspecting an OSM
outline against the same OSM data cannot validate its positional accuracy.

## Coordinates, schema and provider boundary

Interchange is GeoJSON longitude/latitude, explicitly EPSG:4326. WGS84 ellipsoid
ECEF is rotated into local east/north/up at `[72.95, 18.95]`. Three.js maps east
to X, up to Y and north to negative Z. Footprints flatten to the tangent plane;
curvature/unknown elevation is not shown as terrain. The importer rejects
unsupported CRS, invalid/nonfinite coordinates, incomplete ways, unclosed rings,
unknown source IDs, duplicate IDs and features beyond 50 km. Holes/multipolygons
require a future explicit importer rather than silently filling them.

`port-geometry/1` separates horizontal and height quality, keeps nullable terminal
and source dates, stable OSM IDs, geometry version and value kind. Reviewed mapping
entries require a feature ID, operational asset ID, reviewer and review time.
`GeospatialLayer` defines the requested provider-neutral GEE boundary; the local
`layer.json` demonstrates a retained vector display resource. Analytical values
are separate from display RGB. No live GEE integration or credentials are needed.
Future adapters must handle expiry/unavailable states, preserve actual resolution
and clocks, and leave service credentials on the backend. Future camera metadata
can refer to stable feature IDs; camera coverage requires separate reviewed data.

The existing Three.js architecture is reused with on-demand rendering and
resource cleanup on navigation, plan mode and WebGL context loss. Metrics and
horizons do not recreate its scene. Cesium/3D Tiles adds no useful capability for
this bounded flat-footprint pilot; terrain/large-area needs can revisit that choice.

## Accuracy and remaining acceptance work

Design goals, set before validation: principal quay footprint median horizontal
error ≤5 m and p95 ≤10 m. **Achieved error is unknown.** Independent control/check
points: 0; median, p95, maximum, berth-length/orientation differences and height
error: null. No checked asset set or coverage percentage is claimed.

Remaining to satisfy the full brief:

- Retain permitted dated imagery or surveyed/authority GIS with documented accuracy.
- Review terminal/berth names and coverage; register a 2D overlay using fit points
  separate from at least ten suitable distributed independent check points.
- Record per-point/edge errors, reference uncertainty, spatial distribution,
  berth dimensions and any separately supported elevations.
- Review operational ID mappings against the existing simulator. Add mapped overlays
  only after identity is supported. Preserve unmapped features as unavailable.
- Add supported 3D heights/terrain and terminal labels where evidence permits.
- Record interaction performance on a named desktop/GPU/browser and verify ≥30 FPS;
  no FPS acceptance claim is made from software/build tests.
- Complete a second-port source/permission assessment and all four-role regression
  checks before integration. The integration owner handles PR integration/publication.

This branch delivers the reusable geometry path and a real geographic footprint
preview. It does not claim completion of the measured-accuracy port twin.
