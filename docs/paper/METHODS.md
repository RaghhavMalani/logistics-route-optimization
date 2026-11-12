# Cargo risk methods

Reproduce the confirmatory run from the repository root with Python 3.12 and the versions in `requirements-paper.txt`.

```sh
python -m pip install -r requirements-paper.txt
python scripts/paper_experiments.py --all --seed 20261112
```

The command checks the committed preregistration, frozen decision code hashes and locked seed before evaluating the holdout. The manifest records the code SHA, environment, seed derivations, file hashes and timings. Numerical results use fixed seeds. Timing columns, render metadata across library versions, and the manifest's environment fields depend on the machine. The short `--smoke` run uses tuning cases and separate output.

## Loss

For delivery hour $A_{ij}$, deadline $d_i$, and nonnegative delay $D_{ij}=(A_{ij}-a_i^{\rm plan})_+$, use $(x)_+=\max(0,x)$. For option $j$ and cargo $i$,

$$
L_{ij} =
 C_i^{\rm late}(A_{ij}-d_i) +
 r_i^{\rm dem}\frac{(B_{ij}-b_i)_+}{24} +
 r_i^{\rm det}\frac{(T_{ij}-t_i)_+}{24} +
 V_i r_i^{\rm annual}\frac{D_{ij}}{8760} +
 V_i\,\mathbf 1\{U_{ij}>u_i\;\lor\; A_{ij}>s_i\} +
 V_i^{\rm ins}\left(r_i^{\rm policy}+\sum_{a\in\mathcal A_j}r_{ia}^{\rm war}\right)
 + C_{ij}^{\rm retention} + C_{ij}^{\rm GA}.
$$

A daily late penalty multiplies the positive excess hours by the daily rate divided by 24. A flat penalty charges once on a miss. $B$ and $T$ are separate dwell and detention clocks. $U$ is time without power and $s$ is remaining shelf life as of the decision. The gross spoilage indicator charges once if both conditions occur. Base and declared required war-risk premiums price insured value. An illustrative insured-value default is $V_i^{\rm ins}=1.10\,\mathrm{CIF}_i$ with an assumption label. The retention charges $\min(V_i^{\rm ins},\mathrm{deductible}_i)$ only on a separately declared covered event. General average requires a declaration of exposure, contribution and event probability, or an explicit declaration of no exposure for a structural zero. Route exclusions and missing FX are kept explicit.

We sum aligned option costs before computing voyage or Company tail metrics. Voyage-level fuel, fixed charges and declared time-cost proxies are added once. All priced terms are converted on the same future's dated FX quote where necessary. Missing values carry a reason. Comparison on a known subtotal requires identical included and excluded component sets across options. A probability of meeting a deadline is $\Pr(A_{ij}\le d_i)$ and is unavailable without a deadline.

For loss $L$ and confidence level $\alpha$, $\mathrm{CVaR}_\alpha(L)=\mathbb E[L\mid L\ge\mathrm{VaR}_\alpha(L)]$ for a continuous loss distribution. With an atom at VaR we include only the fraction needed to fill the upper tail, using

$$
\mathrm{CVaR}_\alpha(L)=\min_{t}\left[t+\frac{\mathbb E(L-t)_+}{1-\alpha}\right].
$$

