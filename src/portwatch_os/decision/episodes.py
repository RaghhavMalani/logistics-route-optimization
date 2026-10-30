"""Server-owned call identities, independent of ETA edits and evidence vintages."""
import hashlib
import secrets
from datetime import timedelta

from src.portwatch_os.clock import wall_now, world_now


def new_episode(scoped, vessel):
    # wall-clock: call identity creation is an actual operator audit receipt, not the voyage target.
    created_at = wall_now().isoformat()
    return {"contractVersion": "operational-episode-v1", "id": "call-" + secrets.token_hex(16),
            "voyageLegId": "leg-" + secrets.token_hex(16), "vesselId": vessel["id"],
            "portCode": vessel["portCode"], "namespace": hashlib.sha256(str(scoped.root).encode()).hexdigest(),
            "createdAt": created_at, "source": "OPERATOR_DECLARED_DEMO_CALL"}


def ensure_episode(scoped, vessel):
    existing = vessel.get("operationalEpisode")
    if existing:
        return existing
    proposed = new_episode(scoped, vessel)
    def save(world):
        row = next(v for v in world["fleet"] if v["id"] == vessel["id"])
        episode = row.setdefault("operationalEpisode", proposed)
        world.setdefault("operationalEpisodes", {})[episode["id"]] = episode
        return episode
    result = scoped.save_world(save)
    vessel["operationalEpisode"] = result
    return result


def begin_call(scoped, vessel, requested_arrival, request_id):
    from src.portwatch_os.intelligence.current_environment import instant
    if not isinstance(request_id, str) or not 8 <= len(request_id) <= 100:
        raise ValueError('A stable requestId is required for safe new-call retries')
    at = instant(requested_arrival)
    query_at = world_now()
    episode = new_episode(scoped, vessel)
    def save(world):
        intents = world.setdefault('operationalCallIntents', {})
        signature = {'vesselId':vessel['id'], 'requestedArrival':at.isoformat()}
        old = intents.get(request_id)
        if old:
            if old['input'] != signature:
                raise ValueError('New-call requestId was already used with different inputs')
            return old['result']
        if not query_at < at <= query_at + timedelta(days=365):
            raise ValueError('New call arrival must be future and within one year')
        row = next(v for v in world["fleet"] if v["id"] == vessel["id"])
        row["operationalEpisode"] = episode
        row["etaHours"] = (at-instant(world["epoch"])).total_seconds()/3600
        row.pop("declaredPassage", None)
        row.pop("declaredPassages", None)
        row.pop("possibleAssetIds", None)
        world.setdefault("operationalEpisodes", {})[episode["id"]] = episode
        if (world.get("terminalProposal") or {}).get("vesselId") == vessel["id"]:
            for key in ("terminalProposal", "currentArrivalReview", "currentArrivalOutcome"):
                world.pop(key, None)
        result = {"episode": episode, "requestedArrival": at.isoformat()}
        intents[request_id] = {'input':signature, 'result':result}
        return result
    return scoped.save_world(save)
