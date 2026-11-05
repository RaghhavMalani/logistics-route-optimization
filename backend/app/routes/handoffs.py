"""Compatibility import for one release. Use backend.app.domains.advisories.handoffs."""

import sys

from backend.app.domains.advisories import handoffs as _implementation

sys.modules[__name__] = _implementation
