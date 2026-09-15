# The flagship demo — two minutes, from "what should we do?" to the revealed outcome

One job: show a system that computes a decision, puts it in front of a human
with every trade-off on the chart, and then lets history mark its answer.

**The spine:** `SENSE → UNDERSTAND → PREDICT → GENERATE OPTIONS → SIMULATE →
OPTIMISE → CRITIQUE → HUMAN DECISION → OBSERVE OUTCOME → LEARN`

Every number on screen is a measurement a simulator produced on a branch of
the observed world. Where there is none, the screen says so — and that is one
of the things you show.

---

## Before you start

```bash
python -m portwatch.demo start --mode DEMO
```

One command. It validates the environment and refuses a configuration that
would mislead, asks the freshness coordinator which artefact has lapsed and
refreshes it (the event register every six hours, the marine grid every hour,
the pipeline export daily — nobody runs `run_award_demo.py --refresh` by hand
any more), starts the API and the terminal, verifies both, and prints the
mode every signal is actually in. The demo starts when the last line reads
`TERMINAL READY`. If the register shows nothing marked ACT SOON, the claims
have lapsed and the coordinator is already refreshing; `python -m
portwatch.demo status` says where it is.

Sign in as `admin@portwatch.demo` (National Command) at the URL the command
prints. Have `port@portwatch.demo` in a second tab.

`python scripts/demo_acceptance.py` before a buyer sees it: thirty-nine
claims, none failing.

## 00:00–00:20 — Sense and understand

`/admin/global-eye`. The action rail ranks what needs intervention.

> "Fourteen headlines about one Red Sea incident became one event with nine
> sources. It reaches Bab-el-Mandeb, the Europe–India lane, six hulls, two
> ports. MV Coromandel is six hours short of the strait and the option closes
> in five hours fifty. Nothing here is a probability the system has not
> earned: severity times corroboration, and it says so."

## 00:20–00:50 — Generate, simulate, optimise, critique

Press **What should we do?** on MV Coromandel.

> "Four options survived. Doing nothing was computed the same way as the
> others, on its own branch: plus thirty hours, exposure 0.68 at the strait.
> The Cape is not offered — the hull has entered the canal side of the lane
> and the routing branches at Gibraltar; it says why. Delay departure is not
> offered because the subject does not declare a departure port. Nothing was
> invented to fill the list."

Click **Compare**, then option **B**, then **A**.

> "The world changes with the option. Solid is the one selected, dashed the
> alternatives, thin and grey the current plan. The ring on the quay is that
> option's yard pressure, not a decoration."

Open **Frontier**.

> "Every point is a real evaluated option. Filled means nondominated. Hollow
> means some other option is no worse everywhere and better somewhere — hover
> and it names which. The recommendation is never a hollow point, and the
> balanced weights are printed under the chart, not hidden in it."

Open **Why**.

> "The Critic passed it with warnings, and each warning names the computation
> it read: weather confidence 0.23 on 46 per cent grid coverage; four cost
> components unpriced; and the option's zero exposure rests on the claim
> lapsing before the hull arrives — persistence beyond a claim is a stated
> weakness, not a hidden one."

## 00:50–01:10 — Money without invention

Open **Money**.

> "Cost of delay: unknown — no charter rate is configured, and the engine will
> not guess one. Port dues at Nhava Sheva: unknown — the hull declares no
> gross tonnage. Cost of action: zero, with the reason. Unknown is never zero
> here, and there is no total until every component is known."

Type a charter rate and a tonnage, press **Re-price with these assumptions**.

> "Now the delay is priced, labelled ASSUMPTION with my name on it. The port
> dues are priced at JNPA's own scale of rates — page six, verbatim, in force
> from May 2026 — and still labelled an assumption, because the tariff is
> public and the tonnage is mine. The computed problem in the ledger did not
> change; this is a new one."

## 01:10–01:30 — Human decision

Open **Decide**.

> "Decision is not execution. I mark it reviewed. I approve option A. And
> because I am National Command, not the shipping company, the approved option
> reaches the vessel as an advisory — never a command."

Press **Hand into advisory boundary**.

> "It is now a DRAFT advisory in the same boundary the port uses. Eleven
> states, role-gated, every transition audited. The hull sees nothing until a
> named person issues it."

(Thirty seconds spare: in the port tab, `/port/twin`, press **What should we
do?** — six berth plans on the same engine, and the 3D scene rewrites its
berths and cranes to whichever you select. Point at the one marked
*dominated*.)

## 01:30–02:00 — Observe the outcome, learn

`/admin/missions`. The clock reads 23 March 2021, 08:00Z.

> "The Ever Given has been aground for two hours. PortWatch can read only the
> two reports that existed then; nine more are hidden until the reveal. Three
> India-bound hulls are placed on the modelled lane — illustrative, and it
> says so."

Press **Decide** on MV Konkan.

