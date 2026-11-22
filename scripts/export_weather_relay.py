"""Export the only queries the weather relay may send upstream."""
import argparse
import json
from pathlib import Path

from src.portwatch_os.intelligence.current_environment import SURFACE_GROUPS, SURFACE_QUERY
from src.utils.port_registry import PORTS

TARGET = Path(__file__).resolve().parents[1] / "services/weather-relay/queries.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    groups = [PORTS[index::SURFACE_GROUPS] for index in range(SURFACE_GROUPS)]
    queries = [{**SURFACE_QUERY, "latitude": ",".join(str(port.lat) for port in group),
                "longitude": ",".join(str(port.lon) for port in group)} for group in groups]
    rendered = json.dumps(queries, ensure_ascii=True, indent=2) + "\n"
    if args.check:
        if TARGET.read_text(encoding="utf-8") != rendered:
            parser.exit(1, "Weather relay queries are stale. Run python -m scripts.export_weather_relay.\n")
        return
    TARGET.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
