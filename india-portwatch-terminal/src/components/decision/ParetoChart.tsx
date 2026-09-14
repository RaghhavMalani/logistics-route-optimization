/**
 * The decision frontier as a chart an operator can click.
 *
 * Two objectives on two axes, one point per feasible option. Points on the
 * frontier are filled; dominated ones are hollow and labelled with what
 * dominates them. There is no decorative curve: every mark is an option the
 * engine evaluated, and clicking one selects its branch on the map.
 *
 * An axis is offered only when every feasible option is measured on it. A
 * frontier over "cost" when no option is priced would be a chart of nothing,
 * so the chip is disabled with the engine's own reason.
 */

import { useCallback, useMemo } from "react";

import { cn } from "@/lib/utils";
import { optionStyles } from "@/lib/maritime/decision-layers";
import type { DecisionProblem } from "@/types/decisions";

/** The axes a UI may offer, and how they are read. */
const AXES: Array<{ key: string; label: string }> = [
  { key: "eta", label: "ETA" },
  { key: "risk", label: "RISK" },
  { key: "fuel", label: "FUEL" },
  { key: "cost", label: "COST" },
  { key: "emissions", label: "EMISSIONS" },
  { key: "weather", label: "WEATHER" },
  { key: "port_wait", label: "WAIT" },
  { key: "missed_departures", label: "MISSED" },
  { key: "turnaround", label: "TURNAROUND" },
  { key: "sailing", label: "SAILING" },
  { key: "slack", label: "SLACK" },
  { key: "dwell", label: "DWELL" },
];

