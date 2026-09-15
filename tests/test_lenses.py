"""Trade exposure and the security lens.

Trade: every chain is a catalogued fact with a source; no tonnage or value
appears anywhere in the payload; a port-acting event reaches its ports
without a strait; a strait event reaches ports only through lanes that
transit it.

Security: each rule fires on a track built to trip it and names its rule,
evidence, threshold, confidence and instants; a clean track fires nothing;
under SIMULATED_TRAFFIC the lens is UNAVAILABLE and runs no rule.
"""

from __future__ import annotations

import os
import re
import unittest
from collections import deque
from datetime import datetime, timedelta, timezone

from src.portwatch_os.fabric.ais.messages import AisObservation
from src.portwatch_os.fabric.ais.tracks import Track
from src.portwatch_os.security import UNAVAILABLE, analyse_track, security_lens
from src.portwatch_os.security.rules import AVAILABLE
from src.portwatch_os.trade import CLASSES, port_classes, structural_exposure
from src.portwatch_os.trade.catalogue import BPS_ROWS_PRESENT, ROW_CLASS, STATEMENTS

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def _event(chokepoints=(), ports=(), event_id="EV"):
    from src.portwatch_os.global_eye.model import GlobalEvent

    return GlobalEvent(
        event_id=event_id, title="t", category="chokepoint_disruption" if chokepoints else "cyclone", region="r",
        lat=12.0, lon=43.0, geolocation_basis="chokepoint" if chokepoints else "port", first_seen=NOW.isoformat(),
        last_seen=NOW.isoformat(), source_count=2, confidence=0.8, severity=0.8, chokepoints=list(chokepoints),
        threatened_ports=list(ports),
    )


class TradeExposureTests(unittest.TestCase):
    def test_every_link_carries_a_source_and_no_link_carries_a_number(self):
        links = port_classes()
        self.assertGreater(len(links), 50)
        for link in links:
            self.assertTrue(link.sources, f"{link.port_code} {link.commodity_class} has no source")
            for source in link.sources:
                self.assertTrue(source.get("url"))
                self.assertTrue(source.get("retrievedAt"))
            self.assertIn(link.commodity_class, CLASSES)
        text = str([l.to_dict() for l in links])
        self.assertNotIn("tonne", text.lower().replace("tonnages are not reproduced", "").replace("tonnage", ""))
        for forbidden in ("MMT", "million tonnes", "TEU/year", "crore", "₹"):
            self.assertNotIn(forbidden, text)

    def test_the_ministry_table_rows_map_to_classes_and_every_registry_port_is_covered(self):
        from src.utils import port_registry

        for rows in BPS_ROWS_PRESENT.values():
            for row in rows:
                self.assertIn(row, ROW_CLASS, row)
        covered = {l.port_code for l in port_classes()}
        for port in port_registry.all_ports():
            self.assertIn(port.locode, covered, port.locode)
        self.assertIn(("INMUN", "CONTAINER"), STATEMENTS, "the one non-major port is sourced from its operator")

    def test_a_strait_event_reaches_ports_only_through_lanes_that_transit_it(self):
        out = structural_exposure([_event(chokepoints=["HORMUZ"])])
        self.assertEqual(out["kind"], "STRUCTURAL EXPOSURE")
        lanes = {c["laneCode"] for c in out["chains"]}
        self.assertEqual(lanes, {"GULF_IND"})
        ports = {c["portCode"] for c in out["chains"]}
        self.assertEqual(ports, {"INNSA", "INMUN", "INVTZ", "INIXY"})
        for chain in out["chains"]:
            self.assertEqual(chain["path"][0], "event:EV")
            self.assertEqual(chain["path"][1], "chokepoint:HORMUZ")
            self.assertEqual(chain["path"][-1], f"commodity:{chain['commodityClass']}")
        self.assertIn("No tonnage", out["disclaimer"])
        text = str(out)
        self.assertFalse(re.search(r"\b\d+(\.\d+)? ?(MMT|million tonnes|TEU)\b", text))

    def test_a_port_acting_event_reaches_its_ports_without_a_strait(self):
        out = structural_exposure([_event(ports=["INIXY", "INMUN"])])
        self.assertTrue(out["chains"])
        for chain in out["chains"]:
            self.assertIsNone(chain["chokepoint"])
            self.assertIsNone(chain["laneCode"])
            self.assertIn(chain["portCode"], ("INIXY", "INMUN"))
        exposed = {c["commodityClass"] for c in out["classes"] if c["exposed"]}
        self.assertIn("CRUDE", exposed)
        self.assertIn("CONTAINER", exposed)
        lng = next(c for c in out["classes"] if c["commodityClass"] == "LNG")
        self.assertEqual(lng["ports"], ["INMUN"], "Kandla has no sourced LNG link; Mundra does")

    def test_an_event_that_touches_nothing_exposes_nothing_and_says_so(self):
        out = structural_exposure([_event(chokepoints=["PANAMA"])])
        self.assertEqual(out["chains"], [])
        for row in out["classes"]:
            self.assertFalse(row["exposed"])
            self.assertIn("no structural chain", row["statement"])


