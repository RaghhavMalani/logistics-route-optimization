"""The failure demo: three things a buyer will ask about, made to fail for real.

    python scripts/demo_failure.py [--api URL] [--mode DEMO] [--ports 8011,8012]

Each scenario starts its own throwaway API on a spare port and reads back what
the product says through the same routes the terminal reads. Nothing is mocked
and no timestamp is edited: the failures are produced by the configuration a
real deployment could have.

  1. AIS unavailable       RESEARCH mode with an invalid AISStream credential.
                           The socket is refused; the chart must say
                           UNAVAILABLE and never fall back to the replay.
  2. Financial rate missing  The default: no charter rate is configured. The
                           financial twin must say "unknown", never zero, and
                           refuse a total.
  3. Marine stale / missing  A deployment whose marine grid was never fetched and
                           whose fetch cannot reach the provider. Freshness must
                           say MISSING with the reason, readiness must refuse,
                           the refresh must fail visibly with bounded backoff, and
                           a decision must still compute with the weather marked
                           unavailable rather than filled in.

The scenarios are printed as the product's own words. A scenario that does
not fail the way it should is reported as such and the script exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ADMIN = {"X-PortWatch-Actor": "failure-demo", "X-PortWatch-Role": "NATIONAL_ADMIN"}
COMPANY = {"X-PortWatch-Actor": "failure-demo.ops", "X-PortWatch-Role": "SHIPPING_COMPANY",
           "X-PortWatch-Company": "PWD"}

problems: list[str] = []


def say(text: str = "") -> None:
    print(text, flush=True)


def fail(text: str) -> None:
    problems.append(text)
    say(f"  !! {text}")


# --------------------------------------------------------------------------
# the throwaway API
# --------------------------------------------------------------------------


class Api:
    def __init__(self, base: str) -> None:
        self.base = base

    def call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None,
             headers: Optional[Dict[str, str]] = None, timeout: float = 120) -> Tuple[int, Any]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, json.loads(response.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8") or "null")
            except Exception:  # noqa: BLE001
                return exc.code, None

    def get(self, path: str, headers: Optional[Dict[str, str]] = None) -> Tuple[int, Any]:
        return self.call("GET", path, headers=headers)

    def post(self, path: str, body: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Tuple[int, Any]:
        return self.call("POST", path, body=body, headers=headers)


def start_api(port: int, env: Dict[str, str], cwd: Path, log: Path) -> subprocess.Popen:
    command = [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1",
               "--port", str(port), "--log-level", "warning"]
    merged = {**os.environ, **env, "PYTHONPATH": str(ROOT), "PORTWATCH_FRESHNESS_SCHEDULER": "0"}
    handle = log.open("ab")
    kwargs: Dict[str, Any] = {"cwd": str(cwd), "env": merged, "stdout": handle, "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(command, **kwargs)


def wait_ready(api: Api, timeout: float = 120) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, body = api.get("/health")
            if status == 200 and body:
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.0)
    return False


def stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()


# --------------------------------------------------------------------------
# 1. AIS unavailable
# --------------------------------------------------------------------------


def scenario_ais(port: int, log_dir: Path) -> None:
    say("1. AIS UNAVAILABLE -- RESEARCH mode, an AISStream credential the service refuses")
    say("   configuration: PORTWATCH_LICENCE_MODE=RESEARCH AISSTREAM_API_KEY=<invalid>")
    env = {"PORTWATCH_LICENCE_MODE": "RESEARCH",
           "AISSTREAM_API_KEY": "invalid-credential-for-the-failure-demo"}
    process = start_api(port, env, ROOT, log_dir / "ais.log")
    api = Api(f"http://127.0.0.1:{port}/api")
    try:
        if not wait_ready(api):
            fail("the API did not come up")
            return
        # The socket is refused within a few seconds; give the state machine time to say so.
        traffic: Dict[str, Any] = {}
        for _ in range(30):
            status, body = api.get("/fabric/health?mode=RESEARCH")
            traffic = (body or {}).get("traffic") or {}
            if status == 200 and traffic.get("health", {}).get("health") == "AUTH_FAILED":
                break
            time.sleep(1.0)
        say(f"   /fabric/health traffic.mode      {traffic.get('mode')}")
        say(f"   /fabric/health traffic.statement {traffic.get('statement')}")
        say(f"   /fabric/health traffic.health    {traffic.get('health', {}).get('health')}"
            f" -- {traffic.get('health', {}).get('lastError')}")
        if traffic.get("mode") != "UNAVAILABLE":
            fail(f"traffic is {traffic.get('mode')}, not UNAVAILABLE")
        if traffic.get("providerId") == "ais-replay":
            fail("the replay was substituted for the refused feed")

        status, lens = api.get("/security/lens?mode=RESEARCH", headers=ADMIN)
        say(f"   /security/lens status            {lens.get('status')}")
        say(f"   /security/lens reason            {lens.get('reason')}")
        if lens.get("status") != "SECURITY ANALYTICS UNAVAILABLE":
            fail("security analytics ran without observed AIS")

        status, ready = api.get("/admin/readiness?mode=RESEARCH", headers=ADMIN)
        checks = {c["name"]: c for c in (ready or {}).get("checks", [])}
        honesty = checks.get("traffic_honesty", {})
        say(f"   /admin/readiness ready           {ready.get('ready')}")
        say(f"   /admin/readiness traffic_honesty {honesty.get('status')}: {honesty.get('detail')}")
        for refusal in (ready or {}).get("refusals", []):
            say(f"   /admin/readiness refusal         {refusal}")

        status, health = api.get("/health")
        say(f"   /health licenceMode              {health.get('licenceMode', {}).get('mode')}"
            f" ({health.get('licenceMode', {}).get('source')})")

        status, attention = api.get("/attention?mode=RESEARCH&limit=25", headers=ADMIN)
        items = (attention or {}).get("items", []) if status == 200 else []
        vessels = [i for i in items if i.get("subjectType") == "vessel"]
        sources = sorted({i.get("source") for i in vessels})
        say(f"   /attention                       HTTP {status}; traffic {(attention or {}).get('traffic')};"
            f" observed {(attention or {}).get('observed')}; {len(vessels)} vessel subjects, source {sources}")
        # The company's own fleet register (planned passages) may be ranked;
        # nothing may be ranked as observed when no source observed it.
        if (attention or {}).get("observed"):
            fail("attention counts observed hulls with no source delivering")
        if any(i.get("source") not in ("FLEET",) for i in vessels):
            fail(f"attention ranks vessels from {sources}, not the fleet register alone")
    finally:
        stop(process)
    say()


def first_vessel_problem(api: Api, mode: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]:
    """The first actionable hull in the attention queue and the decision computed on it."""
    status, attention = api.get(f"/attention?mode={mode}&limit=25", headers=ADMIN)
    if status != 200:
        return None, None, f"attention HTTP {status}"
    item = next((i for i in attention.get("items", []) if i.get("subjectType") == "vessel" and i.get("actionable")), None)
    if item is None:
        return None, None, "no actionable hull in the register at this instant"
    event_id = item["cascadeId"].split(":")[-1]
    status, problem = api.post("/decisions/problems", {
        "domain": "vessel", "eventId": event_id, "vesselId": item["subjectId"],
        "attentionId": item["attentionId"], "mode": mode,
    }, headers=COMPANY)
    if status != 200:
        return item, None, f"decision HTTP {status}: {problem}"
    return item, problem, ""


def recommended(problem: Dict[str, Any]) -> Dict[str, Any]:
    rec = problem.get("recommendation") or {}
    return next((o for o in problem["options"] if o["optionId"] == rec.get("optionId")), problem["options"][0])


# --------------------------------------------------------------------------
# 2. financial rate missing
# --------------------------------------------------------------------------


def scenario_finance(api: Api, mode: str) -> None:
    say("2. FINANCIAL RATE MISSING -- the running deployment, no charter rate configured")
    status, basis = api.get("/finance/basis")
    if status == 200 and isinstance(basis, dict):
        rates = basis.get("rates") or []
        charter = [r for r in rates if "charter" in str(r.get("primitive", "")).lower()]
        say(f"   /finance/basis rates             {len(rates)} configured, {len(charter)} of them a charter rate")
        say(f"   /finance/basis note              {basis.get('note')}")
    item, problem, why = first_vessel_problem(api, mode)
    if problem is None:
        fail(why)
        return
    option = recommended(problem)
    fin = (option.get("evaluation") or {}).get("financial") or {}
    say(f"   decision {problem['decisionId']} on {item['subjectId']}; option: {option.get('label')}")
    say(f"   total                            {fin.get('total')!r}; complete {fin.get('complete')}")
    for component in fin.get("components", []):
        say(f"   {component['label']:<32} {component['state']:<8} {component.get('reason') or component.get('basis') or ''}")
    unknown = [c for c in fin.get("components", []) if c.get("state") == "UNKNOWN"]
    delay = next((c for c in fin.get("components", []) if c.get("key") == "delay"), {})
    if not unknown:
        fail("no component is UNKNOWN although no rate is configured")
    if delay.get("state") != "UNKNOWN" or delay.get("money") is not None:
        fail(f"the cost of delay is {delay.get('state')} at {delay.get('money')} without a configured rate")
    if fin.get("total") is not None and unknown:
        fail("a total was produced with unknown components")
    if fin.get("complete"):
        fail("the financial view calls itself complete with unknown components")
    say()


# --------------------------------------------------------------------------
# 3. marine missing and unreachable
# --------------------------------------------------------------------------


def scenario_marine(port: int, log_dir: Path) -> None:
    say("3. MARINE MISSING / UNREACHABLE -- DEMO mode, no marine grid ever fetched, provider unreachable")
    say("   configuration: an empty working directory (no data/cache/marine_forecast.json) and")
    say("   HTTPS_PROXY pointing at a closed port, so the fetch cannot reach Open-Meteo")
    scratch = Path(tempfile.mkdtemp(prefix="portwatch-marine-"))
    env = {"PORTWATCH_LICENCE_MODE": "DEMO",
           "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "NO_PROXY": "127.0.0.1"}
    process = start_api(port, env, scratch, log_dir / "marine.log")
    api = Api(f"http://127.0.0.1:{port}/api")
    try:
        if not wait_ready(api):
            fail("the API did not come up")
            return
        status, fresh = api.get("/admin/freshness", headers=ADMIN)
        rows = {r["artifact"]: r for r in (fresh or {}).get("artifacts", [])}
        marine = rows.get("marine", {})
        say(f"   /admin/freshness marine.state    {marine.get('state')} -- {marine.get('reason')}")
        if marine.get("state") != "MISSING":
            fail(f"marine is {marine.get('state')}, not MISSING")

        status, ready = api.get("/admin/readiness?mode=DEMO", headers=ADMIN)
        checks = {c["name"]: c for c in (ready or {}).get("checks", [])}
        check = checks.get("freshness:marine", {})
        say(f"   /admin/readiness ready           {ready.get('ready')}")
        say(f"   /admin/readiness freshness:marine {check.get('status')}: {check.get('detail')}")
        if ready.get("ready"):
            fail("readiness passed with the marine grid missing")

        status, result = api.post("/admin/freshness/marine/refresh?wait=true", {}, headers=ADMIN)
        job = (result or {}).get("job") or {}
        last = job.get("lastResult") or {}
        say(f"   POST /admin/freshness/marine/refresh?wait=true  HTTP {status}; outcome {result.get('outcome')}")
        say(f"   job state / attempts / next     {job.get('state')} / {job.get('attemptsThisCycle')} / {job.get('nextAttemptAt')}")
        say(f"   last result                      ok={last.get('ok')} attempt {last.get('attempt')} -- {last.get('error') or last.get('detail')}")
        if last.get("ok") or last.get("observedAt"):
            fail("a refresh that could not reach the provider reported success")
        if job.get("state") not in ("FAILED", "RETRY_SCHEDULED"):
            fail(f"the failed refresh left the job {job.get('state')}, not FAILED or RETRY_SCHEDULED")
        if job.get("state") == "RETRY_SCHEDULED" and not job.get("nextAttemptAt"):
            fail("a retry is scheduled with no stated instant")

        status, fresh = api.get("/admin/freshness", headers=ADMIN)
        rows = {r["artifact"]: r for r in (fresh or {}).get("artifacts", [])}
        marine = rows.get("marine", {})
        say(f"   /admin/freshness marine after    {marine.get('state')}; observedAt {marine.get('observedAt')}")
        if marine.get("observedAt"):
            fail("a failed refresh produced an observation timestamp")

        status, health = api.get("/fabric/health?mode=DEMO")
        signal = next((s for s in (health or {}).get("signals", []) if s.get("capability") == "marine"), {})
        say(f"   /fabric/health marine            freshness {signal.get('freshness')};"
            f" availability {signal.get('availability', {}).get('status')}")

        item, problem, why = first_vessel_problem(api, "DEMO")
        if problem is None:
            fail(why)
            return
        option = recommended(problem)
        objectives = (option.get("evaluation") or {}).get("objectives") or {}
        weather = objectives.get("weather") or {}
        say(f"   decision {problem['decisionId']} on {item['subjectId']} computed; {len(problem['options'])} options")
        say(f"   recommended option weather       available {weather.get('available')}; value {weather.get('value')};"
            f" confidence {weather.get('confidence')}; {weather.get('unknownBecause') or weather.get('basis')}")
        critic = option.get("critic") or {}
        say(f"   option critic                    {critic.get('verdict')}")
        for check in critic.get("checks", []):
            if "weather" in check.get("name", ""):
                say(f"   critic {check['name']:<25} {'passed' if check.get('passed') else 'FAILED'} -- {check.get('detail')}")
        if weather.get("available") and (weather.get("confidence") or 0) > 0:
            fail("weather was scored with confidence on an option without a marine grid")
    finally:
        stop(process)
    say()


# --------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8000/api", help="the running deployment, for the finance scenario")
    parser.add_argument("--mode", default="DEMO")
    parser.add_argument("--ports", default="8011,8012", help="spare ports for the throwaway instances")
    args = parser.parse_args(argv)
    ais_port, marine_port = (int(p) for p in args.ports.split(","))
    log_dir = ROOT / ".portwatch" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    say("PortWatch failure demo -- what the product says when a signal is not there")
    say()
    scenario_ais(ais_port, log_dir)
    scenario_finance(Api(args.api), args.mode)
    scenario_marine(marine_port, log_dir)

    if problems:
        say(f"{len(problems)} scenario(s) did not fail the way the product promises:")
        for problem in problems:
            say(f"  - {problem}")
        return 1
    say("every failure was reported in the product's own words; nothing was substituted or zeroed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
