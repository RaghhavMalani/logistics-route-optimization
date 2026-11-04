"""Compatibility import for one release. Use backend.app.domains.ports.weather."""

import sys

from backend.app.domains.ports import weather as _implementation

sys.modules[__name__] = _implementation
