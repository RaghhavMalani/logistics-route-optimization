"""Visitor privacy, immutable result integrity and recomputable public metrics."""
import hashlib
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.routes import public_research as public
from src.portwatch_os.clock import get_clock, wall_now

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PORTWATCH_IDENTITY_MODE", "verified")
    # No lifespan startup, background collection, private ledger reads or fitting.
    c = TestClient(app)
    try:
        yield c
    finally:
        c.close()


def test_public_projection_omits_private_records_and_untrusted_urls(client):
    now = wall_now().isoformat()
    event = {"id":"test-news", "title":"Red Sea transit disruption", "timestamp":now,
        "tag":"CHOKEPOINT_CLOSURE", "chokepoint":"BAB_EL_MANDEB", "severity":.7,
        "source":"Public report", "url":"https://public.example/report"}
    provenance = {"sources": {"Maritime events (GDELT + GDACS)":{"isReal":True}, "Port activity (IMF PortWatch)":{"isReal":True}}}
    forecast = {"day":1,"originDate":now,"targetDate":now,"q10":10,"q50":20,"q90":30,"privateCameraUrl":"https://secret.example/camera"}
    with patch.object(public.cache,"get_provenance",return_value=provenance), patch.object(public.cache,"get_news_bundle",return_value={"events":[event]}), patch.object(public.cache,"get_port_state",return_value={"INMAA":{"congestionIndex":20,"operator":"PRIVATE_OPERATOR"}}), patch.object(public.cache,"get_forecast_by_port",return_value={"INMAA":[forecast]}):
        response = client.get("/api/public/explore", headers={"X-PortWatch-Role":"NATIONAL_ADMIN","Authorization":"Bearer forged"})
        assert response.status_code == 200
        data = response.json()
        assert data["readOnly"] is True and len(data["ports"]) == 13
        assert "secret.example" not in response.text and "PRIVATE_OPERATOR" not in response.text
        assert data["events"]
        assert all("affectedVessels" not in p for e in data["events"] for p in e["ports"])
        assert public.safe_url("https://user:password@example.com") is None
        assert public.safe_url("javascript:alert(1)") is None
        with get_clock().pin_replay(wall_now()):
            replay = client.get("/api/public/explore").json()
            assert not replay["events"] and not any(p["forecasts"] for p in replay["ports"])
        provenance["sources"]["Maritime events (GDELT + GDACS)"]["isReal"] = False
        provenance["sources"]["Port activity (IMF PortWatch)"]["isReal"] = False
        simulated = client.get("/api/public/explore").json()
        assert not simulated["events"] and not any(p["forecasts"] for p in simulated["ports"])


def test_visitor_exemption_does_not_authorize_writes_or_private_workspaces(client):
    forged = {"X-PortWatch-Role":"NATIONAL_ADMIN","X-PortWatch-Port":"INMAA"}
    for method,path in [("GET","/api/intelligence/cameras"),("GET","/api/public-arrivals/workspace?portCode=INMAA"),
                        ("POST","/api/public/explore"),("POST","/api/public-arrivals/refresh?portCode=INMAA"),
                        ("POST","/api/public/research/download/results.zip")]:
        assert client.request(method,path,headers=forged).status_code == 401


def test_release_download_allowlist_hash_and_missing_state(client, tmp_path, monkeypatch):
    monkeypatch.setenv("PORTWATCH_PUBLIC_RESEARCH_DIR", str(tmp_path))
    assert public.release()[1]["available"] is False
    assert client.get("/api/public/research/download/results.zip").status_code == 404
    folder = tmp_path/"research-0123456789abcdef"
    folder.mkdir()
    payload = b"model,mae\nGBM,5.9\n"
    (folder/"model_benchmark.csv").write_bytes(payload)
    manifest = {"available":True,"releaseId":folder.name,"downloads":[{"name":"model_benchmark.csv","sha256":hashlib.sha256(payload).hexdigest()}]}
    body = json.dumps(manifest).encode()
    (folder/"report.json").write_bytes(body)
    (tmp_path/"current.json").write_text(json.dumps({"releaseId":folder.name,"reportSha256":hashlib.sha256(body).hexdigest()}))
    assert client.get("/api/public/research/download/model_benchmark.csv").content == payload
    assert client.get("/api/public/research/download/model_benchmark.csv?releaseId="+folder.name).headers["cache-control"] == "no-store"
    assert client.get("/api/public/research/download/model_benchmark.csv?releaseId=research-ffffffffffffffff").status_code == 409
    assert client.get("/api/public/research/download/ledger.db").status_code == 404
    (folder/"model_benchmark.csv").write_bytes(b"changed")
    assert client.get("/api/public/research/download/model_benchmark.csv").status_code == 503
    (folder/"report.json").write_bytes(b"changed")
    assert client.get("/api/public/research/download/model_benchmark.csv").status_code == 503


