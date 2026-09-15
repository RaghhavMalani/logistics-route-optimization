# Decision benchmark

Measured 2026-09-15T10:02:24+00:00. Produced by `python scripts/benchmark_decisions.py`; each corpus is fixed by its seed range (`CORPORA` in `src/portwatch_os/decision/benchmark.py`) and nothing in it was chosen after seeing a result.

Five policies choose from the same simulated option set on every case, so the comparison isolates what the optimiser adds (the frontier, the balanced ranking, the Critic, the robust gate) from what the simulator adds. Each case has a hidden truth the policies never see; every chosen option is scored against it. `regret` is the realised delay of the chosen option minus the realised delay of the best feasible option on that case. Decision time for the two PortWatch policies includes building and evaluating the whole problem; the baselines are charged only for their selection because they are handed the engine's options.

`portwatch_balanced` is the incumbent expected-value ranking. `portwatch_robust` is the candidate: the same options evaluated under four stress horizons (FIZZLE, SHORT, BASE, LONG) with a minimax-regret gate that may answer KEEP_CURRENT_PLAN or WAIT_FOR_MORE_INFORMATION (`docs/ROBUST_DECISIONS.md`). A WAIT is scored by simulating the wait: if the closure had ended by the re-evaluation instant the hull keeps its plan, otherwise it takes the provisional option the recommendation named.

## Corpora

| corpus | seeds | cases per domain | role |
|---|---|---:|---|
| tuning | 1-40 | 40 | the original corpus; its results were read while the robust policy was designed |
| validation | 1001-1100 | 100 | used to check the design and revise it where it failed; every revision is in the git history |
| test | 5001-5200 | 200 | untouched until the final run; the promotion verdict rests on it |

## How each domain is scored

- **VESSEL** — a chokepoint claim and a hull bound through it. Truth: the closure's actual duration, lognormal around a median that grows with severity, fizzling with probability falling in corroboration. Options are scored by the closure outcome model (wait for the reopening, then a queue drained in arrival order; a detour is certain) with the truth's own backlog drain. A `change_destination_port` option has no realised model and is unscored.
- **PORT** — a berth plan for three to six calls that bunch. Truth: arrivals slip (N(+1.0, 1.5) h) and moves run over (×N(1.08, 0.15)). Each plan is re-simulated by the port twin on the true state. Delay is mean wait; a missed departure commitment is a violation.
- **CARGO** — a transshipment connection. Truth: the inbound discharge slips (N(+1.2, 1.4) h, never earlier) and every cut-off moves (N(0, 0.8) h). Delay is hours from the true ready hour to the sailing actually made; a missed connection is a violation and the box takes the next feasible sailing (72 h if there is none in the case).

The robust policy changes only VESSEL recommendations: PORT and CARGO carry no duration-uncertainty model, so there the candidate answers exactly as the incumbent and the tables show it.

## Promotion verdict

**APPROVED** — portwatch_robust approved on validation and test; it is the active policy.

The full check-by-check gate is in `docs/DECISION_POLICY_GATE.md`.

# TUNING corpus — seeds 1-40, 40 cases per domain

## VESSEL — 40 cases

| policy | mean delay (h) | mean regret (h) | median regret | p90 regret | worst regret | zero-regret share | violations | intervention rate | unnecessary interventions | wait rate | mean decision time | p95 decision time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_plan | 45.06 | 0.16 | 0.00 | 0.00 | 2.90 | 0.92 | 0 | 0% | — | 0% | 0.00 ms | 0.00 ms |
| greedy | 45.06 | 0.16 | 0.00 | 0.00 | 2.90 | 0.92 | 0 | 0% | — | 0% | 0.00 ms | 0.01 ms |
| heuristic | 102.28 | 57.38 | 0.00 | 325.20 | 442.40 | 0.73 | 0 | 28% | 82% | 0% | 0.00 ms | 0.00 ms |
| portwatch_balanced | 50.62 | 5.72 | 0.00 | 19.60 | 67.80 | 0.76 | 0 | 30% | 75% | 0% | 16.07 ms | 20.08 ms |
| portwatch_robust | 45.06 | 0.16 | 0.00 | 0.00 | 2.90 | 0.92 | 0 | 0% | — | 0% | 16.07 ms | 20.08 ms |

An intervention was the realised best on 3 case(s); captured by: current_plan 0%, greedy 0%, heuristic 67%, portwatch_balanced 100%, portwatch_robust 0%.

`portwatch_robust` answered: KEEP_CURRENT_PLAN 40.

Head to head on realised delay (cases both policies scored):

| policy | against | wins | loses | ties |
|---|---|---:|---:|---:|
| portwatch_balanced | current_plan | 3 | 9 | 25 |
| portwatch_balanced | greedy | 3 | 9 | 25 |
| portwatch_balanced | heuristic | 7 | 2 | 28 |
| portwatch_balanced | portwatch_robust | 3 | 9 | 25 |
| portwatch_robust | current_plan | 0 | 0 | 37 |
| portwatch_robust | greedy | 0 | 0 | 37 |
| portwatch_robust | heuristic | 9 | 2 | 26 |
| portwatch_robust | portwatch_balanced | 9 | 3 | 25 |

## PORT — 40 cases

| policy | mean delay (h) | mean regret (h) | median regret | p90 regret | worst regret | zero-regret share | violations | intervention rate | unnecessary interventions | wait rate | mean decision time | p95 decision time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_plan | 6.93 | 2.49 | 1.60 | 7.25 | 8.62 | 0.26 | 23 | 0% | — | 0% | 0.00 ms | 0.00 ms |
| greedy | 4.95 | 0.51 | 0.00 | 1.60 | 7.04 | 0.80 | 20 | 72% | 17% | 0% | 0.00 ms | 0.01 ms |
| heuristic | 6.93 | 2.49 | 1.60 | 7.25 | 8.62 | 0.26 | 24 | 100% | 98% | 0% | 0.00 ms | 0.00 ms |
| portwatch_balanced | 4.95 | 0.62 | 0.00 | 1.60 | 7.04 | 0.78 | 16 | 80% | 16% | 0% | 7.61 ms | 9.32 ms |
| portwatch_robust | 4.95 | 0.62 | 0.00 | 1.60 | 7.04 | 0.78 | 16 | 80% | 16% | 0% | 7.61 ms | 9.32 ms |

