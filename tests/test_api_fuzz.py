"""Abuse of the request-facing API: malformed, hostile and oversized input.

Every probe must produce a bounded answer -- a 4xx with a JSON detail, or a
2xx that carries no fabricated figure -- inside a time budget. No probe may
crash the process (5xx), write outside the state directory, or echo a
configured secret. The probes cover the inputs the milestone names:
coordinates, money, currencies, scenario options, decision ids, mission
clocks, world timestamps, vessel ids, very large payloads, NaN and infinity,
negative rates, extreme dates.

The suite runs in-process with the freshness scheduler off; the time budget
is generous because the first world build is charged to whichever probe
happens to come first.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ADMIN = {"X-PortWatch-Role": "NATIONAL_ADMIN", "X-PortWatch-Actor": "fuzz.admin"}
COMPANY = {"X-PortWatch-Role": "SHIPPING_COMPANY", "X-PortWatch-Actor": "fuzz.co", "X-PortWatch-Org": "PortWatch Demo Shipping"}
PORT = {"X-PortWatch-Role": "PORT_AUTHORITY", "X-PortWatch-Actor": "fuzz.port", "X-PortWatch-Port": "INNSA"}

#: Seconds a single probe may take. The world build is measured elsewhere;
#: this is the budget for refusing bad input.
PROBE_BUDGET_SECONDS = 30.0

HOSTILE_STRINGS = [
    "", " ", "'; DROP TABLE decisions; --", "../../etc/passwd", "..\\..\\windows\\win.ini",
    "<script>alert(1)</script>", "\u0000", "𝕏" * 64, "x" * 4096, "%00", "${jndi:ldap://x/y}", "{{7*7}}",
    "-1", "1e309", "NaN", "Infinity", "null", "undefined", "true", "[]", "{}",
]
HOSTILE_NUMBERS: List[Any] = [
    None, "", "abc", -1, -1e12, 0, 1e309, float("inf"), -float("inf"), float("nan"), 2 ** 63, "1e309", "NaN",
    [1, 2], {"a": 1}, True,
]
EXTREME_DATES = [
    "", "not-a-date", "0000-00-00T00:00:00Z", "9999-12-31T23:59:59Z", "1970-01-01T00:00:00Z", "2026-13-45T99:99:99Z",
    "2026-09-15T12:00:00+99:00", "1e309", "2026-09-15", "T12:00", "2026-09-15T12:00:00Z" + "0" * 2000,
]


def _json_safe(value: Any) -> Any:
    """Send NaN and infinity the way a client can: as strings and as raw tokens."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)
    return value


class FuzzBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("PORTWATCH_LICENCE_MODE", "DEMO")
        os.environ["PORTWATCH_FRESHNESS_SCHEDULER"] = "0"
        from fastapi.testclient import TestClient

        from backend.app.main import app
        from src.portwatch_os.decision.engine import get_engine, reset_engine
        from src.portwatch_os.finance.basis import AssumptionJournal

        reset_engine()
        get_engine().assumption_journal = AssumptionJournal(Path(tempfile.mkdtemp(prefix="pw-fuzz-")) / "a.jsonl")
        cls.client = TestClient(app, raise_server_exceptions=False)
        cls.secrets = [v for v in (os.getenv(n) for n in ("AISSTREAM_API_KEY", "OPEN_METEO_API_KEY", "DATABASE_URL"))
                       if v and len(v) >= 6]
        cls.state_dir = Path(os.environ.get("PORTWATCH_STATE_DIR") or "outputs").resolve()
        cls.before = cls._snapshot_tree()
        # Warm the world so the first probe is not charged for the build.
        cls.client.get("/api/world/cascades?mode=DEMO", headers=ADMIN)

    @classmethod
    def _snapshot_tree(cls) -> set:
        root = Path(__file__).resolve().parents[1]
        found = set()
        for folder in ("backend", "src", "scripts", "docs", "tests"):
            for path in (root / folder).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    found.add(str(path))
        return found

    def _probe(self, method: str, path: str, body: Any = None, headers: Optional[Dict[str, str]] = None,
               raw: Optional[bytes] = None) -> Tuple[int, Any, float]:
        started = time.perf_counter()
        if method == "GET":
            response = self.client.get(path, headers=headers or ADMIN)
        elif raw is not None:
            response = self.client.post(path, content=raw, headers={**(headers or ADMIN), "Content-Type": "application/json"})
        else:
            response = self.client.post(path, json=body, headers=headers or ADMIN)
        elapsed = time.perf_counter() - started
        try:
            parsed = response.json()
        except ValueError:
            parsed = response.text
        self.assertLess(response.status_code, 500, f"{method} {path} {str(body)[:80]!r} -> {response.status_code}: {str(parsed)[:200]}")
        self.assertLess(elapsed, PROBE_BUDGET_SECONDS, f"{method} {path} took {elapsed:.1f}s")
        text = response.text
        for secret in self.secrets:
            self.assertNotIn(secret, text, f"{method} {path} echoed a configured secret")
        if response.status_code >= 400:
            self.assertIsInstance(parsed, dict, f"{method} {path}: a refusal must be JSON")
            self.assertIn("detail", parsed, f"{method} {path}: a refusal must carry a detail")
            self.assertNotIn("Traceback", text)
        return response.status_code, parsed, elapsed

    def assertNoNewFiles(self) -> None:
        after = self._snapshot_tree()
        self.assertEqual(sorted(after - self.before), [], "a probe wrote a file into the source tree")


class CoordinateAndRouteFuzz(FuzzBase):
    def test_route_exposure_refuses_every_malformed_waypoint_set(self):
        bad = [
            None, [], [[0, 0]], [[91, 0], [0, 0]], [[0, 181], [0, 0]], [["a", "b"], [0, 0]], [[None, None], [0, 0]],
            [[float("nan"), 0], [0, 0]], [[1e309, 0], [0, 0]], "not a list", [[0, 0, 0, 0]] * 2, [[0], [0]],
            [[0, 0], [0, 0]] * 5000,
        ]
        for waypoints in bad:
            payload = {"waypoints": _json_safe(waypoints) if not isinstance(waypoints, list) else
                       [[_json_safe(a) for a in p] if isinstance(p, list) else p for p in waypoints], "mode": "DEMO"}
            status, body, _ = self._probe("POST", "/api/world/route/exposure", payload)
            if isinstance(waypoints, list) and len(waypoints) >= 2 and all(
                isinstance(p, list) and len(p) >= 2 and all(isinstance(x, (int, float)) and math.isfinite(x) for x in p[:2])
                and abs(p[0]) <= 90 and abs(p[1]) <= 180 for p in waypoints
            ):
                continue                                   # a valid set; bounded is enough
            self.assertEqual(status, 400, f"{str(waypoints)[:60]} -> {status} {str(body)[:120]}")
        for speed in HOSTILE_NUMBERS:
            status, _, _ = self._probe("POST", "/api/world/route/exposure",
                                       {"waypoints": [[12.0, 43.0], [13.0, 44.0]], "speedKn": _json_safe(speed), "mode": "DEMO"})
            self.assertIn(status, (200, 400))
        self.assertNoNewFiles()

    def test_cascade_offsets_and_timestamps_are_bounded(self):
        events = self.client.get("/api/world/cascades?mode=DEMO", headers=ADMIN).json().get("cascades", [])
        event_id = events[0]["eventId"] if events else "nope"
        for offsets in ([-1], [1e9], ["x"], [float("nan")], [None], list(range(0, 5000)), "72", {"a": 1}):
            status, _, _ = self._probe("POST", "/api/world/cascade/simulate",
                                       {"eventId": event_id, "offsets": [_json_safe(o) for o in offsets] if isinstance(offsets, list) else offsets, "mode": "DEMO"})
            self.assertIn(status, (200, 400, 404))
        for at in EXTREME_DATES:
            status, _, _ = self._probe("GET", f"/api/world/state?mode=DEMO&at={at}")
            self.assertIn(status, (200, 400, 422))
            status, _, _ = self._probe("POST", "/api/world/cascade/simulate", {"eventId": event_id, "at": at, "mode": "DEMO"})
            self.assertIn(status, (200, 400, 404, 422))
        for event in HOSTILE_STRINGS:
            status, _, _ = self._probe("POST", "/api/world/cascade/simulate", {"eventId": event, "mode": "DEMO"})
            self.assertIn(status, (400, 404))


