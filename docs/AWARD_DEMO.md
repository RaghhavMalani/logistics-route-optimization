# India PortWatch — 90-second demo

The demo has one job: show that this is a working maritime digital twin whose
every number is traceable, not a dashboard with a model behind it.

**The spine of the story:** *observe → understand → forecast → simulate →
decide → route*, and at every step, "here is where that number came from".

---

## Before you start

```bash
# 1. Build the artefacts (about 4 minutes with the deep model, 90 seconds without)
python run_award_demo.py --source portwatch --model ensemble --benchmark

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
curl -s localhost:8000/api/health | python -m json.tool | head -20
```

`intelligence` should read `live` or `cached`, and `benchmark.available` should
be `true`. If it says `not_ready`, the pipeline has not run.

---

## The 90 seconds

### 0:00–0:15 — National Radar: *which port needs intervention?*

Open the terminal at `/`.

> "This is every major Indian port, live. The map is coloured by the model's own
> risk assessment, and the panel bottom-left already answers the question."

Point at **WHO NEEDS INTERVENTION**. Read the line aloud — it names the port,
the recommended action, the day-1 congestion with its 80% band, the expected
berth wait and the regime with its expected remaining duration.

> "One panel, one answer, with the uncertainty attached."

Then point at the status strip along the top.

> "And notice what it says about itself: the model that produced this, the
> forecast origin, how old that is, source readiness, and how much the models
> disagree. If this were stale, it would say STALE — it does, because IMF
> PortWatch publishes with a lag. Nothing here pretends to be real-time."

**Hover a port** to show the compact operational tooltip. **Click it.**

### 0:15–0:30 — Port Cockpit: *why?*

> "Now the digital twin of one port."

Walk left to right:

- **NOW** — observed congestion, berth wait, daily port calls, queue buildup,
  throughput. Measured, not forecast.
- **SPECIALIST PRESSURE** — capacity, berth pressure, arrival clustering,
  anomaly, disruption, data quality. Each a bounded 0–1 signal.
- **NEXT 24H / 10-DAY FAN** — the quantile band, widening with horizon.
- **HSMM REGIME** — the state, its probabilities, days in state, expected
  remaining duration, transition risk.

> "And this strip is the whole chain: raw signal, expert, regime, forecast,
> decision — each with its own confidence and its own timestamp."

Finish on **WHAT SHOULD WE DO**.

> "A specific instruction, its expected delay saving, the ranked factors that
> drove it, and the fallback if it can't be executed. No language model chooses
> this — it is a deterministic rule cascade over the forecast distribution."

### 0:30–0:45 — Model Intelligence: *how do we know?*

> "This is the part most projects can't show."

Point at the headline row: leading model, MAE, **skill against naive
persistence**, 80% coverage.

> "Four expanding walk-forward folds, twenty-eight thousand out-of-fold
> predictions, every model on identical folds. The ensemble beats a random walk
> by 7.6% and is the only model with a calibrated interval — 0.806 against a
> nominal 0.800."

Switch the drilldown to **HORIZON**.

> "Here's the honest bit. Nothing beats persistence at one day on a smoothed
> index — our first benchmark run had persistence beating every model at every
> horizon. So we made persistence a first-class ensemble member and fitted the
> blend weights per horizon, out-of-fold."

Point at the **ENSEMBLE POLICY** table.

> "80% persistence at day one, shifting to the models by day six. Nobody wrote
> that schedule — it was fitted, and it recovers the physics."

Then the calibration table and the provenance panel.

> "And every source, with what it is, when it was observed, and whether it's
> live, cached, stale or synthetic."

### 0:45–1:10 — Decision Room: *what if Hormuz closes?*

Select **Hormuz closure**, intensity 1.0.

> "Baseline versus shock. These deltas are the difference between two forecasts
> the system actually produced — the live one, and the same one after the shock
> propagates through the measured lane-exposure graph."

Read the propagation chain left to right:

```
HORMUZ CLOSURE  →  no maritime bypass, freight +38%
      →  MUNDRA / KANDLA / JNPA exposure 0.55 / 0.45 / 0.45
      →  congestion +8.4 / +6.9 / +6.9,  expected wait +2.8h
      →  ACTION on the most exposed port
      →  EXPECTED BENEFIT in hours
```

