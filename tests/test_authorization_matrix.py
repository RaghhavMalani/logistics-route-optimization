"""The authorization matrix: every resource against every role, as the API
enforces it, and the identity model it rests on.

    ALLOW   the role gets the resource
    DENY    401 with no identity, 403 with the wrong one
    SCOPED  the role gets the resource filtered to what it holds; a probe of
            another tenant's record is a 403

The matrix below is the policy. The tests probe the live app with each
role's headers and assert the class of outcome; ``docs/SECURITY.md`` renders
the same table and a test checks the two have not drifted apart.

Identity is asserted from headers (``backend.app.identity``): no token is
verified. What the matrix proves is that, given the identity the headers
carry, the API refuses what that identity may not do -- and that no default
grants administration.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Tuple
from unittest import mock

NONE, ADMIN, PORT, COMPANY, VESSEL = "NONE", "NATIONAL_ADMIN", "PORT_AUTHORITY", "SHIPPING_COMPANY", "VESSEL_OPERATOR"
ROLES = (NONE, ADMIN, PORT, COMPANY, VESSEL)

HEADERS: Dict[str, Dict[str, str]] = {
    NONE: {},
    ADMIN: {"X-PortWatch-Role": ADMIN, "X-PortWatch-Actor": "matrix.admin"},
    PORT: {"X-PortWatch-Role": PORT, "X-PortWatch-Actor": "matrix.port", "X-PortWatch-Port": "INNSA",
           "X-PortWatch-Org": "JNPA"},
    COMPANY: {"X-PortWatch-Role": COMPANY, "X-PortWatch-Actor": "matrix.co", "X-PortWatch-Org": "PortWatch Demo Shipping"},
    VESSEL: {"X-PortWatch-Role": VESSEL, "X-PortWatch-Actor": "matrix.ves", "X-PortWatch-Vessels": "PWD-001",
             "X-PortWatch-Org": "PortWatch Demo Shipping"},
}

ALLOW, DENY, SCOPED = "ALLOW", "DENY", "SCOPED"

#: resource, method, path, body, expected per role in ROLES order.
#: NONE is judged in the default (asserted) identity mode, where a missing
#: role is national command everywhere except administration surfaces.
MATRIX: List[Tuple[str, str, str, object, Tuple[str, ...]]] = [
    ("WORLD", "GET", "/api/world/state?mode=DEMO", None, (ALLOW, ALLOW, ALLOW, ALLOW, ALLOW)),
    ("WORLD", "GET", "/api/world/cascades?mode=DEMO", None, (ALLOW, ALLOW, ALLOW, ALLOW, ALLOW)),
    ("WORLD", "POST", "/api/world/branches",
     {"mode": "DEMO", "assumptions": [{"kind": "close_chokepoint", "subject": "SUEZ", "value": 0.9}]},
     (ALLOW, ALLOW, ALLOW, ALLOW, ALLOW)),
    ("WORLD", "POST", "/api/world/clock", {"mode": "LIVE"}, (DENY, ALLOW, DENY, DENY, DENY)),
    ("AIS", "GET", "/api/world/ais/tracks?mode=DEMO", None, (ALLOW, ALLOW, ALLOW, ALLOW, ALLOW)),
    ("AIS", "GET", "/api/fabric/health?mode=DEMO", None, (ALLOW, ALLOW, ALLOW, ALLOW, ALLOW)),
    ("ATTENTION", "GET", "/api/attention?mode=DEMO&limit=5", None, (SCOPED, ALLOW, SCOPED, SCOPED, SCOPED)),
    ("DECISIONS", "GET", "/api/decisions/actions", None, (ALLOW, ALLOW, ALLOW, ALLOW, ALLOW)),
    ("DECISIONS", "GET", "/api/decisions/problems?limit=5", None, (SCOPED, ALLOW, SCOPED, SCOPED, SCOPED)),
    ("DECISIONS", "POST", "/api/decisions/problems", {"domain": "port", "portCode": "INNSA", "mode": "DEMO"},
     (DENY, DENY, ALLOW, DENY, DENY)),
    ("DECISIONS", "POST", "/api/decisions/problems", {"domain": "cargo", "portCode": "INNSA", "mode": "DEMO"},
     (ALLOW, ALLOW, ALLOW, ALLOW, DENY)),
    ("FINANCIAL", "GET", "/api/finance/basis", None, (ALLOW, ALLOW, ALLOW, ALLOW, ALLOW)),
    ("FINANCIAL", "GET", "/api/finance/tariffs", None, (ALLOW, ALLOW, ALLOW, ALLOW, ALLOW)),
    ("FINANCIAL", "POST", "/api/finance/assumptions", {"primitive": "charter_day", "value": 1000, "currency": "USD"},
     (DENY, ALLOW, DENY, DENY, DENY)),
    ("FINANCIAL", "POST", "/api/finance/assumptions/clear", {}, (DENY, ALLOW, DENY, DENY, DENY)),
    ("ADVISORIES", "GET", "/api/advisories", None, (DENY, ALLOW, SCOPED, SCOPED, SCOPED)),
    ("ADVISORIES", "GET", "/api/advisories/policy", None, (ALLOW, ALLOW, ALLOW, ALLOW, ALLOW)),
    ("ADVISORIES", "POST", "/api/advisories",
     {"kind": "speed", "portCode": "INNSA", "recipientVesselId": "PWD-001", "recipientVesselName": "MV Konkan",
      "recipientOrganisation": "PortWatch Demo Shipping", "recommendation": {"recommendedSpeedKn": 10},
      "reason": "authorization matrix probe: a speed advisory a master can evaluate"},
     (DENY, ALLOW, ALLOW, DENY, DENY)),
    ("MISSIONS", "GET", "/api/missions", None, (ALLOW, ALLOW, ALLOW, ALLOW, ALLOW)),
    ("MISSIONS", "POST", "/api/missions/suez-ever-given-2021/replay", {"offsetHours": 0}, (ALLOW, ALLOW, ALLOW, ALLOW, ALLOW)),
    ("ADMIN", "GET", "/api/admin/freshness", None, (DENY, ALLOW, DENY, DENY, DENY)),
    ("ADMIN", "GET", "/api/admin/readiness?mode=DEMO", None, (DENY, ALLOW, DENY, DENY, DENY)),
    ("ADMIN", "POST", "/api/admin/freshness/marine/refresh", {}, (DENY, ALLOW, DENY, DENY, DENY)),
    ("LEARNING", "GET", "/api/learning/summary", None, (ALLOW, ALLOW, ALLOW, DENY, DENY)),
    ("LEARNING", "GET", "/api/learning/policies", None, (ALLOW, ALLOW, ALLOW, DENY, DENY)),
    ("LEARNING", "GET", "/api/decisions/learning", None, (DENY, ALLOW, DENY, DENY, DENY)),
    ("LEARNING", "POST", "/api/learning/run", {}, (DENY, ALLOW, DENY, DENY, DENY)),
    ("LEARNING", "POST", "/api/learning/backfill", {"limit": 1}, (DENY, ALLOW, DENY, DENY, DENY)),
    ("DIAGNOSTICS", "GET", "/api/admin/diagnostics", None, (DENY, ALLOW, DENY, DENY, DENY)),
    ("AGENTS", "GET", "/api/agents/tools", None, (ALLOW, ALLOW, ALLOW, ALLOW, ALLOW)),
    ("LENSES", "GET", "/api/security/lens?mode=DEMO", None, (ALLOW, ALLOW, ALLOW, ALLOW, ALLOW)),
]


def render_matrix() -> str:
    """The matrix as the security document prints it."""
    lines = ["| resource | method | path | " + " | ".join(ROLES) + " |",
             "|---|---|---|" + "---|" * len(ROLES)]
    for resource, method, path, _body, expected in MATRIX:
        lines.append(f"| {resource} | {method} | `{path.split('?')[0]}` | " + " | ".join(expected) + " |")
    return "\n".join(lines)


def _classify(status: int) -> str:
    if status in (401, 403):
        return DENY
    if 200 <= status < 300:
        return ALLOW
    return f"HTTP {status}"


class MatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("PORTWATCH_LICENCE_MODE", "DEMO")
        os.environ["PORTWATCH_FRESHNESS_SCHEDULER"] = "0"
        os.environ.pop("PORTWATCH_IDENTITY_MODE", None)
        from fastapi.testclient import TestClient

        from backend.app.main import app
        from src.portwatch_os.decision.engine import get_engine, reset_engine
        from src.portwatch_os.finance.basis import AssumptionJournal

        reset_engine()
        get_engine().assumption_journal = AssumptionJournal(Path(tempfile.mkdtemp(prefix="pw-matrix-")) / "a.jsonl")
        cls.client = TestClient(app, raise_server_exceptions=False)

    def _call(self, method: str, path: str, body, role: str):
        headers = HEADERS[role]
        if method == "GET":
            return self.client.get(path, headers=headers)
        return self.client.post(path, json=body, headers=headers)

    def test_every_cell_of_the_matrix(self):
        failures = []
        for resource, method, path, body, expected in MATRIX:
            for role, want in zip(ROLES, expected):
                response = self._call(method, path, body, role)
                got = _classify(response.status_code)
                wanted = ALLOW if want == SCOPED else want
                if got != wanted:
                    failures.append(f"{resource} {method} {path} as {role}: wanted {want}, got {response.status_code} "
                                    f"{str(response.json().get('detail') if response.headers.get('content-type', '').startswith('application/json') else '')[:80]}")
        self.assertEqual(failures, [], "\n" + "\n".join(failures))

    def test_no_identity_never_reaches_an_administration_surface(self):
        for path in ("/api/admin/freshness", "/api/admin/diagnostics", "/api/admin/readiness?mode=DEMO",
                     "/api/decisions/learning"):
            self.assertEqual(self.client.get(path).status_code, 401, path)
        self.assertEqual(self.client.post("/api/learning/run", json={}).status_code, 401)
        self.assertEqual(self.client.post("/api/world/clock", json={"mode": "LIVE"}).status_code, 401)

    def test_the_admin_flag_grants_nothing(self):
        flagged = {**HEADERS[COMPANY], "X-PortWatch-Admin": "1"}
        self.assertEqual(self.client.get("/api/admin/diagnostics", headers=flagged).status_code, 403)
        self.assertEqual(self.client.get("/api/decisions/learning", headers=flagged).status_code, 403)
        # A recipient claiming the flag still sees only its own advisories.
        listed = self.client.get("/api/advisories", headers=flagged)
        self.assertEqual(listed.status_code, 200)
        for advisory in listed.json().get("advisories", []):
            self.assertIn(advisory.get("recipientOrganisation"), ("PortWatch Demo Shipping", None))
        policy = self.client.get("/api/advisories/policy").json()
        self.assertFalse(policy.get("identity", {}).get("adminFlagHonoured", True))

    def test_required_identity_mode_refuses_a_request_with_no_role(self):
        with mock.patch.dict(os.environ, {"PORTWATCH_IDENTITY_MODE": "required"}):
            self.assertEqual(self.client.get("/api/world/state?mode=DEMO").status_code, 401)
            self.assertEqual(self.client.get("/api/attention?mode=DEMO").status_code, 401)
            self.assertEqual(self.client.get("/api/world/state?mode=DEMO", headers=HEADERS[COMPANY]).status_code, 200)
            readiness = self.client.get("/api/admin/readiness?mode=DEMO", headers=HEADERS[ADMIN]).json()
            identity = next(c for c in readiness["checks"] if c["name"] == "identity_mode")
            self.assertEqual(identity["status"], "PASS")
        readiness = self.client.get("/api/admin/readiness?mode=COMMERCIAL", headers=HEADERS[ADMIN]).json()
        identity = next(c for c in readiness["checks"] if c["name"] == "identity_mode")
        self.assertEqual(identity["status"], "WARN")
        self.assertIn("asserted", identity["detail"])

    def test_the_document_carries_this_matrix(self):
        doc = Path(__file__).resolve().parents[1] / "docs" / "SECURITY.md"
        self.assertIn(render_matrix(), doc.read_text(encoding="utf-8"))


class DecisionScopeTests(unittest.TestCase):
    """A decision is read and moved by the people it belongs to, and nobody else."""

    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("PORTWATCH_LICENCE_MODE", "DEMO")
        os.environ["PORTWATCH_FRESHNESS_SCHEDULER"] = "0"
        from fastapi.testclient import TestClient

        from backend.app.main import app

        cls.client = TestClient(app, raise_server_exceptions=False)

    def _vessel_problem(self, headers):
        queue = self.client.get("/api/attention?mode=DEMO&limit=25", headers=headers).json()
        item = next((i for i in queue["items"] if i.get("subjectType") == "vessel" and i.get("actionable")), None)
        if item is None:
            self.skipTest("no actionable hull in the register")
        response = self.client.post("/api/decisions/problems", json={
            "domain": "vessel", "eventId": item["cascadeId"].split(":")[-1], "vesselId": item["subjectId"], "mode": "DEMO",
        }, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_a_companys_decision_is_its_own(self):
        mine = self._vessel_problem(HEADERS[COMPANY])
        did = mine["decisionId"]
        other_company = {**HEADERS[COMPANY], "X-PortWatch-Org": "Another Carrier Ltd", "X-PortWatch-Actor": "rival"}
        other_port = {**HEADERS[PORT], "X-PortWatch-Port": "INMAA"}
        self.assertEqual(self.client.get(f"/api/decisions/problems/{did}", headers=HEADERS[COMPANY]).status_code, 200)
        self.assertEqual(self.client.get(f"/api/decisions/problems/{did}", headers=HEADERS[ADMIN]).status_code, 200)
        self.assertEqual(self.client.get(f"/api/decisions/problems/{did}", headers=other_company).status_code, 403)
        self.assertEqual(self.client.get(f"/api/decisions/problems/{did}", headers=other_port).status_code, 403)
        moved = self.client.post(f"/api/decisions/problems/{did}/transition", json={"target": "REVIEWED"}, headers=other_company)
        self.assertEqual(moved.status_code, 403)
        self.assertIn("may not read or move", moved.json()["detail"])
        outcome = self.client.post(f"/api/decisions/problems/{did}/outcome",
                                   json={"actualAction": "KEEP_PLAN", "observed": {"eta": 1}}, headers=other_company)
        self.assertEqual(outcome.status_code, 403)
        listed = self.client.get("/api/decisions/problems?limit=100", headers=other_company).json()
        self.assertNotIn(did, {r["decisionId"] for r in listed["problems"]})
        listed = self.client.get("/api/decisions/problems?limit=100", headers=HEADERS[COMPANY]).json()
        self.assertIn(did, {r["decisionId"] for r in listed["problems"]})

    def test_a_vessel_operator_sees_decisions_about_its_own_hull(self):
        mine = self._vessel_problem(HEADERS[COMPANY])
        did, subject = mine["decisionId"], mine["subject"]["id"]
        own_hull = {**HEADERS[VESSEL], "X-PortWatch-Org": "Somebody Else", "X-PortWatch-Vessels": subject}
        other_hull = {**HEADERS[VESSEL], "X-PortWatch-Org": "Somebody Else", "X-PortWatch-Vessels": "ZZZ-999"}
        self.assertEqual(self.client.get(f"/api/decisions/problems/{did}", headers=own_hull).status_code, 200)
        self.assertEqual(self.client.get(f"/api/decisions/problems/{did}", headers=other_hull).status_code, 403)

    def test_a_port_authoritys_decision_stays_at_its_port(self):
        response = self.client.post("/api/decisions/problems", json={"domain": "port", "portCode": "INNSA", "mode": "DEMO"},
                                    headers=HEADERS[PORT])
        self.assertEqual(response.status_code, 200, response.text)
        did = response.json()["decisionId"]
        other_port = {**HEADERS[PORT], "X-PortWatch-Port": "INMAA"}
        self.assertEqual(self.client.get(f"/api/decisions/problems/{did}", headers=HEADERS[PORT]).status_code, 200)
        self.assertEqual(self.client.get(f"/api/decisions/problems/{did}", headers=other_port).status_code, 403)
        self.assertEqual(self.client.get(f"/api/decisions/problems/{did}", headers=HEADERS[COMPANY]).status_code, 403)


if __name__ == "__main__":
    unittest.main()
