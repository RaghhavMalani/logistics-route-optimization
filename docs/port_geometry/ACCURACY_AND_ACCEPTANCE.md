# Evidence and acceptance status — October 21, 2026

This report separates working engineering from unsupported accuracy/identity
claims. It does not certify the port model for navigation or port access.

## Current evidence

The `authority-20261019-v2` release retains 3,256 features: 3,226 OSM context
features plus 13 authority berth polygons and 17 parts of 10 authority terminal
polygons. The public JNPA GIS provides original EPSG:32643 metadata and server
conversion to EPSG:4326. Acquisition/survey epoch and positional accuracy are
not published; anonymous access is not an explicit redistribution licence.
These are source-reported outlines, not observations of present berth availability.

The independent image is Sentinel-2 product `S2B_43QBA_20260322_0_L2A`, acquired
March 22, 2026 at 05:53:51.540 UTC, native 10 m true-colour pixels. Retained files
include its STAC metadata, native pixel window, display export and SHA-256
receipts. The full remote COG is not retained. Nearest-neighbour export does not
increase spatial resolution. Source geolocation uncertainty is not established
by this pilot.

The [registration overlay](evidence/registration-overlay.png) shows cyan OSM
berth/coast lines and red authority berth polygons on the dated reference.
The ten numbered image selections were made before nearest-vertex matching.
All selections are reported, not filtered for a favourable result.

**These are screening candidates, not validated corresponding survey points.**
The OSM-pier nearest-vertex screen yields median 354.1 m, p95 685.1 m and maximum
700.9 m. Those values expose missing/old geometry and incompatible feature
semantics; they are not a meaningful estimate of absolute horizontal accuracy.
There are zero fitted alignment points and zero independently verified
correspondence points. No shifts/scaling were fitted to conceal the discrepancies.
Detailed coordinates, matched IDs and uncertainties are retained in
`evidence/reference-checks.json`.

The design goals remain median ≤5 m and p95 ≤10 m for principal quay footprints.
**They are not demonstrated.** A 10 m display and unreviewed vertex matches cannot
support a 5 m claim. Absolute median/p95/max error, reference registration error,
height error and the independently verified asset set remain unknown.

## Dimensions and orientation

JNPA's August 2022 land-use plan, page 102/Table 13, is retained locally by hash;
page 27/Figure 8 was visually reviewed for terminal context. Because redistribution
permission is not established, the complete PDF remains in ignored local work
storage. Its URL, exact hash and receipt are in `evidence/source-inventory.json`.

| Published terminal correspondence candidate | 2022 length | GIS length attribute | GIS polygon maximum chord |
| --- | ---: | ---: | ---: |
| JNPCT / later NSFPT name | 680 m | 680 m | 683.5 m |
| NSICT | 600 m | 600 m | 399.3 m |
| NSIGT | 330 m | 300 m | 532.9 m |
| GTIPL / APM | 712 m | 712 m | 715.1 m |

Maximum chord is a geometric extent, not necessarily the quay face. NSICT and
NSIGT need source/semantic clarification; the code does not resize polygons to
force agreement. Historical names and current GIS identity remain candidate
correspondences. `evidence/dimension-comparisons.json` records axis bearings,
all differences and null published orientations. No suitable reference
orientation or height has been established, so orientation/height errors are null.
No undated GIS draught/depth values are imported into operational calculations.

## Operational identity audit

The simulator constructs `B1..Bn` from counts and schematic layout. Neither those
IDs nor a matching count proves identity with named real berths. Every authority
berth has an explicit `reviewed-unmapped` disposition, reviewer/time and reason
in `operational-mappings.json`. This is a code/source audit, not a port operator's
approval. Operational values remain unavailable on those real features.

The renderer now supports explicit reviewed ID mappings for berths, yards and
sheds, reads the existing chosen-horizon state, and preserves geographic
selection. A synthetic browser fixture exercises that path without adding a
false production mapping. Completing a real mapping requires an operator or
an existing authoritative operational ID catalogue; the integration owner
must also decide whether to extend the schematic simulator's asset model.

## Acceptance matrix

| Requirement | Current status |
| --- | --- |
| Separate branch, exact shared base, original role workflows | Implemented and preserved |
| Immutable sources, source inventory and CRS/axis transforms | Implemented; unknown metadata explicit |
| Reference imagery overlay before further 3D detailing | Retained and inspected; discrepancies documented |
| Actual terminal names and berth/source inspection | Authority labels and source geometry integrated |
| 3D heights/terrain | Renderer extrudes supplied heights; current source heights/terrain remain unknown |
| Operational mapping and overlays | Reviewed-unmapped real table; reviewed-ID renderer path tested with synthetic data |
| Orbit/pan/zoom, framing, plan, fit-selection, reset | Implemented |
| Layers, horizons, comparison UI, selection preservation | Implemented, with unavailable state where identity is unsupported |
| GPU disposal and missing/WebGL/layer failure handling | Implemented and browser-tested |
| Performance | Recorded headless desktop interaction; see below |
| Accuracy report | This report records available measurements and limits; high-accuracy goal is not validated |
| Reproducible build and second-port assessment | Build scripts and feasibility assessment supplied |
| GEE descriptor, API, raster/vector loader, dated sample | Implemented and tested; live GEE authentication is teammate-owned |
| Public integration URL | Placeholder supplied; host/deployment still to be decided |

## Performance

The final v2 headless interaction run recorded 84 frames on macOS with an Intel
Core i5-8500 at 3 GHz, Chromium 153.0.8010.12, 1366×768 viewport and the dated
raster and explicitly illustrative 6 m building extrusion enabled. Average frame
cadence was about 37.8 FPS; median interval 16.7 ms, p95 66.7 ms. WebGL exposed
masked `WebKit` vendor/renderer strings, so no physical GPU identification is
claimed. Scene: 3,305 draw calls, 42,567 triangles, 3,256
source features. The catalogue is about 4 MiB and the raster about 1 MiB.

This is a short headless interaction sample, not a sustained hardware-GPU
benchmark or a guarantee that every frame stays above 30 FPS. The original
schematic is preserved. `evidence/performance.json` retains exact results for the
final framing and label collision handling. Later changes require another sample.

## What is still needed for full sign-off

1. A suitable independent survey/high-resolution reference and reviewed
   correspondences, with source accuracy/date and separate fit/check sets.
2. Resolution of terminal geometry/dimension discrepancies and a real operational
   asset identity source. Do not replace these with count/order guesses.
3. Verified heights/terrain if measured 3D elevations are required, plus review of
   source redistribution permissions before public release.
4. An agreed backend host and provider catalogue host for remote GEE integration.

GEE integration can begin with the implemented contract while these evidence
and deployment decisions are resolved. The full original acceptance criteria
are not represented as complete merely because the software tests pass.

## Final engineering handoff check — October 21, 2026

The geometry/API suite passed 17 tests again. An additional handoff test verifies
checksums and runs all required static API routes plus dry-run layer validation
from a clean extracted minimal archive in a separate Python process. No renderer
or simulation changes were made in this check; previously recorded browser and
performance results remain scoped to the v2 implementation.

The remaining evidence and hosting dependencies above are unchanged. They cannot
be completed by relabelling unknown metadata, mapping schematic IDs by order or
providing a placeholder URL. This delivery is ready for teammate integration
development, but full independent accuracy/identity sign-off is outstanding.
