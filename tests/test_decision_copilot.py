"""The Copilot's decision queries: the engine computes, the agent explains.

What these tests defend: each of the product's decision phrasings routes to
the decision intent; the answer names only options the tool returned; a
preference the objectives cannot measure is reported as unmeasured rather
than answered; the SHOW_DECISION command is grounded in the tool call and
follows the question's focus; the run ends at the Critic.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from src.portwatch_os.agents.decision_tools import compared_actions, preference_of, wants_baseline, within_hours
from src.portwatch_os.agents.orchestrator import classify_intent

BUNDLE = Path(__file__).resolve().parents[1] / "data" / "cache" / "news_bundle.json"
#: The instant the shipped register is live at; the events lapse 72 h later.
LIVE_AT = "2026-09-08T12:00:00+00:00"


class PhrasingTests(unittest.TestCase):
    def test_every_decision_phrasing_routes_to_the_decision_intent(self):
        for question in (
            "What should MV Konkan do?",
            "Show me the safest option.",
            "What's the cheapest option?",
            "What happens if it keeps its current route?",
            "Can it avoid the storm and still make Chennai within 24h?",
            "Compare rerouting with slow steaming.",
        ):
            intent, basis = classify_intent(question)
            self.assertEqual(intent.key, "decision", question)
            self.assertTrue(intent.high_impact)

    def test_preferences_and_clauses_are_read_from_the_question(self):
        self.assertEqual(preference_of("show me the safest option"), "LOWEST_RISK")
        self.assertEqual(preference_of("what's the cheapest option?"), "LOWEST_COST")
        self.assertIsNone(preference_of("what should MV Konkan do?"))
        self.assertTrue(wants_baseline("what happens if it keeps its current route?"))
        self.assertEqual(within_hours("still make Chennai within 24h?"), 24.0)
        self.assertEqual(set(compared_actions("compare rerouting with slow steaming")), {"REROUTE", "SLOW_STEAM"})


@unittest.skipUnless(BUNDLE.exists(), "the pipeline's news bundle is not exported on this machine")
class CopilotRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("PORTWATCH_LICENCE_MODE", "DEMO")
        from fastapi.testclient import TestClient

        from backend.app.main import app

        cls.client = TestClient(app)
        cls.headers = {"X-PortWatch-Role": "SHIPPING_COMPANY", "X-PortWatch-Actor": "ops.desk",
                       "X-PortWatch-Org": "PortWatch Demo Shipping"}
        # The hull the register exposes soonest at the live instant.
        r = cls.client.get(f"/api/attention?mode=DEMO&limit=10&at={LIVE_AT}", headers=cls.headers)
        items = [i for i in r.json()["items"] if i["subjectType"] == "vessel" and i["actionable"]]
        cls.subject = items[0] if items else None

    def _ask(self, question):
        r = self.client.post("/api/agents/run", json={"question": question, "role": "SHIPPING_COMPANY",
                                                      "context": {"at": LIVE_AT}}, headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_the_answer_names_only_computed_options_and_is_grounded(self):
        if self.subject is None:
            self.skipTest("no actionable hull at the live instant")
        run = self._ask(f"What should {self.subject['subjectLabel']} do?")
        self.assertEqual(run["intent"], "decision")
        show = next((s for s in run["spatial"] if s["kind"] == "SHOW_DECISION"), None)
        self.assertIsNotNone(show)
        self.assertEqual(show["evidenceTool"], "portwatch.decision.solve")
        self.assertEqual(show["safety"], "UI")
        problem = self.client.get(f"/api/decisions/problems/{show['subject']}").json()
        labels = [o["label"] for o in problem["options"]]
        self.assertTrue(any(label in run["summary"] for label in labels), run["summary"])
        self.assertEqual(show["params"]["optionId"], problem["recommendation"]["optionId"])
        self.assertIn(run["critic"]["verdict"], ("APPROVED", "MODIFIED"))

    def test_cheapest_is_unmeasured_without_a_cost_basis(self):
        if self.subject is None:
            self.skipTest("no actionable hull at the live instant")
        run = self._ask(f"What's the cheapest option for {self.subject['subjectLabel']}?")
        self.assertIn("not measured", run["summary"])
        self.assertIn("cost basis", run["summary"])

    def test_keeping_the_route_focuses_the_baseline(self):
        if self.subject is None:
            self.skipTest("no actionable hull at the live instant")
        run = self._ask(f"What happens if {self.subject['subjectLabel']} keeps its current route?")
        self.assertIn("If unchanged", run["summary"])
        show = next(s for s in run["spatial"] if s["kind"] == "SHOW_DECISION")
        self.assertEqual(show["params"]["optionId"], "keep_plan")


if __name__ == "__main__":
    unittest.main()
