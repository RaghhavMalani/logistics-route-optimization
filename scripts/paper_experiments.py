"""Rebuild the preregistered cargo-risk paper from the repository inputs."""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import paper_figures as figs, paper_score as scoring
from src.portwatch_os.decision.commercial import digest
from src.portwatch_os.decision.paper_corpus import PAPER_SEED


def canonical_bytes(path):
    return path.read_bytes().replace(b"\r\n", b"\n")


def locked_registration(seed, *, smoke):
    path = ROOT / "paper/PREREGISTRATION.json"
    registration = json.loads(path.read_text(encoding="utf-8-sig"))
    canonical = {key: value for key, value in registration.items() if key != "registrationHash"}
    if digest(canonical) != registration["registrationHash"]:
        raise RuntimeError("Invalid preregistration digest")
    if not smoke:
        committed = subprocess.check_output(["git", "show", "HEAD:paper/PREREGISTRATION.json"], cwd=ROOT)
        if committed.replace(b"\r\n", b"\n") != canonical_bytes(path) or seed != registration["seed"]:
            raise RuntimeError("A confirmatory run requires the committed preregistration and its exact seed")
        for relative, expected in registration["registeredInputs"].items():
            if sha256(canonical_bytes(ROOT / relative)).hexdigest() != expected:
                raise RuntimeError(f"Frozen input changed: {relative}")
        if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no",
                                    "--", "scripts", "src", "requirements-paper.txt"], cwd=ROOT).strip():
            raise RuntimeError("Commit experiment code before the confirmatory run")
    return registration


def tex_escape(value):
    substitutions = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
                     "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}
    return "".join(substitutions.get(char, char) for char in str(value))


def table(directory, name, rows, columns=None, *, latex=True):
    headers = list(dict.fromkeys(key for row in rows for key in row)) if columns is None else list(columns)
    path = directory / f"{name}.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    if latex:
        body = [r"% Requires \usepackage{booktabs}", r"\begin{tabular}{" + "l" * len(headers) + "}", r"\toprule"]
        body += [" & ".join(map(tex_escape, headers)) + r" \\", r"\midrule"]
        for row in rows:
            values = []
            for key in headers:
                value = row.get(key)
                values.append(tex_escape("--" if value is None else f"{value:.6g}" if isinstance(value, float) else value))
            body.append(" & ".join(values) + r" \\")
        body += [r"\bottomrule", r"\end{tabular}"]
        (directory / f"{name}.tex").write_text("\n".join(body) + "\n", encoding="utf-8", newline="\n")
    return path


def linked(name, line, label="CSV row"):
    return f"[{label}](../../paper/tables/{name}.csv#L{line})"


