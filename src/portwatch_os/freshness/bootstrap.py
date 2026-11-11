"""Seed rebuildable files onto a persistent root without replacing retained data."""
from pathlib import Path
import os
import shutil
import tempfile


def seed_missing(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or not source.is_dir():
        return 0
    if destination.is_relative_to(source):
        raise ValueError('Persistent destination must be outside its packaged seed')
    copied = 0
    for item in source.rglob('*'):
        if not item.is_file() or item.is_symlink():
            continue
        target = destination / item.relative_to(source)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(dir=target.parent, prefix='.seed-')
        os.close(handle)
        try:
            shutil.copyfile(item, name)
            try:
                os.link(name, target)
                copied += 1
            except FileExistsError:
                pass
        finally:
            Path(name).unlink(missing_ok=True)
    return copied


def initialize():
    from src.utils.config import PROJECT_ROOT, DATA_DIR, CACHE_DIR, OUTPUTS_DIR
    return {'dataFiles': seed_missing(PROJECT_ROOT / 'data', DATA_DIR),
            'cacheFiles': seed_missing(PROJECT_ROOT / 'data/cache', CACHE_DIR),
            'outputFiles': seed_missing(PROJECT_ROOT / 'outputs', OUTPUTS_DIR)}


if __name__ == '__main__':
    print(initialize())
