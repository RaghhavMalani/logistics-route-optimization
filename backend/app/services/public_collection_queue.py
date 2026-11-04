"""Coalesce explicitly requested collection for public snapshot sources."""

import logging
from threading import Lock, Thread

log = logging.getLogger(__name__)
_lock = Lock()
_running: set[str] = set()


def active() -> list[str]:
    with _lock:
        return sorted(_running)


def enqueue(source, collect) -> None:
    with _lock:
        if source in _running:
            return
        _running.add(source)

    def run():
        try:
            collect()
        except Exception:
            log.exception("Public snapshot collection failed for %s", source)
        finally:
            with _lock:
                _running.discard(source)

    worker = Thread(target=run, name=f"public-collection-{source}", daemon=True)
    try:
        worker.start()
    except RuntimeError:
        with _lock:
            _running.discard(source)
        raise
