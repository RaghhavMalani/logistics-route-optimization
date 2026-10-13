"""Collect approved sources now; originals and first-seen times are immutable."""
import argparse
import json
from pathlib import Path

from src.portwatch_os.intelligence.public_ports import PORTS, PublicPilot
from src.utils.config import STATE_DIR


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", choices=PORTS)
    parser.add_argument("--actor", required=True, help="Named collector (CLI bypasses API identity; operator command only)")
    parser.add_argument("--reports", type=int, default=3, choices=range(1, 8))
    parser.add_argument("--ensure-cohort", action="store_true", help="Open a fixed 30-day cohort if none is enrolling")
    args = parser.parse_args()
    service = PublicPilot(Path(STATE_DIR)/"public_port_pilot")
    try:
        if args.ensure_cohort:
            from src.portwatch_os.clock import LIVE, get_clock, wall_now
            if get_clock().state.mode != LIVE:
                raise ValueError("Cohort creation requires the live clock")
            # wall-clock: operator enrollment is defined at the actual present.
            now = wall_now()
            if not any(c["status"] == "ENROLLING" for c in service.cohorts(args.port, now)):
                service.start_cohort(args.port, now, args.actor)
        result = service.refresh(args.port, args.actor, report_limit=args.reports)
        print(json.dumps(result, indent=2))
        return 1 if result["errors"] else 0
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