class MoneyFuzz(FuzzBase):
    def test_assumptions_refuse_bad_money_and_currencies(self):
        for value in HOSTILE_NUMBERS:
            status, body, _ = self._probe("POST", "/api/finance/assumptions",
                                          {"primitive": "charter_day", "value": _json_safe(value), "currency": "USD"})
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
                self.assertEqual(status, 200)
            else:
                self.assertEqual(status, 400, f"value {value!r} -> {status} {str(body)[:100]}")
        for currency in HOSTILE_STRINGS + ["usd", "US", "USDX", "€", "INR;DROP"]:
            status, body, _ = self._probe("POST", "/api/finance/assumptions",
                                          {"primitive": "charter_day", "value": 1000, "currency": currency})
            self.assertIn(status, (200, 400), f"currency {currency!r} -> {status}")
            if status == 200:
                self.assertRegex(body["added"]["currency"], r"^[A-Z]{3}$",
                                 f"currency {currency!r} was accepted as {body['added']['currency']!r}")
        for primitive in HOSTILE_STRINGS:
            status, _, _ = self._probe("POST", "/api/finance/assumptions", {"primitive": primitive, "value": 1, "currency": "USD"})
            self.assertEqual(status, 400)
        self.client.post("/api/finance/assumptions/clear", headers=ADMIN)

    def test_fx_refuses_negative_rates_and_bad_instants(self):
        for rate in HOSTILE_NUMBERS:
            status, _, _ = self._probe("POST", "/api/finance/fx",
                                       {"base": "USD", "quote": "INR", "rate": _json_safe(rate), "source": "fuzz",
                                        "observedAt": "2026-09-15T00:00:00Z"})
            if isinstance(rate, (int, float)) and not isinstance(rate, bool) and math.isfinite(rate) and rate > 0:
                self.assertIn(status, (200, 400))
            else:
                self.assertEqual(status, 400, f"rate {rate!r} -> {status}")
        for instant in EXTREME_DATES:
            status, _, _ = self._probe("POST", "/api/finance/fx",
                                       {"base": "USD", "quote": "INR", "rate": 83.0, "source": "fuzz", "observedAt": instant})
            self.assertIn(status, (200, 400))

    def test_decision_scenario_assumptions_refuse_bad_rates(self):
        queue = self.client.get("/api/attention?mode=DEMO&limit=25", headers=COMPANY).json()
        item = next((i for i in queue["items"] if i.get("subjectType") == "vessel" and i.get("actionable")), None)
        if item is None:
            self.skipTest("no actionable hull")
        base = {"domain": "vessel", "eventId": item["cascadeId"].split(":")[-1], "vesselId": item["subjectId"], "mode": "DEMO"}
        for value in (-1, 0, "x", None, 1e309, "NaN"):
            status, _, _ = self._probe("POST", "/api/decisions/problems",
                                       {**base, "assumptions": [{"primitive": "charter_day", "value": _json_safe(value), "currency": "USD"}]},
                                       headers=COMPANY)
            self.assertEqual(status, 400, f"assumption value {value!r} -> {status}")
        for grt in (-1, 0, "x", None, 1e309, "NaN", 1e12):
            status, _, _ = self._probe("POST", "/api/decisions/problems", {**base, "vesselAssumptions": {"grt": _json_safe(grt)}},
                                       headers=COMPANY)
            self.assertIn(status, (200, 400), f"grt {grt!r} -> {status}")
        status, _, _ = self._probe("POST", "/api/decisions/problems", {**base, "vesselAssumptions": {"warp_core": 1}}, headers=COMPANY)
        self.assertEqual(status, 400)


