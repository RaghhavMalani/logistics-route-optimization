"""Compatibility import for one release. Use backend.app.domains.world.sar."""

import sys

from backend.app.domains.world import sar as _implementation

sys.modules[__name__] = _implementation
