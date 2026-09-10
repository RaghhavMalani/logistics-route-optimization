# Global Eye

World events, and what they do to Indian maritime operations.

Not news on a map. Global Eye is a chain, and every hop is computed from
something measurable:

```
EVENT → CHOKEPOINT → TRADE LANE → VESSEL → PORT → IMPACT → ACTION
```

Where a hop cannot be computed it is reported as unavailable rather than filled
in, and the UI renders the reason.

---

## Ingestion and corroboration

The input is whatever the connectors produced — GDELT article rows, GDACS hazard
rows, the exported `news_bundle.json`. Global Eye consumes their output rather
than opening a second, unaudited network path, so it inherits the existing
provenance recording.

### Classification

Ordered rules, specific phrases before generic ones, so "port strike" classifies
as a strike rather than as unrest. Seventeen categories across six groups:
security, policy, operations, natural, chokepoint, market.

A feed that already typed an item is trusted over the text classifier — the
classifier is the fallback, not the authority. An item that matches nothing is
**not forced into a category**: the ingest report counts it and the UI says how
many items the feed carried that Global Eye could not place.

### Deduplication

This is the part that earns its keep. A single Red Sea incident arrives as
fourteen headlines from nine outlets, and listing all fourteen makes a quiet week
look like a crisis and a crisis look like noise.

Two items merge only when **all four** hold:

1. same category
2. same anchor (chokepoint, else port, else region)
3. within 36 hours of each other
4. headline overlap ≥ 0.34 (Jaccard over content words)

Each condition alone produces obvious false merges: two different strikes in the
same week, or two unrelated stories that both mention "Suez".

Headline dedupe does not need embeddings. The same wire story reprinted by nine
outlets shares most of its nouns; two genuinely different events in the same
strait share few. Anything more elaborate would be harder to explain to an
operator asking why two rows merged.

### Confidence

Built from **distinct outlets**, not article count — four filings from one outlet
is not corroboration. The curve saturates: past about six outlets, more reporting
adds little, because the remaining uncertainty is about what the event *does*,
not whether it happened.

A second independent *feed* (GDACS confirming a GDELT story) counts for more than
a second newspaper.

### Severity

A transparent word-list heuristic, and it is labelled as one everywhere. It is
used because the alternative — asking a language model to assign a number —
would put an invented figure into an operational chain. The number is coarse, its
derivation is visible, and the calibration layer is what turns it into something
with a measured meaning.

Severity across a merged cluster is the **maximum**, not the mean: one outlet
reporting a closure while eight report delays is a closure story, and averaging
it away would hide the case that matters.

---

## Location

Every event states how its position was established:

| Basis | Meaning |
|---|---|
| `reported` | The feed carried coordinates |
| `chokepoint_centroid` | Inferred from the chokepoint it names |
| `port_location` | Inferred from a port it names |
| `unlocated` | No position. Listed in the register, not drawn on the chart |

A coordinate inferred from a chokepoint name is not a geocode, and the inspector
says so under the marker.

---

## Exposure

### Event → lane

The strength of a claim about a lane is the product of three measured things:

```
exposure = severity × confidence × recency_decay
```

Multiplying is the honest combination. A severe but unconfirmed and stale item
should not read as an emergency.

Recency decay is exponential with a half-life of half the category's typical
persistence. An event nobody has mentioned for three half-lives is not deleted —
its outcome is still scored — but it stops driving the live picture, and the
inspector shows the decay weight.

### Lanes

A lane is exposed to a chokepoint if its primary routing transits it. That is a
property of the lane catalogue, not an opinion.

