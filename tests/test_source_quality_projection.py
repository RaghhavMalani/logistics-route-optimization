"""Additive export boundary tests; producer archive correctness is tested separately."""
import copy
from datetime import datetime, timezone
import importlib
import json
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.routes import provenance as endpoint
from src.ingestion import weather_quality
from src.portwatch_os.intelligence import operational_quality
from src.utils import provenance, source_quality


AT = datetime(2026, 10, 22, 10, tzinfo=timezone.utc)


def known_quality():
    # Reader-export fixture, not an invented original/provider response. Its
    # date-only period and retained receipt identity must pass through unchanged.
    return {
        "schemaVersion": 1, "metadataVersion": "reader-fixture-v1",
        "temporalRole": "HISTORICAL", "valueKinds": ["DERIVED"],
        "operationalUse": "CONTEXT_ONLY",
        "receipt": {"status": "CACHED_LIVE", "lastFetchedAt": "2026-10-18T09:35:00Z",
                    "lastCheckedAt": "2026-10-22T09:35:00Z", "fallback": None},
        "coverage": {"portCodes": ["INNSA"], "variables": ["wind_gust"],
                     "observedFrom": "2026-10-01", "observedThrough": "2026-10-15",
                     "datePrecision": "DATE_ONLY", "forecastOriginAt": None,
                     "targetFrom": None, "targetThrough": None},
        "provenance": {"provider": "Open-Meteo", "sourceProductId": "open-meteo:era5:daily-history-v1",
                       "sourceReceiptId": "retained-response-1", "originalHash": "b" * 64,
                       "originalRef": "https://archive-api.open-meteo.com/v1/archive",
                       "derivationVersion": "open-meteo-daily-flatten-v1"},
        "quality": {"rowCount": 15, "confidence": None, "completeness": None,
                    "missingFields": ["visibility", "wave_height"], "issues": []},
        "unknownReasons": ["Provider publication instant is unavailable."],
        "sourceReceipts": [], "units": [{"variable": "wind_gust", "sourceUnit": "km/h",
            "outputUnit": "kn", "derivation": "source × 0.539957", "rawOrDerived": "DERIVED"}],
        "semantics": {"dataKind": "REANALYSIS", "stationObservation": False,
                      "firstAvailableAt": "2026-10-18T09:35:00Z", "originalHashVerified": True},
    }


def legacy_payload():
    return {
        "generatedAt": "2026-10-17T08:00:00Z", "readiness": 0.275,
        "counts": {"LIVE": 0, "CACHED_LIVE": 0, "STALE": 1, "SYNTHETIC": 0,
                   "SIMULATED_TRAFFIC": 0, "SCHEMATIC": 0, "UNAVAILABLE": 1},
        "live": [], "cached": [], "stale": ["weather history"],
        "synthetic": [], "simulated": [], "schematic": [], "unavailable": ["legacy other"],
        "sources": {
            "weather history": {"source": "weather history", "provider": "Open-Meteo",
                "status": "STALE", "confidence": 0.55, "rows": 15,
                "observed_at": "2026-10-15T00:00:00Z", "fetched_at": "2026-10-18T09:35:00Z",
                "detail": "Useful retained legacy history", "fallback": "legacy cache"},
            "legacy other": {"source": "legacy other", "provider": "unknown",
                "status": "UNAVAILABLE", "confidence": 0.0, "rows": None,
                "detail": "No supported original retained", "fallback": None},
        },
    }


@pytest.fixture
def readers(monkeypatch):
    exports = {
        "weather": Mock(return_value=[]), "activity": Mock(return_value=None),
        "weather_row": Mock(return_value=None), "operational": Mock(return_value=[]),
    }
    monkeypatch.setattr(weather_quality, "current_weather_products", exports["weather"])
    monkeypatch.setattr(weather_quality, "quality_for_weather_source", exports["weather_row"])
    monkeypatch.setattr(operational_quality, "operational_source_rows", exports["operational"])
    monkeypatch.setattr(operational_quality, "quality_for_activity_source", exports["activity"])
    return exports


def legacy_fields(payload):
    value = copy.deepcopy(payload)
    value.pop("sourceQualityProducts", None)
    value.pop("sourceQualityProjection", None)
    for row in value.get("sources", {}).values():
        if isinstance(row, dict):
            row.pop("sourceQuality", None)
            row.pop("sourceQualityError", None)
    return value


