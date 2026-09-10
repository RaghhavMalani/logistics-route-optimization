# India PortWatch — the 2-minute demo

One job: show a maritime operations system that closes the loop — it observes,
explains, forecasts, simulates, decides, acts under human approval, and then
comes back to check whether it was right.

**The spine:** `OBSERVE → UNDERSTAND → FORECAST → SIMULATE → DECIDE → ACT → LEARN`

Every screen answers "where did that number come from", and where there is no
measurement it says so instead of drawing one.

---

## Before you start

```bash
# 1. Build the artefacts (about two minutes; add --benchmark for +1 min)
python run_award_demo.py --source portwatch --model ensemble

# 2. Confirm the twin is coherent before anyone watches
python scripts/verify_artefacts.py

# 3. Serve
uvicorn backend.app.main:app --port 8000        # terminal 1
cd india-portwatch-terminal && npm run dev      # terminal 2
```

`india-portwatch-terminal/.env` must contain:

```
VITE_PORTWATCH_API_BASE=http://localhost:8000/api
```

Sanity check before the room fills up:

```bash
curl -s localhost:8000/api/health | python -m json.tool | head -30
```

`intelligence` should read `live` or `cached`. If it says `not_ready`, the
pipeline has not run. Then check the learning history the last segment depends
on:

```bash
curl -s localhost:8000/api/learning/summary | python -m json.tool | head -20
```

`resolved` should be in the thousands. The pipeline backfills it from its own
walk-forward history at the end of every run.

Sign in as **`admin@portwatch.demo`** (password `portwatch`) — the demo starts on
the national picture and switches accounts twice. Have the other three logins to
hand:

| Account | Role | Lands on |
|---|---|---|
| `admin@portwatch.demo` | National Command | `/admin/radar` |
| `port@portwatch.demo` | Port Authority (Chennai) | `/port/overview` |
| `company@portwatch.demo` | Shipping Company | `/company/overview` |
| `vessel@portwatch.demo` | Vessel Operator | `/vessel/overview` |

---

## 00:00–00:20 — National Radar

> *"India's maritime network, with its own status visible."*

Open `/admin/radar`.

The map fills the screen: every major Indian port, the weather composite already
on, simulated traffic moving on the water.

> "One screen. Ports coloured by the model's own risk assessment, the weather
> composite underneath, and traffic on top."

Point at the status strip.

> "And notice what it says about itself. The model that produced this, the
> forecast origin, how old it is, and — this matters — **what each layer
> actually is**. Port state: CACHED_LIVE, because IMF PortWatch publishes with a
> lag. Weather: LIVE. Traffic: SIMULATED_TRAFFIC, because we hold no AIS licence
> and will not pretend otherwise."

Grab the weather timeline and scrub it to **+24h**, then press play.

> "This is the same composite forward in time — wind, rain, wave and storm risk
> together, out to 72 hours. Nobody has to know which field to pick to see
> weather is coming."

Finish on **WHO NEEDS INTERVENTION** bottom-left.

> "And the panel already answers the question: which port, what action, the
> day-1 congestion with its 80% band, and the regime with its expected remaining
> duration."

---

## 00:20–00:40 — Global Eye

> *"A disruption appears in the Red Sea."*

Go to `/admin/global-eye`.

> "Global Eye is not news on a map. It is a chain, and every hop is computed."

Click the Red Sea / Bab-el-Mandeb event. Read the chain out loud as it expands:

```
EVENT  →  CHOKEPOINT  →  TRADE LANE  →  VESSELS  →  PORTS  →  IMPACT  →  ACTIONS
```

Three things to point at, in this order:

1. **Corroboration.** "Nine articles from six outlets, merged into one event —
   same category, same chokepoint, within 36 hours, and the headlines overlap.
   Confidence is built from *distinct outlets*, not article count."
2. **The honesty line.** "Severity is a labelled heuristic and the probability
   says **unavailable** — twenty-six claims are committed with their horizons and
   none has elapsed yet. It shows severity and corroboration instead of inventing
   a percentage."
3. **The lanes.** "Europe–India via Suez, 4,650 nautical miles, with a
   Cape of Good Hope alternative at plus 3,750. Hormuz has **no** alternative,
   and that lane is weighted higher for it, not lower."

---

## 00:40–01:00 — Shipping Company

> *"These vessels are exposed."*

Sign out, sign in as `company@portwatch.demo`. It lands on **Fleet Command**.

> "Same event, one carrier's problem."

Point at the right rail, top.

> "**ACTION REQUIRED** is the first thing on the screen — before the fleet list,
> before the map. Each row: the vessel, the exposure, what to do, and **the
> deadline by which the option closes**."

Then scroll to **Monitor only** on `/company/risk`.

> "And this is the part that makes it operational. These vessels are just as
> exposed — but they are already inside the strait. A diversion is no longer
> available, so they are listed separately instead of being mixed into a queue of
> things you cannot fix. Telling an operator to divert a committed vessel would be
> worse than saying nothing."

Open one vessel.

> "Route options with the detour in nautical miles and hours, the exposure on
> each, and the routing labelled non-navigational — it guarantees water, not a
> passage plan."

