"""Compatibility import for one release. Use backend.app.domains.intelligence.operational_notices."""

import sys

from backend.app.domains.intelligence import operational_notices as _implementation

sys.modules[__name__] = _implementation
