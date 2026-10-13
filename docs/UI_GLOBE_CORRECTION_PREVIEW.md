# UI/globe correction: first functional preview

October 9, 2026. Local product review checkpoint; no deployment or promotion.

**Running preview:** http://127.0.0.1:4197/login. Choose **Open Company Demo**,
then **Compare voyage actions** or **Investigate global signals**. The frontend
uses the separate QA API at `http://127.0.0.1:9296/api`; production port 8000 is
not its data target. The preview is local to this computer.

## What this checkpoint changes

The Company demo now renders its actual route children inside the original
application chrome. `/company/overview` uses the existing Fleet Command action
rows and floating panels, adapted to the visitor-owned `/demo/workspace` world.
Its map occupies the workspace behind a 302-pixel inspector rather than a slot
between two permanent form columns. The original protected Company view remains
available to verified operational sessions.

Company Routes, Cargo and Advisories are separate route screens. Their adapters
read only the visitor's assigned lanes, declared cargo, preserved comparisons and
advisory records. No booking, readiness cutoff or cargo saving is fabricated.
Unsupported Company navigation is omitted from this bounded preview.

Entry offers four explicit demo roles over a functioning geographic scene.
Company Global Eye and `/explore` retain source selection, exposed assets, forecast
inspection, constrained comparisons, uncertainty and weather-learning evidence.
The signal panel collapses; source clocks and stale/missing states remain visible.

The shared Cesium/God's Eye renderer now has:

- A bundled **global** nautical atlas generated from public-domain Natural Earth
  country geometry, independent of the earlier clipped India geometry.
- An optional NASA GIBS Blue Marble imagery view with attribution. It is a static
  geographic composite, not current satellite observations, terrain or port surveys.
- Camera bounds from the selected route, with room for the inspector. Refreshes
  do not refit the camera; selection, option changes and explicit Fit do.
- Vessel glyphs, route-derived heading, selected/zoom-aware labels and Earth
  occlusion. Ports, events, chokepoints, weather observations and cameras use
  different symbols. No wave field or AIS coverage is invented.
- Fit, north-up, follow, imagery and 2D lens controls. The 3D render loop pauses
  in the 2D lens; the viewer is destroyed when its screen unmounts.
- A geographic SVG fallback with real pan, zoom and asset selection when WebGL
  fails. A static screenshot does not substitute for the scene.

## Preserved boundary and remaining work

The isolated demo backend, expiring opaque sessions, role permissions, frozen
comparisons and Company → Port review → approval → Vessel acknowledgment → demo
outcome chain are preserved. The API allowlist still prevents demo requests from
falling through to operational endpoints. QA uses a separate state directory and
disables collection; production evidence and its collector are untouched.

**Vessel, Port and Admin retain the existing functional DemoShell for this first
composition review.** Their original route restoration, port-twin presentation,
forecast/weather views and models/learning tables are still required after this
checkpoint is reviewed. This document does not claim that the four-role visual
recovery is finished. Milestone B and another production release remain deferred.

The globe remains general context rather than a navigation chart. There are no
observed vessel identities, authorized private cameras or connected continuous
weather field in these demo scenes. Cargo connection evidence remains unavailable.

## Review artifacts

The first preview covers entry, Company and global investigation at 1920 × 1080,
1366 × 768 and 390 × 844. Original baselines were inspected before editing:
national command, global consequence view, vessel bridge and Chennai port; the
rejected Company/Admin/Port captures were also inspected.

Artifacts and executable checks are in `work/ui-correction-preview/`,
`work/ui-correction-check.mjs`, `work/ui-correction-fallback.mjs` and
`work/ui-correction-source-check.mjs`. Side-by-side captures compare composition
and framing, not the original simulated vessel counts, weather fields or clocks.

Final verification:

- TypeScript: zero errors. Changed-source lint: zero errors or warnings.
- Compiled Vite/Nitro build passed with the Node preview preset. The corrected
  build is running locally; its cloud deployment behavior has not been verified.
- **16 workflow browser checks passed** at the three sizes, including geometry
  changes, proposal persistence, Company child screens, signal investigation and
  the complete cross-role advisory chain. No page errors or unexpected API failures.
- **Five imagery/failure/permission checks passed**: real NASA tiles rendered;
  a fresh-context unavailable imagery source preserved navigation; a forced widget
  resize failure switched automatically to the interactive 2D lens; asserted demo
  admin identity could not access operational identity/cameras; a separate visitor
  had no other visitor's advisory records.
- Forced public-source HTTP 503 preserved geographic navigation, retry and an
  explicitly assumed shipping comparison.
- Inspected the rendered images, not just the readiness attributes. The immediate
  mobile return-to-scene capture preceded the resized render; its settled capture
  and five scene crops were checked for actual geography. The executable capture
  now waits after the pane switch. Attribution remains clear below the timeline.
- Backend checks returned **12 passed, 2 skipped**: the skipped authorization
  parameter cases had no actionable hull in the current register. They are not
  counted as passes.

Detailed reports: `browser-results.json`, `fallback-results.json`,
`source-fallback-results.json` and `rendered-image-checks.json` under the artifact
directory above. Build/type/lint and Python logs are retained under `work/`.

## Source audit

Installed God's Eye `maps/imagery`, `defaultSources`, map catalog/controller and
data-source notes were inspected. The upstream keyless Esri default is not treated
as proof of this application's source authorization. This preview uses the
bundled Natural Earth geometry and documented NASA GIBS access instead; no account,
paid imagery source or terrain source was enabled.

- Natural Earth terms: https://www.naturalearthdata.com/about/terms-of-use/
- NASA GIBS acknowledgment: https://nasa-gibs.github.io/gibs-api-docs/
- NASA data-use guidance: https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy
- Reproduce the atlas: `scripts/build_nautical_atlas.py`.
- Local asset provenance: `india-portwatch-terminal/public/maps/README.md`.
