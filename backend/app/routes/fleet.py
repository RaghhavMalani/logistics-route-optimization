"""Compatibility import for one release. Use backend.app.domains.voyages.fleet."""

import sys

from backend.app.domains.voyages import fleet as _implementation

sys.modules[__name__] = _implementation
