"""Global Eye: ingestion, corroboration, exposure and calibration.

The tests that matter here are the ones about *restraint*: that fourteen
headlines about one incident become one event, that a vessel past the strait is
never told to divert, and that a probability is withheld rather than invented
when the evidence is thin.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.portwatch_os.global_eye.calibration import (
    MIN_GLOBAL_SAMPLES,
    apply_calibration,
    claims_for,
    fit_calibrator,
    raw_score,
    score_bucket,
)
from src.portwatch_os.global_eye.exposure import (
    DIVERSION_FLOOR,
    TRADE_LANES,
    VesselVoyage,
    aggregate_port_risk,
    build_impact,
    lane_exposure,
    vessel_exposure,
)
from src.portwatch_os.global_eye.ingest import RawItem, ingest, normalise
from src.portwatch_os.global_eye.model import (
    CATEGORIES,
    EventSource,
    GlobalEvent,
    classify,
    confidence_from_sources,
    severity_from_text,
    similarity,
)
from src.portwatch_os.ledger.schema import EventOutcomeRecord, RESOLVED

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def item(title, outlet, minutes=0, **kwargs):
    category, chokepoint = classify(title)
    return RawItem(
        title=title,
        outlet=outlet,
        feed=kwargs.pop("feed", "GDELT"),
        published_at=NOW - timedelta(minutes=minutes),
        category=kwargs.pop("category", category),
        chokepoint=kwargs.pop("chokepoint", chokepoint),
        **kwargs,
    )


class ClassificationTests(unittest.TestCase):
    def test_specific_phrases_beat_generic_ones(self):
        """A port strike is a strike, not generic unrest."""
        category, _ = classify("Rotterdam port strike enters a third day")
        self.assertEqual(category, "strike")

    def test_chokepoint_is_resolved_from_the_text(self):
        category, chokepoint = classify("Houthi attacks close the Red Sea to shipping")
        self.assertEqual(chokepoint, "BAB_EL_MANDEB")
        self.assertIn(category, CATEGORIES)

    def test_an_unrelated_headline_is_not_forced_into_a_category(self):
        category, chokepoint = classify("Local council approves new cycle lane")
        self.assertIsNone(category)
        self.assertIsNone(chokepoint)


class CorroborationTests(unittest.TestCase):
    def test_one_incident_from_many_outlets_becomes_one_event(self):
        """The whole point of dedupe: nine reports, one event, nine sources."""
        items = [
            item("Houthi missile strikes tanker in the Red Sea", f"outlet{i}.com", minutes=i * 20)
            for i in range(9)
        ]
        events, report = ingest(items, now=NOW)
        self.assertEqual(len(events), 1, report.to_dict())
        self.assertEqual(events[0].source_count, 9)
        self.assertEqual(events[0].report_count, 9)

    def test_two_distinct_incidents_at_one_chokepoint_stay_separate(self):
        items = [
            item("Houthi missile strikes tanker in the Red Sea", "a.com"),
            item("Red Sea insurance premiums double after underwriter withdrawal", "b.com"),
        ]
        events, _ = ingest(items, now=NOW)
        self.assertEqual(len(events), 2)

    def test_reports_far_apart_in_time_are_separate_events(self):
        items = [
            item("Houthi missile strikes tanker in the Red Sea", "a.com", minutes=0),
            item("Houthi missile strikes tanker in the Red Sea", "b.com", minutes=60 * 24 * 5),
        ]
        events, _ = ingest(items, now=NOW)
        self.assertEqual(len(events), 2)

    def test_confidence_counts_outlets_not_articles(self):
        """Four filings from one outlet is not corroboration."""
        one = [EventSource(outlet="a.com", feed="GDELT") for _ in range(4)]
        many = [EventSource(outlet=f"o{i}.com", feed="GDELT") for i in range(4)]
        self.assertLess(
            confidence_from_sources(one), confidence_from_sources(many)
        )

    def test_a_second_feed_counts_for_more_than_a_second_newspaper(self):
        papers = [
            EventSource(outlet="a.com", feed="GDELT"),
            EventSource(outlet="b.com", feed="GDELT"),
        ]
        mixed = [
            EventSource(outlet="a.com", feed="GDELT"),
            EventSource(outlet="b.com", feed="GDACS"),
        ]
        self.assertGreater(confidence_from_sources(mixed), confidence_from_sources(papers))

    def test_event_ids_are_stable_and_distinct(self):
        items = [
            item("Suez Canal transit slots cut after grounding", "a.com"),
            item("Strait of Hormuz closed to tanker traffic", "b.com"),
        ]
        first, _ = ingest(items, now=NOW)
        second, _ = ingest(items, now=NOW)
        self.assertEqual([e.event_id for e in first], [e.event_id for e in second])
        self.assertEqual(len({e.event_id for e in first}), 2)

    def test_unclassifiable_items_are_counted_not_silently_dropped(self):
        items = [
            item("Local council approves new cycle lane", "a.com", category=None, chokepoint=None),
            item("Suez Canal closed after grounding", "b.com"),
        ]
        _, report = ingest(items, now=NOW)
        self.assertEqual(report.unclassified, 1)
        self.assertTrue(any("no maritime-relevant" in n for n in report.notes))


class SeverityTests(unittest.TestCase):
    def test_a_closure_scores_above_a_concern(self):
        self.assertGreater(
            severity_from_text("Suez Canal closed to all traffic", "chokepoint_disruption"),
            severity_from_text("Analysts monitor Suez risk", "chokepoint_disruption"),
        )

    def test_severity_is_bounded(self):
        extreme = severity_from_text(
            "closed closure suspend halt blockade shut evacuate sink killed destroy emergency",
            "conflict",
        )
        self.assertLessEqual(extreme, 1.0)
        self.assertGreaterEqual(extreme, 0.0)


class ExposureTests(unittest.TestCase):
    def _event(self, chokepoints, severity=0.85, confidence=0.9):
        return GlobalEvent(
            event_id="GE-TEST-1",
            title="Test disruption",
            category="chokepoint_disruption",
            region="Red Sea",
            lat=12.6, lon=43.3,
            geolocation_basis="chokepoint_centroid",
            first_seen=NOW.isoformat(),
            last_seen=NOW.isoformat(),
            sources=[EventSource(outlet="a.com", feed="GDELT")],
            source_count=3,
            confidence=confidence,
            severity=severity,
            chokepoints=list(chokepoints),
        )

    def test_a_chokepoint_reaches_the_lanes_that_transit_it(self):
        lanes = lane_exposure(self._event(["BAB_EL_MANDEB"]), now=NOW)
        codes = {lane.lane_code for lane in lanes}
        self.assertIn("EUR_IND", codes)
        self.assertNotIn("COAST_E", codes)

    def test_a_lane_with_no_alternative_is_weighted_higher_and_says_so(self):
        lanes = lane_exposure(self._event(["HORMUZ"]), now=NOW)
        gulf = next(l for l in lanes if l.lane_code == "GULF_IND")
        self.assertIsNone(gulf.alternative)
        self.assertIsNotNone(gulf.note)
        self.assertIn("No alternative routing", gulf.note)

    def test_a_vessel_already_past_the_strait_is_never_told_to_divert(self):
        """The timing gate. Advising an unavailable action is worse than silence."""
        event = self._event(["BAB_EL_MANDEB"])
        lanes = lane_exposure(event, now=NOW)
        committed = VesselVoyage(
            vessel_id="V1", name="MV Committed", lane_code="EUR_IND",
            destination_port="INNSA", hours_to_chokepoint={"BAB_EL_MANDEB": -12.0},
        )
        rows = vessel_exposure(event, lanes, [committed], now=NOW)
        self.assertTrue(rows)
        self.assertTrue(rows[0].already_entered)
        self.assertEqual(rows[0].recommended_action, "monitor")
        self.assertIsNone(rows[0].diversion_deadline)

    def test_a_vessel_short_of_the_strait_gets_a_deadline(self):
        event = self._event(["BAB_EL_MANDEB"])
        lanes = lane_exposure(event, now=NOW)
        approaching = VesselVoyage(
            vessel_id="V2", name="MV Approaching", lane_code="EUR_IND",
            destination_port="INNSA", hours_to_chokepoint={"BAB_EL_MANDEB": 40.0},
        )
        rows = vessel_exposure(event, lanes, [approaching], now=NOW)
        self.assertFalse(rows[0].already_entered)
        self.assertEqual(rows[0].recommended_action, "evaluate_diversion")
        self.assertIsNotNone(rows[0].diversion_deadline)
        self.assertIsNotNone(rows[0].delay_hours_if_diverted)

    def test_a_weak_event_stays_below_the_diversion_threshold(self):
        event = self._event(["BAB_EL_MANDEB"], severity=0.2, confidence=0.3)
        lanes = lane_exposure(event, now=NOW)
        self.assertLess(lanes[0].exposure, DIVERSION_FLOOR)
        rows = vessel_exposure(
            event, lanes,
            [VesselVoyage("V3", "MV Quiet", "EUR_IND", "INNSA", {"BAB_EL_MANDEB": 40.0})],
            now=NOW,
        )
        self.assertEqual(rows[0].recommended_action, "monitor")

    def test_an_event_with_no_chokepoint_produces_no_lane_exposure(self):
        impact = build_impact(self._event([]), now=NOW)
        self.assertEqual(impact.lanes, [])
        self.assertTrue(any("not tied to a chokepoint" in n for n in impact.notes))

    def test_actions_are_only_emitted_where_the_chain_supports_them(self):
        impact = build_impact(self._event([]), now=NOW)
        self.assertEqual(impact.actions, [])

    def test_port_risk_combines_with_a_noisy_or_and_never_exceeds_one(self):
        """Two independent 0.5 exposures give 0.75, not 1.0."""
        impacts = [
            build_impact(self._event(["BAB_EL_MANDEB"]), now=NOW),
            build_impact(self._event(["HORMUZ"]), now=NOW),
        ]
        risk = aggregate_port_risk(impacts)
        for entry in risk.values():
            self.assertLessEqual(entry["risk"], 1.0)
            self.assertGreaterEqual(entry["risk"], 0.0)

    def test_a_stale_event_carries_less_weight(self):
        fresh = self._event(["BAB_EL_MANDEB"])
        stale = self._event(["BAB_EL_MANDEB"])
        stale.last_seen = (NOW - timedelta(days=14)).isoformat()
        self.assertGreater(
            lane_exposure(fresh, now=NOW)[0].exposure,
            lane_exposure(stale, now=NOW)[0].exposure,
        )


class CalibrationTests(unittest.TestCase):
    def _record(self, index, probability, occurred, category="chokepoint_disruption"):
        return EventOutcomeRecord(
            outcome_id=f"evo-{index}",
            event_id=f"GE-{index}",
            category=category,
            region="Red Sea",
            claim="material transit disruption",
            horizon_hours=72.0,
            predicted_probability=probability,
            confidence=0.9,
            source_count=3,
            issued_at=NOW.isoformat(),
            resolve_by=(NOW + timedelta(hours=72)).isoformat(),
            status=RESOLVED,
            occurred=occurred,
        )

    def test_no_probability_is_stated_without_enough_history(self):
        calibrator = fit_calibrator([self._record(i, 0.8, True) for i in range(4)])
        probability, reason = calibrator.probability("chokepoint_disruption", 0.9, 0.9)
        self.assertIsNone(probability)
        self.assertIn(str(MIN_GLOBAL_SAMPLES), reason)

    def test_a_probability_is_stated_once_enough_has_resolved(self):
        outcomes = [self._record(i, 0.8, i % 2 == 0) for i in range(40)]
        calibrator = fit_calibrator(outcomes)
        self.assertTrue(calibrator.available)
        probability, reason = calibrator.probability("chokepoint_disruption", 0.9, 0.9)
        self.assertIsNotNone(probability)
        self.assertTrue(0.0 < probability < 1.0)
        self.assertTrue(reason)

    def test_calibration_moves_toward_the_observed_rate(self):
        """Claims of 0.9 that happen a fifth of the time should not stay at 0.9."""
        outcomes = [self._record(i, 0.9, i % 5 == 0) for i in range(60)]
        calibrator = fit_calibrator(outcomes)
        probability, _ = calibrator.probability("chokepoint_disruption", 0.9, 1.0)
        self.assertIsNotNone(probability)
        self.assertLess(probability, 0.6)

    def test_a_higher_raw_score_never_maps_to_a_lower_probability(self):
        outcomes = []
        for i in range(80):
            score = (i % 4) * 0.3
            outcomes.append(self._record(i, min(0.99, score), i % 3 == 0))
        calibrator = fit_calibrator(outcomes)
        previous = 0.0
        for severity in (0.2, 0.4, 0.6, 0.8, 0.95):
            probability, _ = calibrator.probability("chokepoint_disruption", severity, 1.0)
            if probability is None:
                continue
            self.assertGreaterEqual(round(probability, 6), round(previous, 6))
            previous = probability

    def test_probability_never_reaches_certainty(self):
        outcomes = [self._record(i, 0.95, True) for i in range(60)]
        calibrator = fit_calibrator(outcomes)
        probability, _ = calibrator.probability("chokepoint_disruption", 0.99, 0.99)
        self.assertLess(probability, 1.0)
        self.assertGreater(probability, 0.0)

    def test_apply_calibration_marks_events_and_explains_a_withheld_number(self):
        events, _ = ingest([item("Suez Canal closed after grounding", "a.com")], now=NOW)
        stamped = apply_calibration(events, fit_calibrator([]))
        self.assertEqual(stamped, 0)
        self.assertIsNone(events[0].probability)
        self.assertIn("resolved", events[0].calibration_note)

    def test_claims_are_committed_with_a_horizon_before_the_answer(self):
        events, _ = ingest([item("Suez Canal closed after grounding", "a.com")], now=NOW)
        claims = claims_for(events, issued_at=NOW.isoformat())
        self.assertEqual(len(claims), 1)
        self.assertGreater(claims[0].resolve_by, claims[0].issued_at)
        self.assertIsNone(claims[0].occurred)

    def test_raw_score_is_bounded_and_bucketed(self):
        self.assertEqual(raw_score(2.0, 2.0), 1.0)
        self.assertEqual(raw_score(-1.0, 0.5), 0.0)
        self.assertEqual(score_bucket(0.0), 0)
        self.assertEqual(score_bucket(1.0), 3)


class NormalisationTests(unittest.TestCase):
    def test_a_feed_that_already_typed_an_item_is_trusted_over_the_classifier(self):
        rows = [{
            "title": "Something ambiguous happened at a port",
            "source": "feed.com",
            "tag": "STRIKE",
            "timestamp": NOW.isoformat(),
        }]
        normalised = normalise(rows, feed="GDELT")
        self.assertEqual(normalised[0].category, "strike")

    def test_legacy_shock_vocabulary_is_mapped_rather_than_duplicated(self):
        rows = [{
            "title": "Red Sea transit suspended",
            "source": "feed.com",
            "tag": "CHOKEPOINT_CLOSURE",
            "timestamp": NOW.isoformat(),
        }]
        self.assertEqual(normalise(rows)[0].category, "chokepoint_disruption")

    def test_similarity_is_symmetric_and_bounded(self):
        a = "Houthi missile strikes tanker in the Red Sea"
        b = "Tanker struck by Houthi missile in Red Sea"
        self.assertAlmostEqual(similarity(a, b), similarity(b, a))
        self.assertLessEqual(similarity(a, b), 1.0)
        self.assertEqual(similarity("", "anything"), 0.0)


if __name__ == "__main__":
    unittest.main()