An intervention was the realised best on 29 case(s); captured by: current_plan 0%, greedy 83%, heuristic 0%, portwatch_balanced 90%, portwatch_robust 90%.

`portwatch_robust` answered: ACT 32, KEEP_CURRENT_PLAN 8.

Head to head on realised delay (cases both policies scored):

| policy | against | wins | loses | ties |
|---|---|---:|---:|---:|
| portwatch_balanced | current_plan | 26 | 3 | 10 |
| portwatch_balanced | greedy | 2 | 3 | 34 |
| portwatch_balanced | heuristic | 26 | 3 | 10 |
| portwatch_balanced | portwatch_robust | 0 | 0 | 40 |
| portwatch_robust | current_plan | 26 | 3 | 10 |
| portwatch_robust | greedy | 2 | 3 | 34 |
| portwatch_robust | heuristic | 26 | 3 | 10 |
| portwatch_robust | portwatch_balanced | 0 | 0 | 40 |

## CARGO — 40 cases

| policy | mean delay (h) | mean regret (h) | median regret | p90 regret | worst regret | zero-regret share | violations | intervention rate | unnecessary interventions | wait rate | mean decision time | p95 decision time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_plan | 34.99 | 0.00 | 0.00 | 0.00 | 0.00 | 0.70 | 46 | 0% | — | 0% | 0.00 ms | 0.00 ms |
| greedy | 35.01 | 0.02 | 0.00 | 0.00 | 0.50 | 0.65 | 31 | 25% | 100% | 0% | 0.00 ms | 0.00 ms |
| heuristic | 35.45 | 0.66 | 0.00 | 0.00 | 12.80 | 0.65 | 29 | 28% | 100% | 0% | 0.00 ms | 0.00 ms |
| portwatch_balanced | 35.01 | 0.02 | 0.00 | 0.00 | 0.50 | 0.65 | 31 | 25% | 100% | 0% | 0.37 ms | 0.51 ms |
| portwatch_robust | 35.01 | 0.02 | 0.00 | 0.00 | 0.50 | 0.65 | 31 | 25% | 100% | 0% | 0.37 ms | 0.51 ms |

An intervention was the realised best on 0 case(s); captured by: current_plan —, greedy —, heuristic —, portwatch_balanced —, portwatch_robust —.

`portwatch_robust` answered: ACT 10, KEEP_CURRENT_PLAN 18.

Head to head on realised delay (cases both policies scored):

| policy | against | wins | loses | ties |
|---|---|---:|---:|---:|
| portwatch_balanced | current_plan | 0 | 2 | 38 |
| portwatch_balanced | greedy | 0 | 0 | 40 |
| portwatch_balanced | heuristic | 2 | 1 | 37 |
| portwatch_balanced | portwatch_robust | 0 | 0 | 40 |
| portwatch_robust | current_plan | 0 | 2 | 38 |
| portwatch_robust | greedy | 0 | 0 | 40 |
| portwatch_robust | heuristic | 2 | 1 | 37 |
| portwatch_robust | portwatch_balanced | 0 | 0 | 40 |

## Where `portwatch_robust` lost — 10 case(s)

| case | what the case was | robust chose | kind | realised | beaten by |
|---|---|---|---|---:|---|
| vessel-5 | USEC_IND hull 54 h from Suez; SUEZ claim severity 0.52, confidence 0.78, horizon 96 h | keep_plan | KEEP_CURRENT_PLAN | 39.1 h (regret 1.6) | heuristic: slow_steam at 37.5 h; portwatch_balanced: slow_steam at 37.5 h |
| vessel-7 | EUR_IND hull 62 h from Suez; SUEZ claim severity 0.55, confidence 0.43, horizon 96 h | keep_plan | KEEP_CURRENT_PLAN | 39.7 h (regret 2.9) | heuristic: slow_steam at 36.8 h; portwatch_balanced: slow_steam at 36.8 h |
| vessel-34 | USEC_IND hull 31 h from Suez; SUEZ claim severity 0.27, confidence 0.53, horizon 48 h | keep_plan | KEEP_CURRENT_PLAN | 11.2 h (regret 1.4) | portwatch_balanced: slow_steam at 9.8 h |
| port-11 | INNSA: 4 calls over 3 berths, 1 with departure commitments | change_crane_allocation | ACT | 11.9 h (regret 7.04) | current_plan: keep_schedule at 6.2 h; heuristic: prioritise_vessel at 6.2 h |
| port-24 | INMAA: 5 calls over 3 berths, 2 with departure commitments | change_crane_allocation | ACT | 2.8 h (regret 1.58) | current_plan: keep_schedule at 1.2 h; heuristic: prioritise_vessel at 1.2 h |
| port-26 | INMAA: 5 calls over 3 berths, 2 with departure commitments | reassign_berth-greedy | ACT | 6.3 h (regret 6.33) | current_plan: keep_schedule at 0.0 h; greedy: keep_schedule at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-31 | INCOK: 5 calls over 2 berths, 1 with departure commitments | change_crane_allocation | ACT | 8.9 h (regret 0.75) | greedy: reassign_berth-greedy at 8.2 h |
| port-37 | INMAA: 3 calls over 3 berths, 1 with departure commitments | change_crane_allocation | ACT | 3.5 h (regret 1.67) | greedy: reassign_berth-greedy at 1.8 h |
| cargo-14 | INNSA: 8 TEU dry to MYPKG, ready hour 7.6, booked sailing hour 13.0, 3 alternatives | transfer_to_vessel-BM-OUT-14-3 | ACT | 5.5 h (regret 0.1) | current_plan: keep_connection at 5.4 h |
| cargo-32 | INMAA: 12 TEU dry to MYPKG, ready hour 2.6, booked sailing hour 12.5, 3 alternatives | transfer_to_vessel-BM-OUT-32-3 | ACT | 8.6 h (regret 0.5) | current_plan: keep_connection at 8.1 h; heuristic: keep_connection at 8.1 h |

