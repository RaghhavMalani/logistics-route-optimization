"""Run the decision benchmark corpora, publish the aggregate, and put the
robust policy through the promotion gate.

    python scripts/benchmark_decisions.py                       # tuning + validation + test
    python scripts/benchmark_decisions.py --corpus validation   # one corpus
    python scripts/benchmark_decisions.py --json results.json   # keep every case

The corpora are seeded and disjoint (``CORPORA`` in the benchmark module);
the same arguments produce the same cases on every machine. Nothing is
cherry-picked: every case is reported in the aggregate, every case the
candidate lost on is listed with what beat it, and the gate's verdict is
written whether it passed or failed.
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


def _pct(value: Any) -> str:
    return "—" if value is None else f"{100.0 * float(value):.0f}%"


def render_corpus(out: Dict[str, Any]) -> List[str]:
    from src.portwatch_os.decision.benchmark import CANDIDATE, INCUMBENT, POLICIES

    lines: List[str] = []
    agg = out["aggregate"]
    first, last = out["seedRange"]
    lines += [f"# {out['corpus'].upper()} corpus — seeds {first}-{last}, {out['casesPerDomain']} cases per domain", ""]
    for domain, table in agg.items():
        lines += [f"## {domain} — {table['cases']} cases" + (f" ({table['errors']} refused by the engine)" if table["errors"] else ""), "",
                  "| policy | mean delay (h) | mean regret (h) | median regret | p90 regret | worst regret | zero-regret share | violations | intervention rate | unnecessary interventions | wait rate | mean decision time | p95 decision time |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for policy in POLICIES:
            row = table["policies"][policy]
            lines.append(f"| {policy} | {_fmt(row['meanDelay'])} | {_fmt(row['meanRegret'])} | {_fmt(row['medianRegret'])} | "
                         f"{_fmt(row['p90Regret'])} | {_fmt(row['worstRegret'])} | {_fmt(row['zeroRegretShare'])} | "
                         f"{row['violations']} | {_pct(row['interventionRate'])} | {_pct(row['unnecessaryInterventionRate'])} | "
                         f"{_pct(row['waitRate'])} | {_fmt(row['meanDecisionMs'], ' ms')} | {_fmt(row['p95DecisionMs'], ' ms')} |")
        capture = table.get("beneficialInterventionCapture") or {}
        lines += ["", f"An intervention was the realised best on {table.get('interventionWasBest', 0)} case(s); captured by: "
                  + ", ".join(f"{p} {_pct(capture.get(p))}" for p in POLICIES) + ".", ""]
        kinds = table["policies"][CANDIDATE].get("kinds") or {}
        if kinds:
            lines += [f"`{CANDIDATE}` answered: " + ", ".join(f"{k} {n}" for k, n in kinds.items()) + ".", ""]
        lines += ["Head to head on realised delay (cases both policies scored):", "",
                  "| policy | against | wins | loses | ties |", "|---|---|---:|---:|---:|"]
        for mine in (INCUMBENT, CANDIDATE):
            for policy, h in table["headToHead"][mine].items():
                lines.append(f"| {mine} | {policy} | {h['wins']} | {h['loses']} | {h['ties']} |")
        lines.append("")

    lost = out["losses"]
    lines += [f"## Where `{CANDIDATE}` lost — {len(lost)} case(s)", ""]
    if not lost:
        lines.append("No other policy realised a lower delay than the robust recommendation on any case in this corpus.")
    else:
        lines += ["| case | what the case was | robust chose | kind | realised | beaten by |", "|---|---|---|---|---:|---|"]
        for row in lost:
            beaten = "; ".join(f"{p}: {v['optionId']} at {v['delay']:.1f} h" for p, v in row["beatenBy"].items())
            lines.append(f"| {row['caseId']} | {row['description']} | {row['portwatch']['optionId']} | "
                         f"{row['portwatch'].get('kind') or '—'} | {row['portwatch']['delay']:.1f} h (regret {row['portwatch']['regret']}) | {beaten} |")
    lines.append("")
    return lines


def render(suites: Dict[str, Dict[str, Any]], gate: Dict[str, Any], *, measured_at: str) -> str:
    from src.portwatch_os.decision.benchmark import CANDIDATE, CORPORA, INCUMBENT

    lines = [
        "# Decision benchmark",
        "",
        f"Measured {measured_at}. Produced by `python scripts/benchmark_decisions.py`; each corpus is fixed by its "
        "seed range (`CORPORA` in `src/portwatch_os/decision/benchmark.py`) and nothing in it was chosen after "
        "seeing a result.",
        "",
        "Five policies choose from the same simulated option set on every case, so the comparison isolates what "
        "the optimiser adds (the frontier, the balanced ranking, the Critic, the robust gate) from what the "
        "simulator adds. Each case has a hidden truth the policies never see; every chosen option is scored "
        "against it. `regret` is the realised delay of the chosen option minus the realised delay of the best "
        "feasible option on that case. Decision time for the two PortWatch policies includes building and "
        "evaluating the whole problem; the baselines are charged only for their selection because they are "
        "handed the engine's options.",
        "",
        f"`{INCUMBENT}` is the incumbent expected-value ranking. `{CANDIDATE}` is the candidate: the same options "
        "evaluated under four stress horizons (FIZZLE, SHORT, BASE, LONG) with a minimax-regret gate that may "
        "answer KEEP_CURRENT_PLAN or WAIT_FOR_MORE_INFORMATION (`docs/ROBUST_DECISIONS.md`). A WAIT is scored "
        "by simulating the wait: if the closure had ended by the re-evaluation instant the hull keeps its plan, "
        "otherwise it takes the provisional option the recommendation named.",
        "",
        "## Corpora",
        "",
        "| corpus | seeds | cases per domain | role |",
        "|---|---|---:|---|",
    ]
    roles = {"tuning": "the original corpus; its results were read while the robust policy was designed",
             "validation": "used to check the design and revise it where it failed; every revision is in the git history",
             "test": "untouched until the final run; the promotion verdict rests on it"}
    for name, (first, count) in CORPORA.items():
        lines.append(f"| {name} | {first}-{first + count - 1} | {count} | {roles.get(name, '')} |")
    lines += [
        "",
        "## How each domain is scored",
        "",
        "- **VESSEL** — a chokepoint claim and a hull bound through it. Truth: the closure's actual duration, "
        "lognormal around a median that grows with severity, fizzling with probability falling in corroboration. "
        "Options are scored by the closure outcome model (wait for the reopening, then a queue drained in arrival "
        "order; a detour is certain) with the truth's own backlog drain. A `change_destination_port` option has "
        "no realised model and is unscored.",
        "- **PORT** — a berth plan for three to six calls that bunch. Truth: arrivals slip (N(+1.0, 1.5) h) and "
        "moves run over (×N(1.08, 0.15)). Each plan is re-simulated by the port twin on the true state. Delay is "
        "mean wait; a missed departure commitment is a violation.",
        "- **CARGO** — a transshipment connection. Truth: the inbound discharge slips (N(+1.2, 1.4) h, never "
        "earlier) and every cut-off moves (N(0, 0.8) h). Delay is hours from the true ready hour to the sailing "
        "actually made; a missed connection is a violation and the box takes the next feasible sailing (72 h "
        "if there is none in the case).",
        "",
        "The robust policy changes only VESSEL recommendations: PORT and CARGO carry no duration-uncertainty "
        "model, so there the candidate answers exactly as the incumbent and the tables show it.",
        "",
        "## Promotion verdict",
        "",
        f"**{gate['final']['verdict']}** — {gate['final']['summary']}",
        "",
        "The full check-by-check gate is in `docs/DECISION_POLICY_GATE.md`.",
        "",
    ]
    for name in CORPORA:
        if name in suites:
            lines += render_corpus(suites[name])
    lines += ["# Reading the result", ""]
    lines += gate.get("notes", [])
    lines.append("")
    return "\n".join(lines)


def render_gate(gate: Dict[str, Any], *, measured_at: str) -> str:
    from src.portwatch_os.decision.promotion import MIN_CASES, MIN_IMPROVEMENT, PROMOTION_CHECKS, TAIL_TOLERANCE

    lines = [
        "# Decision policy promotion gate",
        "",
        f"Measured {measured_at}. Produced by `python scripts/benchmark_decisions.py`.",
        "",
        "The robust recommendation policy (`portwatch_robust`) is a candidate; the BALANCED expected-value "
        "ranking (`portwatch_balanced`) is the incumbent. The candidate becomes the engine's default only if it "
        "clears every check below on the validation corpus and on the untouched test corpus. The conditions were "
        "fixed in `src/portwatch_os/decision/promotion.py` before either corpus was run:",
        "",
        f"- a material improvement is {MIN_IMPROVEMENT:.0%} on mean and p90 regret on VESSEL, the domain the policy changes; "
        "no rise anywhere else;",
        f"- the worst case may be at most {TAIL_TOLERANCE:.0%} worse than the incumbent's;",
        f"- at least {MIN_CASES} cases per domain; seeds disjoint from the tuning corpus.",
        "",
        f"## Verdict: {gate['final']['verdict']}",
        "",
        gate["final"]["summary"],
        "",
        f"Active policy: `{gate['final']['activePolicy']}`.",
        "",
    ]
    for corpus, decision in gate["decisions"].items():
        lines += [f"## {corpus} corpus — {decision['verdict']}", "", "| check | passed | evidence |", "|---|---|---|"]
        for name in PROMOTION_CHECKS:
            lines.append(f"| {name} | {'yes' if decision['checks'].get(name) else 'NO'} | {decision['reasons'].get(name, '')} |")
        lines.append("")
    lines += ["## What the gate does not decide", ""]
    lines += gate.get("caveats", [])
    lines.append("")
    return "\n".join(lines)


def notes_for(suites: Dict[str, Dict[str, Any]]) -> List[str]:
    from src.portwatch_os.decision.benchmark import CANDIDATE, INCUMBENT

    notes: List[str] = []
    for corpus, out in suites.items():
        for domain, table in out["aggregate"].items():
            cand, inc = table["policies"][CANDIDATE], table["policies"][INCUMBENT]
            if cand["meanRegret"] is None or inc["meanRegret"] is None:
                continue
            base = table["policies"]["current_plan"]
            if domain == "VESSEL":
                notes.append(
                    f"- **{corpus} / VESSEL**: the robust policy's mean regret is {cand['meanRegret']} h against the "
                    f"incumbent's {inc['meanRegret']} h and the current plan's {base['meanRegret']} h; p90 "
                    f"{cand['p90Regret']} against {inc['p90Regret']}; worst {cand['worstRegret']} against "
                    f"{inc['worstRegret']}. It intervened on {_pct(cand['interventionRate'])} of cases "
                    f"(incumbent {_pct(inc['interventionRate'])}), answered WAIT on {_pct(cand['waitRate'])}, and "
                    f"captured {_pct((table.get('beneficialInterventionCapture') or {}).get(CANDIDATE))} of the "
                    f"{table.get('interventionWasBest', 0)} case(s) where an intervention was the realised best "
                    f"(incumbent {_pct((table.get('beneficialInterventionCapture') or {}).get(INCUMBENT))})."
                )
            else:
                same = cand["meanRegret"] == inc["meanRegret"] and cand["violations"] == inc["violations"]
                notes.append(
                    f"- **{corpus} / {domain}**: {'identical to the incumbent' if same else 'differs from the incumbent'} "
                    f"(mean regret {cand['meanRegret']} h, {cand['violations']} violations); the robust gate does not "
                    "apply to this domain."
                )
    # The hedge, read off the cases: the incumbent's slow-steam holds and what
    # they cost when the closure ended before the claim did.
    for corpus, out in suites.items():
        vessel = [r for r in out["results"] if r["domain"] == "VESSEL" and not r["error"]]
        hedged = [r for r in vessel if r["choices"][INCUMBENT]["optionId"] != r["choices"]["current_plan"]["optionId"]]
        if vessel and hedged:
            lost = [r for r in hedged if (r["choices"][INCUMBENT]["delay"] or 0) > (r["choices"]["current_plan"]["delay"] or 0) + 1e-9]
            won = [r for r in hedged if (r["choices"][INCUMBENT]["delay"] or 0) < (r["choices"]["current_plan"]["delay"] or 0) - 1e-9]
            robust_hedged = [r for r in vessel if r["choices"][CANDIDATE]["optionId"] != r["choices"]["current_plan"]["optionId"]]
            notes.append(
                f"- **{corpus} / VESSEL, the hedge**: the incumbent hedged (an action other than proceeding) on "
                f"{len(hedged)} of {len(vessel)} cases and the hedge beat proceeding on {len(won)}, lost on {len(lost)}. "
                f"The robust policy hedged on {len(robust_hedged)}. Under the closure outcome model a hold that "
                "arrives just after the claim lapses lands at the back of the queue the closure formed, so it "
                "pays only in a narrow band of closure lengths; the panel now shows that band as the break-even."
            )
    notes.append("- The baselines were handed the engine's simulated options; their decision times are selection "
                 "only. A baseline that had to enumerate and simulate its own options would pay what PortWatch pays.")
    return notes


CAVEATS = [
    "- It does not score WAIT against a second real observation: the benchmark has none, so a WAIT is scored by the "
    "stated model (the plan if the closure had ended by the re-evaluation instant, else the provisional option).",
    "- It does not reward a hedge that loses on net. A policy that never intervenes on a corpus where no "
    "intervention pays is measured as correct on that corpus; the beneficial-intervention capture figure says "
    "how many paying interventions it declined, and the reader decides whether that is acceptable.",
    "- The truth's backlog drain is drawn from a range the policy does not see; the policy's own drain is the mean "
    "of two recorded closures. The queue-model-agreement check inside the policy guards against a recommendation "
    "that rests on the drain assumption alone.",
    "- PORT and CARGO are unchanged by the candidate; the gate checks them for regressions only.",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--corpus", action="append", default=None,
                        help="tuning, validation or test; repeatable; default all three")
    parser.add_argument("--json", default=None)
    parser.add_argument("--out", default=str(ROOT / "docs" / "DECISION_BENCHMARK.md"))
    parser.add_argument("--gate-out", default=str(ROOT / "docs" / "DECISION_POLICY_GATE.md"))
    args = parser.parse_args()

    from src.portwatch_os.decision.benchmark import CORPORA, run_suite
    from src.portwatch_os.decision.promotion import evaluate_policy_promotion, final_verdict

    corpora = args.corpus or list(CORPORA)
    suites: Dict[str, Dict[str, Any]] = {}
    decisions = []
    for name in corpora:
        out = run_suite(corpus=name)
        suites[name] = out
        decision = evaluate_policy_promotion(out)
        decisions.append(decision)
        print(f"== {name} corpus (seeds {out['seedRange'][0]}-{out['seedRange'][1]})")
        for domain, table in out["aggregate"].items():
            print(f"{domain}: {table['cases']} cases")
            for policy, row in table["policies"].items():
                print(f"  {policy:<19} regret mean {str(row['meanRegret']):>7} median {str(row['medianRegret']):>6} "
                      f"p90 {str(row['p90Regret']):>7} worst {str(row['worstRegret']):>7}  violations {row['violations']:>3}  "
                      f"intervene {_pct(row['interventionRate']):>4} unnecessary {_pct(row['unnecessaryInterventionRate']):>4} "
                      f"wait {_pct(row['waitRate']):>4}  ms {row['meanDecisionMs']}")
        print(f"  gate: {decision.verdict} " + (f"failed {decision.failed_checks}" if not decision.passed else ""))
    final = final_verdict(decisions)
    gate = {"decisions": {d.corpus: d.to_dict() for d in decisions}, "final": final,
            "notes": notes_for(suites), "caveats": CAVEATS}
    measured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"FINAL: {final['verdict']} — {final['summary']}")
    Path(args.out).write_bytes(render(suites, gate, measured_at=measured_at).encode("utf-8"))
    Path(args.gate_out).write_bytes(render_gate(gate, measured_at=measured_at).encode("utf-8"))
    print(f"wrote {args.out} and {args.gate_out}")
    if args.json:
        Path(args.json).write_text(json.dumps({"suites": suites, "gate": gate}, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
