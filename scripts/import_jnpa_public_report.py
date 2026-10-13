"""Import the official public JNPA berth table as evidence awaiting verification."""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

from src.portwatch_os.clock import wall_now
from src.portwatch_os.intelligence.arrivals import stamp
from src.portwatch_os.intelligence.jnpa_public import URL, parse_report, save_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/jnpa/public_reports"))
    args = parser.parse_args()
    with urlopen(Request(URL, headers={"User-Agent": "PortWatch-research/1.0"}), timeout=30) as response:
        if not response.url.startswith("https://www.jnport.gov.in/"):
            raise ValueError("Official report redirected outside JNPA")
        content = response.read(2_000_001)
        if len(content) > 2_000_000:
            raise ValueError("Report exceeds the size limit")
        html = content.decode("utf-8")
    report = parse_report(html, stamp(wall_now()))
    path = save_report(report, args.output)
    stored = json.loads(path.read_text(encoding="utf-8"))
    print(f"Staged {len(stored['records'])} public berth records, report {stored['reportDate']}: {path.resolve()}")
    print("0 qualifying prospective calls; scheduler, MMSI and confirmed all-fast evidence still required.")


if __name__ == "__main__":
    main()
