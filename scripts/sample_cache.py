"""Prepare the offline sample artifacts used by local development and tests."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("port_state.json", "forecast_by_port.json", "news_bundle.json")


def ensure_sample_cache(env=None) -> None:
    cache = ROOT / "data" / "cache"
    if all((cache / name).is_file() for name in REQUIRED):
        return
    subprocess.run(
        [sys.executable, "run_award_demo.py", "--source", "sample", "--model", "baseline", "--offline"],
        cwd=ROOT,
        env=env,
        check=True,
    )
