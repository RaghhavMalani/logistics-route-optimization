"""Compatibility import for one release. Use backend.app.domains.system.provenance."""

import sys

from backend.app.domains.system import provenance as _implementation

sys.modules[__name__] = _implementation
