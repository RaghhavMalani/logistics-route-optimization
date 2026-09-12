"""Adapters: the seam between a provider and this world.

An adapter does three things and refuses to do a fourth. It reports whether it
can run at all in the current deployment, it fetches, and it normalises what
came back into :class:`~src.portwatch_os.fabric.observation.Observation`. What
it must never do is invent a reading when it cannot run.

That last point is the whole reason this file has a shape rather than being a
handful of fetch functions. The tempting failure is an adapter that, finding no
API key, quietly returns the demo data instead -- the product keeps working, the
screen keeps saying LIVE, and nobody discovers until a customer asks where a
position came from. So `availability()` is separate from `fetch()`, and an
adapter that is not configured says exactly that.

Secrets live here, on the server. A credential must never reach the browser,
which is why an adapter reads its key from the environment and the API exposes
provider *status* rather than provider configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from src.portwatch_os.fabric.model import (
    AIS,
    AVAILABLE,
    CONFIGURABLE,
    UNAVAILABLE,
)
from src.portwatch_os.fabric.observation import Observation, observe

# --------------------------------------------------------------------------
# AIS modes
# --------------------------------------------------------------------------

#: Positions observed by a real AIS receiver network.
LIVE_AIS = "LIVE_AIS"
#: The deterministic replay. Labelled as such on every surface it reaches.
SIMULATED_TRAFFIC = "SIMULATED_TRAFFIC"
#: No traffic source this mode may legally use. The honest third answer.
AIS_UNAVAILABLE = "UNAVAILABLE"

AIS_MODES: Tuple[str, ...] = (LIVE_AIS, SIMULATED_TRAFFIC, AIS_UNAVAILABLE)


@dataclass(frozen=True)
class Availability:
    """Whether an adapter can run here, and what is missing when it cannot."""

    status: str
    reason: str = ""
    #: The environment variable or configuration this adapter is waiting for.
    needs: Tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.status == AVAILABLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "needs": list(self.needs),
        }


class Adapter(Protocol):
    """What every provider integration must offer."""

    provider_id: str
    capability: str

    def availability(self) -> Availability: ...

    def fetch(self, *, now: Optional[datetime] = None) -> List[Observation]: ...


class BaseAdapter:
    """Shared behaviour. Subclasses implement `availability` and `_read`."""

    provider_id: str = ""
    capability: str = ""
    coverage: str = "unspecified"
    #: How long a reading from this source stays worth using, in seconds.
    stale_after_seconds: float = 3600.0
    #: Assumed validity where the provider states none.
    valid_for_hours: Optional[float] = None

    def __init__(self, *, licence_mode: str = "RESEARCH") -> None:
        self.licence_mode = licence_mode

    # -- contract --------------------------------------------------------
    def availability(self) -> Availability:  # pragma: no cover - abstract
        raise NotImplementedError

    def _read(self, *, now: datetime) -> Sequence[Tuple[Any, datetime, Dict[str, Any]]]:
        """Return `(value, source_timestamp, provenance)` triples."""
        raise NotImplementedError  # pragma: no cover - abstract

    def fetch(self, *, now: Optional[datetime] = None) -> List[Observation]:
        """Read and normalise, or return nothing.

        An unavailable adapter returns an empty list rather than raising and
        rather than substituting. The caller learns that from `availability()`,
        which is a different question and has a different answer.
        """
        moment = now or datetime.now(timezone.utc)
        if not self.availability().ready:
            return []
        return [
            observe(
                provider_id=self.provider_id,
                capability=self.capability,
                value=value,
                source_timestamp=source_timestamp,
                valid_for_hours=self.valid_for_hours,
                coverage=self.coverage,
                licence_mode=self.licence_mode,
                now=moment,
                stale_after_seconds=self.stale_after_seconds,
                source_time_known=self._split_known(provenance)[0],
                **self._split_known(provenance)[1],
            )
            for value, source_timestamp, provenance in self._read(now=moment)
        ]

    @staticmethod
    def _split_known(provenance):
        """Peel the timestamp-confidence marker off an adapter's provenance."""
        rest = dict(provenance)
        known = bool(rest.pop("source_time_known", True))
        return known, rest


# --------------------------------------------------------------------------
# AIS
# --------------------------------------------------------------------------


