# Original application restoration — local review

October 9, 2026. The user confirmed commit `e906f6a6bd4388cd3c059b4d9a5de6759139528b` as the preferred application. This is the first local restoration checkpoint, before capability extensions or publication.

**Subsequent extension review:** the initial checkpoint below is historical. The connected demo roles and capability additions are documented in [RESTORED_APP_CAPABILITY_REVIEW.md](RESTORED_APP_CAPABILITY_REVIEW.md). Its current scope and source limits supersede the earlier next-step notes here.

## Open the restored application

The running frontend is [http://127.0.0.1:4198/login](http://127.0.0.1:4198/login). Its API runs on `127.0.0.1:9297`. Both bind to loopback.

All review accounts use password `restore-local-review`. They exist only in a separate review identity database.

| Account | Screen | Scope |
| --- | --- | --- |
| `admin@restore.local` | National Command | National review; original View as menu |
| `company@restore.local` | Fleet Command | PortWatch Demo Shipping |
| `vessel@restore.local` | Vessel Bridge | Review vessel membership |
| `port@restore.local` | Port Control and 3D Twin | Chennai / INMAA |

The browser has separate signed-in tabs for all four roles. The local launcher is `scripts/serve_restoration_review.py`. Review identities and decision/advisory writes go into `work/restoration-e906f6a/review-state-*`; `active-state.txt` records the current directory. The review reads the existing exported source cache and does not refresh or replace it. Collection scheduling and private fleet providers are disabled for this review process.

## What was recovered

Ten October-modified screen files were recovered directly from Git blobs: AppShell, GlobalEyeScreen, Company overview/routes/cargo/advisories/Global Eye, Port operations, the index route and login. Their bytes match the selected commit. The other original role routes, map components, layers, inspectors, replay controls, styles and twin scene remain the original source already in the checkout.

The restored AppShell renders the original route children again. It no longer substitutes the October demo command interface. The retained October DemoFleetCommand uses a separate copy of its ActionRow dependency so it can still compile without modifying the recovered Company screen. This component is not mounted by the restored shell.

No repository reset, branch switch, history rewrite, backend rollback or deployment was performed. Newer authentication, demo session storage, advisory logic, source collectors and evidence remain in the working tree. The pre-restoration frontend and tracked changes are saved as `work/restoration-e906f6a/before-frontend.zip` and `before-tracked.patch`.

`restored-source.json` records the recovered source hashes. `protected-before.json` and `preservation-report.json` check backend, data, Python source and tests against their state before restoration.

## Verification

- TypeScript check and production build pass.
- Authentication and isolated demo boundary tests: **16 passed**.
- Recovered source lint with formatting enforcement disabled: zero code errors, two inherited Company hook dependency warnings. The newer formatting rules report legacy formatting differences; the original source was preserved.
- Browser review covered original National radar, replay pause and weather lead time, map traffic layer toggling, Company fleet/asset inspector, Global Eye lenses/timeline, Vessel bridge and Port control.
- Port 3D Twin `+6h` changed berth utilisation from 75% to 63% and approaching arrivals from 14 to 7.
- The original Port decision UI computed six feasible options. The verified review identity recorded REVIEWED and APPROVED, then proposed three DRAFT berth advisories through the retained backend. These writes are in the review ledger.

Logs, the browser review record and screenshots are in `work/restoration-e906f6a/`: `typecheck.log`, `build.log`, `lint-source.log`, `auth-tests-verified.log`, `browser-review.json`, `national-radar.jpg`, `company-fleet.jpg`, `global-eye.jpg`, `vessel-bridge.jpg`, `port-control.jpg`, `port-twin-decision.jpg` and `port-advisory-drafts.jpg`.

## Limits and next work

The cached forecast originated on October 2 and shows **STALE 7D**. Traffic remains labelled **simulated replay**. The original port twin remains labelled **schematic**. Expired event records currently produce no active Global Eye consequences. No new data was invented to fill those gaps.

The newer isolated demo API/session implementation is preserved and its boundary tests pass. It is not yet connected to the recovered role screens: this review uses verified local identities. Restoring that integration requires service adapters within the original application.

Weather feedback, broader God's Eye integration, authorized CCTV observations, neural residual/fusion evaluation and constrained policy training remain the next implementation stage from `RESTORE_AND_EXTEND_HANDOFF.md` and `PORTWATCH_IMPLEMENTATION_PROMPT.md`. They have not been represented as finished or added to this baseline preview. Preserve this source checkpoint while integrating them into the original workflows.

## Independent review — October 9

The review chat independently compared all ten restored file hashes with `restored-source.json` and inspected the saved National, Company, Vessel and Port screenshots. The recovered routes also have no source diff from the selected Git baseline. The original map-focused compositions are present in the saved review evidence.

At this later check, 429 of the 430 protected files still matched `protected-before.json`. The exception was `data/cache/news_bundle.json`: its modification followed the original preservation report, and its metadata identifies a scheduled freshness-coordinator refresh. This later mutable-cache change is separate from a restored screen mismatch; all ten screen hashes match.

The local preview at port 4198 refused the independent browser connection, and no listeners were found on ports 4198 or 9297. Live interaction was therefore not independently re-verified. The saved browser results and test counts above remain the implementation chat's verification record.

The next product deliverable is demo-session integration inside these original screens, followed by fresh supported forecasting and the original capability plan. This review does not authorize a new interface redesign or publication.