---

## 01:00–01:20 — Agentic AI

> *"PortWatch gathers weather, route, port and fleet evidence — and a human still
> decides."*

Go to `/admin/agents`. Run **"Which of my vessels are exposed and what should I
do?"**

Do **not** talk about the answer first. Talk about the trace.

```
GLOBAL EYE  events ✓  exposure ✓
FLEET       fleet ✓  risk ✓
ROUTE       optimize ✓
CRITIC      APPROVED
```

> "Five tool calls across three agents, in sequence, each feeding the next. Every
> step names the module that computed it. Expand any one and you get the actual
> evidence, not a summary of it."

Point at the access column.

> "Four levels — READ, SIMULATE, PROPOSE, EXECUTE. **No agent in this system
> holds an EXECUTE ceiling**, and the browser suite asserts that. The most any
> agent can do is produce a draft."

Point at the Critic verdict.

> "Then a Critic reviews it against eight checks before a human sees it —
> including whether the action is *still available*. It can only lower
> confidence, never raise it."

Then, briefly, the confidence figure.

> "0.30, not 0.70, because one source was stale. Confidence is bounded by the
> weakest link in the chain, not averaged."

---

## 01:20–01:40 — 3D Port Twin

> *"Arrival changes propagate into berth and yard operations."*

Sign in as `port@portwatch.demo`, go to `/port/twin`.

The banner is the first thing you say, not the last:

> "**SCHEMATIC DIGITAL TWIN — NOT A SURVEYED PORT PLAN.** Berth count, capacity,
> occupancy and crane rates are real. The arrangement is generated. We are not
> claiming to have surveyed Chennai."

Click a berth, then a yard block.

> "Length, draught, what may be handled there, which cranes can reach it —
> cranes share a rail, so they serve their berth and its neighbours. Yard block:
> slots, occupancy, mean dwell, reefer plugs."

Step time to **+12h**.

> "That is a real forward run of the discrete-event simulator, not an
> interpolation. And this is the same object the optimisers and the RL
> environment use — a 3D port that rendered its own idea of the terminal would be
> an illustration. This one is an inspector."

Switch overlay to **crane workload**, then **storage pressure**.

> "Colour is state, not decoration. The yard is above 80% here, and above 80%
> every productive move needs re-handles — which is why the arrival change
> matters."

---

## 01:40–01:55 — Decision

> *"The controller approves a new arrival advisory."*

Stay in the port account, go to `/port/advisories`. Press **Draft from the engine**.

> "The system ran the twin, found the calls that will wait more than an hour, put
> each recommendation through the Critic, and drafted advisories for the
> survivors. They are **drafts**. The vessel cannot see them."

Open one draft.

> "The number in it came from the simulator. The Critic's verdict is attached.
> And the recipient sees nothing until a named human presses issue."

Press **Issue**. Then switch to `vessel@portwatch.demo` → `/vessel/advisories`.

> "Now it exists for the master, who can accept, decline with a reason, or
> request a change. Eleven states, role-gated, and every transition is in the
> audit trail with who did it and when."

Accept it, and go back to the port account.

> "The port sees the response. And the acceptance just resolved a decision record
> in the ledger — which is the next screen."

---

## 01:55–02:00 — Learning

> *"PortWatch later compares its prediction with reality and updates reliability."*

Go to `/admin/learning`.

> "Four thousand resolved claims. Mean absolute error 6.33. Interval coverage
> 0.881 against a nominal 0.800 — slightly conservative, and it says so.
> **Why was PortWatch wrong** decomposes the largest misses exactly — the weights
> and the residual close to the error, no invented percentages — and the
> reliability weights that changed as a result are shown with their before and
> after."

Last line, on the policy table:

> "And the learned policy is sitting at **REJECTED**, with the reason: it beats
> first-come-first-served by 5.6% but the hand-written optimiser by only 0.8%,
> which does not clear the gate. A system that only showed its successes would be
> marketing."

---

## If you have four minutes instead of two

Two screens the short version skips, both worth it with a technical audience.

### Model Intelligence — `/admin/model`

Headline row: leading model, MAE, **skill against naive persistence**, 80%
coverage.

> "Four expanding walk-forward folds, twenty-eight thousand out-of-fold
> predictions, every model on identical folds. The ensemble beats a random walk by
> 8% and is the only model with a calibrated interval — 0.807 against a nominal
> 0.800."

Switch the drilldown to **HORIZON**.

> "Here is the honest bit. Nothing beats persistence at one day on a smoothed
> index — our first benchmark run had persistence beating every model at every
> horizon. So we made persistence a first-class ensemble member and fitted the
> blend weights per horizon, out-of-fold."

Point at **ENSEMBLE POLICY**: 80% persistence at day one, shifting to the models
by day six.

> "Nobody wrote that schedule. It was fitted, and it recovers the physics."

### Decision Room — `/admin/scenarios`

Select **Hormuz closure**, intensity 1.0.

