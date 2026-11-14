import study from "@/data/paper-findings.v1.json";

const usd = (value: number) =>
  `USD ${Math.abs(value).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const hours = (value: number) => `${Math.abs(value).toFixed(1)} h`;
const percent = (value: number) => `${(value * 100).toFixed(1)}%`;

function difference(value: number, format: (n: number) => string) {
  return `${value < 0 ? "−" : "+"}${format(value)}`;
}

function interval(
  data: { lower95: number; upper95: number },
  format: (n: number) => string,
) {
  return `${difference(data.lower95, format)} to ${difference(data.upper95, format)}`;
}

export function PaperFindings() {
  const { costFirst, tail, coverage, decisions, paperSourceSha } = study;
  const switches = decisions.reduce((total, row) => total + row.switches, 0);
  return (
    <section className="public-research-intro" aria-labelledby="paper-findings">
      <h2 id="paper-findings">What the study found</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <article>
          <span className="public-badge">SYNTHETIC CORPUS</span>
          <h3>Cost-first reduced cost regret</h3>
          <p>
            On {costFirst.pairs} paired cargo cases the cost-first rule reduced
            mean cost regret by {usd(costFirst.costRegretUsd.estimate)} and
            increased mean time regret by{" "}
            {hours(costFirst.timeRegretHours.estimate)} versus the incumbent.
          </p>
          <p className="public-note">
            Paired 95% intervals for the change are{" "}
            {interval(costFirst.costRegretUsd, usd)} and{" "}
            {interval(costFirst.timeRegretHours, hours)}.
          </p>
        </article>
        <article>
          <span className="public-badge">SYNTHETIC CORPUS</span>
          <h3>Risk-averse rules had fewer large regrets</h3>
          <p>
            Regret above {usd(tail.thresholdUsd)} fell from{" "}
            {percent(tail.incumbentExceedance.estimate)} for the incumbent to{" "}
            {tail.rules
              .map(
                (row) => `${percent(row.exceedance.estimate)} for ${row.rule}`,
              )
              .join(" and ")}
            . Both raised mean time and cost regret. Their worst regret was the
            same {usd(tail.extreme.regretUsd)} case ({tail.extreme.case}).
          </p>
          <ul className="public-note">
            {tail.rules.map((row) => (
              <li key={row.rule}>
                {row.rule} changed mean cost regret by{" "}
                {difference(row.meanCostRegretUsd.estimate, usd)} (95% CI{" "}
                {interval(row.meanCostRegretUsd, usd)}).
              </li>
            ))}
          </ul>
        </article>
        <article>
          <span className="public-badge">Historical forecast benchmark</span>
          <h3>Recalibration improved interval coverage</h3>
          <dl className="space-y-1">
            {coverage.map((row) => (
              <div
                key={row.nominalPercent}
                className="flex justify-between gap-2"
              >
                <dt>Nominal {row.nominalPercent}% interval</dt>
                <dd>
                  {percent(row.before)} → {percent(row.after)}
                </dd>
              </div>
            ))}
          </dl>
          <p className="public-note">
            Before and after on {coverage[0].rows.toLocaleString("en-US")}{" "}
            held-out forecast rows.
          </p>
        </article>
        <article>
          <span className="public-badge">SYNTHETIC CORPUS</span>
          <h3>Recalibration left choices unchanged</h3>
          <p>
            {switches} choices changed across {decisions.length} rules, each
            scored on {decisions[0].pairs} paired cargo cases.
          </p>
        </article>
      </div>
      <p className="public-note">
        <a href="/portwatch-study.pdf" className="public-download">
          Read the paper (PDF)
        </a>
        {" · Source revision "}
        <code>{paperSourceSha.slice(0, 7)}</code>
      </p>
    </section>
  );
}
