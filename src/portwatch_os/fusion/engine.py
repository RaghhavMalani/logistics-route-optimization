"""The fusion engine: deciding, with evidence, which claims are about one hull.

Two strong keys and one that is not a key at all.

**IMO** is the hull's number. It is painted on the ship and survives a sale, a
reflag and a rename. Two claims with the same IMO are about the same hull, full
stop, and an IMO claim outranks an MMSI claim when they disagree.

**MMSI** is the transponder's number. It is strong, because a transponder is
bolted to one hull at a time -- but it is reassigned when a ship reflags, and
it is occasionally programmed wrong. So MMSI links carry two safeguards: a
transponder that starts reporting a *different* IMO from the hull it is linked
to does not move on the first message, because one static report with a typo
must not re-identify a ship; and a transponder silent for longer than the
reuse window that comes back under a different name is treated as possibly a
new hull rather than assumed to be the old one.

**Name** is a string a crew member typed. It is never a key. Two vessels with
the same name are two vessels, and what the engine produces from a name match
is a candidate for a person to look at, not a link.

Everything the engine decides is written down: the link, its strength, the
assertions it rests on and the reason in words. Everything it declines to
decide is also written down, as a conflict or a candidate. Nothing is thrown
away, so a wrong merge is always unpickable.
"""

from __future__ import annotations

import itertools
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.portwatch_os.fabric.ais.messages import (
    AisObservation,
    POSITION_REPORT,
    SHIP_STATIC_DATA,
    STANDARD_CLASS_B,
)
from src.portwatch_os.fusion.model import (
    ATTR_CALLSIGN,
    ATTR_DESTINATION,
    ATTR_ETA,
    ATTR_IMO,
    ATTR_MMSI,
    ATTR_NAME,
    ATTR_NAV_STATUS,
    ATTR_POSITION,
    AttributeValue,
    Candidate,
    CanonicalVessel,
    Conflict,
    EntityAssertion,
    FLEET_ID,
    FLEET_REGISTRY,
    IMO,
    IdentityLink,
    MMSI,
    NAME,
    OBSERVED_AIS,
    SIMULATED_TRAFFIC,
    STRONG,
)
from src.portwatch_os.clock import world_now

#: An MMSI not heard from for this long, returning under a different name,
#: is treated as possibly reassigned rather than assumed the same hull.
DEFAULT_MMSI_REUSE_WINDOW = timedelta(days=30)
#: Consistent static reports naming a *different* IMO before a transponder is
#: moved off the hull it was linked to. One report with a typo must not
#: re-identify a ship.
DEFAULT_IMO_CLAIMS_BEFORE_MOVE = 2

#: Which source kind wins for each attribute when two disagree. The registry
#: knows a hull's particulars better than a field a crew member typed; the
#: transponder knows where the hull is better than any registry.
PRECEDENCE: Dict[str, Tuple[str, ...]] = {
    ATTR_NAME: (FLEET_REGISTRY, OBSERVED_AIS, SIMULATED_TRAFFIC),
    ATTR_IMO: (FLEET_REGISTRY, OBSERVED_AIS, SIMULATED_TRAFFIC),
    ATTR_CALLSIGN: (FLEET_REGISTRY, OBSERVED_AIS, SIMULATED_TRAFFIC),
    ATTR_POSITION: (OBSERVED_AIS, FLEET_REGISTRY, SIMULATED_TRAFFIC),
    ATTR_NAV_STATUS: (OBSERVED_AIS, FLEET_REGISTRY, SIMULATED_TRAFFIC),
    ATTR_DESTINATION: (OBSERVED_AIS, FLEET_REGISTRY, SIMULATED_TRAFFIC),
    ATTR_ETA: (OBSERVED_AIS, FLEET_REGISTRY, SIMULATED_TRAFFIC),
    ATTR_MMSI: (OBSERVED_AIS, FLEET_REGISTRY, SIMULATED_TRAFFIC),
}

