"""Compatibility import for one release. Use backend.app.domains.voyages.decisions."""

import sys

from backend.app.domains.voyages import decisions as _implementation

sys.modules[__name__] = _implementation
