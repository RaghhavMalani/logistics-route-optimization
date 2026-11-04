"""Compatibility import for one release. Use backend.app.domains.ports.ports."""

import sys

from backend.app.domains.ports import ports as _implementation

sys.modules[__name__] = _implementation
