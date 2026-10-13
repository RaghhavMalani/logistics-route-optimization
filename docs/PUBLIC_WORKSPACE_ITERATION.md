# Public globe workspace — first recovery iteration

Prepared October 8, 2026. This iteration implements the first milestone in [the recovery plan](PRODUCT_RECOVERY_PLAN.md): an anonymous visitor can investigate a report, select exposed assets, inspect a dated port forecast, and run the existing constrained shipping engine in the same globe workspace. Research remains at `/research`.

## Visitor journey

1. Open `/` or `/explore`. One Cesium viewer, managed by the existing God's Eye application lifecycle, shows registered ports, chokepoints, routes and located maritime reports. Search filters the signal and port rail.
2. Select a report, then one of its exposed ports. Exposure uses the existing event-to-trade-lane catalogue, not an inferred causal delay. The inspector shows sources, receipt clocks, forecast origin/target, nominal intervals and stale status.
3. Configure a **simulated** vessel and an assumed restriction on its selected lane. Run the existing `DecisionEngine`, including route topology, timing gates, marine safety, Critic, Pareto frontier and robust recommendation. Change duration or sea height and recompute. Selecting an option redraws its geometry in the same viewer.
4. Inspect ETA shift, distance, fuel and exposure proxies, plus individually priced delay/fuel components under visitor-entered rates. Unknown cargo and port charges prevent a total-cost or savings claim. Port congestion predictions are context, not calibrated causal inputs to this simulation.
5. Inspect retained public weather originals and later public ERA5 observation matches where available. Pending observations remain pending. Proposed/retained corrections use the existing supervised workflow; this page does not fit or accept a model.

The desktop uses a signal rail, central globe and inspector. Mobile switches among those panels while retaining one scene. Visitor replay/projection is request-local. The current cache vintage is withheld until both its source receipt and export/refresh clock are available. Current camera streams and economic series without historical vintages are withheld in replay.

## Coverage and integration audit

The installed God's Eye package is pinned to [9542a5e58b19277d1f9b6698a46f69fdaa5fc5c1](https://github.com/bilawalsidhu/gods-eye-view/tree/9542a5e58b19277d1f9b6698a46f69fdaa5fc5c1). The [current upstream README](https://github.com/bilawalsidhu/gods-eye-view#readme), checked October 8, describes broader aircraft, vessel, satellite, weather, hazard, transport and camera capabilities. Upstream modules and advertised feeds do not establish PortWatch provider coverage or authorization.

| Capability | Installed package | Active public iteration | Remaining connection |
|---|---|---|---|
| Globe | Application/viewer lifecycle | One viewer; local Natural Earth imagery; no provider key | Higher-resolution approved imagery, if useful |
| Vessels | `vessels` module | Explicit scenario vessel; **no observed public AIS** | Authorized tracks, verified identities and coverage |
| Routes | PortWatch sea-route catalogue and engine | Ten catalogue lanes; selected decision geometry | Operational voyage/route validation; never navigation |
| News/security | PortWatch clustered maritime ingest | Source-linked events and catalogue exposure | Broader incidents and validated operational relationships |
| Aircraft/satellites | `aircraft`, `flights`, `satellites` modules | Not connected | Provider coverage and shipping relevance |
| Weather | `weather`, `wind`, `cyclones` modules | Dated port snapshots and weather markers; retained forecast feedback | Global/Indian Ocean fields, animation and independent observations |
| Hazards/fires | `earthquakes`, `firms` modules | Maritime hazard reports; public quake/fire geometry not enabled | Source-backed feeds and exposure contracts; operator USGS integration remains |
| Economics | PortWatch FRED context | Dated energy/currency/inflation context; visitor rate assumptions | Freight markets and evaluated economic forecasting relationships |
| Infrastructure | `traffic`, `transit`, `submarineCables`, `installations`, `perimeters` modules | Registered ports and chokepoints | Verified roads, rail, capacity, berth and inland-access feeds |
| Cameras | `cctv` module and scoped PortWatch registry | Only enabled authorized public records; none connected at preparation | Identified viewpoint, frame health, coverage and labelled footage |

Layers disclose catalogue, cached, scenario-only or unavailable coverage. There is no fabricated live vessel or camera fallback. Photorealistic terrain, all upstream layers and globally continuous feeds are not claimed for this iteration.

## Boundaries and next review

Anonymous GET projections have exact allowlisted paths. Operator identity guards and write permissions remain enforced. The public simulation has a local branch registry and no ledger, advisory, shared clock mutation or action approval. The camera projection opens the existing registry read-only and excludes private access, operators and registration metadata. The cloud image includes the same sea-route asset as the frontend, preserving engine geometry in hosted use.

Neural fusion, constrained RL and interval recalibration are the next research experiments **after this workspace review**. They are not implemented or evaluated in this iteration. The weather feedback page does not establish improvement when matched observations are absent. GLAD YOUNG remains a published ETA baseline case, not an ML routing outcome.

Validation records: `work/workspace-local-validation/report.json`, the focused public workspace/research/decision/clock suites, TypeScript, focused lint, and production build. Hosted browser checks, API integrity checks and deployment identifiers are recorded in [PUBLIC_WORKSPACE_RELEASE.md](PUBLIC_WORKSPACE_RELEASE.md). The main public URL opens the globe iteration.