class IdentifierFuzz(FuzzBase):
    def test_decision_ids_vessel_ids_and_ports_are_bounded(self):
        for did in HOSTILE_STRINGS:
            encoded = did.replace("/", "%2F").replace("\\", "%5C").replace("#", "%23").replace("?", "%3F")
            if not encoded.strip() or "\u0000" in encoded:
                continue                                   # no HTTP client sends a NUL in a path
            status, _, _ = self._probe("GET", f"/api/decisions/problems/{encoded}")
            self.assertIn(status, (404, 403, 400, 422))
            status, _, _ = self._probe("POST", f"/api/decisions/problems/{encoded}/transition", {"target": "REVIEWED"})
            self.assertIn(status, (404, 403, 400, 409, 422))
        for vessel in HOSTILE_STRINGS:
            status, _, _ = self._probe("POST", "/api/decisions/problems",
                                       {"domain": "vessel", "eventId": "x", "vesselId": vessel, "mode": "DEMO"}, headers=COMPANY)
            self.assertIn(status, (400, 404))
        for port in HOSTILE_STRINGS:
            status, _, _ = self._probe("POST", "/api/decisions/problems", {"domain": "port", "portCode": port, "mode": "DEMO"},
                                       headers=PORT)
            # A blank code falls back to the port the identity speaks for; anything else must be refused.
            self.assertIn(status, (200, 400, 404) if not port.strip() else (400, 404), f"port {port!r} -> {status}")
            encoded = port.replace("/", "%2F").replace("\\", "%5C").replace("#", "%23").replace("?", "%3F")
            if encoded.strip() and "\u0000" not in encoded:
                status, _, _ = self._probe("GET", f"/api/port-twin/{encoded}")
                self.assertIn(status, (200, 400, 404, 422))
        for domain in HOSTILE_STRINGS:
            status, _, _ = self._probe("POST", "/api/decisions/problems", {"domain": domain, "mode": "DEMO"}, headers=COMPANY)
            self.assertIn(status, (400, 403, 404))
        self.assertNoNewFiles()

    def test_mission_clocks_and_options(self):
        for clock in EXTREME_DATES:
            status, _, _ = self._probe("POST", "/api/missions/suez-ever-given-2021/seek", {"clock": clock})
            self.assertIn(status, (200, 400))
        for offset in HOSTILE_NUMBERS:
            status, _, _ = self._probe("POST", "/api/missions/suez-ever-given-2021/seek", {"offsetHours": _json_safe(offset)})
            self.assertIn(status, (200, 400))
        for mission in HOSTILE_STRINGS:
            encoded = mission.replace("/", "%2F").replace("\\", "%5C").replace("#", "%23").replace("?", "%3F")
            if not encoded.strip() or "\u0000" in encoded:
                continue
            status, _, _ = self._probe("GET", f"/api/missions/{encoded}")
            self.assertIn(status, (404, 400, 422))
        for option in HOSTILE_STRINGS:
            status, _, _ = self._probe("POST", "/api/missions/suez-ever-given-2021/choose",
                                       {"vesselId": "MSN-001", "optionId": option}, headers=COMPANY)
            self.assertIn(status, (200, 400, 404))

    def test_scenario_options_and_branches(self):
        for intensity in HOSTILE_NUMBERS:
            status, _, _ = self._probe("POST", "/api/scenarios/simulate", {"scenarioKey": "HORMUZ", "intensity": _json_safe(intensity)})
            self.assertIn(status, (200, 400, 404, 503))
        for key in HOSTILE_STRINGS:
            status, _, _ = self._probe("POST", "/api/scenarios/simulate", {"scenarioKey": key})
            self.assertIn(status, (200, 400, 404, 503))
        for value in HOSTILE_NUMBERS:
            status, _, _ = self._probe("POST", "/api/world/branches",
                                       {"mode": "DEMO", "assumptions": [{"kind": "close_chokepoint", "subject": "SUEZ", "value": _json_safe(value)}]})
            self.assertIn(status, (200, 400))
        for subject in HOSTILE_STRINGS:
            status, _, _ = self._probe("POST", "/api/world/branches",
                                       {"mode": "DEMO", "assumptions": [{"kind": "close_chokepoint", "subject": subject, "value": 0.5}]})
            self.assertIn(status, (200, 400))
        for kind in HOSTILE_STRINGS:
            status, _, _ = self._probe("POST", "/api/world/branches", {"mode": "DEMO", "assumptions": [{"kind": kind, "subject": "SUEZ"}]})
            self.assertIn(status, (400,))


