# Parallel work: port twins, product quality and shared learning

October 13, 2026. Ananya's primary assignment is accurate port twins, replacing the earlier model-research proposal.

## Ownership

| Owner | Responsibility | First milestone |
| --- | --- | --- |
| You / integration owner | Weather, news/economic/other-factor feedback; operational consequences; role workflows and publication | Extend the current learning/evidence loop |
| Ananya | Accurate georeferenced 3D ports, geographic assets, operational mappings and future GEE integration | One validated real port twin with measured accuracy |
| Preksha | Existing UI, interactions, data quality, contracts and output clarity | Improved Admin Data and one evidence/decision inspector |

Read [Ananya's brief](D:/LogisticOptimization-_Capstone_168/docs/team/ANANYA_ACCURATE_PORT_TWINS.md) and [Preksha's brief](D:/LogisticOptimization-_Capstone_168/docs/team/PREKSHA_UI_DATA_PRODUCT.md). [Local development setup](D:/LogisticOptimization-_Capstone_168/docs/team/README.md) describes separate state and caches.

## Shared branch and separate teammate branches

The shared application branch is [feat/portwatch-restored-intelligence](https://github.com/RaghhavMalani/logistics-route-optimization/tree/feat/portwatch-restored-intelligence). It starts from main after the September deployment branch was merged. Its initial snapshot records the later application source, public assets, tests and these briefs.

The older e906f6a6bd4388cd3c059b4d9a5de6759139528b commit remains the restored UI reference. Use the new shared branch as the development base. Record its exact tip SHA when creating your branch.

Ananya, in her own clone:

    git fetch origin
    git switch -c feat/ananya-georeferenced-port-twins origin/feat/portwatch-restored-intelligence

Preksha, in her own clone:

    git fetch origin
    git switch -c feat/preksha-ui-data-quality origin/feat/portwatch-restored-intelligence

Record the common base:

    git rev-parse origin/feat/portwatch-restored-intelligence

Do not run these switches in the integration owner's active checkout. Each teammate pushes their own branch and submits small PRs. Preserve published history; do not force-push or rewrite pushed commits.

The source snapshot includes application source, lockfiles, public fixtures and asset manifests. Credentials, private operator/session state, local work logs, generated caches/databases and temporary captures are excluded. Production evidence remains on persistent storage. A fresh clone creates its own state and does not inherit visitors or production observation counts. This Git handoff does not deploy the application.

## Keep the work independent

Ananya owns geometry, transforms, renderer assets, operational asset mappings and the GEE adapter boundary. Preksha owns quality/readability/interaction modules. The integration owner owns feedback, calculations, authority parsing, state machines, authentication, shared world state and release settings.

Shared-file coordination:

- PortTwinScreen mounts: Ananya.
- Twin toolbar, quality badges and inspector props: agree an interface together; avoid parallel rewrites.
- Decision/advisory/intelligence panels: the integration owner coordinates small Preksha presentation patches.
- Backend router registration, shared API client, root shell/global styles and production configuration: the integration owner integrates focused changes.

Do not create a second simulation state in the renderer, a second ledger in a UI feature or a contradictory source catalogue. Keep the original maps, globe, layers, timelines and role workflows.

## Common data contract

Use existing registry/entity IDs. New geographic asset IDs need an explicit mapping to operational assets. Source-backed items retain:

    entityId / assetId / portCode
    sourceProductId and sourceReceiptId
    observedAt or acquisition interval, where known
    forecast origin and target, where applicable
    event validity and date precision, where applicable
    firstAvailableAt
    unit, aggregation, geometry CRS/datum where applicable
    original reference/hash and derivation version
    quality / coverage / missingness
    value kind: observed, forecast, derived, assumed, simulated or unknown

This is an additive semantic contract, not a wholesale migration of existing records. Use schema versions and adapters. Unknowns remain null with a reason. Preserve private-source and visitor access boundaries.

Ananya supplies geometry/layer metadata. Preksha presents it consistently. The integration owner consumes identified evidence in existing decision and learning pipelines.

## Your expanded feedback track

The common loop is:

    Preserve original claim and available inputs
        → define a verifiable target
        → receive later independent evidence
        → reconcile identity, time, units and scope
        → score error / reliability
        → validate a correction or revised relationship
        → freeze the next decision's consumed version
        → evaluate its later outcome

| Factor | Later evidence and learning target |
| --- | --- |
| Weather | Matching station/reanalysis variable, location and aggregation; forecast residuals and separately operational-effect error |
| News/events | Later authority/operator confirmation, revision or contradiction of an extracted claim; identity, extraction quality, corroboration and relevance |
| Economic forecasts | Later observations of the same series, unit, target period and available vintage; forecast error and separately cost/demand relationships |
| Economic observations | A dated price/FX quote is already an observation; validate provenance, revisions and relevance rather than scoring it as a forecast |
| Infrastructure/restrictions | Authority revisions, cancellations and actual access/capacity/restoration records; validity and operational consequence |
| AIS / port calls | Later verified identities and actual event timestamps; ETA/call matching and timing error |
| Cameras / CV | Authorized footage with reviewed labels and coverage; detection error and operational observations |
| Satellite/geospatial products | Suitable dated reference geometry/imagery and change labels; geometry/classification quality |

Syndicated headlines are not independent confirmation. Separate correct reporting from an incorrect inferred shipping effect. A price change does not imply a six-hour delay without supporting operational inputs. Real port geometry does not establish real-time occupancy.

Use supervised correction/reliability estimation when alternatives can receive comparable feedback. Bandits fit choices where only the selected option receives feedback. Sequential RL needs a defined action/state/reward process and suitable evaluation. Do not add RL to every connector.

Separate training, selection, calibration and evaluation by chronology and availability. Preserve old claims/model reports. Existing rejected neural/RL candidates remain rejected until a separate experiment earns an adoption decision.

## Current release boundaries

The public application is https://india-portwatch.vercel.app/login. Read [AUTHORITY_RESTRICTION_RELEASE.md](D:/LogisticOptimization-_Capstone_168/docs/AUTHORITY_RESTRICTION_RELEASE.md).

The Eastham example changes planned waiting from 14 h 42 m to zero with the same total schedule shift. Its first operational tide is a conditional planning point. Actual access, fuel, cost and safety benefits remain unavailable.

Weather is collecting. First retained targets become eligible October 17; the retained five-day case around October 21, subject to actual provider availability. The older missing-original claim remains excluded. Authorized camera evaluation is pending. Demo sessions last 12 hours.

These dependencies constrain particular evidence claims; they do not prevent geometry, UI, contracts or source-quality work.

## Integration acceptance

Each PR states its base SHA, ownership boundary, changed files, schemas/assets, evidence and limitations. Include before/after screenshots and relevant tests. Check the four-role workflow after shared component changes. Preserve evidence hashes, source clocks, simulation labels and visitor isolation.

Integrate shared contracts/read-only adapters, pilot geometry and quality data, scene/UI components, then minimal mounts as dependencies require. The integration owner publishes after preview verification.
