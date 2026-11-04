"""Export or check the canonical OpenAPI document without starting the API."""

import argparse
import json
from pathlib import Path

from backend.app.main import app

SCHEMA = Path(__file__).resolve().parents[1] / "backend" / "openapi.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not SCHEMA.is_file() or SCHEMA.read_text(encoding="utf-8") != rendered:
            parser.exit(1, "OpenAPI is stale. Run python -m scripts.export_openapi.\n")
    else:
        SCHEMA.write_text(rendered, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
