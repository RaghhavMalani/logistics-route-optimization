"""Compatibility import for one release. Use backend.app.domains.intelligence.capabilities."""

import sys

from backend.app.domains.intelligence import capabilities as _implementation

sys.modules[__name__] = _implementation
