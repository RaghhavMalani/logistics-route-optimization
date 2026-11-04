"""Source-quality presentation never fabricates originals or weather values."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from src.ingestion import source_receipts, weather_quality
from src.ingestion.connectors import weather_live
from src.utils import port_registry


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTWATCH_CURRENT_ENVIRONMENT_DIR", str(tmp_path / "current"))
    for name, filename in (("ARCHIVE_CACHE", "archive.json"), ("FORECAST_CACHE", "surface.json"), ("MARINE_CACHE", "marine.json")):
        monkeypatch.setattr(weather_live, name, tmp_path / filename)
    monkeypatch.setattr(weather_live, "CACHE_DIR", tmp_path)
    return tmp_path


def response(body):
    raw = (" \n" + json.dumps(body) + "\n").encode()
    return SimpleNamespace(content=raw, json=lambda: body, raise_for_status=lambda: None)


def request_params():
    return {"latitude": ",".join(str(p.lat) for p in port_registry.all_ports()),
        "longitude": ",".join(str(p.lon) for p in port_registry.all_ports()),
        "daily": "wind_speed_10m_max,wind_gusts_10m_max,precipitation_sum", "start_date": "2025-01-01",
        "end_date": "2025-01-02", "models": "era5", "wind_speed_unit": "kmh", "timezone": "UTC"}


def archive_block(**extra):
    return {"latitude": 23.0, "longitude": 70.25,
        "daily_units": {"wind_speed_10m_max": "km/h", "wind_gusts_10m_max": "km/h", "precipitation_sum": "mm"},
        "daily": {"time": ["2025-01-01", "2025-01-02"], "wind_speed_10m_max": [10.0, None],
            "wind_gusts_10m_max": [12.0, 15.0], "precipitation_sum": [0.0, None]}, **extra}


def fetch_once(monkeypatch, body, cache=None, ttl=3600):
    client = Mock()
    client.get.return_value = response(body)
    monkeypatch.setattr(weather_live, "_requests", lambda: client)
    result = weather_live._fetch(weather_live.ARCHIVE_URL, request_params(), cache or weather_live.ARCHIVE_CACHE, ttl)
    return result, client


def test_network_original_and_cache_check_have_separate_clocks(isolated, monkeypatch):
    monkeypatch.setattr(source_receipts, "now_iso", lambda: "2026-10-22T01:00:00+00:00")
    (first, mode), client = fetch_once(monkeypatch, archive_block())
    receipt, sidecar, reason = source_receipts.retained(weather_live.ARCHIVE_CACHE)
    assert mode == "live" and reason is None
    assert receipt["firstAvailableAt"] == "2026-10-22T01:00:00+00:00"
    assert receipt["responseSha256"] == hashlib.sha256(client.get.return_value.content).hexdigest()
    stamp = weather_live.ARCHIVE_CACHE.stat().st_mtime_ns
    before = (source_receipts.archive_root() / "archive" / (receipt["sourceReceiptId"] + ".json")).read_bytes()
    monkeypatch.setattr(source_receipts, "now_iso", lambda: "2026-10-22T02:00:00+00:00")
    cached, cached_mode = weather_live._fetch(weather_live.ARCHIVE_URL, request_params(), weather_live.ARCHIVE_CACHE, 3600)
    receipt2, sidecar2, reason2 = source_receipts.retained(weather_live.ARCHIVE_CACHE)
    assert first == cached and cached_mode == "cache" and client.get.call_count == 1
    assert weather_live.ARCHIVE_CACHE.stat().st_mtime_ns == stamp
    assert receipt2 == receipt and sidecar2["lastFetchedAt"] == sidecar["lastFetchedAt"]
    assert sidecar2["lastCheckedAt"] == "2026-10-22T02:00:00+00:00"
    assert (source_receipts.archive_root() / "archive" / (receipt["sourceReceiptId"] + ".json")).read_bytes() == before


def test_network_revision_keeps_old_original_and_first_receipt(isolated, monkeypatch):
    monkeypatch.setattr(source_receipts, "now_iso", lambda: "2026-10-22T01:00:00+00:00")
    fetch_once(monkeypatch, archive_block())
    first, _, _ = source_receipts.retained(weather_live.ARCHIVE_CACHE)
    modified = archive_block()
    modified["daily"]["wind_gusts_10m_max"][0] = 20.0
    monkeypatch.setattr(source_receipts, "now_iso", lambda: "2026-10-22T02:00:00+00:00")
    fetch_once(monkeypatch, modified, ttl=-1)
    second, _, _ = source_receipts.retained(weather_live.ARCHIVE_CACHE)
    assert second["previousReceiptId"] == first["sourceReceiptId"]
    assert second["lineageRelation"] == "RESPONSE_REVISION"
    assert second["firstAvailableAt"] == "2026-10-22T02:00:00+00:00"
    assert (source_receipts.archive_root() / "archive" / (first["responseSha256"] + ".response")).is_file()
    # A further network retry returning that exact version preserves first-seen.
    monkeypatch.setattr(source_receipts, "now_iso", lambda: "2026-10-22T03:00:00+00:00")
    fetch_once(monkeypatch, modified, ttl=-1)
    third, clocks, _ = source_receipts.retained(weather_live.ARCHIVE_CACHE)
    assert third == second
    assert clocks["lastFetchedAt"] == "2026-10-22T03:00:00+00:00"


def test_legacy_cache_mtime_never_manufactures_original(isolated, monkeypatch):
    params = request_params()
    cache = weather_live.ARCHIVE_CACHE
    cache.write_text(json.dumps([archive_block()]))
    signature = hashlib.sha256(json.dumps({"url": weather_live.ARCHIVE_URL, "params": params}, sort_keys=True).encode()).hexdigest()
    cache.with_suffix(".request").write_text(signature)
    monkeypatch.setattr(weather_live, "_requests", lambda: None)
    _, mode = weather_live._fetch(weather_live.ARCHIVE_URL, params, cache, 3600)
    quality = weather_quality.quality_for_weather_source("Weather history (Open-Meteo ERA5 archive)", {"status": "LIVE", "fetched_at": "2026-10-22T04:00:00Z"})
    assert mode == "cache"
    assert quality["provenance"]["originalHash"] is None
    assert quality["receipt"]["lastFetchedAt"] is None
    assert quality["sourceReceipts"] == []
    assert any("Legacy parsed cache" in reason for reason in quality["unknownReasons"])
    assert not (source_receipts.archive_root() / "archive").exists()


def test_archive_actual_partial_coverage_daily_precision_and_conversion(isolated, monkeypatch):
    fetch_once(monkeypatch, [archive_block(), {"daily": {"time": ["2025-01-01"], "wind_speed_10m_max": [None]}}])
    quality = weather_quality.quality_for_weather_source("Weather history (Open-Meteo ERA5 archive)", {"status": "LIVE", "confidence": 1.0})
    assert quality["temporalRole"] == "HISTORICAL"
    assert quality["semantics"]["dataKind"] == "REANALYSIS"
    assert quality["semantics"]["stationObservation"] is False
    assert quality["coverage"]["portCodes"] == [port_registry.all_ports()[0].locode]
    assert quality["coverage"]["variables"] == ["rainfall", "wind_gust", "wind_speed"]
    assert quality["coverage"]["observedFrom"] == "2025-01-01"
    assert quality["coverage"]["observedThrough"] == "2025-01-02"
    assert quality["coverage"]["targetFrom"] is None
    assert quality["coverage"]["forecastOriginAt"] is None
    assert quality["coverage"]["datePrecision"] == "DATE_ONLY"
    assert len(quality["requestedCoverage"]["portCodes"]) == 13
    assert quality["quality"]["confidence"] is None
    assert quality["quality"]["completeness"] is None
    speed = next(unit for unit in quality["units"] if unit["variable"] == "wind_speed")
    assert speed["sourceUnit"] == "km/h" and speed["outputUnit"] == "kn"
    assert speed["derivation"] == "source × 0.539957"
    # Neither the projection nor archive receipt changes the legacy calculation.
    monkeypatch.setattr(weather_live, "_fetch", lambda *args, **kwargs: ([archive_block()], "cache"))
    monkeypatch.setattr(weather_live.provenance, "record", Mock())
    frame = weather_live.fetch_archive_weather(pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-02"))
    assert frame.loc[0, "wind_speed"] == 10.0 * weather_live.KMH_TO_KNOTS
    assert frame["visibility"].isna().all() and frame["wave_height"].isna().all()


@pytest.mark.parametrize("damage", ["hash", "cache", "clock", "json"])
def test_bad_original_or_metadata_is_unknown_without_losing_daily_semantics(isolated, monkeypatch, damage):
    fetch_once(monkeypatch, archive_block())
    receipt, _, _ = source_receipts.retained(weather_live.ARCHIVE_CACHE)
    receipt_file = source_receipts.archive_root() / "archive" / (receipt["sourceReceiptId"] + ".json")
    if damage == "hash":
        (source_receipts.archive_root() / "archive" / (receipt["responseSha256"] + ".response")).write_bytes(b"tampered")
    elif damage == "cache":
        weather_live.ARCHIVE_CACHE.write_text(json.dumps([archive_block(), archive_block()]))
    elif damage == "json":
        receipt_file.write_text("{bad")
    else:
        receipt["firstAvailableAt"] = "today"
        receipt_file.write_text(json.dumps(receipt))
    quality = weather_quality.quality_for_weather_source("Weather history (Open-Meteo ERA5 archive)", {"status": "STALE"})
    assert quality["temporalRole"] == "HISTORICAL" and quality["coverage"]["variables"]
    assert quality["receipt"]["status"] == "UNAVAILABLE"
    assert quality["semantics"]["legacyDeclaredStatus"] == "STALE"
    assert quality["provenance"]["originalHash"] is None
    assert quality["sourceReceipts"] == []


def test_failure_keeps_original_receipt_and_cache_first_seen(isolated, monkeypatch):
    fetch_once(monkeypatch, archive_block())
    receipt, _, _ = source_receipts.retained(weather_live.ARCHIVE_CACHE)
    client = Mock()
    client.get.side_effect = RuntimeError("provider failed")
    monkeypatch.setattr(weather_live, "_requests", lambda: client)
    _, mode = weather_live._fetch(weather_live.ARCHIVE_URL, request_params(), weather_live.ARCHIVE_CACHE, -1)
    assert mode == "cache"
    assert source_receipts.retained(weather_live.ARCHIVE_CACHE)[0] == receipt


def test_concurrent_same_cache_has_one_network_receipt(isolated, monkeypatch):
    client = Mock()
    client.get.return_value = response(archive_block())
    monkeypatch.setattr(weather_live, "_requests", lambda: client)
    def fetch():
        return weather_live._fetch(weather_live.ARCHIVE_URL, request_params(), weather_live.ARCHIVE_CACHE, 3600)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: fetch(), range(8)))
    assert sum(mode == "live" for _, mode in results) == 1
    assert client.get.call_count == 1
    assert source_receipts.retained(weather_live.ARCHIVE_CACHE)[2] is None


def test_unretained_surface_does_not_invent_forecast_origin_or_date_partition(isolated):
    weather_live.FORECAST_CACHE.write_text(json.dumps([archive_block()]))
    quality = weather_quality.quality_for_weather_source("Marine weather (Open-Meteo)", {"status": "UNAVAILABLE"})
    assert quality["temporalRole"] == "MIXED"
    assert quality["coverage"]["forecastOriginAt"] is None
    assert quality["provenance"]["originalHash"] is None
    assert quality["components"][0]["coverage"]["targetFrom"] is None
    assert quality["components"][1]["coverage"]["portCodes"] == []
    assert "wave_height" not in quality["coverage"]["variables"]


def test_current_hourly_projection_validates_original_without_collection(isolated):
    folder = source_receipts.archive_root()
    (folder / "archive").mkdir(parents=True)
    port = port_registry.all_ports()[0]
    raw = json.dumps({"hourly": {"time": ["2026-10-22T00:00", "2026-10-22T01:00"], "wave_height": [1.2, None]},
        "hourly_units": {"wave_height": "m"}}).encode()
    digest = hashlib.sha256(raw).hexdigest()
    (folder / "archive" / (digest + ".response")).write_bytes(raw)
    snapshot = {"kind": "marine", "portCode": port.locode,
        "source": "https://marine-api.open-meteo.com/v1/marine", "availableAt": "2026-10-21T01:00:00+00:00",
        "responseSha256": digest, "request": {"latitude": port.lat, "longitude": port.lon},
        "units": {"wave_height": "m"}, "rows": [{"validAt": "2026-10-22T00:00:00+00:00", "wave_height": 1.2},
            {"validAt": "2026-10-22T01:00:00+00:00", "wave_height": None}]}
    snapshot["snapshotId"] = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    (folder / f"marine-{port.locode}.json").write_text(json.dumps(snapshot))
    before = sorted(path.name for path in folder.rglob("*"))
    products = weather_quality.current_weather_products()
    assert len(products) == 1
    quality = products[0]["sourceQuality"]
    assert quality["temporalRole"] == "FORECAST" and quality["operationalUse"] == "CONTEXT_ONLY"
    assert quality["receipt"]["status"] == "STALE"
    assert quality["coverage"]["variables"] == ["wave_height"]
    assert quality["quality"]["rowCount"] == 1
    assert quality["sourceReceipts"][0]["originalHash"] == digest
    assert quality["sourceReceipts"][0]["checkedAt"] is None
    assert quality["provenance"]["originalHash"] is None  # aggregate has per-port originals
    assert sorted(path.name for path in folder.rglob("*")) == before


def test_retained_request_subset_does_not_claim_all_configured_ports(isolated, monkeypatch):
    port = port_registry.all_ports()[2]
    params = request_params()
    params.update(latitude=str(port.lat), longitude=str(port.lon))
    client = Mock()
    client.get.return_value = response(archive_block())
    monkeypatch.setattr(weather_live, "_requests", lambda: client)
    weather_live._fetch(weather_live.ARCHIVE_URL, params, weather_live.ARCHIVE_CACHE, 3600)
    quality = weather_quality.quality_for_weather_source("Weather history (Open-Meteo ERA5 archive)", {"status": "LIVE"})
    assert quality["requestedCoverage"]["portCodes"] == [port.locode]
    # Existing numerical parser zips with all configured ports; metadata must
    # expose that mismatch instead of claiming its first port was supplied.
    assert quality["coverage"]["portCodes"] is None
    assert any("physical-port mapping" in issue for issue in quality["quality"]["issues"])


def test_optional_check_metadata_failure_does_not_trigger_fetch(isolated, monkeypatch):
    fetch_once(monkeypatch, archive_block())
    client = Mock()
    monkeypatch.setattr(weather_live, "_requests", lambda: client)
    monkeypatch.setattr(source_receipts, "checked", Mock(side_effect=OSError("readonly metadata")))
    payload, mode = weather_live._fetch(weather_live.ARCHIVE_URL, request_params(), weather_live.ARCHIVE_CACHE, 3600)
    assert payload and mode == "cache" and client.get.call_count == 0


def test_restart_reads_receipt_files_without_process_memory(isolated, monkeypatch):
    fetch_once(monkeypatch, archive_block())
    quality = weather_quality.quality_for_weather_source("Weather history (Open-Meteo ERA5 archive)", {"status": "CACHED_LIVE"})
    import os
    import subprocess
    import sys
    # A separate interpreter has no connector/receipt globals from this test.
    code = """import json,sys
