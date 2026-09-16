/**
 * The decision on a clock: when each option arrives, when it reaches the
 * threatened water, when the claim lapses, when the choice closes, where
 * the rough sea is.
 *
 * One row per visible option, all on the same horizontal scale, so "slow
 * steaming arrives 28 h later than continuing" is a distance on screen
 * rather than a number to subtract. Every mark comes from the option's own
 * `timeline`, which the engine emitted from the same computation as its
 * measures.
 */

import { optionStyles } from "@/lib/maritime/decision-layers";
import type {
  DecisionOption,
  DecisionProblem,
  TimelineMark,
} from "@/types/decisions";

const MARK_GLYPH: Record<TimelineMark["kind"], string> = {
  arrival: "▲",
  chokepoint: "◆",
  deadline: "▮",
  claim_lapses: "┃",
  weather: "≋",
  ready: "●",
  sailing: "▲",
};

const MARK_LABEL: Record<TimelineMark["kind"], string> = {
  arrival: "arrival",
  chokepoint: "reaches strait",
  deadline: "option closes",
  claim_lapses: "claim lapses",
  weather: "rough seas",
  ready: "cargo ready",
  sailing: "sails",
};

export function DecisionTimeline({
  problem,
  selectedOptionId,
  compare,
  onSelect,
}: {
  problem: DecisionProblem;
  selectedOptionId: string | null;
  compare: boolean;
  onSelect: (optionId: string) => void;
}) {
  const styles = optionStyles(problem);
  const rows: DecisionOption[] = problem.options.filter(
    (o) =>
      o.isBaseline ||
      o.optionId === selectedOptionId ||
      (compare && o.status === "FEASIBLE"),
  );
  const horizon = Math.max(
    24,
    ...rows.flatMap((o) => o.timeline.map((m) => m.hours)),
  );
  const ticks = niceTicks(horizon);
  const x = (hours: number) =>
    `${Math.min(100, Math.max(0, (hours / horizon) * 100))}%`;

  return (
    <div
      data-testid="decision-timeline"
      className="flex flex-col gap-1 px-2 py-1.5"
    >
      <div className="relative h-4 border-b border-[var(--line)]">
        {ticks.map((t) => (
          <span
            key={t}
            className="num absolute -translate-x-1/2 text-[10px] text-[var(--text-3)]"
            style={{ left: x(t) }}
          >
            +{t}h
          </span>
        ))}
      </div>
      {rows.map((option) => {
        const style = styles.get(option.optionId)!;
        const selected = option.optionId === selectedOptionId;
        return (
          <button
            key={option.optionId}
            type="button"
            data-testid="timeline-row"
            data-option={option.optionId}
            onClick={() => onSelect(option.optionId)}
            className="group relative h-[18px] w-full rounded text-left hover:bg-[var(--surface-2)]"
            title={option.label}
          >
            <span
              className="absolute left-0 top-1/2 h-px w-full -translate-y-1/2"
              style={{
                background: style.colour,
                opacity: selected ? 0.9 : 0.35,
              }}
            />
            <span
              className="num absolute left-0 top-0 -translate-y-[3px] rounded px-1 text-[10px] font-semibold"
              style={{ background: "var(--panel)", color: style.colour }}
            >
              {option.isBaseline ? "base" : style.letter}
            </span>
            {option.timeline.map((mark, index) => (
              <span
                key={`${mark.kind}-${index}`}
                data-mark={mark.kind}
                className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 text-[10px] leading-none"
                style={{
                  left: x(mark.hours),
                  color:
                    mark.kind === "deadline"
                      ? "var(--crit)"
                      : mark.kind === "claim_lapses"
                        ? "var(--text-3)"
                        : mark.kind === "weather"
                          ? "var(--info)"
                          : style.colour,
                  opacity: selected ? 1 : 0.7,
                }}
                title={`${MARK_LABEL[mark.kind]} · ${mark.subject} · +${mark.hours.toFixed(1)} h${mark.waveM != null ? ` · ${mark.waveM} m` : ""}`}
              >
                {MARK_GLYPH[mark.kind]}
              </span>
            ))}
          </button>
        );
      })}
      <p className="text-[10px] leading-snug text-[var(--text-3)]">
        ▲ arrival · ◆ reaches the strait · ▮ option closes · ┃ claim lapses · ≋
        rough seas. Same scale for every row; each mark is the engine's own
        figure for that option.
      </p>
    </div>
  );
}

function niceTicks(horizon: number): number[] {
  const step =
    horizon <= 48
      ? 12
      : horizon <= 120
        ? 24
        : horizon <= 300
          ? 48
          : horizon <= 600
            ? 96
            : 168;
  const out: number[] = [];
  for (let t = 0; t <= horizon; t += step) out.push(t);
  return out;
}