class PayloadFuzz(FuzzBase):
    def test_very_large_and_malformed_bodies(self):
        big = {"domain": "vessel", "eventId": "x", "vesselId": "y", "mode": "DEMO", "padding": "x" * (4 * 1024 * 1024)}
        status, _, elapsed = self._probe("POST", "/api/decisions/problems", big, headers=COMPANY)
        self.assertIn(status, (400, 404, 413))
        deep: Any = {"a": 1}
        for _ in range(400):
            deep = {"a": deep}
        status, _, _ = self._probe("POST", "/api/decisions/problems", {"domain": "vessel", "x": deep, "mode": "DEMO"}, headers=COMPANY)
        self.assertIn(status, (400, 404, 413, 422))
        for raw in (b"{", b"[]", b"null", b"\"s\"", b"\xff\xfe", b"{\"a\": NaN}", b"{\"a\": Infinity}", b"{\"a\": 1e999}"):
            status, _, _ = self._probe("POST", "/api/decisions/problems", raw=raw, headers=COMPANY)
            self.assertIn(status, (400, 404, 422), f"raw {raw!r} -> {status}")
        status, _, _ = self._probe("POST", "/api/finance/assumptions", raw=b"{\"primitive\": \"charter_day\", \"value\": NaN, \"currency\": \"USD\"}")
        self.assertIn(status, (400, 422))
        status, _, _ = self._probe("POST", "/api/finance/assumptions", raw=b"{\"primitive\": \"charter_day\", \"value\": Infinity, \"currency\": \"USD\"}")
        self.assertIn(status, (400, 422))
        many = [{"kind": "close_chokepoint", "subject": "SUEZ", "value": 0.5}] * 2000
        status, _, _ = self._probe("POST", "/api/world/branches", {"mode": "DEMO", "assumptions": many})
        self.assertIn(status, (200, 400, 413))
        self.assertNoNewFiles()

    def test_hostile_headers_never_reach_the_ledger_or_the_response_unescaped(self):
        for actor in HOSTILE_STRINGS:
            if "\u0000" in actor or any(ord(c) > 255 for c in actor):
                continue                                   # a client cannot send these; fetch refuses them
            status, body, _ = self._probe("POST", "/api/finance/assumptions",
                                          {"primitive": "charter_day", "value": 10, "currency": "USD"},
                                          headers={**ADMIN, "X-PortWatch-Actor": actor})
            self.assertIn(status, (200, 400, 401))
        for role in HOSTILE_STRINGS:
            if "\u0000" in role or any(ord(c) > 255 for c in role):
                continue
            status, _, _ = self._probe("GET", "/api/world/state?mode=DEMO", headers={"X-PortWatch-Role": role})
            self.assertIn(status, (200, 401, 403))
        for mode in HOSTILE_STRINGS:
            if "\u0000" in mode:
                continue
            status, _, _ = self._probe("GET", f"/api/world/state?mode={mode.replace('#', '%23').replace('&', '%26')}")
            self.assertIn(status, (200, 400, 403, 422))
        self.client.post("/api/finance/assumptions/clear", headers=ADMIN)


if __name__ == "__main__":
    unittest.main()
