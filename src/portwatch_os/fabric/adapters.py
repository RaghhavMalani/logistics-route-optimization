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
from src.portwatch_os.clock import world_now

# --------------------------------------------------------------------------
# AIS modes
# --------------------------------------------------------------------------

#: Positions observed by a real AIS receiver network, arriving now.
LIVE_AIS = "LIVE_AIS"
#: Observed positions that have stopped arriving. Still drawn, and said to be old.
AIS_STALE = "AIS_STALE"
#: The deterministic replay. Labelled as such on every surface it reaches.
SIMULATED_TRAFFIC = "SIMULATED_TRAFFIC"
#: No traffic source this mode may legally use, or a live one that has lapsed.
AIS_UNAVAILABLE = "UNAVAILABLE"

AIS_MODES: Tuple[str, ...] = (LIVE_AIS, AIS_STALE, SIMULATED_TRAFFIC, AIS_UNAVAILABLE)


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
        moment = now or world_now()
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

    Three gates, and they are different gates. The licence gate is the
    catalogue's: AISStream publishes no terms for its data service, so its
    commercial standing is REQUIRES_REVIEW and a COMMERCIAL or GOVERNMENT
    deployment cannot use it, because a permission nobody has verified is not a
    permission. The configuration gate is the key. The third gate is the one
    that matters most and is the easiest to forget: the socket has to have
    actually delivered a valid observation. A configured, connected client that
    has received nothing is not a source of positions yet, and this adapter
    says so.

    When any gate is shut this adapter yields nothing. It specifically does not
    fall back to the replay, because the replay reaching the screen through an
    adapter called "AISStream" is how a simulated position ends up labelled as
    observed.

    What it reads, when it reads, is the track store the websocket client
    feeds: one observation per transponder, newest first, each carrying the
    transponder's own timestamp so freshness is the reading's age and not the
    age of this call.
    """

    provider_id = "aisstream"
    capability = AIS
    coverage = "Indian Ocean subscription box; receiver density varies"
    stale_after_seconds = 600.0

    #: The server reads this. It is never sent to a browser.
    ENV_KEY = "AISSTREAM_API_KEY"

    #: The product this adapter serves, so eligibility comes from the
    #: catalogue's verified policy rather than a sentence written here.
    product_id = "aisstream-websocket"

    def __init__(self, *, licence_mode: str = "RESEARCH", client: Any = None) -> None:
        super().__init__(licence_mode=licence_mode)
        # Injectable so the adapter can be exercised against a scripted client;
        # otherwise the process-wide one.
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from src.portwatch_os.fabric.ais.client import get_client

            self._client = get_client()
        return self._client

    def licence_gate(self) -> Optional[Availability]:
        """The catalogue's verdict, or None when the mode may use the product."""
        from src.portwatch_os.fabric.registry import get_fabric

        product = get_fabric(self.licence_mode).product(self.product_id)
        if product is None:
            return None
        permitted, reason = product.policy.permits(self.licence_mode)
        if permitted:
            return None
        return Availability(
            UNAVAILABLE,
            reason=f"{product.name}: {reason}",
            needs=(
                "written confirmation of AISStream's terms, or a commercial "
                "AIS contract (Spire, Kpler)",
            ),
        )

    def availability(self) -> Availability:
        from src.portwatch_os.fabric.ais.client import AUTH_FAILED, LIVE, RATE_LIMITED

        barred = self.licence_gate()
        if barred is not None:
            return barred
        client = self.client
        if not client.configured:
            return Availability(
                CONFIGURABLE,
                reason=(
                    "no AISStream key is configured, so this deployment has no "
                    "observed AIS. Traffic shown is the deterministic replay and "
                    "is labelled as simulated."
                ),
                needs=(self.ENV_KEY,),
            )
        status = client.status
        if status.health == AUTH_FAILED:
            return Availability(
                UNAVAILABLE,
                reason=f"AISStream refused the configured credential: {status.last_error}",
                needs=("a valid " + self.ENV_KEY,),
            )
        if status.health == RATE_LIMITED:
            return Availability(
                UNAVAILABLE,
                reason=f"the AISStream socket is rate limited: {status.last_error}",
            )
        if status.last_good_observation_at is None:
            return Availability(
                UNAVAILABLE,
                reason=(
                    f"a key is configured and the socket is {status.health}, but "
                    "no valid observation has arrived yet, so there are no observed "
                    "positions to show. The replay is not being shown in their place."
                ),
                needs=("the first valid message from AISStream",),
            )
        detail = "delivering" if status.health == LIVE else status.health.lower()
        return Availability(
            AVAILABLE,
            reason=(
                f"observed AIS from AISStream; socket {detail}, "
                f"{status.messages_consumed} observations consumed"
            ),
        )

    def _read(self, *, now: datetime):
        tracks = sorted(
            (t for t in self.client.store.tracks() if t.latest is not None),
            key=lambda t: t.latest.source_timestamp,
            reverse=True,
        )
        rows = []
        for track in tracks:
            head = track.latest
            rows.append((
                track.to_dict(now=now, history=0),
                head.source_timestamp,
                {
                    "source_time_known": bool(head.provenance.get("source_time_known", True)),
                    "message_type": head.message_type,
                    "raw_ref": head.raw_ref,
                    "positions_held": len(track.positions),
                },
            ))
        return rows


