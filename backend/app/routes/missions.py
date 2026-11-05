"""Compatibility import for one release. Use backend.app.domains.voyages.missions."""

import sys

from backend.app.domains.voyages import missions as _implementation

sys.modules[__name__] = _implementation
