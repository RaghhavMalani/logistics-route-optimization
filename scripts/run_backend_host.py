"""Single-process backend entry point for a persistent operating-system host.

No QA fixtures, explicit collection requests or modified collection clocks.
Windows Task Scheduler owns process lifetime; the application's scheduler owns
collection. Local status/control files are private host administration tools.
"""
from __future__ import annotations

import argparse
import json
import logging
import logging.config
import os
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class AlreadyRunning(RuntimeError):
    pass


@contextmanager
def exclusive_host(state: Path):
    """An OS-held lock survives stale files and releases on process death."""
    state.mkdir(parents=True, exist_ok=True)
    with (state / "backend-host.lock").open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise AlreadyRunning("Another managed backend holds this state's process lock") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def atomic_json(path: Path, value: dict):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temp.replace(path)


def now():
    # wall-clock: host uptime/status is operational receipt time, never replay.
    return datetime.now(timezone.utc).isoformat()


def run(args):
    root = Path(__file__).resolve().parents[1]
    state = Path(args.state_dir).resolve()
    os.chdir(root)
    dependencies = [str(root), *[str(Path(p).resolve()) for p in args.dependency_dir]]
    sys.path[:0] = dependencies
    # Pipeline refreshes spawn this Python executable; propagate the same
    # durable dependency paths instead of relying on the caller's shell.
    os.environ["PYTHONPATH"] = os.pathsep.join(dependencies)
    os.environ.update(PORTWATCH_STATE_DIR=str(state), PORTWATCH_IDENTITY_MODE="verified",
                      PORTWATCH_FRESHNESS_SCHEDULER="1", PORTWATCH_PUBLIC_PORT_AUTOREFRESH="1",
                      PORTWATCH_VESSELFINDER_ENABLED="0")
    # Host startup always uses the existing durable identity store, never QA.
    os.environ.pop("PORTWATCH_AUTH_DB", None)
    for key in list(os.environ):
        if key.startswith("PW_QA_"):
            os.environ.pop(key)
    folder = state / "backend_service"
    folder.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig({
        "version": 1, "disable_existing_loggers": False,
        "formatters": {"host": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
        "handlers": {"file": {"class": "logging.handlers.RotatingFileHandler",
            "filename": str(folder / "backend.log"), "encoding": "utf-8",
            "maxBytes": 5_000_000, "backupCount": 5, "formatter": "host"}},
        "root": {"level": "WARNING", "handlers": ["file"]},
        "loggers": {name: {"level": "INFO", "handlers": ["file"], "propagate": False}
            for name in ("portwatch.host", "portwatch.startup", "uvicorn.error",
                         "src.portwatch_os.freshness.coordinator")},
    })
    log = logging.getLogger("portwatch.host")
    try:
        with exclusive_host(state):
            import uvicorn
            from src.portwatch_os.clock import get_clock
            from src.portwatch_os.freshness import get_coordinator
            from src.portwatch_os.intelligence.public_collection import get_service

            run_id, started, pid = str(uuid.uuid4()), now(), os.getpid()
            server = uvicorn.Server(uvicorn.Config("backend.app.main:app", host=args.host,
                port=args.port, workers=1, reload=False, log_config=None, access_log=False))
            end = threading.Event()
            status_path, control_path = folder / "host-status.json", folder / "control.json"

            def write_status(stopped=False):
                coordinator = get_coordinator()
                jobs, collections = {}, {}
                for port in ("INPRT", "INMAA"):
                    artifact = "public_ports_" + port
                    if artifact in coordinator.artifacts():
                        jobs[port] = coordinator.describe(artifact)
                    receipt = get_service().collection_status(port, datetime.now(timezone.utc))
                    latest = receipt["lastRun"] or {}
                    collections[port] = {"lastSuccessfulCollectionAt": receipt["lastSuccessfulCollectionAt"],
                        "lastRunAt": latest.get("finishedAt"), "errors": latest.get("errors", [])}
                atomic_json(status_path, {"runId": run_id, "pid": pid, "startedAt": started,
                    "updatedAt": now(), "stateDir": str(state), "host": args.host, "port": args.port,
                    "serverReady": server.started and not stopped, "stopped": stopped,
                    "schedulerRunning": coordinator.running, "worldMode": get_clock().state.mode,
                    "vesselFinderEnabled": False, "jobs": jobs, "collections": collections})

            def observe():
                next_status = 0.0
                while not end.wait(1):
                    try:
                        if time.monotonic() >= next_status:
                            write_status()
                            next_status = time.monotonic() + 30
                        if control_path.exists():
                            command = json.loads(control_path.read_text(encoding="utf-8-sig"))
                            if command.get("runId") == run_id and command.get("action") == "stop":
                                log.info("Graceful host stop requested for %s", run_id)
                                server.should_exit = True
                    except Exception:
                        log.exception("Host status/control check failed")

            log.info("Starting backend run=%s pid=%s state=%s bind=%s:%s workers=1", run_id, pid, state, args.host, args.port)
            observer = threading.Thread(target=observe, name="backend-host-status", daemon=True)
            observer.start()
            try:
                server.run()
            finally:
                end.set()
                observer.join(timeout=10)
                write_status(stopped=True)
                log.info("Backend stopped run=%s", run_id)
            if not server.started:
                raise RuntimeError("Backend did not reach readiness")
    except AlreadyRunning:
        log.warning("A backend for this state is already running; duplicate entry point exits")
    except BaseException:
        log.exception("Backend host failed")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", default=str(Path(__file__).resolve().parents[1] / "outputs"))
    parser.add_argument("--dependency-dir", action="append", default=[])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
