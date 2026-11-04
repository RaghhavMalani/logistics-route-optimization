"""Compatibility import for one release. Use backend.app.domains.ports.model."""

import sys

from backend.app.domains.ports import model as _implementation

sys.modules[__name__] = _implementation
