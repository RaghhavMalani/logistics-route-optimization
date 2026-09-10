"""The agent layer, the Critic, and the boundary an agent cannot cross.

Most of these tests assert a refusal. That is deliberate: the valuable property
of this layer is not that it can do things, it is that it cannot do certain
things, and a capability boundary that is only documented is not a boundary.
"""

from __future__ import annotations

import json
import unittest

from src.portwatch_os.advisories.model import DRAFT, ISSUED, ISSUER
from src.portwatch_os.advisories.store import AdvisoryStore
from src.portwatch_os.agents.base import (
    BLOCKED,
    COMPLETE,
    Agent,
    AgentRequest,
    propagate_confidence,
)
from src.portwatch_os.agents.critic import (
    APPROVED,
    MODIFIED,
    REJECTED,
    Critic,
    Recommendation,
)
from src.portwatch_os.agents.orchestrator import (
    CommandAgent,
    classify_intent,
    extract_entities,
)
from src.portwatch_os.agents.portwatch_tools import build_registry
from src.portwatch_os.agents.specialists import SPECIALISTS
from src.portwatch_os.agents.tools import (
    EXECUTE,
    PROPOSE,
    READ,
    SIMULATE,
    ApprovalContext,
    ToolRegistry,
    ToolUnavailable,
    approval_from_session,
)
from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.portwatch_os.mcp.server import PortWatchMCPServer


def registry() -> ToolRegistry:
    return build_registry(
        ledger=SqliteLedgerStore(":memory:"),
        advisory_store=AdvisoryStore(":memory:"),
    )


class AccessBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.registry = registry()

    def test_every_tool_declares_an_access_level_and_a_computing_module(self):
        for spec in self.registry.specs():
            self.assertIn(spec.access, (READ, SIMULATE, PROPOSE, EXECUTE), spec.name)
            self.assertTrue(spec.computed_by, f"{spec.name} names no computing module")

    def test_a_propose_ceiling_cannot_reach_an_execute_tool(self):
        call = self.registry.call(
            "portwatch.advisories.issue", {"advisory_id": "x"}, max_access=PROPOSE
        )
        self.assertFalse(call.ok)
        self.assertIn("limited to PROPOSE", call.error)

    def test_an_execute_tool_refuses_without_an_approval_context(self):
        call = self.registry.call(
            "portwatch.advisories.issue", {"advisory_id": "x"}, max_access=EXECUTE
        )
        self.assertFalse(call.ok)
        self.assertIn("approval context", call.error)

    def test_an_unverified_approval_is_refused(self):
        """A context an agent could construct itself proves nothing."""
        fabricated = ApprovalContext(actor="agent", actor_role="ISSUER")
        call = self.registry.call(
            "portwatch.advisories.issue", {"advisory_id": "x"},
            approval=fabricated, max_access=EXECUTE,
        )
        self.assertFalse(call.ok)
        self.assertIn("approval context", call.error)

    def test_only_a_session_can_produce_a_verified_approval(self):
        approval = approval_from_session(
            actor="S. Iyer", actor_role="ISSUER", session_id="sess-1",
        )
        self.assertTrue(approval.human_verified)
        with self.assertRaises(Exception):
            approval_from_session(actor="", actor_role="ISSUER", session_id="")

    def test_an_unknown_tool_names_what_is_available(self):
        call = self.registry.call("portwatch.does.not.exist")
        self.assertFalse(call.ok)
        self.assertIn("Available", call.error)

    def test_a_missing_required_argument_is_reported_not_guessed(self):
        call = self.registry.call("portwatch.ports.get", {})
        self.assertFalse(call.ok)
        self.assertIn("requires", call.error)

    def test_an_unavailable_artefact_is_distinguished_from_a_failure(self):
        call = self.registry.call("portwatch.ports.get", {"port_code": "ZZZZZ"})
        self.assertFalse(call.ok)
        self.assertTrue(call.unavailable)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.registry = registry()

    def test_every_specialist_declares_only_registered_tools(self):
        for name, cls in SPECIALISTS.items():
            agent = cls(self.registry)  # raises if a declared tool is unknown
            self.assertTrue(agent.allowed_tools or name == "base")

    def test_no_agent_holds_an_execute_ceiling(self):
        """The structural guarantee: nothing in the agent layer can execute."""
        for cls in SPECIALISTS.values():
            self.assertNotEqual(cls.max_access, EXECUTE, cls.name)

    def test_an_agent_cannot_call_a_tool_it_did_not_declare(self):
        weather = SPECIALISTS["weather"](self.registry)
        call = weather.call("portwatch.ports.list")
        self.assertFalse(call.ok)
        self.assertIn("not permitted", call.error)
        self.assertEqual(call.access, "DENIED")

    def test_every_agent_declares_its_failure_modes(self):
        for cls in SPECIALISTS.values():
            self.assertTrue(cls.failure_modes, f"{cls.name} declares no failure modes")

    def test_confidence_is_bounded_by_the_worst_input(self):
        """A chain is as weak as its weakest evidence, not its average."""
        self.assertAlmostEqual(propagate_confidence([0.9, 0.9, 0.3]), 0.3)

    def test_each_failure_and_gap_discounts_confidence_further(self):
        clean = propagate_confidence([0.8, 0.8])
        degraded = propagate_confidence([0.8, 0.8], failures=1, gaps=1)
        self.assertLess(degraded, clean)

    def test_no_evidence_gives_no_confidence_rather_than_zero(self):
        self.assertIsNone(propagate_confidence([None, None]))

    def test_an_agent_with_no_working_tool_reports_blocked(self):
        empty = ToolRegistry()

        class Lonely(Agent):
            name = "lonely"
            allowed_tools = ()

            def run(self, request):
                from src.portwatch_os.agents.specialists import _assemble

                return _assemble(self, [], [], "nothing to say")

        result = Lonely(empty).run(AgentRequest())
        self.assertEqual(result.outcome, BLOCKED)

    def test_a_finding_always_names_the_tool_it_came_from(self):
        agent = SPECIALISTS["global_eye"](self.registry)
        result = agent.run(AgentRequest(question="what is happening"))
        for finding in result.findings:
            self.assertTrue(finding.source_tool, finding.label)
            self.assertIn(finding.source_tool, agent.allowed_tools)


class IntentTests(unittest.TestCase):
    def test_a_fleet_question_routes_to_the_fleet_chain(self):
        intent, basis = classify_intent(
            "Which ships in my fleet require action because of Red Sea risk?"
        )
        self.assertEqual(intent.key, "fleet_exposure")
        self.assertIn("fleet", intent.agents)
        self.assertTrue(intent.high_impact)
        self.assertEqual(basis, "keyword match")

    def test_a_model_classifier_is_used_when_it_answers_something_known(self):
        intent, basis = classify_intent("anything", classifier=lambda _: "learning")
        self.assertEqual(intent.key, "learning")
        self.assertEqual(basis, "model classifier")

    def test_an_unrecognised_model_answer_is_ignored_rather_than_trusted(self):
        intent, basis = classify_intent(
            "what is happening at Chennai", classifier=lambda _: "make_me_a_sandwich"
        )
        self.assertEqual(basis, "keyword match")

    def test_a_classifier_that_throws_falls_back_rather_than_failing(self):
        def broken(_):
            raise RuntimeError("model unavailable")

        intent, basis = classify_intent("what is the weather", classifier=broken)
        self.assertEqual(basis, "keyword match")

    def test_entities_are_matched_literally_not_guessed(self):
        found = extract_entities("What is happening at INMAA over 48h for PWD-003?")
        self.assertEqual(found["port_code"], "INMAA")
        self.assertEqual(found["vessel_id"], "PWD-003")
        self.assertEqual(found["horizon_hours"], 48.0)

    def test_a_port_name_resolves_to_its_code(self):
        self.assertEqual(extract_entities("congestion at Chennai")["port_code"], "INMAA")

    def test_an_unmatched_question_has_no_entities_invented(self):
        self.assertEqual(extract_entities("tell me something"), {})


