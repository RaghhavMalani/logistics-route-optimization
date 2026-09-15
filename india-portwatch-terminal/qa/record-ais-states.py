"""Record the traffic-state fixtures the browser suite replays.

The browser suite has to show the chart moving SIMULATED -> LIVE -> STALE,
and no recording of a real socket can do that on cue. So the states are
produced the honest way round: synthetic AIS envelopes are pushed through the
real normaliser, the real track store and the real state machine inside the
real FastAPI app, and what the API then *says* is written down. Nothing in
these files was typed by hand; every field is what the server answered.

Run from the terminal directory:

    python qa/record-ais-states.py

It writes, under qa/fixtures:

    fabric_health.json              the replay deployment (no key), as shipped
    fabric_health_live.json         a key, a socket, valid observations arriving
    fabric_health_stale.json        the same feed, twelve minutes after it stopped
    world_ais_tracks_live.json      the observed tracks behind the LIVE health
    world_ais_tracks_stale.json     the same tracks, gone stale
    world_marine.json               the sea at one instant, from the recorded grid
    world_entities.json             the fused hulls behind the tracks
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402
from src.portwatch_os.fabric.ais import AisStreamClient, TrackStore  # noqa: E402
from src.portwatch_os.fabric.ais import client as client_module  # noqa: E402
from src.portwatch_os.fabric.marine import MarineService, set_service  # noqa: E402
from src.portwatch_os.fusion import engine as fusion_module  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures"
MARINE_FIXTURE = ROOT / "tests" / "fixtures" / "open_meteo_marine_sample.json"


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S.%f") + "000 +0000 UTC"


def position(mmsi: str, lat: float, lon: float, *, at: datetime, sog: float, cog: float, heading: int = 511):
    return {
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": mmsi, "latitude": lat, "longitude": lon, "time_utc": stamp(at)},
        "Message": {"PositionReport": {"UserID": int(mmsi), "Sog": sog, "Cog": cog,
                                       "TrueHeading": heading, "NavigationalStatus": 0}},
    }


def static(mmsi: str, *, at: datetime, imo: int, name: str, callsign: str, destination: str):
    return {
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": mmsi, "latitude": 0.0, "longitude": 0.0, "time_utc": stamp(at)},
        "Message": {"ShipStaticData": {"UserID": int(mmsi), "ImoNumber": imo, "Name": name,
                                       "CallSign": callsign, "Destination": destination,
                                       "Eta": {"Month": at.month, "Day": at.day + 2, "Hour": 6, "Minute": 0}}},
    }


#: Four transponders in the Arabian Sea and the Gulf of Aden. Two say who
#: they are; two only say where they are, which is what a real feed looks like.
def feed(client: AisStreamClient, now: datetime) -> None:
    tracks = [
        ("419001101", 12.75, 45.60, 100.0, 13.8, dict(imo=9411002, name="MV KONKAN PIONEER", callsign="VTKP", destination="INNSA")),
        ("419001102", 16.20, 62.40, 78.0, 11.2, dict(imo=0, name="GULF EXPRESS", callsign="VTGE", destination="MUNDRA")),
        ("419001103", 18.60, 70.90, 45.0, 9.5, None),
        ("419001104", 13.90, 58.10, 250.0, 12.0, None),
    ]
    for mmsi, lat, lon, cog, sog, identity in tracks:
        # Ten minutes of history at one-minute reporting, then the head.
        for minutes in range(10, -1, -1):
            step = minutes / 60.0
            dlat = -step * sog / 60.0 * math.cos(math.radians(cog))
            dlon = -step * sog / 60.0 * math.sin(math.radians(cog))
            client.feed(position(mmsi, round(lat + dlat, 5), round(lon + dlon, 5),
                                 at=now - timedelta(minutes=minutes), sog=sog, cog=cog,
                                 heading=int(cog) if identity else 511), now=now - timedelta(minutes=minutes))
        if identity:
            client.feed(static(mmsi, at=now - timedelta(minutes=2), **identity), now=now - timedelta(minutes=2))


def install_client(api_key, now: datetime) -> AisStreamClient:
    client_module.reset_client()
    fusion_module.reset_engine()
    client = AisStreamClient(TrackStore(), api_key=api_key)
    client._on_observation = client_module._fuse
    if api_key:
        feed(client, now)
        client.status.health = "LIVE"
        client.status.connected_at = now - timedelta(minutes=15)
    client_module._CLIENT = client
    return client


def install_marine(now: datetime) -> None:
    payload = json.loads(MARINE_FIXTURE.read_text(encoding="utf-8"))
    from src.portwatch_os.fabric.marine import SAMPLE_POINTS

    points = SAMPLE_POINTS[:3]
    service = MarineService(points=points, fetcher=lambda url: payload, cache_path=None, api_key=None)
    service.grid(now=now)
    set_service(service)


def write(name: str, body) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(body), encoding="utf-8")
    print(f"{name}: {len(json.dumps(body))} bytes")


def main() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    tc = TestClient(app)

    # The sea, for every state.
    install_marine(now)
    write("world_marine.json", tc.get("/api/world/marine?mode=DEMO").json())

    # The replay deployment, as shipped.
    install_client(None, now)
    write("fabric_health.json", tc.get("/api/fabric/health?mode=DEMO").json())
    write("world_ais_tracks.json", tc.get("/api/world/ais/tracks?mode=DEMO").json())

    # A live feed.
    install_client("recorded-fixture-key", now)
    write("fabric_health_live.json", tc.get("/api/fabric/health?mode=DEMO").json())
    write("world_ais_tracks_live.json", tc.get("/api/world/ais/tracks?mode=DEMO").json())
    write("world_entities.json", tc.get("/api/world/entities?observedOnly=true").json())

    # The same feed, gone quiet: the transponders last reported twelve
    # minutes ago and nothing since. Nothing is re-timed; the messages simply
    # carry the times they carry, and the state machine reads them.
    install_client("recorded-fixture-key", now - timedelta(minutes=12))
    health = tc.get("/api/fabric/health?mode=DEMO").json()
    tracks = tc.get("/api/world/ais/tracks?mode=DEMO").json()
    assert health["traffic"]["mode"] == "AIS_STALE", health["traffic"]["mode"]
    assert all(t["freshness"] == "STALE" for t in tracks["tracks"])
    write("fabric_health_stale.json", health)
    write("world_ais_tracks_stale.json", tracks)

    client_module.reset_client()
    fusion_module.reset_engine()
    set_service(None)


if __name__ == "__main__":
    main()
