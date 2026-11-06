# Frankfurter ECB FX — private trial in progress

The catalogue records Frankfurter's upstream terms and ECB attributed reuse conditions. Trial collection is the unmodified ECB EUR/INR and EUR/USD daily reference observations, retaining their original dates. First successful collection: 6 Nov 18:05:12 UTC. Fixed window and report command are in README.md; cadence is daily, with bounded retries/backoff.

Coverage and lag must be measured over the full window, with weekends/closed reference dates explicit. An INR/USD cross would be a derived value, not FRED DEXINUS; the feed does not replace Brent. No wholesale macro-series replacement or decision-policy change is made before trial review. Decision: pending actual 48-hour measurements; not adopted yet.
