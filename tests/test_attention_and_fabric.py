"""The attention engine, the cascade API, spatial commands and the signal fabric.

What is asserted here is mostly restraint. An attention queue that ranked by
severity would be easy to build and would put an unfixable problem above a
fixable one; a fabric that fell back across a licence boundary would always
return a provider and would eventually return an illegal one; a spatial command
that did not have to point at a tool result could fly an operator's camera to
something nobody observed.

Each of those is a plausible implementation. Each is the wrong one, and the
tests below are the difference.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from fastapi.testclient import TestClient

from backend.app.main import app
from src.portwatch_os.agents.spatial import (
    COMMANDS,
    FOCUS_EVENT,
    FOCUS_VESSEL,
    LENSES,
    OPERATIONS,
    SET_LENS,
    SHOW_CASCADE,
    OPERATIONAL,
    SAFETY_CLASSES,
    SIMULATION,
    SpatialCommand,
    SpatialError,
    UI,
    commands_from_trace,
    grounded,
    safety_of,
)
from src.portwatch_os.agents.tools import READ, ToolCall
from src.portwatch_os.attention.engine import attention_for
from src.portwatch_os.attention.model import (
    ACT_NOW,
    ACT_SOON,
    AttentionItem,
    Effect,
    MONITOR_ONLY,
    WATCH,
    order,
    rank,
    urgency_multiplier,
)
from src.portwatch_os.fabric import (
    ALLOWED,
    AVAILABLE,
    COMMERCIAL,
    CONFIGURABLE,
    DEMO,
    GOVERNMENT,
    LicencePolicy,
    PLANNED,
    PROHIBITED,
    Provider,
    ProviderHealth,
    ProviderProduct,
    RESEARCH,
    SignalFabric,
    TermsEvidence,
    UNAVAILABLE,
)
from src.portwatch_os.global_eye.exposure import VesselVoyage
from src.portwatch_os.global_eye.model import GlobalEvent
from src.portwatch_os.world.build import build_world, seed_for
from src.portwatch_os.world.cascade import propagate
from src.portwatch_os.world.graph import EVENT, PORT, VESSEL, key
from src.portwatch_os.world.quantity import HOURS, INR, RATIO, RISK, VESSELS, utc

NOW = utc()


def an_event(**overrides) -> GlobalEvent:
    base = dict(
        event_id="E-REDSEA", title="Red Sea escalation", category="conflict",
        region="Red Sea", lat=12.6, lon=43.3,
        geolocation_basis="chokepoint_centroid",
        first_seen=NOW.isoformat(), last_seen=NOW.isoformat(),
        source_count=5, confidence=0.82, severity=0.78,
        chokepoints=["BAB_EL_MANDEB"], horizon_hours=72.0,
    )
    base.update(overrides)
    return GlobalEvent(**base)


def a_voyage(vessel_id: str, hours_to: float) -> VesselVoyage:
    return VesselVoyage(
        vessel_id=vessel_id, name=f"MV {vessel_id}", lane_code="EUR_IND",
        destination_port="INNSA",
        hours_to_chokepoint={"BAB_EL_MANDEB": hours_to},
        service_speed_kn=16.0,
    )


def a_cascade(voyages):
    event = an_event()
    graph = build_world(events=[event], voyages=voyages, now=NOW)
    return propagate(graph, key(EVENT, "E-REDSEA"), seed_for(event), at=NOW)


# --------------------------------------------------------------------------
# ranking
# --------------------------------------------------------------------------


class RankingTests(unittest.TestCase):
    """Priority is the loss attention can still prevent, not the severity."""

    def _item(self, **overrides) -> AttentionItem:
        base = dict(
            attention_id="att:x", subject_type=VESSEL, subject_id="V1",
            subject_label="MV Test", scope="SHIPPING_COMPANY",
            headline="h", reason="r", severity=0.5, confidence=0.9, urgency=0.5,
            status=ACT_SOON,
            expected_operational_effect=Effect(value=12.0, unit=HOURS, confidence=0.9),
        )
        base.update(overrides)
        return AttentionItem(**base)

    def test_a_closing_window_outranks_a_worse_problem_nobody_can_fix(self):
        """The ordering a duty controller would choose by hand."""
        urgent = self._item(
            attention_id="att:urgent", severity=0.4,
            status=ACT_NOW, intervention_window_hours=0.5,
        )
        severe_but_lost = self._item(
            attention_id="att:lost", severity=0.95,
            status=MONITOR_ONLY, intervention_window_hours=None,
        )
        ranked = order([severe_but_lost, urgent])
        self.assertEqual(ranked[0].attention_id, "att:urgent")
        self.assertGreater(urgent.priority, severe_but_lost.priority)

    def test_severity_alone_does_not_decide_the_order(self):
        """Identical consequence, different windows, different order."""
        soon = self._item(attention_id="att:a", intervention_window_hours=2.0,
                          status=ACT_NOW)
        later = self._item(attention_id="att:b", intervention_window_hours=40.0,
                           status=WATCH)
        self.assertEqual(soon.severity, later.severity)
        ranked = order([later, soon])
        self.assertEqual([r.attention_id for r in ranked], ["att:a", "att:b"])

    def test_urgency_multiplies_rather_than_replaces_consequence(self):
        big_slow = self._item(
            attention_id="att:big",
            expected_operational_effect=Effect(value=24.0, unit=HOURS, confidence=1.0),
            intervention_window_hours=40.0,
        )
        tiny_urgent = self._item(
            attention_id="att:tiny",
            expected_operational_effect=Effect(value=0.2, unit=HOURS, confidence=1.0),
            intervention_window_hours=0.5,
        )
        order([big_slow, tiny_urgent])
        # A trivial consequence does not jump a large one on urgency alone.
        self.assertGreater(big_slow.priority, tiny_urgent.priority)

    def test_confidence_discounts_an_otherwise_equal_item(self):
        sure = self._item(attention_id="att:sure", confidence=0.9)
        unsure = self._item(attention_id="att:unsure", confidence=0.3)
        order([sure, unsure])
        self.assertGreater(sure.priority, unsure.priority)

    def test_the_ranking_terms_are_recorded_on_the_item(self):
        """A rank an operator cannot interrogate is a rank they will not trust."""
        item = self._item(intervention_window_hours=2.0)
        rank(item)
        self.assertEqual(
            sorted(item.priority_basis),
            ["actionability", "confidence", "consequence", "urgencyMultiplier"],
        )

    def test_a_window_beyond_a_day_carries_no_urgency_bonus(self):
        self.assertEqual(urgency_multiplier(48.0), 1.0)
        self.assertGreater(urgency_multiplier(0.5), 1.0)

    def test_an_absent_window_is_not_treated_as_urgent(self):
        self.assertEqual(urgency_multiplier(None), 1.0)


# --------------------------------------------------------------------------
# intervention windows
# --------------------------------------------------------------------------


class InterventionWindowTests(unittest.TestCase):
    """A closed option is not an option, however bad the thing behind it."""

    def test_a_committed_vessel_is_monitor_only(self):
        cascade = a_cascade([a_voyage("PWD-001", -6.0)])
        items = attention_for(cascade, scope="SHIPPING_COMPANY", now=NOW)
        vessels = [i for i in items if i.subject_type == VESSEL]
        self.assertTrue(vessels)
        self.assertEqual(vessels[0].status, MONITOR_ONLY)

    def test_a_committed_vessel_is_never_offered_a_reroute(self):
        """The rule the product must not break: no fictional options."""
        cascade = a_cascade([a_voyage("PWD-001", -6.0)])
        items = attention_for(cascade, scope="SHIPPING_COMPANY", now=NOW)
        for item in items:
            if item.subject_type == VESSEL:
                self.assertIsNone(item.recommended_action)
                self.assertEqual(item.alternative_actions, [])

    def test_a_window_too_short_to_execute_is_also_monitor_only(self):
        """Twenty minutes is ahead of the water and behind the decision."""
        cascade = a_cascade([a_voyage("PWD-001", 0.3)])
        items = attention_for(cascade, scope="SHIPPING_COMPANY", now=NOW)
        vessels = [i for i in items if i.subject_type == VESSEL]
        self.assertEqual(vessels[0].status, MONITOR_ONLY)

    def test_an_open_window_carries_a_deadline(self):
        cascade = a_cascade([a_voyage("PWD-001", 5.0)])
        items = attention_for(cascade, scope="SHIPPING_COMPANY", now=NOW)
        vessel = next(i for i in items if i.subject_type == VESSEL)
        self.assertEqual(vessel.status, ACT_SOON)
        self.assertIsNotNone(vessel.action_deadline)
        self.assertAlmostEqual(vessel.intervention_window_hours, 5.0)

    def test_a_monitor_only_item_still_appears(self):
        """Exposure nobody can fix must not be mistaken for safety."""
        cascade = a_cascade([a_voyage("PWD-001", -6.0)])
        items = attention_for(cascade, scope="SHIPPING_COMPANY", now=NOW)
        self.assertTrue(any(i.status == MONITOR_ONLY for i in items))


# --------------------------------------------------------------------------
# role scoping
# --------------------------------------------------------------------------


class RoleScopeTests(unittest.TestCase):
    """Four queues, one computation."""

    def setUp(self):
        self.cascade = a_cascade([a_voyage("PWD-001", 6.0), a_voyage("PWD-002", 30.0)])

    def test_a_carrier_sees_its_hulls(self):
        items = attention_for(self.cascade, scope="SHIPPING_COMPANY", now=NOW)
        self.assertTrue(any(i.subject_type == VESSEL for i in items))

    def test_a_port_authority_sees_its_own_port_only(self):
        items = attention_for(
            self.cascade, scope="PORT_AUTHORITY", port_code="INNSA", now=NOW,
        )
        self.assertTrue(items)
        for item in items:
            self.assertEqual(item.subject_type, PORT)
            self.assertEqual(item.subject_id, "INNSA")

    def test_a_port_authority_elsewhere_sees_nothing_from_this_event(self):
        items = attention_for(
            self.cascade, scope="PORT_AUTHORITY", port_code="INMAA", now=NOW,
        )
        self.assertEqual(items, [])

    def test_a_vessel_operator_sees_only_the_hulls_it_holds(self):
        items = attention_for(
            self.cascade, scope="VESSEL_OPERATOR", vessel_ids=["PWD-002"], now=NOW,
        )
        subjects = {i.subject_id for i in items if i.subject_type == VESSEL}
        self.assertEqual(subjects, {"PWD-002"})

    def test_national_command_sees_the_systemic_view(self):
        items = attention_for(self.cascade, scope="NATIONAL_ADMIN", now=NOW, limit=0)
        kinds = {i.subject_type for i in items}
        self.assertIn("chokepoint", kinds)

    def test_the_roles_share_one_arithmetic(self):
        """A port and a carrier must never be shown two different delays."""
        carrier = attention_for(self.cascade, scope="SHIPPING_COMPANY", now=NOW, limit=0)
        port = attention_for(
            self.cascade, scope="PORT_AUTHORITY", port_code="INNSA", now=NOW, limit=0,
        )
        carrier_effect = next(
            i.expected_operational_effect for i in carrier if i.subject_type == VESSEL
        )
        port_hours = self.cascade.reached[key(PORT, "INNSA")].quantities[HOURS]
        self.assertAlmostEqual(carrier_effect.value, port_hours.value)
        self.assertTrue(port)


# --------------------------------------------------------------------------
# money
# --------------------------------------------------------------------------


class FinancialRefusalTests(unittest.TestCase):
    """An invented rupee figure is the one a CFO would quote back."""

    def test_pricing_is_refused_without_a_rate_and_says_why(self):
        cascade = a_cascade([a_voyage("PWD-001", 6.0)])
        items = attention_for(
            cascade, scope="PORT_AUTHORITY", port_code="INNSA", now=NOW,
        )
        effect = items[0].expected_financial_effect
        self.assertFalse(effect.available)
        self.assertIsNone(effect.value)
        self.assertIn("berth day rate", effect.unavailable_because)

    def test_financial_availability_is_a_flag_callers_can_check(self):
        cascade = a_cascade([a_voyage("PWD-001", 6.0)])
        items = attention_for(
            cascade, scope="PORT_AUTHORITY", port_code="INNSA", now=NOW,
        )
        self.assertFalse(items[0].financial_effect_available)
        self.assertFalse(items[0].to_dict()["financialEffectAvailable"])


# --------------------------------------------------------------------------
# spatial commands
# --------------------------------------------------------------------------


class SpatialCommandTests(unittest.TestCase):
    def _call(self, tool: str, result, ok: bool = True) -> ToolCall:
        return ToolCall(
            tool=tool, access=READ, arguments={}, ok=ok, duration_ms=1.0,
            result=result,
        )

    def test_a_command_must_name_a_tool_that_succeeded(self):
        commands = [SpatialCommand(kind=FOCUS_VESSEL, subject="GHOST",
                                   evidence_tool="portwatch.company.risk")]
        failed = self._call("portwatch.company.risk", None, ok=False)
        self.assertEqual(grounded(commands, [failed]), [])

    def test_a_command_with_no_evidence_is_dropped(self):
        commands = [SpatialCommand(kind=FOCUS_VESSEL, subject="GHOST")]
        self.assertEqual(grounded(commands, []), [])

    def test_commands_are_derived_from_real_tool_results(self):
        trace = [
            self._call("portwatch.global_eye.exposure",
                       {"eventId": "E1", "ports": [{"portCode": "INNSA"}]}),
            self._call("portwatch.company.risk", {"rows": [{"vesselId": "PWD-003"}]}),
        ]
        commands = commands_from_trace(trace)
        kinds = {(c.kind, c.subject) for c in commands}
        self.assertIn((FOCUS_EVENT, "E1"), kinds)
        self.assertIn((SHOW_CASCADE, "E1"), kinds)
        self.assertIn((FOCUS_VESSEL, "PWD-003"), kinds)
        self.assertTrue(all(c.evidence_tool for c in commands))

    def test_an_empty_trace_produces_no_commands(self):
        self.assertEqual(commands_from_trace([]), [])

    def test_an_unknown_command_kind_is_refused(self):
        with self.assertRaises(SpatialError):
            SpatialCommand(kind="LAUNCH_MISSILE", subject="x", evidence_tool="t")

    def test_a_lens_must_be_one_the_world_has(self):
        with self.assertRaises(SpatialError):
            SpatialCommand(kind=SET_LENS, subject="CYBERPUNK", evidence_tool="t")
        SpatialCommand(kind=SET_LENS, subject=OPERATIONS, evidence_tool="t")

    def test_every_lens_is_constructible(self):
        for lens in LENSES:
            SpatialCommand(kind=SET_LENS, subject=lens, evidence_tool="t")


class CommandSafetyTests(unittest.TestCase):
    """UI, SIMULATION and OPERATIONAL are three different things.

    They are all called "commands", which is exactly why the distinction has to
    be structural rather than remembered. A view change may run the moment an
    answer arrives; a model run may not; an action that reaches a vessel may
    never run from an answer at all.
    """

    def test_every_command_is_classified(self):
        """An unclassified command would default to auto-executing."""
        for kind in COMMANDS:
            self.assertIn(safety_of(kind), SAFETY_CLASSES, kind)

    def test_an_unclassified_kind_raises_rather_than_defaulting(self):
        with self.assertRaises(SpatialError):
            safety_of("SEND_ADVISORY")

    def test_view_changes_are_the_only_automatic_commands(self):
        for kind in COMMANDS:
            command = SpatialCommand(
                kind=kind,
                subject=OPERATIONS if kind == "SET_LENS" else "x",
                evidence_tool="t",
            )
            self.assertEqual(command.auto_executable, command.safety == UI, kind)

    def test_branching_the_world_is_a_simulation_not_a_camera_move(self):
        self.assertEqual(safety_of("COMPARE_SCENARIOS"), SIMULATION)
        command = SpatialCommand(
            kind="COMPARE_SCENARIOS", subject="x", evidence_tool="t",
        )
        self.assertFalse(command.auto_executable)

    def test_the_safety_class_travels_on_the_wire(self):
        payload = SpatialCommand(
            kind="FOCUS_VESSEL", subject="PWD-001", evidence_tool="t",
        ).to_dict()
        self.assertEqual(payload["safety"], UI)
        self.assertTrue(payload["autoExecutable"])

    def test_no_command_is_classified_operational_yet(self):
        """Nothing an agent can emit today reaches beyond the screen.

        If that changes, this test fails and forces a deliberate decision about
        how the approval boundary applies to it.
        """
        operational = [k for k in COMMANDS if safety_of(k) == OPERATIONAL]
        self.assertEqual(operational, [])


# --------------------------------------------------------------------------
# signal fabric
# --------------------------------------------------------------------------


class FabricTests(unittest.TestCase):
    """Licence is the field that decides, and refusing is a valid answer."""

    def setUp(self):
        self.fabric = SignalFabric(mode=COMMERCIAL)

    def test_an_unverified_source_is_refused_for_a_paying_deployment(self):
        """AISStream publishes no terms. That is REQUIRES_REVIEW, not prohibited."""
        resolution = self.fabric.resolve("ais")
        rejected = dict(resolution.rejected)
        self.assertIn("aisstream-websocket", rejected)
        self.assertIn("requires review", rejected["aisstream-websocket"])
        self.assertNotIn("prohibit", rejected["aisstream-websocket"])

    def test_the_same_source_is_eligible_for_research(self):
        resolution = SignalFabric(mode=RESEARCH).resolve("ais")
        self.assertEqual(resolution.product.product_id, "aisstream-websocket")

    def test_demo_may_use_an_unverified_source(self):
        self.assertEqual(
            SignalFabric(mode=DEMO).resolve("ais").product.product_id,
            "aisstream-websocket",
        )

    def test_a_capability_with_no_eligible_provider_is_unavailable(self):
        resolution = self.fabric.resolve("vessel_registry")
        self.assertFalse(resolution.available)
        self.assertEqual(resolution.to_dict()["status"], UNAVAILABLE)

    def test_every_rejection_carries_its_reason(self):
        """Without the reason, "unavailable" does not tell an operator what to buy."""
        resolution = self.fabric.resolve("vessel_registry")
        self.assertTrue(resolution.rejected)
        for _provider_id, reason in resolution.rejected:
            self.assertTrue(reason)

    def test_a_government_deployment_needs_redistribution_rights(self):
        contracted = Provider(
            provider_id="contracted", name="Contracted", products=(
                ProviderProduct(
                    product_id="contracted-ais", name="Contracted AIS",
                    capabilities=("ais",), status=AVAILABLE, trust=0.99,
                    policy=LicencePolicy(
                        commercial_use=ALLOWED, government_use=ALLOWED,
                        redistribution=PROHIBITED, attribution_required=False,
                        evidence=TermsEvidence(
                            checked_urls=(), reviewed_at="2026-09-12",
                            finding="contract forbids onward sharing",
                        ),
                    ),
                ),
            ),
        )
        fabric = SignalFabric([contracted], mode=GOVERNMENT)
        resolution = fabric.resolve("ais")
        self.assertFalse(resolution.available)
        self.assertIn("agencies", dict(resolution.rejected)["contracted-ais"])

    def test_a_planned_product_is_not_resolved_to(self):
        """Naming a source must not imply an adapter exists."""
        for product_id in ("spire-ais", "kpler-maritime", "gfw-api"):
            self.assertEqual(self.fabric.product(product_id).status, PLANNED)
        self.assertNotEqual(
            self.fabric.resolve("ais").product.product_id, "spire-ais",
        )

    def test_a_synthetic_source_says_so_structurally(self):
        """"May we use it" and "is it real" are different questions."""
        resolution = self.fabric.resolve("ais")
        self.assertTrue(resolution.synthetic)
        self.assertTrue(resolution.to_dict()["synthetic"])

    def test_freshness_is_separate_from_status(self):
        stale = ProviderHealth(last_success=(NOW - timedelta(hours=40)).isoformat())
        fresh = ProviderHealth(last_success=(NOW - timedelta(minutes=5)).isoformat())
        self.assertEqual(stale.freshness(now=NOW), "cold")
        self.assertEqual(fresh.freshness(now=NOW), "fresh")
        self.assertEqual(ProviderHealth().freshness(now=NOW), "unknown")

    def test_an_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            SignalFabric(mode="PIRATE")


# --------------------------------------------------------------------------
# the API
# --------------------------------------------------------------------------


class WorldApiTests(unittest.TestCase):
    """The contract the map depends on."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.headers = {
            "X-PortWatch-Actor": "A. Deshmukh",
            "X-PortWatch-Role": "NATIONAL_ADMIN",
        }

    @classmethod
    def _live_instant(cls):
        """An instant at which the feed's events were within their horizon.

        The register ages: every event carries a claim horizon, and once the
        feed is older than that nothing is live at `now`. A test that skipped
        in that case would silently stop proving anything the day after the
        fixture was captured -- which is exactly what happened. The engine is
        temporal, so the tests query it at a time the events were live rather
        than pretending the present is that time.
        """
        from src.portwatch_os.global_eye.model import parse_time
        from backend.app.routes.global_eye import _load_events

        events, *_ = _load_events()
        stamps = [parse_time(e.first_seen) for e in events if parse_time(e.first_seen)]
        if not stamps:
            return None
        # One hour into the freshest event's window.
        from datetime import timedelta
        return (max(stamps) + timedelta(hours=1)).isoformat()

    def _at(self) -> str:
        from urllib.parse import quote

        instant = self._live_instant()
        if instant is None:
            self.skipTest("the feed carries no dated events at all")
        return f"at={quote(instant)}"

    def _live_event(self):
        rows = self.client.get(
            f"/api/world/cascades?{self._at()}", headers=self.headers,
        ).json()
        live = [r for r in rows["cascades"] if r.get("live")]
        if not live:
            self.skipTest("no event propagates consequence even at its own instant")
        return live[0]["eventId"]

    def test_the_world_reports_its_own_rule_catalogue(self):
        """A number whose unit change has no published rule is not shippable."""
        body = self.client.get("/api/world/state", headers=self.headers).json()
        self.assertTrue(body["rules"])
        for rule in body["rules"]:
            self.assertTrue(rule["explains"])

    def test_a_cascade_carries_the_trace_behind_every_number(self):
        event_id = self._live_event()
        body = self.client.get(
            f"/api/world/cascades/{event_id}?{self._at()}", headers=self.headers,
        ).json()
        self.assertTrue(body["steps"])
        for step in body["steps"]:
            self.assertTrue(step["rule"])
            self.assertIn("incoming", step)
            self.assertIn("outgoing", step)

    def test_every_propagated_quantity_keeps_its_unit_and_confidence(self):
        event_id = self._live_event()
        body = self.client.get(
            f"/api/world/cascades/{event_id}?{self._at()}", headers=self.headers,
        ).json()
        for group in body["affected"].values():
            for subject in group:
                for unit, quantity in subject["quantities"].items():
                    self.assertEqual(quantity["unit"], unit)
                    self.assertIn("confidence", quantity)
                    self.assertIn("interval", quantity)

    def test_the_affected_sets_are_resolved_server_side(self):
        """The map must not have to work out which lanes light up."""
        event_id = self._live_event()
        body = self.client.get(
            f"/api/world/cascades/{event_id}?{self._at()}", headers=self.headers,
        ).json()
        self.assertEqual(
            sorted(body["affected"]), ["chokepoints", "lanes", "ports", "vessels"],
        )

    def test_no_vessel_appears_twice_in_a_cascade(self):
        event_id = self._live_event()
        body = self.client.get(
            f"/api/world/cascades/{event_id}?{self._at()}", headers=self.headers,
        ).json()
        ids = [v["id"] for v in body["affected"]["vessels"]]
        self.assertEqual(len(ids), len(set(ids)))
        for vessel in body["affected"]["vessels"]:
            count = vessel["quantities"].get("vessels")
            if count:
                self.assertEqual(count["value"], 1.0)

    def test_projection_queries_the_same_graph_at_each_horizon(self):
        event_id = self._live_event()
        body = self.client.post(
            "/api/world/cascade/simulate",
            json={"eventId": event_id, "at": self._live_instant()},
            headers=self.headers,
        ).json()
        offsets = [f["offsetHours"] for f in body["frames"]]
        self.assertEqual(offsets, sorted(offsets))
        self.assertEqual(offsets[0], 0.0)

    def test_a_lapsed_event_stops_reaching_anything(self):
        """PROJECT 72H is a query, so consequence drains rather than being predicted."""
        event_id = self._live_event()
        body = self.client.post(
            "/api/world/cascade/simulate",
            json={"eventId": event_id, "offsets": [0, 168], "at": self._live_instant()},
            headers=self.headers,
        ).json()
        first, last = body["frames"][0], body["frames"][-1]
        self.assertTrue(first["live"])
        self.assertFalse(last["live"])
        self.assertEqual(last["affected"]["vessels"], [])

    def test_an_attention_item_can_be_traced_to_its_computation(self):
        queue = self.client.get(f"/api/attention?{self._at()}", headers=self.headers).json()
        if not queue["items"]:
            self.skipTest("the queue is empty even at the events' own instant")
        item_id = queue["items"][0]["attentionId"]
        body = self.client.get(
            f"/api/attention/{item_id}?{self._at()}", headers=self.headers,
        ).json()
        self.assertTrue(body["evidence"])
        self.assertEqual(body["item"]["attentionId"], item_id)

    def test_the_evidence_chain_runs_from_the_event_not_just_the_last_hop(self):
        queue = self.client.get(f"/api/attention?{self._at()}", headers=self.headers).json()
        if not queue["items"]:
            self.skipTest("the queue is empty even at the events' own instant")
        item = next(
            (i for i in queue["items"] if i["subjectType"] in (PORT, VESSEL)), None,
        )
        if item is None:
            self.skipTest("no port or vessel item in the queue")
        body = self.client.get(
            f"/api/attention/{item['attentionId']}?{self._at()}", headers=self.headers,
        ).json()
        depths = [s["depth"] for s in body["evidence"]]
        self.assertEqual(depths, sorted(depths))
        self.assertEqual(min(depths), 1)

    def test_an_unknown_role_is_refused(self):
        response = self.client.get(
            "/api/attention", headers={"X-PortWatch-Role": "PIRATE_KING"},
        )
        self.assertEqual(response.status_code, 403)

    def test_a_malformed_instant_is_refused(self):
        response = self.client.get("/api/world/state?at=yesterday")
        self.assertEqual(response.status_code, 400)

    def test_an_offset_beyond_the_horizon_is_refused(self):
        response = self.client.post(
            "/api/world/cascade/simulate",
            json={"eventId": "anything", "offsets": [9999]},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_an_unknown_event_is_a_404(self):
        response = self.client.get(
            "/api/world/cascades/not-an-event", headers=self.headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_the_fabric_refuses_an_unknown_capability(self):
        self.assertEqual(
            self.client.get("/api/fabric/resolve/telepathy").status_code, 404,
        )

    def test_the_fabric_reports_commercial_restrictions_over_http(self):
        body = self.client.get("/api/fabric/resolve/ais?mode=COMMERCIAL").json()
        self.assertEqual(body["status"], AVAILABLE)
        rejected = {r["productId"] for r in body["rejected"]}
        self.assertIn("aisstream-websocket", rejected)

    # -- observed AIS over HTTP -------------------------------------------
    def _with_client(self, api_key, feed=()):
        """Install a scripted, unstarted AIS client as the process's one."""
        from src.portwatch_os.fabric.ais import AisStreamClient, TrackStore
        from src.portwatch_os.fabric.ais import client as client_module

        client_module.reset_client()
        client = AisStreamClient(TrackStore(), api_key=api_key)
        for envelope in feed:
            client.feed(envelope)
        client_module._CLIENT = client
        self.addCleanup(client_module.reset_client)
        return client

    @staticmethod
    def _position(mmsi="419001234", at=None):
        from datetime import datetime, timezone

        moment = at or datetime.now(timezone.utc)
        return {
            "MessageType": "PositionReport",
            "MetaData": {"MMSI": mmsi, "ShipName": "JOINED NAME", "latitude": 12.6,
                         "longitude": 43.3,
                         "time_utc": moment.strftime("%Y-%m-%d %H:%M:%S.%f") + "000 +0000 UTC"},
            "Message": {"PositionReport": {"UserID": int(mmsi), "Sog": 11.0, "Cog": 90.0,
                                           "TrueHeading": 511, "NavigationalStatus": 0}},
        }

    def test_health_without_a_key_reports_the_replay_by_name(self):
        self._with_client(None)
        body = self.client.get("/api/fabric/health?mode=RESEARCH").json()
        self.assertEqual(body["traffic"]["mode"], "SIMULATED_TRAFFIC")
        self.assertEqual(body["traffic"]["providerId"], "ais-replay")
        ais = next(s for s in body["signals"] if s["capability"] == "ais")
        self.assertEqual(ais["availability"]["status"], CONFIGURABLE)
        self.assertEqual(ais["freshness"], "UNAVAILABLE")
        self.assertEqual(ais["commercialUse"], "REQUIRES_REVIEW")

    def test_health_with_a_key_and_no_messages_is_not_live(self):
        self._with_client("k")
        body = self.client.get("/api/fabric/health?mode=RESEARCH").json()
        self.assertEqual(body["traffic"]["mode"], "UNAVAILABLE")
        self.assertIsNone(body["traffic"]["providerId"])
        self.assertIn("no valid observation has arrived", body["traffic"]["availability"]["reason"])
        # And the key itself is in no field of the response.
        self.assertNotIn('"k"', self.client.get("/api/fabric/health?mode=RESEARCH").text)

    def test_health_becomes_live_only_when_a_message_arrived(self):
        self._with_client("k", feed=[self._position()])
        body = self.client.get("/api/fabric/health?mode=RESEARCH").json()
        self.assertEqual(body["traffic"]["mode"], "LIVE_AIS")
        self.assertEqual(body["traffic"]["health"]["messagesConsumed"], 1)
        ais = next(s for s in body["signals"] if s["capability"] == "ais")
        self.assertEqual(ais["availability"]["status"], AVAILABLE)
        self.assertEqual(ais["freshness"], "LIVE")
        self.assertLess(ais["ageSeconds"], 60)

    def test_observed_tracks_carry_only_what_was_said(self):
        self._with_client("k", feed=[self._position()])
        body = self.client.get("/api/world/ais/tracks?mode=RESEARCH").json()
        self.assertEqual(body["traffic"]["mode"], "LIVE_AIS")
        self.assertEqual(body["count"], 1)
        track = body["tracks"][0]
        self.assertEqual(track["mmsi"], "419001234")
        self.assertIsNone(track["name"])          # a position report names nobody
        self.assertIsNone(track["imo"])
        self.assertIsNone(track["latest"]["headingDegrees"])   # 511 is not a heading
        self.assertEqual(track["source"], "OBSERVED_AIS")
        self.assertEqual(track["freshness"], "LIVE")

    def test_observed_tracks_are_empty_when_the_replay_is_showing(self):
        self._with_client(None)
        body = self.client.get("/api/world/ais/tracks?mode=RESEARCH").json()
        self.assertEqual(body["traffic"]["mode"], "SIMULATED_TRAFFIC")
        self.assertEqual(body["tracks"], [])

    def test_observed_tracks_are_withheld_from_a_commercial_deployment(self):
        self._with_client("k", feed=[self._position()])
        body = self.client.get("/api/world/ais/tracks?mode=COMMERCIAL").json()
        self.assertEqual(body["traffic"]["mode"], "UNAVAILABLE")
        self.assertEqual(body["tracks"], [])

    # -- observed hulls in the world graph ---------------------------------
    @staticmethod
    def _static(mmsi="419001234", imo=9000001, name="OBSERVED HULL", destination="INNSA", at=None):
        from datetime import datetime, timezone

        moment = at or datetime.now(timezone.utc)
        return {
            "MessageType": "ShipStaticData",
            "MetaData": {"MMSI": mmsi, "latitude": 12.8, "longitude": 45.5,
                         "time_utc": moment.strftime("%Y-%m-%d %H:%M:%S.%f") + "000 +0000 UTC"},
            "Message": {"ShipStaticData": {"UserID": int(mmsi), "ImoNumber": imo, "Name": name,
                                           "CallSign": "VT", "Destination": destination,
                                           "Eta": {"Month": 9, "Day": 20, "Hour": 1, "Minute": 0}}},
        }

    @staticmethod
    def _aden_position(mmsi="419001234", at=None, cog=100.0, sog=14.0):
        """East of Bab-el-Mandeb, heading east: through the strait, bound for India."""
        from datetime import datetime, timezone

        moment = at or datetime.now(timezone.utc)
        return {
            "MessageType": "PositionReport",
            "MetaData": {"MMSI": mmsi, "latitude": 12.8, "longitude": 45.5,
                         "time_utc": moment.strftime("%Y-%m-%d %H:%M:%S.%f") + "000 +0000 UTC"},
            "Message": {"PositionReport": {"UserID": int(mmsi), "Sog": sog, "Cog": cog,
                                           "TrueHeading": int(cog), "NavigationalStatus": 0}},
        }

    def _with_fused_client(self, api_key, feed=()):
        """A scripted client wired to a fresh fusion engine, as the process's."""
        from src.portwatch_os.fabric.ais import client as client_module
        from src.portwatch_os.fusion import engine as fusion_module
        from src.portwatch_os.world.live import reset_live_world

        fusion_module.reset_engine()
        reset_live_world()
        self.addCleanup(fusion_module.reset_engine)
        self.addCleanup(reset_live_world)
        client = self._with_client(api_key)
        # The production hook: fuse the observation and move the world on.
        client._on_observation = client_module._fuse
        for envelope in feed:
            client.feed(envelope)
        return client

    def test_an_observed_hull_enters_the_world_with_its_confidences(self):
        self._with_fused_client("k", feed=[self._aden_position(), self._static()])
        body = self.client.get("/api/world/state?mode=RESEARCH").json()
        self.assertEqual(body["summary"]["observedVessels"], 1)
        node = next(n for n in body["nodes"] if n["attrs"].get("source") == "OBSERVED_AIS")
        attrs = node["attrs"]
        self.assertEqual(attrs["mmsi"], "419001234")
        self.assertEqual(attrs["imo"], "9000001")
        self.assertEqual(attrs["destination_port"], "INNSA")
        self.assertEqual(attrs["destination_confidence"], 0.9)          # a LOCODE
        self.assertEqual(attrs["lane_code"], "EUR_IND")
        self.assertLess(attrs["lane_confidence"], 1.0)                  # inferred, and says so
        self.assertLess(attrs["placement_confidence"], 0.5)
        self.assertTrue(attrs["name_stated"])
        self.assertEqual(attrs["lat"], 12.8)

    def test_a_hull_without_a_destination_is_on_the_chart_but_not_on_a_lane(self):
        self._with_fused_client("k", feed=[self._aden_position()])           # position only
        body = self.client.get("/api/world/state?mode=RESEARCH").json()
        node = next(n for n in body["nodes"] if n["attrs"].get("source") == "OBSERVED_AIS")
        self.assertIsNone(node["attrs"]["destination_port"])
        self.assertIsNone(node["attrs"]["lane_code"])
        self.assertEqual(node["attrs"]["placement_confidence"], 0.0)
        self.assertFalse(node["attrs"]["name_stated"])
        self.assertTrue(node["label"].startswith("MMSI "))                   # no invented name
        sails = [e for e in body["edges"] if e["dst"] == node["key"] and e["kind"] == "SAILS"]
        self.assertEqual(sails, [])

    def test_observed_hulls_are_absent_from_a_commercial_view(self):
        self._with_fused_client("k", feed=[self._aden_position(), self._static()])
        body = self.client.get("/api/world/state?mode=COMMERCIAL").json()
        self.assertEqual(body["summary"]["observedVessels"], 0)

    def test_an_observed_hull_is_reached_by_a_cascade_with_discounted_confidence(self):
        """The point of the exercise: consequence reaches a real hull, and the
        confidence on it is lower than on a fleet vessel by what was inferred."""
        self._with_fused_client("k", feed=[self._aden_position(), self._static()])
        listing = self.client.get(
            f"/api/world/cascades?mode=RESEARCH&{self._at()}", headers=self.headers,
        ).json()
        bab = [c for c in listing["cascades"] if c["live"] and "BAB_EL_MANDEB" in
               {s["id"] for s in c["affected"]["chokepoints"]}]
        if not bab:
            self.skipTest("no live Bab-el-Mandeb cascade in the register at this instant")
        detail = self.client.get(
            f"/api/world/cascades/{bab[0]['eventId']}?mode=RESEARCH&{self._at()}",
            headers=self.headers,
        ).json()
        reached = [v for v in detail["affected"]["vessels"] if v["attrs"].get("source") == "OBSERVED_AIS"]
        self.assertEqual(len(reached), 1)
        fleet = [v for v in detail["affected"]["vessels"] if v["attrs"].get("source") != "OBSERVED_AIS"]
        observed_conf = max(q["confidence"] for q in reached[0]["quantities"].values())
        if fleet:
            fleet_conf = max(max(q["confidence"] for q in v["quantities"].values()) for v in fleet)
            self.assertLess(observed_conf, fleet_conf)

    # -- entities over HTTP --------------------------------------------------
    def test_entities_list_and_detail_carry_the_whole_record(self):
        self._with_fused_client("k", feed=[self._aden_position(), self._static()])
        listing = self.client.get("/api/world/entities?observedOnly=true").json()
        self.assertEqual(listing["count"], 1)
        hull = listing["vessels"][0]
        self.assertEqual(hull["mmsis"], ["419001234"])
        self.assertEqual(hull["imo"], "9000001")
        self.assertTrue(hull["observed"])
        detail = self.client.get(f"/api/world/entities/{hull['canonicalId']}").json()
        self.assertGreaterEqual(len(detail["assertions"]), 6)
        self.assertEqual({l["key"]["kind"] for l in detail["links"]}, {"MMSI", "IMO"})

    def test_entity_lookup_is_by_strong_key_only(self):
        self._with_fused_client("k", feed=[self._aden_position(), self._static()])
        by_mmsi = self.client.get("/api/world/entities/lookup?mmsi=419001234").json()
        by_imo = self.client.get("/api/world/entities/lookup?imo=9000001").json()
        self.assertEqual(by_mmsi["canonicalId"], by_imo["canonicalId"])
        self.assertEqual(self.client.get("/api/world/entities/lookup?mmsi=419009999").status_code, 404)
        self.assertEqual(self.client.get("/api/world/entities/lookup").status_code, 400)
        # No name parameter exists; passing one is ignored, not honoured.
        self.assertEqual(self.client.get("/api/world/entities/lookup?name=OBSERVED%20HULL").status_code, 400)

    # -- attention reacting to observed state -------------------------------
    def _red_sea_hull(self, mmsi="419001234", at=None):
        """Mid Red Sea, southbound: Bab-el-Mandeb ahead, hours away."""
        from datetime import datetime, timezone

        moment = at or datetime.now(timezone.utc)
        stamp = moment.strftime("%Y-%m-%d %H:%M:%S.%f") + "000 +0000 UTC"
        return [
            {"MessageType": "PositionReport",
             "MetaData": {"MMSI": mmsi, "latitude": 20.0, "longitude": 38.5, "time_utc": stamp},
             "Message": {"PositionReport": {"UserID": int(mmsi), "Sog": 14.0, "Cog": 150.0,
                                            "TrueHeading": 150, "NavigationalStatus": 0}}},
            {"MessageType": "ShipStaticData",
             "MetaData": {"MMSI": mmsi, "latitude": 20.0, "longitude": 38.5, "time_utc": stamp},
             "Message": {"ShipStaticData": {"UserID": int(mmsi), "ImoNumber": 9000002, "Name": "SEEN HULL",
                                            "CallSign": "VT", "Destination": "INNSA",
                                            "Eta": {"Month": 9, "Day": 20, "Hour": 1, "Minute": 0}}}},
        ]

    def test_an_observed_hull_is_advised_not_ordered(self):
        """A national centre can tell a third-party hull about the water ahead;
        it cannot order it to divert, and the queue must not say it can."""
        self._with_fused_client("k", feed=self._red_sea_hull())
        body = self.client.get(
            f"/api/attention?mode=RESEARCH&limit=25&{self._at()}", headers=self.headers,
        ).json()
        observed = [i for i in body["items"] if i["source"] == "OBSERVED_AIS"]
        if not observed:
            self.skipTest("no live Red Sea cascade reaches the hull at this instant")
        item = observed[0]
        self.assertEqual(item["provenance"]["mmsi"], "419001234")
        self.assertTrue(item["provenance"]["nameStated"])
        self.assertLess(item["provenance"]["placementConfidence"], 1.0)
        self.assertIn("Observed via AIS", item["reason"])
        self.assertIn("(observed)", item["headline"])
        if item["recommendedAction"]:
            self.assertEqual(item["recommendedAction"]["action"], "advise")
            self.assertNotEqual(item["recommendedAction"]["action"], "reroute")
        self.assertEqual(body["traffic"], "LIVE_AIS")
        self.assertGreaterEqual(body["observed"], 1)

    def test_a_stale_feed_is_an_item_of_its_own_and_never_actionable(self):
        from datetime import datetime, timedelta, timezone

        self._with_fused_client("k", feed=self._red_sea_hull(at=datetime.now(timezone.utc) - timedelta(minutes=15)))
        body = self.client.get(
            f"/api/attention?mode=RESEARCH&limit=25&{self._at()}", headers=self.headers,
        ).json()
        self.assertEqual(body["traffic"], "AIS_STALE")
        feed = [i for i in body["items"] if i["source"] == "FEED"]
        self.assertEqual(len(feed), 1)
        self.assertEqual(feed[0]["status"], "MONITOR_ONLY")
        self.assertFalse(feed[0]["actionable"])
        self.assertIn("stale", feed[0]["headline"].lower())
        self.assertEqual(feed[0]["provenance"]["mode"], "AIS_STALE")
        # The stale item ranks beneath anything actionable.
        actionable = [i for i in body["items"] if i["actionable"]]
        if actionable:
            self.assertGreater(body["items"].index(feed[0]), body["items"].index(actionable[-1]))

    def test_a_live_feed_produces_no_feed_item(self):
        self._with_fused_client("k", feed=self._red_sea_hull())
        body = self.client.get(
            f"/api/attention?mode=RESEARCH&limit=25&{self._at()}", headers=self.headers,
        ).json()
        self.assertEqual([i for i in body["items"] if i["source"] == "FEED"], [])

    def test_a_replay_deployment_produces_no_feed_item(self):
        self._with_client(None)
        body = self.client.get(
            f"/api/attention?mode=RESEARCH&limit=25&{self._at()}", headers=self.headers,
        ).json()
        self.assertEqual(body["traffic"], "SIMULATED_TRAFFIC")
        self.assertEqual([i for i in body["items"] if i["source"] == "FEED"], [])
        self.assertTrue(all(i["source"] == "FLEET" for i in body["items"]))

    def test_a_fleet_vessel_sharing_a_name_is_a_candidate_not_a_merge(self):
        from backend.app.routes.global_eye import _company_voyages

        fleet_name = _company_voyages(None)[0].name
        self._with_fused_client("k", feed=[self._aden_position(), self._static(name=fleet_name)])
        self.client.get("/api/world/state?mode=RESEARCH")                    # registers the fleet
        listing = self.client.get("/api/world/entities").json()
        observed = next(v for v in listing["vessels"] if v["observed"])
        self.assertEqual(observed["fleetIds"], [])                            # not merged
        self.assertTrue(observed["candidates"])                               # offered
        self.assertFalse(observed["candidates"][0]["applied"])


if __name__ == "__main__":
    unittest.main()
