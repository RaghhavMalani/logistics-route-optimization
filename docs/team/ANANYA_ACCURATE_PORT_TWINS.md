# Ananya — accurate, georeferenced 3D port twins

Prepared October 13, 2026. Owner: Ananya. Suggested separate branch: feat/ananya-georeferenced-port-twins.

## Assignment and intended result

Build a recognisable, geographically accurate 3D representation of real ports inside the existing PortWatch application. Start with one complete, verifiable pilot, then make the asset pipeline reusable across ports. Leave a defined integration path for Google Earth Engine (GEE), satellite-derived layers and future authorized camera observations.

This replaces the earlier suggestion that Ananya should own model research. This assignment is geospatial modelling, 3D engineering and port-twin integration. ML-assisted feature extraction is useful where it can be evaluated and reviewed, but it is not a requirement to add a neural network.

The product should let someone select a port on the existing map/globe, open its twin, recognise the actual terminal layout, inspect a berth or yard, and compare the existing simulation overlays on the same assets. A visually impressive model must also have documented coordinates, dimensions, source dates and positional limitations.

## Branch starting point

Read [the shared work plan](D:/LogisticOptimization-_Capstone_168/docs/team/PARALLEL_WORK_AND_FEEDBACK_PLAN.md) before creating the branch.

The shared base is feat/portwatch-restored-intelligence, created from main after the earlier deployment branch was merged. It contains the current application updates and these briefs. Fetch that remote branch and create your own branch from its tip. Record the exact tip SHA as your base. The older e906f6a commit remains the restored-interface reference; use the new shared branch for development.

Use a separate checkout/worktree with separate development state. Do not switch or reset the integration owner's active checkout. Do not rewrite published history. Your proposed teammate branch has not been created by this brief; create it from origin/feat/portwatch-restored-intelligence.

## Read and reuse

- [PortTwinScene.tsx](D:/LogisticOptimization-_Capstone_168/india-portwatch-terminal/src/components/twin/PortTwinScene.tsx): current Three.js scene, picking and overlays.
- [PortTwinScreen.tsx](D:/LogisticOptimization-_Capstone_168/india-portwatch-terminal/src/components/twin/PortTwinScreen.tsx): time controls, inspector, simulations and decision comparison.
- [Twin state](D:/LogisticOptimization-_Capstone_168/src/portwatch_os/twin/state.py), [simulation](D:/LogisticOptimization-_Capstone_168/src/portwatch_os/twin/simulation.py) and [API](D:/LogisticOptimization-_Capstone_168/backend/app/routes/port_twin.py).
- [Port registry](D:/LogisticOptimization-_Capstone_168/src/utils/port_registry.py).
- [Connected globe](D:/LogisticOptimization-_Capstone_168/india-portwatch-terminal/src/components/intelligence/ConnectedGodsEye.tsx).
- [Latest release](D:/LogisticOptimization-_Capstone_168/docs/AUTHORITY_RESTRICTION_RELEASE.md) and [restoration intent](D:/LogisticOptimization-_Capstone_168/docs/RESTORE_AND_EXTEND_HANDOFF.md).
- [Frontend repository instructions](D:/LogisticOptimization-_Capstone_168/india-portwatch-terminal/AGENTS.md).

The current scene explicitly generates schematic geometry from berth counts and coastline orientation. Its simulation state is useful; its geometry is not a surveyed plan. Preserve that original scene as a labelled fallback/reference while adding the new geometry path.

## Scope ownership

Own the port geometry catalogue, coordinate transforms, asset preparation, 3D scene implementation, geometry verification and the GEE layer adapter boundary.

Suggested new areas, to confirm against the shared base:

    data/port_geometry/<port-code>/<version>/
    src/portwatch_os/geospatial/
    scripts/port_geometry/
    india-portwatch-terminal/src/components/twin/georeferenced/
    tests/test_port_geometry_*.py
    docs/port_geometry/

These are proposed locations, not existing integrations. Make focused changes to PortTwinScreen for mounting/selection if needed. Keep the existing role shell, native workflows and original schematic scene available. The new user assignment permits a targeted twin upgrade; the earlier protected-file manifest is a comparison baseline, not a reason to prevent this work.

