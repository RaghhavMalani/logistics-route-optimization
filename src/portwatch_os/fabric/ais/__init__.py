"""Observed AIS: the socket, the store, and the two state machines.

See :mod:`~src.portwatch_os.fabric.ais.client` for the rule that shapes all of
it -- the picture is LIVE_AIS because messages arrived, never because a key
exists, and a failed live provider never becomes the replay by falling through.
"""

from src.portwatch_os.fabric.ais.client import (
    AIS_STALE,
    AUTH_FAILED,
    AisStreamClient,
    CONNECTING,
    DEGRADED,
    DISCONNECTED,
    HEALTH_STATES,
    LIVE,
    LIVE_AIS,
    ProviderStatus,
    RATE_LIMITED,
    SIMULATED_TRAFFIC,
    SOURCE_STATES,
    STALE,
    UNAVAILABLE,
    get_client,
)
from src.portwatch_os.fabric.ais.recorder import ObservationRecorder, replay
from src.portwatch_os.fabric.ais.messages import (
    AisMessageError,
    AisObservation,
    CONSUMED_TYPES,
    normalise,
)
from src.portwatch_os.fabric.ais.tracks import IngestOutcome, Track, TrackStore

__all__ = [
    "AIS_STALE", "AUTH_FAILED", "AisMessageError", "AisObservation",
    "AisStreamClient", "CONNECTING", "CONSUMED_TYPES", "DEGRADED", "DISCONNECTED",
    "HEALTH_STATES", "IngestOutcome", "LIVE", "LIVE_AIS", "ProviderStatus",
    "RATE_LIMITED", "SIMULATED_TRAFFIC", "SOURCE_STATES", "STALE", "Track",
    "TrackStore", "UNAVAILABLE", "get_client", "normalise",
]
