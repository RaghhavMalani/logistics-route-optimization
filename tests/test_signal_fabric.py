"""The ingestion fabric: observations, quality, adapters and traffic mode.

The failure this suite exists to prevent is a single sentence: the product says
LIVE when it is not. Every assertion below is some version of that.

It is an easy failure to write. An adapter that falls back to demo data when a
key is missing keeps the screen working. A freshness computed from the moment we
read a file is always small. A timestamp stood in for by `now` looks exactly
like a fresh one. Each of those makes the product *appear* healthier, which is
why each needs a test rather than a convention.
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone

from src.portwatch_os.fabric.adapters import (
    AIS_STALE,
    AIS_UNAVAILABLE,
    AisStreamAdapter,
    Availability,
    BaseAdapter,
    GdeltAdapter,
    LIVE_AIS,
    OpenMeteoAdapter,
    SIMULATED_TRAFFIC,
    ais_mode,
    build_adapters,
)
from src.portwatch_os.fabric.ais import AUTH_FAILED, AisStreamClient, TrackStore
from src.portwatch_os.fabric.model import AVAILABLE, CONFIGURABLE, UNAVAILABLE
from src.portwatch_os.fabric.observation import (
    DEGRADED,
    OK,
    Observation,
    ObservationError,
    REJECTED,
    assess,
    observe,
)

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def a_reading(**overrides):
    base = dict(
        provider_id="test", capability="weather", value={"x": 1},
        source_timestamp=NOW - timedelta(minutes=1), now=NOW,
    )
    base.update(overrides)
    return observe(**base)


# --------------------------------------------------------------------------
# observations
# --------------------------------------------------------------------------


class ObservationTimeTests(unittest.TestCase):
    """Source time is not ingest time, and the difference is the whole point."""

    def test_age_is_measured_from_when_the_provider_observed_it(self):
        reading = a_reading(source_timestamp=NOW - timedelta(hours=6))
        # Fetched just now, six hours old. The second number is the true one.
        self.assertAlmostEqual(reading.age_seconds(now=NOW), 6 * 3600, delta=1)
        self.assertAlmostEqual(reading.latency_seconds(), 6 * 3600, delta=1)

    def test_a_recent_reading_is_live(self):
        self.assertEqual(a_reading().freshness(now=NOW), "LIVE")

    def test_an_old_reading_is_stale_rather_than_live(self):
        reading = a_reading(source_timestamp=NOW - timedelta(hours=13))
        self.assertEqual(reading.freshness(now=NOW), "STALE")

    def test_a_reading_past_its_stated_validity_is_expired(self):
        reading = a_reading(
            source_timestamp=NOW - timedelta(hours=3), valid_for_hours=1.0,
        )
        self.assertEqual(reading.freshness(now=NOW), "EXPIRED")

    def test_a_reading_with_no_known_time_is_unknown_not_live(self):
        """The bug this caught in the GDELT adapter, pinned.

        Standing `now` in for a missing timestamp produces age zero, which reads
        as LIVE. An artefact of unknown age reporting itself as current is the
        most damaging thing in this module.
        """
        reading = a_reading(source_time_known=False)
        self.assertEqual(reading.freshness(now=NOW), "UNKNOWN")
        self.assertIsNone(reading.to_dict(now=NOW)["ageSeconds"])
        self.assertEqual(reading.quality.level, DEGRADED)
        self.assertTrue(
            any("no timestamp" in r for r in reading.quality.reasons),
            reading.quality.reasons,
        )


class QualityTests(unittest.TestCase):
    def test_a_reading_from_the_future_is_rejected(self):
        """A clock problem, not a forecast."""
        reading = a_reading(source_timestamp=NOW + timedelta(hours=2))
        self.assertEqual(reading.quality.level, REJECTED)
        self.assertFalse(reading.quality.usable)

    def test_a_reading_with_no_payload_is_rejected(self):
        self.assertEqual(a_reading(value=None).quality.level, REJECTED)

    def test_an_empty_payload_is_degraded_rather_than_dropped(self):
        """A source that started returning nothing is something to notice."""
        reading = a_reading(value=[])
        self.assertEqual(reading.quality.level, DEGRADED)
        self.assertTrue(reading.quality.usable)

    def test_an_old_reading_is_degraded_and_says_how_old(self):
        reading = a_reading(source_timestamp=NOW - timedelta(hours=9))
        self.assertEqual(reading.quality.level, DEGRADED)
        self.assertTrue(any("old" in r for r in reading.quality.reasons))

    def test_an_assumed_validity_is_declared(self):
        reading = a_reading(valid_for_hours=6.0)
        self.assertTrue(reading.validity_assumed)
        self.assertTrue(
            any("assumption" in r for r in reading.quality.reasons),
            reading.quality.reasons,
        )

    def test_a_clean_recent_reading_is_ok(self):
        self.assertEqual(a_reading().quality.level, OK)

    def test_an_unknown_mode_cannot_be_observed_under(self):
        with self.assertRaises(ObservationError):
            a_reading(licence_mode="PIRATE")


# --------------------------------------------------------------------------
# adapters
# --------------------------------------------------------------------------


class AdapterContractTests(unittest.TestCase):
    """An adapter that cannot run returns nothing. It never substitutes."""

    class _Unavailable(BaseAdapter):
        provider_id = "nope"
        capability = "weather"

        def availability(self):
            return Availability(CONFIGURABLE, reason="no key", needs=("KEY",))

        def _read(self, *, now):  # pragma: no cover - must never be reached
            raise AssertionError("_read must not run when unavailable")

    def test_an_unavailable_adapter_yields_nothing_rather_than_substituting(self):
        self.assertEqual(self._Unavailable().fetch(now=NOW), [])

    def test_availability_is_a_separate_question_from_fetching(self):
        adapter = self._Unavailable()
        self.assertFalse(adapter.availability().ready)
        self.assertEqual(adapter.availability().needs, ("KEY",))

    def test_every_shipped_adapter_reports_an_availability(self):
        for adapter in build_adapters(licence_mode="RESEARCH"):
            availability = adapter.availability()
            self.assertIn(
                availability.status, (AVAILABLE, CONFIGURABLE, UNAVAILABLE),
            )
            if not availability.ready:
                # An adapter that is not ready has to say what it is waiting for.
                self.assertTrue(availability.reason, adapter.provider_id)


def _envelope(mmsi="419001234", lat=12.6, lon=43.3, at=None):
    moment = at or NOW
    return {
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": mmsi, "latitude": lat, "longitude": lon,
                     "time_utc": moment.strftime("%Y-%m-%d %H:%M:%S.%f") + "000 +0000 UTC"},
        "Message": {"PositionReport": {"UserID": int(mmsi), "Sog": 11.0, "Cog": 90.0,
                                       "TrueHeading": 91, "NavigationalStatus": 0}},
    }


class AisModeTests(unittest.TestCase):
    """The claim most likely to be misread, and the one a buyer asks first.

    The client is injected and never started, so these tests describe the
    state machine and not the network. What the network does with a bad key
    is covered where the socket is exercised.
    """

    def _client(self, key):
        return AisStreamClient(TrackStore(), api_key=key)

    def test_without_a_key_research_shows_simulated_traffic(self):
        mode = ais_mode(licence_mode="RESEARCH", client=self._client(None), now=NOW)
        self.assertEqual(mode["mode"], SIMULATED_TRAFFIC)
        self.assertEqual(mode["providerId"], "ais-replay")
        self.assertIn("not observed AIS", mode["statement"])
        self.assertEqual(mode["availability"]["status"], CONFIGURABLE)

    def test_a_commercial_deployment_has_no_eligible_traffic_source(self):
        """AISStream's licence bars it however well configured it is, and
        however many messages are arriving."""
        client = self._client("a-key")
        client.feed(_envelope(), now=NOW)
        mode = ais_mode(licence_mode="COMMERCIAL", client=client, now=NOW)
        self.assertEqual(mode["mode"], AIS_UNAVAILABLE)
        self.assertIn("commercial", mode["availability"]["reason"])
        self.assertIsNone(mode["providerId"])

    def test_a_key_alone_does_not_make_traffic_live(self):
        """The test that stops a future change flipping the label to LIVE_AIS
        before anything has actually been received."""
        mode = ais_mode(licence_mode="RESEARCH", client=self._client("a-key"), now=NOW)
        self.assertNotEqual(mode["mode"], LIVE_AIS)
        self.assertNotEqual(mode["mode"], SIMULATED_TRAFFIC)   # and not the replay
        self.assertEqual(mode["mode"], AIS_UNAVAILABLE)
        self.assertIn("no valid observation has arrived", mode["availability"]["reason"])

    def test_one_valid_observation_makes_traffic_live(self):
        client = self._client("a-key")
        client.feed(_envelope(), now=NOW)
        mode = ais_mode(licence_mode="RESEARCH", client=client, now=NOW)
        self.assertEqual(mode["mode"], LIVE_AIS)
        self.assertEqual(mode["providerId"], "aisstream")
        self.assertEqual(mode["availability"]["status"], AVAILABLE)
        self.assertEqual(mode["vessels"]["live"], 1)

    def test_live_goes_stale_then_unavailable_never_simulated(self):
        """The rule with a name: never silently LIVE_AIS -> SIMULATED_TRAFFIC."""
        client = self._client("a-key")
        client.feed(_envelope(), now=NOW)
        later = ais_mode(licence_mode="RESEARCH", client=client, now=NOW + timedelta(minutes=12))
        self.assertEqual(later["mode"], AIS_STALE)
        self.assertIn("last known", later["statement"])
        lapsed = ais_mode(licence_mode="RESEARCH", client=client, now=NOW + timedelta(hours=2))
        self.assertEqual(lapsed["mode"], AIS_UNAVAILABLE)
        self.assertIn("not been replaced by the replay", lapsed["statement"])

    def test_a_refused_credential_is_unavailable_not_simulated(self):
        client = self._client("bad")
        client.status.health = AUTH_FAILED
        client.status.last_error = "refused"
        mode = ais_mode(licence_mode="RESEARCH", client=client, now=NOW)
        self.assertEqual(mode["mode"], AIS_UNAVAILABLE)
        self.assertIn("refused", mode["availability"]["reason"])

    def test_the_replay_is_never_served_through_the_ais_adapter(self):
        adapter = AisStreamAdapter(licence_mode="RESEARCH", client=self._client("a-key"))
        self.assertEqual(adapter.fetch(now=NOW), [])

    def test_the_adapter_serves_observed_tracks_with_the_transponders_time(self):
        client = self._client("a-key")
        earlier = NOW - timedelta(minutes=3)
        client.feed(_envelope(mmsi="419000001", at=earlier), now=NOW)
        client.feed(_envelope(mmsi="419000002", at=NOW), now=NOW)
        observations = AisStreamAdapter(licence_mode="RESEARCH", client=client).fetch(
            now=NOW + timedelta(seconds=30)
        )
        self.assertEqual([o.value["mmsi"] for o in observations], ["419000002", "419000001"])
        self.assertEqual(observations[1].source_timestamp, earlier)
        self.assertEqual(observations[1].age_seconds(now=NOW + timedelta(seconds=30)), 210.0)
        self.assertEqual(observations[0].value["source"], "OBSERVED_AIS")
        self.assertTrue(observations[0].source_time_known)

    def test_the_process_client_is_not_started_by_reading_status(self):
        """Asking what mode we are in must not dial the server."""
        from src.portwatch_os.fabric.ais import client as client_module

        client_module.reset_client()
        try:
            os.environ[AisStreamAdapter.ENV_KEY] = "a-key"
            client = client_module.get_client()
            self.assertTrue(client.configured)
            self.assertIsNone(client._thread)
        finally:
            os.environ.pop(AisStreamAdapter.ENV_KEY, None)
            client_module.reset_client()


class ArtefactAdapterTests(unittest.TestCase):
    """The artefact-backed adapters report the artefact's age, not the read's."""

    def test_the_free_weather_artefact_is_barred_from_a_commercial_deployment(self):
        """Found by the demo acceptance run: the weather adapter reported the
        free-tier artefact AVAILABLE in COMMERCIAL while the marine adapter,
        reading the same product, refused it. Same product, same verdict."""
        os.environ.pop("OPEN_METEO_API_KEY", None)
        availability = OpenMeteoAdapter(licence_mode="COMMERCIAL").availability()
        self.assertEqual(availability.status, UNAVAILABLE)
        self.assertIn("commercial", availability.reason)
        self.assertEqual(OpenMeteoAdapter(licence_mode="COMMERCIAL").fetch(now=NOW), [])

    def test_the_weather_adapter_reads_the_pipeline_artefact(self):
        adapter = OpenMeteoAdapter(licence_mode="RESEARCH")
        if not adapter.availability().ready:
            self.skipTest("no forecast artefact in this checkout")
        readings = adapter.fetch()
        self.assertTrue(readings)
        # Whatever the age is, it is measured from the forecast origin.
        self.assertGreater(readings[0].latency_seconds(), 0)

    def test_the_event_adapter_declares_where_its_timestamp_came_from(self):
        """The bundle carries no time, so the basis has to be stated."""
        adapter = GdeltAdapter(licence_mode="RESEARCH")
        if not adapter.availability().ready:
            self.skipTest("no news bundle in this checkout")
        readings = adapter.fetch()
        self.assertTrue(readings)
        basis = readings[0].provenance.get("timestamp_basis")
        self.assertIn(basis, ("provider fetchedAt", "artefact write time", "unknown"))
        if basis == "unknown":
            self.assertEqual(readings[0].freshness(), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
