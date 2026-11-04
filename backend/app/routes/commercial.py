"""Compatibility import for one release. Use backend.app.domains.voyages.commercial."""

import sys

from backend.app.domains.voyages import commercial as _implementation

sys.modules[__name__] = _implementation
