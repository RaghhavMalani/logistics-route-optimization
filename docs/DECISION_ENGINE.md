# The decision intelligence engine

The primary question PortWatch X answers is no longer "what is happening?" but
**"what should I do?"** — for a hull, a quay, or a consignment — and every
number in the answer is computed by a simulator on a branch of the observed
world, never written by a language model.

```
SENSE → UNDERSTAND → PREDICT → GENERATE OPTIONS → SIMULATE → OPTIMISE → CRITIQUE
      → HUMAN DECISION → OBSERVE OUTCOME → LEARN
```

This document is the engine's contract: what a decision is, which actions
exist, how options are evaluated and ranked, how money is priced without
inventing a figure, who may hold which decision, how a choice reaches the
world, and how the engine is scored afterwards. Code lives under
`src/portwatch_os/decision/`, `src/portwatch_os/finance/` and
`src/portwatch_os/missions/`; the routes under `backend/app/routes/decisions.py`,
`finance.py` and `missions.py`.

---

## 1. The decision model

One object, `DecisionProblem`, for every domain:

| Field | Meaning |
|---|---|
| `decisionId`, `createdAt`, `at` | Identity and the instant the world was read. |
| `domain` | `VESSEL_ROUTING`, `PORT_BERTHING` or `CARGO_CONNECTION`. |
| `worldStateId`, `worldRevision` | The immutable observed world the problem was computed from. Every option forks from it; none edits it. |
| `subject` | The hull, port or consignment, with its label. |
| `actor` | Who the problem is framed for: role, organisation, port, vessels. |
| `availableActions` | Every catalogue action for the domain, with its availability and reason. |
| `options` | One `DecisionOption` per generated plan, the do-nothing baseline among them. |
| `baselineOptionId` | The option that is "do nothing", evaluated like any other. |
| `frontier` | Nondominated set, the dominated map, incomparable options, named picks. |
| `recommendation` | The BALANCED choice, with its weights, statement, expected avoidable cost and Critic verdict. |
| `decisionWindowHours`, `decisionDeadline` | When the earliest option closes. |
| `workflow`, `workflowHistory`, `humanChoice` | The approval state and who moved it. |
| `evidence` | Position, exposure, routes, marine coverage, cost basis, FX table, frontier objectives, execution mechanism, assumptions. |

Every measure is a `Measure`: `value`, `unit`, `confidence`, `basis` — or
`available: false` with `unknownBecause`. An unknown is never a zero, and a
measure without a basis is refused by `validate()`.

A `DecisionOption` carries its action, label, actor, status
(`FEASIBLE` / `REJECTED` / `NOT_EVALUATED`), the constraints it was checked
against, its `DecisionEvaluation` (objectives, consequences, derived state,
financial evaluation, the branch it ran on), the geometry the chart draws, a
timeline of marks, its Critic review, and provenance.

## 2. The action catalogue

`decision/actions.py` holds the typed catalogue. Each `ActionSpec` names its
domain, the actors who may execute it, the subject data it needs, and the
simulator that can evaluate it.

| Domain | Actions |
|---|---|
| Vessel | `KEEP_PLAN` (baseline), `REROUTE`, `SLOW_STEAM`, `SPEED_UP`, `DELAY_DEPARTURE`, `DELAY_ARRIVAL`, `CHANGE_DESTINATION_PORT`, `CHANGE_TRANSSHIPMENT`, `REBUNKER` |
| Port | `KEEP_SCHEDULE` (baseline), `SHIFT_ARRIVAL_SLOT`, `REASSIGN_BERTH`, `ALTER_HOLDING_WINDOW`, `CHANGE_CRANE_ALLOCATION`, `CHANGE_YARD_ALLOCATION`, `PRIORITISE_VESSEL`, `ISSUE_ADVISORY` |
| Cargo | `KEEP_CONNECTION` (baseline), `CHANGE_CONNECTION`, `CHANGE_YARD`, `TRANSFER_TO_VESSEL`, `DEFER_SHIPMENT` |

`availability_of()` decides, in order: entitlement (`UNAVAILABLE` — "executed
by SHIPPING_COMPANY, not by PORT_AUTHORITY"), simulator support (`UNSUPPORTED`
— "no simulator in this deployment evaluates change transshipment hub"), data
(`INSUFFICIENT_DATA` — "delay departure needs departure_port, departure_at,
which the subject does not declare"), then the domain's own check. An action
that is not offered is listed with that reason; the UI shows it under
**Not offered**. Nothing is invented to fill the list.

## 3. Hard constraints

A hard constraint **rejects**; it is never a score penalty. Vessel routing
checks `speed_envelope`, `route_topology` (a hull past Suez cannot reach the
Cape routing, which branches at Gibraltar), `not_committed`, `decision_window`
and `weather_safety`; `berth_draught` is soft. Port berthing rejects on the
twin's physical constraints and on a defining departure commitment; cargo
rejects on the cargo model's own rules (capacity, plugs, dangerous goods,
deadweight, connection window). A rejected option keeps the constraint that
rejected it, carries no score, and takes no part in ranking.

