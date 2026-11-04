"""Compatibility import for one release. Use backend.app.domains.voyages.scenarios."""

import sys

from backend.app.domains.voyages import scenarios as _implementation

sys.modules[__name__] = _implementation
