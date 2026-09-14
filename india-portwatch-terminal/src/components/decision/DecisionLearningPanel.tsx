/**
 * Did the recommendations help? The decision engine scored from its ledger.
 *
 * Agreement (did the operator choose what the engine recommended), ranking
 * accuracy and regret where counterfactual outcomes exist (a mission reveals
 * every option's outcome; a live decision reveals only the one taken),
 * prediction error per objective for the option taken, and calibration of
 * that error against the confidence the engine attached. All of it is read
 * from stored problems and observed outcomes; the engine is never re-run
 * with hindsight, and the panel says so.
 */

import { Panel, Section } from "@/components/kit/layout";
import { useDecisionLearning } from "@/services/decisions";

export function DecisionLearningPanel() {
  const learning = useDecisionLearning();
  const data = learning.data;
  return (
    <Panel
      title="Decision learning"
      note={data?.resolved != null ? `${data.resolved} scored` : "…"}
      testId="decision-learning"
    >
      {!data?.available ? (
        <Section title="Not yet scorable">
          <p className="text-[10.5px] leading-relaxed text-[var(--text-3)]">
            {data?.note ??
              "No decision has an observed outcome yet. Record one from a decision's Decide tab, or reveal a historical mission."}
          </p>
        </Section>
      ) : (
        <>
          <Section title="Was the recommendation right?">
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              {(
                [
                  [
                    "Agreement",
                    data.agreementRate == null
                      ? null
                      : `${(data.agreementRate * 100).toFixed(0)}%`,
                  ],
                  [
                    "Ranking accuracy",
                    data.rankingAccuracy == null
                      ? "no counterfactuals"
                      : `${(data.rankingAccuracy * 100).toFixed(0)}%`,
                  ],
                  [
                    "Mean regret",
                    data.meanRegret == null
                      ? "n/a"
                      : `${data.meanRegret.toFixed(1)} h`,
                  ],
                  [
                    "Mean reward",
                    data.meanReward == null
                      ? "n/a"
                      : data.meanReward.toFixed(1),
                  ],
                  [
                    "Constraint violations",
                    String(data.constraintViolations ?? 0),
                  ],
                  ["Decisions", `${data.resolved}/${data.count}`],
                ] as Array<[string, string | null]>
              ).map(([label, value]) => (
                <div key={label}>
                  <div className="text-[9px] uppercase tracking-[0.06em] text-[var(--text-3)]">
                    {label}
                  </div>
                  <div className="num text-[15px] leading-none text-[var(--text)]">
                    {value ?? "n/a"}
                  </div>
                </div>
              ))}
            </div>
          </Section>
          {data.predictionError && Object.keys(data.predictionError).length ? (
            <Section title="Prediction error, option taken">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-[8.5px] uppercase tracking-wide text-[var(--text-3)]">
                    <th className="text-left font-normal">objective</th>
                    <th className="text-right font-normal">MAE</th>
                    <th className="text-right font-normal">bias</th>
                    <th className="text-right font-normal">n</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data.predictionError).map(([key, row]) => (
                    <tr key={key} className="num">
                      <td className="text-[var(--text-2)]">{key}</td>
                      <td className="text-right text-[var(--text)]">
                        {row.meanAbsoluteError.toFixed(1)} {row.unit}
                      </td>
                      <td className="text-right text-[var(--text-2)]">
                        {row.bias >= 0 ? "+" : ""}
                        {row.bias.toFixed(1)}
                      </td>
                      <td className="text-right text-[var(--text-3)]">
                        {row.count}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
          ) : null}
          {data.calibration && Object.keys(data.calibration).length ? (
            <Section title="Calibration · error by stated confidence">
              <ul className="space-y-0.5">
                {Object.entries(data.calibration).map(([bucket, row]) => (
                  <li
                    key={bucket}
                    className="num flex items-center gap-2 text-[10px]"
                  >
                    <span className="w-16 text-[var(--text-3)]">{bucket}</span>
                    <span
                      className="h-[5px] rounded-sm bg-[var(--warn)]"
                      style={{
                        width: `${Math.min(100, row.meanAbsoluteError)}%`,
                      }}
                    />
                    <span className="text-[var(--text-2)]">
                      {row.meanAbsoluteError.toFixed(1)} h · n={row.count}
                    </span>
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}
          <Section title="Method">
            <p className="text-[9.5px] leading-relaxed text-[var(--text-3)]">
              {data.method}
            </p>
          </Section>
        </>
      )}
    </Panel>
  );
}
