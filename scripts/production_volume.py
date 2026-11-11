"""Verify, back up and retain release state on the production volume."""

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from src.portwatch_os.state_capacity import require_capacity, state_capacity

BACKUP_ROOT = ".release-backups"
BACKUP_NAME = re.compile(r"20\d{6}-[a-z0-9-]{3,63}")
METADATA = {"manifest.json", "restore-state.py"}
KEEP = 2


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def state_files(root: Path) -> list[Path]:
    result = []
    for directory, folders, files in os.walk(root):
        folders[:] = [name for name in folders if name not in (BACKUP_ROOT, "backups")]
        for name in folders:
            if (Path(directory) / name).is_symlink():
                raise ValueError("State backup does not follow links")
        for name in files:
            if name.endswith(("-wal", "-shm", "-journal", ".tmp", ".lock")) or name == "collector-owner.json":
                continue
            path = Path(directory) / name
            if not path.is_file() or path.is_symlink():
                raise ValueError("State backup requires regular files")
            result.append(path)
    return sorted(result)


def copy_size(files: list[Path]) -> int:
    # Count a full copy. SQLite can incorporate live WAL pages into its copy.
    # Round small files up to a filesystem block and reserve metadata space.
    size = 1024 * 1024
    for path in files:
        wal = Path(f"{path}-wal")
        size += ((path.stat().st_size + 4095) // 4096 + 1) * 4096
        if wal.is_file():
            size += wal.stat().st_size
    return size


def backup_path(root: Path, name: str) -> Path:
    parent = root / BACKUP_ROOT
    target = parent / name
    if (not BACKUP_NAME.fullmatch(name) or parent.is_symlink() or target.is_symlink()
            or target.resolve().parent != parent.resolve()):
        raise ValueError("Invalid release backup path")
    return target


def file_receipt(root: Path, path: Path) -> dict:
    return {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)}


def verify_backup(path: Path) -> dict:
    for item in path.rglob("*"):
        if item.is_symlink():
            raise ValueError("Backup contains a symbolic link")
    files = [file_receipt(path, file) for file in sorted(path.rglob("*")) if file.is_file()]
    actual = {row["path"]: row for row in files}
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    declared = {row["path"]: row for row in manifest}
    if (not declared or len(declared) != len(manifest) or set(actual) != set(declared) | METADATA
            or set(declared) & METADATA):
        raise ValueError("Backup file list does not match its manifest")
    for name, row in declared.items():
        if any(row[key] != actual[name][key] for key in ("bytes", "sha256")):
            raise ValueError("Backup file hashes do not match its manifest")
    signature = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"name": path.name, "backup": str(path), "signature": signature, "files": files,
            "sqliteDatabases": sum(bool(row["sqlite"]) for row in manifest)}


def inventory(root: Path) -> dict:
    folder = root / BACKUP_ROOT
    if folder.is_symlink():
        raise ValueError("Release backup directory is a symbolic link")
    verified, unverified = [], []
    for entry in sorted(folder.iterdir()) if folder.is_dir() else []:
        if not BACKUP_NAME.fullmatch(entry.name) or not entry.is_dir() or entry.is_symlink():
            unverified.append(entry.name)
            continue
        try:
            verified.append(verify_backup(entry))
        except (OSError, ValueError, KeyError, TypeError):
            unverified.append(entry.name)
    return {"capacity": state_capacity(root), "verified": verified, "unverified": unverified}


def prune(root: Path, signatures: dict[str, str]) -> dict:
    before = inventory(root)
    older = before["verified"][:-KEEP]
    expected = {row["name"]: row["signature"] for row in older}
    if expected != signatures:
        raise ValueError("Retention candidates changed. Record the exact current file hashes before deleting")
    for name in signatures:
        shutil.rmtree(backup_path(root, name))
    return {"before": before["capacity"], "after": state_capacity(root), "deleted": list(signatures),
            "kept": [row["name"] for row in before["verified"][-KEEP:]], "unverified": before["unverified"]}


def backup(root: Path, name: str, restore_source: str) -> dict:
    destination = backup_path(root, name)
    if destination.exists():
        raise ValueError("Use a new release backup name")
    files = state_files(root)
    if not files or not restore_source:
        raise ValueError("Backup requires durable state and the restore program")
    size = copy_size(files)
    before = state_capacity(root)
    require_capacity(before, copy_bytes=size)
    destination.mkdir(parents=True)
    accepted = False
    databases = {}
    records = []
    try:
        for path in files:
            relative = path.relative_to(root)
            if relative.as_posix() in METADATA:
                raise ValueError("State file conflicts with backup metadata")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with path.open("rb") as stream:
                is_sqlite = stream.read(16) == b"SQLite format 3\x00"
            if is_sqlite:
                source = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
                databases[path] = (source, None)
                version = source.execute("PRAGMA data_version").fetchone()[0]
                databases[path] = (source, version)
                with closing(sqlite3.connect(target)) as copy:
                    source.backup(copy)
                    if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Copied SQLite database failed integrity check")
            else:
                shutil.copy2(path, target)
            records.append({**file_receipt(destination, target), "sqlite": is_sqlite})
        if files != state_files(root):
            raise ValueError("State file list changed during the backup")
        for path, (source, version) in databases.items():
            if source.execute("PRAGMA data_version").fetchone()[0] != version:
                raise ValueError(f"SQLite state changed during the backup: {path.relative_to(root)}")
        for row in records:
            if not row["sqlite"] and digest(root / row["path"]) != row["sha256"]:
                raise ValueError(f"State file changed during the backup: {row['path']}")
        (destination / "manifest.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        (destination / "restore-state.py").write_text(restore_source, encoding="utf-8")
        receipt = verify_backup(destination)
        after = state_capacity(root)
        require_capacity(after)
        accepted = True
        return {**receipt, "before": before, "after": after, "estimatedCopyBytes": size}
    finally:
        for source, _ in databases.values():
            source.close()
        if not accepted:
            shutil.rmtree(backup_path(root, name))


def main(argv=None, *, restore_source=""):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inventory", "prune", "backup", "deploy-check"))
    parser.add_argument("--name")
    parser.add_argument("--signatures", type=json.loads, default={})
    parser.add_argument("--signature")
    args = parser.parse_args(argv)
    root = Path("/app/state").resolve()
    if not root.is_mount():
        raise ValueError("The production state volume is not mounted at /app/state")
    os.umask(0o077)
    if args.action == "inventory":
        result = inventory(root)
    elif args.action == "prune":
        result = prune(root, args.signatures)
    elif args.action == "backup":
        result = backup(root, args.name or "", restore_source)
    else:
        state = inventory(root)
        verified = state["verified"]
        if not verified or len(verified) > KEEP:
            raise ValueError("Verify the new backup and apply the two-set retention rule before deployment")
        latest = verified[-1]
        if latest["name"] != args.name or latest["signature"] != args.signature:
            raise ValueError("Backup differs from the verified release receipt")
        capacity = state["capacity"]
        require_capacity(capacity)
        result = {"backup": latest["backup"], "signature": latest["signature"], "capacity": capacity}
    print(json.dumps(result, separators=(",", ":")))