def test_packaged_results_are_recomputable_and_common_ablations():
    folder, report = public.release()
    assert report["available"] is True
    for item in report["downloads"]:
        assert hashlib.sha256((folder/item["name"]).read_bytes()).hexdigest() == item["sha256"]
    assert hashlib.sha256((folder/"dataset.csv").read_bytes()).hexdigest() == report["reproducibility"]["datasetSha256"]
    rows = pd.read_csv(folder/"holdout_predictions.csv")
    for model in report["models"]:
        predictions = rows[rows.model == model["model"]]
        error = predictions.y_congestion_index-predictions.predicted_congestion
        assert len(predictions) == model["n"]
        assert abs(float(error.abs().mean())-model["mae"]) < .00006
        assert abs(float(error.mean())-model["signed_bias"]) < .00006
    keys = ["port_id","forecast_origin_date","target_date","horizon_day"]
    reference = rows[rows.model == "GBM quantile"][keys].reset_index(drop=True)
    for name in ("GBM history + calendar","GBM history only"):
        pd.testing.assert_frame_equal(reference, rows[rows.model == name][keys].reset_index(drop=True))


def test_published_research_survives_optional_store_failure_without_false_zero_counts(client):
    from src.portwatch_os.ledger.store import LedgerError
    with patch("src.portwatch_os.ledger.store.get_ledger", side_effect=LedgerError("PRIVATE_DATABASE_PATH")), patch.object(public,"pilot_counts",side_effect=sqlite3.DatabaseError("PRIVATE_COLLECTION_PATH")):
        response = client.get("/api/public/research")
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True and data["models"]
        assert data["weather"]["available"] is False and data["weather"]["total"] is None
        assert data["operational"]["available"] is False and not data["operational"]["ports"]
        assert "PRIVATE_DATABASE_PATH" not in response.text and "PRIVATE_COLLECTION_PATH" not in response.text


def test_public_weather_reads_configured_durable_archive_and_filters_private_sources(client, tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from src.portwatch_os.ledger.store import SqliteLedgerStore
    from src.portwatch_os.learning.weather_feedback import WeatherFeedback

    path = tmp_path / "public-weather.sqlite3"
    issued = datetime(2025, 6, 1, 10, tzinfo=timezone.utc)
    frame = pd.DataFrame([{"port_id": "JNPT", "date": pd.Timestamp(issued.replace(hour=0) + timedelta(days=5)).tz_localize(None), "wind_speed": 10.0}])
    ledger = SqliteLedgerStore(path)
    feedback = WeatherFeedback(ledger)
    for provider in ("Open-Meteo surface", "PRIVATE_OPERATOR"):
        feedback.record_frame(frame, issued_at=issued, provider=provider, source_state="LIVE", now=issued)
    ledger.close()
    monkeypatch.setenv("PORTWATCH_WEATHER_FEEDBACK_DB", str(path))
    response = client.get("/api/public/research")
    assert response.status_code == 200
    assert response.json()["weather"]["total"] == 1
    assert response.json()["weather"]["pending"] == 1
    assert response.json()["weather"]["resolved"] == 0
    assert "PRIVATE_OPERATOR" not in response.text
    monkeypatch.setenv("PORTWATCH_WEATHER_FEEDBACK_DB", str(tmp_path / "missing.sqlite3"))
    unavailable = client.get("/api/public/research").json()
    assert unavailable["available"] is True
    assert unavailable["weather"]["available"] is False
    assert unavailable["weather"]["total"] is None
