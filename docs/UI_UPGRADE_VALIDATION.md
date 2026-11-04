# Local UI capability validation

Date: 2 November 2026. Branch: `feat/portwatch-restored-intelligence`.
Production remains unchanged. The separately authorized isolated hosted preview
is tracked in `INTEGRATED_PREVIEW_20261102.md`. Generated evidence is ignored.

## Backend checks

| Completed run | Result | Evidence |
|---|---|---|
| Commercial accounting/API, public-source truth, all thirteen fictional commercial templates, world clock and clock boundaries | 61 passed | `work/ui-visual-upgrade-20261101/reviewed61-final.log` |
| Existing current-weather, official port-context, AIS ingestion and recorder regressions | 57 passed | `work/ui-visual-upgrade-20261101/existing-final.log` |
| Bounded jobs, commercial API/shadow, image-source proof, backup/restore, release identity and clock boundaries | 45 passed | `work/ui-visual-upgrade-20261101/hosted-release-tests.log` |
| Final candidate one-shot backup/receipt refusal plus the preceding release subset | 47 passed | `work/hosted-preview-20261102/startup-backup-tests.log` |
| Same-visitor concurrent cancellation through the real demo adapter plus release subset | 48 passed | `work/hosted-preview-20261102/cancel-adapter-tests.log` |
| Public-only seed integrity, import/idempotency, quarantine and privacy boundaries | 9 passed | `work/ui-visual-upgrade-20261101/seed-release-tests.log` |

The first two runs cover non-overlapping test files. The 45/47/48-test release runs
overlap commercial/clock files and one another and are reported separately,
never added to their total.
Earlier interrupted or incorrectly configured attempts are not added. One attempt
omitted the repository's PDF dependency directory. The weather unit test now
explicitly aligns world and receipt clocks; a frozen receipt alone must not make
old data current in a live world. The final existing-suite run emitted a slow
import stack during AIS replay/model import and subsequently passed all 57 tests.
The core run has the existing Starlette/httpx deprecation warning.

The checks cover private ownership/role refusal, retry/resource-cache recovery,
minimal advisory bindings, immutable successors, decimal/currency accounting,
required commitments, missing components, shared resource capacity, finite CVaR
ties, seeded/candidate-order-independent shared samples, empirical collecting,
old-date/new-receipt semantics, failed/unqualified retention, future availability,
source reads without network writes and actual AIS normalizer sentinel/time rules.
They demonstrate software behavior, not operational accuracy.

## Frontend and visual evidence

TypeScript and changed-file lint are run against the existing frontend, with
isolated Nitro/node-server builds. Lint's existing mixed-export/hook warnings and
large Cesium/map/twin bundle warnings are retained as build limitations.

The first compiled-browser attempt found an inspector bug: changing Radix's root
modal mode remounted the contents and reset an opening globe. The final design
keeps that root stable and uses a separate focus scope for expanded inspection.
The worklist close action clears its own hash so the same exact deep link can
reopen it. Source inspection does the same. These are implementation fixes,
not hidden acceptance exceptions. The final compiled build passed TypeScript,
changed-file lint (warnings only), and 21 normal-login browser checks with no
application runtime errors: exact saved option/reload, queue and source reopening,
globe mounting, keyboard focus, 1920/390/360/landscape layouts, mobile Layers and
Timeline, enlarged text and a separate visitor's refusal. Results are in
`work/ui-visual-upgrade-20261101/browser-audit.json`.

Paired full-size screenshots are under
`work/ui-visual-upgrade-20261101/{before,after}`. They use the same normal QA
visitor and saved case, frozen before-response payloads, viewport and map camera.
The after display clock is fixed to the corresponding before capture for this
read-only presentation check. The original scenario response is replayed to open
the identical old comparison, without executing a new calculation or approval.
This presentation fixture is separate from the unmocked exact-link and recovery
checks. New public-only products without a prior equivalent
are identified separately. The mixed worklist is explicitly named a fixed
synthetic UI fixture. Independent provider and workflow checks use normal time,
no response substitution and normal demo entry.

All sixteen pairs completed: Company 1366/1920, actual and fixed synthetic fleet
queues, source review 1366/1920, approach comparison, strategic-route comparison,
globe, Port advisory, Vessel response, Admin source inspector, mobile Layers and
Timeline, and 390/360-pixel comparison views. The board, full-size links and
captioned video are available only on `http://127.0.0.1:8922/`; the server has an
explicit file allowlist and does not serve private capture/session state.

The real provider-backed case retained in the local profile calculated a
fictional passage using genuine current forecasts. Its incumbent recommendation
was KEEP_CURRENT_PLAN; fuel and total-cost benefits stayed unavailable without
the necessary declarations. A Company-private multiple-consignment study and
256-draw assumption-sensitivity run were retained with hashes and a linked
commercial successor. No learning or operational-policy promotion occurred.

## Recording and reproduction

`scripts/record_ui_upgrade.mjs` records actual loopback UI interactions through
normal one-click login. With `--restart-backend` it invokes the narrowly scoped
`scripts/restart_local_provider_backend.py`, which verifies the recorded process
ID, executable, creation time, script, state directory and port before restarting
only that local provider process with durable state.
No authentication seeding, route mocks, clock overrides, fabricated DOM results
or public upload are used by that recorder.

The generated manifest, captions, screenshots and recording are in
`work/ui-visual-upgrade-20261101/video`. The previous 7:25 demonstration remains
under `work/current-source-demo/video/final`; the new recording does not rewrite
that historical evidence. Public receipts and private declarations remain out
of Git. See the source coverage document for failed providers and product rights.

The final compiled recording passed in 114.2 seconds (115.2-second encoded clip),
with fifteen scenes, no runtime errors and an actual local backend restart after
Company approval. It retained comparison
`dec-commercial-0fcf93544fe27732de574d9e14a8d4c4`, commercial context hash
`7c3eda235b8eb0afe15be99b173f36543e1b28c0ee92042535ab5c5d0e5c570a`
and sample hash `e8f4baef4e78efb8b1b9b27015eab560a213b029e3196bfa656dd33d95e85426`.
Advisory `ADV-INPRT-59D1A63573` passed Port review/issue, Vessel acknowledgement
and acceptance, followed by a labelled simulated outcome. The historical video's
SHA-256 remains `a1efdddb5c4270e8eab1303b59d7b103130f8258faa938c52ce82a6b8fc804ea`.
