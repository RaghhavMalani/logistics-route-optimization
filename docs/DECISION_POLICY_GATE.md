# Decision policy promotion gate

Measured 2026-09-15T10:02:24+00:00. Produced by `python scripts/benchmark_decisions.py`.

The robust recommendation policy (`portwatch_robust`) is a candidate; the BALANCED expected-value ranking (`portwatch_balanced`) is the incumbent. The candidate becomes the engine's default only if it clears every check below on the validation corpus and on the untouched test corpus. The conditions were fixed in `src/portwatch_os/decision/promotion.py` before either corpus was run:

- a material improvement is 10% on mean and p90 regret on VESSEL, the domain the policy changes; no rise anywhere else;
- the worst case may be at most 5% worse than the incumbent's;
- at least 100 cases per domain; seeds disjoint from the tuning corpus.

## Verdict: APPROVED

portwatch_robust approved on validation and test; it is the active policy.

Active policy: `portwatch_robust`.

## tuning corpus — REJECTED

| check | passed | evidence |
|---|---|---|
| no_more_violations | yes | VESSEL: 0 against 0; PORT: 16 against 16; CARGO: 31 against 31 |
| mean_regret_lower | yes | meanRegret: VESSEL: 0.16 against 5.72 (needs <= 5.15); PORT: 0.62 against 0.62 (must not rise); CARGO: 0.02 against 0.02 (must not rise) |
| p90_regret_lower | yes | p90Regret: VESSEL: 0.00 against 19.60 (needs <= 17.64); PORT: 1.60 against 1.60 (must not rise); CARGO: 0.00 against 0.00 (must not rise) |
| worst_case_not_worse | yes | VESSEL: worst 2.9 against 67.8 (+3.4 allowed); PORT: worst 7.0 against 7.0 (+0.4 allowed); CARGO: worst 0.5 against 0.5 (+0.0 allowed) |
| intervention_rate_reasonable | yes | VESSEL: intervenes 0% against 30%, unnecessary 0% against 75%, captures 0% of the 3 case(s) where an intervention was best (incumbent 100%); PORT: intervenes 80% against 80%, unnecessary 16% against 16%, captures 90% of the 29 case(s) where an intervention was best (incumbent 90%); CARGO: intervenes 25% against 25%, unnecessary 100% against 100%, captures 0% of the 0 case(s) where an intervention was best (incumbent 0%) |
| held_out | NO | seeds 1-40 against the tuning corpus's 1-40: overlapping; the result measures memorisation |
| sufficient_cases | NO | 40 declared cases in the smallest domain (100 required); refused by the engine: VESSEL 0, PORT 0, CARGO 0 (at most 10% allowed) |

## validation corpus — APPROVED

| check | passed | evidence |
|---|---|---|
| no_more_violations | yes | VESSEL: 0 against 0; PORT: 26 against 26; CARGO: 79 against 79 |
| mean_regret_lower | yes | meanRegret: VESSEL: 1.07 against 12.46 (needs <= 11.21); PORT: 1.30 against 1.30 (must not rise); CARGO: 0.01 against 0.01 (must not rise) |
| p90_regret_lower | yes | p90Regret: VESSEL: 0.00 against 36.90 (needs <= 33.21); PORT: 4.67 against 4.67 (must not rise); CARGO: 0.00 against 0.00 (must not rise) |
| worst_case_not_worse | yes | VESSEL: worst 80.1 against 80.1 (+4.0 allowed); PORT: worst 16.8 against 16.8 (+0.8 allowed); CARGO: worst 0.3 against 0.3 (+0.0 allowed) |
| intervention_rate_reasonable | yes | VESSEL: intervenes 0% against 44%, unnecessary 0% against 91%, captures 0% of the 5 case(s) where an intervention was best (incumbent 80%); PORT: intervenes 80% against 80%, unnecessary 30% against 30%, captures 85% of the 66 case(s) where an intervention was best (incumbent 85%); CARGO: intervenes 23% against 23%, unnecessary 100% against 100%, captures 0% of the 2 case(s) where an intervention was best (incumbent 0%) |
| held_out | yes | seeds 1001-1100 against the tuning corpus's 1-40: disjoint |
| sufficient_cases | yes | 100 declared cases in the smallest domain (100 required); refused by the engine: VESSEL 2, PORT 0, CARGO 0 (at most 10% allowed) |

## test corpus — APPROVED

| check | passed | evidence |
|---|---|---|
| no_more_violations | yes | VESSEL: 0 against 0; PORT: 45 against 45; CARGO: 158 against 158 |
| mean_regret_lower | yes | meanRegret: VESSEL: 1.05 against 12.14 (needs <= 10.93); PORT: 1.13 against 1.13 (must not rise); CARGO: 0.00 against 0.00 (must not rise) |
| p90_regret_lower | yes | p90Regret: VESSEL: 0.00 against 42.10 (needs <= 37.89); PORT: 3.88 against 3.88 (must not rise); CARGO: 0.00 against 0.00 (must not rise) |
| worst_case_not_worse | yes | VESSEL: worst 67.4 against 77.8 (+3.9 allowed); PORT: worst 16.9 against 16.9 (+0.8 allowed); CARGO: worst 0.2 against 0.2 (+0.0 allowed) |
| intervention_rate_reasonable | yes | VESSEL: intervenes 0% against 48%, unnecessary 0% against 93%, captures 0% of the 10 case(s) where an intervention was best (incumbent 70%); PORT: intervenes 79% against 79%, unnecessary 28% against 28%, captures 83% of the 135 case(s) where an intervention was best (incumbent 83%); CARGO: intervenes 32% against 32%, unnecessary 97% against 97%, captures 100% of the 2 case(s) where an intervention was best (incumbent 100%) |
| held_out | yes | seeds 5001-5200 against the tuning corpus's 1-40: disjoint |
| sufficient_cases | yes | 200 declared cases in the smallest domain (100 required); refused by the engine: VESSEL 0, PORT 0, CARGO 0 (at most 10% allowed) |

## What the gate does not decide

- It does not score WAIT against a second real observation: the benchmark has none, so a WAIT is scored by the stated model (the plan if the closure had ended by the re-evaluation instant, else the provisional option).
- It does not reward a hedge that loses on net. A policy that never intervenes on a corpus where no intervention pays is measured as correct on that corpus; the beneficial-intervention capture figure says how many paying interventions it declined, and the reader decides whether that is acceptable.
- The truth's backlog drain is drawn from a range the policy does not see; the policy's own drain is the mean of two recorded closures. The queue-model-agreement check inside the policy guards against a recommendation that rests on the drain assumption alone.
- PORT and CARGO are unchanged by the candidate; the gate checks them for regressions only.
