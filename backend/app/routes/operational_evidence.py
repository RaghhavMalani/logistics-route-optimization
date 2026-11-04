"""Compatibility import for one release. Use backend.app.domains.intelligence.operational_evidence."""

import sys

from backend.app.domains.intelligence import operational_evidence as _implementation

sys.modules[__name__] = _implementation
