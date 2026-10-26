# Economic and news feedback reconciliation

October 26, 2026. Bounded local integration from `caba5893a97eb32de18b31e424f107bcc9d0a3c5`, on `feat/portwatch-restored-intelligence`. The restored role screens and twin remain unchanged. This milestone extends the existing ledger, six-hour reconciliation worker, Outcome Agent, feedback disclosures and visitor review tasks. Production publication is excluded.

## Audited public state

The initial read-only audit at **2026-10-25T09:30:00.387422Z** examined unscoped public feedback only. The canonical `outputs/portwatch_ledger.db` held 33 DEXINUS observation vintages/dates, nine prospective targets/vintages, three legacy stored matches and two missing-date records. Its last run started October 24 at 17:43:11Z; last retained receipt was 17:43:12Z. Under the earlier qualification policy, news had three event families/targets, two report documents/revisions, one ambiguous-period claim and seven stored unresolved assessments. Those historical classifications are retained, not treated as new verified evidence.

A separate older public store under `work/operational-pilot-20261017/local-state` held 30 observation dates, five FX targets, no matches and nine unresolved news targets. Its counts were not merged with the canonical store. Private visitor namespaces were neither enumerated nor copied into either audit.

The live API audit at **2026-10-26T00:17:19.496074Z** (05:47:19 IST) reports:

| Public dataset quantity | Count / interpretation |
| --- | --- |
| Retained FX observation vintages / independent dates | 33 / 33 |
| Prospective FX targets / forecast vintages | 10 / 10 |
| Qualified independent matches | 3, all one-calendar-day persistence forecasts |
| Unresolved FX targets | 7: October 19–23, 26 and 27; no matching later retained release |
| Excluded / revised FX targets | 0 / 0 in this snapshot |
| History-only observation dates | 30; these are not retrospectively manufactured forecasts |
| News event families / exact targets | 9 / 9 under the existing identity policy |
| News report documents / revisions / origin lineages | 3 / 3 / 3 |
| Qualified resolved / pending news targets | 0 / 0; nine exact targets lack a qualified predicate and are excluded |
| Excluded news groups / ambiguous-period claims | 10 / 1; excluded groups include ambiguous identities, so counts overlap |

An independent public-table check at **2026-10-26T00:21:29.864951Z** found 29 total retained claims, 36 evidence rows (33 FX observations and three primary announcement records), three preserved matches and three additive economic qualification records. Public actual operational records, public simulated-operation records and public context dispositions were each zero in this unscoped store. **Visitor-specific simulations and dispositions were not enumerated; those public zeros are not system-wide totals.** Source corroboration, reference-rate errors and demo approvals add zero actual shipping outcomes.

The existing worker fetched DEXINUS successfully at 00:14:25Z on October 26. Its response contained 25 observation rows in the requested recent range; unchanged rows did not increase the 33 retained observations. Latest observation date remained October 16, ten calendar days old. A new October 27 forecast was frozen prospectively. Observation age, last check, last successful fetch and first original receipt are separate clocks. The nominal October 26 release window had not arrived at this audit; eligibility never guarantees availability. USCG discovery was current with 389 features, of which one had supported operational extraction; this is not 389 validated event predictions.

## DEXINUS matching and errors