def results(output, rows, deltas, stable, checks, contrast, case_rows, break_even, bench):
    lines = [
        "# Cargo risk study results", "",
        "The vessel corpus uses a synthetic USD 250/h proxy. The cargo corpus prices fictional terms. "
        "Intervals on policy differences use paired case bootstrap resampling and describe this case-generating design. "
        "See [methods](METHODS.md) and [threats to validity](THREATS.md).", "",
        "## E1 · Held-out policy comparison", "",
        "| Corpus | Policy | Scored | Mean regret (h) | P90 regret (h) | Mean cost regret (USD) | Δ mean USD vs incumbent [95% CI] | Act-best captures |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for i, row in enumerate(rows, 2):
        domain, policy = row["domain"], row["policy"]
        j, delta = next((j, d) for j, d in enumerate(deltas, 2)
                        if (d["domain"], d["policy"], d["metric"]) == (domain, policy, "costUsdMean"))
        lines.append(f"| {domain} | {policy} | {row['scored']}/{row['offered']} | {row['hoursMean']:.2f} | "
                     f"{row['hoursP90']:.2f} | {row['costUsdMean']:.2f} | {delta['differenceVsIncumbent']:.2f} "
                     f"[{delta['lower95']:.2f}, {delta['upper95']:.2f}] {linked('e1-paired', j, 'Δ')} | "
                     f"{row['captured']}/{row['actIsBest']} {linked('e1-policy', i, 'E1')} |")
    lines += ["", "The [E1 summary](../../paper/tables/e1-policy.csv), [paired intervals](../../paper/tables/e1-paired.csv) "
              "and [signed-rank results](../../paper/tables/e1-signed-rank.csv) include the remaining metrics.",
              "", "### Preregistered R5 decision", "",
              f"**{'Promote' if all(row['passes'] for row in checks) else 'Do not promote'}** under the committed gate.", ""]
    for i, row in enumerate(checks, 2):
        estimate = row["observed"]
        observed = f"{estimate:.4g}" if estimate is not None else "unavailable"
        lines.append(f"- {row['split']} · {row['metric']} · {observed} {row['comparison']} {row['threshold']:.4g} "
                     f"· {'pass' if row['passes'] else 'fail'}. {linked('r5-promotion', i)}")
    lines += ["", "## E2 · Variance reduction", "",
              "[Log–log plot](../../paper/figures/e2-variance.pdf) · [SE and intervals](../../paper/tables/e2-variance.csv)", ""]
    for i, row in enumerate(stable, 2):
        first = row["futuresPerOptionToStableRank"]
        lines.append(f"- {row['method']} · {first if first else 'no stable tier'} futures per option. {linked('e2-stable-rank', i)}")
    lines += ["", "## E3 · Sensitivity", "",
              "[Tornado](../../paper/figures/e3-tornado.pdf) · [endpoints](../../paper/tables/e3-tornado.csv) · "
              "[Sobol indices and intervals](../../paper/tables/e3-sobol.csv) · [index plot](../../paper/figures/e3-sobol.pdf)",
              "", "## E4 · Cargo-blind comparison", ""]
    for i, row in enumerate(contrast, 2):
        lines.append(f"- {row['metric']} · {row['estimate']:.4g}, 95% CI [{row['lower95']:.4g}, {row['upper95']:.4g}], "
                     f"{row['pairedCases']} paired cases. {linked('e4-cargo-blind', i)}")
    lines += ["", "## E5 · Case studies", ""]
    for i, row in enumerate(case_rows, 2):
        if row["selectedR1"]:
            key = row["case"]
            lines.append(f"- {key} · {row['reasonR1']} {linked('e5-cases', i)} "
                         f"[Arrival fan](../../paper/figures/e5-{key}-arrival.pdf) · "
                         f"[Cost distribution](../../paper/figures/e5-{key}-cost.pdf)")
    lines += ["", "The recorded Ever Given reopening is scored separately in the "
              "[conditional replay table](../../paper/tables/e5-historical-conditional.csv).", ""]
    for i, row in enumerate(break_even, 2):
        bracket = (f"{row['lowerHours']:.2f}–{row['upperHours']:.2f} h" if "lowerHours" in row else
                   f"no flip from {row['gridMinHours']:.0f} to {row['gridMaxHours']:.0f} h")
        lines.append(f"- {row['case']} · {bracket}. {linked('e3-break-even', i)}")
    lines += ["", "[All rule choices](../../paper/tables/e5-rule-choices.csv) · "
              "[Excluded cost components](../../paper/tables/e5-unknown-costs.csv)", "", "## Runtime", ""]
    for i, row in enumerate(bench, 2):
        lines.append(f"- {row['profile']} · {row['seconds']:.3f} s · {row['options']} options × {row['consignments']} consignments · "
                     f"{row['futures']} futures · {row['stop']} at USD {row['pairedSeUsd']:.2f} SE. {linked('runtime', i)}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--all", action="store_true")
    modes.add_argument("--smoke", action="store_true")
    parser.add_argument("--seed", type=int, default=PAPER_SEED)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    seed, smoke = args.seed, args.smoke
    started = perf_counter()
    registration = locked_registration(seed, smoke=smoke)
    output = args.output or ROOT / ("work/paper-smoke" if smoke else "paper")
    output.mkdir(parents=True, exist_ok=True)
    tables, figures, data = (output / name for name in ("tables", "figures", "data"))
    for folder in (tables, figures, data):
        folder.mkdir(exist_ok=True)
    runtimes = {}
    settings = registration["selected"]
    resamples = 99 if smoke else 10_000
    splits = ("tuning",) if smoke else ("validation", "test")
    scores, offered = {}, {}
    for split in splits:
        now = perf_counter()
        scores[split], failures = scoring.score_split(split, seed, settings, smoke)
        offered[split] = 2 if smoke else registration["corpora"][split][1]
        table(data, f"{split}-case-scores", scores[split], latex=False)
        table(data, f"{split}-excluded", failures, ("id", "domain", "split", "error"), latex=False)
        runtimes[f"score_{split}"] = perf_counter() - now
    now = perf_counter()
    scored = scores[splits[-1]]
    summary, intervals, signed_ranks = scoring.compare(scored, seed, resamples, offered[splits[-1]])
    contrast = scoring.time_only_comparison(scored, seed, resamples)
    checks = [] if smoke else scoring.promotion(scores, registration["gate"], offered)
    for name, rows in (("e1-policy", summary), ("e1-paired", intervals), ("e1-signed-rank", signed_ranks),
                       ("e4-cargo-blind", contrast), ("r5-promotion", checks)):
        table(tables, name, rows)
    runtimes["e1_e4_summary"] = perf_counter() - now
    studies = list(figs.studies(seed))
    case = studies[1][0]
    now = perf_counter()
    e2, stable = figs.variance(case, seed, figures, smoke)
    table(tables, "e2-variance", e2)
    table(tables, "e2-stable-rank", stable)
    runtimes["e2"] = perf_counter() - now
    now = perf_counter()
    tornado, sobol = figs.sensitivity(case, seed, figures, smoke)
    table(tables, "e3-tornado", tornado)
    table(tables, "e3-sobol", sobol)
    runtimes["e3"] = perf_counter() - now
    now = perf_counter()
    case_rows, break_even, unknown, historical, choices = figs.case_outputs(studies, seed, settings, figures, smoke)
    bench = figs.runtime(case, seed, smoke)
    for name, rows in (("e5-cases", case_rows), ("e3-break-even", break_even), ("e5-unknown-costs", unknown),
                       ("e5-historical-conditional", historical), ("e5-rule-choices", choices), ("runtime", bench)):
        table(tables, name, rows)
    runtimes["e5_and_runtime"] = perf_counter() - now
    if not smoke and output.resolve() == ROOT / "paper":
        results(ROOT / "docs/paper/RESULTS.md", summary, intervals, stable, checks, contrast, case_rows, break_even, bench)
    manifest = {
        "gitSha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "seed": seed, "preregistrationHash": registration["registrationHash"],
        "mode": "tuning smoke" if smoke else "confirmatory", "evaluatedSplits": splits,
        "selected": settings, "bootstrapResamples": resamples,
        "seedDerivation": {
            "corpus": "vessel case seed; cargo case seed plus 100000; cargo mix [master,case,620]; hidden truth [master,case,1009]",
            "caseSobol": "[master,case,413]; Sobol replicate streams from [derived seed,stream]",
            "bootstrap": "E1 [master,901,domainIndex]; E4 [master,904]",
            "figures": "E5 cargo [master,510..513], E2 [master,520], E3 [master,521..522], E5 [master,530..533], runtime [master,540..542]",
        },
        "packages": {name: version(name) for name in ("numpy", "scipy", "matplotlib", "pydantic", "pandas", "networkx")},
        "python": platform.python_version(), "platform": platform.platform(),
        "cpu": os.getenv("PROCESSOR_IDENTIFIER") or platform.processor() or platform.machine(),
        "logicalCpus": os.cpu_count(), "runtimeSeconds": {**runtimes, "total": perf_counter() - started},
        "r5Promotion": None if smoke else all(row["passes"] for row in checks),
        "artifacts": {str(file.relative_to(output)).replace("\\", "/"): sha256(file.read_bytes()).hexdigest()
                      for folder in (data, tables, figures) for file in sorted(folder.iterdir()) if file.is_file()},
    }
    (output / "RUN_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{manifest['mode']} finished in {manifest['runtimeSeconds']['total']:.2f}s, manifest {output / 'RUN_MANIFEST.json'}")


if __name__ == "__main__":
    main()
