"""Freeze R5 using only the registered tuning and validation splits."""

import argparse
import json
from hashlib import sha256
from pathlib import Path

import numpy as np

from src.portwatch_os.decision.cargo_policy import RuleSettings, decide
from src.portwatch_os.decision.commercial import digest
from src.portwatch_os.decision.paper_corpus import (
    DOMAINS, PAPER_SEED, TUNING_EPSILON, TUNING_Q, cases, prepared, score,
)
from src.portwatch_os.decision.benchmark import CORPORA


def metrics(rows):
    scored = [row for row in rows if row["scored"]]
    eligible = sum(row["actIsBest"] for row in rows)
    captured = sum(row["captured"] for row in scored)
    return {
        "scored": len(scored), "p90Hours": float(np.quantile([r["hoursRegret"] for r in scored], .9)) if scored else None,
        "meanCost": float(np.mean([r["costRegret"] for r in scored])) if scored else None,
        "captured": captured, "actIsBest": eligible, "captureRate": captured / eligible if eligible else None,
        "interventions": sum(row["acted"] for row in scored),
    }


def project(split, master, settings):
    if split not in ("tuning", "validation"):
        raise ValueError("The calibration command cannot read the test split")
    data = {key: {domain: [] for domain in DOMAINS} for key in settings}
    errors = []
    for domain in DOMAINS:
        for case, error in cases(split, domain, master):
            if error:
                errors.append(error)
                continue
            rows, worlds, _ = prepared(case, master)
            for key, rule in settings.items():
                pick = decide(case.study, rows, worlds, rule, evaluate_wait=False)
                data[key][domain].append(score(case, "R5", pick["optionId"], 0))
    return {key: {domain: metrics(rows) for domain, rows in result.items()}
            for key, result in data.items()}, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=PAPER_SEED)
    parser.add_argument("--output", type=Path, default=Path("paper/PREREGISTRATION.json"))
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preregistration already exists")
    grid = {(q, eps): RuleSettings(rule="R5", q=q, epsilon=eps) for q in TUNING_Q for eps in TUNING_EPSILON}
    tuning, failures = project("tuning", args.seed, grid)
    def rank(key):
        vessel, cargo = (tuning[key][name] for name in DOMAINS)
        q, eps = key
        return (
            vessel["p90Hours"] > 1,
            -((vessel["captureRate"] or 0) + (cargo["captureRate"] or 0)),
            vessel["meanCost"] / 250 + cargo["meanCost"] / 1000,
            vessel["interventions"] + cargo["interventions"], -q, eps,
        )

    selected = min(grid, key=rank)
    validation, validation_errors = project("validation", args.seed, {selected: grid[selected]})
    record = {
        "version": "cargo-paper-preregistration-v1", "seed": args.seed, "corpora": CORPORA,
        "selected": {"q": selected[0], "epsilon": selected[1]},
        "tuningCriterion": "Prefer vessel p90 <= 1 h, then maximize sum of two capture rates, minimize weighted mean cost regret, minimize interventions, prefer higher q and lower epsilon",
        "candidateGrid": [{"q": q, "epsilon": eps, "metrics": tuning[(q, eps)]} for q, eps in grid],
        "validation": validation[selected], "failures": failures + validation_errors,
        "gate": {"vesselP90MaxHours": 1, "vesselCaptureMinFraction": .5, "minimumCoverageFraction": .9,
                 "cargoP90CostMaxRatioVsIncumbent": 1.05, "evaluate": ["validation", "test"]},
        "registeredInputs": {
            path: sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for path in ("src/portwatch_os/decision/benchmark.py", "src/portwatch_os/decision/paper_corpus.py",
                         "src/portwatch_os/decision/cargo_policy.py", "src/portwatch_os/decision/cargo_sampling.py",
                         "src/portwatch_os/decision/cargo_risk.py", "src/portwatch_os/decision/outcome.py",
                         "src/portwatch_os/cargo/demo_consignments.py", "scripts/tune_cargo_policy.py")
        },
        "testInspected": False,
    }
    record["registrationHash"] = digest(record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"selected": record["selected"], "validation": record["validation"],
                      "failures": record["failures"], "registrationHash": record["registrationHash"]}, indent=2))


if __name__ == "__main__":
    main()
