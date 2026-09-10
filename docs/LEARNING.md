# Learning

How India PortWatch finds out it was wrong, and what it does about it.

---

## The ledger

Nothing may learn from an outcome it did not record at the time it made the
claim. That single rule drives the schema.

```
PredictionRecord    a numerical or probabilistic claim + its eventual outcome
DecisionRecord      a recommendation + whether it was taken + what it was worth
EventOutcomeRecord  a Global Eye claim + whether the thing happened
ReliabilityRecord   a learned weight for one contributor in one context
PolicyRecord        a learned policy + its promotion state and evidence
```

### Three properties the store enforces

**A claim is written before its outcome exists.** `issued_at` and `valid_at` are
separate fields, and an observation arriving later updates only the observation
columns. `record_prediction` on a resolved row raises:

```python
LedgerError: prediction pred-5cf5e4b420070d68 is resolved and cannot be rewritten
```

Rewriting a claim after seeing the answer is the single most damaging thing a
learning system can do to itself, so it is refused rather than warned about.

**Context is stored, not re-derived.** Reliability is learned per context. If the
context were recomputed at scoring time from today's data, the weights would be
fitted on information the model did not have. Every record therefore carries the
context that was true when it was issued: port, region, horizon, HSMM regime,
weather regime, event regime, source provenance state, source age, season.

**Ids are content-derived.** `PredictionRecord.make_id` hashes the domain,
target, subject, valid instant and model, so re-running the pipeline over the
same window updates rows rather than accumulating near-duplicates. A ledger that
double-counts looks more confident than it is.

Every write also appends to `ledger_audit`, so a row's history is reconstructable.

---

## Scoring

Only proper rules, so honesty about uncertainty is the way to win rather than a
cost. If Global Eye were scored on accuracy alone, the way to win would be to
claim 0% or 100% on everything.

| Claim kind | Scored by |
|---|---|
| Continuous | signed error, absolute error, RMSE, bias, interval coverage against nominal |
| Binary | Brier score, log loss, calibration bins, confusion at an explicit threshold |
| Quantile | pinball loss |

Probabilities are clipped to `[1e-6, 1-1e-6]` before the logarithm, so a
confident miss costs a large but finite amount. Without that, one wrong 0.0
makes the mean log loss infinite and the diagnostic useless.

**Skill is reported against a reference the claim has to beat.** For binary
claims that is the base rate — the Brier score of always predicting the
climatology. A negative skill score means the claims carry no information the
climatology did not, and it is reported as such rather than hidden.

Calibration uses ten equal-*width* bins rather than equal-count, so a bin's label
("claims we called 70%") means the same thing across runs. Expected calibration
error is the count-weighted mean gap; maximum calibration error is reported
alongside it, because the worst single bin is what actually burns an operator.

---

## Contextual reliability

The existing forecast stack already learns global and per-horizon ensemble
weights during walk-forward fitting. This layer does something complementary: it
learns, from resolved ledger rows only, how much a named contributor deserves to
be trusted **in a specific context**, and exposes that as a multiplier.

A weather expert well calibrated on the west coast in the pre-monsoon can be
badly biased on the south-east coast at +24 h during an active monsoon. Blending
those into one number hides both.

### Contexts, most specific first

```
port_code | horizon_hours | weather_regime
port_code | horizon_hours
region    | horizon_hours
horizon_hours
port_code
global
```

`ReliabilityTable.weight_for` walks them from most specific to least and returns
the first with enough evidence, together with the record it came from — so the
UI can show *which slice* justified the adjustment rather than an unexplained
multiplier.

### Three rules that make the fit defensible

**Leakage.** `fit_reliability` takes an explicit `as_of` barrier. A row observed
at or after it raises `LeakageError` rather than being skipped:

```python
LeakageError: prediction pred-… was observed at 2026-09-04T06:00:00+00:00,
at or after the as_of barrier 2026-09-01T00:00:00+00:00; fitting on it would leak
```

Raising rather than skipping is deliberate. A silent skip is how a leakage bug
survives a code review, and a reliability table fitted on the future would make
every downstream benchmark meaningless while looking like an improvement.

**Shrinkage.** Weights shrink toward 1.0 with a prior strength of 24
observations, so a context earns influence over its weight only as evidence
accumulates. Nine bad rows do not switch an expert off. Below 8 resolved rows a
context is *reported* — the dashboard should show the system is watching it —
but never applied.

**Bounded movement.** Weights are clamped to 0.35–1.60 and move at most 0.12 per
update. One bad monsoon week cannot silence a contributor, and recovery is
equally gradual.

### The weight itself

A contributor's raw weight is its error relative to *its peers in the same
context*, not to an absolute target:

```
raw = sqrt(peer_mean_MAE / own_MAE)
```

A context where everything is hard does not penalise everyone; what matters is
who is worse than the room. Halving the error roughly doubles the weight,
doubling it roughly halves it, and the square root damps the response so a single
noisy context does not swing it.

---

## Error attribution

"The model was wrong" is not an answer an operator can use.

For a weighted blend, the decomposition is exact:

```
predicted = Σᵢ wᵢ · sᵢ
y − predicted = Σᵢ wᵢ · (y − sᵢ)
```

