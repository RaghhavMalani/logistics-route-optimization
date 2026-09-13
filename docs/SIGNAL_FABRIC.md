# Signal Fabric

Where PortWatch's data comes from, whether this deployment may use it, how old
it actually is, and how an observation becomes a fact about the world.

Most of the interesting maritime data in the world is available and *not*
licensed for commercial redistribution. A product that wires those sources
straight into features does not discover the problem at integration time — it
discovers it during a customer's procurement review, by which point the
dependency is load-bearing. So licence is a first-class field here, answered
per product and backed by recorded evidence, and the resolver refuses rather
than degrades.

## The pipeline

```
PROVIDER ─ PRODUCT ─ LICENCE POLICY
              │
           ADAPTER → NORMALISER → OBSERVATION → QUALITY
                                       │
                      AIS: TRACK STORE → FUSION → WORLD STATE
                      SEA: MARINE GRID → ROUTE EXPOSURE
```

| Stage | Module | What it decides |
|---|---|---|
| Product | `fabric/products.py`, `fabric/licence.py` | May we use this product, in this mode? On what evidence? |
| Adapter | `fabric/adapters.py`, `fabric/marine.py` | Can it run here, and what did it return? |
| Observation | `fabric/observation.py` | When was this observed, and how long is it true? |
| AIS ingest | `fabric/ais/` | What did each transponder actually say, in order, deduplicated? |
| Fusion | `fusion/` | Which claims are about one hull, and how sure are we? |
| World | `world/observed.py` | Where does an observed hull sit in the consequence graph, and at what confidence? |
| Sea | `world/route_exposure.py` | What sea will a passage run through, at the hours it runs? |

Nothing in the fabric fetches on the request path. The weather and event
adapters read artefacts the pipeline exported; the AIS client is a background
websocket; the marine grid is refreshed by a background thread inside its TTL.
Every one of them reports the **reading's** age, not the age of the read.

## Licence at product granularity

A provider is a company. A product is a thing it sells or gives away, with its
own terms. Open-Meteo's free API is non-commercial and its subscription is
not; they are the same company, and a licence recorded on the company would be
wrong for one of them. So `Provider → ProviderProduct → LicencePolicy`, and
the adapter chooses the product (by whether a key is configured) before the
catalogue is asked whether the mode may use it.

Each permission — commercial use, government use, redistribution — is one of
four states:

| State | Meaning | Resolves as |
|---|---|---|
| `ALLOWED` | The published terms permit it | permitted |
| `PROHIBITED` | The published terms forbid it | refused, with the terms quoted |
| `REQUIRES_REVIEW` | Terms were looked for and not found, or do not address it | refused: *a permission nobody has verified is not a permission* |
| `UNKNOWN` | Not yet examined | refused |

Every policy carries `TermsEvidence`: the URLs checked, the review date and
the finding — quoted verbatim where the terms say something, and "no terms
were found" where they do not. **Never infer a restriction that has not been
verified**, and never infer a permission either. AISStream is the worked
example: its site, documentation and repository publish no terms of use, so
its standing is `REQUIRES_REVIEW` with those three URLs recorded, not
"non-commercial" as an earlier version of this document asserted without
evidence.

`docs/DATA_SOURCES.md` is rendered from the catalogue by
`scripts/render_data_sources.py`; the trust surface in the terminal shows the
same four states. Neither can say something the catalogue does not record.

## The rules this exists to enforce

**A licence boundary is never crossed silently.** Asking for AIS in
`COMMERCIAL` returns a product that may legally serve it, or `UNAVAILABLE`.
There is deliberately no fallback to a research feed because the commercial
one was not configured. Every rejection carries its reason and, where the
terms were the reason, the words of the terms.

**Source time is not ingest time.** A forecast issued six hours ago and
fetched thirty seconds ago is six hours old. Freshness is computed from when
the provider observed it. Where a provider publishes no observation time
(Open-Meteo publishes no model-run time; the GDELT bundle carries no field),
the provenance says which time stood in and the freshness is graded on that.

**An unknown age is not a fresh one.** Where a payload carries no timestamp,
the observation reports `UNKNOWN` rather than a number derived from `now`.

**An adapter that cannot run returns nothing.** It never substitutes demo
data. An adapter that, finding no API key, quietly served the replay would
keep the screen working and keep it saying LIVE.

