"""Compatibility import for one release. Use backend.app.domains.intelligence.public_research."""

import sys

from backend.app.domains.intelligence import public_research as _implementation

sys.modules[__name__] = _implementation
