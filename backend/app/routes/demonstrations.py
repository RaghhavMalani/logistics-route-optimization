"""Compatibility import for one release. Use backend.app.domains.voyages.demonstrations."""

import sys

from backend.app.domains.voyages import demonstrations as _implementation

sys.modules[__name__] = _implementation
