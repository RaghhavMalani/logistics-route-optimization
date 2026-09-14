"""Live AIS acceptance: prove, with a real key, that the observed path works.

    python scripts/verify_live_ais.py                 # up to 120 s of listening
    python scripts/verify_live_ais.py --wait 300      # a quiet box needs longer

Runs the whole observed-traffic path against the real AISStream socket and
prints one line per claim. Without AISSTREAM_API_KEY every claim is SKIP with
the reason, and the exit status is 0: a missing key is not a failure and it is
not a pass. There is no path here that manufactures a PASS -- no recording is
replayed, no timestamp is written, no message is invented. If the socket
delivers nothing in the window, the run says so and fails.

Claims, in order:

    key present             AISSTREAM_API_KEY is set (its value is never printed)
    licence                 the deployment's mode may use AISStream (DEMO / RESEARCH)
    connect                 the client opened a socket and subscribed
    observations            valid position reports arrived (count, message types)
    source timestamp        every accepted report carries the transponder's own
                            instant, within a stated skew of arrival
    LIVE_AIS                the traffic state machine moved to LIVE_AIS because
                            observations arrived, and says so
    track storage           the track store holds a track per observed hull
    observed world          the fusion engine offers observed hulls and the world
                            graph carries OBSERVED_AIS nodes with placement
                            confidence
    signal health           the fabric health surface reports the same, from the
                            socket, not the key
    anonymised summary      printed: counts, bounding box, message types; no MMSI,
                            no name, no callsign
    disconnect -> stale     after the socket is closed the state machine reads
                            AIS_STALE at (last good + stale window), never
                            SIMULATED_TRAFFIC

The stale claim advances the instant explicitly rather than waiting ten real
minutes; the printed line says so. Everything else is measured on the wall.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
KEY_ENV = "AISSTREAM_API_KEY"
#: The transponder's instant may not lead the arrival by more than this.
MAX_FUTURE_SKEW = timedelta(minutes=5)
#: Nor lag it by more than this and still count as a current observation.
MAX_LAG = timedelta(hours=6)


class Skip(Exception):
    pass


class Report:
    def __init__(self) -> None:
        self.rows: List[Tuple[str, str, str]] = []

    def check(self, claim: str, fn: Callable[[], Optional[str]]) -> bool:
        try:
            reason = fn()
        except Skip as skip:
            self.rows.append((SKIP, claim, str(skip)))
            return False
        except Exception as exc:  # noqa: BLE001 - a crash is a failed claim
            self.rows.append((FAIL, claim, f"{type(exc).__name__}: {exc}"))
            return False
        self.rows.append((FAIL if reason else PASS, claim, reason or ""))
        return not reason

    def skip_rest(self, claims: List[str], reason: str) -> None:
        for claim in claims:
            self.rows.append((SKIP, claim, reason))

    def print(self, out: Callable[[str], None] = print) -> int:
        width = max(len(c) for _, c, _ in self.rows)
        for status, claim, note in self.rows:
            out(f"[{status}] {claim.ljust(width)}  {note}")
        counts = {s: sum(1 for r in self.rows if r[0] == s) for s in (PASS, FAIL, SKIP)}
        out(f"\n{counts[PASS]} passed, {counts[FAIL]} failed, {counts[SKIP]} skipped")
        if counts[FAIL]:
            return 1
        return 0


def _anonymous(mmsi: str) -> str:
    """A stable, non-reversible handle for a transponder. Never the MMSI."""
    return "hull-" + hashlib.sha256(mmsi.encode("utf-8")).hexdigest()[:8]


CLAIMS = [
    "connect", "observations", "source timestamp", "LIVE_AIS", "track storage",
    "observed world", "signal health", "anonymised summary", "disconnect -> stale",
]


def main(argv: Optional[List[str]] = None, *, client_factory: Optional[Callable[..., Any]] = None,
         out: Callable[[str], None] = print) -> int:
    """Run the acceptance. ``client_factory`` exists so the utility's own logic can be
    tested against a scripted socket; the shipped command always dials the real one."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--wait", type=float, default=120.0, help="seconds to listen for observations")
    parser.add_argument("--min-observations", type=int, default=3)
    args = parser.parse_args(argv)

    report = Report()
    state: Dict[str, Any] = {}

    # ---------------------------------------------------------------- key --
    def key_present() -> Optional[str]:
        if not os.getenv(KEY_ENV):
            raise Skip(f"{KEY_ENV} is not set; nothing can be verified without a real key")
        return None
    if not report.check("key present", key_present):
        report.skip_rest(["licence"] + CLAIMS, f"no {KEY_ENV}")
        return report.print(out)

    # ------------------------------------------------------------ licence --
    from src.portwatch_os.fabric import SignalFabric, deployment_mode
    from src.portwatch_os.fabric.model import MODE_ENV

    mode = deployment_mode()

    def licence() -> Optional[str]:
        found = SignalFabric(mode=mode).resolve("ais")
        if found.product is None or found.product.product_id != "aisstream-websocket":
            rejected = "; ".join(f"{pid}: {why}" for pid, why in found.rejected)
            raise Skip(f"AISStream may not be used in {mode} ({MODE_ENV}); {rejected}")
        return None
    if not report.check("licence", licence):
        report.skip_rest(CLAIMS, f"AISStream is not eligible in {mode}")
        return report.print(out)

    # ------------------------------------------------------------ connect --
    from src.portwatch_os.fabric.ais.client import (
        AIS_STALE,
        AUTH_FAILED,
        LIVE_AIS,
        SIMULATED_TRAFFIC,
        AisStreamClient,
        DEFAULT_STALE_AFTER,
    )
    from src.portwatch_os.fabric.ais.messages import AisObservation
    from src.portwatch_os.fusion.engine import FusionEngine

    engine = FusionEngine()
    accepted: List[AisObservation] = []
    arrivals: List[datetime] = []

    def on_observation(observation: AisObservation) -> None:
        accepted.append(observation)
        arrivals.append(datetime.now(timezone.utc))
        engine.ingest_ais(observation)

    if client_factory is not None:
        client = client_factory(on_observation=on_observation)
        out("      (scripted socket: this run tests the utility, not a live feed)")
    else:
        client = AisStreamClient(on_observation=on_observation)
    state["client"] = client

    def connect() -> Optional[str]:
        client.start()
        deadline = time.monotonic() + min(30.0, args.wait)
        while time.monotonic() < deadline:
            if client.status.health == AUTH_FAILED:
                return f"the server refused the credential: {client.status.last_error}"
            if client.status.connected_at is not None:
                return None
            time.sleep(0.5)
        return f"no socket opened in 30 s (health {client.status.health}; {client.status.last_error})"
    if not report.check("connect", connect):
        client.stop()
        report.skip_rest(CLAIMS[1:], "not connected")
        return report.print(out)

    # ------------------------------------------------------- observations --
    def observations() -> Optional[str]:
        deadline = time.monotonic() + args.wait
        while time.monotonic() < deadline and len(accepted) < args.min_observations:
            if client.status.health == AUTH_FAILED:
                return f"the server refused the credential mid-session: {client.status.last_error}"
            time.sleep(1.0)
        if len(accepted) < args.min_observations:
            return (f"only {len(accepted)} valid observation(s) in {args.wait:.0f} s "
                    f"({client.status.messages_seen} messages seen, {client.status.messages_rejected} rejected); "
                    "not enough to claim a live feed")
        state["types"] = sorted({o.message_type for o in accepted})
        return None
    live = report.check("observations", observations)

    # --------------------------------------------------- source timestamp --
    def source_timestamp() -> Optional[str]:
        if not accepted:
            raise Skip("no observations")
        problems = []
        for observation, arrived in zip(accepted, arrivals):
            if observation.source_timestamp.tzinfo is None:
                problems.append(f"{_anonymous(observation.mmsi)}: naive timestamp")
                continue
            skew = observation.source_timestamp - arrived
            if skew > MAX_FUTURE_SKEW:
                problems.append(f"{_anonymous(observation.mmsi)}: transponder instant leads arrival by {skew}")
            elif -skew > MAX_LAG:
                problems.append(f"{_anonymous(observation.mmsi)}: transponder instant lags arrival by {-skew}")
        if problems:
            return "; ".join(problems[:3])
        return None
    report.check("source timestamp", source_timestamp)

    # ------------------------------------------------------------ LIVE_AIS --
    def live_ais() -> Optional[str]:
        if not live:
            raise Skip("no observations arrived")
        source = client.traffic_source(replay_chosen=True)
        if source["mode"] != LIVE_AIS:
            return f"traffic is {source['mode']} with observations on record: {source['statement']}"
        if not (source["health"] or {}).get("lastGoodObservationAt"):
            return "LIVE_AIS without lastGoodObservationAt"
        state["source"] = source
        return None
    report.check("LIVE_AIS", live_ais)

    # ------------------------------------------------------- track storage --
    def track_storage() -> Optional[str]:
        if not live:
            raise Skip("no observations arrived")
        tracks = client.store.tracks()
        hulls = {o.mmsi for o in accepted}
        stored = {t.mmsi for t in tracks}
        missing = hulls - stored
        if missing:
            return f"{len(missing)} observed hull(s) have no track"
        if not any(t.latest is not None for t in tracks):
            return "no track carries a latest observation"
        state["tracks"] = len(tracks)
        return None
    report.check("track storage", track_storage)

    # ------------------------------------------------------ observed world --
    def observed_world() -> Optional[str]:
        if not live:
            raise Skip("no observations arrived")
        from src.portwatch_os.world.build import build_world
        from src.portwatch_os.world.graph import VESSEL
        from src.portwatch_os.world.observed import observed_voyages

        placements = observed_voyages(engine)
        if not placements:
            return "the fusion engine offers no observed hull to the world"
        graph = build_world(voyages=[p.voyage for p in placements])
        nodes = [n for n in graph.nodes(kind=VESSEL) if n.attrs.get("source") == "OBSERVED_AIS"]
        if not nodes:
            return "no OBSERVED_AIS vessel node in the world graph"
        for node in nodes:
            if node.attrs.get("placement_confidence") is None:
                return f"{node.key} carries no placement confidence"
            if node.attrs.get("lane_code") and node.attrs.get("placement_confidence", 1.0) >= 1.0:
                return f"{node.key} is on a lane at confidence 1.0; a placement was inferred as fact"
        state["observed_nodes"] = len(nodes)
        return None
    report.check("observed world", observed_world)

    # ------------------------------------------------------- signal health --
    def signal_health() -> Optional[str]:
        if not live:
            raise Skip("no observations arrived")
        from src.portwatch_os.fabric import ais_mode

        health = ais_mode(licence_mode=mode, client=client)
        if health["mode"] != LIVE_AIS:
            return f"the fabric reads {health['mode']} while the client holds observations"
        if health.get("providerId") != "aisstream":
            return f"LIVE_AIS attributed to {health.get('providerId')}"
        return None
    report.check("signal health", signal_health)

    # -------------------------------------------------- anonymised summary --
    def summary() -> Optional[str]:
        if not accepted:
            raise Skip("no observations arrived")
        lats = [o.lat for o in accepted]
        lons = [o.lon for o in accepted]
        hulls = {o.mmsi for o in accepted}
        text = (f"{len(accepted)} observations from {len(hulls)} hulls; types {', '.join(state.get('types', []))}; "
                f"box lat {min(lats):.1f}..{max(lats):.1f} lon {min(lons):.1f}..{max(lons):.1f}; "
                f"first three hulls {', '.join(_anonymous(m) for m in sorted(hulls)[:3])}")
        for observation in accepted:
            for field in (observation.mmsi, observation.name, observation.callsign, observation.imo):
                if field and str(field) in text:
                    return f"the summary would have carried an identity field"
        out(f"      summary: {text}")
        return None
    report.check("anonymised summary", summary)

    # --------------------------------------------------- disconnect -> stale --
    def disconnect_stale() -> Optional[str]:
        if not live:
            raise Skip("no observations arrived")
        client.stop()
        last_good = client.status.last_good_observation_at
        if last_good is None:
            return "no last good observation to age"
        later = last_good + DEFAULT_STALE_AFTER + timedelta(seconds=1)
        source = client.traffic_source(now=later, replay_chosen=True)
        if source["mode"] == SIMULATED_TRAFFIC:
            return "a lapsed live feed fell through to SIMULATED_TRAFFIC"
        if source["mode"] != AIS_STALE:
            return f"at last good + {DEFAULT_STALE_AFTER} the state is {source['mode']}, not AIS_STALE"
        out(f"      (the instant was advanced explicitly to {later.isoformat(timespec='seconds')}; "
            f"a real ten-minute wait was not performed)")
        return None
    report.check("disconnect -> stale", disconnect_stale)

    client.stop()
    return report.print(out)


if __name__ == "__main__":
    raise SystemExit(main())