from src.ingestion import source_receipts
receipt, sidecar, reason = source_receipts.retained(sys.argv[1])
print(json.dumps({'receipt':receipt, 'reason':reason}))
"""
    result = subprocess.run([sys.executable, "-c", code, str(weather_live.ARCHIVE_CACHE)],
        text=True, capture_output=True, check=True, env=dict(os.environ))
    after = json.loads(result.stdout)
    assert after["reason"] is None
    assert after["receipt"]["sourceReceiptId"] == quality["provenance"]["sourceReceiptId"]
    assert after["receipt"]["firstAvailableAt"] == quality["sourceReceipts"][0]["firstAvailableAt"]


def test_current_hourly_repeated_bytes_preserve_first_original_availability(isolated):
    folder = source_receipts.archive_root()
    (folder / "archive").mkdir(parents=True)
    port = port_registry.all_ports()[0]
    raw = json.dumps({"hourly": {"time": ["2026-10-22T00:00"], "wave_height": [1.2]},
        "hourly_units": {"wave_height": "m"}}).encode()
    digest = hashlib.sha256(raw).hexdigest()
    (folder / "archive" / (digest + ".response")).write_bytes(raw)
    def snapshot(at):
        body = {"kind": "marine", "portCode": port.locode,
            "source": "https://marine-api.open-meteo.com/v1/marine", "availableAt": at,
            "responseSha256": digest, "request": {"latitude": port.lat, "longitude": port.lon},
            "units": {"wave_height": "m"}, "rows": [{"validAt": "2026-10-22T00:00:00+00:00", "wave_height": 1.2}]}
        body["snapshotId"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        (folder / "archive" / (body["snapshotId"] + ".json")).write_text(json.dumps(body))
        return body
    snapshot("2026-10-21T00:00:00+00:00")
    latest = snapshot("2026-10-22T00:00:00+00:00")
    (folder / f"marine-{port.locode}.json").write_text(json.dumps(latest))
    quality = weather_quality.current_weather_products()[0]["sourceQuality"]
    assert quality["sourceReceipts"][0]["firstAvailableAt"] == "2026-10-21T00:00:00+00:00"
    assert quality["sourceReceipts"][0]["fetchedAt"] == "2026-10-22T00:00:00+00:00"
    assert quality["units"][0]["sourceUnit"] == "m" and quality["units"][0]["rawOrDerived"] == "RAW"


def test_legacy_single_block_cannot_inherit_configured_physical_port(isolated):
    # A copied Chennai grid block has no original request/order mapping. The
    # currently configured first port must not become its physical coverage.
    block = archive_block(latitude=13.0, longitude=80.25)
    weather_live.ARCHIVE_CACHE.write_text(json.dumps([block]))
    quality = weather_quality.quality_for_weather_source(
        "Weather history (Open-Meteo ERA5 archive)", {"status": "LIVE"})
    assert quality["coverage"]["portCodes"] is None
    assert quality["coverage"]["variables"] == ["rainfall", "wind_gust", "wind_speed"]
    assert quality["coverage"]["observedThrough"] == "2025-01-02"
    assert all(row["portCode"] is None for row in quality["gridLocations"])
    assert quality["receipt"]["status"] == "UNAVAILABLE"
    assert any("physical ports are unknown" in reason for reason in quality["unknownReasons"])


def test_optional_quality_failure_preserves_numeric_ingestion(isolated, monkeypatch):
    monkeypatch.setattr(weather_live, "_fetch", lambda *a, **k: ([archive_block()], "cache"))
    monkeypatch.setattr(weather_quality, "quality_for_weather_source", Mock(side_effect=ValueError("private/local/path")))
    recorded = Mock()
    monkeypatch.setattr(weather_live.provenance, "record", recorded)
    frame = weather_live.fetch_archive_weather(pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-02"))
    assert frame.loc[0, "wind_speed"] == 10 * weather_live.KMH_TO_KNOTS
    assert recorded.call_args.kwargs["source_quality"] is None


@pytest.mark.parametrize("damage", ["identity", "provider", "future"])
def test_invalid_hourly_metadata_cannot_assert_coverage(isolated, damage):
    folder = source_receipts.archive_root()
    folder.mkdir(parents=True)
    port = port_registry.all_ports()[0]
    body = {"kind": "marine", "portCode": port.locode,
        "source": "https://marine-api.open-meteo.com/v1/marine",
        "availableAt": "2099-01-01T00:00:00+00:00" if damage == "future" else "2026-10-21T00:00:00+00:00",
        "rows": [{"validAt": "2026-10-22T00:00:00+00:00", "wave_height": 1.2}],
        "units": {"wave_height": "m"}}
    if damage == "provider":
        body["source"] = "https://unapproved.example.test/forecast"
    body["snapshotId"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    if damage == "identity":
        body["snapshotId"] = "bad-identity"
    (folder / f"marine-{port.locode}.json").write_text(json.dumps(body))
    q = weather_quality.current_weather_products()[0]["sourceQuality"]
    assert q["coverage"]["portCodes"] == [] and q["coverage"]["variables"] == []
    assert q["coverage"]["targetFrom"] is None and q["units"] == []
    assert q["sourceReceipts"][0]["parseStatus"] == "REJECTED"
    assert q["sourceReceipts"][0]["firstAvailableAt"] is None
    assert q["receipt"]["status"] == "UNAVAILABLE"


def test_future_daily_receipt_is_not_claimed_as_fresh(isolated, monkeypatch):
    monkeypatch.setattr(source_receipts, "now_iso", lambda: "2099-01-01T00:00:00+00:00")
    fetch_once(monkeypatch, archive_block())
    q = weather_quality.quality_for_weather_source("Weather history (Open-Meteo ERA5 archive)", {"status": "LIVE"})
    assert q["provenance"]["originalHash"] is None
    assert q["receipt"]["lastFetchedAt"] is None and q["receipt"]["lastCheckedAt"] is None
    assert q["receipt"]["status"] == "UNAVAILABLE"
    assert q["coverage"]["portCodes"] is None


def test_unwritable_optional_lock_preserves_readable_cache(isolated, monkeypatch):
    (first, _), client = fetch_once(monkeypatch, archive_block())
    monkeypatch.setattr(source_receipts, "cache_lock", Mock(side_effect=PermissionError("private path")))
    cached, mode = weather_live._fetch(weather_live.ARCHIVE_URL, request_params(), weather_live.ARCHIVE_CACHE, 3600)
    assert mode == "cache" and cached == first
    assert client.get.call_count == 1
