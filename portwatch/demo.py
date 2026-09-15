"""One command that starts PortWatch and says what it started.

    python -m portwatch.demo start              validate, refresh, start, verify, report
    python -m portwatch.demo doctor             validate and report; start nothing
    python -m portwatch.demo status             ask a running deployment the same questions
    python -m portwatch.demo stop               stop what `start --detach` left running

``start`` refuses to run on a misleading configuration -- a licence mode that
was never stated, a key for a product the mode may not use, a register so
old the world would be empty -- and refuses to *pretend*: every signal is
printed with the mode it is actually in, and a feed that has delivered no
observation is not called live because a key exists.

The command does what an operator used to do from memory: it asks the
freshness coordinator which artifacts are missing or lapsed and refreshes
them before the backend comes up, so the first screen a buyer sees is a
world with something live in it. No pipeline command has to be known.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = ROOT / "india-portwatch-terminal"
RUN_DIR = ROOT / ".portwatch"
RUN_FILE = RUN_DIR / "run.json"
LOG_DIR = RUN_DIR / "logs"

sys.path.insert(0, str(ROOT))

HEADERS = {"Accept": "application/json", "X-PortWatch-Actor": "portwatch.demo", "X-PortWatch-Role": "NATIONAL_ADMIN"}

OK, WARN, FAIL = "OK", "WARN", "FAIL"


class DemoError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# printing
# --------------------------------------------------------------------------


def say(text: str = "") -> None:
    print(text, flush=True)


def row(label: str, state: str, detail: str = "") -> None:
    say(f"  {label.ljust(16)} {state.ljust(18)} {detail}")


def hours(seconds: Optional[float]) -> str:
    if seconds is None:
        return "never"
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 3 * 3600:
        return f"{seconds / 60:.0f} min"
    if seconds < 3 * 86400:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} d"


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


def get(base: str, path: str, *, timeout: float = 20.0, params: Optional[Dict[str, str]] = None,
        html: bool = False) -> Any:
    query = "&".join(f"{k}={v}" for k, v in (params or {}).items())
    url = f"{base.rstrip('/')}{path}" + (f"?{query}" if query else "")
    headers = {**HEADERS, "Accept": "text/html"} if html else HEADERS
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", "replace")
        return raw if html else json.loads(raw)


def wait_for(base: str, path: str, *, timeout: float, label: str, html: bool = False) -> Any:
    deadline = time.monotonic() + timeout
    last: Optional[str] = None
    while time.monotonic() < deadline:
        try:
            return get(base, path, timeout=5.0, html=html)
        except urllib.error.HTTPError as exc:
            body = " ".join(exc.read().decode("utf-8", "replace")[:300].split())
            last = f"HTTP {exc.code}: {body}"
            if 200 <= exc.code < 500 and exc.code != 404:
                return None
        except Exception as exc:  # noqa: BLE001 - not up yet
            last = f"{type(exc).__name__}"
        time.sleep(1.0)
    raise DemoError(f"{label} did not answer at {base}{path} within {timeout:.0f}s ({last})")


# --------------------------------------------------------------------------
# environment
# --------------------------------------------------------------------------


def resolve_mode(argument: Optional[str]) -> str:
    from src.portwatch_os.deployment import resolve_mode as _resolve

    mode, source, problem = _resolve(argument)
    if problem:
        raise DemoError(problem)
    say(f"  licence mode     {mode.ljust(18)} from {source}")
    return mode


def check_runtime(*, terminal: bool) -> List[str]:
    problems: List[str] = []
    if sys.version_info < (3, 11):
        problems.append(f"Python {sys.version.split()[0]}; 3.11 or newer is required")
    for module in ("fastapi", "uvicorn", "pandas", "numpy"):
        try:
            __import__(module)
        except ImportError:
            problems.append(f"python package '{module}' is not installed (pip install -r requirements.txt)")
    if terminal:
        if shutil.which("npm") is None:
            problems.append("npm is not on PATH; the terminal cannot be started (use --no-terminal for the API alone)")
        if not (TERMINAL / "node_modules").exists():
            problems.append(f"{TERMINAL / 'node_modules'} is missing; run `npm ci` in india-portwatch-terminal")
    return problems


def preflight(mode: str) -> Any:
    """Validate with the mode already in the environment, so children inherit the same answer."""
    from src.portwatch_os.deployment import validate

    os.environ["PORTWATCH_LICENCE_MODE"] = mode
    return validate()


def print_report(report: Any) -> None:
    for check in report.checks:
        mark = {"PASS": "ok  ", "WARN": "warn", "FAIL": "FAIL", "SKIP": "skip"}[check.status]
        say(f"  [{mark}] {check.name.ljust(26)} {check.detail}")


# --------------------------------------------------------------------------
# caches
# --------------------------------------------------------------------------


def refresh_caches(*, run_pipeline: bool, allow_network: bool) -> None:
    """Bring every missing or lapsed artifact within policy before starting."""
    from src.portwatch_os.freshness import get_coordinator
    from src.portwatch_os.freshness.jobs import install_product_jobs

    coordinator = install_product_jobs(get_coordinator())
    status = {r["artifact"]: r for r in coordinator.status()["artifacts"]}

    def needs(artifact: str) -> bool:
        return status[artifact]["state"] in ("MISSING", "DUE", "EXPIRED", "STALE")

    if needs("port_forecast") and (status["port_forecast"]["state"] == "MISSING" or run_pipeline):
        say("  port forecast    generating         the pipeline takes about two minutes on first run")
        outcome = coordinator.request("port_forecast", reason="demo start", wait=True, requested=True)
        result = coordinator.record("port_forecast").last_result
        if outcome != "started" or result is None or not result.ok:
            raise DemoError(f"the pipeline did not produce the port forecasts: {outcome}; "
                            f"{result.error if result else 'no result'}")
    elif needs("port_forecast"):
        say(f"  port forecast    {status['port_forecast']['state'].lower().ljust(18)} "
            f"{hours(status['port_forecast']['ageSeconds'])} old; served as last known good, refreshed by the scheduler")

    for artifact in ("events", "marine"):
        state = status[artifact]
        if state["state"] in ("NOT_APPLICABLE", "SIMULATED"):
            continue
        label = artifact.replace("_", " ")
        if not needs(artifact):
            row(label, state["state"].lower(), f"{hours(state['ageSeconds'])} old")
            continue
        if not allow_network:
            row(label, state["state"].lower(), f"{hours(state['ageSeconds'])} old; --offline, not refreshed")
            continue
        row(label, "refreshing", f"was {state['state'].lower()}, {hours(state['ageSeconds'])} old")
        outcome = coordinator.request(artifact, reason="demo start", wait=True, requested=True)
        result = coordinator.record(artifact).last_result
        if result is not None and not result.ok:
            row(label, "refresh failed", f"{result.error}; the last known good stays in place")
        elif result is not None:
            row(label, "refreshed", json.dumps(result.detail))


# --------------------------------------------------------------------------
# processes
# --------------------------------------------------------------------------


def _spawn(command: Sequence[str], *, cwd: Path, env: Dict[str, str], log: Path) -> subprocess.Popen:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handle = open(log, "ab")  # noqa: SIM115 - the child owns it
    kwargs: Dict[str, Any] = {"cwd": str(cwd), "env": env, "stdout": handle, "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        kwargs["shell"] = True
        return subprocess.Popen(" ".join(command), **kwargs)
    kwargs["start_new_session"] = True
    return subprocess.Popen(list(command), **kwargs)


def _terminate(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
        else:
            os.killpg(pid, signal.SIGTERM)
    except Exception:  # noqa: BLE001 - already gone
        pass


def start_backend(mode: str, port: int, env: Dict[str, str]) -> subprocess.Popen:
    command = [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(port)]
    return _spawn(command, cwd=ROOT, env=env, log=LOG_DIR / "api.log")


def start_terminal(port: int, api_base: str, env: Dict[str, str]) -> subprocess.Popen:
    env = {**env, "VITE_PORTWATCH_API_BASE": api_base}
    npm = shutil.which("npm") or "npm"
    command = [npm, "run", "dev", "--", "--port", str(port), "--host", "127.0.0.1"]
    return _spawn(command, cwd=TERMINAL, env=env, log=LOG_DIR / "terminal.log")


# --------------------------------------------------------------------------
# the report
# --------------------------------------------------------------------------


def report(api: str, *, terminal_url: Optional[str], mode: str) -> bool:
    """Print the mode of every important signal. Returns False on a misleading state."""
    misleading: List[str] = []

    health = get(api, "/health")
    clock = health.get("worldClock") or {}
    row("WORLD", "READY" if health.get("status") == "ok" else "DEGRADED",
        f"clock {clock.get('mode', '?')}; intelligence {health.get('intelligence')}; "
        f"{len(health.get('availablePorts') or [])} ports")

    freshness = {r["artifact"]: r for r in get(api, "/admin/freshness")["artifacts"]}

    def fresh_row(label: str, artifact: str, extra: str = "") -> None:
        r = freshness[artifact]
        detail = f"age {hours(r['ageSeconds'])}"
        if r.get("sourceLagSeconds"):
            detail += f"; source lag {hours(r['sourceLagSeconds'])}"
        if r["job"]["state"] not in ("IDLE", "DISABLED"):
            detail += f"; job {r['job']['state']}"
        if r["job"]["lastResult"] and not r["job"]["lastResult"]["ok"]:
            detail += f"; last refresh failed: {r['job']['lastResult']['error']}"
        row(label, r["state"], (detail + (f"; {extra}" if extra else "")).strip())

    fresh_row("EVENTS", "events", f"{freshness['events']['detail'].get('events', '?')} events")
    fresh_row("MARINE", "marine", f"{freshness['marine']['detail'].get('cells', 0)} cells")

    fabric = get(api, "/fabric/health", params={"mode": mode})
    traffic = fabric["traffic"]
    traffic_health = traffic.get("health") or {}
    if traffic["mode"] == "LIVE_AIS" and not traffic_health.get("lastGoodObservationAt"):
        misleading.append("traffic claims LIVE_AIS with no valid observation on record")
    row("AIS", traffic["mode"], traffic.get("statement", ""))

    fresh_row("PORT FORECAST", "port_forecast",
              f"{freshness['port_forecast']['detail'].get('model')}; origin {freshness['port_forecast']['detail'].get('forecastOriginStatus')}")

    actions = get(api, "/decisions/actions")
    critic = actions.get("critic") or {}
    row("DECISION ENGINE", "READY",
        f"{len(actions.get('actions') or [])} catalogue actions; Critic runs {len(critic.get('checks') or [])} checks")

    missions = get(api, "/missions")
    names = [m.get("name", m.get("missionId")) for m in (missions.get("missions") or [])]
    row("MISSION ENGINE", "READY", f"{len(names)} missions: " + "; ".join(str(n)[:40] for n in names))

    for signal_ in fabric.get("signals", []):
        cap = signal_.get("capability", "?")
        if cap in ("ais",):
            continue
        row(f"  {cap[:14]}", str(signal_.get("mode") or signal_.get("availability", {}).get("status") or "?"),
            f"{signal_.get('productId')}; commercial {signal_.get('commercialUse')}")

    if terminal_url:
        row("TERMINAL", "READY", terminal_url)

    readiness = get(api, "/admin/readiness", params={"mode": mode})
    for name in readiness.get("refusals", []):
        misleading.append(f"readiness refused: {name}")
    if misleading:
        say("")
        say("  REFUSED -- this configuration would mislead:")
        for item in misleading:
            say(f"    - {item}")
        return False
    return True


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    say("PortWatch doctor")
    try:
        mode = resolve_mode(args.mode)
    except DemoError as exc:
        say(f"  [FAIL] licence_mode              {exc}")
        return 2
    os.environ["PORTWATCH_LICENCE_MODE"] = mode
    problems = check_runtime(terminal=not args.no_terminal)
    for problem in problems:
        say(f"  [FAIL] runtime                   {problem}")
    report_ = preflight(mode)
    print_report(report_)
    say("")
    say("  READY" if report_.ready and not problems else "  NOT READY")
    return 0 if report_.ready and not problems else 2


def cmd_start(args: argparse.Namespace) -> int:
    say("PortWatch start")
    try:
        mode = resolve_mode(args.mode)
    except DemoError as exc:
        say(f"  [FAIL] licence_mode              {exc}")
        return 2
    os.environ["PORTWATCH_LICENCE_MODE"] = mode
    problems = check_runtime(terminal=not args.no_terminal)
    if problems:
        for problem in problems:
            say(f"  [FAIL] runtime                   {problem}")
        return 2

    say("")
    say("Configuration")
    pre = preflight(mode)
    print_report(pre)
    blocking = [c for c in pre.refusals if not c.name.startswith("freshness:")]
    if blocking:
        say("")
        say("  REFUSED -- fix the configuration above; nothing was started.")
        return 2

    say("")
    say("Caches")
    refresh_caches(run_pipeline=args.pipeline, allow_network=not args.offline)

    env = {**os.environ, "PORTWATCH_LICENCE_MODE": mode}
    api = f"http://127.0.0.1:{args.api_port}/api"
    terminal_url = None if args.no_terminal else f"http://127.0.0.1:{args.terminal_port}"
    children: Dict[str, subprocess.Popen] = {}

    def stop_all() -> None:
        for name, child in children.items():
            _terminate(child.pid)
        RUN_FILE.unlink(missing_ok=True)

    say("")
    say("Services")
    try:
        children["api"] = start_backend(mode, args.api_port, env)
        wait_for(api, "/health", timeout=args.timeout, label="the backend")
        row("backend", "UP", f"{api}  (log: {LOG_DIR / 'api.log'})")
        if terminal_url:
            children["terminal"] = start_terminal(args.terminal_port, api, env)
            wait_for(terminal_url, "/login", timeout=args.timeout, label="the terminal", html=True)
            row("terminal", "UP", f"{terminal_url}  (log: {LOG_DIR / 'terminal.log'})")

        say("")
        say("Signals")
        honest = report(api, terminal_url=terminal_url, mode=mode)
        if not honest:
            stop_all()
            return 2
    except DemoError as exc:
        say(f"  [FAIL] {exc}")
        stop_all()
        return 1
    except KeyboardInterrupt:
        stop_all()
        return 130

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    RUN_FILE.write_text(json.dumps({
        "mode": mode, "api": api, "terminal": terminal_url,
        "pids": {name: child.pid for name, child in children.items()},
    }, indent=2), encoding="utf-8")

    say("")
    say(f"  Sign in at {terminal_url or api}  --  admin@portwatch.demo for National Command.")
    if args.detach:
        say(f"  Running detached; `python -m portwatch.demo stop` ends it. ({RUN_FILE})")
        return 0
    say("  Ctrl+C stops everything.")
    try:
        while True:
            for name, child in children.items():
                if child.poll() is not None:
                    say(f"  [FAIL] {name} exited with {child.returncode}; see {LOG_DIR / (name + '.log')}")
                    stop_all()
                    return 1
            time.sleep(2.0)
    except KeyboardInterrupt:
        say("  stopping")
        stop_all()
        return 0


def cmd_status(args: argparse.Namespace) -> int:
    api = args.api or f"http://127.0.0.1:{args.api_port}/api"
    mode = args.mode or os.getenv("PORTWATCH_LICENCE_MODE") or "DEMO"
    say(f"PortWatch status ({api})")
    try:
        honest = report(api, terminal_url=None, mode=mode)
    except Exception as exc:  # noqa: BLE001
        say(f"  [FAIL] {type(exc).__name__}: {exc}")
        return 1
    return 0 if honest else 2


def cmd_stop(_: argparse.Namespace) -> int:
    if not RUN_FILE.exists():
        say("nothing recorded as running")
        return 0
    state = json.loads(RUN_FILE.read_text(encoding="utf-8"))
    for name, pid in (state.get("pids") or {}).items():
        _terminate(int(pid))
        say(f"  stopped {name} ({pid})")
    RUN_FILE.unlink(missing_ok=True)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m portwatch.demo", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--mode", default=None, help="RESEARCH | DEMO | COMMERCIAL | GOVERNMENT (else PORTWATCH_LICENCE_MODE)")
        p.add_argument("--api-port", type=int, default=8000)
        p.add_argument("--no-terminal", action="store_true", help="start the API only")

    start = sub.add_parser("start", help="validate, refresh, start, verify, report")
    common(start)
    start.add_argument("--terminal-port", type=int, default=8080)
    start.add_argument("--pipeline", action="store_true", help="run the two-minute pipeline even when a forecast exists")
    start.add_argument("--offline", action="store_true", help="do not refresh anything over the network")
    start.add_argument("--timeout", type=float, default=240.0, help="seconds to wait for each service")
    start.add_argument("--detach", action="store_true", help="leave the services running and return")
    start.set_defaults(fn=cmd_start)

    doctor = sub.add_parser("doctor", help="validate the configuration; start nothing")
    common(doctor)
    doctor.set_defaults(fn=cmd_doctor)

    status = sub.add_parser("status", help="ask a running deployment")
    common(status)
    status.add_argument("--api", default=None, help="base URL, default http://127.0.0.1:<api-port>/api")
    status.set_defaults(fn=cmd_status)

    stop = sub.add_parser("stop", help="stop a detached deployment")
    stop.set_defaults(fn=cmd_stop)

    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
