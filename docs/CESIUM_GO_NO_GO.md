# Cesium: GO / NO-GO

**Verdict: NO-GO for this milestone. Conditional GO for a later globe view,
behind a lens, once two conditions are met.** The conditions are a licence
decision and a rendering decision, and neither is a code problem.

Investigated 2026-09-13. Everything below is either read from the current
repository or quoted from Cesium's published pages on that date.

## What was checked

| Question | Finding | Source |
|---|---|---|
| Is the CesiumJS library free to use commercially? | Yes. CesiumJS is Apache-2.0. The library is not the constraint. | github.com/CesiumGS/cesium (LICENSE) |
| Is Cesium **ion** — the hosted terrain, imagery and asset service — free to use commercially? | **No.** The Community tier is "Personal and non-commercial use"; a paid account is needed "if your company currently makes more than $50K in annual gross revenues or has raised funds in excess of $50K" or for government / funded research. Commercial is $149/month individual, $524/month team, "commercial use within your organization"; use "in solutions used outside your organization" is separately priced. | cesium.com/platform/cesium-ion/pricing/ |
| What does the ion licence require on screen? | "making the 'Cesium ion' logo prominently viewable to users" — "prominently displayed on the main application window of Your Application". | cesium.com/legal/terms-of-service/ (updated 2025-08-20) |
| Is Cesium World Terrain usable without ion? | No. World Terrain, Bing/Sentinel imagery through ion and the ion asset pipeline all require an ion token. Self-hosted terrain (quantized-mesh tiles you build yourself) works without ion. | Cesium documentation |
| What does this product render today? | MapLibre GL 5 (BSD-3), one canvas, ~1,900 lines of layer code (`MaritimeMap.tsx`, `basemap.ts`, `traffic-layers.ts`, `weather-layers.ts`, `WindLayer.tsx`), an 800-vessel replay written straight into GL sources at 60 fps, a particle wind canvas composited over the map, and a browser suite that reads the map's own sources (`window.__portwatchMap`, `window.__portwatchSources`). | this repository |
| Does anything here need a globe? | Nothing in the current requirements. The operational picture is the Indian Ocean from Suez to Malacca; it fits a Mercator chart and every user is looking at it as a chart. Bathymetry is faked with blurred coast strokes deliberately (see `basemap.ts`), and the product says so. | this repository |

## Why NO-GO now

1. **The licence would become a second REQUIRES_REVIEW dependency in the
   product's core.** Cesium ion's Community tier is non-commercial in the same
   way Open-Meteo's free tier is, and this milestone has just spent
   considerable effort making that class of dependency visible and
   refusable. A globe that only looks right with ion terrain and imagery is a
   globe that is non-commercial until somebody signs. The product would need
   `cesium-ion-community` (PROHIBITED commercially) and `cesium-ion-commercial`
   (ALLOWED, API_KEY) in the catalogue, an adapter that refuses the free tier
   in COMMERCIAL, and the ion logo on the main window under the terms. None
   of that is hard; all of it is a decision, not an implementation.

2. **Two renderers is the wrong number.** Cesium is a full 3D engine with its
   own scene graph and render loop. Running it beside MapLibre means every
   layer written for the chart — vessels, tracks, observed rings, cascade
   halos, the sea-state discs, the wind particles — is written twice or
   drawn once and lost on the other view. Replacing MapLibre means rewriting
   ~1,900 lines of layer code and the browser suite's map assertions, and
   losing the replay's 60 fps direct-to-source path, which Cesium's entity
   API does not give.

3. **Weight.** CesiumJS ships a multi-megabyte bundle plus workers and assets
   (the minified library alone is several times MapLibre's 1.1 MB), against a
   terminal that is currently verified at 1366×768 on a software renderer in
   CI. The browser suite's 45-second map-ready budget is already close.

4. **No requirement asks for it.** The milestone's remaining unavailable
   things — commercial AIS, a government redistribution right, port geometry
   that is not schematic — are data problems. A globe changes none of them.

## What would make it a GO

*   **A licence decision**: either a Cesium ion Commercial plan on record in
    the catalogue as a product with its terms evidence, or a self-hosted
    terrain and imagery set that does not touch ion at all (quantized-mesh
    from open DEM data; open imagery). The second is more work and cleaner.
*   **A rendering decision**: Cesium as an *additional* view behind a lens
    ("GLOBE"), reading the same GeoJSON the chart's sources already publish,
    with the chart remaining the product. Not a replacement.
*   **A use that needs it**: a global picture (transpacific or Cape routings
    drawn end to end without Mercator's distortion), or a 3D port approach
    that a chart cannot show. Neither is in the current requirements.

## What was done instead

Nothing in the product references Cesium. The trust surface, the sea-state
layer and the observed-AIS layer were all built on the existing MapLibre
chart, which is why they ship in this milestone rather than the next one.
