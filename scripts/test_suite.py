"""Run the complete pytest suite with the reviewed node-level quarantine."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import pytest

from scripts.sample_cache import ensure_sample_cache

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
    if "--collect-only" not in pytest_args and "--co" not in pytest_args:
        ensure_sample_cache()
    os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    # API lifespans would otherwise start a live worker that races the
    # reconciliation tests for the same process-wide lock.
    os.environ.setdefault("PORTWATCH_INTELLIGENCE_RECONCILIATION", "0")
    return pytest.main(
        [str(ROOT / "tests"), "--rootdir", str(ROOT), "-q",
         "-p", "anyio.pytest_plugin", "-p", "hypothesis.extra.pytestplugin",
         "-p", "pytest_timeout", *pytest_args],
        plugins=[Quarantine(enabled=not args.include_quarantined)],
    )


if __name__ == "__main__":
    sys.exit(main())
