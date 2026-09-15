"""Run the decision benchmark corpus and publish the aggregate.

    python scripts/benchmark_decisions.py                    # 40 cases per domain, seed 1
    python scripts/benchmark_decisions.py --cases 100        # a larger fixed corpus
    python scripts/benchmark_decisions.py --json results.json

The corpus is seeded; the same arguments produce the same cases on every
machine. Nothing is cherry-picked: every case is reported in the aggregate,
and every case PortWatch lost on is listed with what beat it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PORTWATCH_LICENCE_MODE", "DEMO")
os.environ.setdefault("PORTWATCH_FRESHNESS_SCHEDULER", "0")


def _fmt(value: Any, unit: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}{unit}"
    return f"{value}{unit}"


def render(out: Dict[str, Any], *, measured_at: str) -> str:
    from src.portwatch_os.decision.benchmark import POLICIES

    agg = out["aggregate"]
    lines = [
        "# Decision benchmark",
        "",
        f"Measured {measured_at}. Produced by `python scripts/benchmark_decisions.py --cases "
        f"{out['casesPerDomain']} --seed {out['baseSeed']}`; the corpus is fixed by those two numbers and "
        "nothing in it was chosen after seeing a result.",
        "",
        "Four policies choose from the same simulated option set on every case, so the comparison isolates "
        "what the optimiser adds (the frontier, the balanced ranking, the Critic) from what the simulator "
        "adds. Each case has a hidden truth the policies never see; every chosen option is scored against it. "
        "`regret` is the realised delay of the chosen option minus the realised delay of the best feasible "
        "option on that case. Decision time for `portwatch` includes building and evaluating the whole "
        "problem; the baselines are charged only for their selection because they are handed the engine's "
        "options.",
        "",
        "## How each domain is scored",
        "",
        "- **VESSEL** — a chokepoint claim and a hull bound through it. Truth: the closure's actual duration, "
        "lognormal around a median that grows with severity, fizzling with probability falling in corroboration. "
        "Options are scored by the mission scorecard's realised model (wait for the reopening, then a queue "
        "drained in arrival order; a detour is certain). A `change_destination_port` option has no realised model "
        "and is unscored.",
        "- **PORT** — a berth plan for three to six calls that bunch. Truth: arrivals slip (N(+1.0, 1.5) h) and "
        "moves run over (×N(1.08, 0.15)). Each plan is re-simulated by the port twin on the true state. Delay is "
        "mean wait; a missed departure commitment is a violation.",
        "- **CARGO** — a transshipment connection. Truth: the inbound discharge slips (N(+1.2, 1.4) h, never "
        "earlier) and every cut-off moves (N(0, 0.8) h). Delay is hours from the true ready hour to the sailing "
        "actually made; a missed connection is a violation and the box takes the next feasible sailing (72 h "
        "if there is none in the case).",
        "",
    ]
    for domain, table in agg.items():
        lines += [f"## {domain} — {table['cases']} cases" + (f" ({table['errors']} refused by the engine)" if table["errors"] else ""), "",
                  "| policy | mean delay (h) | mean regret (h) | zero-regret share | violations | mean risk | mean fuel index | mean berth utilisation | mean decision time | unscored |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for policy in POLICIES:
            row = table["policies"][policy]
            lines.append(f"| {policy} | {_fmt(row['meanDelay'])} | {_fmt(row['meanRegret'])} | "
                         f"{_fmt(row['zeroRegretShare'])} | {row['violations']} | {_fmt(row['meanRisk'])} | "
                         f"{_fmt(row['meanFuel'])} | {_fmt(row['meanThroughput'])} | {_fmt(row['meanDecisionMs'], ' ms')} | {row['unscored']} |")
        lines += ["", "Head to head on realised delay (cases both policies scored):", ""]
        lines += ["| against | PortWatch wins | PortWatch loses | ties |", "|---|---:|---:|---:|"]
        for policy, h in table["headToHead"].items():
            lines.append(f"| {policy} | {h['portwatchWins']} | {h['portwatchLoses']} | {h['ties']} |")
        lines.append("")

    lost = out["losses"]
    lines += [f"## Where PortWatch lost — {len(lost)} case(s)", ""]
    if not lost:
        lines.append("No baseline realised a lower delay than the recommendation on any case in this corpus.")
    else:
        lines += ["| case | what the case was | PortWatch chose | realised | beaten by |", "|---|---|---|---:|---|"]
        for row in lost:
            beaten = "; ".join(f"{p}: {v['optionId']} at {v['delay']:.1f} h" for p, v in row["beatenBy"].items())
            lines.append(f"| {row['caseId']} | {row['description']} | {row['portwatch']['optionId']} | "
                         f"{row['portwatch']['delay']:.1f} h (regret {row['portwatch']['regret']}) | {beaten} |")
    lines += ["", "## Reading the result", ""]
    lines += out.get("notes", [])
    lines.append("")
    return "\n".join(lines)


def notes_for(out: Dict[str, Any]) -> List[str]:
    agg = out["aggregate"]
    notes: List[str] = []
    for domain, table in agg.items():
        pw = table["policies"]["portwatch"]
        best_baseline = min(
            ((p, table["policies"][p]) for p in ("current_plan", "greedy", "heuristic")
             if table["policies"][p]["meanRegret"] is not None),
            key=lambda kv: kv[1]["meanRegret"], default=None,
        )
        if pw["meanRegret"] is None or best_baseline is None:
            continue
        name, row = best_baseline
        fewest = min(table["policies"][p]["violations"] for p in ("current_plan", "greedy", "heuristic"))
        if pw["meanRegret"] < row["meanRegret"]:
            verdict = "lower than the best baseline's"
        elif pw["meanRegret"] == row["meanRegret"]:
            verdict = "equal to the best baseline's"
        else:
            verdict = "*higher* than the best baseline's"
        violations = ("fewer violations than any baseline" if pw["violations"] < fewest else
                      "as many violations as the best baseline" if pw["violations"] == fewest else
                      "more violations than the best baseline")
        notes.append(f"- **{domain}**: PortWatch's mean regret {pw['meanRegret']} h is {verdict} ({name}, "
                     f"{row['meanRegret']} h), with {pw['violations']} violations -- {violations} (fewest {fewest}). "
                     + ("The losses table says where it lost on delay." if pw["meanRegret"] > row["meanRegret"] else ""))
    # The vessel finding, read off the cases rather than asserted: how often the
    # recommendation was a hedge (an action other than the plan), and what the
    # hedge cost when the claim fizzled or the closure ended before arrival.
    vessel = [r for r in out["results"] if r["domain"] == "VESSEL" and not r["error"]]
    hedged = [r for r in vessel if r["choices"]["portwatch"]["optionId"] != r["choices"]["current_plan"]["optionId"]]
    if vessel and hedged:
        lost_hedges = [r for r in hedged if (r["choices"]["portwatch"]["delay"] or 0) > (r["choices"]["current_plan"]["delay"] or 0) + 1e-9]
        won_hedges = [r for r in hedged if (r["choices"]["portwatch"]["delay"] or 0) < (r["choices"]["current_plan"]["delay"] or 0) - 1e-9]
        fizzled = [r for r in lost_hedges if r["truth"].get("fizzled")]
        notes.append(
            f"- **VESSEL, the hedge**: on {len(hedged)} of {len(vessel)} cases the engine recommended an action other than "
            f"proceeding (a slow-steam hold to arrive after the claim horizon, mostly). The hedge beat proceeding on "
            f"{len(won_hedges)} and lost on {len(lost_hedges)}; {len(fizzled)} of the losses were claims that fizzled, "
            f"where the hold was pure cost. Under the realised queue model a hull that arrives early in a closure "
            f"queues near the front, so holding rarely pays unless the closure outlasts the claim horizon by a wide "
            f"margin. The BALANCED ranking pays for zero exposure with hours; this corpus says how many."
        )
    lost = out["losses"]
    if lost:
        by_domain: Dict[str, int] = {}
        for row in lost:
            by_domain[row["domain"]] = by_domain.get(row["domain"], 0) + 1
        notes.append("- Losses by domain: " + ", ".join(f"{d} {n}" for d, n in sorted(by_domain.items())) + ".")
    notes.append("- The baselines were handed the engine's simulated options; their decision times are selection "
                 "only. A baseline that had to enumerate and simulate its own options would pay what PortWatch pays.")
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cases", type=int, default=40)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--json", default=None)
    parser.add_argument("--out", default=str(ROOT / "docs" / "DECISION_BENCHMARK.md"))
    args = parser.parse_args()

    from src.portwatch_os.decision.benchmark import run_suite

    out = run_suite(cases_per_domain=args.cases, base_seed=args.seed)
    out["notes"] = notes_for(out)
    measured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for domain, table in out["aggregate"].items():
        print(f"{domain}: {table['cases']} cases")
        for policy, row in table["policies"].items():
            print(f"  {policy:<13} delay {str(row['meanDelay']):>8}  regret {str(row['meanRegret']):>7}  "
                  f"zero-regret {str(row['zeroRegretShare']):>6}  violations {row['violations']:>3}  ms {row['meanDecisionMs']}")
        print(f"  head-to-head: {table['headToHead']}")
    print(f"losses: {len(out['losses'])}")
    Path(args.out).write_bytes(render(out, measured_at=measured_at).encode("utf-8"))
    print(f"wrote {args.out}")
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
