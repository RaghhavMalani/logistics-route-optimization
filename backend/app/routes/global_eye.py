"""Compatibility import for one release. Use backend.app.domains.world.global_eye."""

import sys

from backend.app.domains.world import global_eye as _implementation

sys.modules[__name__] = _implementation