So contributor *i* accounts for `wᵢ · (y − sᵢ)` of the miss. `attribute()`
computes that identity and `verify_decomposition()` asserts it closes. There is
no room in it for an invented percentage.

Two consequences:

- **No signals, no attribution.** If a prediction's `features` and
  `contributions` were not recorded, `attribute()` returns `available=False` with
  the reason, and the UI must say the attribution is unavailable rather than draw
  a plausible bar chart.
- **The residual is its own term.** Weights that do not sum to one, or a
  post-blend calibration step, leave error the contributors do not explain. It is
  reported separately rather than smeared across them, because a blend that does
  not close is itself a finding.

Misses are ranked by Brier score for binary claims and absolute error for
continuous ones — a 0.9 claim that failed and a 0.55 claim that failed are not
equally wrong.

---

## The Outcome Agent

One pass, four steps, in this order:

1. **Resolve.** Every open claim whose `valid_at` has passed is matched against
   an observation and scored with the proper rule for its kind. A claim about
   tomorrow simply has no observation today; pending is reported as pending, not
   as an error, because a count that treats it as one trains operators to ignore
   the number.
2. **Score.** Resolved rows are aggregated into calibration and error reports,
   sliced by domain, model, horizon and port.
3. **Attribute.** The worst misses are decomposed.
4. **Recalibrate.** Reliability is refitted from resolved rows only, behind a
   leakage barrier, and written back with the before-and-after.

The observers are **injected**, not imported. The agent never decides for itself
what "actually happened" means: in the pipeline they read the observed panel and
the event feed; in tests they are deterministic stubs; in a deployment they could
read a port authority's own record.

### Event claims past their horizon

An unresolved event claim past its horizon with no confirming observation
resolves as a **measured non-event**:

```python
resolve_event_outcome(id, occurred=False, source="horizon elapsed with no confirming observation")
```

Refusing to make that call would quietly drop every false alarm from the
calibration — exactly the rows that matter most. A false alarm is defined as a
*confident* claim (≥ 0.5) that did not happen; below that the claim was hedged
and the operator was told so.

---

## Backfill

A freshly cloned repository has an empty ledger, which is honest but leaves every
calibration screen saying "unavailable". `backfill_forecasts` fills it with real
history rather than generated data.

`outputs/forecasts/walk_forward_predictions.csv` already holds precisely what a
ledger row and its outcome are: for each port, origin and horizon, what every
model predicted and what was observed — produced under the evaluation's own
leakage discipline, so the forecast at origin *t* used nothing after *t*.

The attribution is exact by construction. The adaptive ensemble is a weighted
blend of its members, so the member models' predictions become the contributor
signals and the fitted weights from `ensemble_weights.json` become the
contributions. The most specific weight set in force is used — per regime, then
per horizon, then global — because using the global set everywhere would make the
decomposition close only on average.

Measured on the shipped run, 4,000 claims:

| | |
|---|---:|
| Mean absolute error | 6.33 |
| Bias | −0.82 |
| Interval coverage | 0.881 |
| Nominal coverage | 0.800 |
| Reliability weights fitted | 459 |

> These figures are **not** the headline benchmark in the README. That is a
> separate evaluation (`src.evaluation.model_benchmark`) over a different panel
> and horizon set. This is the walk-forward evaluation across horizons 1–10 for
> the most recent window, loaded into the ledger so the learning screens have
> real history. Do not conflate them.

---

## Event calibration

Turning `severity × corroboration` into a percentage that means something.

1. Bucket resolved outcomes by category and by raw score (four bands).
2. Within each bucket, the observed frequency *is* the calibrated probability —
   that is the definition.
3. Shrink toward the category base rate, and the category rate toward the global
   rate, with an explicit prior strength.
4. Enforce monotonicity: a higher raw score must never map to a lower
   probability. Small samples routinely produce a dip in the middle band, and no
   operator would accept a more severe, better corroborated event being shown as
   less likely.

Below 20 resolved outcomes overall, **no probability is emitted at all** — the
UI shows severity and confidence and says why. A product that prints "72%" from
four historical observations is lying with a decimal point.

Probabilities are clamped to `[0.02, 0.97]`. A categorical claim about the future
is not certain, and a zero would make the log loss on a surprise infinite.

---

## Operational learning

Recommendations go into the decision ledger with what they claimed they would
achieve, and are resolved with what happened and whether the operator took them.

`ACTION_NOT_TAKEN` is as valuable as `ACTION_TAKEN`: it is the only way to see
whether operators trust the system. **Take-up rate is reported next to reward**,
because a recommendation nobody accepts has no operational value however good its
simulated reward looks.

The advisory workflow feeds this automatically: accepting resolves the decision
as taken, declining as not-taken, and the reason the controller or master gave is
kept with it.

---

## Reading the dashboard

`/admin/learning` shows, in order:

1. What the ledger holds and how much has resolved
2. Forecast accuracy, with coverage against nominal stated in words
3. **Why was PortWatch wrong** — the largest misses, decomposed, with the
   reliability changes that followed
4. Reliability weights with before-and-after, sample counts and bias
5. Event calibration — or the reason it is unavailable
6. Decision take-up
7. Policies and their promotion state, including the rejected ones and why

A dashboard that only showed successes would be marketing.
