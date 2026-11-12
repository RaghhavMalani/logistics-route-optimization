# Cargo risk study results

The vessel corpus uses a synthetic USD 250/h proxy. The cargo corpus prices fictional terms. Intervals on policy differences use paired case bootstrap resampling and describe this case-generating design. See [methods](METHODS.md) and [threats to validity](THREATS.md).

## E1 · Held-out policy comparison

| Corpus | Policy | Scored | Mean regret (h) | P90 regret (h) | Mean cost regret (USD) | Δ mean USD vs incumbent [95% CI] | Act-best captures |
|---|---|---:|---:|---:|---:|---:|---:|
| vessel | current_plan | 190/200 | 1.05 | 0.00 | 262.11 | 0.00 [0.00, 0.00] [Δ](../../paper/tables/e1-paired.csv#L6) | 0/10 [E1](../../paper/tables/e1-policy.csv#L2) |
| vessel | heuristic | 190/200 | 70.43 | 365.45 | 17608.29 | 17346.18 [12335.22, 22795.00] [Δ](../../paper/tables/e1-paired.csv#L19) | 6/10 [E1](../../paper/tables/e1-policy.csv#L3) |
| vessel | portwatch_balanced | 190/200 | 12.14 | 42.18 | 3034.47 | 2772.37 [2176.31, 3407.25] [Δ](../../paper/tables/e1-paired.csv#L32) | 7/10 [E1](../../paper/tables/e1-policy.csv#L4) |
| vessel | portwatch_robust | 190/200 | 1.05 | 0.00 | 262.11 | 0.00 [0.00, 0.00] [Δ](../../paper/tables/e1-paired.csv#L45) | 0/10 [E1](../../paper/tables/e1-policy.csv#L5) |
| vessel | R1 | 190/200 | 1.05 | 0.00 | 262.11 | 0.00 [0.00, 0.00] [Δ](../../paper/tables/e1-paired.csv#L58) | 0/10 [E1](../../paper/tables/e1-policy.csv#L6) |
| vessel | R2 | 190/200 | 1.05 | 0.00 | 262.11 | 0.00 [0.00, 0.00] [Δ](../../paper/tables/e1-paired.csv#L71) | 0/10 [E1](../../paper/tables/e1-policy.csv#L7) |
| vessel | R3 | 190/200 | 30.28 | 158.05 | 7569.74 | 7307.63 [4423.37, 10472.63] [Δ](../../paper/tables/e1-paired.csv#L84) | 3/10 [E1](../../paper/tables/e1-policy.csv#L8) |
| vessel | R4 | 190/200 | 22.17 | 77.17 | 5541.71 | 5279.61 [2976.39, 7887.39] [Δ](../../paper/tables/e1-paired.csv#L97) | 3/10 [E1](../../paper/tables/e1-policy.csv#L9) |
| vessel | R5 | 190/200 | 1.05 | 0.00 | 262.11 | 0.00 [0.00, 0.00] [Δ](../../paper/tables/e1-paired.csv#L110) | 0/10 [E1](../../paper/tables/e1-policy.csv#L10) |
| vessel | time_only | 190/200 | 1.05 | 0.00 | 262.11 | 0.00 [0.00, 0.00] [Δ](../../paper/tables/e1-paired.csv#L123) | 0/10 [E1](../../paper/tables/e1-policy.csv#L11) |
| cargo | current_plan | 182/200 | 0.44 | 0.00 | 9602.75 | 0.00 [0.00, 0.00] [Δ](../../paper/tables/e1-paired.csv#L136) | 0/42 [E1](../../paper/tables/e1-policy.csv#L12) |
| cargo | heuristic | 182/200 | 79.26 | 403.38 | 56180.64 | 46577.89 [20930.73, 77354.09] [Δ](../../paper/tables/e1-paired.csv#L149) | 12/42 [E1](../../paper/tables/e1-policy.csv#L13) |
| cargo | portwatch_balanced | 182/200 | 10.04 | 35.10 | 13015.03 | 3412.28 [2016.47, 5019.63] [Δ](../../paper/tables/e1-paired.csv#L162) | 0/42 [E1](../../paper/tables/e1-policy.csv#L14) |
| cargo | portwatch_robust | 182/200 | 0.44 | 0.00 | 9602.75 | 0.00 [0.00, 0.00] [Δ](../../paper/tables/e1-paired.csv#L175) | 0/42 [E1](../../paper/tables/e1-policy.csv#L15) |
| cargo | R1 | 182/200 | 71.19 | 322.21 | 482.09 | -9120.66 [-12046.80, -6365.86] [Δ](../../paper/tables/e1-paired.csv#L188) | 41/42 [E1](../../paper/tables/e1-policy.csv#L16) |
| cargo | R2 | 111/200 | 116.03 | 376.05 | 0.00 | -14954.59 [-19445.29, -10731.88] [Δ](../../paper/tables/e1-paired.csv#L201) | 41/42 [E1](../../paper/tables/e1-policy.csv#L17) |
| cargo | R3 | 182/200 | 83.32 | 349.04 | 18783.14 | 9180.39 [-4000.93, 24776.77] [Δ](../../paper/tables/e1-paired.csv#L214) | 41/42 [E1](../../paper/tables/e1-policy.csv#L18) |
| cargo | R4 | 182/200 | 87.99 | 349.04 | 26656.79 | 17054.05 [1159.84, 35696.88] [Δ](../../paper/tables/e1-paired.csv#L227) | 42/42 [E1](../../paper/tables/e1-policy.csv#L19) |
| cargo | R5 | 182/200 | 71.19 | 322.21 | 482.09 | -9120.66 [-12046.80, -6365.86] [Δ](../../paper/tables/e1-paired.csv#L240) | 41/42 [E1](../../paper/tables/e1-policy.csv#L20) |
| cargo | time_only | 182/200 | 0.44 | 0.00 | 9602.75 | 0.00 [0.00, 0.00] [Δ](../../paper/tables/e1-paired.csv#L253) | 0/42 [E1](../../paper/tables/e1-policy.csv#L21) |

The [E1 summary](../../paper/tables/e1-policy.csv), [paired intervals](../../paper/tables/e1-paired.csv) and [signed-rank results](../../paper/tables/e1-signed-rank.csv) include the remaining metrics.

### Preregistered R5 decision

**Do not promote** under the committed gate.

- validation · vesselCoverage · 0.9 >= 0.9 · pass. [CSV row](../../paper/tables/r5-promotion.csv#L2)
- validation · cargoCoverage · 0.94 >= 0.9 · pass. [CSV row](../../paper/tables/r5-promotion.csv#L3)
- validation · vesselCapture · 0 >= 0.5 · fail. [CSV row](../../paper/tables/r5-promotion.csv#L4)
- validation · vesselP90Hours · 0 <= 1 · pass. [CSV row](../../paper/tables/r5-promotion.csv#L5)
- validation · pairedCargoP90CostUsd · 0 <= 4.793e+04 · pass. [CSV row](../../paper/tables/r5-promotion.csv#L6)
- test · vesselCoverage · 0.95 >= 0.9 · pass. [CSV row](../../paper/tables/r5-promotion.csv#L7)
- test · cargoCoverage · 0.91 >= 0.9 · pass. [CSV row](../../paper/tables/r5-promotion.csv#L8)
- test · vesselCapture · 0 >= 0.5 · fail. [CSV row](../../paper/tables/r5-promotion.csv#L9)
- test · vesselP90Hours · 0 <= 1 · pass. [CSV row](../../paper/tables/r5-promotion.csv#L10)
- test · pairedCargoP90CostUsd · 0 <= 4.661e+04 · pass. [CSV row](../../paper/tables/r5-promotion.csv#L11)

## E2 · Variance reduction

[Log–log plot](../../paper/figures/e2-variance.pdf) · [SE and intervals](../../paper/tables/e2-variance.csv)

- Independent PRNG · 4096 futures per option. [CSV row](../../paper/tables/e2-stable-rank.csv#L2)
- CRN PRNG · 512 futures per option. [CSV row](../../paper/tables/e2-stable-rank.csv#L3)
- CRN scrambled Sobol · 512 futures per option. [CSV row](../../paper/tables/e2-stable-rank.csv#L4)

## E3 · Sensitivity

[Tornado](../../paper/figures/e3-tornado.pdf) · [endpoints](../../paper/tables/e3-tornado.csv) · [Sobol indices and intervals](../../paper/tables/e3-sobol.csv) · [index plot](../../paper/figures/e3-sobol.pdf)

## E4 · Cargo-blind comparison

- timeOnlyCostsMoreFraction · 0.2253, 95% CI [0.1648, 0.2912], 182 paired cases. [CSV row](../../paper/tables/e4-cargo-blind.csv#L2)
- meanExtraUsdAllPairs · 9121, 95% CI [6389, 1.204e+04], 182 paired cases. [CSV row](../../paper/tables/e4-cargo-blind.csv#L3)
- meanExtraUsdWhenMore · 4.049e+04, 95% CI [3.384e+04, 4.706e+04], 182 paired cases. [CSV row](../../paper/tables/e4-cargo-blind.csv#L4)

## E5 · Case studies

- s10-meridian · 10 kn has the lowest expected cost (similar median arrival versus keep · complete declared cost). [CSV row](../../paper/tables/e5-cases.csv#L3) [Arrival fan](../../paper/figures/e5-s10-meridian-arrival.pdf) · [Cost distribution](../../paper/figures/e5-s10-meridian-cost.pdf)
- suez-reefer · Keep via Suez has the lowest expected cost (similar median arrival versus keep · complete declared cost). [CSV row](../../paper/tables/e5-cases.csv#L4) [Arrival fan](../../paper/figures/e5-suez-reefer-arrival.pdf) · [Cost distribution](../../paper/figures/e5-suez-reefer-cost.pdf)
- suez-time-critical · Keep via Suez has the lowest expected cost (similar median arrival versus keep · complete declared cost). [CSV row](../../paper/tables/e5-cases.csv#L7) [Arrival fan](../../paper/figures/e5-suez-time-critical-arrival.pdf) · [Cost distribution](../../paper/figures/e5-suez-time-critical-cost.pdf)
- ever-given · Keep via Suez has the lowest expected cost (similar median arrival versus keep · complete declared cost). [CSV row](../../paper/tables/e5-cases.csv#L10) [Arrival fan](../../paper/figures/e5-ever-given-arrival.pdf) · [Cost distribution](../../paper/figures/e5-ever-given-cost.pdf)

The recorded Ever Given reopening is scored separately in the [conditional replay table](../../paper/tables/e5-historical-conditional.csv).

- s10-meridian · no flip from 0 to 48 h. [CSV row](../../paper/tables/e3-break-even.csv#L2)
- suez-reefer · 40.50–54.00 h. [CSV row](../../paper/tables/e3-break-even.csv#L3)
- suez-reefer · 81.00–94.50 h. [CSV row](../../paper/tables/e3-break-even.csv#L4)
- suez-reefer · 121.50–135.00 h. [CSV row](../../paper/tables/e3-break-even.csv#L5)
- suez-reefer · 175.50–189.00 h. [CSV row](../../paper/tables/e3-break-even.csv#L6)
- suez-time-critical · 40.50–54.00 h. [CSV row](../../paper/tables/e3-break-even.csv#L7)
- suez-time-critical · 229.50–243.00 h. [CSV row](../../paper/tables/e3-break-even.csv#L8)
- ever-given · 54.00–67.50 h. [CSV row](../../paper/tables/e3-break-even.csv#L9)
- ever-given · 81.00–94.50 h. [CSV row](../../paper/tables/e3-break-even.csv#L10)
- ever-given · 94.50–108.00 h. [CSV row](../../paper/tables/e3-break-even.csv#L11)
- ever-given · 148.50–162.00 h. [CSV row](../../paper/tables/e3-break-even.csv#L12)

[All rule choices](../../paper/tables/e5-rule-choices.csv) · [Excluded cost components](../../paper/tables/e5-unknown-costs.csv)

## Runtime

- 0.083 s · 3 options × 12 consignments · 16384 futures · maximum N at USD 213.26 SE. [CSV row](../../paper/tables/runtime.csv#L2)
- 0.081 s · 3 options × 12 consignments · 16384 futures · maximum N at USD 267.16 SE. [CSV row](../../paper/tables/runtime.csv#L3)
- 0.083 s · 3 options × 12 consignments · 16384 futures · maximum N at USD 183.15 SE. [CSV row](../../paper/tables/runtime.csv#L4)
