"""Compatibility import for one release. Use backend.app.domains.world.world."""

import sys

from backend.app.domains.world import world as _implementation

sys.modules[__name__] = _implementation
