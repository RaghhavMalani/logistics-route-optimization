"""Compatibility import for one release. Use backend.app.domains.voyages.finance."""

import sys

from backend.app.domains.voyages import finance as _implementation

sys.modules[__name__] = _implementation