# VALIDATION corpus — seeds 1001-1100, 100 cases per domain

## VESSEL — 98 cases (2 refused by the engine)

| policy | mean delay (h) | mean regret (h) | median regret | p90 regret | worst regret | zero-regret share | violations | intervention rate | unnecessary interventions | wait rate | mean decision time | p95 decision time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_plan | 33.74 | 1.07 | 0.00 | 0.00 | 80.10 | 0.94 | 0 | 0% | — | 0% | 0.00 ms | 0.00 ms |
| greedy | 33.74 | 1.07 | 0.00 | 0.00 | 80.10 | 0.94 | 0 | 0% | — | 0% | 0.00 ms | 0.00 ms |
| heuristic | 108.82 | 76.15 | 0.00 | 382.40 | 646.70 | 0.61 | 0 | 36% | 97% | 0% | 0.00 ms | 0.00 ms |
| portwatch_balanced | 45.13 | 12.46 | 0.00 | 36.90 | 80.10 | 0.56 | 0 | 44% | 91% | 0% | 14.64 ms | 19.93 ms |
| portwatch_robust | 33.74 | 1.07 | 0.00 | 0.00 | 80.10 | 0.94 | 0 | 0% | — | 1% | 14.64 ms | 19.93 ms |

An intervention was the realised best on 5 case(s); captured by: current_plan 0%, greedy 0%, heuristic 20%, portwatch_balanced 80%, portwatch_robust 0%.

`portwatch_robust` answered: KEEP_CURRENT_PLAN 97, WAIT_FOR_MORE_INFORMATION 1.

Head to head on realised delay (cases both policies scored):

| policy | against | wins | loses | ties |
|---|---|---:|---:|---:|
| portwatch_balanced | current_plan | 4 | 39 | 47 |
| portwatch_balanced | greedy | 4 | 39 | 47 |
| portwatch_balanced | heuristic | 15 | 9 | 66 |
| portwatch_balanced | portwatch_robust | 4 | 39 | 47 |
| portwatch_robust | current_plan | 0 | 0 | 90 |
| portwatch_robust | greedy | 0 | 0 | 90 |
| portwatch_robust | heuristic | 34 | 1 | 55 |
| portwatch_robust | portwatch_balanced | 39 | 4 | 47 |

## PORT — 100 cases

| policy | mean delay (h) | mean regret (h) | median regret | p90 regret | worst regret | zero-regret share | violations | intervention rate | unnecessary interventions | wait rate | mean decision time | p95 decision time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_plan | 6.79 | 2.37 | 1.38 | 5.90 | 12.73 | 0.33 | 43 | 0% | — | 0% | 0.00 ms | 0.00 ms |
| greedy | 5.30 | 0.88 | 0.00 | 3.38 | 13.62 | 0.73 | 37 | 76% | 20% | 0% | 0.02 ms | 0.02 ms |
| heuristic | 6.76 | 2.34 | 1.30 | 5.90 | 12.73 | 0.34 | 43 | 94% | 96% | 0% | 0.00 ms | 0.01 ms |
| portwatch_balanced | 5.72 | 1.30 | 0.00 | 4.67 | 16.75 | 0.67 | 26 | 80% | 30% | 0% | 38.99 ms | 48.02 ms |
| portwatch_robust | 5.72 | 1.30 | 0.00 | 4.67 | 16.75 | 0.67 | 26 | 80% | 30% | 0% | 38.99 ms | 48.02 ms |

An intervention was the realised best on 66 case(s); captured by: current_plan 0%, greedy 92%, heuristic 4%, portwatch_balanced 85%, portwatch_robust 85%.

`portwatch_robust` answered: ACT 80, KEEP_CURRENT_PLAN 20.

Head to head on realised delay (cases both policies scored):

| policy | against | wins | loses | ties |
|---|---|---:|---:|---:|
| portwatch_balanced | current_plan | 56 | 17 | 26 |
| portwatch_balanced | greedy | 5 | 14 | 80 |
| portwatch_balanced | heuristic | 54 | 16 | 29 |
| portwatch_balanced | portwatch_robust | 0 | 0 | 99 |
| portwatch_robust | current_plan | 56 | 17 | 26 |
| portwatch_robust | greedy | 5 | 14 | 80 |
| portwatch_robust | heuristic | 54 | 16 | 29 |
| portwatch_robust | portwatch_balanced | 0 | 0 | 99 |

## CARGO — 100 cases

| policy | mean delay (h) | mean regret (h) | median regret | p90 regret | worst regret | zero-regret share | violations | intervention rate | unnecessary interventions | wait rate | mean decision time | p95 decision time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_plan | 35.32 | 0.01 | 0.00 | 0.00 | 0.30 | 0.64 | 123 | 0% | — | 0% | 0.00 ms | 0.00 ms |
| greedy | 35.35 | 0.01 | 0.00 | 0.00 | 0.30 | 0.64 | 79 | 23% | 100% | 0% | 0.01 ms | 0.01 ms |
| heuristic | 35.92 | 0.87 | 0.00 | 3.80 | 9.70 | 0.54 | 76 | 29% | 100% | 0% | 0.01 ms | 0.01 ms |
| portwatch_balanced | 35.35 | 0.01 | 0.00 | 0.00 | 0.30 | 0.64 | 79 | 23% | 100% | 0% | 1.48 ms | 2.31 ms |
| portwatch_robust | 35.35 | 0.01 | 0.00 | 0.00 | 0.30 | 0.64 | 79 | 23% | 100% | 0% | 1.48 ms | 2.31 ms |

An intervention was the realised best on 2 case(s); captured by: current_plan 0%, greedy 0%, heuristic 0%, portwatch_balanced 0%, portwatch_robust 0%.

`portwatch_robust` answered: ACT 23, KEEP_CURRENT_PLAN 43.

Head to head on realised delay (cases both policies scored):

