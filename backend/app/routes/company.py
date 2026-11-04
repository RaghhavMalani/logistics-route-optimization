"""Compatibility import for one release. Use backend.app.domains.voyages.company."""

import sys

from backend.app.domains.voyages import company as _implementation

sys.modules[__name__] = _implementation