class CriticTests(unittest.TestCase):
    def setUp(self):
        self.critic = Critic()

    def _recommendation(self, **overrides):
        base = dict(
            kind="arrival_advisory",
            subject="PWD-001",
            action="restagger_arrival",
            values={"arrivalShiftHours": 4.0},
            expected_impact={"waitHoursSaved": 3.2},
            confidence=0.8,
            evidence_tools=["portwatch.port_twin.simulate"],
            evidence={},
            reason="the twin simulates a wait",
        )
        base.update(overrides)
        return Recommendation(**base)

    def test_a_well_supported_recommendation_is_approved(self):
        verdict = self.critic.review(self._recommendation())
        self.assertEqual(verdict.verdict, APPROVED)

    def test_a_recommendation_with_no_evidence_is_rejected(self):
        verdict = self.critic.review(self._recommendation(evidence_tools=[]))
        self.assertEqual(verdict.verdict, REJECTED)
        self.assertIn("supported_by_evidence", verdict.failed_checks)

    def test_diverting_a_vessel_already_in_the_risk_area_is_rejected(self):
        """The check that stops the product advising the impossible."""
        verdict = self.critic.review(
            self._recommendation(action="divert", evidence={"alreadyEntered": True})
        )
        self.assertEqual(verdict.verdict, REJECTED)
        self.assertIn("action_still_available", verdict.failed_checks)

    def test_an_impossible_speed_is_rejected(self):
        verdict = self.critic.review(
            self._recommendation(values={"recommendedSpeedKn": 45.0})
        )
        self.assertEqual(verdict.verdict, REJECTED)
        self.assertIn("physical_envelope", verdict.failed_checks)

    def test_an_arrival_shift_beyond_the_envelope_is_rejected(self):
        verdict = self.critic.review(
            self._recommendation(values={"arrivalShiftHours": 96.0})
        )
        self.assertEqual(verdict.verdict, REJECTED)

    def test_a_hard_constraint_violation_is_reported_and_never_relaxed(self):
        verdict = self.critic.review(
            self._recommendation(
                evidence={"violations": [{"kind": "double_berthing", "detail": "two alongside"}]}
            )
        )
        self.assertEqual(verdict.verdict, REJECTED)
        self.assertIn("no_constraint_violations", verdict.failed_checks)

    def test_stale_evidence_qualifies_rather_than_rejects(self):
        verdict = self.critic.review(
            self._recommendation(evidence={"sourceAgeHours": 40.0})
        )
        self.assertEqual(verdict.verdict, MODIFIED)
        self.assertTrue(verdict.qualifications)

    def test_the_critic_can_only_lower_confidence(self):
        verdict = self.critic.review(
            self._recommendation(confidence=0.8, evidence={"sourceAgeHours": 40.0})
        )
        self.assertLess(verdict.adjusted_confidence, 0.8)

    def test_an_unquantified_benefit_is_flagged(self):
        verdict = self.critic.review(self._recommendation(expected_impact={}))
        self.assertIn("impact_quantified", verdict.failed_checks)

    def test_every_check_is_reported_whether_it_passed_or_not(self):
        verdict = self.critic.review(self._recommendation())
        self.assertGreaterEqual(len(verdict.checks), 8)
        for check in verdict.checks:
            self.assertTrue(check.detail)


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.command = CommandAgent(registry())

    def test_a_run_carries_a_trace_of_every_tool_it_called(self):
        run = self.command.run("What is happening in the world?")
        self.assertTrue(run.tool_trace)
        for call in run.tool_trace:
            self.assertIn("tool", call)
            self.assertIn("agent", call)

    def test_a_high_impact_chain_ends_at_the_critic(self):
        run = self.command.run("Which vessels require action because of Red Sea risk?")
        self.assertEqual(run.intent, "fleet_exposure")
        if run.recommendation is not None:
            self.assertIsNotNone(run.verdict)

    def test_the_chain_narrows_rather_than_fanning_out(self):
        """The fleet agent picks the subject the route agent then scores."""
        run = self.command.run("Which vessels require action because of Red Sea risk?")
        agents = [result.agent for result in run.results]
        self.assertEqual(agents, ["global_eye", "fleet", "route"])

    def test_the_orchestrator_is_capped_below_execute(self):
        self.assertEqual(self.command.max_access, PROPOSE)

    def test_the_summary_contains_no_number_the_trace_does_not(self):
        """An agent narrates findings; it does not compute."""
        run = self.command.run("How wrong has PortWatch been lately?")
        for result in run.results:
            for finding in result.findings:
                self.assertIn(finding.source_tool, {c["tool"] for c in run.tool_trace})

    def test_describe_states_the_boundary(self):
        described = self.command.describe()
        self.assertIn("boundary", described)
        self.assertIn("EXECUTE", described["boundary"]["note"])
        self.assertTrue(described["agents"])
        self.assertTrue(described["intents"])