> "Mundra moves most because it is the most Hormuz-exposed port in the graph,
> not because someone typed a bigger number for it. Vizag barely moves — it
> ships through Malacca."

Move the intensity slider and let the numbers respond.

> "And the recommendation is not scenario copy: it's the decision engine re-run
> against the shocked forecast. It even tells you whether the action *changed*
> from the baseline."

### 1:10–1:25 — Decision and route

Point at **RECOMMENDED ACTION UNDER SHOCK**, then jump to **Fleet Board**.

> "Per vessel: intended call, best alternative, and the three numbers that
> justify the choice — ETA difference, risk difference, port-wait difference.
> A reroute is only advised when the modelled waiting saving clears the extra
> steaming with margin. Most of the time it says keep the call, which is the
> correct answer and the one a fake system never gives."

### 1:25–1:30 — Close on auditability

Back to Model Intelligence, or the rail's source panel.

> "Everything you just saw is reproducible from one command, measured by a
> walk-forward benchmark, and labelled with where it came from. Where we don't
> have a measurement — per-vessel AIS, SAR detection — the system says
> UNAVAILABLE instead of drawing something."

---

## The questions you will be asked

**"Is this real data or a simulation?"**
Real. IMF PortWatch satellite-AIS port calls, Open-Meteo surface and marine
weather, GDELT and GDACS events, FRED macro series. `/api/provenance` lists
every source with its observation timestamp and state. Nothing is currently
`SYNTHETIC` on the PortWatch path — and if a feed failed, the affected panels
would say so.

**"How do you know the model is any good?"**
`python -m src.evaluation.model_benchmark --folds 4`. Expanding walk-forward,
identical folds for every candidate, ensemble weights fitted only on
out-of-fold predictions, scored on the same rows as the baselines. MAE 7.47
against persistence 8.08, and calibrated intervals.

**"Isn't the ensemble just tuned until it won?"**
The weights are chosen by minimising pinball loss on out-of-fold predictions
only, never on the block they are scored on. And the benchmark still reports the
cells where the ensemble loses — persistence wins in the CONGESTED regime, and
that is printed in `regime_benchmark.csv`.

**"Why is the TFT worse than a gradient-booster?"**
Because at this data scale it is — 12 ports, about a year of daily history. It
is genuinely better at long horizons (7.00 MAE at +9d against 9.89), which is
why the stacker gives it real weight there and almost none at day 1. Its
intervals are badly calibrated and we say so rather than hiding it behind the
ensemble.

**"Is the scenario engine just multiplying a constant?"**
No — that is exactly what it used to do, and it was replaced. The shock is
applied to the live quantile forecast through elasticities calibrated against
documented analogues, propagated by each port's measured lane exposure, and the
reported deltas are the difference between the two forecasts. `simulate_scenario`
refuses to run at all without a live forecast.

**"What are the agents actually doing?"**
Every specialist writes a CSV under `outputs/expert_features/`, and every one of
those columns is in the HSMM feature matrix and the forecaster's feature list.
`scripts/verify_artefacts.py` fails the build if a specialist column is missing
from the merged panel or was silently suffixed by a duplicate join — which is a
bug this project actually had and fixed.

**"What would you do next?"**
Wire port-authority dwell times to replace the berth-wait proxy, add a
commercial AIS feed for per-vessel tracking, and extend the registry beyond the
13 ports it covers.

---

## If something breaks mid-demo

| Symptom | Cause | Fix |
|---|---|---|
| Every screen says *Intelligence API unavailable* | Backend not running | `uvicorn backend.app.main:app --port 8000` |
| Screens load but say *has not been exported* | Pipeline never ran | `python run_award_demo.py --source portwatch` |
| Model Intelligence shows *No benchmark artefacts* | Benchmark not run | `python -m src.evaluation.model_benchmark --folds 4` |
| Everything reads `STALE` | PortWatch cache is old | `python run_award_demo.py --source portwatch --refresh` |
| No network in the room | Expected | `python run_award_demo.py --source portwatch --offline` — it runs on cache and labels itself accordingly |
