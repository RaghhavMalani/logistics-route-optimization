from datetime import datetime, timedelta, timezone
import hashlib
import json
from unittest.mock import Mock
from src.portwatch_os.intelligence import current_environment as env

AT = datetime(2026,10,10,8,tzinfo=timezone.utc)


def response():
    payload = {"hourly_units":{"wind_speed_10m":"kn","wind_gusts_10m":"kn","wind_direction_10m":"°","precipitation":"mm","visibility":"m"},
               "hourly":{"time":["2026-10-10T08:00","2026-10-10T09:00"],"wind_speed_10m":[10.,11.],"wind_gusts_10m":[18.,19.],"wind_direction_10m":[220,230],"precipitation":[.1,0],"visibility":[10000,9000]}}
    return payload


def test_raw_forecast_receipt_archived_without_inventing_issue_or_observation(tmp_path,monkeypatch):
    monkeypatch.setattr(env,"ROOT",tmp_path)
    monkeypatch.setattr(env,"wall_now",lambda:AT)
    raw=json.dumps(response()).encode()
    provider=Mock(content=raw);provider.json.return_value=response()
    get=Mock(return_value=provider);monkeypatch.setattr(env.requests,"get",get)
    result=env.refresh("surface",env.port_registry.resolve("INNSA"))
    assert result["status"]=="CURRENT" and result["issuedAt"] is None and result["observedAt"] is None
    assert result["availableAt"]==AT.isoformat() and result["rows"][0]["validAt"]==AT.isoformat()
    assert result["rows"][0]["wind_gusts_10m"]==18
    assert (tmp_path/"archive"/(hashlib.sha256(raw).hexdigest()+".response")).read_bytes()==raw
    env.refresh("surface",env.port_registry.resolve("INNSA"))
    assert get.call_count==1
    assert env.dated(result,AT+timedelta(hours=2))["status"]=="STALE"


def test_unexpected_units_do_not_create_current_weather(tmp_path,monkeypatch):
    monkeypatch.setattr(env,"ROOT",tmp_path)
    bad=response();bad["hourly_units"]["wind_gusts_10m"]="km/h"
    provider=Mock(content=json.dumps(bad).encode());provider.json.return_value=bad
    monkeypatch.setattr(env.requests,"get",Mock(return_value=provider))
    assert env.refresh("surface",env.port_registry.resolve("INNSA"))["status"]=="UNAVAILABLE"
    assert not list(tmp_path.glob("surface-*.json"))


def test_hazard_publication_event_validity_and_latest_event_are_retained():
    def item(pub, end="Sat, 10 Oct 2026 09:00:00 GMT"):
        return f'<item><title>Dated earthquake</title><pubDate>{pub}</pubDate><fromdate>Sat, 10 Oct 2026 07:00:00 GMT</fromdate><todate>{end}</todate><point>20 70</point><eventtype>EQ</eventtype><eventid>7</eventid><alertlevel>Green</alertlevel><link>https://www.gdacs.org/report.aspx?eventid=7</link></item>'
    xml='<rss><channel>'+item("Sat, 10 Oct 2026 07:10:00 GMT")+item("Sat, 10 Oct 2026 07:20:00 GMT")+item("Sun, 11 Oct 2026 07:20:00 GMT")+'</channel></rss>'
    rows=env._hazards(xml,AT)
    assert len(rows)==1 and rows[0]["publishedAt"]=="2026-10-10T07:20:00+00:00"
    assert rows[0]["observedAt"]=="2026-10-10T07:00:00+00:00"
    assert rows[0]["validThrough"]=="2026-10-10T09:00:00+00:00"
    assert "no port closure" in rows[0]["relationship"]