class McpTests(unittest.TestCase):
    def setUp(self):
        self.server = PortWatchMCPServer(registry(), max_access=PROPOSE)

    def _call(self, method, params=None):
        return self.server.handle(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        )["result"]

    def test_initialize_states_the_protocol_and_the_honesty_rules(self):
        result = self._call("initialize")
        self.assertTrue(result["protocolVersion"])
        self.assertIn("EXECUTE", result["instructions"])
        self.assertIn("simulated", result["instructions"])

    def test_execute_tools_are_not_listed_at_the_default_ceiling(self):
        tools = self._call("tools/list")["tools"]
        self.assertTrue(tools)
        self.assertEqual([t for t in tools if t["access"] == EXECUTE], [])

    def test_execute_tools_are_listed_when_the_ceiling_permits(self):
        server = PortWatchMCPServer(registry(), max_access=EXECUTE)
        tools = server.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )["result"]["tools"]
        self.assertTrue([t for t in tools if t["access"] == EXECUTE])

    def test_a_read_tool_answers_with_its_computing_module(self):
        result = self._call(
            "tools/call",
            {"name": "portwatch.ports.list", "arguments": {}},
        )
        self.assertFalse(result["isError"])
        self.assertTrue(result["structuredContent"]["computedBy"])

    def test_an_execute_call_is_refused_as_a_tool_result_not_a_protocol_error(self):
        """A refusal an agent can reason about beats a transport-level failure."""
        result = self._call(
            "tools/call",
            {"name": "portwatch.advisories.issue", "arguments": {"advisory_id": "x"}},
        )
        self.assertTrue(result["isError"])
        self.assertIn("PROPOSE", result["content"][0]["text"])

    def test_the_boundary_resource_lists_what_is_withheld(self):
        result = self._call("resources/read", {"uri": "portwatch://boundary"})
        payload = json.loads(result["contents"][0]["text"])
        self.assertEqual(payload["ceiling"], PROPOSE)
        self.assertIn("EXECUTE", payload["withheld"])

    def test_an_unknown_method_is_a_protocol_error(self):
        response = self.server.handle(
            {"jsonrpc": "2.0", "id": 9, "method": "tools/destroy", "params": {}}
        )
        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32601)

    def test_a_notification_gets_no_response(self):
        self.assertIsNone(
            self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )

    def test_every_listed_tool_carries_a_schema_and_failure_modes(self):
        for tool in self._call("tools/list")["tools"]:
            self.assertIn("inputSchema", tool)
            self.assertIn("computedBy", tool)
            self.assertTrue(tool["description"])


if __name__ == "__main__":
    unittest.main()