class AisStreamAdapter(BaseAdapter):
    """AISStream: observed positions, when a key is configured and the mode allows.

    Two gates, and they are different gates. The licence gate is the catalogue's:
    AISStream publishes no terms for its data service, so its commercial
    standing is REQUIRES_REVIEW and a COMMERCIAL or GOVERNMENT deployment cannot
    use it however well configured it is -- not because it is prohibited, but
    because a permission nobody has verified is not a permission. The
    configuration gate is this one: a RESEARCH or DEMO deployment may use it and
    still has to have a key.

    When either gate is shut this adapter yields nothing. It specifically does
    not fall back to the replay, because the replay reaching the screen through
    an adapter called "AISStream" is how a simulated position ends up labelled
    as observed.

    The websocket client itself is not implemented here. What exists is the
    seam, the gating and the status, so that wiring a socket is a contained
    change rather than a redesign -- and so the product tells the truth about
    not having one today.
    """

    provider_id = "aisstream"
    capability = AIS
    coverage = "global, varying with receiver density"
    stale_after_seconds = 300.0

    #: The server reads this. It is never sent to a browser.
    ENV_KEY = "AISSTREAM_API_KEY"

    #: The product this adapter serves, so eligibility comes from the
    #: catalogue's verified policy rather than a sentence written here.
    product_id = "aisstream-websocket"

    def availability(self) -> Availability:
        from src.portwatch_os.fabric.registry import get_fabric

        product = get_fabric(self.licence_mode).product(self.product_id)
        if product is not None:
            permitted, reason = product.policy.permits(self.licence_mode)
            if not permitted:
                return Availability(
                    UNAVAILABLE,
                    reason=f"{product.name}: {reason}",
                    needs=(
                        "written confirmation of AISStream's terms, or a commercial "
                        "AIS contract (Spire, Kpler)",
                    ),
                )
        if not os.getenv(self.ENV_KEY):
            return Availability(
                CONFIGURABLE,
                reason=(
                    "no AISStream key is configured, so this deployment has no "
                    "observed AIS. Traffic shown is the deterministic replay and "
                    "is labelled as simulated."
                ),
                needs=(self.ENV_KEY,),
            )
        return Availability(
            UNAVAILABLE,
            reason=(
                "a key is configured but the AISStream websocket client is not "
                "implemented in this build, so no observed positions are ingested"
            ),
            needs=("the AISStream websocket client",),
        )

    def _read(self, *, now: datetime):  # pragma: no cover - never ready yet
        return []


def ais_mode(*, licence_mode: str = "RESEARCH") -> Dict[str, Any]:
    """What kind of traffic this deployment is actually showing.

    The one question the traffic layer must never get wrong. It is answered from
    the adapter's availability rather than from a flag somebody remembered to
    set, so a configured-but-unimplemented socket cannot report LIVE.
    """
    adapter = AisStreamAdapter(licence_mode=licence_mode)
    availability = adapter.availability()
    if availability.ready:
        return {
            "mode": LIVE_AIS,
            "providerId": adapter.provider_id,
            "statement": "Positions are observed AIS.",
            "availability": availability.to_dict(),
        }
    if licence_mode in ("RESEARCH", "DEMO"):
        return {
            "mode": SIMULATED_TRAFFIC,
            "providerId": "ais-replay",
            "statement": (
                "Positions are a deterministic replay, not observed AIS, and are "
                "labelled as simulated wherever they are drawn."
            ),
            "availability": availability.to_dict(),
        }
    return {
        "mode": AIS_UNAVAILABLE,
        "providerId": None,
        "statement": (
            "No traffic source this deployment may legally use is configured."
        ),
        "availability": availability.to_dict(),
    }


# --------------------------------------------------------------------------
# weather
# --------------------------------------------------------------------------