| Lane | Chokepoints | Primary | Alternative | Detour |
|---|---|---:|---|---:|
| Europe ↔ India | Suez, Bab-el-Mandeb | 4,650 nm | Cape of Good Hope | +3,750 nm |
| Mediterranean ↔ India | Suez, Bab-el-Mandeb | 3,300 nm | Cape of Good Hope | +4,600 nm |
| Persian Gulf ↔ India | Hormuz | 1,150 nm | **none** | — |
| East Africa ↔ India | none | 2,400 nm | — | — |
| South-east Asia ↔ India | Malacca | 1,900 nm | Sunda / Lombok | +550 nm |
| Far East ↔ India | Malacca | 3,900 nm | Lombok | +650 nm |
| US East Coast ↔ India | Suez, Bab-el-Mandeb | 8,200 nm | Cape of Good Hope | +2,200 nm |
| US West Coast ↔ India | Malacca | 9,100 nm | Lombok | +550 nm |
| West coast cabotage | none | 620 nm | — | — |
| East coast cabotage | none | 780 nm | — | — |

**A lane with no alternative is weighted higher, not lower.** Hormuz has no
bypass: traffic cannot route around the problem at all, and the row says so.

### Lane → vessel: the timing gate

This is the part that makes the chain operational rather than descriptive.

| State | Recommendation | Why |
|---|---|---|
| Hours to chokepoint > 6, exposure ≥ 0.35, lane has an alternative | `evaluate_diversion` | The option is open and costed |
| Hours to chokepoint ≤ 0 | `monitor` | **Already inside. A diversion is not available** |
| Lane has no alternative | `hold_or_reschedule` | There is nowhere to route to |
| Exposure < 0.35 | `monitor` | Schedule buffer should absorb it |

0.35 is the floor below which no single event recommends a diversion. A caller
asking `portwatch.routing.optimize` for a whole voyage applies its own tolerance
on top — 0.25, 0.40 or 0.60 for low, medium or high — so the same measured
exposure gives a cautious operator more options than a tolerant one, without
either of them changing the measurement.

A vessel three days short of Bab-el-Mandeb can be rerouted; one already north of
it cannot, and telling an operator to divert it would be worse than saying
nothing. The diversion deadline is six hours before the strait, not the strait
itself — a vessel that close is committed in practice.

The Critic independently rejects any recommendation that tries to divert a
committed vessel, so the rule is enforced in two places.

### Vessel → port

Diverted vessels shift their arrival windows, which changes the berth queue at
the destination. Port exposure combines lane-level exposure with the vessels
actually bound there.

Across events, port risk combines with a **noisy-OR**: two independent 0.5
exposures give 0.75, not 1.0, and no amount of piling on events pushes a port
past certainty.

### Actions

Only actions the chain supports are emitted, and each names the measurement that
justifies it. An event with no computable consequence produces **no actions** —
the register simply carries fewer rows, which is the correct outcome when the
evidence is thin.

---

## Calibration

Severity × confidence is not a probability and is never shown as one.

It becomes a percentage only once enough resolved outcomes exist. Until then the
event carries `probability: null` and a `calibrationNote` explaining why, which
the UI renders in place of a number:

> Only 26 event claims have been resolved; 20 are required before Global Eye
> states a calibrated probability. Severity and confidence are shown instead.

See [LEARNING.md](LEARNING.md) for the fitting method, the monotonicity
constraint and the shrinkage.

### Committing a claim

`claims_for()` writes one falsifiable outcome claim per event, with a horizon,
*before* the world answers. Without that, the calibration above would have
nothing to fit on, forever. The pipeline does this at the end of every run.

A claim past its horizon with no confirming observation resolves as a measured
non-event — see LEARNING.md for why that matters.

---

## Company scope

The same chain, filtered to one carrier's voyages. The "Vessels" tab then answers
*what impacts my fleet* rather than *what is happening in the world*, and the
Fleet Command screen splits the answer into:

- **ACTION REQUIRED** — exposed, and something can still be done, with the
  deadline by which the option closes
- **Monitor only** — exposed, already committed, listed so they are not mistaken
  for safe

Mixing the second into the first would send an operator looking for a lever that
is not there.

---

## API

```
GET  /api/global-eye/events        register, with ingest and calibration status
GET  /api/global-eye/events/{id}   the full impact chain for one event
GET  /api/global-eye/exposure      every live event traced, plus aggregated port risk
GET  /api/global-eye/calibration   the fitted calibrator and its scores
POST /api/global-eye/claims        commit a falsifiable claim per current event
```
