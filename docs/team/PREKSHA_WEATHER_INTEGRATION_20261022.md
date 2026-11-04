# Source-quality and weather-shadow integration

Validated locally on October 21–22, 2026, on `feat/portwatch-restored-intelligence`. Source publication is the scope of this milestone; production deployment remains deferred.

## Preserved history and delivered scope

| Boundary | Commit |
| --- | --- |
| Integration base | `1d99630320ce8eefd3e90be691dcb86706657eaa` |
| Weather-shadow checkpoint | `9afc553af969bfb248015de3a28c63a90d6a691d` |
| Preksha's reviewed published tip | `fae2a1a405c297f17dfda683e48c71a8c25ff7e3` |
| Normal merge | `1d35fb3d468b69b92d8f08bfc10a3655eaf9fecc` |
| Forecast identity, focus and context fixes | `f41f747e69f22cf27353a7bb6c2a713865d09af8` |

The teammate tip was fetched and checked for later commits; none existed at the final remote-tip check. The merge preserves Preksha's authorship and published history. No checkout switch, reset, rebase, squash or force-push was used. Unrelated modified `data/portwatch` CSVs remain outside these commits. Local databases, visitor records, credentials, downloaded reports, captures, build output and disposable QA artifacts remain ignored.

Preksha's delivered iteration adds Admin Data's inline source inspector and JSON diagnostic download, optional source-quality metadata validation, the registry client boundary, parent-owned archive-location selection, mission-comparison button polish and her dated QA/audit evidence. It does not complete every mobile, comparison, advisory or collector task in the original team brief. Ananya's port geometry and future GEE boundary remain outside this change.

The eight protected Company/Vessel/Port/Admin/twin source files still match restored `e906f6a` after line-ending normalization. The hourly approach calculator still matches the base commit. Maps, globe, layers, timeline and original role entry points retain their implementations. Historical predictions, approvals, advisory evidence and rejected model artifacts are not rewritten.

## Correct forecast identity

`ForecastClaimSchema` adds optional `predictionId`, `provider`, `sourceProductId` and `sourceVersion`; `targetId` continues to identify the outcome being forecast. Both `QualityBatchSchema` and `parseQualityBatch` use `forecastPredictionIdentity` under `forecast-prediction-v1`.

An explicit prediction ID is authoritative. Legacy compatibility identity uses target ID, normalized origin instant, known provider/product and actual model/source version. Missing provider/product remains explicitly unknown; no provider is inferred. Without an explicit ID, a precise origin and a known model or source version are required. Insufficient identity is quarantined. The original two-vintage reproduction, which has origin/model versions but no provider/product fields, retains both forecasts.

Forecast value, error, receipt order and receipt identity never manufacture a new prediction identity. Receipt references form an evidence set. Exact retries coalesce; conflicting payloads under one prediction identity quarantine every version with its original payload and a reason. Ordering cannot choose a winning forecast. The strict batch schema rejects conflicts; the normalizer returns their audit records. Compatibility cannot distinguish unreported providers, so conflicting claims in that namespace remain unresolved rather than guessed.

This is an additive presentation/diagnostic contract. It is not connected to the weather ledger and changes no existing ledger IDs or independent-target counts.

## Context, focus and source semantics

`WeatherLearningPanel` owns archive location independently from variable. Its feedback query uses that location, variable and caller identity. The verification child remounts for the selected location/variable so old source-response selection cannot appear under a new context. Matched inspection, original-response controls, daily watch and `WeatherShadowPanel` remain combined in the existing view.

The Admin inspector replaces the table inline. Opening focuses Close (or the heading if no Close action exists); returning focuses the corresponding remounted Inspect control. The removed table button has no misleading `aria-pressed`. No modal role or focus trap was added. Inspector-local wrapping supports long originals/hashes, with a separately scrolling body and accessible Close control at 390px.

Malformed optional quality metadata is explained while legacy receipt data remains available. Missing fields remain unknown. Receipt freshness, underlying observation age, historical role, forecast role and operational use remain separate. The exact strict registry schema accepts all 13 entries from the live backend contract.

## Validation actually performed

| Check | Result and date |
| --- | --- |
| Weather/API/raw consumption, journey/recovery, arrival and cache suite | 89 passed, October 21 |
| Additional isolated outage and context suite | 12 passed, October 21; distinct from the 89 above |
| Contract and fixture browser suite | 44 passed across desktop 1366×768 and 390×844, October 21 |
| TypeScript and changed-file ESLint | Passed on the integrated files, October 21 |
| Isolated frontend build | Passed using the node-server preset, October 21; owner preview/output not stopped or overwritten |
| Final source/build correspondence | All 250 frontend TS/TSX files match build inputs after CRLF→LF normalization only, October 22 |
| Live local API | Four roles, exact registry contract, frozen report replay, original hashes/aggregates, raw guards, rejected models and visitor isolation passed, October 21 |
| Real browser advisory workflow | Company approval → Port review/draft/issue → Vessel acknowledgement/acceptance → labelled simulated outcome, October 21 |
| Recovery | Browser Back/reload, Company-approval reload and Vessel-acceptance reload passed October 21. A fresh valid visitor, immutable task/disposition, idempotent writes, second-visitor isolation and exact October 21 frozen report survived an actual backend restart October 22 |

