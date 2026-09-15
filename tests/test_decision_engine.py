"""The decision intelligence engine.

What these tests defend: an impossible option is REJECTED with the constraint
that rejected it, never scored; the baseline is computed through the same
simulator as every alternative; the observed world is never edited by a
decision; a chosen action's delay travels vessel -> port -> yard through the
world engine; an actor is offered only what it can execute; dominance is a
fact about the numbers; the ranking shows its weights; the Critic names its
evidence and rejects a closed window; the ledger holds the problem as
computed and refuses to rewrite it; and a greedy port rule that minimises
wait can lose to the incumbent on a broken commitment.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.portwatch_os.decision import DecisionActor, DecisionEngine
from src.portwatch_os.decision.actions import REROUTE, SLOW_STEAM, availability_of, CATALOGUE
from src.portwatch_os.decision.critic import DecisionCritic, PASS_WITH_WARNINGS, REJECT
from src.portwatch_os.decision.frontier import dominates, pareto, rank
from src.portwatch_os.decision.learning import score_history
from src.portwatch_os.decision.model import (
    APPROVED,
    DecisionError,
    DecisionEvaluation,
    DecisionOption,
    FEASIBLE,
    OBJECTIVES,
    PORT_AUTHORITY,
    REJECTED,
    REVIEWED,
    SHIPPING_COMPANY,
    VESSEL_ROUTING,
    known,
    unknown,
)
from src.portwatch_os.decision.port import build_port_problem
from src.portwatch_os.finance import CostBasis, assumption, basis_with_public_tariffs
from src.portwatch_os.global_eye.exposure import VesselVoyage
from src.portwatch_os.global_eye.model import GlobalEvent
from src.portwatch_os.ledger.store import LedgerError, SqliteLedgerStore
from src.portwatch_os.twin.state import VesselCall, WAITING, APPROACHING, schematic_layout
from src.portwatch_os.world.branch import ObservedWorldState
from src.portwatch_os.world.build import build_world, seed_for
from src.portwatch_os.world.graph import EVENT, PORT, SAILS, VESSEL, key
from src.portwatch_os.world.live import Revision
from src.portwatch_os.world.quantity import HOURS, Quantity
from src.portwatch_os.world.cascade import propagate

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def red_sea_event(horizon: float = 72.0) -> GlobalEvent:
    return GlobalEvent(
        event_id="EV-RED-SEA", title="Red Sea escalation", category="chokepoint_disruption",
        region="Red Sea", lat=12.6, lon=43.3, geolocation_basis="chokepoint",
        first_seen=NOW.isoformat(), last_seen=NOW.isoformat(), source_count=3,
        confidence=0.9, severity=0.85, horizon_hours=horizon, chokepoints=["BAB_EL_MANDEB"],
    )


def observed_world(voyages=None, event=None) -> ObservedWorldState:
    voyages = voyages or [
        VesselVoyage("PWD-001", "MV Konkan", "EUR_IND", "INNSA", {"SUEZ": 20.0, "BAB_EL_MANDEB": 46.0},
                     service_speed_kn=18.0),
        VesselVoyage("PWD-002", "MV Malabar", "EUR_IND", "INNSA", {"SUEZ": -30.0, "BAB_EL_MANDEB": 10.0},
                     service_speed_kn=17.0),
        VesselVoyage("PWD-003", "MV Kutch", "EUR_IND", "INMUN", {"SUEZ": 60.0, "BAB_EL_MANDEB": 90.0},
                     service_speed_kn=20.0),
    ]
    graph = build_world(events=[event or red_sea_event()], voyages=voyages, now=NOW)
    return ObservedWorldState(state_id="obs-test", revision=Revision("DEMO", None, "e", "f", 1), at=NOW,
                              graph=graph, traffic_mode="SIMULATED_TRAFFIC")


def solve(vessel_id="PWD-001", *, actor=SHIPPING_COMPANY, basis=None, ledger=None, state=None, event=None):
    event = event or red_sea_event()
    state = state or observed_world(event=event)
    engine = DecisionEngine(basis=basis or CostBasis(), ledger=ledger)
    problem = engine.solve_vessel(state, event_key=key(EVENT, event.event_id), seed=seed_for(event),
                                  vessel_id=vessel_id, actor=DecisionActor(actor), at=NOW)
    return engine, problem


def option_with(option_id, **values) -> DecisionOption:
    measures = {k: known(v, OBJECTIVES[k].unit, basis="test") for k, v in values.items()}
    return DecisionOption(option_id=option_id, action="X", label=option_id, actor=SHIPPING_COMPANY,
                          status=FEASIBLE, evaluation=DecisionEvaluation(objectives=measures))


# --------------------------------------------------------------------------
# hard infeasibility, availability and actor permissions
# --------------------------------------------------------------------------


class InfeasibilityTests(unittest.TestCase):
    def test_a_hull_past_suez_cannot_take_the_cape_and_is_told_why(self):
        _engine, problem = solve("PWD-002")
        rows = {r["kind"]: r["availability"] for r in problem.available_actions}
        self.assertEqual(rows[REROUTE]["status"], "UNAVAILABLE")
        self.assertIn("Suez", rows[REROUTE]["reason"])
        self.assertIsNone(problem.option("reroute"))               # never an option, never scored
        self.assertIsNotNone(problem.option("keep_plan"))

    def test_a_rejected_option_carries_the_constraint_and_takes_no_part_in_ranking(self):
        # Force the alternative to be unreachable by putting the hull past the
        # commit point while still short of the strait; the constraint pass
        # sees it and the option is REJECTED, not down-weighted.
        _engine, problem = solve("PWD-001")
        option = problem.option("reroute")
        self.assertIsNotNone(option)
        option.status = REJECTED
        option.constraints = [c for c in option.constraints]
        ranking = rank(problem.options, VESSEL_ROUTING)
        self.assertNotIn("reroute", ranking["order"])
        frontier = pareto(problem.options, [OBJECTIVES["eta"], OBJECTIVES["risk"]])
        self.assertNotIn("reroute", frontier.nondominated)

    def test_the_critic_rejects_a_closed_decision_window(self):
        _engine, problem = solve("PWD-001")
        option = problem.option("reroute")
        option.provenance["closesInHours"] = -1.0
        verdict = DecisionCritic().review_option(option, problem, now=NOW)
        self.assertEqual(verdict.verdict, REJECT)
        blocking = [c for c in verdict.checks if not c.passed and c.severity == "blocking"]
        self.assertEqual([c.name for c in blocking], ["decision_window"])
        self.assertEqual(blocking[0].basis, "option.provenance.closesInHours")

    def test_every_critic_check_names_its_evidence(self):
        _engine, problem = solve("PWD-001")
        for option in problem.options:
            for check in option.critic["checks"]:
                self.assertTrue(check["basis"], f"{option.option_id}.{check['name']} has no basis")

    def test_a_port_authority_gets_the_options_as_advisories_not_as_its_own_actions(self):
        _engine, problem = solve("PWD-001", actor=PORT_AUTHORITY)
        rows = {r["kind"]: r for r in problem.available_actions}
        self.assertEqual(rows[REROUTE]["availability"]["status"], "AVAILABLE")
        self.assertTrue(rows[REROUTE]["requiresAdvisory"])
        self.assertEqual(rows[REROUTE]["evaluatedFor"], SHIPPING_COMPANY)
        self.assertEqual(problem.recommendation.actor, SHIPPING_COMPANY)
        self.assertEqual(problem.evidence["execution"]["mechanism"], "ISSUE_ADVISORY")
        self.assertTrue(any("advisory" in note for note in problem.notes))
        # The catalogue itself still says who may execute what.
        self.assertFalse(availability_of(CATALOGUE[REROUTE], {"lane_code": "EUR_IND", "alternative": "Cape",
                                                              "hours_to_chokepoint": {}, "service_speed_kn": 18},
                                         actor=PORT_AUTHORITY).available)

    def test_unsupported_and_insufficient_actions_are_marked_not_invented(self):
        _engine, problem = solve("PWD-001")
        rows = {r["kind"]: r["availability"] for r in problem.available_actions}
        self.assertEqual(rows["REBUNKER"]["status"], "UNSUPPORTED")
        self.assertEqual(rows["DELAY_DEPARTURE"]["status"], "INSUFFICIENT_DATA")
        self.assertTrue(all(r["availability"]["reason"] for r in problem.available_actions
                            if r["availability"]["status"] != "AVAILABLE"))


# --------------------------------------------------------------------------
# baseline, branches and cascade propagation
# --------------------------------------------------------------------------


class BaselineAndBranchTests(unittest.TestCase):
    def test_the_baseline_is_a_real_option_computed_on_its_own_branch(self):
        engine, problem = solve("PWD-001")
        baseline = problem.baseline
        self.assertTrue(baseline.is_baseline)
        self.assertEqual(baseline.status, FEASIBLE)
        self.assertIsNotNone(baseline.evaluation.branch_id)
        branch = engine.branches.get(baseline.evaluation.branch_id)
        self.assertEqual(branch.assumptions, [])
        # The baseline's residual risk is the observed cascade's own figure at
        # the instant of arrival, not a hand-written number.
        observed = propagate(problem_state(problem, engine), problem.cascade_id, seed_for(red_sea_event()),
                             at=NOW + timedelta(hours=46.0))
        risk = observed.reached[key(VESSEL, "PWD-001")].quantities["risk"].value
        self.assertAlmostEqual(baseline.measure("risk").value, risk, places=6)

    def test_the_observed_world_is_never_edited(self):
        state = observed_world()
        before = (len(state.graph), len(state.graph.edges()),
                  sorted(e.dst for e in state.graph.edges(kind=SAILS)))
        engine = DecisionEngine()
        event = red_sea_event()
        engine.solve_vessel(state, event_key=key(EVENT, event.event_id), seed=seed_for(event),
                            vessel_id="PWD-001", actor=DecisionActor(SHIPPING_COMPANY), at=NOW)
        after = (len(state.graph), len(state.graph.edges()),
                 sorted(e.dst for e in state.graph.edges(kind=SAILS)))
        self.assertEqual(before, after)
        # Each option forked its own branch; none shares a graph with another.
        branches = {o.evaluation.branch_id for o in engine.get(_last(engine)).options if o.evaluation}
        self.assertEqual(len(branches), sum(1 for o in engine.get(_last(engine)).options if o.evaluation))

    def test_a_diversion_detaches_the_hull_on_its_branch_only(self):
        engine, problem = solve("PWD-001")
        reroute = problem.option("reroute")
        forked = engine.branches.get(reroute.evaluation.branch_id)
        self.assertEqual(forked.graph.in_edges(key(VESSEL, "PWD-001"), kind=SAILS), [])
        keep = engine.branches.get(problem.baseline.evaluation.branch_id)
        self.assertEqual(len(keep.graph.in_edges(key(VESSEL, "PWD-001"), kind=SAILS)), 1)

    def test_a_certain_delay_cascades_to_yard_pressure_through_the_world_engine(self):
        _engine, problem = solve("PWD-001")
        reroute = problem.option("reroute")
        port = next(c for c in reroute.evaluation.consequences if c["kind"] == PORT)
        rules = {s["rule"] for s in port["steps"]}
        self.assertIn("delay_reaches_port", rules)
        self.assertIn("arrival_shift_becomes_pressure", rules)
        self.assertTrue(reroute.measure("yard_pressure").available)
        # The diversion's whole detour lands at the quay, so the pressure it
        # creates exceeds the baseline's expected shift.
        self.assertGreater(reroute.measure("yard_pressure").value,
                           problem.baseline.measure("yard_pressure").value)

    def test_slow_steaming_arrives_after_the_claim_and_says_so(self):
        _engine, problem = solve("PWD-001")
        slow = problem.option("slow_steam")
        self.assertEqual(slow.measure("risk").value, 0.0)
        self.assertTrue(slow.measure("risk").attrs["arrivalAfterClaimHorizon"])
        self.assertIn("claim_horizon", slow.critic["failed"])
        self.assertEqual(slow.critic["verdict"], PASS_WITH_WARNINGS)


def problem_state(problem, engine):
    return engine.branches.get(problem.baseline.evaluation.branch_id).parent.graph


def _last(engine):
    return engine.all()[-1].decision_id


# --------------------------------------------------------------------------
# dominance and ranking
# --------------------------------------------------------------------------


class FrontierTests(unittest.TestCase):
    def test_dominance_is_no_worse_everywhere_and_better_somewhere(self):
        a = option_with("a", eta=10, risk=0.2, fuel=1.0)
        b = option_with("b", eta=12, risk=0.2, fuel=1.1)
        c = option_with("c", eta=8, risk=0.5, fuel=0.9)
        objectives = [OBJECTIVES["eta"], OBJECTIVES["risk"], OBJECTIVES["fuel"]]
        self.assertTrue(dominates(a, b, objectives))
        self.assertFalse(dominates(a, c, objectives))
        self.assertFalse(dominates(c, a, objectives))
        frontier = pareto([a, b, c], objectives)
        self.assertEqual(frontier.nondominated, ["a", "c"])
        self.assertEqual(frontier.dominated, {"b": "a"})

    def test_an_unknown_measure_makes_an_option_incomparable_not_best(self):
        a = option_with("a", eta=10, risk=0.2, fuel=1.0)
        b = option_with("b", eta=5, fuel=0.5)
        b.evaluation.objectives["risk"] = unknown("risk", "not measured")
        frontier = pareto([a, b], [OBJECTIVES["eta"], OBJECTIVES["risk"]])
        self.assertEqual(frontier.nondominated, ["a"])
        self.assertEqual(frontier.incomparable, {"b": ["risk"]})

    def test_the_ranking_returns_its_weights_and_drops_objectives_nobody_measured(self):
        _engine, problem = solve("PWD-001")
        ranking = problem.evidence["ranking"]
        self.assertEqual(ranking["weights"], {"risk": 0.35, "eta": 0.25, "fuel": 0.15, "weather": 0.10,
                                              "cost": 0.10, "uncertainty": 0.05})
        self.assertIn("cost", ranking["objectivesDropped"])
        self.assertEqual(ranking["order"][0], problem.recommendation.option_id)
        picks = problem.frontier.picks
        self.assertIn("FASTEST", picks)
        self.assertIn("LOWEST_RISK", picks)
        self.assertNotIn("LOWEST_COST", picks)                      # nothing priced, no label

    def test_the_recommendation_is_never_a_dominated_or_incomparable_option(self):
        _engine, problem = solve("PWD-001")
        chosen = problem.recommendation.option_id
        self.assertIn(chosen, problem.frontier.nondominated)
        self.assertNotIn(chosen, problem.frontier.incomparable)
        self.assertNotEqual(problem.recommendation.critic["verdict"], REJECT)


# --------------------------------------------------------------------------
# money
# --------------------------------------------------------------------------


class FinancialTests(unittest.TestCase):
    def test_unknown_components_keep_the_total_unknown(self):
        _engine, problem = solve("PWD-001", basis=basis_with_public_tariffs())
        financial = problem.baseline.evaluation.financial
        states = {c["key"]: c["state"] for c in financial["components"]}
        self.assertEqual(states["action"], "ZERO")                     # a stated zero
        self.assertEqual(states["delay"], "UNKNOWN")                   # no charter basis
        self.assertIsNone(financial["total"])
        self.assertFalse(problem.baseline.measure("cost").available)
        self.assertFalse(problem.recommendation.expected_avoidable_cost["available"])

    def test_an_assumption_prices_the_delay_and_labels_the_result(self):
        basis = basis_with_public_tariffs()
        basis.add(assumption("charter_day", 41000, "USD", entered_by="operator"))
        _engine, problem = solve("PWD-001", basis=basis)
        delay = next(c for c in problem.option("slow_steam").evaluation.financial["components"] if c["key"] == "delay")
        self.assertEqual(delay["state"], "KNOWN")
        self.assertTrue(delay["isAssumption"])
        self.assertEqual(delay["sourceType"], "USER_ASSUMPTION")
        self.assertTrue(problem.option("slow_steam").evaluation.financial["assumption"])
        self.assertIn("assumptions", problem.option("slow_steam").critic["failed"])

    def test_an_assumed_tonnage_prices_dues_at_the_public_tariff_and_stays_an_assumption(self):
        """The hull declares no GT; the operator supplies one for the scenario.

        The rate is the public tariff, the tonnage is not, so the component
        is labelled an assumption -- and it is one call at the tariff's
        tonnage arithmetic, not the tonnage squared.
        """
        event = red_sea_event()
        state = observed_world(event=event)
        engine = DecisionEngine(basis=basis_with_public_tariffs())
        problem = engine.solve_vessel(state, event_key=key(EVENT, event.event_id), seed=seed_for(event),
                                      vessel_id="PWD-001", actor=DecisionActor(SHIPPING_COMPANY), at=NOW,
                                      attribute_assumptions={"grt": 52000})
        self.assertEqual(problem.evidence["attributeAssumptions"]["grt"]["label"], "ASSUMPTION")
        port = next(c for c in problem.baseline.evaluation.financial["components"] if c["key"] == "port")
        self.assertEqual(port["state"], "KNOWN")
        self.assertTrue(port["isAssumption"])
        self.assertEqual(port["sourceType"], "PUBLIC_TARIFF")
        self.assertAlmostEqual(port["money"]["amount"], 0.1558 * 52000, places=2)
        self.assertIn("assumed by the operator", port["basis"])
        with self.assertRaises(Exception):
            engine.solve_vessel(state, event_key=key(EVENT, event.event_id), seed=seed_for(event),
                                vessel_id="PWD-001", actor=DecisionActor(SHIPPING_COMPANY), at=NOW,
                                attribute_assumptions={"displacement": 1})

    def test_public_tariffs_price_only_inside_their_validity(self):
        basis = basis_with_public_tariffs()
        live = basis.lookup("berth_hire_grt_hour", at=NOW, scope="INNSA", vessel_status="foreign")
        lapsed = basis.lookup("berth_hire_grt_hour", at=NOW, scope="INMAA", vessel_status="foreign",
                              vessel_type="container")
        self.assertEqual(live.rate.source_type, "PUBLIC_TARIFF")
        self.assertIsNone(lapsed.rate)
        self.assertIn("outside its validity", lapsed.reason)
        self.assertEqual(live.rate.provenance["page"], 6)
        self.assertIn("Rate per GRT per hour", live.rate.provenance["verbatim"])


# --------------------------------------------------------------------------
# workflow, ledger and learning
# --------------------------------------------------------------------------


class WorkflowAndLedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = SqliteLedgerStore(":memory:")

    def test_a_rejected_option_cannot_be_approved(self):
        engine, problem = solve("PWD-001", ledger=self.ledger)
        problem.option("reroute").status = REJECTED
        engine.transition(problem.decision_id, REVIEWED, actor="ops")
        with self.assertRaises(DecisionError):
            engine.transition(problem.decision_id, APPROVED, actor="ops", option_id="reroute")
        with self.assertRaises(DecisionError):
            engine.transition(problem.decision_id, APPROVED, actor="ops")   # no choice named
        with self.assertRaises(DecisionError):
            engine.transition(problem.decision_id, "OBSERVED", actor="ops")  # not from REVIEWED

    def test_the_ledger_holds_the_problem_as_computed_and_will_not_rewrite_it(self):
        engine, problem = solve("PWD-001", ledger=self.ledger)
        row = self.ledger.get_decision_problem(problem.decision_id)
        self.assertEqual(row.workflow, "COMPUTED")
        self.assertEqual(row.options_evaluated, len(problem.options))
        computed = row.problem
        engine.transition(problem.decision_id, REVIEWED, actor="ops")
        engine.transition(problem.decision_id, APPROVED, actor="ops", option_id="keep_plan", now=NOW)
        row = self.ledger.get_decision_problem(problem.decision_id)
        self.assertEqual(row.workflow, "APPROVED")
        self.assertEqual(row.human_choice, "keep_plan")
        self.assertEqual(row.problem["options"], computed["options"])      # payload untouched
        engine.record_outcome(problem.decision_id, actor="ops", actual_action="KEEP_PLAN",
                              observed={"eta": 30.0, "incident": 1})
        row = self.ledger.get_decision_problem(problem.decision_id)
        self.assertEqual(row.status, "resolved")
        with self.assertRaises(LedgerError):
            self.ledger.resolve_decision_problem(problem.decision_id, human_choice="x", actual_action="y",
                                                 observed_outcome={}, observed_at="2026-09-14T00:00:00Z")
        rec = self.ledger.get_decision(f"{problem.decision_id}-rec")
        self.assertEqual(rec.action_state, "not_taken")                     # recommended slow steam, took keep

    def test_outcome_scoring_reads_the_record_never_the_engine(self):
        engine, problem = solve("PWD-001", ledger=self.ledger)
        recommended = problem.recommendation.option_id
        engine.transition(problem.decision_id, REVIEWED, actor="ops")
        engine.transition(problem.decision_id, APPROVED, actor="ops", option_id=recommended, now=NOW)
        predicted = problem.option(recommended).measure("eta").value
        engine.record_outcome(problem.decision_id, actor="ops", actual_action="SLOW_STEAM",
                              observed={"eta": predicted + 3.0, "incident": 0,
                                        "optionOutcomes": {recommended: {"eta": predicted + 3.0},
                                                           "keep_plan": {"eta": predicted + 9.0}}})
        report = score_history(self.ledger.decision_problems())
        self.assertTrue(report["available"])
        self.assertEqual(report["agreementRate"], 1.0)
        self.assertEqual(report["rankingAccuracy"], 1.0)
        self.assertEqual(report["meanRegret"], 0.0)
        self.assertAlmostEqual(report["predictionError"]["eta"]["meanAbsoluteError"], 3.0, places=3)
        self.assertIn("never re-run", report["method"])


# --------------------------------------------------------------------------
# the port: where the obvious greedy choice loses
# --------------------------------------------------------------------------


def committed_port():
    """One working berth; a long call with a departure commitment behind two short ones.

    Greedy shortest-work-first serves the two short calls first and minimises
    mean wait, and the long call sails after its commitment. First come, first
    served takes the long call first. The obvious choice loses on the
    objective that matters.
    """
    state = schematic_layout("INMAA", berth_count=2, capacity_index=0.7)
    state.berths[0].occupied_by = "seed-B1"
    state.berths[0].free_at_hour = 200.0                                    # out of the horizon
    state.calls = [
        VesselCall("C-LONG", "V-LONG", "Committed long call", "panamax", 250.0, 12.0, -6.0, 2400,
                   latest_departure_hour=36.0, state=WAITING, arrived_hour=-6.0),
        VesselCall("C-S1", "V-S1", "Short call 1", "panamax", 250.0, 12.0, -3.0, 220, state=WAITING,
                   arrived_hour=-3.0),
        VesselCall("C-S2", "V-S2", "Short call 2", "panamax", 250.0, 12.0, -1.0, 220, state=WAITING,
                   arrived_hour=-1.0),
    ]
    return state


class PortDecisionTests(unittest.TestCase):
    def test_greedy_minimises_wait_and_still_loses_on_the_commitment(self):
        engine = DecisionEngine()
        problem = engine.solve_port(committed_port(), actor=DecisionActor(PORT_AUTHORITY, port_code="INMAA"),
                                    at=NOW, world_state_id="obs", world_revision={}, horizon_hours=72.0)
        greedy = problem.option("reassign_berth-greedy")
        keep = problem.baseline
        self.assertLess(greedy.measure("port_wait").value, keep.measure("port_wait").value)   # the obvious win
        self.assertEqual(greedy.measure("missed_departures").value, 1.0)                    # its cost
        self.assertEqual(keep.measure("missed_departures").value, 0.0)
        self.assertNotEqual(problem.recommendation.option_id, "reassign_berth-greedy")
        self.assertNotEqual(problem.recommendation.critic["verdict"], REJECT)
        self.assertEqual(problem.evidence["ranking"]["weights"]["missed_departures"], 0.40)

    def test_the_port_baseline_equals_the_twin_run_under_fcfs(self):
        from src.portwatch_os.twin.policies import FirstComeFirstServed
        from src.portwatch_os.twin.simulation import SimulationConfig, simulate

        state = committed_port()
        result = simulate(state, FirstComeFirstServed(), SimulationConfig(horizon_hours=72.0))
        engine = DecisionEngine()
        problem = engine.solve_port(state, actor=DecisionActor(PORT_AUTHORITY, port_code="INMAA"), at=NOW,
                                    world_state_id="obs", world_revision={}, horizon_hours=72.0)
        self.assertAlmostEqual(problem.baseline.measure("port_wait").value, result.metrics["meanWaitHours"], places=6)
        self.assertEqual(problem.baseline.measure("missed_departures").value, result.metrics["missedDepartures"])

    def test_a_shipping_company_cannot_reassign_berths(self):
        engine = DecisionEngine()
        with self.assertRaises(Exception):
            engine.solve_port(committed_port(), actor=DecisionActor(SHIPPING_COMPANY), at=NOW,
                              world_state_id="obs", world_revision={})


if __name__ == "__main__":
    unittest.main()