def _obs(mmsi: str, lat: float, lon: float, at: datetime, *, sog=12.0, cog=90.0, status="under way using engine"):
    return AisObservation(provider_id="aisstream", message_type="PositionReport", mmsi=mmsi, lat=lat, lon=lon,
                          source_timestamp=at, ingested_at=at, sog_knots=sog, cog_degrees=cog, nav_status=status)


def _track(mmsi: str, observations, *, destination=None) -> Track:
    return Track(mmsi=mmsi, positions=deque(observations, maxlen=240), destination_text=destination)


class SecurityRuleTests(unittest.TestCase):
    def _assert_shape(self, detection):
        payload = detection.to_dict()
        for key in ("rule", "evidence", "threshold", "confidence", "observationTimestamps", "statement"):
            self.assertIn(key, payload)
        self.assertTrue(payload["threshold"])
        self.assertTrue(payload["observationTimestamps"])
        self.assertTrue(0.0 < payload["confidence"] <= 1.0)

    def test_a_clean_passage_fires_nothing(self):
        # Twelve knots east along 15N, a report every twenty minutes for four hours.
        observations = [_obs("100", 15.0, 60.0 + i * (12.0 / 3 / 60.0) / 60.0 * 60.0 / 57.0, NOW - timedelta(hours=4) + timedelta(minutes=20 * i))
                        for i in range(13)]
        self.assertEqual(analyse_track(_track("100", observations), now=NOW), [])

    def test_prolonged_gap_and_open_gap(self):
        observations = [_obs("101", 15.0, 60.0, NOW - timedelta(hours=9)), _obs("101", 15.0, 61.0, NOW - timedelta(hours=5))]
        found = analyse_track(_track("101", observations), now=NOW)
        rules = [d.rule for d in found]
        self.assertEqual(rules.count("prolonged_ais_gap"), 2, rules)
        closed, open_ = [d for d in found if d.rule == "prolonged_ais_gap"]
        self.assertAlmostEqual(closed.evidence["gapHours"], 4.0, places=1)
        self.assertTrue(open_.evidence["open"])
        for d in found:
            self._assert_shape(d)

    def test_an_improbable_jump_names_the_implied_speed(self):
        observations = [_obs("102", 15.0, 60.0, NOW - timedelta(hours=1)), _obs("102", 15.0, 63.0, NOW - timedelta(minutes=30))]
        found = [d for d in analyse_track(_track("102", observations), now=NOW) if d.rule == "improbable_position_jump"]
        self.assertEqual(len(found), 1)
        self.assertGreater(found[0].evidence["impliedSpeedKn"], 50.0)
        self.assertEqual(found[0].threshold["impliedSpeedKn"], 50.0)
        self._assert_shape(found[0])

    def test_loitering_far_from_any_port_while_under_way(self):
        observations = [_obs("103", 10.0, 70.0 + (i % 2) * 0.01, NOW - timedelta(hours=8) + timedelta(minutes=30 * i), sog=0.4)
                        for i in range(17)]
        found = [d for d in analyse_track(_track("103", observations), now=NOW) if d.rule == "unusual_loitering"]
        self.assertEqual(len(found), 1)
        self.assertGreaterEqual(found[0].evidence["hours"], 6.0)
        self.assertGreater(found[0].evidence["nearestPortNm"], 25.0)
        self._assert_shape(found[0])

    def test_loitering_at_a_port_approach_is_not_a_finding(self):
        # Sitting off Nhava Sheva for eight hours is a queue, not loitering.
        observations = [_obs("104", 18.85, 72.8 + (i % 2) * 0.01, NOW - timedelta(hours=8) + timedelta(minutes=30 * i), sog=0.3)
                        for i in range(17)]
        self.assertEqual([d for d in analyse_track(_track("104", observations), now=NOW) if d.rule == "unusual_loitering"], [])

    def test_a_course_sustained_away_from_the_resolved_destination(self):
        # Bound for Chennai (INMAA, ~13.1N 80.3E) but steaming east, away from it.
        observations = [_obs("105", 12.0, 82.0 + i * 0.2, NOW - timedelta(hours=3) + timedelta(hours=i), cog=90.0)
                        for i in range(4)]
        found = [d for d in analyse_track(_track("105", observations, destination="INMAA"), now=NOW)
                 if d.rule == "destination_inconsistency"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].evidence["destinationPort"], "INMAA")
        self.assertEqual(len(found[0].observation_timestamps), 3)
        self._assert_shape(found[0])

    def test_speed_that_contradicts_the_declared_status(self):
        moving_at_anchor = [_obs("106", 15.0, 60.0, NOW - timedelta(minutes=5), sog=6.0, status="at anchor")]
        found = [d for d in analyse_track(_track("106", moving_at_anchor), now=NOW) if d.rule == "abnormal_speed_state"]
        self.assertEqual(len(found), 1)
        self.assertIn("at anchor", found[0].statement)
        stopped_under_way = [_obs("107", 15.0, 60.0, NOW - timedelta(hours=3) + timedelta(hours=i), sog=0.0) for i in range(4)]
        found = [d for d in analyse_track(_track("107", stopped_under_way), now=NOW) if d.rule == "abnormal_speed_state"]
        self.assertTrue(found)
        self.assertGreaterEqual(found[0].evidence["hoursStopped"], 2.0)

    def test_repeated_identity_conflicts_from_the_fusion_engine(self):
        from src.portwatch_os.fusion.model import Conflict

        conflicts = [Conflict(canonical_id="c", attribute="imo", held="1", claimed="2", held_by="a", claimed_by="b",
                              at=NOW - timedelta(minutes=i), reason="r") for i in range(2)]
        observations = [_obs("108", 15.0, 60.0, NOW - timedelta(minutes=1))]
        found = [d for d in analyse_track(_track("108", observations), now=NOW, conflicts=conflicts)
                 if d.rule == "repeated_identity_conflict"]
        self.assertEqual(len(found), 1)
        self.assertEqual(len(found[0].evidence["conflicts"]), 2)


