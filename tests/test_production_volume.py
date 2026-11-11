from pathlib import Path
from contextlib import closing
import sqlite3

import pytest

from scripts import production_volume as volume
from src.portwatch_os import state_capacity


def test_backup_preflight_preserves_reserve_and_creates_no_folder(tmp_path, monkeypatch):
    (tmp_path / "state").write_text("preserve me")
    size = volume.copy_size(volume.state_files(tmp_path))
    name = "20261111-150000-insufficient"
    monkeypatch.setattr(volume, "state_capacity", lambda _: {"totalBytes": size * 5, "freeBytes": size})
    with pytest.raises(ValueError, match="1.5 ×"):
        volume.backup(tmp_path, name, "restore program")
    assert not (tmp_path / volume.BACKUP_ROOT).exists()

    monkeypatch.setattr(volume, "state_capacity", lambda _: {"totalBytes": size * 10, "freeBytes": size * 2})
    with pytest.raises(ValueError, match="20%"):
        volume.backup(tmp_path, name, "restore program")
    assert not (tmp_path / volume.BACKUP_ROOT).exists()


def test_backup_retains_sqlite_wal_and_prune_requires_exact_recorded_hashes(tmp_path):
    with sqlite3.connect(tmp_path / "test.db") as database:
        database.execute("PRAGMA journal_mode=WAL")
        database.execute("CREATE TABLE saved (name TEXT)")
        database.execute("INSERT INTO saved VALUES ('committed state')")
        database.commit()
        oldest, middle, newest = [
            volume.backup(tmp_path, f"202611{day:02d}-150000-test", "restore program")
            for day in (9, 10, 11)
        ]
    uri = (Path(newest["backup"]) / "test.db").as_uri() + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as restored:
        assert restored.execute("SELECT name FROM saved").fetchone() == ("committed state",)
    with pytest.raises(ValueError, match="candidates changed"):
        volume.prune(tmp_path, {oldest["name"]: "wrong signature"})
    assert Path(oldest["backup"]).exists()
    result = volume.prune(tmp_path, {oldest["name"]: oldest["signature"]})
    assert result["deleted"] == [oldest["name"]]
    assert result["kept"] == [middle["name"], newest["name"]]
    assert not Path(oldest["backup"]).exists()
    assert volume.verify_backup(Path(newest["backup"]))["signature"] == newest["signature"]


@pytest.mark.parametrize(("free", "status"), [(199, "degraded"), (200, "ok")])
def test_health_degrades_below_twenty_percent(free, status, monkeypatch, tmp_path):
    from backend.app.domains.intelligence import source_status
    from backend.app.domains.system import health
    from backend.app.services import cache_service as cache

    forecast = tmp_path / "forecast.json"
    forecast.write_text("{}")
    monkeypatch.setattr(cache, "FORECAST_CACHE", forecast)
    monkeypatch.setattr(health, "durable_stores", lambda: {"ok": True})
    monkeypatch.setattr(source_status, "source_status", lambda: {"degraded": False, "sources": []})
    monkeypatch.setattr(state_capacity.shutil, "disk_usage", lambda _: (1000, 1000 - free, free))
    result = health.health_check()
    assert result["status"] == status
    assert result["stateCapacity"]["freeBytes"] == free
    assert result["stateCapacity"]["minimumFreePercent"] == 20
    if free < 200:
        with pytest.raises(ValueError, match="20%"):
            state_capacity.require_capacity(result["stateCapacity"])
    else:
        state_capacity.require_capacity(result["stateCapacity"])