> "The whole Cape diversion is drawn, from the Mediterranean round Africa.
> The engine recommends slowing and holding clear of Suez, expecting the
> canal to reopen inside its seventy-two-hour claim horizon."

Press **Choose this option**, then **Reveal outcome**.

> "The canal was blocked for a hundred and fifty-five hours. The seventy-two
> hour claim horizon understated it by eighty-one, and the scorecard says so
> in those words. Every option is scored against what actually happened —
> the Cape hull arrived when the engine said it would; the hull that waited
> then took its turn in a queue the sources put at four hundred ships. Regret
> is thirty-one hours against the
> realised best, and the ranking was wrong. That verdict is written to the
> ledger and it feeds the learning screen. The point of the product is not
> that it was right. It is that it can tell you, in numbers, when it was
> wrong."

---

## The recorded run

`node qa/executive-demo.mjs` (in `india-portwatch-terminal/`) drives every
beat above against the running stack exactly as a buyer would — a seeded
sign-in, then clicks; no API mocked, nothing refreshed by hand, the devtools
closed — and records how long each beat took to reach. The talk track fills
the two minutes; the product itself is on screen inside ten seconds of machine
time. Recorded 15 September 2026, Chromium on the GPU at 1920×1080, licence
mode DEMO, world clock LIVE:

| Beat | Reached at | Took | What was on screen |
|---|---:|---:|---|
| Global Eye opens with the chart drawn | 1.9 s | 1.84 s | the world, drawn |
| The live register lists corroborated events | 2.5 s | 0.13 s | 6 cascades |
| The action rail ranks what needs intervention | 2.8 s | 0.09 s | 5 items, 2 with a decision open |
| **What should we do?** — the decision computed | 3.4 s | 0.48 s | 4 options on the table, 5 not offered with a reason |
| Compare — every option's world on the chart | 5.3 s | 1.73 s* | option A selected, B and the current plan drawn |
| Frontier | 5.5 s | 0.04 s | 4 evaluated points |
| Why | 5.6 s | 0.04 s | 12 Critic checks |
| Money | 5.8 s | 0.06 s | 5 cost components, "unknown" ten times |
| Re-price with the operator's assumptions | 6.2 s | 0.33 s | 4 components priced as labelled assumptions; JNPA's public tariff cited |
| Decide — mark reviewed | 6.7 s | 0.33 s | |
| Approve the recommended option | 7.2 s | 0.34 s | *Slow to 10.2 kn and hold clear of BAB_EL_MANDEB* |
| Hand into the advisory boundary | 7.4 s | 0.12 s | 1 DRAFT advisory |
| Mission — the clock reads March 2021 | 8.1 s | 0.61 s | 2021-03-23 08:00Z; 9 observations hidden until reveal |
| Decide on the illustrative hull | 8.4 s | 0.20 s | |
| Choose this option | 8.7 s | 0.15 s | |
| Reveal the outcome — the scorecard | 8.9 s | 0.11 s | regret 31.1 h against the realised best; ranking incorrect |

\* 1.4 s of that is the script's own pauses so the chart can be seen redrawing.
Total 9.0 s; zero page errors. The screenshots of each beat and the JSON the
table is built from are in [qa/executive-demo/](qa/executive-demo/).

Headless Chromium renders WebGL in software and can run the chart at two or
three frames a second, which makes every click wait for the map to settle;
the same run took 31–157 s headless. That is the test browser, not the
product — `PW_HEADED=1` is the buyer's browser — and it is why CI's browser
suite is a regression suite, not a timing.

## The failure demo

Three things a buyer will ask about, made to fail for real, on throwaway API
instances with the configuration a real deployment could have. No timestamp
is edited and nothing is mocked. `python scripts/demo_failure.py` reproduces
it and exits non-zero if the product ever substitutes or zeroes. Recorded
15 September 2026:

**1. AIS unavailable** — `PORTWATCH_LICENCE_MODE=RESEARCH` with an AISStream
credential the service refuses.

```
/fabric/health traffic.mode      UNAVAILABLE
/fabric/health traffic.statement AISStream refused the configured credential
/fabric/health traffic.health    AUTH_FAILED -- the connection closed immediately after
                                 subscribing 3 times in a row with nothing delivered. That is
                                 how AISStream rejects an invalid key; check AISSTREAM_API_KEY.
/security/lens status            SECURITY ANALYTICS UNAVAILABLE
/security/lens reason            no observed AIS is available (AISStream refused the configured credential)
/admin/readiness ready           False
/admin/readiness refusal         traffic_feed
/attention                       traffic UNAVAILABLE; observed 0; 16 vessel subjects, source ['FLEET']
```

The chart shows no traffic and does not fall back to the replay. The
attention queue still ranks the company's own registered fleet by its
*planned* passages — the operator's own declarations, labelled `FLEET`,
never as observed. Readiness refuses: a configured credential the provider
rejects is a broken deployment, not merely an honest one (the `traffic_feed`
check was added by this demo; before it, readiness passed).

