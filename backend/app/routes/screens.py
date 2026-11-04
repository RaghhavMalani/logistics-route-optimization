"""Compatibility import for one release. Use backend.app.domains.system.screens."""

import sys

from backend.app.domains.system import screens as _implementation

sys.modules[__name__] = _implementation
