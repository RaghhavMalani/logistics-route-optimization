"""Compatibility import for one release. Use backend.app.domains.world.news."""

import sys

from backend.app.domains.world import news as _implementation

sys.modules[__name__] = _implementation
