"""Demo acceptance: the claims the product makes about itself, checked in order.

Runs the demo's own sequence against the API -- in-process by default, or a
running server with ``--base-url`` -- and prints a checklist. Each line is a
claim from the milestone, stated as the product states it, and the check is
whether the API says the same. A FAIL is a broken promise; a SKIP is a claim
this deployment cannot make (no AIS key, say) and says so.

    python scripts/demo_acceptance.py
    python scripts/demo_acceptance.py --base-url http://127.0.0.1:8000/api --mode DEMO

Exit status is non-zero on any FAIL.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class Api:
    def __init__(self, base_url: Optional[str]) -> None:
        self.base_url = base_url
        if base_url:
            import urllib.request

            self._urllib = urllib.request
            self._client = None
        else:
            from fastapi.testclient import TestClient

            from backend.app.main import app

            self._client = TestClient(app)

    def get(self, path: str, headers: Optional[Dict[str, str]] = None, **params: Any) -> Tuple[int, Any]:
        query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        url = f"{path}?{query}" if query else path
        head = headers or HEADERS
        if self._client is not None:
            response = self._client.get(f"/api{url}", headers=head)
            return response.status_code, response.json()
        request = self._urllib.Request(f"{self.base_url}{url}", headers=head)
        try:
            with self._urllib.urlopen(request, timeout=60) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except self._urllib.HTTPError as error:  # a refusal is an answer, not a crash
            return error.code, json.loads(error.read().decode("utf-8") or "{}")

    def post(self, path: str, body: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Tuple[int, Any]:
        head = headers or HEADERS
        if self._client is not None:
            response = self._client.post(f"/api{path}", json=body, headers=head)
            return response.status_code, response.json()
        data = json.dumps(body).encode("utf-8")
        request = self._urllib.Request(
            f"{self.base_url}{path}", data=data, headers={**head, "Content-Type": "application/json"},
        )
        try:
            with self._urllib.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except self._urllib.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8") or "{}")


HEADERS = {"X-PortWatch-Actor": "acceptance", "X-PortWatch-Role": "NATIONAL_ADMIN"}
COMPANY = {"X-PortWatch-Actor": "acceptance.ops", "X-PortWatch-Role": "SHIPPING_COMPANY",
           "X-PortWatch-Org": "PortWatch Demo Shipping"}
PORT = {"X-PortWatch-Actor": "acceptance.port", "X-PortWatch-Role": "PORT_AUTHORITY", "X-PortWatch-Port": "INNSA"}


class Checklist:
    def __init__(self) -> None:
        self.rows: List[Tuple[str, str, str]] = []

    def check(self, claim: str, fn: Callable[[], Optional[str]]) -> None:
        """fn returns None for PASS, a reason for FAIL, or raises Skip."""
        try:
            reason = fn()
        except Skip as skip:
            self.rows.append((SKIP, claim, str(skip)))
            return
        except Exception as exc:  # noqa: BLE001 - a crash is a failed claim
            self.rows.append((FAIL, claim, f"{type(exc).__name__}: {exc}"))
            return
        self.rows.append((FAIL if reason else PASS, claim, reason or ""))

    def report(self) -> int:
        width = max(len(c) for _, c, _ in self.rows)
        for status, claim, note in self.rows:
            print(f"[{status}] {claim.ljust(width)}  {note}")
        counts = {s: sum(1 for r in self.rows if r[0] == s) for s in (PASS, FAIL, SKIP)}
        print(f"\n{counts[PASS]} passed, {counts[FAIL]} failed, {counts[SKIP]} skipped")
        return 1 if counts[FAIL] else 0


class Skip(Exception):
    pass


def run(api: Api, mode: str) -> int:
    rows = Checklist()
    state: Dict[str, Any] = {}

    # ---------------------------------------------------------------- trust --
    def health():
        status, body = api.get("/fabric/health", mode=mode)
        if status != 200:
            return f"HTTP {status}"
        state["health"] = body
        return None
    rows.check("Signal health answers", health)

    def traffic_honest():
        traffic = state["health"]["traffic"]
        health = traffic.get("health") or {}
        if traffic["mode"] == "LIVE_AIS" and not health.get("lastGoodObservationAt"):
            return "LIVE_AIS claimed with no valid observation on record"
        if traffic["mode"] == "SIMULATED_TRAFFIC" and traffic["providerId"] != "ais-replay":
            return f"SIMULATED_TRAFFIC attributed to {traffic['providerId']}"
        state["traffic"] = traffic
        return None
    rows.check("Traffic is LIVE_AIS only because observations arrived", traffic_honest)

    def licence_states():
        for signal in state["health"]["signals"]:
            for field in ("commercialUse", "governmentUse"):
                if signal[field] not in ("ALLOWED", "PROHIBITED", "REQUIRES_REVIEW", "UNKNOWN", None):
                    return f"{signal['capability']}.{field} is {signal[field]!r}, not a four-state permission"
            if signal["productId"] is None:
                return f"{signal['capability']} names no product"
        return None
    rows.check("Every signal names its product and a four-state licence", licence_states)

    def aisstream_review():
        ais = next((s for s in state["health"]["signals"] if s["capability"] == "ais"), None)
        if ais is None:
            return "no ais signal"
        if ais["productId"] == "aisstream-websocket" and ais["commercialUse"] != "REQUIRES_REVIEW":
            return f"AISStream commercial use is {ais['commercialUse']}; no terms were ever found"
        return None
    rows.check("AISStream is REQUIRES_REVIEW, not inferred either way", aisstream_review)

    def no_secret():
        text = json.dumps(state["health"])
        for name in ("AISSTREAM_API_KEY", "OPEN_METEO_API_KEY"):
            value = os.getenv(name)
            if value and value in text:
                return f"{name}'s value appears in the health payload"
        if "APIKey" in text or "apikey=" in text:
            return "a key-shaped field appears in the health payload"
        return None
    rows.check("No secret reaches the browser", no_secret)

    # ------------------------------------------------------------- commercial --
    def commercial_withholds():
        status, body = api.get("/fabric/health", mode="COMMERCIAL")
        if status != 200:
            return f"HTTP {status}"
        if body["traffic"]["mode"] not in ("UNAVAILABLE",):
            return f"COMMERCIAL traffic is {body['traffic']['mode']}"
        for signal in body["signals"]:
            if signal["productId"] in ("open-meteo-free", "aisstream-websocket") and signal["availability"]["status"] == "AVAILABLE":
                return f"{signal['productId']} is AVAILABLE in COMMERCIAL"
        return None
    rows.check("A COMMERCIAL view gets no non-commercial product", commercial_withholds)

    # ------------------------------------------------------------------ world --
    def world():
        status, body = api.get("/world/state", mode=mode)
        if status != 200:
            return f"HTTP {status}"
        state["world"] = body
        observed = body["summary"].get("observedVessels", 0)
        traffic = state["traffic"]["mode"]
        if observed and traffic not in ("LIVE_AIS", "AIS_STALE"):
            return f"{observed} observed hulls in the graph while traffic is {traffic}"
        return None
    rows.check("Observed hulls are in the world only when the source is observed", world)

    def observed_provenance():
        nodes = [n for n in state["world"]["nodes"] if n["attrs"].get("source") == "OBSERVED_AIS"]
        if not nodes:
            raise Skip("no observed hulls in this deployment")
        for node in nodes:
            attrs = node["attrs"]
            if attrs.get("placement_confidence") is None:
                return f"{node['key']} carries no placement confidence"
            if attrs.get("lane_code") and attrs.get("placement_confidence", 1) >= 1.0:
                return f"{node['key']} is on a lane at confidence 1.0; a placement was inferred"
            if not attrs.get("name_stated") and not node["label"].startswith("MMSI "):
                return f"{node['key']} has an invented name {node['label']!r}"
        return None
    rows.check("Every observed hull carries its placement confidence and no invented name", observed_provenance)

    def tracks():
        status, body = api.get("/world/ais/tracks", mode=mode)
        if status != 200:
            return f"HTTP {status}"
        if body["traffic"]["mode"] != state["traffic"]["mode"]:
            return "tracks and health disagree about the traffic mode"
        if state["traffic"]["mode"] == "SIMULATED_TRAFFIC" and body["tracks"]:
            return "observed tracks served while the source is the replay"
        for track in body["tracks"]:
            if track["source"] != "OBSERVED_AIS":
                return f"track {track['mmsi']} is {track['source']}"
            latest = track["latest"]
            if latest and latest.get("headingDegrees") == 511:
                return f"track {track['mmsi']} reports heading 511 as a bearing"
        state["tracks"] = body
        return None
    rows.check("Observed tracks carry only what was said, under the same traffic block", tracks)

    def entities():
        status, body = api.get("/world/entities")
        if status != 200:
            return f"HTTP {status}"
        for hull in body["vessels"]:
            for candidate in hull["candidates"]:
                if candidate["applied"]:
                    return f"{hull['canonicalId']} applied a name candidate"
        status, _ = api.get("/world/entities/lookup", name="anything")
        if status != 400:
            return f"lookup by name answered {status}, not 400"
        return None
    rows.check("Fusion never merges by name, and lookup has no name key", entities)

    # -------------------------------------------------------------------- sea --
    def marine():
        status, body = api.get("/world/marine", mode=mode)
        if status != 200:
            return f"HTTP {status}"
        state["marine"] = body
        if body["availability"]["status"] != "AVAILABLE":
            raise Skip(f"marine {body['availability']['status']}: {body['availability']['reason']}")
        if not body["attribution"]:
            return "cells served without attribution"
        if body["ageSeconds"] is None or body["fetchedAt"] is None:
            return "cells served without a fetch age"
        if not body["cells"]:
            return "AVAILABLE with no cells"
        return None
    rows.check("The sea is served with product, fetch age and attribution", marine)

    def route():
        if state.get("marine", {}).get("availability", {}).get("status") != "AVAILABLE":
            raise Skip("no marine grid")
        departs = datetime.now(timezone.utc) + timedelta(hours=1)
        status, body = api.post("/world/route/exposure", {
            "mode": mode, "speedKn": 14, "departsAt": departs.isoformat(),
            "waypoints": [[12.6, 44.5], [12.5, 52.0], [15.0, 60.0], [18.0, 69.5], [18.9, 72.8]],
        })
        if status != 200:
            return f"HTTP {status}"
        if body["confidence"] > 0.5:
            return f"route confidence {body['confidence']} above the heuristic's ceiling"
        if body["coverage"] < 0.5:
            return f"coverage {body['coverage']}: the grid does not cover the demo passage"
        return None
    rows.check("A passage is graded by coverage, with confidence never above 0.5", route)

    # -------------------------------------------------------------- attention --
    def attention():
        status, body = api.get("/attention", mode=mode, limit=25)
        if status != 200:
            return f"HTTP {status}"
        for item in body["items"]:
            if item["source"] == "OBSERVED_AIS":
                action = (item.get("recommendedAction") or {}).get("action")
                if action == "reroute":
                    return f"{item['subjectLabel']} is observed and the queue would order it to reroute"
            if item["source"] == "FEED" and item["actionable"]:
                return "a feed item is actionable"
        stale = state["traffic"]["mode"] in ("AIS_STALE",)
        has_feed = any(i["source"] == "FEED" for i in body["items"])
        if stale and not has_feed:
            return "traffic is stale and the queue does not say so"
        return None
    rows.check("Attention advises observed hulls and names a stale feed", attention)

    # --------------------------------------------------------------- branches --
    def branch():
        status, body = api.post("/world/branches", {
            "mode": mode, "assumptions": [{"kind": "close_chokepoint", "subject": "BAB_EL_MANDEB", "value": 0.9}],
        })
        if status != 200:
            return f"HTTP {status}: {body}"
        branch_id = body["branch"]["branchId"]
        seed = body["branch"]["seeds"][0].split(":", 1)[1]
        status, detail = api.get(f"/world/branches/{branch_id}/cascades/{seed}", mode=mode)
        if status != 200:
            return f"HTTP {status}"
        if not detail["assumed"]:
            return "the branch's own seed is not marked assumed"
        if not any(step["source"] == "ASSUMPTION" for step in detail["branched"]["steps"]):
            return "no step in the branched cascade is labelled ASSUMPTION"
        if detail["observed"] is not None:
            return "the observed world acquired the assumed event"
        return None
    rows.check("A branch never edits the observed world and labels every assumed link", branch)

    # ------------------------------------------------------------------
    # The decision engine: fifteen claims, in the order the product makes
    # them. Each one is what the milestone promised, checked against what
    # the API says now.
    # ------------------------------------------------------------------
    held: Dict[str, Any] = {}

    def first_actionable():
        status, body = api.get("/attention", limit=25, mode=mode)
        if status != 200:
            raise Skip(f"attention queue HTTP {status}")
        item = next((i for i in body.get("items", []) if i.get("subjectType") == "vessel" and i.get("actionable")), None)
        if item is None:
            raise Skip("no actionable hull in the register at this instant (the claims may have lapsed; refresh the demo)")
        return item

    def solve():
        item = first_actionable()
        event_id = item["cascadeId"].split(":")[-1]
        status, body = api.post("/decisions/problems", {
            "domain": "vessel", "eventId": event_id, "vesselId": item["subjectId"],
            "attentionId": item["attentionId"], "mode": mode,
        }, headers=COMPANY)
        if status != 200:
            return f"HTTP {status}: {body}"
        held["problem"] = body
        held["item"] = item
        if not body.get("worldStateId") or not body.get("worldRevision"):
            return "the problem is not tied to a world state and revision"
        if body["baselineOptionId"] not in {o["optionId"] for o in body["options"]}:
            return "the do-nothing baseline is not one of the options"
        if not body.get("doNothingStatement", "").startswith("If unchanged"):
            return "no 'if unchanged' statement"
        return None
    rows.check("1. 'What should this hull do?' returns one DecisionProblem tied to a world revision", solve)

    def catalogue():
        problem = held.get("problem")
        if not problem:
            raise Skip("no problem")
        kinds = {a["kind"] for a in problem["availableActions"]}
        for kind in ("KEEP_PLAN", "REROUTE", "SLOW_STEAM", "SPEED_UP", "CHANGE_DESTINATION_PORT", "REBUNKER"):
            if kind not in kinds:
                return f"catalogue row {kind} missing"
        for row in problem["availableActions"]:
            if row["availability"]["status"] != "AVAILABLE" and not row["availability"]["reason"]:
                return f"{row['kind']} is not offered and gives no reason"
        offered = {o["action"] for o in problem["options"]}
        if not offered <= kinds:
            return f"an option is not a catalogue action: {offered - kinds}"
        return None
    rows.check("2. Every option is a typed catalogue action; an absent one names why", catalogue)

    def infeasible():
        # A hull already past Suez cannot take the Cape: rejected by a named
        # constraint and given no score, never merely ranked last.
        status, body = api.post("/world/branches", {
            "mode": mode, "assumptions": [{"kind": "close_chokepoint", "subject": "SUEZ", "value": 0.9}],
        })
        if status != 200:
            raise Skip(f"branch HTTP {status}")
        branch_id = body["branch"]["branchId"]
        status, fleet = api.get("/company/fleet", mode=mode, headers=COMPANY)
        past = None
        if status == 200:
            for v in fleet.get("vessels", []):
                hours = (v.get("hours_to_chokepoint") or {}).get("SUEZ")
                if hours is not None and hours < 0:
                    past = v["vessel_id"]
                    break
        if past is None:
            raise Skip("no fleet hull past Suez to test against")
        status, problem = api.post("/decisions/problems", {
            "domain": "vessel", "branchId": branch_id, "seed": "event:" + body["branch"]["seeds"][0].split(":", 1)[1]
            if not body["branch"]["seeds"][0].startswith("event:") else body["branch"]["seeds"][0],
            "vesselId": past, "mode": mode,
        }, headers=COMPANY)
        if status != 200:
            return f"HTTP {status}: {problem}"
        reroute = next((o for o in problem["options"] if o["action"] == "REROUTE"), None)
        rows_by_kind = {a["kind"]: a for a in problem["availableActions"]}
        if reroute is None:
            reason = rows_by_kind["REROUTE"]["availability"]["reason"]
            return None if reason else "REROUTE absent without a reason"
        if reroute["status"] != "REJECTED":
            return f"a hull past Suez has REROUTE {reroute['status']}"
        if reroute.get("evaluation") and reroute["evaluation"].get("score") is not None:
            return "a rejected option carries a score"
        if not reroute["rejectedBy"]:
            return "rejected without a named constraint"
        return None
    rows.check("3. A hard constraint rejects an option and names itself; it never becomes a penalty", infeasible)

    def baseline_same_simulator():
        problem = held.get("problem")
        if not problem:
            raise Skip("no problem")
        baseline = next(o for o in problem["options"] if o["isBaseline"])
        if not baseline.get("evaluation") or not baseline["evaluation"].get("objectives"):
            return "the baseline carries no measures"
        if not baseline["evaluation"].get("branchId"):
            return "the baseline was not evaluated on its own branch"
        branches = {o["evaluation"]["branchId"] for o in problem["options"] if o.get("evaluation")}
        if len(branches) != len([o for o in problem["options"] if o.get("evaluation")]):
            return "two options share a branch"
        eta = baseline["evaluation"]["objectives"].get("eta")
        if not eta or not eta.get("basis"):
            return "the baseline's ETA shift has no basis"
        return None
    rows.check("4. Doing nothing is computed through the same simulator, on its own branch", baseline_same_simulator)

    def frontier():
        problem = held.get("problem")
        if not problem:
            raise Skip("no problem")
        front = problem.get("frontier") or {}
        if "nondominated" not in front or "picks" not in front:
            return "no frontier"
        rec = problem.get("recommendation")
        if rec and rec["optionId"] in (front.get("dominated") or {}):
            return "the recommendation is a dominated option"
        ranking = (problem.get("evidence") or {}).get("ranking") or {}
        if not ranking.get("weights"):
            return "the ranking does not state its weights"
        for pick, option_id in front["picks"].items():
            if option_id is not None and option_id not in {o["optionId"] for o in problem["options"]}:
                return f"pick {pick} names an option that does not exist"
        return None
    rows.check("5. A Pareto frontier with named picks; the recommendation is never dominated", frontier)

    def deterministic():
        item = held.get("item")
        problem = held.get("problem")
        if not item or not problem:
            raise Skip("no problem")
        event_id = item["cascadeId"].split(":")[-1]
        status, again = api.post("/decisions/problems", {
            "domain": "vessel", "eventId": event_id, "vesselId": item["subjectId"], "mode": mode,
            "at": problem["at"],
        }, headers=COMPANY)
        if status != 200:
            return f"HTTP {status}"
        order = [o["optionId"] for o in problem["options"]]
        order_again = [o["optionId"] for o in again["options"]]
        if order != order_again:
            return "the same world produced a different option set"
        if (problem.get("recommendation") or {}).get("optionId") != (again.get("recommendation") or {}).get("optionId"):
            return "the same world produced a different recommendation"
        for a, b in zip(problem["options"], again["options"]):
            ea, eb = (a.get("evaluation") or {}).get("objectives", {}), (b.get("evaluation") or {}).get("objectives", {})
            for key in ea:
                if ea[key].get("value") != eb.get(key, {}).get("value"):
                    return f"{a['optionId']}.{key} differs between two solves of the same world"
        return None
    rows.check("6. The optimiser is deterministic: the same world, the same answer", deterministic)

    def critic():
        problem = held.get("problem")
        if not problem:
            raise Skip("no problem")
        for option in problem["options"]:
            verdict = (option.get("critic") or {}).get("verdict")
            if verdict not in ("PASS", "PASS_WITH_WARNINGS", "REJECT"):
                return f"{option['optionId']} has no critic verdict"
            for check in (option["critic"].get("checks") or []):
                if not check.get("basis"):
                    return f"critic check {check.get('name')} names no evidence"
        rec = problem.get("recommendation")
        if rec and not (rec.get("critic") or {}).get("verdict"):
            return "the recommendation has no critic verdict"
        return None
    rows.check("7. The Critic passes or rejects every option and names the computation it read", critic)

    def money_honest():
        problem = held.get("problem")
        if not problem:
            raise Skip("no problem")
        baseline = next(o for o in problem["options"] if o["isBaseline"])
        financial = baseline["evaluation"]["financial"]
        unknown = [c for c in financial["components"] if c["state"] == "UNKNOWN"]
        if unknown and financial["total"] is not None:
            return "a total exists with unknown components"
        for c in financial["components"]:
            if c["state"] == "UNKNOWN" and not c["reason"]:
                return f"{c['key']} is unknown without a reason"
            if c["state"] == "ZERO" and not c["reason"]:
                return f"{c['key']} is zero without a reason"
        status, body = api.post("/finance/fx", {"base": "USD", "quote": "INR", "rate": 83.0}, headers=COMPANY)
        if status == 200:
            return "an exchange rate without an instant and a source was accepted"
        return None
    rows.check("8. Unknown money is never zero; a total needs every component; FX needs an observation", money_honest)

    def tariff_and_assumption():
        status, tariffs = api.get("/finance/tariffs")
        if status != 200:
            return f"HTTP {status}"
        jnpa = next((s for s in tariffs["schedules"] if s["scheduleId"] == "jnpa-sor-2026-27"), None)
        if jnpa is None:
            return "the JNPA scale of rates is not held"
        if jnpa["sourceType"] != "PUBLIC_TARIFF" or not jnpa["provenance"].get("url"):
            return "the tariff is not labelled PUBLIC_TARIFF with its URL"
        if not jnpa.get("reuse"):
            return "the tariff's reuse is not stated"
        item, problem = held.get("item"), held.get("problem")
        if not item or not problem:
            raise Skip("no problem")
        event_id = item["cascadeId"].split(":")[-1]
        status, priced = api.post("/decisions/problems", {
            "domain": "vessel", "eventId": event_id, "vesselId": item["subjectId"], "mode": mode,
            "assumptions": [{"primitive": "charter_day", "value": 28000, "currency": "USD"}],
            "vesselAssumptions": {"grt": 52000},
        }, headers=COMPANY)
        if status != 200:
            return f"HTTP {status}: {priced}"
        baseline = next(o for o in priced["options"] if o["isBaseline"])
        components = {c["key"]: c for c in baseline["evaluation"]["financial"]["components"]}
        if components["delay"]["state"] != "KNOWN" or not components["delay"]["isAssumption"]:
            return "the assumed charter rate did not price the delay as an assumption"
        if baseline["evaluation"]["financial"]["label"] != "ASSUMPTION":
            return "an option priced on an assumption is not labelled ASSUMPTION"
        if priced["evidence"]["attributeAssumptions"]["grt"]["label"] != "ASSUMPTION":
            return "the assumed tonnage is not labelled"
        return None
    rows.check("9. Public tariffs are cited PUBLIC_TARIFF; operator figures are labelled ASSUMPTION", tariff_and_assumption)

    def actors():
        item = held.get("item")
        if not item:
            raise Skip("no problem")
        event_id = item["cascadeId"].split(":")[-1]
        status, advised = api.post("/decisions/problems", {
            "domain": "vessel", "eventId": event_id, "vesselId": item["subjectId"], "mode": mode,
        }, headers=PORT)
        if status != 200:
            return f"HTTP {status}: {advised}"
        execution = advised["evidence"].get("execution") or {}
        if execution.get("mechanism") != "ISSUE_ADVISORY" or execution.get("by") != "SHIPPING_COMPANY":
            return "a port authority's routing options are not framed as an advisory to the company"
        status, body = api.post("/decisions/problems", {"domain": "port", "portCode": "INNSA", "mode": mode}, headers=COMPANY)
        if status == 200:
            return "a shipping company was allowed to hold a berth decision"
        held["advised"] = advised
        return None
    rows.check("10. Actors get only their own actions; a port authority advises, it does not steer", actors)

    def workflow_and_handoff():
        problem = held.get("advised")
        if not problem:
            raise Skip("no advised problem")
        did = problem["decisionId"]
        rec = problem.get("recommendation")
        if not rec:
            raise Skip("no recommendation to approve")
        status, body = api.post(f"/decisions/problems/{did}/transition", {"target": "APPROVED", "optionId": rec["optionId"]}, headers=PORT)
        if status == 200:
            return "APPROVED was reachable straight from COMPUTED"
        status, body = api.post(f"/decisions/problems/{did}/transition", {"target": "REVIEWED"}, headers=PORT)
        if status != 200:
            return f"REVIEWED refused: {body}"
        status, body = api.post(f"/decisions/problems/{did}/transition", {"target": "APPROVED", "optionId": rec["optionId"]}, headers=PORT)
        if status != 200:
            return f"APPROVED refused: {body}"
        if body["workflow"] != "APPROVED" or not body.get("workflowHistory"):
            return "no workflow history"
        if body.get("humanChoice") != rec["optionId"]:
            return "the approved option was not recorded as the human choice"
        if rec["optionId"] == problem["baselineOptionId"]:
            raise Skip("the recommendation is to keep the plan; no advisory is needed for that")
        status, body = api.post(f"/decisions/problems/{did}/handoff", {}, headers=PORT)
        if status != 200:
            return f"handoff refused: {body}"
        if not body.get("advisories") or any(a.get("state") != "draft" for a in body["advisories"]):
            return "the handoff did not create DRAFT advisories"
        if body["decision"]["workflow"] != "PROPOSED":
            return "the problem did not move to PROPOSED"
        return None
    rows.check("11. Human approval: COMPUTED -> REVIEWED -> APPROVED -> PROPOSED, into the advisory boundary", workflow_and_handoff)

    def ledger():
        problem = held.get("problem")
        if not problem:
            raise Skip("no problem")
        status, body = api.get(f"/decisions/problems/{problem['decisionId']}")
        if status != 200:
            return f"HTTP {status}"
        if body["worldRevision"] != problem["worldRevision"]:
            return "the ledger's revision differs from the computed one"
        if [o["optionId"] for o in body["options"]] != [o["optionId"] for o in problem["options"]]:
            return "the ledger's options differ from the computed ones"
        status, listed = api.get("/decisions/problems", limit=50)
        if status != 200 or not any(r["decisionId"] == problem["decisionId"] for r in listed["problems"]):
            return "the problem is not in the ledger list"
        return None
    rows.check("12. The decision ledger holds every problem as computed", ledger)

    def learning():
        status, body = api.get("/decisions/learning")
        if status != 200:
            return f"HTTP {status}"
        if "method" not in body or "hindsight" not in body["method"].lower() and "records" not in body["method"].lower():
            return "the learning method does not state that it reads records only"
        return None
    rows.check("13. Decision learning scores from the ledger and says it never re-runs with hindsight", learning)

    def mission_replay():
        status, body = api.get("/missions")
        if status != 200 or not body["missions"]:
            return "no mission"
        mission_id = body["missions"][0]["missionId"]
        status, state = api.post(f"/missions/{mission_id}/replay", {"offsetHours": 0}, headers=HEADERS)
        if status != 200:
            return f"replay HTTP {status}"
        if state["hidden"] is not None or state["hiddenCount"] < 1:
            return "the future is readable before the reveal"
        status, outcome = api.get(f"/missions/{mission_id}/outcome")
        if status != 403:
            return f"the outcome was served before the reveal (HTTP {status})"
        clock = datetime.fromisoformat(state["clock"].replace("Z", "+00:00"))
        for obs in state["visible"]:
            if datetime.fromisoformat(obs["observedAt"].replace("Z", "+00:00")) > clock:
                return "a visible observation is later than the clock"
        hull = state["fleet"][0]["vesselId"]
        status, problem = api.post(f"/missions/{mission_id}/decide", {"vesselId": hull}, headers=COMPANY)
        if status != 200:
            return f"decide HTTP {status}: {problem}"
        if not problem["evidence"].get("replay"):
            return "the replay decision is not stamped as a replay"
        rec = problem.get("recommendation") or {}
        chosen = rec.get("optionId") or problem["baselineOptionId"]
        status, _ = api.post(f"/missions/{mission_id}/choose", {"vesselId": hull, "optionId": chosen}, headers=HEADERS)
        if status != 200:
            return "choose refused"
        status, reveal = api.post(f"/missions/{mission_id}/reveal", {}, headers=HEADERS)
        if status != 200:
            return f"reveal HTTP {status}"
        card = reveal["scorecards"].get(hull)
        if not card or "regretHours" not in card or "learned" not in card:
            return "no scorecard with regret and lessons"
        if not reveal["mission"]["revealed"] or reveal["mission"]["hidden"] is None:
            return "the reveal did not open the chronology"
        return None
    rows.check("14. A historical mission hides its future until the reveal, then scores every option", mission_replay)

    def port_and_cargo():
        status, port = api.post("/decisions/problems", {"domain": "port", "portCode": "INNSA", "mode": mode, "bunchArrivals": 3}, headers=PORT)
        if status != 200:
            return f"port HTTP {status}: {port}"
        if port["domain"] != "PORT_BERTHING" or not port.get("frontier"):
            return "the port problem is not a decision problem with a frontier"
        status, cargo = api.post("/decisions/problems", {"domain": "cargo", "portCode": "INNSA", "mode": mode}, headers=COMPANY)
        if status != 200:
            return f"cargo HTTP {status}: {cargo}"
        if cargo["domain"] != "CARGO_CONNECTION" or not cargo.get("frontier"):
            return "the cargo problem is not a decision problem with a frontier"
        keys = {"decisionId", "options", "baselineOptionId", "frontier", "recommendation", "workflow"}
        for name, problem in (("port", port), ("cargo", cargo)):
            if not keys <= set(problem):
                return f"the {name} problem lacks {keys - set(problem)}"
            if not (problem["evidence"].get("ranking") or {}).get("weights"):
                return f"the {name} ranking does not state its weights"
        return None
    rows.check("15. Port and cargo decisions run through the same engine as vessel routing", port_and_cargo)

    return rows.report()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default=None, help="a running API, e.g. http://127.0.0.1:8000/api")
    parser.add_argument("--mode", default=os.getenv("PORTWATCH_LICENCE_MODE", "DEMO"))
    args = parser.parse_args()
    if args.base_url is None:
        os.environ.setdefault("PORTWATCH_LICENCE_MODE", args.mode)
    return run(Api(args.base_url), args.mode.upper())


if __name__ == "__main__":
    sys.exit(main())
