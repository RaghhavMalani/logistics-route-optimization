"""Refresh supported sources and forecast outputs, retaining the prior artifacts.

Learning writes use a review ledger for this local verification. The operational
evidence/identity stores are never reset or supplied with QA fixtures.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

root = Path(__file__).resolve().parents[1]
review = root / "work" / "capability-upgrades"
review.mkdir(parents=True, exist_ok=True)
archive = review / "before-forecast-refresh.zip"
if not archive.exists():
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as saved:
        for relative in ("data/cache", "outputs/forecasts", "outputs/expert_features", "outputs/regimes"):
            for path in (root / relative).rglob("*"):
                if path.is_file():
                    saved.write(path, path.relative_to(root))
env = dict(os.environ)
env["PORTWATCH_STATE_DIR"] = str(review / "learning-state")
env["PORTWATCH_LICENCE_MODE"] = "DEMO"
with (review / "forecast-refresh.log").open("w", encoding="utf-8") as log:
    result = subprocess.run([sys.executable, str(root / "run_award_demo.py"),
        "--source", "portwatch", "--model", "ensemble", "--refresh"], cwd=root,
        env=env, stdout=log, stderr=subprocess.STDOUT)
print(json.dumps({"exitCode": result.returncode, "archive": str(archive), "log": str(review / "forecast-refresh.log")}))
raise SystemExit(result.returncode)
