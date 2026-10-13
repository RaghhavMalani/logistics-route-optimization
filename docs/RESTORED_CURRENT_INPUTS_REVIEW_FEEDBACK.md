# Independent review of the current-input workflow

Reviewed October 10, 2026. This follows `RESTORED_CURRENT_INPUTS_VERIFICATION.md`. Application code and deployed services were not changed by this review. A fresh local demo was used for browser inspection; regression and recovery probes used separate test stores and mocked providers.

## Verified progress

- All eight protected role/twin files still match `e906f6a6bd4388cd3c059b4d9a5de6759139528b`, after normalizing checkout line endings.
- The neural training artifact and historical evaluation report match their previous hashes. The corrected dropout code hides unavailable specialist inputs and uses the masked feature matrix in the gradient.
- The saved RL policy and report both say `REJECTED`, share an experiment ID, and their exact report-byte hash matches. These checks close both earlier model findings. The revised neural training procedure has not yet received a new chronological evaluation.
- The native Company map labels independently refreshed weather as **FORECAST**, reports current receipts separately from the stale October 2 activity input, and retains the original navigation, timeline and surrounding simulated traffic.
- Company Global Eye's current-input controls show the October 15 five-day target as **UNMATCHED**. Unknown provider issue times remain unavailable.
- The browser comparison for PW Meridian's requested October 18, 11:00 UTC arrival consumed 15.9 kn gust and 13,920 m visibility. Under the explicit 15 kn / 5,000 m / two-clear-hour assumptions, the panel shows **4 h versus 0 h assumed anchorage wait**, with the same October 18, 15:00 UTC clear approach for both options.

This comparison moves the assumed waiting to the arrival plan; it does not establish earlier port access, fuel savings or measured operational savings. GDACS hazards are displayed as regional context and do not enter this delay calculation. The release description should distinguish those two capabilities.

## Validation performed in this review

Ten existing focused tests passed: `test_review_model_fixes.py`, `test_current_environment.py` and `test_current_input_journey.py`. They cover the model fixes, unit/time/source preservation, forecast failures, demo isolation and the Company → Port → Vessel → simulated-outcome chain. One inherited Starlette test-client deprecation warning remains.

The reported 76-test suite, TypeScript check and production build were not rerun. Browser inspection independently reproduced the frozen comparison, without issuing an advisory from the reviewer's fresh browser demo.

## P2: Preserve continuation of a pending frozen proposal

An isolated probe created and approved a Company proposal, then created and approved its Port review. It recreated only that test process's visitor-resource cache, leaving the persisted visitor world and ledger intact.

After recreation:

- The world still held the Company proposal and Port review identifiers.
- Both complete decision records still existed in the visitor's SQLite ledger.
- `GET /decisions/current-proposals` returned no proposals and a recomputation notice.
- Port handoff returned **409**, requiring a new computation.

`DecisionEngine.get()` reads its in-memory registry. The current-proposal and outcome routes require that registry rather than restoring a pending comparison from its stored decision record. The visitor resources also use a bounded 128-entry cache, so this is relevant to process restarts and cache eviction in a public application.

The refusal is deliberate and protects against continuing a decision whose world has not been rebuilt. The product gap is that a visitor cannot continue an otherwise fresh, frozen review after the resources are recreated.

The reproduction is `work/current-inputs-independent-review/test_restart_probe.py`. Its passing assertions reproduce the existing loss of continuation; they do not indicate that recovery is fixed. It does not restart or write to the running preview backend.

## Bounded next handoff

Keep the restored interface and current evidence model. Improve continuation before promoting this version for public event use:

1. Restore the visitor's frozen comparison, chosen option, workflow and advisory links from its own durable records. Recheck visitor/role scope, source receipt age, arrival time and any consumed world revision before permitting the next action. Restoration must not silently approve or issue anything.
2. When evidence has expired, provide an explicit refresh path that creates a linked successor comparison and keeps the original evidence and approvals intact. Keep already issued/accepted advisories visible; avoid making them unreachable when a new Company proposal is created.
3. Verify recovery after Company approval, Port approval, advisory issue and Vessel acceptance, plus resource-cache eviction. Confirm that retries do not duplicate advisories/outcomes and that another visitor cannot resume the records.
4. Adjust the extension's recommendation explanation. The current weather comparison shows the legacy message "the claim carries no horizon, or the current plan could not be evaluated" under `robust-v1`, although its baseline is evaluated. Explain that the closure-duration stress model does not apply to this forecast-gate comparison; retain the uncertainty limitation without suggesting the comparison failed.
5. Promote a preview of this restored application and exercise the same role journey anonymously on that domain. Carry forward the distinction between weather-driven assumed consequences, contextual hazards, simulated traffic and stale congestion inputs.

Matched weather observations, authorized camera evaluation and a revised neural experiment can continue as research work alongside the demonstration release. Their absence should remain visible rather than preventing publication of the capabilities that work.