def ais_mode(
    *,
    licence_mode: str = "RESEARCH",
    client: Any = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """What kind of traffic this deployment is actually showing.

    The one question the traffic layer must never get wrong. The licence gate
    is answered first, from the catalogue, so a COMMERCIAL deployment with a key
    is UNAVAILABLE and not LIVE. Everything after that is answered by the
    client's own state machine from evidence: LIVE_AIS because observations are
    arriving, AIS_STALE because they stopped, SIMULATED_TRAFFIC only when the
    replay was the chosen source, and never the replay by falling through.
    """
    adapter = AisStreamAdapter(licence_mode=licence_mode, client=client)
    barred = adapter.licence_gate()
    if barred is not None:
        return {
            "mode": AIS_UNAVAILABLE,
            "providerId": None,
            "statement": "No traffic source this deployment may legally use is configured.",
            "availability": barred.to_dict(),
            "health": None,
            "vessels": None,
        }
    availability = adapter.availability()
    source = adapter.client.traffic_source(
        now=now,
        replay_chosen=licence_mode in ("RESEARCH", "DEMO"),
    )
    source["availability"] = availability.to_dict()
    return source


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

    @property
    def product_id(self) -> str:
        """The subscription when a key is configured; the free tier otherwise."""
        return "open-meteo-customer" if os.getenv("OPEN_METEO_API_KEY") else "open-meteo-free"

    def licence_gate(self) -> Optional[Availability]:
        """The catalogue's verdict on the product the artefact was fetched with.

        The artefact on disk was produced by the free host unless a key was
        configured when the pipeline ran, and a COMMERCIAL deployment may not
        use what the free host produced however long ago it was fetched.
        """
        from src.portwatch_os.fabric.registry import get_fabric

        product = get_fabric(self.licence_mode).product(self.product_id)
        if product is None:
            return None
        permitted, reason = product.policy.permits(self.licence_mode)
        if permitted:
            return None
        return Availability(
            UNAVAILABLE,
            reason=f"{product.name}: {reason}",
            needs=("OPEN_METEO_API_KEY for the Open-Meteo API subscription",),
        )

    def availability(self) -> Availability:
        barred = self.licence_gate()
        if barred is not None:
            return barred
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
    product_id = "gdelt-events"
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
    # The marine adapter lives in its own module (it carries a service and a
    # cache); imported here rather than at the top to keep the import acyclic.
    from src.portwatch_os.fabric.marine import OpenMeteoMarineAdapter

    return [cls(licence_mode=licence_mode) for cls in (*ADAPTERS, OpenMeteoMarineAdapter)]


__all__ = [
    "ADAPTERS",
    "AIS_MODES",
    "AIS_STALE",
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
