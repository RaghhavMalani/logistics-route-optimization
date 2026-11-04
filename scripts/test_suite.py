"""Run the complete pytest suite with the reviewed node-level quarantine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "tests" / "quarantine.json"


class Quarantine:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.entries = {}
        for entry in json.loads(REGISTER.read_text(encoding="utf-8")):
            node = entry["test"]
            if "::" not in node or node in self.entries or not entry["reason"].strip() or not entry["owner"].strip():
                raise ValueError(f"Quarantine requires a unique test, reason, and owner: {node}")
            self.entries[node] = entry

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_modifyitems(self, items):
        missing = self.entries.keys() - {item.nodeid for item in items}
        if missing:
            raise pytest.UsageError("Stale quarantine entries: " + ", ".join(sorted(missing)))
        if not self.enabled:
            return
        for item in items:
            entry = self.entries.get(item.nodeid)
            if entry:
                item.add_marker(pytest.mark.skip(reason=f"{entry['reason']} · Owner: {entry['owner']}"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--include-quarantined", action="store_true")
    args, pytest_args = parser.parse_known_args()
    return pytest.main(
        [str(ROOT / "tests"), "--rootdir", str(ROOT), "-q", *pytest_args],
        plugins=[Quarantine(enabled=not args.include_quarantined)],
    )


if __name__ == "__main__":
    sys.exit(main())