class SecurityLensTests(unittest.TestCase):
    def test_unavailable_under_the_replay_and_no_rule_runs(self):
        trap = _track("999", [_obs("999", 15.0, 60.0, NOW - timedelta(hours=1)), _obs("999", 15.0, 63.0, NOW)])
        out = security_lens(traffic={"mode": "SIMULATED_TRAFFIC", "statement": "replay"}, tracks=[trap], now=NOW)
        self.assertEqual(out["status"], UNAVAILABLE)
        self.assertEqual(out["detections"], [])
        self.assertEqual(out["tracksAnalysed"], 0)
        self.assertIn("replay", out["reason"])
        self.assertIn("thresholds", out)

    def test_available_on_observed_traffic_and_stale_is_said(self):
        trap = _track("999", [_obs("999", 15.0, 60.0, NOW - timedelta(hours=1)), _obs("999", 15.0, 63.0, NOW)])
        out = security_lens(traffic={"mode": "AIS_STALE", "statement": "stale"}, tracks=[trap], now=NOW)
        self.assertEqual(out["status"], AVAILABLE)
        self.assertTrue(out["stale"])
        self.assertEqual(out["tracksAnalysed"], 1)
        self.assertTrue(any(d["rule"] == "improbable_position_jump" for d in out["detections"]))

    def test_the_route_refuses_under_demo_replay(self):
        from fastapi.testclient import TestClient

        from backend.app.main import app

        os.environ["PORTWATCH_FRESHNESS_SCHEDULER"] = "0"
        if os.getenv("AISSTREAM_API_KEY"):
            self.skipTest("a live key is configured")
        with TestClient(app) as client:
            body = client.get("/api/security/lens", params={"mode": "DEMO"}).json()
            self.assertEqual(body["status"], UNAVAILABLE)
            self.assertEqual(body["detections"], [])
            trade = client.get("/api/trade/exposure").json()
            self.assertEqual(trade["kind"], "STRUCTURAL EXPOSURE")


if __name__ == "__main__":
    unittest.main()
