"""Compatibility import for one release. Use backend.app.domains.intelligence.intelligence."""

import sys

from backend.app.domains.intelligence import intelligence as _implementation

sys.modules[__name__] = _implementation
