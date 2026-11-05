"""Compatibility import for one release. Use backend.app.domains.ports.weather_verification."""

import sys

from backend.app.domains.ports import weather_verification as _implementation

sys.modules[__name__] = _implementation
