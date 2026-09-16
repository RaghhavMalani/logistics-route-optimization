# Robust decisions

The decision engine's recommendation policy for vessel routing, as of the
release candidate: an intervention is recommended only when it survives not
knowing how long the disruption will last. Code: `src/portwatch_os/decision/robust.py`
(the policy), `outcome.py` (the closure outcome model), `promotion.py` (the gate
that decided whether this policy ships). Numbers: `DECISION_BENCHMARK.md` and
`DECISION_POLICY_GATE.md`.

## 1. The weakness it fixes

The first decision benchmark (40 seeded vessel cases) put the expected-value
policy's mean regret at 5.72 h against 0.16 h for simply continuing the plan.
On twelve cases the engine recommended a slow-steam hold to arrive after the
claim horizon; the hold beat proceeding on three and lost on nine, two of them
claims that never materialised. The BALANCED ranking weighted residual risk at
35% and ETA at 25%, and a hold zeroes residual risk by construction -- so it paid
certain hours for an exposure that mostly did not happen. The structural
error: the ranking asked "which option scores best if the claim is exactly
right?", and a closure claim never says how long the closure lasts.

Nothing in the fix is tuned to those twelve cases. The tuning corpus was read
while the policy was designed; a disjoint validation corpus checked it; a
disjoint test corpus, untouched until the final run, decided the promotion.

## 2. One outcome model

`decision/outcome.py` holds the closure outcome model, extracted from the
mission scorecard so that the policy evaluates options with exactly the physics
the product later scores them with:

- a hull reaching the closed water waits for the reopening, then queues in
  arrival order through a backlog drained linearly to the clearance bound;
- a hull arriving after the reopening but before the backlog clears waits the
  remaining share of the drain;
- a diversion takes its certain detour; a change of destination takes the
  passage difference, with onward carriage not modelled and said so.

The one figure a claim does not state is the backlog drain. It is taken from
the two closures the product records with sources -- Ever Given 2021 (drain
0.82 × closure) and Cyclone Biparjoy at Kandla 2023 (0.61) -- as the mean, and
labelled a stated assumption. Every recommendation is also evaluated with no
queue at all; one that rests on the queue assumption alone fails the gate
(`queue_model_agreement`).

## 3. Four stress horizons, no invented distribution

No calibrated duration distribution exists for a chokepoint claim (the Global
Eye calibrator calibrates whether a claim materialises, not for how long). So
none is invented and none is weighted. Every candidate option is evaluated
under four labelled horizons, multiples of the remaining claim horizon:

| horizon | the closure |
|---|---|
| FIZZLE | does not materialise: the water is open on arrival, no backlog |
| SHORT | ends halfway to the claim horizon |
| BASE | ends at the claim horizon, as claimed |
| LONG | persists to twice the claim horizon |

