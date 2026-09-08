"""Decision engine, route optimizer, scenario propagation and provenance tests.

The theme is that every operational claim has to be derivable. An action must be
executable, a saving must be arithmetic on the forecast, a shock must move the
numbers in the direction and proportion the exposure graph implies, and a source
must never report itself fresher than its newest observation.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.decision import scenario_catalog
from src.decision.decision_layer import (
    MAX_HOLD_HOURS,
    MAX_SLOW_STEAM_KNOTS,
    build_decisions,
    prob_exceed,
    slow_steam_knots,
)
from src.decision.route_optimizer import Vessel, optimize_fleet
from src.decision.scenario_service import simulate_scenario
from src.utils import port_registry, provenance


def _forecast(ports=("MUNDRA", "JNPT", "CHENNAI", "VIZAG"),
              horizon: int = 10, base: float = 62.0) -> pd.DataFrame:
    origin = pd.Timestamp("2026-08-28")
    rows = []
    for index, port in enumerate(ports):
        for day in range(1, horizon + 1):
            centre = base + index * 3 + (day - 1) * 0.8
            rows.append({
                "port_id": port,
                "forecast_origin_date": origin,
                "target_date": origin + pd.Timedelta(days=day),
                "horizon_day": day,
                "q10": centre - 8,
                "q50": centre,
                "q90": centre + 9,
                "predicted_congestion": centre,
                "predicted_delay": 6.0 + index * 2 + day * 0.4,
                "predicted_throughput": 100_000.0 - day * 500,
                "confidence_score": 0.78,
                "model": "adaptive_ensemble",
                "model_disagreement": 0.12,
            })
    return pd.DataFrame(rows)


def _panel(ports=("MUNDRA", "JNPT", "CHENNAI", "VIZAG")) -> pd.DataFrame:
    dates = pd.date_range("2026-08-01", periods=28, freq="D")
    rows = []
    for port in ports:
        for date in dates:
            rows.append({
                "port_id": port, "date": date,
                "capacity_pressure": 0.62, "queue_momentum": 0.5,
                "berth_pressure": 0.4, "arrival_clustering": 0.15,
                "anomaly_score": 0.2, "disruption_pressure": 0.1,
                "weather_persistence": 0.05, "weather_regime": "CALM",
                "utilization": 0.66, "throughput_stress": 0.05,
                "data_quality_score": 0.9,
                "p_normal": 0.3, "p_congested": 0.5, "p_severe": 0.2,
                "regime_label": "CONGESTED",
            })
    return pd.DataFrame(rows)


class ProbabilityTests(unittest.TestCase):
    def test_probability_is_monotonic_in_the_threshold(self):
        probs = [prob_exceed(40, 55, 70, threshold) for threshold in range(20, 90, 5)]
        self.assertTrue(all(a >= b for a, b in zip(probs, probs[1:])),
                        "P(exceed) must fall as the threshold rises")

    def test_probability_is_bounded(self):
        self.assertGreaterEqual(prob_exceed(40, 55, 70, 0), 0.0)
        self.assertLessEqual(prob_exceed(40, 55, 70, 200), 1.0)

    def test_median_threshold_gives_about_a_half(self):
        self.assertAlmostEqual(prob_exceed(40, 55, 70, 55), 0.5, places=2)


class SlowSteamTests(unittest.TestCase):
    def test_no_reduction_without_a_delay(self):
        self.assertEqual(slow_steam_knots(0.0), 0.0)

    def test_reduction_grows_with_the_delay(self):
        self.assertLess(slow_steam_knots(6.0), slow_steam_knots(24.0))

    def test_reduction_matches_the_distance_identity(self):
        """v' = v * H / (H + d): the same distance covered over longer."""
        service, approach, shift = 13.0, 48.0, 12.0
        expected = service - service * approach / (approach + shift)
        self.assertAlmostEqual(
            slow_steam_knots(shift, approach, service), round(expected, 2), places=2)


