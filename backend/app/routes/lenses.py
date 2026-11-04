"""Compatibility import for one release. Use backend.app.domains.world.lenses."""

import sys

from backend.app.domains.world import lenses as _implementation

sys.modules[__name__] = _implementation
