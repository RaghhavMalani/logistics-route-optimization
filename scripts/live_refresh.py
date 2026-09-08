"""Continuously refresh the PortWatch digital-twin artefacts.

Designed for a long-running demo/deployment worker. Each cycle runs the award
pipeline against the freshest available live source and atomically replaces the
API cache only after a successful pipeline run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cycle(source: str, model: str, refresh: bool) -> int:
    command = [
        sys.executable,
        str(ROOT / "run_award_demo.py"),
        "--source", source,
        "--model", model,
    ]
    if refresh:
        command.append("--refresh")
    stamp = datetime.now(timezone.utc).isoformat()
    print(f"[{stamp}] refresh: {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh PortWatch intelligence on a fixed cadence.")
    parser.add_argument("--interval-minutes", type=float, default=15.0)
    parser.add_argument("--source", default="portwatch", choices=["auto", "portwatch", "real", "sample"])
    parser.add_argument("--model", default="ensemble", choices=["ensemble", "tft", "baseline"])
    parser.add_argument("--no-network-refresh", action="store_true")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    args = parser.parse_args()

    interval = max(args.interval_minutes, 1.0) * 60.0
    while True:
        code = run_cycle(args.source, args.model, not args.no_network_refresh)
        if code != 0:
            print("Refresh failed; last known-good cache remains available.", flush=True)
        if args.once:
            raise SystemExit(code)
        time.sleep(interval)


if __name__ == "__main__":
    main()
