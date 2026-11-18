"""Accept signed Open-Meteo originals from an opt-in weather relay."""

from datetime import datetime, timezone
import hashlib
import hmac

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from src.portwatch_os.clock import wall_now
from src.portwatch_os.freshness.free_research import current_weather_eligibility
from src.portwatch_os.freshness.write_health import is_storage_error, record_write
from src.portwatch_os.intelligence import current_environment as weather, surface_relay
from src.portwatch_os.intelligence.surface_transport import MAX_RESPONSE_BYTES
from src.utils.port_registry import PORTS


router = APIRouter()


def store(group, sent_at, body):
    now = wall_now()
    ports = PORTS[group::weather.SURFACE_GROUPS]
    digest = hashlib.sha256(body).hexdigest()
    with weather.LOCK:
        previous = {port.locode: weather.read("surface", port, at=now) for port in ports}
        if all(row.get("relayFetchedAt") == sent_at.isoformat() and row.get("responseSha256") == digest
               for row in previous.values()):
            return {locode: row["snapshotId"] for locode, row in previous.items()}
        for row in previous.values():
            if row.get("relayFetchedAt") and (
                weather.instant(row["relayFetchedAt"]) > sent_at
                or (row["relayFetchedAt"] == sent_at.isoformat() and row.get("responseSha256") != digest)
            ):
                raise HTTPException(409, "A newer relay receipt is already present")
        try:
            rows = weather.publish_surface_batch(ports, body, now, relay_fetched_at=sent_at)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
            raise HTTPException(422, "Open-Meteo original failed source validation") from error
        except OSError as error:
            if is_storage_error(error):
                record_write(weather.SURFACE_BATCH_ARTIFACT, ok=False)
            raise
    return {locode: row["snapshotId"] for locode, row in rows.items()}


@router.post(surface_relay.CALLBACK_PATH.removeprefix("/api"), include_in_schema=False)
async def accept(request: Request):
    config = surface_relay.relay_settings()
    if not config or current_weather_eligibility():
        raise HTTPException(404, "Relay unavailable")
    group = request.headers.get("X-Weather-Group", "")
    timestamp = request.headers.get("X-Weather-Timestamp", "")
    provided = request.headers.get("X-Weather-Signature", "")
    if (group not in {str(index) for index in range(weather.SURFACE_GROUPS)}
            or len(timestamp) != 10 or not timestamp.isascii() or not timestamp.isdecimal()
            or len(provided) != 64 or not provided.isascii()):
        raise HTTPException(401, "Invalid relay signature")
    now = wall_now()
    sent_at = datetime.fromtimestamp(int(timestamp), timezone.utc)
    if not -30 <= (now - sent_at).total_seconds() <= surface_relay.MAX_SKEW_SECONDS:
        raise HTTPException(401, "Expired relay signature")
    body = bytearray()
    async for data in request.stream():
        if len(body) + len(data) > MAX_RESPONSE_BYTES:
            raise HTTPException(413, "Weather response exceeds relay limit")
        body.extend(data)
    original = bytes(body)
    expected = surface_relay.signature(config[1], "receipt", group, timestamp, original)
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(401, "Invalid relay signature")
    return {"snapshots": await run_in_threadpool(store, int(group), sent_at, original)}