#: How much an AIS static field is trusted as a statement about identity. It
#: is typed by hand, and the literature on AIS data quality is not kind.
AIS_STATIC_CONFIDENCE = 0.8
AIS_POSITION_CONFIDENCE = 0.95
REGISTRY_CONFIDENCE = 0.9


def _normalise_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    text = re.sub(r"[^A-Z0-9 ]", " ", name.upper())
    text = re.sub(r"\b(MV|MT|MS|M/V|M/T)\b", " ", text)
    return " ".join(text.split()) or None


class FusionOutcome:
    """What the engine did with one batch of claims, in words."""

    def __init__(self, canonical: CanonicalVessel) -> None:
        self.canonical = canonical
        self.created = False
        self.links_added: List[IdentityLink] = []
        self.links_retracted: List[IdentityLink] = []
        self.conflicts: List[Conflict] = []
        self.candidates: List[Candidate] = []
        self.merged_from: Optional[str] = None
        self.notes: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonicalId": self.canonical.canonical_id,
            "created": self.created,
            "linksAdded": [l.to_dict() for l in self.links_added],
            "linksRetracted": [l.to_dict() for l in self.links_retracted],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "candidates": [c.to_dict() for c in self.candidates],
            "mergedFrom": self.merged_from,
            "notes": list(self.notes),
        }


