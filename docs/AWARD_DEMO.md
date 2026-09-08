# India PortWatch — Award Demo Playbook

## The 15-second thesis

**India PortWatch is a predictive maritime digital twin for Indian ports.** It
fuses vessel activity, weather, news/geopolitical events, trade demand,
capacity pressure and anomaly detection; infers the current operating regime;
forecasts the next 10 days probabilistically; then recommends operational and
routing actions.

The important distinction is not “we have many agents.” Every specialist emits
bounded numerical features and confidence, and those signals enter the same
leakage-safe state/forecast path. The UI exposes freshness, uncertainty and
source confidence instead of presenting generated text as ground truth.

## One-command showcase

```bash
python run_award_demo.py --source portwatch --model ensemble --refresh
```

If the live source is unavailable, omit `--refresh` to use the last known-good
PortWatch cache. For a fully deterministic offline demo:

```bash
python run_award_demo.py --source sample --model ensemble
```

Serve the backend and terminal in separate shells:

```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
cd india-portwatch-terminal
VITE_PORTWATCH_API_BASE=http://localhost:8000/api npm run dev
```

For a continuously refreshing installation:

```bash
python scripts/live_refresh.py --interval-minutes 15 --source portwatch --model ensemble
```

The worker never deletes the previous cache before a cycle succeeds, so a
temporary external-data outage leaves the last known-good intelligence visible.

## 90-second judge demo

### 0–15s — National Radar

Open the National Radar. Point out:

- the 5-second data-fusion refresh pulse;
- live signal count and last-fusion timestamp;
- national logistics stress computed from current port and alert state;
- ranked, clickable priority ports;
- AIS/SAR/weather/event overlays on one operational map.

Do **not** start by explaining models. Start with the operational question:
**“Which port needs intervention right now?”**

### 15–35s — Port Cockpit

Open the highest-pressure port. Show the current regime, confidence and 10-day
uncertainty. Explain that the forecast is a distribution (q10/q50/q90), not a
single magic number.

### 35–55s — Model Intelligence

Show the specialist pipeline:

1. Weather Expert
2. News + Geopolitical Expert
3. AIS / Port-Ops Expert
4. Trade Demand Expert
5. Capacity Agent
6. Anomaly Agent
7. HSMM Regime Engine
8. Adaptive TFT + GBM Ensemble
9. Decision + Route Engine

Each expert score/confidence in the API cache is calculated from its latest
artefact. The HSMM card is sourced from the actual HSMM output, not recreated
from the forecast.

### 55–75s — Decision Room

Trigger a scenario such as Hormuz, Suez, Malacca or a severe weather event.
Compare the baseline and shock-adjusted forecast, then show the recommended
operational action and alternate arrival/routing choice.

### 75–90s — Credibility close

End with three proof points:

- leakage-safe transforms and expanding-window evaluation;
- calibrated probabilistic intervals and model-disagreement confidence;
- explicit provenance/freshness rather than hidden mock fallbacks.

Then say what the system optimizes for: **earlier intervention, lower vessel
waiting time, safer arrival windows and better capacity utilization.**

## New intelligence added in the award build

### Capacity Agent

Estimates berth/yard squeeze from utilization, queue pressure, turnaround,
queue acceleration and throughput degradation. Its queue baseline is shifted,
so future information cannot enter a historical feature.

### Anomaly Agent

Uses a rolling robust median/MAD reference distribution per port to detect
abnormal congestion, delay, throughput and queue behaviour. References are
shifted one day, making the detector leakage-safe.

### Adaptive Ensemble

TFT captures multi-horizon nonlinear temporal interactions; the GBM provides a
strong, lower-variance quantile baseline. The ensemble uses inverse benchmark
MAE when a benchmark artefact is available and conservative weights otherwise.
Confidence decreases when the models materially disagree.

This is deliberately preferable to adding several redundant deep models just
to increase the model count.

## Accuracy evidence to show judges

Run the existing benchmark/evaluation path before the final presentation and
put the resulting numbers directly in the Model Intelligence screen or report:

- MAE and RMSE versus naive persistence;
- q10/q50/q90 pinball loss;
- 80% interval empirical coverage;
- metrics by horizon (Day +1 … Day +10);
- metrics by port;
- metrics by HSMM regime;
- ensemble versus TFT-only versus GBM-only;
- calibration before/after conformal adjustment.

Do not claim a percentage improvement until it is measured on the final data
snapshot. A smaller, reproducible improvement beats an impressive invented
number in a capstone review.

## Reliability checks

```bash
python -m unittest tests.test_award_intelligence -v
```

The tests cover anomaly-spike detection, capacity-pressure response and
ensemble quantile monotonicity/disagreement reporting.

## Production configuration

The backend accepts a deployment CORS regex through:

```bash
PORTWATCH_CORS_REGEX='https://your-frontend-domain\.example'
```

The terminal backend base URL is configured with:

```bash
VITE_PORTWATCH_API_BASE=https://your-api-domain.example/api
```

`GET /api/health` reports model/cache freshness, model identity, forecast
origin, port count and pipeline step count. A cache older than 30 minutes is
reported as stale.

## What still needs real credentials/data for a production-grade deployment

- continuous raw AIS tracks rather than aggregated PortWatch port calls;
- licensed/high-frequency terminal berth and yard feeds where available;
- production weather/ocean credentials for the chosen provider;
- a deployment provider/domain and persistent worker process.

The demo remains functional without those integrations, but they should be
labelled by provenance rather than represented as live when they are not.