## 4. Evaluation and the frontier

Every feasible option is simulated on its own `ScenarioBranch` of the observed
world (`world/branch.py`), through the same World State Engine cascade the
live product uses. A chosen delay travels vessel → port → yard → INR through
the `delay_reaches_port` transfer. The baseline is evaluated the same way, on
its own branch: doing nothing is computed, not assumed.

Objectives are typed (`OBJECTIVES`): ETA shift, delay, distance, fuel index,
weather, wave hours, storm, chokepoint risk, port wait, berth utilisation, yard
pressure, dwell, missed connection, emissions, cost, uncertainty, turnaround,
crane utilisation, missed departures, slack, handling, sailing. Uncertainty is
`1 − min confidence` over the domain's frontier objectives, unknown if any of
them is unknown.

`frontier.py` computes Pareto dominance ("no worse everywhere, better
somewhere"; an unknown measure makes a pair incomparable, never dominated),
the named picks — `FASTEST`, `LOWEST_RISK`, `LOWEST_FUEL`, `LOWEST_COST`,
`BEST_SCHEDULE_RELIABILITY`, `LOWEST_WEATHER`, `SHORTEST_WAIT`,
`FEWEST_MISSED_DEPARTURES`, `EARLIEST_SAILING`, `MOST_SLACK` — and the
BALANCED ranking: min–max normalised, objectives not measured for every
feasible option dropped and named as dropped, weights returned with the
result. Ties go to the baseline. Vessel weights: risk 0.35, eta 0.25, fuel
0.15, weather 0.10, cost 0.10, uncertainty 0.05. Port weights charge a missed
departure the way the twin's own reward does (0.40).

The recommendation is never a dominated or incomparable option. When no
feasible option survives, the problem says so.

## 5. The optimiser is deterministic, and greedy loses

There is no learned policy in the loop. The same world produces the same
option set, the same measures and the same recommendation (acceptance claim
6). `tests/test_decision_engine.py::committed_port` is the case where the
obvious choice is wrong: one working berth, a long call with a departure
commitment behind two short ones. Greedy shortest-work-first minimises mean
wait and sails the committed call late; the engine's ranking, charging the
missed departure, prefers first-come-first-served and says why.

## 6. The Critic

`DecisionCritic.review_option` runs named checks — `hard_constraints`,
`decision_window`, `source_freshness` (replay-aware), `weather_confidence`,
`model_disagreement` (geometry against the catalogue detour), `route_feasibility`,
`port_feasibility`, `cargo_feasibility`, `data_availability`, `assumptions`,
`claim_horizon` — and returns `PASS`, `PASS_WITH_WARNINGS` or `REJECT`. Each
check names the computation it read (`basis`). `review_recommendation` adds
`recommended_option_passes`, `risk_tradeoff_stated` and `not_dominated`. A
REJECT withdraws the option from ranking.

## 7. The financial twin

`finance/` prices an option without ever inventing a figure.

- **Types.** `Money` (amount, currency), `Rate` (money per unit), `Quantity`
  (value, unit: hour, day, tonne, teu, teu_day, grt, grt_hour, nm, move, call,
  crane_hour). Currencies do not add without an FX observation; a rate refuses
  the wrong unit and converts only time.
- **Basis.** `CostBasis.lookup(primitive, at, scope, vessel_status, vessel_type,
  gt)` prefers `CUSTOMER_CONTRACT` > `PORT_TARIFF` > `PUBLIC_TARIFF` >
  `MARKET_DATA` > `USER_ASSUMPTION`, honours validity windows ("lapsed; not
  used") and tiered tonnage rates (`charge_for_grt`).
- **Pricer.** Every component is `KNOWN` (with rate, source type and basis),
  `ZERO` (with the reason it is zero) or `UNKNOWN` (with the reason it could
  not be priced). A total exists only when every component is known; a partial
  total is labelled partial and never compared as complete. **UNKNOWN ≠ ZERO.**
- **Public tariffs.** `data/tariffs/public_tariffs.json` holds the JNPA Scale
  of Rates w.e.f. 1 May 2026 and the Chennai indexed SoR 2025-26 (lapsed),
  transcribed verbatim with page, section, URL, retrieval date and sha256, and
  labelled `PUBLIC_TARIFF` — a port's published charge, not a customer's cost.
  Their reuse is `REQUIRES_REVIEW`. TAMP was unreachable when investigated and
  the attempt is recorded. See `docs/DATA_SOURCES.md`.
- **Assumptions.** A rate an operator supplies (`POST /finance/assumptions`, or
  `assumptions` on a problem request) is `USER_ASSUMPTION`, named, dated and
  labelled `ASSUMPTION` on every number it touches. A hull attribute the
  subject does not declare — gross tonnage — can be supplied as
  `vesselAssumptions`; the tariff is public, the tonnage is not, so the
  component stays an assumption.
- **FX.** A cross-currency total exists only with an explicit `FxObservation`
  (base, quote, rate, instant, source). Without one the engine refuses.
- **Avoidable cost.** The recommendation carries the cost of doing nothing
  against the option's cost when both are complete, otherwise the reason it is
  not computable and the partial figures, marked as such.

## 8. Actors

`ACTORS` are `SHIPPING_COMPANY`, `PORT_AUTHORITY`, `TERMINAL_OPERATOR`,
`NATIONAL_ADMIN`, `VESSEL_OPERATOR`. A port authority is never told to
reassign a shipping company's routing: for vessel and cargo decisions an
advising actor gets the executing actor's options, each marked
`requiresAdvisory`, and `evidence.execution` says `{by: SHIPPING_COMPANY,
requestedBy: PORT_AUTHORITY, mechanism: ISSUE_ADVISORY}`. A shipping company
asking for a berth decision is refused.

## 9. Human approval and the advisory boundary

```
COMPUTED → REVIEWED → APPROVED → PROPOSED → ISSUED → ACCEPTED / DECLINED → OBSERVED
```

`POST /decisions/problems/{id}/transition` moves the workflow; `APPROVED`
needs an `optionId` and refuses a rejected one; every move records who and
when. `POST .../handoff` (issuers only) turns an approved non-baseline option
into DRAFT advisories in the existing advisory store — approach, speed,
arrival-window or berth advisories — and moves the problem to `PROPOSED`.
Continuing the current plan needs no advisory and the door says so. The
decision is never the execution.

## 10. Ledger and learning

Every problem is written to the ledger as computed
(`DecisionProblemRecord`); `resolve` refuses to rewrite the payload. `POST
.../outcome` records what was observed and moves the problem to `OBSERVED`.
`GET /decisions/learning` scores from the stored records only — agreement
rate, ranking accuracy and regret where counterfactuals exist, prediction
error per objective, calibration of that error against stated confidence,
constraint violations, reward (`REWARD_TERMS`) — and says in its `method` that
the engine is never re-run with hindsight.

## 11. Historical missions

`missions/` replays a sourced incident with only what was knowable at the
clock. `Mission.visible(clock)` gates every read; anything later raises
`FutureLeak` until the reveal. The replay builds the world from the visible
claims, advances the illustrative hulls by the elapsed hours on the modelled
lane (their positions are derived, with the basis on every point, and served
as `geography`), and runs the same engine. `choose` records the operator's
option before the future opens; `reveal` opens the chronology and the outcome
and scores every option against what happened: forecast error (claim horizon
against the real blockage, Brier on baseline risk), each option's realised
delay under a stated realised model, the realised best, regret, ranking
correctness, and the lessons. The one mission shipped is the Ever Given
grounding, 23 March – 3 April 2021, transcribed from Wikipedia, Boskalis, CNN
and Supply Chain Dive on the retrieval date recorded in the catalogue.

## 12. The decision UI

- **Global Eye.** Actionable hulls carry **What should we do?** The panel
  states the decision window as a countdown, what happens if unchanged,
  3–5 alternatives, COMPARE, a Frontier tab (every point is a real option),
  a Timeline, Money (with the assumption form for the gaps a figure would
  close), Why (the Critic) and Decide (the workflow and the handoff). The
  chart draws every alternative: the baseline thin and neutral, the selected
  option solid in its colour, the others dashed, the rejected faint; the port
  ring's radius is the option's own yard pressure, so the world changes when
  the option does.
- **Port twin.** *What should we do?* computes the berth plan problem on the
  twin; selecting an option rewrites the 3D scene's berths, cranes and calls
  to that option's assignments.
- **Cargo.** The first consignment that misses its booking, and every way
  the cargo model's rules allow it to move.
- **Missions.** A map-first replay: the chronology as it stood, seek, decide,
  choose, reveal, scorecard. The chart draws only the mission's world — the
  live 2026 ports, weather and traffic stay off it.
- **Copilot.** "What should MV Konkan do?", "safest", "cheapest", "keeps the
  current route", "avoid the storm within 24 h", "compare rerouting with slow
  steaming" go through `portwatch.decision.solve` and explain the computed
  options only; `SHOW_DECISION` opens the panel on the option named.

## 13. Tests

`tests/test_decision_engine.py`, `tests/test_finance_and_missions.py` and
`tests/test_decision_copilot.py` cover hard infeasibility, Pareto dominance,
baseline equality with the twin's own run, branch isolation, cascade
propagation, actor permissions (vessel and cargo), cost unit safety,
unknown ≠ zero, FX refusal, assumption labelling (rates and tonnage), decision
ranking, Critic rejection, advisory handoff, the ledger, outcome scoring,
replay no-future-leakage, mission chronology and the greedy-loses case.
`scripts/demo_acceptance.py` checks the fifteen product claims against a
running API. The screenshots under `docs/qa/decision/` are the eight views
at 1920×1080, 1440×900 and 1366×768, captured by `qa/shots-decision.mjs`.