**Secrets stay on the server.** Adapters read keys from the environment. The
API exposes provider *status*, never provider configuration, and a key
appears in no payload, log line or status response.

**A deployment says what it is.** `PORTWATCH_LICENCE_MODE` names the mode a
process runs in. It defaults to `COMMERCIAL`, the most restrictive reading:
a process that has not said it is non-commercial never calls the Open-Meteo
free host, and a request may only *view* the world in a mode; it cannot make
the process fetch what the process's own mode forbids.

## Deployment modes

| Mode | Non-commercial products | Redistribution required |
|---|---|---|
| `RESEARCH` | eligible | no |
| `DEMO` | eligible, attribution enforced | no |
| `COMMERCIAL` | **ineligible** | no |
| `GOVERNMENT` | **ineligible** | **yes** — output is shared between agencies |

## Observed AIS

`fabric/ais/` is a server-side websocket client for AISStream, and it is the
part of the fabric most likely to be misread, so its rules are the strictest.

**Two state machines, kept apart.** *Provider health* is the pipe:
`CONNECTING`, `LIVE`, `DEGRADED`, `STALE`, `DISCONNECTED`, `AUTH_FAILED`,
`RATE_LIMITED`. *Traffic source* is the picture: `LIVE_AIS`, `AIS_STALE`,
`SIMULATED_TRAFFIC`, `UNAVAILABLE`. The rule that connects them: **the source
is LIVE_AIS because valid observations arrived, never because a key exists.**

| Condition | Traffic source |
|---|---|
| A valid observation within the last 10 minutes | `LIVE_AIS` |
| The last valid observation is 10–60 minutes old | `AIS_STALE` — positions shown are the last known |
| A key is configured and nothing valid has arrived, or the feed lapsed, or the credential was refused | `UNAVAILABLE` — the chart is not showing the replay in its place |
| `RESEARCH`/`DEMO` with no key: the replay was chosen | `SIMULATED_TRAFFIC` |
| `COMMERCIAL`/`GOVERNMENT`: no eligible product | `UNAVAILABLE` |

A live provider never becomes the replay by falling through. The transition
`LIVE_AIS → SIMULATED_TRAFFIC` does not exist.

**Reconnection** is bounded exponential backoff with jitter (1 s doubling to
60 s). A subscription must be sent within three seconds of connecting; a
socket quiet for ninety seconds is `DEGRADED`. Authentication failure is
detected the way the real endpoint behaves — observed 2026-09-12 against
`wss://stream.aisstream.io/v0/stream`, an invalid key produces **no error
envelope**, just an abrupt close with no close frame — so three consecutive
sessions that close with nothing delivered are `AUTH_FAILED`, and the client
stops rather than hammering a server that has refused it.

**Normalisation preserves exactly what was said.** A position report carries
an MMSI and a position. It does not carry an IMO, a name or a destination,
and an observation built from it has `None` there, not a value looked up from
elsewhere. AISStream joins a ship name onto position reports from earlier
static data; that join is kept as provenance (`meta_ship_name`), never
promoted to a claim. Sentinels (heading 511, SOG 102.3, COG 360, position
91/181) become `None`, not numbers. IMO 0 is absence.

**The track store** deduplicates on (MMSI, source time, position), orders by
source time — a late report is slotted into history and never moves the head
backwards — bounds memory per vessel and overall, and evicts transponders
quiet for two hours. It refuses to merge identity; that is fusion's job.

## Entity fusion

`fusion/` decides, with evidence, which claims are about one hull.

*   **IMO is strong.** Two claims with the same IMO are one hull.
*   **MMSI is strong, with two safeguards.** A transponder reporting a
    *different* IMO from the hull it is linked to does not move on the first
    message; it moves on the second consistent one, and the move is recorded.
    A transponder silent past the reuse window (30 days) that returns under a
    different name is a possible reassignment, and gets a new hull.
*   **A name is never a key.** A name match produces a *candidate* for a
    person to review. It merges nothing. There is no name parameter on the
    lookup route, because a lookup by name would be the merge by name the
    engine refuses.

Every `EntityAssertion` is immutable and kept. Every `IdentityLink` is
appended, never rewritten, and retracted with a reason. Every disagreement is
a `Conflict` on the record. A `CanonicalVessel` is derived from those and can
be rebuilt from them, so a wrong merge is always unpickable.

