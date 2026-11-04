"""Compatibility import for one release. Use backend.app.domains.intelligence.shared_feedback."""

import sys

from backend.app.domains.intelligence import shared_feedback as _implementation

sys.modules[__name__] = _implementation
