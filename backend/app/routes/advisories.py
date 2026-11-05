"""Compatibility import for one release. Use backend.app.domains.advisories.advisories."""

import sys

from backend.app.domains.advisories import advisories as _implementation

sys.modules[__name__] = _implementation
