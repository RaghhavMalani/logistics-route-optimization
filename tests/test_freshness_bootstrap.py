from src.portwatch_os.freshness.bootstrap import seed_missing


def test_restart_keeps_retained_bytes_and_dates(tmp_path):
    source, durable = tmp_path / 'seed', tmp_path / 'durable'
    source.mkdir()
    (source / 'weather.json').write_text('old response')
    assert seed_missing(source, durable) == 1
    (durable / 'weather.json').write_text('new response')
    before = (durable / 'weather.json').stat().st_mtime_ns
    assert seed_missing(source, durable) == 0
    assert (durable / 'weather.json').read_text() == 'new response'
    assert (durable / 'weather.json').stat().st_mtime_ns == before


def test_key_alone_cannot_publish_ais(monkeypatch):
    from types import SimpleNamespace
    from src.portwatch_os.fabric.ais import client
    started = []
    monkeypatch.setattr(client, 'get_client', lambda: SimpleNamespace(configured=True, start=lambda: started.append(True)))
    monkeypatch.setenv('PORTWATCH_AIS_PUBLICATION_APPROVED', '0')
    monkeypatch.setenv('PORTWATCH_AIS_REPLAY_PATH', '')
    client.start_client()
    assert started == []
    monkeypatch.setenv('PORTWATCH_AIS_PUBLICATION_APPROVED', '1')
    client.start_client()
    assert started == [True]


def test_unapproved_workspace_uses_replay_even_with_a_local_key(monkeypatch):
    from src.portwatch_os.fabric.ais import client
    from src.portwatch_os.fabric import ais_mode
    monkeypatch.setenv('AISSTREAM_API_KEY', 'not-a-real-key')
    monkeypatch.setenv('PORTWATCH_AIS_PUBLICATION_APPROVED', '0')
    client.reset_client()
    try:
        assert client.get_client().configured is False
        assert ais_mode(licence_mode='DEMO')['mode'] == 'SIMULATED_TRAFFIC'
    finally:
        client.reset_client()