[FRED's series metadata](https://fred.stlouisfed.org/series/DEXINUS) and the [Federal Reserve H.10 methodology](https://www.federalreserve.gov/releases/h10/about.htm) identify INR per USD, New York noon buying rates, daily observations in a weekly release. The [October 19 release](https://www.federalreserve.gov/releases/h10/current/default.htm), inspected during validation, supplied October 13–16 values and an unavailable October 12 observation. Provider release instants remain unknown for retained CSV responses. The derived Monday 16:15 America/New_York check window accounts for federal holidays; it is not relabelled as an actual publication or measurement time.

`DEXINUS_FIRST_RETAINED_COMPATIBLE_DATE_OUTCOME_V2` requires matching series, currency direction, unit, statistic, product, scope and date. Forecast issue and first availability must precede the target observation date; all frozen inputs must have been available then. Originals must match their SHA-256, source receipt and original CSV row. Date-only values acquire no artificial intraday precision. Entire malformed responses fail before partial observation ingestion. Missing rows are retained separately and never become zero, an interpolated value or a carried-forward outcome.

The existing `persistence-v1` policy is unchanged. Independence uses `EARLIEST_PROSPECTIVE_FORECAST_PER_SERIES_DATE_V1`; repeated snapshots, representations and retries do not multiply targets. First-retained outcome scoring remains identifiable. Later revisions/reversions are preserved separately and exclude the affected target from reliability fitting without silently replacing its stored error. Conflicting first outcomes remain excluded. Legacy scores remain auditable; a new qualification record becomes visible only when the stronger checks actually ran.

| Target observation date | Frozen forecast | Input quote date / age at issue | First retained observation | Signed error | Absolute error |
| --- | --- | --- | --- | --- | --- |
| 2026-10-14 | 96.31 | October 2 / 11 days | 95.15 | −1.16 | 1.16 |
| 2026-10-15 | 96.73 | October 9 / 5 days | 95.06 | −1.67 | 1.67 |
| 2026-10-16 | 96.73 | October 9 / 6 days | 94.96 | −1.77 | 1.77 |

Values and errors are **INR/USD**. Error convention is **observed minus predicted**. These three forecasts overpredicted the subsequent reference rate: bias −1.5333, MAE 1.5333, target span October 14–16. Three targets cannot establish a reliable correction or improvement over the persistence baseline itself. All contexts remain `COLLECTING`, weight 1, correction unavailable. The first retained outcomes arrived October 20 at 01:30:20Z; stronger legacy qualification became available October 26 at 00:14:38Z. Earlier as-of views cannot see that later qualification.

## News scope and genuine provider attempt

The single new bounded adapter is documented in [REVIEWED_NEWS_FAMILY.md](REVIEWED_NEWS_FAMILY.md). It can verify that a specific authority **announced** a closure for an exact location/calendar period. GAC's attributed report and Peel Ports' primary notice share the same originating lineage: separate documents do not count as independent reporting confirmations. The narrow primary-document exception verifies attribution, not actual closure, vessel execution or shipping benefit.

The direct GAC request returned HTTP 403 in the initial attempt and again during the live worker run. Indexed text was not substituted for retained original response bytes. The official MNTM 2026-18 PDF was retained successfully (204,725 bytes; SHA-256 `04a5847e17eae7787aa2feecd017039e6ab3020f9070d314319f15d5ec63e332`). Three primary announcement interpretations became available at interpretation time. **There is no genuinely resolved GAC/authority pair yet because the secondary original is unavailable.** Fixture transitions demonstrate the implemented path and remain labelled synthetic.

Legacy targets without an explicit qualified predicate, unknown reporting periods, conflicting revisions, self-reference and missing/corrupt originals remain unresolved or excluded. Original bodies/IDs are preserved. A later explicit cancellation can change applicability while the earlier announcement remains accurately corroborated. Disappearance is not cancellation. Different cumulative periods cannot settle one another. No probabilistic news forecast score is generated for a reported fact without a frozen probability.

Full GAC response redistribution remains unqualified. The application retains local research originals, attribution, a short excerpt, source links and hashes; download access cannot bypass that restriction, including when parsing produced no claim. Public original downloads require a retained public record binding and a matching hash. Collector-controlled receipt paths support configured public archive roots without accepting a caller-supplied filesystem selector.

## Existing UI and connected review

The compact shared feedback disclosure remains inside Global Eye's existing Global intelligence panel. It adds category/as-of filtering, paging, selected-case summaries, original/hash inspection and a complete filtered or selected-claim JSON audit. Selection and owned-voyage context survive paging. Economic cases display input quote age, issue, target, outcome or specific pending reason, signed/absolute error, qualification time and revisions. News cases show exact predicate, period, assessment, applicability, decisive evidence and exclusions. Hashes and detailed records stay behind disclosures. No additional expanded evidence block precedes passage controls.

Public inspection and audit GETs neither fetch providers nor create forecasts or reliability records. Summary counts use the full declared as-of dataset rather than the 100-claim response page. Audits include selection policies, outcomes, receipts and metrics; internal archive paths and visitor tasks are excluded. Completed collector results become visible at completion/availability, not at run start; legacy runs use conservative retained check/receipt clocks.

New claim-linked review tasks freeze the **current as-of assessment**, even if the worker has not yet persisted an assessment. `assessmentBasis=CURRENT_AS_OF_PROJECTION_V1` distinguishes these from older stored-assessment snapshots. Relevant evidence, revision, applicability or original-availability changes project `sourceReview=REVIEW_REQUIRED` through the existing task/continuation machinery. The original task, approval, advisory and consumed policy remain inspectable. A fresh task can consume the changed evidence immediately. Another claim, global count or unused neutral descriptive update does not invalidate the original decision. No FX hold, speed adjustment, delay coefficient, savings claim or extra approval state machine is introduced.

## Validation and retained local evidence

- Final backend acceptance/regression run: **303 passed** across 20 files, including feedback, news, originals, collector timing, navigation, current-input role journey, passage/finance and weather shadow. One existing FastAPI/httpx deprecation warning. Earlier focused runs overlap and are not added to this total.
- TypeScript, changed-file ESLint and isolated production build pass. All 267 frontend source files match the isolated build snapshot under line-ending normalization.
- Browser contracts: 28 passes, comprising 14 feedback/passage contracts at 1366px and 390px, with keyboard disclosures, enlarged text, hash downloads, as-of filtering and saved-record recovery. Eight feedback cases were rerun on the final summary correction; these overlap the original four contracts.
- Eight genuine local one-click role landing checks passed (four roles × desktop/mobile), without uncaught page errors or document overflow. These are separate from fixture contracts. Backend tests cover Company → Port → Vessel → explicitly simulated outcome, retries, recovery and visitor isolation; they do not establish actual operational execution.
- All eight protected role/twin files match `e906f6a` after line-ending normalization. Geometry, hourly approach weather and rejected neural/RL artifacts are unchanged.
- Three economic source-original downloads matched their retained SHA-256 values. The public audit at 00:17:19Z had SHA-256 `8d75941ed64ca8c923f0415be9a420b84ba21d1c942a6559dab21b6668df129c`; the exact same bytes/hash were reproduced after backend restart.

Local preview: **http://127.0.0.1:4209/login**, backend 8810. The existing weather and intelligence reconciliation workers remain enabled in this one local backend; they continue on their six-hour cadence while it runs. The weather report updated at 00:23Z on October 26. No Codex automation, Windows task, collector service or new infrastructure was added.

Audits, source attempts, screenshots, fixture browser results and validation logs remain locally under ignored `work/feedback-reconciliation-20261025/`. Original public bytes remain in the established archives. None of those runtime artifacts, visitor/session records, credentials, `debug.log` or the 19 unrelated CSV changes belong in this commit.

The verified production branch is `main`; public alias `india-portwatch.vercel.app` remains on `dpl_A1h2oea2ujsFCgL5BCx3hYvjYyYQ`. Feature-branch source publication is separate from production promotion. Remaining dependencies are a retrievable qualified secondary news original, subsequent FX releases and enough prospective independent outcomes for chronological evaluation. No improved accuracy, calibrated news reliability or measured shipping benefit is claimed.