**2. Financial rate missing** — the default: no charter rate is configured.

```
/finance/basis rates             19 configured, 0 of them a charter rate
/finance/basis note              No default rate exists. A primitive with no configured rate
                                 prices nothing, and every figure built on it is reported as unknown.
option: Slow to 10.2 kn and hold clear of BAB_EL_MANDEB
total                            None; complete False
Cost of delay                    UNKNOWN  no vessel charter rate is configured for INNSA
Fuel difference                  UNKNOWN  no fuel burn rate is configured for *
Cost of action                   ZERO     the option incurs no direct charge
Port dues at destination         UNKNOWN  the hull declares no gross tonnage, so per-GRT dues
                                          cannot be computed; supply one as a scenario assumption
Cargo impact                     UNKNOWN  no consignment is linked to this hull in the world graph
```

Zero appears once, with its reason (the option incurs no charge). There is no
total. The Money tab shows the same rows and offers the assumption form, and
a figure entered there is labelled ASSUMPTION on every number it touches.

**3. Marine grid missing and the provider unreachable** — DEMO mode, no grid
ever fetched, the fetch routed through a closed port.

```
/admin/freshness marine.state    MISSING -- no grid fetched yet
/admin/readiness ready           False
/admin/readiness freshness:marine FAIL: Marine forecast grid (Open-Meteo) has never been produced
POST /admin/freshness/marine/refresh?wait=true   outcome started
job state / attempts / next      RETRY_SCHEDULED / 1 / 2026-09-15T08:43:06+00:00
last result                      ok=False attempt 1 -- RuntimeError: URLError: <urlopen error
                                 [WinError 10061] No connection could be made ...>
/admin/freshness marine after    MISSING; observedAt None
/fabric/health marine            freshness UNAVAILABLE; availability UNAVAILABLE
decision on PWD-003 computed; 4 options
recommended option weather       available False; value None; confidence None;
                                 no marine forecast grid is available to this deployment
option critic                    PASS_WITH_WARNINGS
critic weather_confidence        FAILED -- no marine forecast grid is available to this deployment
```

The refresh fails in the open with the provider's error, the next attempt has
an instant, no observation timestamp is invented, readiness refuses (a
required capability with no data has never been produced — this check was
also tightened by the demo), and the decision still computes with the weather
objective marked unavailable and the Critic saying so, rather than a
confidence of zero passed off as a measurement.

Marine *stale* rather than missing is the more common case, and it is what the
start command met on 15 September: `[FAIL] freshness:marine  Marine forecast
grid (Open-Meteo) is STALE (3.2 h old); the world built from it would be
empty` → `marine  refreshing  was stale, 3.2 h old` → `marine  refreshed
{"cells": 4560, "points": 38}` → `MARINE  FRESH  age 29 s`. The operator did
nothing.

## The questions you will be asked

**"Did an LLM produce those numbers?"** No. The Copilot orchestrates and
explains; every figure is a `Measure` with a basis from a simulator. Ask it
"What should MV Coromandel do?" and it opens the same panel on the same
problem.

**"Why is the Cape not offered?"** `route_topology`: the alternative routing
branches at Gibraltar; a hull past the branch cannot reach it. The row under
*Not offered* says exactly that.

**"Where do the tariffs come from?"** `data/tariffs/public_tariffs.json`:
JNPA Scale of Rates w.e.f. 1 May 2026 and the Chennai indexed SoR 2025-26,
transcribed verbatim with page, section, URL, retrieval date and sha256;
labelled `PUBLIC_TARIFF`, reuse `REQUIRES_REVIEW`. TAMP was unreachable when
investigated and the attempt is recorded.

**"Can it be gamed by an assumption?"** An assumption prices a component and
labels it; it never changes a constraint, a risk or an ETA, and the Critic's
`assumptions` check flags every option built on one.

**"What if no option survives?"** The problem says so and recommends nothing.
A rejected option is still shown, with the constraint that rejected it.

**"Is the mission real?"** The chronology and the outcome are transcribed from
cited sources; the hulls are illustrative and the screen says so on every
one. Nothing operational the sources do not state has been reconstructed.

## If something breaks mid-demo

- **No ACT SOON items:** the register lapsed and the coordinator is
  refreshing it (System → Freshness shows the job; *Refresh* there asks for
  it now). Reload when the row reads FRESH.
- **The chart shows INITIALISING:** the pane was hidden while the map loaded;
  reload the tab with it visible.
- **The mission says "no observation is visible at the replay clock":** press
  *restart* on the rail; a replay is a run, not a page.
- **A decision id collides:** the ledger refuses to rewrite a resolved
  problem; press *What should we do?* again — the new instant makes a new id.