| policy | against | wins | loses | ties |
|---|---|---:|---:|---:|
| portwatch_balanced | current_plan | 0 | 1 | 99 |
| portwatch_balanced | greedy | 0 | 0 | 100 |
| portwatch_balanced | heuristic | 10 | 0 | 90 |
| portwatch_balanced | portwatch_robust | 0 | 0 | 100 |
| portwatch_robust | current_plan | 0 | 1 | 99 |
| portwatch_robust | greedy | 0 | 0 | 100 |
| portwatch_robust | heuristic | 10 | 0 | 90 |
| portwatch_robust | portwatch_balanced | 0 | 0 | 100 |

## Where `portwatch_robust` lost — 28 case(s)

| case | what the case was | robust chose | kind | realised | beaten by |
|---|---|---|---|---:|---|
| vessel-1052 | USEC_IND hull 17 h from Suez; BAB_EL_MANDEB claim severity 0.85, confidence 0.57, horizon 72 h | keep_plan | KEEP_CURRENT_PLAN | 46.5 h (regret 5.2) | portwatch_balanced: slow_steam at 41.3 h |
| vessel-1066 | USEC_IND hull 56 h from Suez; SUEZ claim severity 0.79, confidence 0.71, horizon 96 h | keep_plan | KEEP_CURRENT_PLAN | 36.2 h (regret 0.3) | portwatch_balanced: slow_steam at 35.9 h |
| vessel-1091 | EUR_IND hull 72 h from Suez; SUEZ claim severity 0.76, confidence 0.93, horizon 96 h | keep_plan | KEEP_CURRENT_PLAN | 39.6 h (regret 8.1) | portwatch_balanced: slow_steam at 31.5 h |
| vessel-1093 | USEC_IND hull 43 h from Suez; SUEZ claim severity 0.70, confidence 0.79, horizon 72 h | keep_plan | KEEP_CURRENT_PLAN | 24.5 h (regret 2.9) | heuristic: slow_steam at 21.6 h; portwatch_balanced: slow_steam at 21.6 h |
| port-1002 | INCOK: 3 calls over 2 berths, 0 with departure commitments | reassign_berth-greedy | ACT | 2.8 h (regret 2.75) | current_plan: keep_schedule at 0.0 h; heuristic: keep_schedule at 0.0 h |
| port-1003 | INMAA: 6 calls over 2 berths, 1 with departure commitments | change_crane_allocation | ACT | 8.1 h (regret 8.12) | current_plan: keep_schedule at 0.0 h; greedy: keep_schedule at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-1013 | INNSA: 5 calls over 2 berths, 2 with departure commitments | keep_schedule | KEEP_CURRENT_PLAN | 8.3 h (regret 0.83) | greedy: reassign_berth-greedy at 7.5 h |
| port-1014 | INNSA: 5 calls over 3 berths, 2 with departure commitments | change_crane_allocation | ACT | 2.0 h (regret 2.0) | current_plan: keep_schedule at 0.0 h; greedy: shift_arrival_slot at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-1018 | INCOK: 5 calls over 2 berths, 1 with departure commitments | reassign_berth-greedy | ACT | 1.0 h (regret 1.0) | current_plan: keep_schedule at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-1021 | INNSA: 3 calls over 3 berths, 0 with departure commitments | shift_arrival_slot | ACT | 2.2 h (regret 1.17) | current_plan: keep_schedule at 1.5 h |
| port-1025 | INCOK: 6 calls over 2 berths, 3 with departure commitments | change_crane_allocation | ACT | 14.4 h (regret 7.94) | current_plan: keep_schedule at 9.5 h; greedy: reassign_berth-greedy at 6.5 h; heuristic: prioritise_vessel at 9.5 h |
| port-1033 | INNSA: 6 calls over 2 berths, 3 with departure commitments | shift_arrival_slot | ACT | 12.8 h (regret 3.41) | greedy: reassign_berth-greedy at 9.4 h |
| port-1037 | INNSA: 4 calls over 2 berths, 2 with departure commitments | keep_schedule | KEEP_CURRENT_PLAN | 10.6 h (regret 4.0) | greedy: reassign_berth-greedy at 6.6 h |
| port-1038 | INMAA: 3 calls over 3 berths, 1 with departure commitments | change_crane_allocation | ACT | 8.9 h (regret 8.92) | current_plan: keep_schedule at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-1039 | INCOK: 5 calls over 3 berths, 1 with departure commitments | change_crane_allocation | ACT | 11.7 h (regret 8.07) | current_plan: keep_schedule at 3.6 h; heuristic: prioritise_vessel at 3.6 h |
| port-1042 | INNSA: 5 calls over 2 berths, 2 with departure commitments | reassign_berth-greedy | ACT | 16.2 h (regret 3.29) | current_plan: keep_schedule at 12.9 h; greedy: keep_schedule at 12.9 h; heuristic: prioritise_vessel at 12.9 h |
| port-1048 | INNSA: 5 calls over 3 berths, 1 with departure commitments | change_crane_allocation | ACT | 12.8 h (regret 6.08) | current_plan: keep_schedule at 11.7 h; greedy: shift_arrival_slot at 11.0 h; heuristic: prioritise_vessel at 11.7 h |
| port-1049 | INCOK: 6 calls over 3 berths, 2 with departure commitments | change_crane_allocation | ACT | 10.8 h (regret 3.14) | current_plan: keep_schedule at 7.7 h; heuristic: prioritise_vessel at 7.7 h |
| port-1054 | INMAA: 5 calls over 2 berths, 2 with departure commitments | reassign_berth-greedy | ACT | 16.8 h (regret 16.75) | current_plan: keep_schedule at 0.0 h; greedy: change_crane_allocation at 9.2 h; heuristic: prioritise_vessel at 0.0 h |
| port-1056 | INCOK: 6 calls over 3 berths, 2 with departure commitments | reassign_berth-greedy | ACT | 3.4 h (regret 1.61) | current_plan: keep_schedule at 1.8 h; heuristic: prioritise_vessel at 1.8 h |
| port-1063 | INMAA: 5 calls over 2 berths, 1 with departure commitments | change_crane_allocation | ACT | 11.2 h (regret 6.79) | current_plan: keep_schedule at 4.4 h; heuristic: prioritise_vessel at 4.4 h |
| port-1066 | INCOK: 6 calls over 2 berths, 4 with departure commitments | keep_schedule | KEEP_CURRENT_PLAN | 11.9 h (regret 3.12) | greedy: reassign_berth-greedy at 8.8 h |
| port-1078 | INMAA: 5 calls over 2 berths, 2 with departure commitments | change_crane_allocation | ACT | 13.6 h (regret 13.62) | current_plan: keep_schedule at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-1080 | INMAA: 6 calls over 3 berths, 4 with departure commitments | change_crane_allocation | ACT | 11.4 h (regret 6.7) | current_plan: keep_schedule at 9.2 h; greedy: reassign_berth-greedy at 4.8 h; heuristic: prioritise_vessel at 9.2 h |
| port-1089 | INNSA: 4 calls over 2 berths, 0 with departure commitments | change_crane_allocation | ACT | 7.1 h (regret 2.0) | greedy: reassign_berth-greedy at 5.1 h |
| port-1095 | INCOK: 4 calls over 3 berths, 1 with departure commitments | reassign_berth-greedy | ACT | 9.7 h (regret 2.19) | greedy: change_crane_allocation at 7.5 h |
| port-1098 | INMAA: 6 calls over 2 berths, 1 with departure commitments | change_crane_allocation | ACT | 6.9 h (regret 4.67) | current_plan: keep_schedule at 2.2 h; greedy: reassign_berth-greedy at 6.0 h; heuristic: prioritise_vessel at 2.2 h |
| cargo-1093 | INNSA: 12 TEU dry to SGSIN, ready hour 2.6, booked sailing hour 6.4, 3 alternatives | transfer_to_vessel-BM-OUT-1093-2 | ACT | 9.6 h (regret 0.0) | current_plan: keep_connection at 6.1 h |

