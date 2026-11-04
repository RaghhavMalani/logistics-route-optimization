"""Compatibility import for one release. Use backend.app.domains.ports.arrivals."""

import sys

from backend.app.domains.ports import arrivals as _implementation

sys.modules[__name__] = _implementation
