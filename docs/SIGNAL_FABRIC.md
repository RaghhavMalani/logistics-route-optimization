# Signal Fabric

Where PortWatch's data comes from, whether this deployment may use it, and how
old it actually is.

Most of the interesting maritime data in the world is available and *not*
licensed for commercial redistribution. A product that wires those sources
straight into features does not discover the problem at integration time — it
discovers it during a customer's procurement review, by which point the
dependency is load-bearing. So licence is a first-class field here, and the
resolver refuses rather than degrades.

## The pipeline

```
PROVIDER → ADAPTER → NORMALISER → OBSERVATION → QUALITY → WORLD STATE
```

| Stage | Module | What it decides |
|---|---|---|
| Provider | `fabric/model.py`, `fabric/registry.py` | May we use this source, in this mode? |
| Adapter | `fabric/adapters.py` | Can it run here, and what did it return? |
| Observation | `fabric/observation.py` | When was this observed, and how long is it true? |
| Quality | `fabric/observation.py` | Did anything about this reading look wrong? |

Nothing in the fabric fetches on the request path except where noted. The
weather and event adapters read artefacts the pipeline exported, and report the
**artefact's** age rather than the age of the read.

## The rules this exists to enforce

**A licence boundary is never crossed silently.** Asking for AIS in
`COMMERCIAL` returns a provider that may legally serve it, or `UNAVAILABLE`.
There is deliberately no fallback to a research feed because the commercial one
was not configured. Every rejection carries its reason — "no commercial AIS is
configured" is only useful next to "AISStream was rejected because its licence
does not permit commercial use", because the second sentence tells an operator
what to buy.

**Source time is not ingest time.** A forecast issued six hours ago and fetched
thirty seconds ago is six hours old. Freshness is computed from when the
provider observed it.

**An unknown age is not a fresh one.** Where a payload carries no timestamp, the
observation reports `UNKNOWN` rather than a number derived from `now`. This is
not hypothetical: the GDELT bundle carries no time field, and the first version
of that adapter stood `now` in for it and reported a two-day-old artefact as
`LIVE`.

**An adapter that cannot run returns nothing.** It never substitutes demo data.
An adapter that, finding no API key, quietly served the replay would keep the
screen working and keep it saying LIVE.

**Secrets stay on the server.** Adapters read keys from the environment. The API
exposes provider *status*, never provider configuration.

## Deployment modes

| Mode | Non-commercial sources | Redistribution required |
|---|---|---|
| `RESEARCH` | eligible | no |
| `DEMO` | eligible, attribution enforced | no |
| `COMMERCIAL` | **ineligible** | no |
| `GOVERNMENT` | **ineligible** | **yes** — output is shared between agencies |

## Traffic mode

The claim most likely to be misread, so it is answered from the adapter's own
availability rather than a flag:

| Condition | Mode |
|---|---|
| Observed AIS receiving | `LIVE_AIS` |
| `RESEARCH`/`DEMO`, no observed AIS | `SIMULATED_TRAFFIC` |
| `COMMERCIAL`/`GOVERNMENT`, no eligible source | `UNAVAILABLE` |

A configured `AISSTREAM_API_KEY` **does not** produce `LIVE_AIS` in this build,
because the websocket client is not implemented. The seam, the gating and the
status exist; the socket does not, and the product says so.

## Status vocabulary

| Term | Meaning |
|---|---|
| `AVAILABLE` | Configured, reachable, returning observations here |
| `CONFIGURABLE` | Seam exists; needs a key or an endpoint |
| `PLANNED` | Named, with no adapter. Nothing reads it |
| `UNAVAILABLE` | Known and not usable here — wrong licence, or dead |
| `LIVE` | Observed within this capability's live window |
| `CACHED` | Older than live, inside the staleness threshold |
| `STALE` | Beyond the threshold |
| `EXPIRED` | Past the validity the provider stated |
| `UNKNOWN` | The payload carried no timestamp |
| `SIMULATED` | Modelled, not observed. Labelled wherever drawn |
| `SCHEMATIC` | Representative geometry, not surveyed |
| `ASSUMPTION` | A user-entered scenario value, never mixed with observed rates |

## Adapters shipped in this build

| Capability | Provider | Status | Notes |
|---|---|---|---|
| `weather` | Open-Meteo | `AVAILABLE` | Reads the pipeline's forecast artefact |
| `events` | GDELT | `AVAILABLE` | Reads the news bundle; timestamp basis is the artefact write time |
| `ais` | AISStream | `CONFIGURABLE` | Gated by licence *and* key; socket not implemented |

Registered with a licence and read by nothing yet: `marine`, `disaster`,
`seismic`, `fire`, `vessel_registry`, `port_stats`, `geography`.

See [DATA_SOURCES.md](DATA_SOURCES.md) for the full provider matrix.