## Observed hulls in the world graph

An observed hull enters the consequence graph through `world/observed.py`,
and every step of its placement is graded:

| Derivation | Method | Confidence |
|---|---|---|
| Destination | The typed AIS field, resolved by `fusion/destination.py`: LOCODE / port name / India-unknown / foreign / none | 0.9 / 0.7 / 0.2 / — / — |
| Lane | Position region × destination coast; refused when several lanes with different chokepoints cross the region | 0.6, or 0.48 when the origin is unknown |
| Hours to chokepoint | Great-circle distance over SOG, only when making way and pointing towards the strait | 0.5 |

The joint placement confidence attenuates the **confidence** of what a
cascade delivers to the hull — never the magnitude. The water is as
dangerous; being in it is less certain. A hull nothing can be derived for is
still on the chart and in the inspector; it transmits no consequence it has
not earned.

## The sea

`fabric/marine.py` reads Open-Meteo's Marine API for significant wave height,
direction and period; swell height, direction and period; wind-wave height;
sea-surface temperature; and current speed and direction (converted from
km/h to knots), on a grid of chokepoints, port approaches and open-water legs.
The free host is called only from a `RESEARCH` or `DEMO` process; a key
selects the subscription product and host. A fetched grid is reused within
its TTL, persisted so a restart shows the last known sea state with its age,
and never fabricated — with no successful fetch there is no grid.

`world/route_exposure.py` walks a route at a vessel's speed, samples the grid
at the place *and the hour* the vessel would be there, and reports a
`RouteExposureProfile`: the heaviest sea and where, hours in rough and heavy
seas, hours in head seas, the along-track current, and the hours the sea
state adds by a documented speed-loss heuristic. The profile carries its
coverage (the share of samples with a usable cell) and a confidence that is
never above 0.5, because the heuristic is order-of-magnitude seakeeping, not
this hull's curve.

## Status vocabulary

| Term | Meaning |
|---|---|
| `AVAILABLE` | Configured, reachable, returning observations here |
| `CONFIGURABLE` | Seam exists; needs a key, an endpoint or a first fetch |
| `PLANNED` | Named, with no adapter. Nothing reads it |
| `UNAVAILABLE` | Known and not usable here — wrong licence, refused, or lapsed |
| `LIVE` | Observed within this capability's live window |
| `CACHED` | Older than live, inside the staleness threshold |
| `STALE` | Beyond the threshold |
| `EXPIRED` | Past the validity the provider stated |
| `UNKNOWN` | The payload carried no timestamp |
| `SIMULATED` | Modelled, not observed. Labelled wherever drawn |
| `SCHEMATIC` | Representative geometry, not surveyed |
| `ASSUMPTION` | A user-entered scenario value, never mixed with observed rates |

## Adapters shipped in this build

| Capability | Product | Status without a key | Notes |
|---|---|---|---|
| `ais` | `aisstream-websocket` | `CONFIGURABLE` | Needs `AISSTREAM_API_KEY` *and* a first valid message before anything is LIVE |
| `marine` | `open-meteo-free` / `open-meteo-customer` | `AVAILABLE` in RESEARCH/DEMO once fetched | Background refresh; `OPEN_METEO_API_KEY` selects the subscription |
| `weather` | `open-meteo-free` / `open-meteo-customer` | `AVAILABLE` | Reads the pipeline's forecast artefact |
| `events` | `gdelt-events` | `AVAILABLE` | Reads the news bundle; timestamp basis is the artefact write time |

Registered with a licence and read by nothing yet: `disaster`, `seismic`,
`fire`, `vessel_registry`, `port_stats`, `geography`.

## The trust surface

`GET /api/fabric/health?mode=` answers, for every capability: MODE, STATUS,
LAST OBSERVATION, AGE, COVERAGE, PRODUCT and LICENCE STATE, plus the traffic
block with the socket's own health beneath the picture's mode. The terminal's
Signal Health panel shows exactly those fields in that order, and the observed
vessel inspector says `OBSERVED AIS` with the transponder's own timestamp
where the replay inspector says `SIMULATED TRAFFIC`.

See [DATA_SOURCES.md](DATA_SOURCES.md) for the full product matrix with
evidence.