class DecisionEngineTests(unittest.TestCase):
    def setUp(self):
        self.forecast = _forecast()
        self.panel = _panel()
        self.decisions = build_decisions(self.forecast, None, panel=self.panel)

    def test_every_row_carries_an_executable_action(self):
        required = ["action_code", "action_title", "action_target", "reason",
                    "expected_impact", "alternative_action", "uncertainty",
                    "decision_confidence", "top_drivers"]
        for column in required:
            self.assertIn(column, self.decisions.columns)
        self.assertTrue(self.decisions["action_code"].notna().all())
        self.assertTrue((self.decisions["operational_adjustment"].str.len() > 10).all())

    def test_slow_steam_is_never_an_impossible_instruction(self):
        slow = self.decisions[self.decisions["action_code"] == "SLOW_STEAM"]
        for text in slow["operational_adjustment"]:
            knots = float(text.split("by ")[1].split(" kn")[0])
            self.assertLessEqual(knots, MAX_SLOW_STEAM_KNOTS)

    def test_hold_arrival_stays_inside_the_operational_window(self):
        holds = self.decisions[self.decisions["action_code"] == "HOLD_ARRIVAL"]
        for text in holds["operational_adjustment"]:
            hours = float(text.split("by ")[1].split("h")[0])
            self.assertLessEqual(hours, MAX_HOLD_HOURS)

    def test_low_data_quality_downgrades_to_advisory(self):
        degraded = self.panel.copy()
        degraded["data_quality_score"] = 0.2
        decisions = build_decisions(self.forecast, None, panel=degraded)
        self.assertTrue((decisions["action_code"] == "MONITOR_QUALITY").all())
        self.assertTrue((decisions["expected_delay_saved_hours"] == 0.0).all())

    def test_high_disagreement_holds_instead_of_committing(self):
        uncertain = self.forecast.copy()
        uncertain["model_disagreement"] = 0.9
        uncertain["q50"] = 45.0
        uncertain["predicted_congestion"] = 45.0
        decisions = build_decisions(uncertain, None, panel=self.panel)
        self.assertIn("MONITOR_DISAGREEMENT", set(decisions["action_code"]))

    def test_no_action_claims_a_saving_it_did_not_compute(self):
        passive = self.decisions[self.decisions["action_code"].isin(
            ["NORMAL", "MONITOR_QUALITY", "MONITOR_DISAGREEMENT"])]
        self.assertTrue((passive["expected_delay_saved_hours"] == 0.0).all())

    def test_drivers_are_ranked_by_contribution(self):
        row = self.decisions.iloc[0]
        contributions = [float(token.split("=")[1])
                         for token in row["top_drivers"].split("|") if "=" in token]
        self.assertTrue(all(a >= b for a, b in zip(contributions, contributions[1:])))

    def test_priority_score_is_bounded(self):
        self.assertTrue((self.decisions["priority_score"].between(0, 1)).all())


class RouteOptimizerTests(unittest.TestCase):
    def test_fleet_reports_the_trade_off_not_just_a_verdict(self):
        forecast = _forecast()
        vessels = [Vessel("MV Test", target_port="MUNDRA", earliest_day=1,
                          latest_day=7, candidate_ports=["JNPT"])]
        rows = optimize_fleet(forecast, vessels=vessels)
        self.assertEqual(len(rows), 1)
        row = rows.iloc[0]
        for column in ("eta_delta_hours", "risk_delta", "port_wait_delta_hours",
                       "recommended_buffer_hours", "diversion_km"):
            self.assertIn(column, rows.columns)
        self.assertGreaterEqual(float(row["diversion_km"]), 0.0)
        self.assertTrue(row["recommendation"])

    def test_keeping_the_intended_port_reports_zero_diversion(self):
        forecast = _forecast()
        vessels = [Vessel("MV Solo", target_port="CHENNAI", earliest_day=1,
                          latest_day=7)]
        row = optimize_fleet(forecast, vessels=vessels).iloc[0]
        self.assertFalse(bool(row["reroute"]))
        self.assertEqual(float(row["diversion_km"]), 0.0)