def test_known_reader_metadata_passes_through_without_changing_legacy_semantics(readers):
    quality = known_quality()
    readers["weather_row"].side_effect = lambda name, row: quality if name == "weather history" else None
    product = {"source": "Current surface forecast / INNSA", "status": "CACHED_LIVE",
               "confidence": None, "sourceQuality": {**quality, "temporalRole": "FORECAST"}}
    readers["weather"].return_value = [product]
    original = legacy_payload()
    before = copy.deepcopy(original)
    result = source_quality.project(original)
    assert legacy_fields(result) == before
    assert original == before
    assert result["sources"]["weather history"]["sourceQuality"] == quality
    assert result["sourceQualityProducts"][product["source"]] == product
    assert result["sources"]["weather history"]["confidence"] == 0.55
    assert result["sources"]["weather history"]["sourceQuality"]["quality"]["confidence"] is None
    assert result["sourceQualityProjection"]["readOnly"] is True
    assert result["sourceQualityProjection"]["unavailableProjections"] == []
    assert "not calibrated accuracy" in result["sourceQualityProjection"]["legacyReadinessMeaning"]
    assert readers["activity"].call_count == 1  # Fallback only for the unsupported other source.
    assert readers["weather"].call_count == readers["operational"].call_count == 1


def test_source_record_optional_export_preserves_snapshot_and_readiness(monkeypatch):
    monkeypatch.setattr(provenance, "_STATE", {})
    monkeypatch.setattr(provenance, "_now", lambda: AT)
    first = provenance.record("weather history", "STALE", provider="Open-Meteo",
                              fetched_at=AT, rows=15)
    baseline = provenance.snapshot()
    assert "sourceQuality" not in first.to_dict() and "source_quality" not in first.to_dict()
    quality = known_quality()
    second = provenance.record("weather history", "STALE", provider="Open-Meteo",
                               fetched_at=AT, rows=15, source_quality=quality)
    with_quality = provenance.snapshot()
    assert legacy_fields(with_quality) == baseline
    assert with_quality["sources"]["weather history"]["sourceQuality"] == quality
    assert "source_quality" not in second.to_dict()
    # Serialized diagnostics are detached from the record's frozen declaration.
    exported = second.to_dict()
    exported["sourceQuality"]["coverage"]["portCodes"].append("INMAA")
    assert second.to_dict()["sourceQuality"]["coverage"]["portCodes"] == ["INNSA"]


def test_optional_unknown_and_malformed_quality_leave_legacy_information_visible(readers):
    payload = legacy_payload()
    malformed = {"schemaVersion": 999, "temporalRole": {"wrong": "shape"}}
    payload["sources"]["legacy other"]["sourceQuality"] = malformed
    result = source_quality.project(payload)
    assert legacy_fields(result) == legacy_fields(payload)
    assert result["sources"]["legacy other"]["sourceQuality"] == malformed
    assert "sourceQuality" not in result["sources"]["weather history"]
    # Validation/fallback of optional DTOs belongs to the existing frontend
    # boundary; the export must not discard the useful legacy register row.
    assert result["sources"]["legacy other"]["detail"] == "No supported original retained"
    assert result["readiness"] == payload["readiness"]


def test_reader_failures_are_sanitized_and_do_not_hide_legacy_rows(readers):
    secret = "D:/private/keys/provider-token-secret.json"
    readers["weather_row"].side_effect = RuntimeError(secret)
    readers["weather"].side_effect = OSError(secret)
    readers["operational"].side_effect = ValueError(secret)
    payload = legacy_payload()
    result = source_quality.project(payload)
    assert legacy_fields(result) == payload
    assert result["sourceQualityProducts"] == {}
    assert result["sourceQualityProjection"]["unavailableProjections"] == ["weather", "operational"]
    assert all(row["sourceQualityError"] == "Retained source-quality evidence could not be verified."
               for row in result["sources"].values())
    assert secret not in json.dumps(result)
    assert secret not in json.dumps(payload)


def test_projection_reads_do_not_collect_or_mutate_cached_register(readers, monkeypatch, tmp_path):
    sentinel = tmp_path / "retained-original.response"
    sentinel.write_bytes(b"retained original must remain unchanged")
    before_files = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    payload = legacy_payload()
    before_payload = copy.deepcopy(payload)
    import requests
    forbidden = Mock(side_effect=AssertionError("GET projection must not collect"))
    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(requests, "post", forbidden)
    monkeypatch.setattr(provenance, "save", forbidden)
    first = source_quality.project(payload)
    second = source_quality.project(payload)
    assert first == second
    assert payload == before_payload
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before_files
    forbidden.assert_not_called()