For each horizon and option: realised delay, regret against the best option
under that horizon, and the arithmetic. Per option: worst-case regret and the
horizon it occurs in, unweighted mean regret (labelled as unweighted), horizons
won (regret within the noise tolerance of the best), advantage over the current
plan per horizon, robustness margin (the plan's worst-case regret minus the
option's), reversibility, and the break-even.

The noise tolerance is half an hour: the route geometry is non-navigational and
hull timings are declared to a tenth of an hour. It is the minimax margin, the
win tolerance and the break-even tolerance alike, so there is one figure to
disagree with.

## 4. Three picks

Alongside the expected-value frontier and the BALANCED ranking, which are kept
unchanged, the assessment publishes three picks the operator can compare:

- **EXPECTED_BEST** -- the BALANCED ranking's pick (the incumbent policy);
- **ROBUST_BEST** -- the option that wins the most horizons, ties to the lower
  worst case, then to the current plan;
- **LOWEST_WORST_CASE_REGRET** -- the minimax pick.

## 5. The gate

The recommendation starts from the minimax pick with the current plan as a
first-class candidate. An intervention displaces the plan only if it clears
every blocking check:

| check | blocking | passes when |
|---|---|---|
| `worst_case_regret` | yes | its worst-case regret is below the plan's by more than the tolerance |
| `scenario_wins` | yes | it wins at least as many horizons as the plan |
| `queue_model_agreement` | yes | the margin survives with no queue at all |
| `claim_as_stated` | for irreversible moves | its regret under BASE is within tolerance: the claim as stated justifies it, not the tail alone |
| `passage_weather` | advisory | a re-routed passage was weather-checked |
| `eta_certain` | advisory | its delay is certain, not an expected value |
| `claim_calibrated` | advisory | the claim's probability is calibrated |

Dominance on the expected frontier does not withdraw an option from candidacy
here: it rests on the expected figures, which assume the claim's duration. If
the robust pick is dominated in expectation, the Critic's `not_dominated` check
is a warning that says so rather than a block, and acceptance claim 5 requires
the robust reason on the recommendation.

## 6. Three answers

- **ACT** -- the intervention clears the gate. Named, with its worst-case regret
  against the plan's, the horizons it wins and its break-even.
- **KEEP_CURRENT_PLAN** -- no intervention clears the gate and either nothing
  wins any horizon or the window closes before the next observation. Stated
  with the contender's break-even ("beats the current plan only if the closure
  persists beyond 31 h from now"), the duration confidence (`LOW / UNCALIBRATED`,
  or `ASSUMED` for an operator's assumed closure) and how many horizons the
  plan wins.
- **WAIT_FOR_MORE_INFORMATION** -- do nothing yet. Given when which option is
  best depends on the horizon, knowing the duration is worth more than the
  tolerance (upper bound: the plan's worst-case regret), and the contender's
  branch point is later than the next event-register refresh (the freshness
  policy's 6 h SLA) with the minimum window to spare. The answer names the
  re-evaluation instant and the branch point. When an intervention has cleared
  the gate but is reversible only until its branch point, the answer is also
  WAIT, with the intervention named as provisional: take it if the claim still
  stands at re-evaluation. A highly reversible intervention (a speed change)
  that clears the gate is ACT.

## 7. Reversibility

Each option carries a class: `OPEN` (the plan; every other option stays
available until its own branch point), `HIGH` (a speed change, restored at any
time), `UNTIL_BRANCH` (a diversion, reversible until the branch point, then
committed), `PARTIAL` (a destination change; onward carriage unmodelled),
`IRREVERSIBLE`. It decides whether `claim_as_stated` blocks and whether a
cleared intervention is deferred to WAIT. No score is built from it.

## 8. Break-even

On a one-hour grid of closure lengths from "reopens now" to three times the
remaining claim horizon (at least a day), each intervention is compared with
the plan under the outcome model. The panel states the first hour it wins and,
where the winning band closes, the last: "beats the current plan only if the
closure persists beyond 45 h from now and ends before 58 h". A hold to the
claim horizon usually has a narrow band: arriving just after the claim lapses
lands the hull at the back of the queue the closure formed. That is the finding
the benchmark made, now visible to the operator on every decision.

## 9. What it does not do

- It does not weight the horizons. Where a calibrated duration distribution
  exists one day, expected regret can be computed from the same table; the
  policy will still publish the unweighted figures beside it.
- It does not model persistence past 2× the claim horizon. A claim that
  understates a closure fivefold (validation case 1027: a 72 h claim, a 395 h
  closure) is outside the stress set; the operational answer is the WAIT
  loop, re-evaluating as the register extends the claim, which the one-shot
  benchmark cannot score.
- It changes only vessel routing. Port and cargo decisions carry no
  duration-uncertainty model; there the expected-value ranking decides, the
  recommendation is `ACT` or `KEEP_CURRENT_PLAN` by whether the ranking's pick
  is the baseline, and `robustness.applicable` is false and says why.
- It does not redesign the hold. The slow-steam option is still "hold until
  the claim lapses plus a margin"; the policy shows when that pays and mostly
  declines it. A shorter hold that arrives after the backlog clears in the
  SHORT horizon would be a new option, not a policy change, and is not in this
  release.

## 10. Where the incumbent still lives

`DecisionEngine(policy="balanced-v1")` runs the expected-value policy unchanged;
the benchmark scores it as `portwatch_balanced` on every corpus, and the
engine's default (`ACTIVE_POLICY`) is whatever `DECISION_POLICY_GATE.md` says.
`tests/test_robust_decisions.py` asserts the two agree.
