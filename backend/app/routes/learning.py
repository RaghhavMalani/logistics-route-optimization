"""Compatibility import for one release. Use backend.app.domains.intelligence.learning."""

import sys

from backend.app.domains.intelligence import learning as _implementation

sys.modules[__name__] = _implementation
