# Decision benchmark

Measured 2026-09-15T03:22:40+00:00. Produced by `python scripts/benchmark_decisions.py --cases 40 --seed 1`; the corpus is fixed by those two numbers and nothing in it was chosen after seeing a result.

Four policies choose from the same simulated option set on every case, so the comparison isolates what the optimiser adds (the frontier, the balanced ranking, the Critic) from what the simulator adds. Each case has a hidden truth the policies never see; every chosen option is scored against it. `regret` is the realised delay of the chosen option minus the realised delay of the best feasible option on that case. Decision time for `portwatch` includes building and evaluating the whole problem; the baselines are charged only for their selection because they are handed the engine's options.

## How each domain is scored

- **VESSEL** — a chokepoint claim and a hull bound through it. Truth: the closure's actual duration, lognormal around a median that grows with severity, fizzling with probability falling in corroboration. Options are scored by the mission scorecard's realised model (wait for the reopening, then a queue drained in arrival order; a detour is certain). A `change_destination_port` option has no realised model and is unscored.
- **PORT** — a berth plan for three to six calls that bunch. Truth: arrivals slip (N(+1.0, 1.5) h) and moves run over (×N(1.08, 0.15)). Each plan is re-simulated by the port twin on the true state. Delay is mean wait; a missed departure commitment is a violation.
- **CARGO** — a transshipment connection. Truth: the inbound discharge slips (N(+1.2, 1.4) h, never earlier) and every cut-off moves (N(0, 0.8) h). Delay is hours from the true ready hour to the sailing actually made; a missed connection is a violation and the box takes the next feasible sailing (72 h if there is none in the case).

## VESSEL — 40 cases

| policy | mean delay (h) | mean regret (h) | zero-regret share | violations | mean risk | mean fuel index | mean berth utilisation | mean decision time | unscored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_plan | 45.06 | 0.16 | 0.92 | 0 | 0.41 | 1.00 | — | 0.00 ms | 3 |
| greedy | 45.06 | 0.16 | 0.92 | 0 | 0.41 | 1.00 | — | 0.00 ms | 3 |
| heuristic | 102.28 | 57.38 | 0.73 | 0 | 0.16 | 1.29 | — | 0.00 ms | 3 |
| portwatch | 50.62 | 5.72 | 0.76 | 0 | 0.27 | 0.97 | — | 13.81 ms | 3 |

Head to head on realised delay (cases both policies scored):

| against | PortWatch wins | PortWatch loses | ties |
|---|---:|---:|---:|
| current_plan | 3 | 9 | 25 |
| greedy | 3 | 9 | 25 |
| heuristic | 7 | 2 | 28 |

## PORT — 40 cases

| policy | mean delay (h) | mean regret (h) | zero-regret share | violations | mean risk | mean fuel index | mean berth utilisation | mean decision time | unscored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_plan | 6.93 | 2.49 | 0.26 | 23 | 0.44 | — | 0.46 | 0.00 ms | 1 |
| greedy | 4.95 | 0.51 | 0.80 | 20 | 0.36 | — | 0.44 | 0.00 ms | 1 |
| heuristic | 6.93 | 2.49 | 0.26 | 24 | 0.44 | — | 0.46 | 0.00 ms | 1 |
| portwatch | 4.95 | 0.62 | 0.78 | 16 | 0.28 | — | 0.44 | 8.09 ms | 0 |

Head to head on realised delay (cases both policies scored):

| against | PortWatch wins | PortWatch loses | ties |
|---|---:|---:|---:|
| current_plan | 26 | 3 | 10 |
| greedy | 2 | 3 | 34 |
| heuristic | 26 | 3 | 10 |

## CARGO — 40 cases

| policy | mean delay (h) | mean regret (h) | zero-regret share | violations | mean risk | mean fuel index | mean berth utilisation | mean decision time | unscored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_plan | 34.99 | 0.00 | 0.70 | 46 | 0.65 | — | — | 0.00 ms | 0 |
| greedy | 35.01 | 0.02 | 0.65 | 31 | 0.47 | — | — | 0.00 ms | 0 |
| heuristic | 35.45 | 0.66 | 0.65 | 29 | 0.42 | — | — | 0.00 ms | 0 |
| portwatch | 35.01 | 0.02 | 0.65 | 31 | 0.47 | — | — | 0.34 ms | 0 |

Head to head on realised delay (cases both policies scored):

| against | PortWatch wins | PortWatch loses | ties |
|---|---:|---:|---:|
| current_plan | 0 | 2 | 38 |
| greedy | 0 | 0 | 40 |
| heuristic | 2 | 1 | 37 |

## Where PortWatch lost — 16 case(s)

