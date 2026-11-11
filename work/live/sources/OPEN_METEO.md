# Open-Meteo marine and ensemble

Reviewed 11 Nov 2026 against the retained evidence from the 48-hour window in [Source trials](README.md). The collectors checked all 13 registered ports on a six-hour cadence with bounded retries. The catalogue records the free-service noncommercial restriction and CC BY 4.0 attribution.

| Product | Successful checks | Latest port coverage | Last successful check (UTC) | Decision |
| --- | ---: | --- | --- | --- |
| Extended marine | 8/12 | 12/13 for each of waves, swell, current velocity and current direction. INCCU had no qualifying response. | 8 Nov 12:38:09 | Adopt modelled context for covered ports. |
| Wind ensemble | 8/8 | 13/13 with finite values across 40 wind series per port. The first qualifying snapshot covered 72 hourly values per series. | 8 Nov 12:06:06 | Adopt the modelled wind member range for context. |

Marine's first four attempts failed under the initial all-fields qualification rule. The collector was corrected to preserve individual nulls alongside usable fields. Its first success came at 6 Nov 18:37:15 UTC. Coverage above describes the latest qualifying sample. The aggregate does not establish continuous coverage at each port.

Both APIs omit model issue time in these responses. Issuance lag is unmeasured. The preview checks response age against nine hours and requires the actual current UTC hour to be covered by finite forecast values. It shows port coverage and modelled readings with their valid times and units. Missing values stay unavailable, including null currents. This extends the independent existing surface and basic marine feed. The wind range describes spread across returned series. No comparison scores or decision-policy inputs use it.

Publication is opt-in for the noncommercial preview. The worker collects new published snapshots in a separate scope. Private trial readings remain private.