The 44 runs include pure contract cases repeated in each viewport project; they are not 44 different operational outcomes. The browser fixtures establish presentation/contract behavior, not live provider correctness. They cover optional metadata rejection, historical/current labels, diagnostic download, keyboard focus/return, no modal semantics, long-evidence scrolling and location/variable persistence. The real browser pass separately used the actual local backend and all four original role entries, current weather and separate activity age, matched-original inspection, shadow report/audit download, and the connected advisory journey. At 390px the actual advisory page had document width 390px; the actual source inspector had width/scrollWidth 343px and body height/scrollHeight 278/485px.

The advisory example compares requested approach at October 29 11:00Z with a later arrival at 15:00Z. Both options reach the same clear approach time, with assumed anchorage wait 4 h versus 0 h. Its outcome is `SIMULATED_DEMO_OUTCOME`, not weather verification, real execution, a measured saving or a berth guarantee. Unsupported fuel, cost and uncertainty remain unavailable.

The October 21 demo session had expired normally before October 22's recovery check. Demo lifetime is 12 hours. A fresh visitor was prepared before the restart; no expired credential was refreshed or bypassed. Restart recovery is established within a valid session, not indefinite access after expiry.

The build retains existing large-map/globe chunk and ineffective dynamic-import warnings. Tests retain the existing Starlette/httpx deprecation warning. These are not new correctness failures.

## Dated weather and operational evidence

The historical October 19 audit remains 654 matched forecast snapshots / 117 outcome identities / three dates. The October 21 frozen report `wx-shadow-report-e88abc2fb434310c9235ca10`, at `2026-10-21T10:32:59.854277Z`, contains **1,116 qualified matched snapshots / 195 outcome identities / five dates**. All 195 exact contexts remain **COLLECTING**, `decisionEligible=false`; daily operational consumers remain raw. These are neither independent weather days nor independent training examples across repeated forecast receipts.

The retained five-day INNSA maximum-gust example has now resolved against explicitly identified ERA5 gridded reanalysis: **17.1 kn original forecast → 12.8 kn outcome → +4.3 kn forecast-minus-outcome error** for October 15. Outcome first availability is `2026-10-21T10:19:41.800872Z`. Both retained byte hashes and both complete 24-hour maximum aggregates were independently verified. The latest-prospective cohort selection uses a different original vintage, 15.7 kn, for the same outcome: +2.9 kn and one independent target. The earlier missing-original claim remains open and excluded; the retained example is not substituted into it. No correction or rejected neural/RL model was adopted.

NAVCEN was reachable and CURRENT during the October 21 live check. The register contained 403 retained/catalogue rows, including ten missing rows disabled for calculation and one currently supported notice. It would be false to describe that live check as a provider outage. Separate isolated tests verify 403 historical recovery/restart and non-calculable unavailable, missing and unsupported records. A context review remains `UNRESOLVED` / `NOT_OBSERVED`, adds zero real outcomes and creates no delay/cost claim.

## Evidence locations and remaining limits

Ignored local evidence is retained in `work/preksha-integration-20261021/`: `backend-tests.txt`, `source-failure-and-context-tests.txt`, `fixture-browser-tests.txt`, `isolated-build.log`, `build-source-manifest.json`, `LIVE_API_VALIDATION.json`, original/hash proofs and fresh browser captures. October 22's `work/preksha-integration-20261022/RESTART_RECOVERY.json` records the actual restart check. Private QA credentials remain in separately named ignored files and must never be published. Preksha's committed screenshots/audits retain their original dates; they are not relabelled as this integration run.

Local build validation used frontend `http://127.0.0.1:4201` and the existing isolated backend `http://127.0.0.1:8798/api`. The owner's development preview remains separately configured on 4199. Durable local backend state and archives were reused; production state was not copied into QA or modified.

Weather remains collecting. Reanalysis is not a station observation. Broader mobile/comparison/advisory review, source coverage and economic metadata remain follow-ups. Existing weather-comparison annotations still contain fixed October 2 activity wording; actual source observation/receipt ages are available separately in the source register/status strip, and activity does not enter this hourly gate calculation. Removing that inherited wording needs a scoped cleanup preserving old frozen decisions. Authorized camera evidence, model research, Ananya's geometry and GEE integration are not completed by this merge. No production promotion is included.
