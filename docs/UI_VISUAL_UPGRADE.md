# Local interface and commercial review upgrade

Continuation of `cc8c265` on `feat/portwatch-restored-intelligence`. Hosting is
deferred. This document describes the local implementation, not the public build.

## Interface

The restored four-role application, chart renderer, Cesium globe, timeline,
digital twin and advisory state machine remain in place. Existing uncommitted
shell, typography and panel work was integrated into shared `operations.css`
rules rather than replaced with a new application.

- The Company rail has a searchable, filtered fleet worklist with one selected
  detail. Counts retain their server-defined scope; paging does not rerank cases.
- Sources, Learning, Scenarios and Globe share a docked inspector. Expand is an
  explicit action. Heavy evidence disclosures mount on first inspection.
- Passage comparison leads with current/alternative choices, conditional timing,
  waiting, signed schedule shift, fuel and cargo. Continue remains accessible.
- Port and Vessel cards separate lifecycle, permitted actions and retained audit
  details. Only existing authorized transitions are offered.
- Admin shows source products and recorded states instead of an unexplained
  readiness percentage. The world clock is labelled independently of data age.
- Layers and Timeline use the existing narrow-screen panel switcher. Focus,
  Escape/Close, reduced motion, bounded scrolling and basemap attribution remain
  part of acceptance, not decorative changes.

## Private commercial sidecar

Company's **Business** tab belongs to an exact frozen declared-passage comparison.
It provides Cargo, Business impact, Insurance review and Uncertainty views.
Loading any of the thirteen example declarations is explicit and labelled
fictional. An editable JSON disclosure preserves the complete typed basis.

`commercial-components-v1` uses decimal amounts and explicit currencies, parties,
payers, beneficiaries, future accounting scope and multiple consignments. Cargo
events have named deadlines and declared downstream offsets. Ship fuel is charged
once; invoice, replacement and insured values remain distinct. Missing components
withhold a supported total-cost winner. Required cargo, physical and insurance
review constraints cannot be exchanged for a cheaper result. Resource allocation
checks aggregate simultaneous claims over half-open intervals.

Insurance is contract-evidence screening, not adjudication or a broker quote.
Unknown clauses, listed-area geometry, expiry or missing evidence require review.
A dated JWC notice alone establishes neither closure nor premium nor recovery.
Public trade totals establish neither a buyer nor a shipment's selling price.

Studies are immutable Company-private ledger records. Retrying identical inputs
returns the retained study. A deliberate successor freezes the selected study's
version and hashes, creates a new comparison requiring review and preserves the
prior comparison. Port and Vessel receive only the minimal operational binding;
policies, parties, invoices and simulation assumptions stay private. Approval and
handoff recheck the current commercial version and applicable evidence.

## Reproducible uncertainty

`commercial-mc-shadow-v1` samples **additional downstream handling delay** only.
Discrete declared weights or a bounded triangular assumption generate a shared
world for every option and consignment. The recorded seed, generator version,
configuration hash and sample hash make the result reproducible. This version
does not vary hourly approach weather, route geometry, FX or dependencies that
have not been implemented.

The UI reports supported mean, quantiles, empirical CVaR, paired deltas, conditional
constraint-failure frequency, numerical mean standard error, half/full drift and
fixed-point sensitivity. Tail preference is an operator assumption. Draws are
simulation samples, not independent voyages or calibrated event probabilities.
Empirical mode remains collecting without a suitable cohort. The incumbent policy
and rejected neural/RL artifacts are retained; no policy is adopted by this study.

## Local reproduction and evidence

1. Set the repository and Python dependencies on `PYTHONPATH`. Run
   `python scripts/run_local_provider_backend.py` for loopback port 8820. State is
   isolated under ignored `work/ui-visual-upgrade-20261101/provider-state`.
2. Build the existing frontend with `VITE_PORTWATCH_API_BASE` set to
   `http://127.0.0.1:8820/api`, production auth and Nitro's node-server preset.
   Serve its compiled output on loopback port 4220. Use normal one-click demos;
   no injected identity or replacement login is needed.
3. Choose **Use current provider data** for a genuine retained forecast plus an
   explicitly fictional voyage declaration. Scenario fixtures are a separate
   choice. Source reads do not fetch or silently fall back to fixtures.
4. Inspect Business, calculate a study, optionally create a successor, and use
   the existing Company → Port → Vessel journey. Outcomes remain simulated.

Full-size paired captures, validation logs, a comparison board and the new local
recording live under ignored `work/ui-visual-upgrade-20261101`. The prior 7:25
recording is preserved. Matched presentation captures use the same normal QA
visitor, frozen API payloads and camera; their fixed display clock and any
synthetic worklist are labelled. Independent live-profile checks use real time
and no response substitution. See `UI_AND_FREE_PROVIDER_COVERAGE.md` for source
boundaries and `UI_UPGRADE_VALIDATION.md` for the final run evidence.
