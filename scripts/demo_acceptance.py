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

    def get(self, path: str, **params: Any) -> Tuple[int, Any]:
        query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        url = f"{path}?{query}" if query else path
        if self._client is not None:
            response = self._client.get(f"/api{url}", headers=HEADERS)
            return response.status_code, response.json()
        request = self._urllib.Request(f"{self.base_url}{url}", headers=HEADERS)
        with self._urllib.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def post(self, path: str, body: Dict[str, Any]) -> Tuple[int, Any]:
        if self._client is not None:
            response = self._client.post(f"/api{path}", json=body, headers=HEADERS)
            return response.status_code, response.json()
        data = json.dumps(body).encode("utf-8")
        request = self._urllib.Request(
            f"{self.base_url}{path}", data=data, headers={**HEADERS, "Content-Type": "application/json"},
        )
        with self._urllib.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))


HEADERS = {"X-PortWatch-Actor": "acceptance", "X-PortWatch-Role": "NATIONAL_ADMIN"}


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