We use $\alpha=.95$. [Rockafellar and Uryasev](https://sites.math.washington.edu/~rtr/papers/rtr187-CVaR2.pdf)

## Shared futures and stopping

Independent scrambled Sobol replicates use powers-of-two prefixes. All options use the same uniforms in each future. Normal inverse transforms and a Gaussian copula introduce the declared closure–port, weather–port, port–handling and fuel–FX dependence. The marginals are a lognormal/fizzle mixture for closure, discrete retained weather members or a labelled triangular weather fallback, piecewise interpolation of port quantiles or a fallback, the declared downstream delay, bounded uniform fuel and paired dated ECB FX. Historical receipts are eligible only if available at the decision time. [SciPy Sobol reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.qmc.Sobol.html)

With paired loss gap $G_r$ averaged inside replicate $r$, the estimated SE is $s(G_r)/\sqrt R$. The reported simulation intervals use a $t_{R-1}$ quantile. Adaptive sampling doubles each replicate until the ordered top two have remained unchanged across two tiers and the paired SE falls below the declared threshold. Exhaustion of the cap is reported separately. This precision criterion concerns the mean gap. CVaR and rare deadline misses can need more samples.

## Rules and test protocol

Let $j_0$ be keep, $\mu_j=\mathbb E[L_j]$, $p_j=\Pr(\exists i\in\mathrm{priority\ 1}:A_{ij}>d_i)$, and $R_j=\max_\omega[L_j(\omega)-\min_k L_k(\omega)]$ over the common sampled futures.

| Rule | Selection |
|---|---|
| R1 | Minimise $\mu_j$. |
| R2 | Minimise $\mu_j$ among options with $p_j\le\epsilon$. No feasible declared chance constraint yields no choice. |
| R3 | Minimise $\mathrm{CVaR}_{.95}(L_j)$. |
| R4 | Minimise $R_j$ on cost or substitute delivery time for $L_j$. |
| R5 | Among interventions with $\Pr(L_j<L_{j_0})\ge q$, no worse CVaR and the declared chance limit, minimise $\mu_j$. Otherwise keep. |

Waiting is an optional additional rule. It selects wait when the cross-fitted cost after a modelled binary reopening signal plus the cost of delay is below the expected immediate cost, subject to the latest valid start. The held-out rule comparison disables waiting unless the problem declares the required refresh and timing basis. Decisions remain research recommendations.

The existing seeded vessel generator and hidden closure truth are retained. Its USD outcomes use an explicitly illustrative USD 250 per delay hour. The cargo corpus has separate seeds, four cargo families, separate hidden latent truth, and a cargo-cost oracle. Cargo-blind and cargo-aware rules see the same available clocks and use the same sampled futures. Unscoreable cases remain in coverage denominators. Act-best capture requires a selected intervention that improves on keep in the realised scoring metric. Unnecessary intervention is conditional on a scoreable intervention. Zero regret means zero cost regret within $10^{-9}$ USD.

The tuning grid and selection rank are frozen in [the preregistration](../../paper/PREREGISTRATION.json). Validation checks the selected setting. Both validation and test must satisfy the coverage, vessel p90, act-best capture and paired cargo regret limits in [the decision-policy gate](../DECISION_POLICY_GATE.md). The existing vessel benchmark has published results. The cargo holdout is independently generated. No test results inform settings or thresholds.

For E1 we report per-policy summaries and paired differences on the intersection of scored cases. We draw 10,000 bootstrap samples of matched cases with replacement, report the percentile 95% interval, and compute two-sided paired Wilcoxon signed-rank tests with the Pratt zero convention. These p-values are descriptive and are not used to select or promote a rule. E4 applies the same resampling to realised cost differences for time-only versus R1. Decision time includes shared model setup and simulation for methods that require them.

## Figures and cases

E2 fixes the top two using a separate Sobol pilot on the synthetic Suez reefer case. It reports standard error across 16 independent replicates with independent PRNG, shared PRNG and shared Sobol worlds. The first stable tier is the second consecutive tier with a same-sign 95% interval excluding zero.

E3 changes each input multiplier from 0.5 to 1.5 one at a time around the nominal margin. Global indices use independent uniform multipliers on the same range. For independently sampled factor vectors $A,B$ and $A_B^{(i)}$ with column $i$ replaced, we use the Jansen estimators $S_i=1-\mathbb E[(f(B)-f(A_B^{(i)}))^2]/(2\operatorname{Var}f)$ and $S_{T_i}=\mathbb E[(f(A)-f(A_B^{(i)}))^2]/(2\operatorname{Var}f)$. The conditional response $f$ averages common inner futures. Outer replicate intervals quantify integration uncertainty conditional on those inner futures. Negative first-order estimates can occur from finite sampling. [SciPy sensitivity index reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.sobol_indices.html)

E5 uses the frozen S10 hourly fixture and existing passage gate and fuel calculation, two synthetic Suez cargo mixes, and the Ever Given mission timeline with illustrative cargo and routes. The observed reopening appears only in a separate conditional calculation. Break-even reports the bracket between two conditional closure grid points that change R1's choice. A case can have multiple flips or none in the evaluated range. [Ever Given mission source](https://boskalis.com/press/press-releases-and-company-news/suez-canal-unblocked-we-pulled-it-off)
