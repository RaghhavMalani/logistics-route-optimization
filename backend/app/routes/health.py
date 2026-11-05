"""Compatibility import for one release. Use backend.app.domains.system.health."""

import sys

from backend.app.domains.system import health as _implementation

sys.modules[__name__] = _implementation