# TEST corpus — seeds 5001-5200, 200 cases per domain

## VESSEL — 200 cases

| policy | mean delay (h) | mean regret (h) | median regret | p90 regret | worst regret | zero-regret share | violations | intervention rate | unnecessary interventions | wait rate | mean decision time | p95 decision time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_plan | 51.07 | 1.05 | 0.00 | 0.00 | 67.40 | 0.95 | 0 | 0% | — | 0% | 0.00 ms | 0.00 ms |
| greedy | 51.07 | 1.05 | 0.00 | 0.00 | 67.40 | 0.95 | 0 | 0% | — | 0% | 0.02 ms | 0.02 ms |
| heuristic | 120.46 | 70.43 | 0.00 | 364.40 | 573.70 | 0.57 | 0 | 42% | 93% | 0% | 0.01 ms | 0.02 ms |
| portwatch_balanced | 62.16 | 12.14 | 0.00 | 42.10 | 77.80 | 0.51 | 0 | 48% | 93% | 0% | 67.71 ms | 93.83 ms |
| portwatch_robust | 51.07 | 1.05 | 0.00 | 0.00 | 67.40 | 0.95 | 0 | 0% | — | 2% | 67.71 ms | 93.83 ms |

An intervention was the realised best on 10 case(s); captured by: current_plan 0%, greedy 0%, heuristic 60%, portwatch_balanced 70%, portwatch_robust 0%.

`portwatch_robust` answered: KEEP_CURRENT_PLAN 196, WAIT_FOR_MORE_INFORMATION 4.

Head to head on realised delay (cases both policies scored):

| policy | against | wins | loses | ties |
|---|---|---:|---:|---:|
| portwatch_balanced | current_plan | 7 | 90 | 93 |
| portwatch_balanced | greedy | 7 | 90 | 93 |
| portwatch_balanced | heuristic | 32 | 18 | 140 |
| portwatch_balanced | portwatch_robust | 7 | 90 | 93 |
| portwatch_robust | current_plan | 0 | 0 | 190 |
| portwatch_robust | greedy | 0 | 0 | 190 |
| portwatch_robust | heuristic | 78 | 6 | 106 |
| portwatch_robust | portwatch_balanced | 90 | 7 | 93 |

## PORT — 200 cases

| policy | mean delay (h) | mean regret (h) | median regret | p90 regret | worst regret | zero-regret share | violations | intervention rate | unnecessary interventions | wait rate | mean decision time | p95 decision time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_plan | 6.69 | 2.24 | 1.00 | 5.62 | 19.62 | 0.31 | 72 | 0% | — | 0% | 0.00 ms | 0.00 ms |
| greedy | 5.20 | 0.76 | 0.00 | 2.75 | 9.62 | 0.72 | 51 | 76% | 23% | 0% | 0.02 ms | 0.03 ms |
| heuristic | 6.68 | 2.24 | 1.00 | 5.62 | 19.62 | 0.32 | 75 | 96% | 96% | 0% | 0.01 ms | 0.01 ms |
| portwatch_balanced | 5.55 | 1.13 | 0.00 | 3.88 | 16.88 | 0.66 | 45 | 79% | 28% | 0% | 38.92 ms | 49.26 ms |
| portwatch_robust | 5.55 | 1.13 | 0.00 | 3.88 | 16.88 | 0.66 | 45 | 79% | 28% | 0% | 38.92 ms | 49.26 ms |

An intervention was the realised best on 135 case(s); captured by: current_plan 0%, greedy 87%, heuristic 3%, portwatch_balanced 83%, portwatch_robust 83%.

`portwatch_robust` answered: ACT 158, KEEP_CURRENT_PLAN 42.

Head to head on realised delay (cases both policies scored):

| policy | against | wins | loses | ties |
|---|---|---:|---:|---:|
| portwatch_balanced | current_plan | 112 | 31 | 53 |
| portwatch_balanced | greedy | 3 | 18 | 175 |
| portwatch_balanced | heuristic | 110 | 32 | 54 |
| portwatch_balanced | portwatch_robust | 0 | 0 | 197 |
| portwatch_robust | current_plan | 112 | 31 | 53 |
| portwatch_robust | greedy | 3 | 18 | 175 |
| portwatch_robust | heuristic | 110 | 32 | 54 |
| portwatch_robust | portwatch_balanced | 0 | 0 | 197 |

## CARGO — 200 cases

