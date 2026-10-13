"""Weather requests with different date ranges must not share a fresh response."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.ingestion.connectors import weather_live


class WeatherCacheTests(unittest.TestCase):
    def test_same_request_reuses_original_snapshot_without_fetching(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive.json"
            response = Mock()
            response.json.return_value = {"daily": {"time": ["2025-06-01"]}}
            client = Mock()
            client.get.return_value = response
            with patch.object(weather_live, "CACHE_DIR", Path(tmp)), patch.object(weather_live, "_requests", return_value=client):
                first, mode = weather_live._fetch("https://example.com/archive", {"start": "2025-06-01"}, path, 3600)
                stamp = path.stat().st_mtime_ns
                cached, cached_mode = weather_live._fetch("https://example.com/archive", {"start": "2025-06-01"}, path, 3600)
            self.assertEqual((mode, cached_mode), ("live", "cache"))
            self.assertEqual(first, cached)
            self.assertEqual(path.stat().st_mtime_ns, stamp)
            self.assertEqual(client.get.call_count, 1)

    def test_changed_range_cannot_return_an_unrelated_cached_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive.json"
            client = Mock()
            client.get.return_value.json.return_value = {"daily": {"time": ["2025-06-01"]}}
            with patch.object(weather_live, "CACHE_DIR", Path(tmp)), patch.object(weather_live, "_requests", return_value=client):
                weather_live._fetch("https://example.com/archive", {"start": "2025-06-01"}, path, 3600)
            with patch.object(weather_live, "_requests", return_value=None):
                payload, mode = weather_live._fetch("https://example.com/archive", {"start": "2025-07-01"}, path, 3600)
            self.assertIsNone(payload)
            self.assertEqual(mode, "unavailable")
