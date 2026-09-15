"""The restart and recovery demo: what survives a process restart, and how the
product fails when its durable store or its caches are broken.

    python scripts/demo_restart.py [--ports 8021,8022] [--mode DEMO]

Nothing is mocked. A throwaway API is started with PORTWATCH_STATE_DIR set to
a fresh directory, operated through the same routes the terminal reads, and
then stopped and started again on the same directory:

  1. RESTART        make a decision, choose an option, hand it into the advisory
                    boundary, record an outcome on a second decision, enter a
                    cost assumption; restart; the ledger rows, the advisory,
                    the assumption and the outcome must all be there, and the
                    world must rebuild from the same caches to the same
                    revision. The engine's memory is empty by design and the
                    restored problems say so.
  2. CORRUPT LEDGER a state directory whose ledger is not a database. The API
                    must answer 503 with the path and the fault on every ledger
                    route, health must report the store as unavailable, and
                    nothing may be started in its place.
  3. CORRUPT CACHE  an event register cache that is not JSON. Freshness must
                    say so and the world must not be built from it.

A scenario that does not behave as stated is reported and the script exits
non-zero.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
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

COMPANY = {"X-PortWatch-Actor": "restart-demo.ops", "X-PortWatch-Role": "SHIPPING_COMPANY",
           "X-PortWatch-Org": "PortWatch Demo Shipping"}
PORT = {"X-PortWatch-Actor": "restart-demo.port", "X-PortWatch-Role": "PORT_AUTHORITY",
        "X-PortWatch-Port": "INNSA", "X-PortWatch-Org": "JNPA"}
ADMIN = {"X-PortWatch-Actor": "restart-demo.admin", "X-PortWatch-Role": "NATIONAL_ADMIN"}

problems: list[str] = []


def say(text: str = "") -> None:
    print(text, flush=True)


def fail(text: str) -> None:
    problems.append(text)
    say(f"  !! {text}")


class Api:
    def __init__(self, base: str) -> None:
        self.base = base

    def call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None,
             headers: Optional[Dict[str, str]] = None, timeout: float = 180) -> Tuple[int, Any]:
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


def start_api(port: int, env: Dict[str, str], log: Path) -> subprocess.Popen:
    command = [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1",
               "--port", str(port), "--log-level", "warning"]
    merged = {**os.environ, **env, "PYTHONPATH": str(ROOT), "PORTWATCH_FRESHNESS_SCHEDULER": "0"}
    handle = log.open("ab")
    kwargs: Dict[str, Any] = {"cwd": str(ROOT), "env": merged, "stdout": handle, "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(command, **kwargs)


def wait_ready(api: Api, timeout: float = 180) -> bool:
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
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()


# --------------------------------------------------------------------------
# 1. restart
# --------------------------------------------------------------------------


def _first_actionable(api: Api, mode: str) -> Optional[Dict[str, Any]]:
    status, body = api.get(f"/attention?limit=25&mode={mode}", headers=COMPANY)
    if status != 200:
        return None
    return next((i for i in body.get("items", []) if i.get("subjectType") == "vessel" and i.get("actionable")), None)


def _decide(api: Api, mode: str, item: Dict[str, Any], headers: Dict[str, str]) -> Tuple[int, Any]:
    event_id = item["cascadeId"].split(":")[-1]
    return api.post("/decisions/problems", {"domain": "vessel", "eventId": event_id, "vesselId": item["subjectId"],
                                            "attentionId": item["attentionId"], "mode": mode}, headers=headers)


def scenario_restart(port: int, mode: str, log_dir: Path, state_dir: Path) -> None:
    say("1. RESTART -- operate, stop, start again on the same state directory")
    say(f"   PORTWATCH_STATE_DIR={state_dir}")
    env = {"PORTWATCH_LICENCE_MODE": mode, "PORTWATCH_STATE_DIR": str(state_dir)}
    api = Api(f"http://127.0.0.1:{port}/api")
    process = start_api(port, env, log_dir / "restart-1.log")
    before: Dict[str, Any] = {}
    try:
        if not wait_ready(api):
            fail("the API did not come up")
            return
        status, health = api.get("/health")
        stores = (health or {}).get("durableStores") or {}
        say(f"   /health durableStores.stateDir   {stores.get('stateDir')} ({stores.get('stateDirSource')})")
        if stores.get("stateDir") != str(state_dir):
            fail(f"the state directory in force is {stores.get('stateDir')}")
        status, world = api.get(f"/world/observed?mode={mode}", headers=ADMIN)
        revision = (((world or {}).get("state") or {}).get("revision") or {})
        before["revision"] = {k: revision.get(k) for k in ("mode", "eventsStamp", "fleetStamp", "fingerprint")}
        say(f"   /world/observed revision         fingerprint {revision.get('fingerprint')}; events {str(revision.get('eventsStamp'))[:24]}..")
        if not revision.get("fingerprint"):
            fail("the observed world states no revision fingerprint")

        item = _first_actionable(api, mode)
        if item is None:
            fail("no actionable hull to decide about (refresh the demo caches)")
            return
        # A port authority's decision: approve an intervention, hand it off.
        status, advised = _decide(api, mode, item, PORT)
        if status != 200:
            fail(f"decision (port authority) HTTP {status}: {advised}")
            return
        did = advised["decisionId"]
        rec = advised["recommendation"] or {}
        feasible = [o for o in advised["options"] if o["status"] == "FEASIBLE" and not o["isBaseline"]
                    and (o.get("critic") or {}).get("verdict") != "REJECT"]
        chosen = feasible[0]["optionId"] if feasible else rec.get("optionId")
        say(f"   decision {did}: recommendation {rec.get('kind')} {rec.get('optionId')}; operator chooses {chosen}")
        api.post(f"/decisions/problems/{did}/transition", {"target": "REVIEWED"}, headers=PORT)
        status, body = api.post(f"/decisions/problems/{did}/transition", {"target": "APPROVED", "optionId": chosen}, headers=PORT)
        if status != 200:
            fail(f"APPROVED refused: {body}")
            return
        advisory_ids: list[str] = []
        if chosen != advised["baselineOptionId"]:
            status, body = api.post(f"/decisions/problems/{did}/handoff", {}, headers=PORT)
            if status != 200:
                fail(f"handoff refused: {body}")
            else:
                advisory_ids = [a["advisoryId"] for a in body.get("advisories", [])]
                say(f"   handoff -> {len(advisory_ids)} DRAFT advisory(ies): {', '.join(advisory_ids)}")
        before["decision"] = did
        before["advisories"] = advisory_ids
        before["workflow"] = "PROPOSED" if advisory_ids else "APPROVED"

        # A shipping company's decision with an observed outcome.
        status, own = _decide(api, mode, item, COMPANY)
        if status != 200:
            fail(f"decision (company) HTTP {status}: {own}")
            return
        did2 = own["decisionId"]
        rec2 = own["recommendation"] or {}
        api.post(f"/decisions/problems/{did2}/transition", {"target": "REVIEWED"}, headers=COMPANY)
        api.post(f"/decisions/problems/{did2}/transition", {"target": "APPROVED", "optionId": rec2.get("optionId")}, headers=COMPANY)
        status, body = api.post(f"/decisions/problems/{did2}/outcome",
                                {"actualAction": "KEEP_PLAN", "observed": {"eta": 4.0, "incident": 0}, "note": "restart demo"},
                                headers=COMPANY)
        if status != 200:
            fail(f"outcome refused: {body}")
        say(f"   decision {did2}: approved {rec2.get('optionId')}, outcome recorded ({body.get('workflow') if status == 200 else status})")
        before["outcome_decision"] = did2

        # An operator's cost assumption.
        status, body = api.post("/finance/assumptions", {"primitive": "charter_day", "value": 41000, "currency": "USD",
                                                          "note": "restart demo"}, headers=COMPANY)
        if status != 200 or not body.get("journalled"):
            fail(f"the assumption was not journalled: {status} {body}")
        say(f"   /finance/assumptions: charter_day 41000 USD entered by {COMPANY['X-PortWatch-Actor']}, journalled {body.get('journalled') if body else None}")
        status, learning = api.get("/decisions/learning")
        before["scored"] = (learning or {}).get("scored") or (learning or {}).get("problems") or (learning or {}).get("resolved")
        say(f"   /decisions/learning before restart: available {(learning or {}).get('available')}")
    finally:
        stop(process)
        say("   -- process stopped --")

    process = start_api(port, env, log_dir / "restart-2.log")
    try:
        if not wait_ready(api):
            fail("the API did not come back up")
            return
        status, health = api.get("/health")
        stores = (health or {}).get("durableStores") or {}
        say(f"   /health durableStores.ok         {stores.get('ok')}; ledger counts {stores.get('ledger', {}).get('counts')}; "
            f"advisories {stores.get('advisories', {}).get('counts')}; assumptions {stores.get('costAssumptions', {}).get('counts')}")
        if not stores.get("ok"):
            fail("durable stores not ok after restart")

        # The decision from before the restart: not in this process's memory, served from the ledger.
        did = before.get("decision")
        status, restored = api.get(f"/decisions/problems/{did}")
        say(f"   GET /decisions/problems/{did}: HTTP {status}, restoredFromLedger {(restored or {}).get('restoredFromLedger')}, "
            f"workflow {(restored or {}).get('workflow')}, humanChoice {(restored or {}).get('humanChoice')}")
        if status != 200 or not (restored or {}).get("restoredFromLedger"):
            fail("the decision made before the restart is not served from the ledger")
        elif (restored or {}).get("workflow") != before.get("workflow"):
            fail(f"the restored workflow is {(restored or {}).get('workflow')}, expected {before.get('workflow')}")
        status, listed = api.get("/decisions/problems?limit=50")
        ids = {r.get("decisionId") for r in (listed or {}).get("problems", [])}
        say(f"   GET /decisions/problems: {len(ids)} listed, {(listed or {}).get('restoredFromLedger')} restored from the ledger")
        if did not in ids or before.get("outcome_decision") not in ids:
            fail("a pre-restart decision is missing from the list")
        status, moved = api.post(f"/decisions/problems/{did}/transition", {"target": "ISSUED"}, headers=PORT)
        say(f"   POST transition on the restored decision: HTTP {status} -- {(moved or {}).get('detail', '')[:90]}")
        if status == 200:
            fail("a restored decision was moved through the workflow without being recomputed")
        elif status != 409 or "recompute" not in str((moved or {}).get("detail", "")):
            fail(f"the refusal is {status} and does not say to recompute")

        # The advisory the handoff raised.
        status, advisories = api.get("/advisories", headers=PORT)
        held = {a.get("advisoryId") for a in (advisories or {}).get("advisories", [])} if status == 200 else set()
        missing = [a for a in before.get("advisories", []) if a not in held]
        say(f"   GET /advisories: {len(held)} held; pre-restart advisories present: {len(before.get('advisories', [])) - len(missing)}/{len(before.get('advisories', []))}")
        if missing:
            fail(f"advisories lost across the restart: {missing}")

        # The outcome and the learning it feeds.
        status, learning = api.get("/decisions/learning")
        say(f"   /decisions/learning after restart: available {(learning or {}).get('available')}, "
            f"mean regret {(learning or {}).get('meanRegret')}, agreement {(learning or {}).get('agreementRate')}")
        if not (learning or {}).get("available"):
            fail("the outcome recorded before the restart no longer scores")

        # The assumption.
        status, basis = api.get("/finance/basis")
        rates = (basis or {}).get("rates") or (basis or {}).get("assumptions") or []
        found = [r for r in rates if r.get("isAssumption") and r.get("primitive") == "charter_day"]
        say(f"   GET /finance/basis: {len(found)} journalled charter_day assumption(s) reloaded"
            + (f", entered by {found[0]['provenance'].get('enteredBy')}" if found else ""))
        if not found:
            fail("the cost assumption did not survive the restart")

        # The world, rebuilt from the same caches to the same revision.
        status, world = api.get(f"/world/observed?mode={mode}", headers=ADMIN)
        revision = (((world or {}).get("state") or {}).get("revision") or {})
        after = {k: revision.get(k) for k in ("mode", "eventsStamp", "fleetStamp", "fingerprint")}
        say(f"   /world/observed revision after   fingerprint {after.get('fingerprint')}; events {str(after.get('eventsStamp'))[:24]}..")
        if after != before.get("revision"):
            fail(f"the world did not rebuild to the same revision: {before.get('revision')} -> {after}")
        else:
            say("   the world rebuilt from the caches to the same revision")
    finally:
        stop(process)


# --------------------------------------------------------------------------
# 2. corrupt ledger
# --------------------------------------------------------------------------


def scenario_corrupt_ledger(port: int, mode: str, log_dir: Path, state_dir: Path) -> None:
    say("2. CORRUPT LEDGER -- the ledger file is not a database")
    state_dir.mkdir(parents=True, exist_ok=True)
    ledger = state_dir / "portwatch_ledger.db"
    ledger.write_bytes(b"this is not a sqlite database; it is the failure demo\n" * 64)
    env = {"PORTWATCH_LICENCE_MODE": mode, "PORTWATCH_STATE_DIR": str(state_dir)}
    api = Api(f"http://127.0.0.1:{port}/api")
    process = start_api(port, env, log_dir / "corrupt-ledger.log")
    try:
        if not wait_ready(api):
            fail("the API did not come up")
            return
        status, health = api.get("/health")
        stores = (health or {}).get("durableStores") or {}
        say(f"   /health status                   {(health or {}).get('status')}; durableStores.ok {stores.get('ok')}")
        say(f"   /health durableStores.ledger     ok {stores.get('ledger', {}).get('ok')} -- {str(stores.get('ledger', {}).get('error'))[:110]}")
        if stores.get("ok") or stores.get("ledger", {}).get("ok"):
            fail("health reports a corrupt ledger as ok")
        if (health or {}).get("status") != "degraded":
            fail("health is not degraded with a corrupt ledger")
        status, body = api.get("/decisions/problems?limit=5")
        say(f"   GET /decisions/problems          HTTP {status} -- {str((body or {}).get('detail'))[:110]}")
        if status != 503:
            fail(f"a ledger route answered {status}, not 503")
        if "substituted" not in str((body or {}).get("remedy", "")):
            fail("the 503 does not say nothing was substituted")
        status, readiness = api.get(f"/admin/readiness?mode={mode}", headers=ADMIN)
        checks = {c["name"]: c for c in (readiness or {}).get("checks", [])}
        store_check = checks.get("store:ledger") or {}
        say(f"   /admin/readiness store:ledger    {store_check.get('status')} -- {str(store_check.get('detail'))[:100]}")
        say(f"   /admin/readiness ready           {(readiness or {}).get('ready')}")
        if store_check.get("status") != "FAIL" or (readiness or {}).get("ready"):
            fail("readiness did not refuse on a corrupt ledger")
        if ledger.read_bytes()[:16] == b"SQLite format 3\x00":
            fail("the corrupt ledger was replaced with a fresh database")
        else:
            say("   the corrupt file was left as it was; no fresh ledger was started in its place")
    finally:
        stop(process)


# --------------------------------------------------------------------------
# 3. corrupt cache
# --------------------------------------------------------------------------


def scenario_corrupt_cache(port: int, mode: str, log_dir: Path, state_dir: Path) -> None:
    say("3. CORRUPT CACHE -- the event register cache is not JSON")
    events = ROOT / "data" / "cache" / "news_bundle.json"
    if not events.exists():
        say("   no event register cache on disk; skipped")
        return
    backup = events.read_bytes()
    events.write_bytes(b"{ this is not json")
    env = {"PORTWATCH_LICENCE_MODE": mode, "PORTWATCH_STATE_DIR": str(state_dir)}
    api = Api(f"http://127.0.0.1:{port}/api")
    process = start_api(port, env, log_dir / "corrupt-cache.log")
    try:
        if not wait_ready(api):
            fail("the API did not come up")
            return
        status, fresh = api.get("/admin/freshness", headers=ADMIN)
        rows = {r["artifact"]: r for r in (fresh or {}).get("artifacts", [])}
        row = rows.get("events") or {}
        say(f"   /admin/freshness events          {row.get('state')} -- {str(row.get('reason'))[:100]}")
        status, world = api.get(f"/world/state?mode={mode}", headers=ADMIN)
        say(f"   /world/state                     HTTP {status} -- {str((world or {}).get('detail') or (world or {}).get('revision', {}).get('eventsStamp'))[:100]}")
        status, cascades = api.get(f"/world/cascades?mode={mode}", headers=ADMIN)
        count = len((cascades or {}).get("cascades", [])) if status == 200 else None
        say(f"   /world/cascades                  HTTP {status}; cascades {count}")
        if row.get("state") not in ("MISSING", "STALE", "EXPIRED") and status == 200 and count:
            fail("a corrupt event cache produced a world with live cascades")
    finally:
        stop(process)
        events.write_bytes(backup)
        say("   the event cache was restored")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ports", default="8021,8022,8023")
    parser.add_argument("--mode", default="DEMO")
    args = parser.parse_args()
    ports = [int(p) for p in args.ports.split(",")]
    workdir = Path(tempfile.mkdtemp(prefix="portwatch-restart-"))
    log_dir = workdir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    say(f"logs in {log_dir}")
    say()
    scenario_restart(ports[0], args.mode, log_dir, workdir / "state-restart")
    say()
    scenario_corrupt_ledger(ports[1 % len(ports)], args.mode, log_dir, workdir / "state-corrupt")
    say()
    scenario_corrupt_cache(ports[2 % len(ports)], args.mode, log_dir, workdir / "state-cache")
    say()
    if problems:
        say(f"{len(problems)} problem(s):")
        for line in problems:
            say(f"  - {line}")
        return 1
    say("every scenario behaved as stated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
