"""Restore a verified release backup on its own volume with API workers stopped."""

import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path


def main():
    root = Path("/app/state")
    backup = Path(__file__).resolve().parent
    if not root.is_mount() or backup.parent != root / ".release-backups":
        raise ValueError("Run this program from its backup folder on the production volume")
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            command = (proc / "cmdline").read_bytes().split(b"\0")
        except (OSError, PermissionError):
            continue
        if command and any(b"uvicorn" in arg for arg in command[:3]):
            raise ValueError("Stop the application workers before restoring state")

    records = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    for row in records:
        relative = Path(row["path"])
        source = backup / relative
        if relative.is_absolute() or ".." in relative.parts or source.resolve() != source:
            raise ValueError("Invalid path in backup manifest")
        with source.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if source.stat().st_size != row["bytes"] or actual != row["sha256"]:
            raise ValueError("Backup hash verification failed")
        if row["sqlite"]:
            with closing(sqlite3.connect(source.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup SQLite integrity check failed")

    preserved = root / "backups" / ("before-restore-" + backup.name)
    if preserved.exists() or preserved.parent.is_symlink():
        raise ValueError("Pre-restore state already exists or its path is unsafe")
    if shutil.disk_usage(root).free < sum(row["bytes"] for row in records):
        raise ValueError("The volume lacks room to restore while preserving the current state")
    for directory, folders, files in os.walk(root):
        folders[:] = [name for name in folders if name not in (".release-backups", "backups")]
        for name in files:
            path = Path(directory) / name
            target = preserved / path.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            path.rename(target)
    for row in records:
        relative = Path(row["path"])
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup / relative, target)
    print(json.dumps({"status": "restored", "files": len(records), "previousState": str(preserved)}))


if __name__ == "__main__":
    main()