export function ParetoChart({
  problem,
  x,
  y,
  onAxes,
  selectedOptionId,
  onSelect,
  height = 150,
}: {
  problem: DecisionProblem;
  x: string;
  y: string;
  onAxes: (x: string, y: string) => void;
  selectedOptionId: string | null;
  onSelect: (optionId: string) => void;
  height?: number;
}) {
  const feasible = useMemo(
    () =>
      problem.options.filter((o) => o.status === "FEASIBLE" && o.evaluation),
    [problem],
  );
  const measured = useCallback(
    (key: string) =>
      feasible.length > 0 &&
      feasible.every((o) => o.evaluation?.objectives[key]?.available),
    [feasible],
  );
  const offered = AXES.filter((axis) =>
    problem.objectives.some((o) => o.key === axis.key),
  );
  const styles = optionStyles(problem);
  const objective = (key: string) =>
    problem.objectives.find((o) => o.key === key);

  const points = useMemo(() => {
    if (!measured(x) || !measured(y)) return [];
    return feasible.map((o) => ({
      option: o,
      x: o.evaluation!.objectives[x].value as number,
      y: o.evaluation!.objectives[y].value as number,
    }));
  }, [feasible, measured, x, y]);

  const width = 300;
  const pad = { l: 34, r: 12, t: 10, b: 24 };
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const range = (values: number[]) => {
    const lo = Math.min(...values),
      hi = Math.max(...values);
    const span = hi - lo || Math.abs(hi) || 1;
    return { lo: lo - span * 0.12, hi: hi + span * 0.12 };
  };
  const rx = xs.length ? range(xs) : { lo: 0, hi: 1 };
  const ry = ys.length ? range(ys) : { lo: 0, hi: 1 };
  const sx = (v: number) =>
    pad.l + ((v - rx.lo) / (rx.hi - rx.lo)) * (width - pad.l - pad.r);
  const sy = (v: number) =>
    height - pad.b - ((v - ry.lo) / (ry.hi - ry.lo)) * (height - pad.t - pad.b);
  const frontier = new Set(problem.frontier?.nondominated ?? []);
  const dominated = problem.frontier?.dominated ?? {};

  return (
    <div data-testid="pareto-chart" className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-1">
        {offered.map((axis) => {
          const ok = measured(axis.key);
          const reason = ok
            ? undefined
            : (feasible
                .map((o) => o.evaluation?.objectives[axis.key]?.unknownBecause)
                .find(Boolean) ?? "not measured");
          const active = axis.key === x || axis.key === y;
          return (
            <button
              key={axis.key}
              type="button"
              disabled={!ok}
              title={
                ok
                  ? `${objective(axis.key)?.description ?? axis.label}`
                  : `Not on offer: ${reason}`
              }
              data-testid="pareto-axis"
              data-axis={axis.key}
              data-active={active}
              onClick={() => {
                if (axis.key === x || axis.key === y) return;
                onAxes(y, axis.key);
              }}
              className={cn(
                "num rounded px-1.5 py-0.5 text-[9px] uppercase tracking-wide transition-colors",
                active
                  ? "bg-[var(--accent)] text-[var(--surface)]"
                  : "text-[var(--text-2)] hover:bg-[var(--surface-2)]",
                !ok && "cursor-not-allowed opacity-35",
              )}
            >
              {axis.label}
            </button>
          );
        })}
      </div>

      {points.length === 0 ? (
        <p className="px-1 py-2 text-[9.5px] italic text-[var(--text-3)]">
          {feasible.length === 0
            ? "No feasible option to plot."
            : `Not every feasible option is measured on ${x} and ${y}; pick axes the engine could compute.`}
        </p>
      ) : (
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full"
          role="img"
          aria-label={`Frontier over ${x} and ${y}`}
        >
          <line
            x1={pad.l}
            y1={height - pad.b}
            x2={width - pad.r}
            y2={height - pad.b}
            stroke="var(--line-strong)"
            strokeWidth={1}
          />
          <line
            x1={pad.l}
            y1={pad.t}
            x2={pad.l}
            y2={height - pad.b}
            stroke="var(--line-strong)"
            strokeWidth={1}
          />
          <text
            x={width - pad.r}
            y={height - 8}
            textAnchor="end"
            fontSize={8}
            fill="var(--text-3)"
            className="num"
          >
            {objective(x)?.label ?? x} ({objective(x)?.unit}) →{" "}
            {objective(x)?.direction === "max"
              ? "higher better"
              : "lower better"}
          </text>
          <text
            x={pad.l - 2}
            y={pad.t + 8}
            textAnchor="end"
            fontSize={8}
            fill="var(--text-3)"
            transform={`rotate(-90 ${pad.l - 2} ${pad.t + 8})`}
            className="num"
          >
            {objective(y)?.label ?? y} ({objective(y)?.unit})
          </text>
          {/* The frontier, joined in x order so the trade-off reads as a line of choices. */}
          {(() => {
            const chain = points
              .filter((p) => frontier.has(p.option.optionId))
              .sort((a, b) => a.x - b.x);
            if (chain.length < 2) return null;
            return (
              <polyline
                points={chain.map((p) => `${sx(p.x)},${sy(p.y)}`).join(" ")}
                fill="none"
                stroke="var(--text-3)"
                strokeWidth={1}
                strokeDasharray="2 3"
                opacity={0.7}
              />
            );
          })()}
          {points.map((p) => {
            const style = styles.get(p.option.optionId)!;
            const onFrontier = frontier.has(p.option.optionId);
            const selected = p.option.optionId === selectedOptionId;
            return (
              <g
                key={p.option.optionId}
                data-testid="pareto-point"
                data-option={p.option.optionId}
                data-frontier={onFrontier}
                className="cursor-pointer"
                onClick={() => onSelect(p.option.optionId)}
              >
                <title>
                  {p.option.label}: {objective(x)?.label} {p.x.toFixed(2)},{" "}
                  {objective(y)?.label} {p.y.toFixed(2)}
                  {onFrontier
                    ? " · on the frontier"
                    : ` · dominated by ${dominated[p.option.optionId]}`}
                </title>
                <circle
                  cx={sx(p.x)}
                  cy={sy(p.y)}
                  r={selected ? 7 : 5}
                  fill={onFrontier ? style.colour : "transparent"}
                  stroke={style.colour}
                  strokeWidth={selected ? 2.5 : 1.5}
                  opacity={onFrontier ? 0.95 : 0.6}
                />
                <text
                  x={sx(p.x) + 9}
                  y={sy(p.y) + 3}
                  fontSize={9}
                  fill="var(--text-2)"
                  className="num"
                >
                  {style.letter}
                </text>
              </g>
            );
          })}
        </svg>
      )}
      <p className="px-1 text-[9px] leading-snug text-[var(--text-3)]">
        Filled: nondominated. Hollow: dominated by the option named on hover.
        Every point is an evaluated option; click one to switch the world to its
        branch.
      </p>
    </div>
  );
}
