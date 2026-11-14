"""Export selected rows and the manuscript from the reviewed paper/v2 revision."""

import csv
import io
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "92567c527a424c57cc392bc86b175a9a7903299d"
TERMINAL = ROOT / "india-portwatch-terminal"


def blob(path):
    return subprocess.check_output(["git", "show", f"{SOURCE}:{path}"], cwd=ROOT)


def read_table(name):
    return list(csv.DictReader(io.StringIO(blob(f"paper/tables/{name}.csv").decode("utf-8-sig"))))


def select(rows, **fields):
    row, = (row for row in rows if all(row[key] == value for key, value in fields.items()))
    return row


def interval(row, estimate, lower="lower95", upper="upper95"):
    return {"estimate": float(row[estimate]), "lower95": float(row[lower]), "upper95": float(row[upper])}


def main():
    ablation = read_table("e1-ablation-paired")
    tails = read_table("e1-cost-tails")

    def delta(rule, objective):
        row = select(ablation, domain="cargo", policy=rule, metric=objective)
        return interval(row, "differenceVsIncumbent")

    def exceedance(rule):
        row = select(tails, domain="cargo", policy=rule, metric="probabilityCostRegretOver10000")
        return interval(row, "estimate")

    r1 = select(ablation, domain="cargo", policy="R1", metric="costUsdMean")
    extreme, = read_table("e1-worst-cargo-cases")
    coverage = [row for row in read_table("e7-coverage") if row["horizon"] == "all"]
    threshold = select(read_table("manuscript-settings"), parameter="tailThreshold")
    decisions = read_table("e7-cargo-decisions")
    data = {
        "schemaVersion": 1,
        "paperSourceSha": SOURCE,
        "costFirst": {"pairs": int(r1["pairedCases"]), "timeRegretHours": delta("R1", "hoursMean"),
                      "costRegretUsd": delta("R1", "costUsdMean")},
        "tail": {"thresholdUsd": float(threshold["value"]), "incumbentExceedance": exceedance("portwatch_robust"),
                 "rules": [{"rule": rule, "exceedance": exceedance(rule),
                            "meanCostRegretUsd": delta(rule, "costUsdMean"),
                            "meanTimeRegretHours": delta(rule, "hoursMean")} for rule in ("R3", "R4")],
                 "extreme": {"case": extreme["case"], "regretUsd": float(extreme["observedRegretUsd"])}},
        "coverage": [{"nominalPercent": int(row["nominalPercent"]), "rows": int(row["testRows"]),
                      "before": float(row["coverageBefore"]), "after": float(row["coverageAfter"])} for row in coverage],
        "decisions": [{"rule": row["rule"], "pairs": int(row["pairs"]), "switches": int(row["switches"])}
                      for row in decisions],
    }
    (TERMINAL / "src/data/paper-findings.v1.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    (TERMINAL / "public/portwatch-study.pdf").write_bytes(blob("docs/paper/paper.pdf"))


if __name__ == "__main__":
    main()
