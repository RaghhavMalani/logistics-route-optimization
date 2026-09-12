"""The fabric's public face over the product catalogue.

`SignalFabric` used to hold its own provider-level licence booleans. That model
was too coarse -- Open-Meteo is one provider whose free and paid products give
opposite answers to "may we use this commercially" -- and it was wrong in one
place, recording AISStream as non-commercial on nobody's evidence. Both live in
:mod:`~src.portwatch_os.fabric.products` now, and this module keeps the name
the API and adapters already use while delegating every decision there.

A resolution answers with a *product*. Callers that only want the provider get
it through the product, which is the direction the truth actually flows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.portwatch_os.fabric.model import COMMERCIAL, MODES
from src.portwatch_os.fabric.products import (
    ProductCatalogue,
    ProductResolution,
    Provider,
    ProviderProduct,
    default_catalogue,
)


class SignalFabric:
    """The provider registry, resolved at product granularity."""

    def __init__(
        self,
        providers: Optional[Sequence[Provider]] = None,
        *,
        mode: str = COMMERCIAL,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"{mode!r} is not a deployment mode")
        self.mode = mode
        self._catalogue = ProductCatalogue(providers, mode=mode)

    # -- reading ---------------------------------------------------------
    def providers(self) -> List[Provider]:
        return self._catalogue.providers()

    def get(self, provider_id: str) -> Optional[Provider]:
        return next(
            (p for p in self._catalogue.providers() if p.provider_id == provider_id),
            None,
        )

    def product(self, product_id: str) -> Optional[ProviderProduct]:
        found = self._catalogue.product(product_id)
        return None if found is None else found[1]

    def products(self, *, capability: Optional[str] = None) -> List[ProviderProduct]:
        return [product for _, product in self._catalogue.products(capability=capability)]

    # -- resolution ------------------------------------------------------
    def resolve(
        self,
        capability: str,
        *,
        mode: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> ProductResolution:
        """The best legally usable product for a capability, or UNAVAILABLE."""
        return self._catalogue.resolve(capability, mode=mode, now=now)

    def report(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        return self._catalogue.report(now=now)


_DEFAULT: Optional[SignalFabric] = None


def get_fabric(mode: str = COMMERCIAL) -> SignalFabric:
    """The process-wide fabric. Mode is a deployment property, not a request one."""
    global _DEFAULT
    if _DEFAULT is None or _DEFAULT.mode != mode:
        _DEFAULT = SignalFabric(mode=mode)
    return _DEFAULT


__all__ = ["SignalFabric", "default_catalogue", "get_fabric"]