| case | what the case was | PortWatch chose | realised | beaten by |
|---|---|---|---:|---|
| vessel-4 | MED_IND hull -17 h from Suez; BAB_EL_MANDEB claim severity 0.33, confidence 0.62, horizon 48 h | slow_steam | 35.7 h (regret 12.1) | current_plan: keep_plan at 23.6 h; greedy: keep_plan at 23.6 h; heuristic: keep_plan at 23.6 h |
| vessel-8 | MED_IND hull -1 h from Suez; BAB_EL_MANDEB claim severity 0.97, confidence 0.47, horizon 96 h | slow_steam | 67.8 h (regret 67.8) | current_plan: keep_plan at 0.0 h; greedy: keep_plan at 0.0 h |
| vessel-9 | USEC_IND hull 50 h from Suez; SUEZ claim severity 0.53, confidence 0.48, horizon 96 h | slow_steam | 47.0 h (regret 44.7) | current_plan: keep_plan at 2.3 h; greedy: keep_plan at 2.3 h |
| vessel-11 | USEC_IND hull 62 h from Suez; SUEZ claim severity 0.89, confidence 0.83, horizon 72 h | slow_steam | 71.0 h (regret 2.8) | current_plan: keep_plan at 68.2 h; greedy: keep_plan at 68.2 h |
| vessel-17 | MED_IND hull 73 h from Suez; SUEZ claim severity 0.97, confidence 0.56, horizon 96 h | slow_steam | 182.8 h (regret 12.3) | current_plan: keep_plan at 170.5 h; greedy: keep_plan at 170.5 h |
| vessel-19 | USEC_IND hull 20 h from Suez; BAB_EL_MANDEB claim severity 0.34, confidence 0.51, horizon 72 h | slow_steam | 11.5 h (regret 11.5) | current_plan: keep_plan at 0.0 h; greedy: keep_plan at 0.0 h; heuristic: keep_plan at 0.0 h |
| vessel-35 | EUR_IND hull 15 h from Suez; SUEZ claim severity 0.81, confidence 0.88, horizon 72 h | slow_steam | 179.3 h (regret 25.7) | current_plan: keep_plan at 153.6 h; greedy: keep_plan at 153.6 h |
| vessel-38 | MED_IND hull 32 h from Suez; SUEZ claim severity 0.82, confidence 0.46, horizon 72 h | slow_steam | 85.1 h (regret 15.0) | current_plan: keep_plan at 70.1 h; greedy: keep_plan at 70.1 h |
| vessel-39 | MED_IND hull -19 h from Suez; BAB_EL_MANDEB claim severity 0.54, confidence 0.51, horizon 72 h | slow_steam | 75.5 h (regret 19.6) | current_plan: keep_plan at 55.9 h; greedy: keep_plan at 55.9 h |
| port-11 | INNSA: 4 calls over 3 berths, 1 with departure commitments | change_crane_allocation | 11.9 h (regret 7.04) | current_plan: keep_schedule at 6.2 h; heuristic: prioritise_vessel at 6.2 h |
| port-24 | INMAA: 5 calls over 3 berths, 2 with departure commitments | change_crane_allocation | 2.8 h (regret 1.58) | current_plan: keep_schedule at 1.2 h; heuristic: prioritise_vessel at 1.2 h |
| port-26 | INMAA: 5 calls over 3 berths, 2 with departure commitments | reassign_berth-greedy | 6.3 h (regret 6.33) | current_plan: keep_schedule at 0.0 h; greedy: keep_schedule at 0.0 h; heuristic: prioritise_vessel at 0.0 h |
| port-31 | INCOK: 5 calls over 2 berths, 1 with departure commitments | change_crane_allocation | 8.9 h (regret 0.75) | greedy: reassign_berth-greedy at 8.2 h |
| port-37 | INMAA: 3 calls over 3 berths, 1 with departure commitments | change_crane_allocation | 3.5 h (regret 1.67) | greedy: reassign_berth-greedy at 1.8 h |
| cargo-14 | INNSA: 8 TEU dry to MYPKG, ready hour 7.6, booked sailing hour 13.0, 3 alternatives | transfer_to_vessel-BM-OUT-14-3 | 5.5 h (regret 0.1) | current_plan: keep_connection at 5.4 h |
| cargo-32 | INMAA: 12 TEU dry to MYPKG, ready hour 2.6, booked sailing hour 12.5, 3 alternatives | transfer_to_vessel-BM-OUT-32-3 | 8.6 h (regret 0.5) | current_plan: keep_connection at 8.1 h; heuristic: keep_connection at 8.1 h |

## Reading the result

- **VESSEL**: PortWatch's mean regret 5.72 h is *higher* than the best baseline's (current_plan, 0.16 h), with 0 violations -- as many violations as the best baseline (fewest 0). The losses table says where it lost on delay.
- **PORT**: PortWatch's mean regret 0.62 h is *higher* than the best baseline's (greedy, 0.51 h), with 16 violations -- fewer violations than any baseline (fewest 20). The losses table says where it lost on delay.
- **CARGO**: PortWatch's mean regret 0.02 h is *higher* than the best baseline's (current_plan, 0.0 h), with 31 violations -- more violations than the best baseline (fewest 29). The losses table says where it lost on delay.
- **VESSEL, the hedge**: on 12 of 40 cases the engine recommended an action other than proceeding (a slow-steam hold to arrive after the claim horizon, mostly). The hedge beat proceeding on 3 and lost on 9; 2 of the losses were claims that fizzled, where the hold was pure cost. Under the realised queue model a hull that arrives early in a closure queues near the front, so holding rarely pays unless the closure outlasts the claim horizon by a wide margin. The BALANCED ranking pays for zero exposure with hours; this corpus says how many.
- Losses by domain: CARGO 2, PORT 5, VESSEL 9.
- The baselines were handed the engine's simulated options; their decision times are selection only. A baseline that had to enumerate and simulate its own options would pay what PortWatch pays.
