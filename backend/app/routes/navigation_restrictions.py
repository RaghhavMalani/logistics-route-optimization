"""Compatibility import for one release. Use backend.app.domains.intelligence.navigation_restrictions."""

import sys

from backend.app.domains.intelligence import navigation_restrictions as _implementation

sys.modules[__name__] = _implementation