| policy | mean delay (h) | mean regret (h) | median regret | p90 regret | worst regret | zero-regret share | violations | intervention rate | unnecessary interventions | wait rate | mean decision time | p95 decision time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_plan | 36.33 | 0.02 | 0.00 | 0.00 | 2.00 | 0.67 | 264 | 0% | — | 0% | 0.00 ms | 0.00 ms |
| greedy | 36.39 | 0.00 | 0.00 | 0.00 | 0.20 | 0.67 | 158 | 32% | 97% | 0% | 0.01 ms | 0.01 ms |
| heuristic | 37.14 | 1.11 | 0.00 | 3.00 | 24.80 | 0.59 | 153 | 34% | 100% | 0% | 0.01 ms | 0.01 ms |
| portwatch_balanced | 36.39 | 0.00 | 0.00 | 0.00 | 0.20 | 0.67 | 158 | 32% | 97% | 0% | 1.61 ms | 2.74 ms |
| portwatch_robust | 36.39 | 0.00 | 0.00 | 0.00 | 0.20 | 0.67 | 158 | 32% | 97% | 0% | 1.61 ms | 2.74 ms |

An intervention was the realised best on 2 case(s); captured by: current_plan 0%, greedy 100%, heuristic 0%, portwatch_balanced 100%, portwatch_robust 100%.

`portwatch_robust` answered: ACT 63, KEEP_CURRENT_PLAN 72.

Head to head on realised delay (cases both policies scored):

| policy | against | wins | loses | ties |
|---|---|---:|---:|---:|
| portwatch_balanced | current_plan | 2 | 2 | 196 |
| portwatch_balanced | greedy | 0 | 0 | 200 |
| portwatch_balanced | heuristic | 17 | 1 | 182 |
| portwatch_balanced | portwatch_robust | 0 | 0 | 200 |
| portwatch_robust | current_plan | 2 | 2 | 196 |
| portwatch_robust | greedy | 0 | 0 | 200 |
| portwatch_robust | heuristic | 17 | 1 | 182 |
| portwatch_robust | portwatch_balanced | 0 | 0 | 200 |

## Where `portwatch_robust` lost — 50 case(s)