class OpenMeteoAdapter(BaseAdapter):
    """Open-Meteo, read through the artefact the pipeline already exports.

    This deployment does not call Open-Meteo from the request path -- the
    forecast pipeline fetches, and the API serves what it wrote. The adapter
    therefore reports on that artefact rather than pretending to be a live
    client, and its freshness is the artefact's, which is the number an operator
    actually needs.
    """

    provider_id = "open-meteo"
    capability = "weather"
    coverage = "global"
    stale_after_seconds = 6 * 3600.0

    def availability(self) -> Availability:
        try:
            from backend.app.services import cache_service as cache

            status = cache.get_live_status()
        except Exception as exc:  # noqa: BLE001 - a missing cache is a status
            return Availability(
                CONFIGURABLE,
                reason=f"the forecast artefact could not be read: {exc}",
                needs=("a pipeline run: python -m src.pipeline",),
            )
        if not isinstance(status, dict) or not status.get("forecastOrigin"):
            return Availability(
                CONFIGURABLE,
                reason="the forecast artefact carries no origin",
                needs=("a pipeline run: python -m src.pipeline",),
            )
        return Availability(AVAILABLE)

    def _read(self, *, now: datetime):
        from backend.app.services import cache_service as cache

        status = cache.get_live_status()
        origin = str(status.get("forecastOrigin"))
        try:
            issued = datetime.fromisoformat(origin.replace("Z", "+00:00"))
        except ValueError:
            issued = now
        if issued.tzinfo is None:
            issued = issued.replace(tzinfo=timezone.utc)
        return [(status, issued, {"artefact": "live_status", "origin": origin})]


# --------------------------------------------------------------------------
# events
# --------------------------------------------------------------------------


class GdeltAdapter(BaseAdapter):
    """GDELT, through the news bundle the ingest pipeline writes.

    Same shape as the weather adapter and for the same reason: the request path
    reads an artefact, so the honest freshness is the artefact's age rather than
    the age of the HTTP call that just read a file.
    """

    provider_id = "gdelt"
    capability = "events"
    coverage = "global news"
    stale_after_seconds = 3 * 3600.0

    def availability(self) -> Availability:
        try:
            from backend.app.services import cache_service as cache

            cache.get_news_bundle()
        except Exception as exc:  # noqa: BLE001 - a missing bundle is a status
            return Availability(
                CONFIGURABLE,
                reason=f"the news bundle could not be read: {exc}",
                needs=("a pipeline run that exports the news bundle",),
            )
        return Availability(AVAILABLE)

    def _read(self, *, now: datetime):
        from backend.app.services import cache_service as cache

        bundle = cache.get_news_bundle()
        items = bundle.get("events", []) if isinstance(bundle, dict) else []

        # The bundle carries no time of its own. Standing `now` in for it would
        # report an artefact of unknown age as LIVE, so fall back to when the
        # file was written and say that is what the number is.
        stamp = bundle.get("fetchedAt") if isinstance(bundle, dict) else None
        known = True
        fetched = None
        if stamp:
            try:
                fetched = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            except ValueError:
                fetched = None
        basis = "provider fetchedAt"
        if fetched is None:
            written = _artefact_written(getattr(cache, "NEWS_CACHE", None))
            if written is not None:
                fetched, basis = written, "artefact write time"
            else:
                fetched, known, basis = now, False, "unknown"
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return [(
            items,
            fetched,
            {
                "artefact": "news_bundle",
                "events": len(items),
                "timestamp_basis": basis,
                "source_time_known": known,
            },
        )]


def _artefact_written(path):
    """When an artefact file was last written, where that is knowable."""
    try:
        return datetime.fromtimestamp(os.path.getmtime(str(path)), tz=timezone.utc)
    except (OSError, TypeError, ValueError):
        return None


#: Adapters this build actually ships. A provider in the registry with no entry
#: here is one nothing reads yet, which is why the registry marks it PLANNED.
ADAPTERS: Tuple[type, ...] = (
    AisStreamAdapter,
    OpenMeteoAdapter,
    GdeltAdapter,
)


def build_adapters(*, licence_mode: str = "RESEARCH") -> List[BaseAdapter]:
    return [cls(licence_mode=licence_mode) for cls in ADAPTERS]


__all__ = [
    "ADAPTERS",
    "AIS_MODES",
    "AIS_UNAVAILABLE",
    "Adapter",
    "AisStreamAdapter",
    "Availability",
    "BaseAdapter",
    "GdeltAdapter",
    "LIVE_AIS",
    "OpenMeteoAdapter",
    "SIMULATED_TRAFFIC",
    "ais_mode",
    "build_adapters",
]