The integration owner keeps forecasting, feedback learning, authority notices, decisions, approvals, authentication and production deployment. Preksha owns shared UI conventions and data-quality presentation. Coordinate component interfaces with her; she should not rebuild your renderer.

## Milestone 1 — pilot evidence and geography

Proposed pilot: JNPA / INNSA, matching the current public advisory workflow. Compare evidence availability with Chennai / INMAA before committing to that choice. If another port has materially better source geometry, document that choice. Do not build all ports from generic repeated boxes.

For the pilot, identify and retain:

- Port and terminal boundaries, coastline, breakwaters and principal water areas.
- Berth/quay alignments, terminal names and published dimensions.
- Yard blocks, warehouse/building footprints, gates, major roads and rail connections.
- Terrain/elevations, imagery acquisition dates and any published vertical reference.
- Asset identifiers that can link to operational records.
- Depths, dredged channels and berth restrictions only when a dated, suitable authority source exists.

Prioritize authority plans, openly usable surveyed GIS, permitted high-resolution imagery and mapped features with traceable provenance. OpenStreetMap can support reference geometry; its completeness and positional accuracy require checking. Satellite pixels cannot establish precise crane positions, current container counts or berth availability.

Create a source inventory with URL/product, publisher, acquisition/publication date, first receipt, original hash, CRS, ground resolution, vertical datum, coverage, permitted use and attribution. Use null or unknown for missing fields. Preserve immutable originals separately from derived geometry.

Deliver a 2D overlay of the pilot footprint on its reference imagery before substantial 3D detailing. Check shoreline alignment, orientation, berth names and scale. The 2D check should catch a shifted or mirrored model early.

## Milestone 2 — georeferenced geometry pipeline

Use longitude/latitude with an explicit horizontal CRS for interchange; record elevation and its datum separately. Convert to a documented local metric frame for the port scene. Specify axis orientation and transformations, including the mapping from east/north/up to Three.js axes. Do not treat degrees as metres.

Each feature needs a stable ID, port/terminal ID, geometry type, feature kind, source IDs, geometry version, source date and quality class. Separate horizontal footprint quality from height quality.

Recommended quality classes:

| Class | Meaning |
| --- | --- |
| Surveyed | Source survey and reference system are documented |
| Authority plan | Digitized or supplied authority geometry, with scale/date limits |
| Imagery-derived | Digitized/extracted from dated imagery, with measured uncertainty |
| Illustrative | Visual detail or assumed dimensions |
| Unknown | Insufficient geometry evidence |

A warehouse can have an imagery-derived footprint and an illustrative height. Do not assign one global accuracy label to every object.

Keep the geometry-to-operational-asset mapping explicit. Existing simulator berth IDs may not correspond to actual named berths. Use a reviewed mapping table; unmapped real features can render with operational state unavailable. Do not spread simulated occupancy across real assets by array order.

Export reproducible assets, such as GeoJSON footprints and glTF/GLB meshes, with a manifest of geometry versions, hashes, transforms, source coverage and feature IDs. Include a script or documented build procedure rather than a manually edited mesh with no reconstruction path.

## Milestone 3 — the operational 3D experience

Retain the original Port workflow and implement:

1. Correct whole-port framing, north indication, metric scale and terminal/berth labels.
2. Orbit/pan/zoom, fit-selection, reset-view and plan/oblique views.
3. Layer controls for imagery, buildings, berths, yards, roads/rail and supported operational overlays.
4. Selection of an asset that opens its existing operational inspector, plus geometry provenance.
5. The current horizon controls and option comparison using the existing twin API/state.
6. Visible separation of real static geography, dated observations and simulated vessels/occupancy/projections.
7. Useful 2D/schematic fallback when assets, imagery or WebGL are unavailable.

Model cranes and equipment with detailed geometry only to the level supported by evidence. Illustrative textures, vehicles and container stacks must not become reported observations. A real-looking port with simulated operations should say so clearly.

Preserve selection IDs when changing overlays or horizon. Dispose GPU resources on navigation and avoid rebuilding the full scene for every metric update. Lazy-load heavy assets and use suitable levels of detail. Measure performance on a recorded desktop/browser configuration; target a usable 30 FPS or better for the pilot, reporting the actual scene/asset size and results.

