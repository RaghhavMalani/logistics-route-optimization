"""Synthetic context/revision tests plus existing retained public PDF regression."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.portwatch_os.intelligence import operational_feed as feed
from src.portwatch_os.intelligence.public_ports import CHENNAI_ETA, PublicPilot, parse_pdf

NOW = datetime(2026, 10, 17, 14, tzinfo=timezone.utc)
URL = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/Daily_Ports_Data/FeatureServer/0/query"


def response(day="2026-10-09", calls=28, **changes):
    return json.dumps({"features": [{"attributes": {"date": day, "portid": "port776", "portcalls": calls, **changes}}]}).encode()


def retain(archive, payload=None, at=NOW):
    return archive.retain(payload or response(), port="INNSA", url=URL, received_at=at)


def test_aggregate_revisions_repeat_receipts_and_first_availability_survive_restart(tmp_path, monkeypatch):
    archive = feed.AggregateArchive(tmp_path)
    first = retain(archive)
    repeated = retain(archive, at=NOW + timedelta(hours=1))
    revised = retain(archive, response(calls=29), NOW + timedelta(hours=2))
    assert first["sha256"] == repeated["sha256"] != revised["sha256"]
    assert len(archive.receipts(NOW + timedelta(hours=3))) == 3
    assert repeated["records"][0]["firstAvailableAt"] == first["receivedAt"]
    assert revised["records"][0]["firstAvailableAt"] == revised["receivedAt"]
    archive = feed.AggregateArchive(tmp_path)
    monkeypatch.setattr(feed, "get_aggregate", lambda: archive)
    item = feed.aggregate_product(archive, "INNSA", NOW + timedelta(hours=3))
    selected = item["records"][0]["selector"]
    resolved = feed.resolve_evidence(selected, NOW + timedelta(hours=3))
    assert item["status"] == resolved["status"] == "STALE"
    assert item["clocks"]["reportDate"] == "2026-10-09"
    assert item["clocks"]["observedAt"] is None and item["clocks"]["publishedAt"] is None
    assert resolved["record"]["unit"] == "calls/day"
    assert resolved["eligibleForRealTarget"] is False
    with pytest.raises(ValueError, match="unavailable"):
        feed.resolve_evidence(selected, NOW + timedelta(hours=1))


@pytest.mark.parametrize("raw", [response("2026-10-18"), response(calls=-1), response(calls=1.5),
    response(calls=True), response(portid="port235"), b'{"error":{"message":"unavailable"}}',
    b'{"features":[],"exceededTransferLimit":true}', b'[]', b'null', b'{"features":[null]}',
    b'{"features":[12]}', b'{"features":[{"attributes":null}]}', b'not json', response(calls=float("nan"))])
def test_invalid_or_future_aggregate_retains_original_but_cannot_become_evidence(tmp_path, raw):
    archive = feed.AggregateArchive(tmp_path)
    receipt = retain(archive, raw)
    assert receipt["errors"] and not receipt["records"]
    assert archive.evidence(receipt, NOW).read_bytes() == raw
    assert feed.aggregate_product(archive, "INNSA", NOW)["status"] == "UNAVAILABLE"


def test_failure_preserves_last_good_and_original_hash_is_rechecked(tmp_path, monkeypatch):
    archive = feed.AggregateArchive(tmp_path)
    receipt = retain(archive)
    archive.check("INNSA", NOW + timedelta(hours=1), "provider unavailable")
    product = feed.aggregate_product(feed.AggregateArchive(tmp_path), "INNSA", NOW + timedelta(hours=2))
    assert product["records"] and product["status"] == "STALE"
    assert product["collection"]["errors"] == ["provider unavailable"]
    assert product["collection"]["lastSuccessfulCollectionAt"] == receipt["receivedAt"]
    archive.evidence(receipt, NOW).write_bytes(b"corrupted synthetic original")
    assert feed.aggregate_product(archive, "INNSA", NOW)["status"] == "UNAVAILABLE"
    monkeypatch.setattr(feed, "get_aggregate", lambda: archive)
    selector = product["records"][0]["selector"]
    with pytest.raises(ValueError, match="hash mismatch"):
        feed.resolve_evidence(selector, NOW + timedelta(hours=2))


def test_aggregate_parsed_metadata_cannot_override_source_original(tmp_path):
    archive = feed.AggregateArchive(tmp_path)
    receipt = retain(archive)
    receipt["records"][0]["portcalls"] = 999
    with pytest.raises(ValueError, match="original response"):
        archive.evidence(receipt, NOW)
    with pytest.raises(ValueError, match="approved exact"):
        archive.retain(response(), port="INNSA", url="https://fixture.example/query", received_at=NOW)


def test_pdf_header_geometry_preserves_complete_dimensions_in_existing_original():
    raw = (Path(__file__).parent / "fixtures/public_ports/chennai-eta-2026-10-07.pdf").read_bytes()
    report = parse_pdf(raw, "INMAA", "expected")
    vessel = next(r for r in report["records"] if r["vesselName"] == "HOSEI LIBERTY")
    assert (vessel["loa"], vessel["beam"], vessel["draft"]) == (127.7, 19.6, 6.2)
    assert vessel["berthRef"] == "JD&CB2"


def test_pdf_context_future_expected_allowed_without_actual_vessel_link(tmp_path, monkeypatch):
    store = PublicPilot(tmp_path)
    raw = (Path(__file__).parent / "fixtures/public_ports/chennai-eta-2026-10-07.pdf").read_bytes()
    at = NOW - timedelta(days=10)
    store.import_pdf("INMAA", "expected", CHENNAI_ETA, raw, collected=at, actor="fixture")
    monkeypatch.setattr(feed, "get_service", lambda: store)
    monkeypatch.setattr(feed, "get_aggregate", lambda: feed.AggregateArchive(tmp_path))
    products = feed.latest_products(at + timedelta(seconds=1))
    product = next(p for p in products if p["product"] == "PUBLIC_PORT_PDF" and p["records"])
    future = next(r for r in product["records"] if r["record"].get("etaAt") and feed.instant(r["record"]["etaAt"]) > at)
    evidence = feed.resolve_evidence(future["selector"], at + timedelta(seconds=1))
    assert evidence["semanticClass"] == "PUBLISHED_EXPECTED_ARRIVAL"
    assert evidence["observedAt"] is None and evidence["eligibleForRealTarget"] is False
    assert len(product["records"]) == product["counts"]["records"]
    with pytest.raises(ValueError, match="physical port"):
        feed.resolve_evidence({**future["selector"], "portCode": "INNSA"}, at + timedelta(seconds=1))
    with pytest.raises(ValueError, match="unavailable"):
        feed.resolve_evidence(future["selector"], at - timedelta(seconds=1))
    store.close()


def test_collection_uses_existing_query_receipt_sink_and_persists_network_failure(tmp_path):
    archive = feed.AggregateArchive(tmp_path)
    with patch("app.data.portwatch._query", side_effect=TimeoutError("fixture outage")):
        with pytest.raises(TimeoutError):
            feed.collect_aggregate(archive=archive)
    # Last attempt survives a new adapter instance, even without an HTTP response.
    status = feed.aggregate_product(feed.AggregateArchive(tmp_path), "INNSA", feed.wall_now())
    assert status["collection"]["errors"] == ["fixture outage"]
