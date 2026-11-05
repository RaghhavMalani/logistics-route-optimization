"""Compatibility import for one release. Use backend.app.domains.ports.port_context."""

import sys

from backend.app.domains.ports import port_context as _implementation

sys.modules[__name__] = _implementation