class FusionEngine:
    """Holds the assertions, the links, and the canonical vessels they imply."""

    def __init__(
        self,
        *,
        mmsi_reuse_window: timedelta = DEFAULT_MMSI_REUSE_WINDOW,
        imo_claims_before_move: int = DEFAULT_IMO_CLAIMS_BEFORE_MOVE,
    ) -> None:
        self.mmsi_reuse_window = mmsi_reuse_window
        self.imo_claims_before_move = imo_claims_before_move
        self._vessels: Dict[str, CanonicalVessel] = {}
        #: Active links by key. A retracted link leaves this index.
        self._by_key: Dict[Tuple[str, str], str] = {}
        #: Name index for candidates only. Never consulted for a link.
        self._by_name: Dict[str, List[str]] = {}
        #: Repeated "my IMO is X" claims from a transponder linked elsewhere.
        self._imo_claims: Dict[Tuple[str, str], int] = {}
        self._lock = threading.RLock()
        self._ids = itertools.count(1)
        self._assertion_ids = itertools.count(1)
        self._link_ids = itertools.count(1)

    # -- identifiers -----------------------------------------------------
    def _new_canonical(self, now: datetime) -> CanonicalVessel:
        vessel = CanonicalVessel(canonical_id=f"hull-{next(self._ids):06d}", created_at=now)
        self._vessels[vessel.canonical_id] = vessel
        return vessel

    def _assertion(self, **fields: Any) -> EntityAssertion:
        return EntityAssertion(assertion_id=f"a-{next(self._assertion_ids):08d}", **fields)

    def _link(
        self,
        vessel: CanonicalVessel,
        kind: str,
        value: str,
        *,
        strength: str,
        evidence: Iterable[str],
        reason: str,
        now: datetime,
        outcome: FusionOutcome,
    ) -> IdentityLink:
        link = IdentityLink(
            link_id=f"l-{next(self._link_ids):06d}",
            canonical_id=vessel.canonical_id,
            key_kind=kind,
            key_value=value,
            strength=strength,
            established_at=now,
            evidence=list(evidence),
            reason=reason,
        )
        vessel.links.append(link)
        if strength == STRONG:
            self._by_key[(kind, value)] = vessel.canonical_id
            if kind == IMO:
                vessel.imo = value
            elif kind == MMSI and value not in vessel.mmsis:
                vessel.mmsis.append(value)
            elif kind == FLEET_ID and value not in vessel.fleet_ids:
                vessel.fleet_ids.append(value)
        outcome.links_added.append(link)
        return link

    def _retract(
        self,
        vessel: CanonicalVessel,
        kind: str,
        value: str,
        *,
        reason: str,
        now: datetime,
        outcome: FusionOutcome,
    ) -> None:
        for link in vessel.links:
            if link.active and link.key_kind == kind and link.key_value == value:
                link.retracted_at = now
                link.retraction_reason = reason
                outcome.links_retracted.append(link)
        if self._by_key.get((kind, value)) == vessel.canonical_id:
            del self._by_key[(kind, value)]
        if kind == MMSI and value in vessel.mmsis:
            vessel.mmsis.remove(value)
        if kind == IMO and vessel.imo == value:
            vessel.imo = None

    # -- attributes ------------------------------------------------------
    def _hold(
        self,
        vessel: CanonicalVessel,
        assertion: EntityAssertion,
        *,
        now: datetime,
        outcome: FusionOutcome,
    ) -> None:
        """Record the assertion, and let it set the attribute if it outranks."""
        vessel.assertions.append(assertion)
        if assertion.source_kind == OBSERVED_AIS:
            if vessel.last_observed_at is None or assertion.observed_at > vessel.last_observed_at:
                vessel.last_observed_at = assertion.observed_at
        if assertion.attribute == ATTR_IMO and vessel.imo and assertion.value != vessel.imo:
            # The IMO attribute is governed by the identity link, not by the
            # latest claim. A claim that disagrees with the link is evidence
            # (kept above) and a conflict (recorded once), never the value.
            already = any(
                c.attribute == ATTR_IMO and c.claimed == assertion.value and c.at == now
                for c in vessel.conflicts
            )
            if not already:
                conflict = Conflict(
                    canonical_id=vessel.canonical_id, attribute=ATTR_IMO,
                    held=vessel.imo, claimed=assertion.value,
                    held_by="fusion:link", claimed_by=assertion.source_id, at=now,
                    reason="the IMO is governed by the identity link; a differing claim is kept as evidence",
                )
                vessel.conflicts.append(conflict)
                outcome.conflicts.append(conflict)
            return
        held = vessel.attributes.get(assertion.attribute)
        order = PRECEDENCE.get(assertion.attribute, (OBSERVED_AIS, FLEET_REGISTRY, SIMULATED_TRAFFIC))
        rank_new = order.index(assertion.source_kind) if assertion.source_kind in order else len(order)
        if held is None:
            vessel.attributes[assertion.attribute] = _value_of(assertion)
            return
        rank_held = order.index(held.source_kind) if held.source_kind in order else len(order)
        if rank_new < rank_held or (rank_new == rank_held and assertion.observed_at >= held.observed_at):
            if held.value != assertion.value and assertion.attribute in (ATTR_IMO, ATTR_NAME, ATTR_CALLSIGN):
                # A stronger or newer source changing an identity attribute is
                # worth a written conflict even though it wins.
                conflict = Conflict(
                    canonical_id=vessel.canonical_id,
                    attribute=assertion.attribute,
                    held=held.value, claimed=assertion.value,
                    held_by=held.source_id, claimed_by=assertion.source_id,
                    at=now,
                    reason=f"{assertion.source_kind} outranks or postdates {held.source_kind} for {assertion.attribute}",
                )
                vessel.conflicts.append(conflict)
                outcome.conflicts.append(conflict)
            vessel.attributes[assertion.attribute] = _value_of(assertion)
        elif held.value != assertion.value:
            conflict = Conflict(
                canonical_id=vessel.canonical_id,
                attribute=assertion.attribute,
                held=held.value, claimed=assertion.value,
                held_by=held.source_id, claimed_by=assertion.source_id,
                at=now,
                reason=f"{held.source_kind} outranks {assertion.source_kind} for {assertion.attribute}; the claim is kept, not applied",
            )
            vessel.conflicts.append(conflict)
            outcome.conflicts.append(conflict)

    def _index_name(self, vessel: CanonicalVessel) -> None:
        name = _normalise_name(vessel.name)
        if name:
            bucket = self._by_name.setdefault(name, [])
            if vessel.canonical_id not in bucket:
                bucket.append(vessel.canonical_id)

    def _name_candidates(
        self, vessel: CanonicalVessel, *, evidence: Iterable[str], outcome: FusionOutcome,
    ) -> None:
        """Same name, different hull as far as the keys know: a suggestion only."""
        name = _normalise_name(vessel.name)
        if not name:
            return
        for other_id in self._by_name.get(name, []):
            if other_id == vessel.canonical_id:
                continue
            other = self._vessels[other_id]
            if any(c.canonical_id == other_id for c in vessel.candidates):
                continue
            reason = (
                f"same name {vessel.name!r} as {other_id}; a name is not an identifier, "
                "so this is offered for review and has not merged anything"
            )
            forward = Candidate(other_id, NAME, name, reason, tuple(evidence))
            back = Candidate(vessel.canonical_id, NAME, name, reason, tuple(evidence))
            vessel.candidates.append(forward)
            other.candidates.append(back)
            outcome.candidates.append(forward)

    # -- merging ---------------------------------------------------------
    def _merge(
        self, keep: CanonicalVessel, absorb: CanonicalVessel, *, reason: str, now: datetime, outcome: FusionOutcome,
    ) -> None:
        """Fold `absorb` into `keep` because a strong key proved them one hull."""
        for link in absorb.links:
            if link.active:
                link.retracted_at = now
                link.retraction_reason = f"merged into {keep.canonical_id}: {reason}"
                outcome.links_retracted.append(link)
                if link.strength == STRONG:
                    self._link(keep, link.key_kind, link.key_value, strength=STRONG,
                               evidence=link.evidence, reason=f"carried over in merge: {reason}",
                               now=now, outcome=outcome)
            keep.links.append(link)
        for assertion in absorb.assertions:
            self._hold(keep, assertion, now=now, outcome=outcome)
        keep.conflicts.extend(absorb.conflicts)
        keep.candidates.extend(c for c in absorb.candidates if c.canonical_id != keep.canonical_id)
        name = _normalise_name(absorb.name)
        if name and absorb.canonical_id in self._by_name.get(name, []):
            self._by_name[name].remove(absorb.canonical_id)
        del self._vessels[absorb.canonical_id]
        outcome.merged_from = absorb.canonical_id
        outcome.notes.append(f"merged {absorb.canonical_id} into {keep.canonical_id}: {reason}")

    # -- AIS -------------------------------------------------------------
    def ingest_ais(self, observation: AisObservation, *, now: Optional[datetime] = None) -> FusionOutcome:
        """Attach one observation to the hull it is evidence about."""
        moment = now or observation.ingested_at or world_now()
        with self._lock:
            assertions = self._ais_assertions(observation)
            evidence = [a.assertion_id for a in assertions]
            mmsi = observation.mmsi

            by_mmsi = self._by_key.get((MMSI, mmsi))
            by_imo = self._by_key.get((IMO, observation.imo)) if observation.imo else None

            if observation.imo and by_imo is not None:
                vessel = self._vessels[by_imo]
                outcome = FusionOutcome(vessel)
                if by_mmsi is None:
                    self._link(vessel, MMSI, mmsi, strength=STRONG, evidence=evidence,
                               reason=f"transponder {mmsi} reports IMO {observation.imo}, already linked to this hull",
                               now=moment, outcome=outcome)
                elif by_mmsi != by_imo:
                    other = self._vessels[by_mmsi]
                    if other.imo is None:
                        # The MMSI-only hull was this hull all along.
                        self._merge(vessel, other, now=moment, outcome=outcome,
                                    reason=f"transponder {mmsi} now reports IMO {observation.imo}")
                    else:
                        outcome = self._imo_disagreement(other, vessel, observation, evidence, moment)
                        vessel = outcome.canonical
            elif observation.imo and by_mmsi is not None:
                vessel = self._vessels[by_mmsi]
                outcome = FusionOutcome(vessel)
                if vessel.imo is None:
                    self._link(vessel, IMO, observation.imo, strength=STRONG, evidence=evidence,
                               reason=f"static data from transponder {mmsi} stated IMO {observation.imo}",
                               now=moment, outcome=outcome)
                elif vessel.imo != observation.imo:
                    outcome = self._imo_disagreement(vessel, None, observation, evidence, moment)
                    vessel = outcome.canonical
            elif by_mmsi is not None:
                vessel = self._vessels[by_mmsi]
                outcome = FusionOutcome(vessel)
                if self._looks_reassigned(vessel, observation, moment):
                    reason = (
                        f"transponder {mmsi} was silent for longer than {self.mmsi_reuse_window.days} days "
                        f"and returned as {observation.name!r} rather than {vessel.name!r}; "
                        "treated as a possible reassignment, not the same hull"
                    )
                    self._retract(vessel, MMSI, mmsi, reason=reason, now=moment, outcome=outcome)
                    previous = outcome
                    vessel = self._new_canonical(moment)
                    outcome = FusionOutcome(vessel)
                    outcome.created = True
                    outcome.links_retracted.extend(previous.links_retracted)
                    outcome.notes.append(reason)
                    self._link(vessel, MMSI, mmsi, strength=STRONG, evidence=evidence,
                               reason="new hull for a transponder returning after the reuse window",
                               now=moment, outcome=outcome)
            else:
                vessel = self._new_canonical(moment)
                outcome = FusionOutcome(vessel)
                outcome.created = True
                self._link(vessel, MMSI, mmsi, strength=STRONG, evidence=evidence,
                           reason=f"first observation of transponder {mmsi}", now=moment, outcome=outcome)
                if observation.imo:
                    self._link(vessel, IMO, observation.imo, strength=STRONG, evidence=evidence,
                               reason=f"static data from transponder {mmsi} stated IMO {observation.imo}",
                               now=moment, outcome=outcome)

            for assertion in assertions:
                self._hold(vessel, assertion, now=moment, outcome=outcome)
            self._index_name(vessel)
            self._name_candidates(vessel, evidence=evidence, outcome=outcome)
            return outcome

    def _imo_disagreement(
        self,
        current: CanonicalVessel,
        claimed_hull: Optional[CanonicalVessel],
        observation: AisObservation,
        evidence: List[str],
        now: datetime,
    ) -> FusionOutcome:
        """A transponder linked to one IMO now says it has another.

        Not acted on until it repeats. The first time is a conflict on the
        current hull; the Nth consistent time moves the transponder.
        """
        mmsi, imo = observation.mmsi, observation.imo or ""
        counter = (mmsi, imo)
        self._imo_claims[counter] = self._imo_claims.get(counter, 0) + 1
        seen = self._imo_claims[counter]
        outcome = FusionOutcome(current)
        if seen < self.imo_claims_before_move:
            conflict = Conflict(
                canonical_id=current.canonical_id, attribute=ATTR_IMO,
                held=current.imo, claimed=imo, held_by="fusion:link", claimed_by=observation.provider_id,
                at=now,
                reason=(
                    f"transponder {mmsi} reported IMO {imo} once while linked to IMO {current.imo}; "
                    f"not re-identified on a single static report ({seen} of "
                    f"{self.imo_claims_before_move} needed)"
                ),
            )
            current.conflicts.append(conflict)
            outcome.conflicts.append(conflict)
            return outcome

        reason = (
            f"transponder {mmsi} reported IMO {imo} {seen} times in a row while linked to "
            f"IMO {current.imo}; the transponder has moved hull"
        )
        self._retract(current, MMSI, mmsi, reason=reason, now=now, outcome=outcome)
        retracted = list(outcome.links_retracted)
        if claimed_hull is None:
            claimed_hull = self._new_canonical(now)
            moved = FusionOutcome(claimed_hull)
            moved.created = True
            self._link(claimed_hull, IMO, imo, strength=STRONG, evidence=evidence,
                       reason=f"static data from transponder {mmsi} stated IMO {imo}", now=now, outcome=moved)
        else:
            moved = FusionOutcome(claimed_hull)
        moved.links_retracted.extend(retracted)
        moved.notes.append(reason)
        self._link(claimed_hull, MMSI, mmsi, strength=STRONG, evidence=evidence, reason=reason,
                   now=now, outcome=moved)
        del self._imo_claims[counter]
        return moved

    def _looks_reassigned(self, vessel: CanonicalVessel, observation: AisObservation, now: datetime) -> bool:
        if not observation.name or vessel.name is None:
            return False
        if _normalise_name(observation.name) == _normalise_name(vessel.name):
            return False
        last = vessel.last_observed_at
        if last is None:
            return False
        return observation.source_timestamp - last > self.mmsi_reuse_window

    def _ais_assertions(self, observation: AisObservation) -> List[EntityAssertion]:
        common = dict(
            source_id=observation.provider_id,
            source_kind=OBSERVED_AIS,
            subject_kind=MMSI,
            subject_value=observation.mmsi,
            observed_at=observation.source_timestamp,
            ingested_at=observation.ingested_at,
            raw_ref=observation.raw_ref,
            provenance={"message_type": observation.message_type,
                        "source_time_known": observation.provenance.get("source_time_known", True)},
        )
        rows: List[EntityAssertion] = [
            self._assertion(attribute=ATTR_MMSI, value=observation.mmsi,
                            confidence=AIS_POSITION_CONFIDENCE, **common),
        ]
        if observation.message_type in (POSITION_REPORT, STANDARD_CLASS_B):
            rows.append(self._assertion(
                attribute=ATTR_POSITION,
                value={"lat": observation.lat, "lon": observation.lon,
                       "sog": observation.sog_knots, "cog": observation.cog_degrees,
                       "heading": observation.heading_degrees},
                confidence=AIS_POSITION_CONFIDENCE, **common,
            ))
            if observation.nav_status:
                rows.append(self._assertion(attribute=ATTR_NAV_STATUS, value=observation.nav_status,
                                            confidence=AIS_STATIC_CONFIDENCE, **common))
        if observation.message_type == SHIP_STATIC_DATA:
            for attribute, value in (
                (ATTR_IMO, observation.imo), (ATTR_NAME, observation.name),
                (ATTR_CALLSIGN, observation.callsign),
                (ATTR_DESTINATION, observation.destination_text), (ATTR_ETA, observation.eta_text),
            ):
                if value:
                    rows.append(self._assertion(attribute=attribute, value=value,
                                                confidence=AIS_STATIC_CONFIDENCE, **common))
        return rows

    # -- the fleet registry ---------------------------------------------
    def register_fleet_vessel(
        self,
        *,
        vessel_id: str,
        name: str,
        imo: Optional[str],
        source_id: str = "fleet-registry",
        position: Optional[Dict[str, float]] = None,
        position_source_kind: str = SIMULATED_TRAFFIC,
        now: Optional[datetime] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> FusionOutcome:
        """A registry entry: strong on IMO when it has one, a hull of its own when not."""
        moment = now or world_now()
        with self._lock:
            common = dict(
                source_id=source_id, source_kind=FLEET_REGISTRY, subject_kind=FLEET_ID,
                subject_value=vessel_id, observed_at=moment, ingested_at=moment,
                raw_ref=f"fleet:{vessel_id}", provenance=dict(extra or {}),
            )
            assertions = [self._assertion(attribute=ATTR_NAME, value=name,
                                          confidence=REGISTRY_CONFIDENCE, **common)]
            if imo:
                assertions.append(self._assertion(attribute=ATTR_IMO, value=imo,
                                                  confidence=REGISTRY_CONFIDENCE, **common))
            evidence = [a.assertion_id for a in assertions]

            existing = self._by_key.get((FLEET_ID, vessel_id))
            by_imo = self._by_key.get((IMO, imo)) if imo else None
            if existing is not None:
                vessel = self._vessels[existing]
                outcome = FusionOutcome(vessel)
            elif by_imo is not None:
                vessel = self._vessels[by_imo]
                outcome = FusionOutcome(vessel)
                self._link(vessel, FLEET_ID, vessel_id, strength=STRONG, evidence=evidence,
                           reason=f"registry entry {vessel_id} carries IMO {imo}, already linked to this hull",
                           now=moment, outcome=outcome)
            else:
                vessel = self._new_canonical(moment)
                outcome = FusionOutcome(vessel)
                outcome.created = True
                self._link(vessel, FLEET_ID, vessel_id, strength=STRONG, evidence=evidence,
                           reason=f"registry entry {vessel_id}", now=moment, outcome=outcome)
                if imo:
                    self._link(vessel, IMO, imo, strength=STRONG, evidence=evidence,
                               reason=f"registry entry {vessel_id} states IMO {imo}", now=moment, outcome=outcome)
                else:
                    outcome.notes.append(
                        f"registry entry {vessel_id} has no IMO; it can be linked to an observed "
                        "transponder only by a person, never by its name"
                    )
            for assertion in assertions:
                self._hold(vessel, assertion, now=moment, outcome=outcome)
            if position is not None:
                self._hold(vessel, self._assertion(
                    attribute=ATTR_POSITION, value=dict(position), confidence=0.5,
                    **{**common, "source_kind": position_source_kind},
                ), now=moment, outcome=outcome)
            self._index_name(vessel)
            self._name_candidates(vessel, evidence=evidence, outcome=outcome)
            return outcome

    # -- reading ---------------------------------------------------------
    def lookup(self, kind: str, value: str) -> Optional[CanonicalVessel]:
        with self._lock:
            canonical_id = self._by_key.get((kind, str(value)))
            return None if canonical_id is None else self._vessels.get(canonical_id)

    def get(self, canonical_id: str) -> Optional[CanonicalVessel]:
        with self._lock:
            return self._vessels.get(canonical_id)

    def vessels(self) -> List[CanonicalVessel]:
        with self._lock:
            return list(self._vessels.values())

    def explain(self, canonical_id: str) -> Optional[Dict[str, Any]]:
        vessel = self.get(canonical_id)
        return None if vessel is None else vessel.to_dict(include_assertions=True)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            vessels = list(self._vessels.values())
            return {
                "vessels": len(vessels),
                "observed": sum(1 for v in vessels if v.observed),
                "withImo": sum(1 for v in vessels if v.imo),
                "activeLinks": len(self._by_key),
                "conflicts": sum(len(v.conflicts) for v in vessels),
                "candidates": sum(len(v.candidates) for v in vessels),
                "assertions": sum(len(v.assertions) for v in vessels),
            }


def _value_of(assertion: EntityAssertion) -> AttributeValue:
    return AttributeValue(
        value=assertion.value,
        assertion_id=assertion.assertion_id,
        source_id=assertion.source_id,
        source_kind=assertion.source_kind,
        observed_at=assertion.observed_at,
        confidence=assertion.confidence,
    )


# --------------------------------------------------------------------------
# process-wide instance
# --------------------------------------------------------------------------

_ENGINE: Optional[FusionEngine] = None
_ENGINE_LOCK = threading.Lock()


def get_engine() -> FusionEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = FusionEngine()
        return _ENGINE


def reset_engine() -> None:
    global _ENGINE
    with _ENGINE_LOCK:
        _ENGINE = None


__all__ = [
    "DEFAULT_IMO_CLAIMS_BEFORE_MOVE",
    "DEFAULT_MMSI_REUSE_WINDOW",
    "FusionEngine",
    "FusionOutcome",
    "PRECEDENCE",
    "get_engine",
    "reset_engine",
]