| case | what the case was | robust chose | kind | realised | beaten by |
|---|---|---|---|---:|---|
| vessel-5007 | MED_IND hull 34 h from Suez; BAB_EL_MANDEB claim severity 0.69, confidence 0.83, horizon 96 h | keep_plan | KEEP_CURRENT_PLAN | 53.1 h (regret 7.8) | heuristic: slow_steam at 45.3 h; portwatch_balanced: slow_steam at 45.3 h |
| vessel-5031 | EUR_IND hull 62 h from Suez; SUEZ claim severity 0.51, confidence 0.59, horizon 96 h | keep_plan | KEEP_CURRENT_PLAN | 35.0 h (regret 4.5) | heuristic: slow_steam at 30.5 h; portwatch_balanced: slow_steam at 30.5 h |
| vessel-5047 | USEC_IND hull 49 h from Suez; BAB_EL_MANDEB claim severity 0.53, confidence 0.85, horizon 96 h | keep_plan | KEEP_CURRENT_PLAN | 42.5 h (regret 8.3) | heuristic: slow_steam at 34.2 h; portwatch_balanced: slow_steam at 34.2 h |
| vessel-5094 | USEC_IND hull 6 h from Suez; BAB_EL_MANDEB claim severity 0.63, confidence 0.46, horizon 48 h | keep_plan | KEEP_CURRENT_PLAN | 15.1 h (regret 2.1) | heuristic: slow_steam at 13.0 h; portwatch_balanced: slow_steam at 13.0 h |
| vessel-5114 | USEC_IND hull 20 h from Suez; BAB_EL_MANDEB claim severity 0.59, confidence 0.72, horizon 96 h | keep_plan | KEEP_CURRENT_PLAN | 43.3 h (regret 2.3) | heuristic: slow_steam at 41.0 h; portwatch_balanced: slow_steam at 41.0 h |
| vessel-5131 | MED_IND hull 25 h from Suez; SUEZ claim severity 0.25, confidence 0.82, horizon 48 h | keep_plan | KEEP_CURRENT_PLAN | 23.2 h (regret 0.3) | portwatch_balanced: slow_steam at 22.9 h |
| vessel-5133 | MED_IND hull 32 h from Suez; SUEZ claim severity 0.60, confidence 0.51, horizon 48 h | keep_plan | KEEP_CURRENT_PLAN | 27.5 h (regret 4.8) | heuristic: slow_steam at 22.7 h; portwatch_balanced: slow_steam at 22.7 h |
| port-5008 | INMAA: 5 calls over 3 berths, 1 with departure commitments | change_crane_allocation | ACT | 7.8 h (regret 0.3) | current_plan: keep_schedule at 7.5 h; heuristic: prioritise_vessel at 7.5 h |
| port-5014 | INCOK: 5 calls over 2 berths, 1 with departure commitments | change_crane_allocation | ACT | 19.5 h (regret 16.88) | current_plan: keep_schedule at 2.6 h; greedy: reassign_berth-greedy at 8.6 h; heuristic: prioritise_vessel at 2.6 h |
| port-5026 | INNSA: 3 calls over 2 berths, 1 with departure commitments | change_crane_allocation | ACT | 3.4 h (regret 1.42) | current_plan: keep_schedule at 2.0 h; heuristic: prioritise_vessel at 2.0 h |
| port-5027 | INCOK: 5 calls over 2 berths, 2 with departure commitments | change_crane_allocation | ACT | 8.6 h (regret 2.38) | current_plan: keep_schedule at 6.2 h; heuristic: prioritise_vessel at 6.2 h |
| port-5033 | INNSA: 5 calls over 3 berths, 2 with departure commitments | reassign_berth-greedy | ACT | 1.7 h (regret 1.69) | current_plan: keep_schedule at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-5041 | INMAA: 5 calls over 3 berths, 1 with departure commitments | reassign_berth-greedy | ACT | 9.7 h (regret 8.11) | current_plan: keep_schedule at 2.1 h; heuristic: prioritise_vessel at 2.1 h |
| port-5045 | INCOK: 5 calls over 3 berths, 2 with departure commitments | reassign_berth-greedy | ACT | 9.9 h (regret 4.03) | greedy: change_crane_allocation at 5.8 h |
| port-5048 | INNSA: 6 calls over 2 berths, 1 with departure commitments | reassign_berth-greedy | ACT | 5.8 h (regret 5.75) | current_plan: keep_schedule at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-5049 | INMAA: 5 calls over 3 berths, 2 with departure commitments | change_crane_allocation | ACT | 11.0 h (regret 3.75) | current_plan: keep_schedule at 7.2 h; heuristic: prioritise_vessel at 7.2 h |
| port-5053 | INMAA: 6 calls over 2 berths, 2 with departure commitments | reassign_berth-greedy | ACT | 12.2 h (regret 6.45) | current_plan: keep_schedule at 5.8 h; greedy: keep_schedule at 5.8 h; heuristic: prioritise_vessel at 5.8 h |
| port-5055 | INCOK: 4 calls over 2 berths, 2 with departure commitments | reassign_berth-greedy | ACT | 13.1 h (regret 13.12) | current_plan: keep_schedule at 0.0 h; greedy: change_crane_allocation at 9.6 h; heuristic: prioritise_vessel at 0.0 h |
| port-5057 | INMAA: 4 calls over 3 berths, 1 with departure commitments | reassign_berth-greedy | ACT | 5.7 h (regret 2.04) | current_plan: keep_schedule at 3.6 h; heuristic: prioritise_vessel at 3.6 h |
| port-5058 | INNSA: 5 calls over 2 berths, 2 with departure commitments | change_crane_allocation | ACT | 6.1 h (regret 6.12) | current_plan: keep_schedule at 0.0 h; greedy: keep_schedule at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-5059 | INCOK: 6 calls over 2 berths, 3 with departure commitments | change_crane_allocation | ACT | 6.1 h (regret 6.12) | current_plan: keep_schedule at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-5060 | INMAA: 4 calls over 2 berths, 1 with departure commitments | change_crane_allocation | ACT | 9.4 h (regret 2.58) | greedy: reassign_berth-greedy at 6.8 h |
| port-5061 | INCOK: 6 calls over 3 berths, 3 with departure commitments | change_crane_allocation | ACT | 13.9 h (regret 9.5) | current_plan: keep_schedule at 11.4 h; greedy: reassign_berth-greedy at 4.5 h; heuristic: prioritise_vessel at 11.4 h |
| port-5068 | INMAA: 5 calls over 3 berths, 3 with departure commitments | keep_schedule | KEEP_CURRENT_PLAN | 15.9 h (regret 1.22) | greedy: shift_arrival_slot at 15.4 h |
| port-5069 | INMAA: 5 calls over 3 berths, 2 with departure commitments | shift_arrival_slot | ACT | 7.2 h (regret 1.25) | greedy: change_crane_allocation at 6.0 h |
| port-5073 | INMAA: 6 calls over 2 berths, 1 with departure commitments | change_crane_allocation | ACT | 17.5 h (regret 1.33) | current_plan: keep_schedule at 17.2 h; heuristic: prioritise_vessel at 17.2 h |
| port-5077 | INCOK: 6 calls over 3 berths, 4 with departure commitments | reassign_berth-greedy | ACT | 6.3 h (regret 6.31) | current_plan: keep_schedule at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-5078 | INCOK: 4 calls over 3 berths, 3 with departure commitments | change_crane_allocation | ACT | 5.2 h (regret 3.6) | current_plan: keep_schedule at 1.6 h; heuristic: prioritise_vessel at 1.6 h |
| port-5079 | INNSA: 5 calls over 3 berths, 1 with departure commitments | change_crane_allocation | ACT | 9.7 h (regret 6.12) | current_plan: keep_schedule at 3.9 h; greedy: shift_arrival_slot at 3.6 h; heuristic: prioritise_vessel at 3.9 h |
| port-5083 | INCOK: 5 calls over 3 berths, 3 with departure commitments | change_crane_allocation | ACT | 4.4 h (regret 2.04) | current_plan: keep_schedule at 2.3 h; heuristic: prioritise_vessel at 2.3 h |
| port-5110 | INCOK: 6 calls over 3 berths, 2 with departure commitments | change_crane_allocation | ACT | 3.5 h (regret 1.55) | greedy: shift_arrival_slot at 1.9 h |
| port-5121 | INCOK: 5 calls over 3 berths, 1 with departure commitments | change_crane_allocation | ACT | 12.8 h (regret 2.91) | current_plan: keep_schedule at 10.9 h; heuristic: prioritise_vessel at 10.9 h |
| port-5125 | INCOK: 3 calls over 2 berths, 1 with departure commitments | change_crane_allocation | ACT | 9.2 h (regret 6.92) | current_plan: keep_schedule at 2.6 h; heuristic: prioritise_vessel at 2.6 h |
| port-5126 | INNSA: 5 calls over 2 berths, 4 with departure commitments | change_crane_allocation | ACT | 6.0 h (regret 3.12) | current_plan: keep_schedule at 2.9 h; heuristic: prioritise_vessel at 2.9 h |
| port-5127 | INMAA: 5 calls over 2 berths, 4 with departure commitments | shift_arrival_slot | ACT | 6.8 h (regret 0.81) | current_plan: keep_schedule at 6.0 h; heuristic: prioritise_vessel at 6.0 h |
| port-5132 | INMAA: 3 calls over 2 berths, 1 with departure commitments | change_crane_allocation | ACT | 6.8 h (regret 3.38) | current_plan: keep_schedule at 3.4 h; heuristic: prioritise_vessel at 3.4 h |
| port-5140 | INMAA: 6 calls over 2 berths, 1 with departure commitments | reassign_berth-greedy | ACT | 11.9 h (regret 5.65) | current_plan: keep_schedule at 6.2 h; greedy: keep_schedule at 6.2 h; heuristic: prioritise_vessel at 6.2 h |
| port-5149 | INCOK: 5 calls over 3 berths, 2 with departure commitments | change_crane_allocation | ACT | 5.1 h (regret 1.41) | greedy: reassign_berth-greedy at 3.7 h |
| port-5154 | INCOK: 6 calls over 2 berths, 3 with departure commitments | reassign_berth-greedy | ACT | 3.2 h (regret 3.17) | current_plan: keep_schedule at 0.0 h; greedy: keep_schedule at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-5173 | INMAA: 3 calls over 2 berths, 1 with departure commitments | change_crane_allocation | ACT | 7.3 h (regret 0.33) | greedy: shift_arrival_slot at 7.0 h |
| port-5175 | INMAA: 5 calls over 3 berths, 3 with departure commitments | change_crane_allocation | ACT | 9.8 h (regret 3.68) | current_plan: keep_schedule at 6.1 h; heuristic: prioritise_vessel at 6.1 h |
| port-5179 | INCOK: 3 calls over 3 berths, 0 with departure commitments | reassign_berth-greedy | ACT | 9.3 h (regret 1.75) | heuristic: shift_arrival_slot at 8.7 h |
| port-5180 | INNSA: 3 calls over 2 berths, 1 with departure commitments | reassign_berth-greedy | ACT | 8.1 h (regret 8.12) | current_plan: keep_schedule at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-5185 | INCOK: 4 calls over 2 berths, 2 with departure commitments | reassign_berth-greedy | ACT | 5.8 h (regret 1.88) | current_plan: keep_schedule at 3.9 h; heuristic: prioritise_vessel at 3.9 h |
| port-5186 | INNSA: 5 calls over 3 berths, 2 with departure commitments | change_crane_allocation | ACT | 7.5 h (regret 2.0) | current_plan: keep_schedule at 6.0 h; greedy: shift_arrival_slot at 5.5 h; heuristic: prioritise_vessel at 6.0 h |
| port-5189 | INMAA: 5 calls over 2 berths, 2 with departure commitments | change_crane_allocation | ACT | 21.6 h (regret 1.38) | greedy: shift_arrival_slot at 20.2 h |
| port-5192 | INMAA: 5 calls over 3 berths, 0 with departure commitments | change_crane_allocation | ACT | 5.7 h (regret 1.2) | current_plan: keep_schedule at 4.5 h; heuristic: shift_arrival_slot at 4.5 h |
| port-5196 | INCOK: 6 calls over 2 berths, 4 with departure commitments | keep_schedule | KEEP_CURRENT_PLAN | 14.2 h (regret 6.5) | greedy: reassign_berth-greedy at 7.8 h |
| cargo-5068 | INNSA: 2 TEU dry to AEJEA, ready hour 7.7, booked sailing hour 11.2, 1 alternatives | transfer_to_vessel-BM-OUT-5068-1 | ACT | 18.2 h (regret 0.0) | current_plan: keep_connection at 4.1 h |
| cargo-5168 | INNSA: 4 TEU dry to LKCMB, ready hour 5.1, booked sailing hour 12.9, 2 alternatives | transfer_to_vessel-BM-OUT-5168-1 | ACT | 17.0 h (regret 0.2) | current_plan: keep_connection at 16.8 h; heuristic: transfer_to_vessel-BM-OUT-5168-2 at 16.8 h |

