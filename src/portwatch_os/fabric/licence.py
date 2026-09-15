"""Licence policy, at the granularity where it is actually true.

A provider is not licensed. A *product* is. Open-Meteo's free endpoint is
non-commercial and its paid plans are not; the same organisation, the same
data, two different answers to "may we sell what this produced". A registry
that put one boolean on the provider would be wrong about one of them, and the
first version of this fabric was.

The second thing this corrects is confidence. The first registry recorded
AISStream as non-commercial. On checking, AISStream publishes no terms for its
data service at all -- not on its homepage, not in its documentation, not in
its repository. "Non-commercial" was an inference, and an inference about a
licence is worse than an admission of ignorance, because it will be quoted as
fact by whoever reads it next. So every permission here is one of four states,
and two of those states are ways of saying *we do not know*:

    ALLOWED           the published terms permit it
    PROHIBITED        the published terms forbid it
    REQUIRES_REVIEW   terms exist and a person has to read them, or none were
                      found and a person has to ask
    UNKNOWN           nobody has looked yet

Neither REQUIRES_REVIEW nor UNKNOWN resolves for a paying deployment. That is
the property the resolver enforces: a commercial product cannot be built on a
source whose permission to use it is a guess.

Every policy carries its evidence -- what was checked, when, and what it said.
A licence claim without its evidence is a licence claim that cannot be
re-verified, and terms change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

ALLOWED = "ALLOWED"
PROHIBITED = "PROHIBITED"
REQUIRES_REVIEW = "REQUIRES_REVIEW"
UNKNOWN = "UNKNOWN"

PERMISSION_STATES: Tuple[str, ...] = (ALLOWED, PROHIBITED, REQUIRES_REVIEW, UNKNOWN)

#: Credential a product needs, so the health surface can say what is missing.
NO_CREDENTIAL = "none"
API_KEY = "api_key"
CONTRACT = "contract"

CREDENTIAL_TYPES: Tuple[str, ...] = (NO_CREDENTIAL, API_KEY, CONTRACT)


class LicenceError(ValueError):
    """A policy was declared that this registry cannot reason about."""


@dataclass(frozen=True)
class TermsEvidence:
    """What was actually read, and when.

    ``finding`` is the quoted text or the explicit absence. An empty finding
    with a reviewed date would be a claim that somebody looked and saw nothing
    worth writing down, which is not the same as finding nothing.
    """

    #: Every URL checked, including ones that turned out to say nothing.
    checked_urls: Tuple[str, ...]
    #: ISO date the terms were read.
    reviewed_at: str
    #: The relevant wording, quoted, or the explicit statement that none exists.
    finding: str
    #: The canonical terms page, where one exists.
    terms_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkedUrls": list(self.checked_urls),
            "reviewedAt": self.reviewed_at,
            "finding": self.finding,
            "termsUrl": self.terms_url,
        }


@dataclass(frozen=True)
class LicencePolicy:
    """What one product's terms permit, in four-state form."""

    commercial_use: str
    government_use: str
    redistribution: str
    #: ALLOWED here means "attribution is not required"; PROHIBITED is not a
    #: meaningful value. Recorded as `attribution_required` for clarity.
    attribution_required: bool
    evidence: TermsEvidence
    #: The data licence, where the provider names one (e.g. CC-BY 4.0).
    data_licence: Optional[str] = None
    summary: str = ""

    def __post_init__(self) -> None:
        for name in ("commercial_use", "government_use", "redistribution"):
            value = getattr(self, name)
            if value not in PERMISSION_STATES:
                raise LicenceError(f"{name}={value!r} is not a permission state")

    def permits(self, mode: str) -> Tuple[bool, Optional[str]]:
        """Whether this policy allows a deployment mode, and why not.

        RESEARCH and DEMO are non-commercial uses, so a non-commercial licence
        permits them. COMMERCIAL requires an explicit ALLOWED -- a permission we
        have not verified is not a permission. GOVERNMENT additionally needs
        redistribution, because output is shared between agencies.
        """
        if mode in ("RESEARCH", "DEMO"):
            return True, None

        if mode == "COMMERCIAL":
            return _require(self.commercial_use, "commercial use")

        if mode == "GOVERNMENT":
            ok, reason = _require(self.government_use, "government use")
            if not ok:
                return ok, reason
            return _require(self.redistribution, "redistribution between agencies")

        return False, f"{mode!r} is not a deployment mode"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commercialUse": self.commercial_use,
            "governmentUse": self.government_use,
            "redistribution": self.redistribution,
            "attributionRequired": self.attribution_required,
            "dataLicence": self.data_licence,
            "summary": self.summary,
            "evidence": self.evidence.to_dict(),
        }


def _require(state: str, what: str) -> Tuple[bool, Optional[str]]:
    if state == ALLOWED:
        return True, None
    if state == PROHIBITED:
        return False, f"the published terms prohibit {what}"
    if state == REQUIRES_REVIEW:
        return False, (
            f"{what} requires review: the terms either need a person to read them "
            "or could not be found, and a permission we have not verified is not "
            "a permission"
        )
    return False, f"{what} is unknown: nobody has checked the terms yet"


# --------------------------------------------------------------------------
# reusable policies, each with its evidence
# --------------------------------------------------------------------------

#: Public-domain or CC-BY open data. Attribution is the only obligation.
OPEN_DATA = LicencePolicy(
    commercial_use=ALLOWED,
    government_use=ALLOWED,
    redistribution=ALLOWED,
    attribution_required=True,
    evidence=TermsEvidence(
        checked_urls=(),
        reviewed_at="2026-09-12",
        finding="Open data with an attribution requirement; see product notes.",
    ),
    summary="Open data. Commercial use and redistribution permitted with attribution.",
)

#: Nothing published. The honest state, and the one that blocks commercial use.
NO_TERMS_FOUND = TermsEvidence(
    checked_urls=(),
    reviewed_at="2026-09-12",
    finding="No terms of use or data licence were found at the URLs checked.",
)


__all__ = [
    "ALLOWED",
    "API_KEY",
    "CONTRACT",
    "CREDENTIAL_TYPES",
    "LicenceError",
    "LicencePolicy",
    "NO_CREDENTIAL",
    "NO_TERMS_FOUND",
    "OPEN_DATA",
    "PERMISSION_STATES",
    "PROHIBITED",
    "REQUIRES_REVIEW",
    "TermsEvidence",
    "UNKNOWN",
]
