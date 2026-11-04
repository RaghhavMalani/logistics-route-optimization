"""Compatibility import for one release. Use backend.app.domains.ports.port_twin."""

import sys

from backend.app.domains.ports import port_twin as _implementation

sys.modules[__name__] = _implementation
