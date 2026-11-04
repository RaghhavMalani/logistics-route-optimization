"""Run the API and terminal together in a foreground development session."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = ROOT / "india-portwatch-terminal"
STATE = ROOT / "work" / "dev" / "state"
API_PORT = 9304
WEB_PORT = 4265
API = f"http://127.0.0.1:{API_PORT}/api"
WEB = f"http://127.0.0.1:{WEB_PORT}"


def wait_ready(processes: list[subprocess.Popen]) -> None:
    deadline = monotonic() + 90
    while monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise RuntimeError("A development server exited. See its output above.")
        try:
            with urlopen(API + "/health", timeout=2) as health:
                ready = json.load(health)["status"] == "ok"
            if ready:
                with urlopen(WEB + "/login", timeout=2) as terminal:
                    if terminal.status == 200:
                        return
        except (URLError, OSError, ValueError, KeyError):
            pass
        sleep(0.4)
    raise RuntimeError("The development stack did not become ready within 90 seconds.")


def main() -> None:
    node = shutil.which("node")
    vite = TERMINAL / "node_modules" / "vite" / "bin" / "vite.js"
    if not node or not vite.is_file():
        raise SystemExit("Install Node and run npm --prefix india-portwatch-terminal ci first.")

    env = os.environ.copy()
    for name, value in {
        "PORTWATCH_STATE_DIR": str(STATE),
        "PORTWATCH_LICENCE_MODE": "DEMO",
        "PORTWATCH_IDENTITY_MODE": "verified",
        "PORTWATCH_FRESHNESS_SCHEDULER": "0",
        "PORTWATCH_INTELLIGENCE_RECONCILIATION": "0",
        "PORTWATCH_WEATHER_RECONCILIATION": "0",
    }.items():
        env.setdefault(name, value)
    if not (ROOT / "data" / "cache" / "port_state.json").is_file():
        subprocess.run(
            [sys.executable, "run_award_demo.py", "--source", "sample", "--model", "baseline", "--offline"],
            cwd=ROOT,
            env=env,
            check=True,
        )

    processes: list[subprocess.Popen] = []
    try:
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
            cwd=ROOT,
            env=env,
        ))
        processes.append(subprocess.Popen(
            [node, str(vite), "--host", "127.0.0.1", "--port", str(WEB_PORT), "--strictPort"],
            cwd=TERMINAL,
            env={**env, "VITE_PORTWATCH_API_BASE": API, "VITE_PORTWATCH_AUTH_MODE": "demo"},
        ))
        wait_ready(processes)
        print(f"READY · open {WEB}/login", flush=True)
        while all(process.poll() is None for process in processes):
            sleep(0.5)
        raise RuntimeError("A development server exited.")
    except KeyboardInterrupt:
        pass
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