# Reading the result

- **tuning / VESSEL**: the robust policy's mean regret is 0.16 h against the incumbent's 5.72 h and the current plan's 0.16 h; p90 0.0 against 19.6; worst 2.9 against 67.8. It intervened on 0% of cases (incumbent 30%), answered WAIT on 0%, and captured 0% of the 3 case(s) where an intervention was the realised best (incumbent 100%).
- **tuning / PORT**: identical to the incumbent (mean regret 0.62 h, 16 violations); the robust gate does not apply to this domain.
- **tuning / CARGO**: identical to the incumbent (mean regret 0.02 h, 31 violations); the robust gate does not apply to this domain.
- **validation / VESSEL**: the robust policy's mean regret is 1.07 h against the incumbent's 12.46 h and the current plan's 1.07 h; p90 0.0 against 36.9; worst 80.1 against 80.1. It intervened on 0% of cases (incumbent 44%), answered WAIT on 1%, and captured 0% of the 5 case(s) where an intervention was the realised best (incumbent 80%).
- **validation / PORT**: identical to the incumbent (mean regret 1.3 h, 26 violations); the robust gate does not apply to this domain.
- **validation / CARGO**: identical to the incumbent (mean regret 0.01 h, 79 violations); the robust gate does not apply to this domain.
- **test / VESSEL**: the robust policy's mean regret is 1.05 h against the incumbent's 12.14 h and the current plan's 1.05 h; p90 0.0 against 42.1; worst 67.4 against 77.8. It intervened on 0% of cases (incumbent 48%), answered WAIT on 2%, and captured 0% of the 10 case(s) where an intervention was the realised best (incumbent 70%).
- **test / PORT**: identical to the incumbent (mean regret 1.13 h, 45 violations); the robust gate does not apply to this domain.
- **test / CARGO**: identical to the incumbent (mean regret 0.0 h, 158 violations); the robust gate does not apply to this domain.
- **tuning / VESSEL, the hedge**: the incumbent hedged (an action other than proceeding) on 12 of 40 cases and the hedge beat proceeding on 3, lost on 9. The robust policy hedged on 0. Under the closure outcome model a hold that arrives just after the claim lapses lands at the back of the queue the closure formed, so it pays only in a narrow band of closure lengths; the panel now shows that band as the break-even.
- **validation / VESSEL, the hedge**: the incumbent hedged (an action other than proceeding) on 43 of 98 cases and the hedge beat proceeding on 4, lost on 39. The robust policy hedged on 0. Under the closure outcome model a hold that arrives just after the claim lapses lands at the back of the queue the closure formed, so it pays only in a narrow band of closure lengths; the panel now shows that band as the break-even.
- **test / VESSEL, the hedge**: the incumbent hedged (an action other than proceeding) on 97 of 200 cases and the hedge beat proceeding on 7, lost on 90. The robust policy hedged on 0. Under the closure outcome model a hold that arrives just after the claim lapses lands at the back of the queue the closure formed, so it pays only in a narrow band of closure lengths; the panel now shows that band as the break-even.
- The baselines were handed the engine's simulated options; their decision times are selection only. A baseline that had to enumerate and simulate its own options would pay what PortWatch pays.