def test_exported_product_diagnostics_are_detached_from_reader_owned_rows(readers):
    product = {"source": "Current surface / INNSA", "status": "CACHED_LIVE",
               "sourceQuality": known_quality()}
    readers["weather"].return_value = [product]
    before = copy.deepcopy(product)
    result = source_quality.project(legacy_payload())
    result["sourceQualityProducts"][product["source"]]["sourceQuality"]["coverage"]["portCodes"].append("INMAA")
    assert product == before


def test_get_projection_and_reimport_keep_supported_identities_and_cache_unchanged(readers, monkeypatch):
    quality = known_quality()
    readers["weather_row"].side_effect = lambda name, row: quality if name == "weather history" else None
    product = {"source": "IMF daily aggregate / INNSA", "status": "STALE", "sourceQuality": quality}
    readers["operational"].return_value = [product]
    payload = legacy_payload()
    original = copy.deepcopy(payload)
    cache_read = Mock(return_value=payload)
    monkeypatch.setattr(endpoint.cache, "get_provenance", cache_read)
    monkeypatch.setattr(endpoint.cache, "artefact_age_seconds", lambda path: 123.0)
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/api")
    with TestClient(app) as client:
        first = client.get("/api/provenance")
        second = client.get("/api/provenance")
        assert first.status_code == second.status_code == 200
        body = first.json()
        assert second.json() == body
        importlib.reload(source_quality)
        restarted = client.get("/api/provenance")
        assert restarted.status_code == 200 and restarted.json() == body
    assert body["cacheAgeSeconds"] == 123.0
    assert body["sourceQualityProjection"]["version"] == "retained-public-source-quality-v1"
    frozen = body["sources"]["weather history"]["sourceQuality"]
    assert frozen["provenance"] == quality["provenance"]
    assert frozen["coverage"]["observedThrough"] == "2026-10-15"
    assert frozen["coverage"]["targetThrough"] is None
    assert body["sourceQualityProducts"][product["source"]]["sourceQuality"] == quality
    assert payload == original and cache_read.call_count == 3


def test_empty_legacy_get_keeps_rebuild_reason_separate_from_available_products(readers, monkeypatch):
    readers["weather"].return_value = [{"source": "Public weather", "status": "UNAVAILABLE",
                                        "sourceQuality": known_quality()}]
    monkeypatch.setattr(endpoint.cache, "get_provenance", lambda: {"sources": {}, "readiness": 0.0})
    monkeypatch.setattr(endpoint.cache, "artefact_age_seconds", lambda path: None)
    result = endpoint.provenance()
    assert result["sources"] == {} and result["readiness"] == 0.0
    assert result["reason"] == endpoint.cache.REBUILD_HINT
    assert result["cacheAgeSeconds"] is None
    assert list(result["sourceQualityProducts"]) == ["Public weather"]


@pytest.mark.parametrize("bad_number", [float("nan"), float("inf")])
@pytest.mark.parametrize("placement", ["legacy", "product"])
def test_nonfinite_optional_quality_cannot_make_legacy_get_unserializable(readers, monkeypatch, bad_number, placement):
    payload = legacy_payload()
    malformed = {"quality": {"confidence": bad_number}}
    if placement == "legacy":
        payload["sources"]["weather history"]["sourceQuality"] = malformed
    else:
        readers["weather"].return_value = [{**payload["sources"]["weather history"],
            "source": "Additional public product", "sourceQuality": malformed}]
    monkeypatch.setattr(endpoint.cache, "get_provenance", lambda: payload)
    monkeypatch.setattr(endpoint.cache, "artefact_age_seconds", lambda path: None)
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/api")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/provenance")
    assert response.status_code == 200, response.text
    row = (response.json()["sources"]["weather history"] if placement == "legacy" else
           response.json()["sourceQualityProducts"]["Additional public product"])
    assert row["detail"] == payload["sources"]["weather history"]["detail"]
    assert row["status"] == "STALE" and row["confidence"] == 0.55
    assert row.get("sourceQuality") is None
    assert isinstance(row.get("sourceQualityError"), str)