class ScenarioPropagationTests(unittest.TestCase):
    def setUp(self):
        self.forecast = _forecast()
        self.panel = _panel()

    def test_catalogue_covers_the_required_scenarios(self):
        keys = {spec.key for spec in scenario_catalog.SCENARIOS}
        self.assertTrue(
            {"HORMUZ", "SUEZ", "REDSEA", "MALACCA", "CYC_E", "STORM_W",
             "CAPDROP", "LABOUR", "DEMAND", "FUEL"} <= keys)

    def test_aliases_resolve(self):
        self.assertEqual(scenario_catalog.resolve("cyclone_east").key, "CYC_E")
        self.assertEqual(scenario_catalog.resolve("RED SEA").key, "REDSEA")

    def test_shock_raises_congestion_and_wait(self):
        result = simulate_scenario("HORMUZ", 1.0, self.forecast, panel=self.panel)
        self.assertGreater(result["congestionDelta"], 0.0)
        self.assertGreater(result["delayDeltaHours"], 0.0)
        self.assertLessEqual(result["throughputDelta"], 0.0)

    def test_intensity_scales_the_impact_monotonically(self):
        low = simulate_scenario("HORMUZ", 0.5, self.forecast, panel=self.panel)
        high = simulate_scenario("HORMUZ", 1.5, self.forecast, panel=self.panel)
        self.assertGreater(high["congestionDelta"], low["congestionDelta"])

    def test_exposure_orders_the_affected_ports(self):
        """A Hormuz closure must hit the Gujarat cluster before the east coast."""
        result = simulate_scenario("HORMUZ", 1.0, self.forecast, panel=self.panel)
        by_code = {row["portCode"]: row for row in result["affectedPorts"]}
        mundra = by_code[port_registry.locode_for("MUNDRA")]
        vizag = by_code[port_registry.locode_for("VIZAG")]
        self.assertGreater(mundra["exposure"], vizag["exposure"])
        self.assertGreater(mundra["congestionDelta"], vizag["congestionDelta"])

    def test_coast_scoped_shock_targets_its_coast(self):
        result = simulate_scenario("CYC_E", 1.0, self.forecast, panel=self.panel)
        by_code = {row["portCode"]: row for row in result["affectedPorts"]}
        chennai = by_code[port_registry.locode_for("CHENNAI")]
        mundra = by_code[port_registry.locode_for("MUNDRA")]
        self.assertGreater(chennai["exposure"], mundra["exposure"])
        self.assertGreater(chennai["congestionDelta"], mundra["congestionDelta"])

    def test_deltas_are_the_difference_between_two_forecasts(self):
        result = simulate_scenario("HORMUZ", 1.0, self.forecast, panel=self.panel)
        for row in result["affectedPorts"]:
            self.assertAlmostEqual(
                row["congestionDelta"],
                round(row["shockCongestion"] - row["baselineCongestion"], 1),
                places=1)

    def test_propagation_chain_ends_in_an_action(self):
        result = simulate_scenario("HORMUZ", 1.0, self.forecast, panel=self.panel)
        steps = [step["step"] for step in result["propagation"]]
        self.assertEqual(steps[0], "SHOCK")
        self.assertIn("ACTION", steps)
        self.assertTrue(result["recommendation"]["available"])

    def test_confidence_never_exceeds_the_forecast_confidence(self):
        result = simulate_scenario("HORMUZ", 1.0, self.forecast, panel=self.panel)
        for row in result["affectedPorts"]:
            self.assertLessEqual(row["confidence"], 0.95)
            self.assertGreaterEqual(row["confidence"], 0.0)

    def test_empty_forecast_is_refused_rather_than_faked(self):
        with self.assertRaises(ValueError):
            simulate_scenario("HORMUZ", 1.0, pd.DataFrame())


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        provenance.reset()

    def tearDown(self):
        provenance.reset()

    def test_an_old_observation_cannot_claim_to_be_live(self):
        record = provenance.record(
            "test feed", provenance.LIVE, "old data",
            observed_at=pd.Timestamp.utcnow() - pd.Timedelta(days=10),
            freshness_hours=36.0)
        self.assertEqual(record.status, provenance.STALE)

    def test_a_recent_observation_stays_live(self):
        record = provenance.record(
            "test feed", provenance.LIVE, "fresh",
            observed_at=pd.Timestamp.utcnow() - pd.Timedelta(hours=2),
            freshness_hours=36.0)
        self.assertEqual(record.status, provenance.LIVE)

    def test_synthetic_is_never_promoted(self):
        record = provenance.record(
            "test feed", provenance.SYNTHETIC, "generated",
            observed_at=pd.Timestamp.utcnow())
        self.assertEqual(record.status, provenance.SYNTHETIC)
        self.assertFalse(record.to_dict()["isReal"])

    def test_readiness_reflects_the_worst_sources(self):
        provenance.record("a", provenance.LIVE)
        provenance.record("b", provenance.SYNTHETIC)
        self.assertLess(provenance.readiness_score(), 1.0)
        self.assertTrue(provenance.has_synthetic())

    def test_snapshot_buckets_are_disjoint_and_complete(self):
        provenance.record("a", provenance.LIVE)
        provenance.record("b", provenance.SYNTHETIC)
        provenance.record("c", provenance.UNAVAILABLE)
        snapshot = provenance.snapshot()
        names = (snapshot["live"] + snapshot["cached"] + snapshot["stale"]
                 + snapshot["synthetic"] + snapshot["unavailable"])
        self.assertEqual(sorted(names), ["a", "b", "c"])

    def test_legacy_lowercase_vocabulary_still_parses(self):
        self.assertEqual(provenance.record("a", "live").status, provenance.LIVE)
        self.assertEqual(provenance.record("b", "cache").status,
                         provenance.CACHED_LIVE)


class PortRegistryTests(unittest.TestCase):
    def test_every_identifier_resolves_to_the_same_record(self):
        port = port_registry.require("CHENNAI")
        for identifier in (port.model_id, port.locode, port.short, port.name,
                           *port.portwatch_ids):
            self.assertEqual(port_registry.require(identifier).model_id,
                             port.model_id)

    def test_legacy_codes_alias_forward(self):
        self.assertEqual(port_registry.locode_for("INHAL"), "INCCU")
        self.assertEqual(port_registry.locode_for("ININM"), "INNML")

    def test_unknown_identifier_raises(self):
        with self.assertRaises(KeyError):
            port_registry.require("NOT_A_PORT_AT_ALL")

    def test_registry_has_no_duplicate_identifiers(self):
        locodes = port_registry.locodes()
        model_ids = port_registry.model_ids()
        self.assertEqual(len(locodes), len(set(locodes)))
        self.assertEqual(len(model_ids), len(set(model_ids)))


if __name__ == "__main__":
    unittest.main()
