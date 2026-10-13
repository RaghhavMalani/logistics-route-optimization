# Independent review of the restored capabilities

Reviewed October 10, 2026. This is review feedback for the implementation chat, not a new application design. No application source, training artifacts, operational evidence or deployment was changed by this review.

## What was independently checked

- Company demo opens at `http://127.0.0.1:4198/company/overview` in the original Fleet Command interface, with the map, layers, surrounding simulated traffic, original navigation and weather timeline.
- Company Global Eye opens in the original workflow. The additional God's Eye globe renders within its intelligence panel; the original workspace remains behind it. Provider coverage and cached/archived/fictional distinctions are visible.
- Eight core Company, Vessel, Port, Admin and twin files listed in `work/capability-upgrades/review-manifest.json` match Git commit `e906f6a6bd4388cd3c059b4d9a5de6759139528b` after normalizing checkout line endings.
- The UI shows **STALE 8D**, and `data/cache/port_state.json` records `INNSA.observedAt` as October 2. The forecast export retains its October 2 origin and October 3–12 targets. On October 10, only October 11–12 remain strictly future dates.
- The neural report records rejection and MAE 5.9844 versus GBM 5.8279. The RL report records rejection and lower simulator reward than lookahead. These comparisons do not establish operational accuracy or savings.

The reported 64-test run, TypeScript check and build were not rerun during this read-only implementation review. The browser checks above were performed independently; they do not replace the full four-role lifecycle suite.

## Findings for the implementation chat

### P2: Serialize the evaluated RL status into the policy artifact

`src/portwatch_os/twin/constrained_rl.py:107` computes rejection, but the experiment writes `policy.to_dict()` at line 118 without assigning that result to `policy.experiment_status`. `to_dict()` defaults to `CANDIDATE` at line 77.

The current files consequently disagree: `outputs/forecasts/constrained_rl.json` says **CANDIDATE**, while `constrained_rl_report.json` says **REJECTED**. The existing loader reads the report and restores rejection; this review found no evidence that the rejected policy replaced the incumbent. However, a downloaded or independently consumed policy artifact misstates its evaluation status.

Persist the evaluated status before serialization, bind policy and report to the same experiment identity, and add a regression for a rejected run. Preserve the existing training/report evidence rather than silently changing its recorded experiment history.

### P2: Make source dropout hide source inputs during training

`src/forecasting/neural_fusion.py:59` creates a dropped-source mask, but line 62 still computes the gate from the full feature matrix. That matrix includes each specialist's median, interval width and original availability flag. Only the output weights are masked.

The gate can therefore use a supposedly unavailable specialist to choose weights for the remaining specialists during training. Actual missing-source inference zeroes those inputs and changes the availability flags, creating a different input condition.

For future experiments, construct the training feature matrix from the dropped-source values and masks as well as masking the output weights. Evaluate the revised candidate under missing-provider conditions on a new chronological reporting period. Keep the current rejected model and its report as the record of the experiment already performed; this finding does not justify promotion or invalidate the recorded comparison of that saved model.

## Next product priority

Keep this restored interface as the base. The next milestone should demonstrate a current, connected shipping decision within it:

1. Refresh supported current weather and regional hazard inputs independently of the lagging IMF activity observation. Retain each source's issue, valid, availability and observation times; retain the October 2 age on the congestion inputs.
2. Trace one relevant signal through affected route/port exposure into the existing decision comparison. Show the consumed input and a concrete change in a dated shipping consequence, such as arrival window, simulated wait or feasible berth action. Geographic context alone is insufficient evidence of an effect.
3. Complete Company proposal → Port review → Vessel acknowledgement → demo outcome in the original role screens, with the same frozen evidence and assumptions visible throughout.
4. Make the five-day weather case inspectable now, including unmatched outcomes. As later valid observations become available, match them prospectively and display forecast error; enable learned correction only after its existing data and validation gates pass.
5. Complete the camera evidence-review and scenario-application controls when authorized footage is available. No camera accuracy or whole-port occupancy claim should be inferred from the synthetic regression fixtures.

Acceptance is a working user journey with traceable, dated consequences. It does not require the rejected neural or RL candidates to beat the baselines, and it does not require another frontend replacement.
