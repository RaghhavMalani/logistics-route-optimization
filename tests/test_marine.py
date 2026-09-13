"""The sea: a real forecast service, honestly aged, sampled along a passage.

The fixture is three points and six hours recorded from Open-Meteo's marine
endpoint on 2026-09-13; the service is never called from a test. What the
suite defends: the licence gate chooses the product before anything is
fetched, a cell never invents a value, freshness is the fetch's age and says
so, and a route profile grades itself by how much of the passage it could
actually see.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from src.portwatch_os.fabric.marine import (
    ENV_KEY,
    MarineForecastCell,
    MarineGrid,
    MarineService,
    OpenMeteoMarineAdapter,
    parse_response,
    set_service,
)
from src.portwatch_os.fabric.model import AVAILABLE, CONFIGURABLE, UNAVAILABLE
from src.portwatch_os.world.route_exposure import (
    HEAVY_M,
    RouteExposureProfile,
    sample_route,
    walk,
)

FIXTURE = Path(__file__).parent / "fixtures" / "open_meteo_marine_sample.json"
FETCHED = datetime(2026, 9, 13, 11, 20, tzinfo=timezone.utc)
POINTS = (("HORMUZ", 26.6, 56.3), ("BAB_EL_MANDEB", 12.6, 43.3), ("SUEZ_SOUTH", 29.5, 32.6))


def fixture_payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def scripted_service(payload=None, *, api_key=None, fail=False):
    def fetcher(url):
        if fail:
            raise OSError("no route to host")
        return payload if payload is not None else fixture_payload()

    return MarineService(points=POINTS, fetcher=fetcher, cache_path=None, api_key=api_key)


class ParseTests(unittest.TestCase):
    def test_the_fixture_parses_into_cells_with_converted_units(self):
        cells = parse_response(fixture_payload(), requested=POINTS, fetched_at=FETCHED,
                               product_id="open-meteo-free")
        self.assertEqual(len(cells), 18)                      # 3 points x 6 hours
        cell = cells[0]
        self.assertEqual(cell.label, "HORMUZ")
        self.assertEqual(cell.requested, (26.6, 56.3))
        self.assertEqual(cell.valid_at.tzinfo, timezone.utc)
        self.assertEqual(cell.fetched_at, FETCHED)
        # The service reports currents in km/h; the cell reports knots.
        raw_kmh = fixture_payload()[0]["hourly"]["ocean_current_velocity"][0]
        self.assertAlmostEqual(cell.current_speed_kn, raw_kmh * 0.539957, places=2)

    def test_a_null_variable_stays_none(self):
        payload = fixture_payload()
        payload[1]["hourly"]["wave_height"][2] = None
        cells = parse_response(payload, requested=POINTS, fetched_at=FETCHED, product_id="p")
        bab = [c for c in cells if c.label == "BAB_EL_MANDEB"]
        self.assertIsNone(bab[2].wave_height_m)
        self.assertIsNotNone(bab[1].wave_height_m)

    def test_location_id_binds_a_row_to_the_point_it_was_asked_for(self):
        payload = fixture_payload()
        payload.reverse()                                     # the service may reorder
        cells = parse_response(payload, requested=POINTS, fetched_at=FETCHED, product_id="p")
        suez = [c for c in cells if c.label == "SUEZ_SOUTH"][0]
        self.assertEqual(suez.requested, (29.5, 32.6))
        self.assertAlmostEqual(suez.lat, 29.5, delta=0.3)


class GridTests(unittest.TestCase):
    def setUp(self):
        self.grid = MarineGrid(parse_response(fixture_payload(), requested=POINTS,
                                              fetched_at=FETCHED, product_id="open-meteo-free"))

    def test_at_gives_one_cell_per_point_at_the_nearest_hour(self):
        lo, _ = self.grid.horizon
        cells = self.grid.at(lo + timedelta(hours=2, minutes=20))
        self.assertEqual(len(cells), 3)
        self.assertTrue(all(c.valid_at == lo + timedelta(hours=2) for c in cells))

    def test_sample_reports_how_far_off_it_is_in_space_and_time(self):
        lo, _ = self.grid.horizon
        sample = self.grid.sample(13.0, 44.0, lo + timedelta(hours=1, minutes=45))
        self.assertEqual(sample.cell.label, "BAB_EL_MANDEB")
        self.assertGreater(sample.distance_nm, 30)
        self.assertLess(sample.distance_nm, 60)
        self.assertEqual(sample.hours_off, -0.25)             # nearest hour is 15 min later

    def test_a_grid_survives_a_round_trip_through_json(self):
        rebuilt = MarineGrid.from_dict(json.loads(json.dumps(self.grid.to_dict())))
        self.assertEqual(len(rebuilt), len(self.grid))
        self.assertEqual(rebuilt.fetched_at, FETCHED)
        self.assertEqual(sorted(rebuilt.points), sorted(self.grid.points))


class ServiceTests(unittest.TestCase):
    def test_no_key_means_the_free_product_and_the_free_host(self):
        service = scripted_service()
        self.assertEqual(service.product_id, "open-meteo-free")
        self.assertIn("marine-api.open-meteo.com", service.url())
        self.assertNotIn("apikey", service.url())

    def test_a_key_means_the_customer_product_and_never_appears_in_status(self):
        service = scripted_service(api_key="secret-key")
        self.assertEqual(service.product_id, "open-meteo-customer")
        self.assertIn("customer-marine-api.open-meteo.com", service.url())
        self.assertNotIn("secret-key", json.dumps(service.status()))

    def test_a_failed_fetch_leaves_the_last_grid_and_records_why(self):
        good = scripted_service()
        grid = good.grid(now=FETCHED)
        self.assertEqual(len(grid), 18)
        good._fetcher = lambda url: (_ for _ in ()).throw(OSError("no route to host"))
        later = good.grid(now=FETCHED + timedelta(hours=3))     # past the TTL: tries, fails
        self.assertIs(later, grid)                              # the last good grid, aged
        self.assertIn("no route to host", good.last_error)
        self.assertEqual(good.status(now=FETCHED + timedelta(hours=3))["ageSeconds"], 3 * 3600.0)

    def test_nothing_is_fabricated_when_no_fetch_ever_succeeded(self):
        service = scripted_service(fail=True)
        self.assertIsNone(service.grid(now=FETCHED))
        self.assertEqual(service.failures, 1)

    def test_within_the_ttl_the_service_is_not_asked_again(self):
        service = scripted_service()
        service.grid(now=FETCHED)
        service.grid(now=FETCHED + timedelta(minutes=30))
        self.assertEqual(service.fetches, 1)


class AdapterTests(unittest.TestCase):
    def test_the_free_product_is_barred_from_a_commercial_deployment(self):
        adapter = OpenMeteoMarineAdapter(licence_mode="COMMERCIAL", service=scripted_service())
        availability = adapter.availability()
        self.assertEqual(availability.status, UNAVAILABLE)
        self.assertIn("commercial", availability.reason)
        self.assertEqual(adapter.fetch(), [])

    def test_a_key_makes_the_customer_product_available_commercially(self):
        service = scripted_service(api_key="k")
        service.grid(now=FETCHED)
        adapter = OpenMeteoMarineAdapter(licence_mode="COMMERCIAL", service=service)
        self.assertEqual(adapter.availability().status, AVAILABLE)
        self.assertEqual(adapter.product_id, "open-meteo-customer")

    def test_before_any_fetch_the_adapter_is_configurable_not_live(self):
        adapter = OpenMeteoMarineAdapter(licence_mode="RESEARCH", service=scripted_service())
        self.assertEqual(adapter.availability().status, CONFIGURABLE)
        self.assertEqual(adapter.fetch(), [])

    def test_freshness_is_the_fetch_age_and_the_provenance_says_so(self):
        service = scripted_service()
        service.grid(now=FETCHED)
        adapter = OpenMeteoMarineAdapter(licence_mode="RESEARCH", service=service)
        observation = adapter.fetch(now=FETCHED + timedelta(minutes=10))[0]
        self.assertEqual(observation.source_timestamp, FETCHED)
        # Ten minutes is a cached forecast, not a live reading; the word matters.
        self.assertEqual(observation.freshness(now=FETCHED + timedelta(seconds=30)), "LIVE")
        self.assertEqual(observation.freshness(now=FETCHED + timedelta(minutes=10)), "CACHED")
        self.assertEqual(observation.freshness(now=FETCHED + timedelta(hours=4)), "STALE")
        self.assertFalse(observation.provenance["model_run_time_known"])
        self.assertEqual(observation.value["cells"], 18)


class RouteSamplerTests(unittest.TestCase):
    def setUp(self):
        self.grid = MarineGrid(parse_response(fixture_payload(), requested=POINTS,
                                              fetched_at=FETCHED, product_id="open-meteo-free"))
        self.lo, self.hi = self.grid.horizon

    def test_walk_spaces_samples_along_the_route(self):
        points = walk([(12.6, 43.3), (12.6, 46.3)], step_nm=60.0)
        self.assertGreaterEqual(len(points), 3)
        self.assertEqual(points[0][2], 0.0)
        self.assertAlmostEqual(points[-1][2], 175.5, delta=2)      # ~3 degrees of longitude at 12.6N
        self.assertAlmostEqual(points[0][3], 90.0, delta=1.0)       # heading east

    def test_a_short_passage_inside_the_horizon_is_fully_covered(self):
        # Along the Bab-el-Mandeb approach for two hours, inside the fixture's window.
        profile = sample_route([(12.6, 43.3), (12.6, 43.9)], grid=self.grid,
                               departs_at=self.lo + timedelta(hours=1), speed_kn=14.0)
        self.assertEqual(profile.coverage, 1.0)
        self.assertIsNotNone(profile.max_wave)
        self.assertIsNotNone(profile.added_hours)
        self.assertIn(profile.samples[0].aspect, ("HEAD", "BEAM", "FOLLOWING"))
        self.assertLessEqual(profile.confidence, 0.5)

    def test_a_passage_beyond_the_horizon_is_uncovered_and_says_so(self):
        profile = sample_route([(12.6, 43.3), (12.6, 46.3)], grid=self.grid,
                               departs_at=self.hi + timedelta(days=2), speed_kn=14.0)
        self.assertEqual(profile.coverage, 0.0)
        self.assertIsNone(profile.max_wave)
        self.assertIsNone(profile.added_hours)
        self.assertIn("LOW_COVERAGE", profile.flags)
        self.assertIn("BEYOND_FORECAST_HORIZON", profile.flags)

    def test_no_grid_means_no_coverage_not_a_guess(self):
        profile = sample_route([(12.6, 43.3), (12.6, 46.3)], grid=None,
                               departs_at=self.lo, speed_kn=14.0)
        self.assertEqual(profile.coverage, 0.0)
        self.assertEqual(profile.confidence, 0.0)

    def test_head_seas_cost_more_than_following_seas(self):
        heavy = MarineGrid([
            MarineForecastCell(lat=12.6, lon=44.0, valid_at=self.lo + timedelta(hours=h), fetched_at=FETCHED,
                               wave_height_m=4.5, wave_direction_deg=90.0,        # waves from the east
                               current_speed_kn=0.0, current_direction_deg=0.0,
                               requested=(12.6, 44.0), label="X")
            for h in range(0, 48)
        ])
        east = sample_route([(12.6, 43.3), (12.6, 45.3)], grid=heavy, departs_at=self.lo, speed_kn=14.0)
        west = sample_route([(12.6, 45.3), (12.6, 43.3)], grid=heavy, departs_at=self.lo, speed_kn=14.0)
        self.assertEqual(east.samples[0].aspect, "HEAD")
        self.assertEqual(west.samples[0].aspect, "FOLLOWING")
        self.assertGreater(east.added_hours, west.added_hours)
        self.assertIn("HEAVY_SEAS", east.flags)
        self.assertIn("SUSTAINED_HEAD_SEAS", east.flags)

    def test_an_adverse_current_is_flagged(self):
        against = MarineGrid([
            MarineForecastCell(lat=12.6, lon=44.0, valid_at=self.lo + timedelta(hours=h), fetched_at=FETCHED,
                               wave_height_m=0.5, wave_direction_deg=180.0,
                               current_speed_kn=1.5, current_direction_deg=270.0,   # flowing west
                               requested=(12.6, 44.0), label="X")
            for h in range(0, 48)
        ])
        profile = sample_route([(12.6, 43.3), (12.6, 45.3)], grid=against, departs_at=self.lo, speed_kn=14.0)
        self.assertLess(profile.mean_current_along_kn, -1.0)
        self.assertIn("ADVERSE_CURRENT", profile.flags)


class MarineApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def _install(self, *, api_key=None, fetched=True):
        service = scripted_service(api_key=api_key)
        if fetched:
            service.grid(now=FETCHED)
        set_service(service)
        self.addCleanup(set_service, None)
        return service

    def test_marine_cells_carry_product_age_and_attribution(self):
        self._install()
        lo = FETCHED.replace(hour=0, minute=0)
        body = self.client.get(f"/api/world/marine?mode=RESEARCH&at={lo.isoformat().replace('+', '%2B')}").json()
        self.assertEqual(body["productId"], "open-meteo-free")
        self.assertEqual(body["availability"]["status"], AVAILABLE)
        self.assertEqual(len(body["cells"]), 3)
        self.assertIn("Open-Meteo", body["attribution"])
        self.assertIsNotNone(body["ageSeconds"])
        cell = body["cells"][0]
        self.assertIn("waveHeightM", cell)
        self.assertIn("currentSpeedKn", cell)
        self.assertIn("validAt", cell)

    def test_marine_is_withheld_from_a_commercial_view_without_a_key(self):
        self._install()
        body = self.client.get("/api/world/marine?mode=COMMERCIAL").json()
        self.assertEqual(body["availability"]["status"], UNAVAILABLE)
        self.assertEqual(body["cells"], [])
        self.assertIsNone(body["attribution"])

    def test_route_exposure_returns_a_graded_profile(self):
        self._install()
        lo = FETCHED.replace(hour=0, minute=0)
        body = self.client.post("/api/world/route/exposure", json={
            "mode": "RESEARCH", "speedKn": 14,
            "departsAt": (lo + timedelta(hours=1)).isoformat(),
            "waypoints": [[12.6, 43.3], [12.6, 43.9]],
        }).json()
        self.assertEqual(body["coverage"], 1.0)
        self.assertLessEqual(body["confidence"], 0.5)
        self.assertIn("method", body)
        self.assertTrue(body["samples"])

    def test_route_exposure_validates_its_input(self):
        self._install()
        self.assertEqual(self.client.post("/api/world/route/exposure", json={"waypoints": [[1, 2]]}).status_code, 400)
        self.assertEqual(self.client.post("/api/world/route/exposure",
                                          json={"waypoints": [[1, 2], [3, 4]], "speedKn": 99}).status_code, 400)
        self.assertEqual(self.client.post("/api/world/route/exposure",
                                          json={"waypoints": [[1, 2], [95, 4]]}).status_code, 400)

    def test_signal_health_now_reports_the_marine_capability(self):
        self._install()
        body = self.client.get("/api/fabric/health?mode=RESEARCH").json()
        marine = next(s for s in body["signals"] if s["capability"] == "marine")
        self.assertEqual(marine["productId"], "open-meteo-free")
        self.assertEqual(marine["freshness"] in ("LIVE", "CACHED", "STALE"), True)
        self.assertEqual(marine["commercialUse"], "PROHIBITED")
        self.assertNotIn("marine", body["unwired"])


if __name__ == "__main__":
    unittest.main()
