"""Operator CLI for the same collector used by the backend refresh scheduler."""
import argparse
import json
from pathlib import Path

from src.portwatch_os.clock import wall_now
from src.portwatch_os.intelligence.public_collection import (
    collect_port, collection_quality, prepare_audit, verify_chain,
)
from src.portwatch_os.intelligence.public_ports import PORTS, PublicPilot, stamp
from src.utils.config import STATE_DIR


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor", required=True)
    args = parser.parse_args()
    store = PublicPilot(Path(STATE_DIR)/"public_port_pilot")
    try:
        # wall-clock: every operator run keeps its actual start receipt.
        started = wall_now()
        results = {}
        for port in PORTS:
            results[port] = collect_port(store, port, args.actor)
        result = {"startedAt": stamp(started), "actor": args.actor, "ports": results}
        folder = store.root/"collection_runs"
        folder.mkdir(exist_ok=True)
        receipt = folder/(stamp(started).replace(":", "-")+".json")
        receipt.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"receipt": str(receipt.resolve()), **result}, indent=2))
        return int(any(r["errors"] for r in results.values()))
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