Reuse the existing Three.js scene architecture first. The global globe already has its own renderer. Evaluate a Cesium/3D Tiles path only if geographic extent, terrain or asset scale makes it useful; avoid running duplicate full renderers merely for visual effect. Document the choice and tradeoffs.

## Milestone 4 — quantified accuracy

Define accuracy goals before measuring the final model. A provisional pilot goal for principal berth/quay footprints is median horizontal error at or below 5 m and p95 at or below 10 m, using independent reference material capable of supporting that test. These are design goals, not claims about the available data.

Use distributed control/check points, preferably at least ten where suitable references exist. Report:

- Reference source, dates, its own accuracy/resolution and registration method.
- Point/edge errors in metres, median, p95 and maximum, with spatial distribution.
- Berth-length and orientation differences against suitable published dimensions.
- Which assets were checked and the unverified portions of the port.
- Height/elevation error separately where reference heights exist.

Do not calibrate alignment and evaluate it using exactly the same control points. Report uncertainty from both the source and the model. If imagery resolution, reference age or missing survey data cannot support the goals, state the achieved quality and preserve unknowns. A general label such as extremely accurate is insufficient.

No invented bathymetry, draught-clearance calculation or navigation authorization may follow from this model. Geometry accuracy alone does not validate operating capacity or real port access.

## GEE-ready boundary

GEE is interpreted here as Google Earth Engine. It provides satellite/geospatial analysis and raster/vector outputs; the 3D port scene remains the presentation and operational integration layer. [Official overview](https://developers.google.com/earth-engine/guides).

Define a provider-neutral geospatial-layer descriptor containing:

    layerId, portCode, kind, bounds, horizontalCrs, verticalDatum,
    acquisitionFrom, acquisitionThrough, firstAvailableAt,
    nativeResolutionM, resamplingMethod, noDataDefinition,
    sourceProduct, processingVersion, sourceHashes,
    attribution, quality, displayResource, assetIds

Unknown metadata is explicit. Raw analytical values remain distinct from display RGB textures. A future adapter can supply imagery, shoreline/change-detection products or flood masks without rebuilding the twin or changing asset IDs.

Prepare one locally retained, dated raster/vector overlay to demonstrate alignment. Live GEE access is not needed to complete the geometry pipeline and adapter contract. If existing approved project access is available, add an optional live adapter with unavailable/error states. Keep service credentials on the backend and account for expiring display resources.

Useful official references: [image visualization](https://developers.google.com/earth-engine/guides/image_visualization), [image export and projections](https://developers.google.com/earth-engine/guides/exporting_images), and [Cesium coordinate transforms](https://cesium.com/learn/cesiumjs/ref-doc/Transforms.html). GEE layers must retain their actual spatial resolution and source date; an overlay does not increase the accuracy of the underlying port geometry.

Future camera viewpoints should attach through asset IDs, geographic pose and reviewed coverage polygons. Leave that seam available without inventing cameras or training a CV model without authorized footage.

## Deliverables and acceptance

First PR: pilot source inventory, 2D registration proof, geometry schema and transformation tests.

Second PR: georeferenced 3D pilot, reviewed operational ID mapping, original overlays/selection/horizons, performance results and failure fallbacks.

Third PR: accuracy report, reusable import/build process, second-port feasibility assessment and GEE-ready layer contract with an aligned sample.

Include geometry fixtures for transformations, known distances, axis orientation, bad CRS/coordinates, missing assets and mapping integrity. Browser verification must cover selection, overlays, time changes, navigation cleanup and fallback. Run frontend type/build checks and relevant backend tests. Provide original/current screenshots at the same viewport and state.

Completion means one real port is recognisable and geographically anchored, the supported accuracy is measured, operational state uses explicit mappings, and future remote-sensing layers can align to it. It does not require every port, live GEE credentials or measured operational savings.

## Copyable starting instruction

Work on your separate branch from the shared current-release source commit. Read this brief and the shared plan. Build a verified georeferenced port twin, beginning with source inventory and a 2D accuracy check. Preserve the existing role UI, simulator state and original schematic fallback. Own geometry/renderer/GEE adapter work; leave feedback learning, decision rules, authentication and deployment with the integration owner. Deliver small PRs with provenance, measured accuracy, screenshots and reproducible assets.
