"""Entity fusion: what was asserted, what was linked, and what that makes.

Three shapes, and the discipline between them is the whole design.

An **assertion** is one claim by one source about one attribute of one thing:
"the transponder with MMSI 419001234 said its IMO is 9876543, at 12:04, in
this message". Assertions are never edited and never discarded. They are the
evidence, and the evidence is kept whether or not it was believed.

An **identity link** is the fusion engine's decision that a key -- an IMO, an
MMSI, a fleet id -- refers to a particular canonical vessel, with the strength
of that decision and the assertions it rests on. A link is appended, and
retracted by appending a retraction; it is not rewritten, so the history of
what was believed is recoverable.

A **canonical vessel** is what the links add up to: the identifiers currently
believed to refer to one hull, the best current value of each attribute with
where it came from, and every assertion ever made about it, including the
ones that contradict each other. It is derived, and it can be rebuilt from the
assertions and links at any time.

The rule that keeps this honest is stated once here and enforced in the
engine: **a name is never an identifier.** Two things with the same name are
two things until an IMO or an MMSI says otherwise. A name match produces a
*candidate*, which is a suggestion to a person, and not a link.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------

#: Kinds of source an assertion can come from. A source *kind* is about how
#: much the claim can be trusted to be about the physical world; the source
#: *id* says which provider.
OBSERVED_AIS = "OBSERVED_AIS"
FLEET_REGISTRY = "FLEET_REGISTRY"
SIMULATED_TRAFFIC = "SIMULATED_TRAFFIC"
OPERATOR_INPUT = "OPERATOR_INPUT"

SOURCE_KINDS: Tuple[str, ...] = (OBSERVED_AIS, FLEET_REGISTRY, SIMULATED_TRAFFIC, OPERATOR_INPUT)

#: Keys that can identify a hull, and how strongly.
IMO = "IMO"
MMSI = "MMSI"
FLEET_ID = "FLEET_ID"
NAME = "NAME"

KEY_KINDS: Tuple[str, ...] = (IMO, MMSI, FLEET_ID, NAME)

#: Link strength. STRONG links merge; WEAK links are recorded and shown but
#: never cause two canonical vessels to become one.
STRONG = "STRONG"
WEAK = "WEAK"

#: Attributes an assertion can be about.
ATTR_IMO = "imo"
ATTR_MMSI = "mmsi"
ATTR_NAME = "name"
ATTR_CALLSIGN = "callsign"
ATTR_DESTINATION = "destination_text"
ATTR_ETA = "eta_text"
ATTR_POSITION = "position"
ATTR_NAV_STATUS = "nav_status"


# --------------------------------------------------------------------------
# assertions
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EntityAssertion:
    """One claim, by one source, about one attribute, at one time. Immutable."""

    assertion_id: str
    #: Which provider (``aisstream``, ``fleet-registry``, ``ais-replay``).
    source_id: str
    #: How the claim reached the world: observed, registered, simulated, typed.
    source_kind: str
    #: The key the source used to say *which* thing it was talking about.
    subject_kind: str
    subject_value: str
    attribute: str
    value: Any
    #: When the source says it was true, and when we heard it.
    observed_at: datetime
    ingested_at: datetime
    #: The source's own confidence in this claim, 0..1. An AIS static field
    #: is typed by a crew member and is not 1.0.
    confidence: float = 1.0
    #: A pointer to the raw message or record. Not the record itself.
    raw_ref: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assertionId": self.assertion_id,
            "sourceId": self.source_id,
            "sourceKind": self.source_kind,
            "subject": {"kind": self.subject_kind, "value": self.subject_value},
            "attribute": self.attribute,
            "value": self.value,
            "observedAt": self.observed_at.isoformat(),
            "ingestedAt": self.ingested_at.isoformat(),
            "confidence": self.confidence,
            "rawRef": self.raw_ref,
            "provenance": dict(self.provenance),
        }


# --------------------------------------------------------------------------
# links
# --------------------------------------------------------------------------


@dataclass
class IdentityLink:
    """A key believed to refer to a canonical vessel, and why.

    Appended, never rewritten. A link that stops being believed gets
    ``retracted_at`` and ``retraction_reason`` set and stays in the record.
    """

    link_id: str
    canonical_id: str
    key_kind: str
    key_value: str
    strength: str
    established_at: datetime
    #: The assertion ids this decision rests on.
    evidence: List[str]
    reason: str
    retracted_at: Optional[datetime] = None
    retraction_reason: Optional[str] = None

    @property
    def active(self) -> bool:
        return self.retracted_at is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "linkId": self.link_id,
            "canonicalId": self.canonical_id,
            "key": {"kind": self.key_kind, "value": self.key_value},
            "strength": self.strength,
            "establishedAt": self.established_at.isoformat(),
            "evidence": list(self.evidence),
            "reason": self.reason,
            "active": self.active,
            "retractedAt": None if self.retracted_at is None else self.retracted_at.isoformat(),
            "retractionReason": self.retraction_reason,
        }


@dataclass(frozen=True)
class Candidate:
    """A possible identity the engine will not act on by itself.

    Produced by name matches. Shown to a person; never applied as a link.
    """

    canonical_id: str
    key_kind: str
    key_value: str
    reason: str
    evidence: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonicalId": self.canonical_id,
            "key": {"kind": self.key_kind, "value": self.key_value},
            "strength": WEAK,
            "applied": False,
            "reason": self.reason,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class Conflict:
    """Two sources that cannot both be right, kept rather than resolved."""

    canonical_id: str
    attribute: str
    held: Any
    claimed: Any
    held_by: str
    claimed_by: str
    at: datetime
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonicalId": self.canonical_id,
            "attribute": self.attribute,
            "held": self.held,
            "claimed": self.claimed,
            "heldBy": self.held_by,
            "claimedBy": self.claimed_by,
            "at": self.at.isoformat(),
            "reason": self.reason,
        }


# --------------------------------------------------------------------------
# the canonical entity
# --------------------------------------------------------------------------


@dataclass
class AttributeValue:
    """The current best value of one attribute, and the assertion behind it."""

    value: Any
    assertion_id: str
    source_id: str
    source_kind: str
    observed_at: datetime
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "assertionId": self.assertion_id,
            "sourceId": self.source_id,
            "sourceKind": self.source_kind,
            "observedAt": self.observed_at.isoformat(),
            "confidence": self.confidence,
        }


@dataclass
class CanonicalVessel:
    """One hull as the links currently describe it. Derived; rebuildable."""

    canonical_id: str
    created_at: datetime
    #: Identifiers currently linked. Several MMSIs can be linked to one IMO
    #: over time (reflagging); at most one IMO is ever linked.
    imo: Optional[str] = None
    mmsis: List[str] = field(default_factory=list)
    fleet_ids: List[str] = field(default_factory=list)
    #: Best current value per attribute, with its provenance.
    attributes: Dict[str, AttributeValue] = field(default_factory=dict)
    #: Everything ever said about this vessel, in arrival order.
    assertions: List[EntityAssertion] = field(default_factory=list)
    links: List[IdentityLink] = field(default_factory=list)
    conflicts: List[Conflict] = field(default_factory=list)
    candidates: List[Candidate] = field(default_factory=list)
    last_observed_at: Optional[datetime] = None

    @property
    def sources(self) -> List[str]:
        seen: List[str] = []
        for assertion in self.assertions:
            if assertion.source_id not in seen:
                seen.append(assertion.source_id)
        return seen

    @property
    def source_kinds(self) -> List[str]:
        seen: List[str] = []
        for assertion in self.assertions:
            if assertion.source_kind not in seen:
                seen.append(assertion.source_kind)
        return seen

    @property
    def observed(self) -> bool:
        """Whether any assertion about this hull was an actual observation."""
        return OBSERVED_AIS in self.source_kinds

    def attribute(self, name: str) -> Any:
        held = self.attributes.get(name)
        return None if held is None else held.value

    @property
    def name(self) -> Optional[str]:
        return self.attribute(ATTR_NAME)

    def to_dict(self, *, include_assertions: bool = False) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "canonicalId": self.canonical_id,
            "createdAt": self.created_at.isoformat(),
            "imo": self.imo,
            "mmsis": list(self.mmsis),
            "fleetIds": list(self.fleet_ids),
            "name": self.name,
            "attributes": {k: v.to_dict() for k, v in self.attributes.items()},
            "sources": self.sources,
            "sourceKinds": self.source_kinds,
            "observed": self.observed,
            "links": [link.to_dict() for link in self.links],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "candidates": [c.to_dict() for c in self.candidates],
            "assertionCount": len(self.assertions),
            "lastObservedAt": (
                None if self.last_observed_at is None else self.last_observed_at.isoformat()
            ),
        }
        if include_assertions:
            body["assertions"] = [a.to_dict() for a in self.assertions]
        return body


__all__ = [
    "ATTR_CALLSIGN",
    "ATTR_DESTINATION",
    "ATTR_ETA",
    "ATTR_IMO",
    "ATTR_MMSI",
    "ATTR_NAME",
    "ATTR_NAV_STATUS",
    "ATTR_POSITION",
    "AttributeValue",
    "Candidate",
    "CanonicalVessel",
    "Conflict",
    "EntityAssertion",
    "FLEET_ID",
    "FLEET_REGISTRY",
    "IMO",
    "IdentityLink",
    "KEY_KINDS",
    "MMSI",
    "NAME",
    "OBSERVED_AIS",
    "OPERATOR_INPUT",
    "SIMULATED_TRAFFIC",
    "SOURCE_KINDS",
    "STRONG",
    "WEAK",
]