```
HORMUZ CLOSURE  →  no maritime bypass, freight +38%
      →  MUNDRA / KANDLA / JNPA exposure 0.55 / 0.45 / 0.45
      →  congestion +8.4 / +6.9 / +6.9,  expected wait +2.8h
      →  ACTION on the most exposed port
      →  EXPECTED BENEFIT in hours
```

> "These deltas are the difference between two forecasts the system actually
> produced — the live one, and the same one after the shock propagates through
> the measured lane-exposure graph. Mundra moves most because it is the most
> Hormuz-exposed port in the graph, not because someone typed a bigger number for
> it. Vizag barely moves — it ships through Malacca."

---

## The questions you will be asked

**"Is the ship traffic real?"**
No, and the map says `SIMULATED_TRAFFIC` on every surface that shows it. It is a
deterministic replay engine behind a `TrafficSource` interface — the seam a
licensed AIS feed plugs into. Nothing on the water is an observed position, and
we would rather say that than lose the argument later.

**"Is the 3D port real?"**
The counts are; the arrangement is not. Berth count and capacity index come from
the port registry, occupancy from the observed snapshot, crane rates from
published envelopes. Positions are generated, and the banner says
SCHEMATIC and does not scroll away.

**"So what is the AI actually doing, if the numbers are all deterministic?"**
Orchestrating. An agent decides which tools to call and in what order, carries
results between them, reconciles disagreement and absence, and reports. Every
figure in its output came out of a named module — `ToolSpec.computed_by` is
required and a test fails any tool shipped without one. If a language model wrote
the recommended arrival time, that number would be unfalsifiable, and the entire
learning loop downstream of it would be measuring fiction.

**"Can it act on its own?"**
No, and it is enforced in two independent places. Every agent is constructed with
a ceiling of PROPOSE at most, so an EXECUTE tool is unreachable — over MCP at the
default ceiling it is not even listed. And an EXECUTE call additionally requires
an approval context whose `human_verified` flag is set, which only
`approval_from_session` can set, which requires an authenticated session. There is
deliberately no path from agent output to that function.

**"Is there reinforcement learning in this?"**
Yes, and it is a contextual bandit over scheduling rules — not PPO, because the
problem does not need it and the honest thing is to start with the simplest thing
that could work. It trains inside the twin, on training seeds disjoint from the
evaluation seeds, and it is currently **REJECTED** by the promotion gate. That is
the demonstration: the gate works, and it did not approve our own learned policy.

**"How do you know the model is any good?"**
`python -m src.evaluation.model_benchmark --folds 4`. Expanding walk-forward,
identical folds for every candidate, ensemble weights fitted only on out-of-fold
predictions, scored on the same rows as the baselines. MAE 7.43 against
persistence 8.08, with calibrated intervals. The benchmark also reports the cells
where the ensemble loses — persistence wins in the CONGESTED regime, and that is
printed in `regime_benchmark.csv`.

**"Where does the learning history on the last screen come from? Is it generated?"**
No. It is backfilled from `outputs/forecasts/walk_forward_predictions.csv` — the
run's own walk-forward evaluation, which already holds exactly what a ledger row
and its outcome are, produced under the evaluation's leakage discipline. The
member models become the contributor signals and the fitted ensemble weights
become the contributions, so the attribution closes by construction.

**"Why does the event probability say unavailable?"**
Because 26 claims are committed and none has elapsed, and the threshold is 20
resolved outcomes. A product that prints "72%" from four historical observations
is lying with a decimal point. The claims are written *before* the world answers,
with horizons, which is the only way that screen can ever become available.

**"Isn't the ensemble just tuned until it won?"**
The weights are chosen by minimising pinball loss on out-of-fold predictions
only, never on the block they are scored on. `fit_reliability` goes further and
*raises* on a row observed at or after its `as_of` barrier rather than skipping
it — a silent skip is how a leakage bug survives code review.

**"What would you do next?"**
A licensed AIS feed behind `TrafficSource`, surveyed geometry behind the layout
generator, and port-authority dwell times to replace the berth-wait proxy. All
three are provider implementations, not rewrites — which is the point of having
built the seams.

---

## If something breaks mid-demo

| Symptom | Cause | Fix |
|---|---|---|
| Every screen says *Intelligence API unavailable* | Backend not running | `uvicorn backend.app.main:app --port 8000` |
| Screens load but say *has not been exported* | Pipeline never ran | `python run_award_demo.py --source portwatch` |
| `/admin/learning` says the ledger is empty | Learning pass skipped | `curl -X POST localhost:8000/api/learning/backfill` |
| Model Intelligence shows *No benchmark artefacts* | Benchmark not run | `python -m src.evaluation.model_benchmark --folds 4` |
| The twin renders nothing | Three.js chunk blocked | Check the console; the scene is lazy-loaded and will report the failure |
| Everything reads `STALE` | PortWatch cache is old | `python run_award_demo.py --source portwatch --refresh` |
| No network in the room | Expected | `python run_award_demo.py --source portwatch --offline` — it runs on cache and labels itself accordingly |

**Rehearse the account switches.** Three of the seven segments change role, and
fumbling a sign-in costs more of the two minutes than any screen does.
